#!/usr/bin/env python3
"""Restricted Telegram control plane for the NSMITTY AGY worker."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = Path(os.environ.get("NSSMITTY_REPO", "/home/nytr/nssmitty"))
ENV_FILE = Path(
    os.environ.get(
        "NSSMITTY_TELEGRAM_ENV",
        "/home/nytr/.config/nssmitty-telegram/env",
    )
)
WORKER_SERVICE = "nssmitty-antigravity.service"
OFFSET_FILE = REPO / ".telegram-update-offset"
AUDIT_FILE = REPO / ".telegram-control-audit.log"
STOP_FILE = REPO / ".antigravity-stop"
STATUS_FILE = REPO / ".antigravity-runner-status"
DEADLINE_FILE = REPO / ".antigravity-deadline"
LOG_DIR = REPO / ".antigravity-runs"

CONTROL_ACTIONS = {
    "pause": "현재 세션을 종료하고 자동 재시작을 일시정지합니다.",
    "resume": "일시정지를 해제하고 AGY 작업기를 시작합니다.",
    "stop": "AGY 작업기와 하위 프로세스를 즉시 중지합니다.",
    "restart": "AGY 작업기와 하위 프로세스를 다시 시작합니다.",
}


def redact_text(text: str) -> str:
    patterns = (
        (r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b", "[REDACTED_BOT_TOKEN]"),
        (r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]"),
        (
            r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s]+",
            r"\1=[REDACTED]",
        ),
    )
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"invalid environment entry for {key!r}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def tail_text(path: Path, lines: int = 50, max_chars: int = 3500) -> str:
    if not path.is_file():
        return "기록이 없습니다."
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    text = "\n".join(data)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return redact_text(text[-max_chars:]) or "기록이 없습니다."


def run_fixed(args: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        result = subprocess.run(
            args,
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


@dataclass
class PendingAction:
    action: str
    user_id: int
    chat_id: int
    expires_at: float


class TelegramBot:
    def __init__(self, token: str, user_id: int, chat_id: int) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}/"
        self.user_id = user_id
        self.chat_id = chat_id
        self.pending: dict[str, PendingAction] = {}
        self.offset = self._read_offset()

    def _read_offset(self) -> int:
        try:
            return int(OFFSET_FILE.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return 0

    def _save_offset(self) -> None:
        tmp = OFFSET_FILE.with_suffix(".tmp")
        tmp.write_text(f"{self.offset}\n", encoding="ascii")
        tmp.replace(OFFSET_FILE)

    def api(self, method: str, payload: dict[str, object]) -> dict[str, object]:
        encoded = urllib.parse.urlencode(
            {
                key: json.dumps(value) if isinstance(value, (dict, list)) else value
                for key, value in payload.items()
            }
        ).encode()
        request = urllib.request.Request(self.base_url + method, data=encoded)
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
        if not result.get("ok"):
            raise RuntimeError(str(result.get("description", "Telegram API error")))
        return result

    def send(self, text: str, reply_markup: dict[str, object] | None = None) -> None:
        payload: dict[str, object] = {"chat_id": self.chat_id, "text": text[:4096]}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self.api("sendMessage", payload)

    def answer_callback(self, callback_id: str, text: str) -> None:
        self.api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})

    def authorized(self, update: dict[str, object]) -> bool:
        message = update.get("message") or {}
        callback = update.get("callback_query") or {}
        source = callback.get("from") or message.get("from") or {}
        chat = message.get("chat") or (callback.get("message") or {}).get("chat") or {}
        return (
            source.get("id") == self.user_id
            and chat.get("id") == self.chat_id
            and chat.get("type") == "private"
        )

    def audit(self, action: str, result: str) -> None:
        with AUDIT_FILE.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} "
                f"user={self.user_id} action={action} result={result}\n"
            )

    def status(self) -> str:
        rc, unit = run_fixed(
            ["systemctl", "--user", "is-active", WORKER_SERVICE], timeout=5
        )
        runner = tail_text(STATUS_FILE, lines=20, max_chars=1200)
        paused = STOP_FILE.exists()
        deadline = "설정되지 않음"
        try:
            seconds = int(DEADLINE_FILE.read_text(encoding="ascii").strip()) - int(time.time())
            deadline = "만료" if seconds <= 0 else f"{seconds // 3600}시간 {seconds % 3600 // 60}분 남음"
        except (OSError, ValueError):
            pass
        return (
            "NSMITTY AGY 상태\n"
            f"service: {unit or 'unknown'} (rc={rc})\n"
            f"paused: {'yes' if paused else 'no'}\n"
            f"deadline: {deadline}\n\n{runner}"
        )

    def progress(self) -> str:
        state = tail_text(REPO / "MVP_STATE.md", lines=80, max_chars=2700)
        _, commits = run_fixed(["git", "log", "--oneline", "-5"], timeout=5)
        return f"MVP 진행 상태\n\n{state}\n\n최근 commit\n{commits or '없음'}"

    def recent_log(self) -> str:
        logs = sorted(LOG_DIR.glob("*.log"), key=lambda item: item.stat().st_mtime)
        if not logs:
            return "AGY 실행 로그가 아직 없습니다."
        return f"최근 로그: {logs[-1].name}\n\n{tail_text(logs[-1])}"

    def errors(self) -> str:
        return "최근 runner 오류\n\n" + tail_text(LOG_DIR / "runner-error.log")

    def request_control(self, action: str) -> None:
        now = time.monotonic()
        self.pending = {
            key: value for key, value in self.pending.items() if value.expires_at >= now
        }
        token = secrets.token_urlsafe(12)
        self.pending[token] = PendingAction(
            action=action,
            user_id=self.user_id,
            chat_id=self.chat_id,
            expires_at=now + 60,
        )
        keyboard = {
            "inline_keyboard": [[
                {"text": "확인", "callback_data": f"confirm:{token}"},
                {"text": "취소", "callback_data": f"cancel:{token}"},
            ]]
        }
        self.send(f"⚠️ {CONTROL_ACTIONS[action]}\n60초 안에 확인하세요.", keyboard)

    def execute_control(self, pending: PendingAction) -> tuple[bool, str]:
        action = pending.action
        if action == "pause":
            STOP_FILE.touch(mode=0o600, exist_ok=True)
            rc, output = run_fixed(
                ["systemctl", "--user", "stop", WORKER_SERVICE], 30
            )
        elif action == "resume":
            STOP_FILE.unlink(missing_ok=True)
            rc, output = run_fixed(["systemctl", "--user", "start", WORKER_SERVICE])
        elif action == "stop":
            STOP_FILE.touch(mode=0o600, exist_ok=True)
            rc, output = run_fixed(["systemctl", "--user", "stop", WORKER_SERVICE], 30)
        elif action == "restart":
            STOP_FILE.unlink(missing_ok=True)
            rc, output = run_fixed(["systemctl", "--user", "restart", WORKER_SERVICE], 30)
        else:
            return False, "알 수 없는 제어 동작입니다."
        return rc == 0, output or ("완료" if rc == 0 else f"실패(rc={rc})")

    def handle_callback(self, callback: dict[str, object]) -> None:
        callback_id = str(callback.get("id", ""))
        data = str(callback.get("data", ""))
        verb, separator, token = data.partition(":")
        pending = self.pending.pop(token, None) if separator else None
        if not pending or pending.expires_at < time.monotonic():
            self.answer_callback(callback_id, "요청이 없거나 만료되었습니다.")
            return
        if verb == "cancel":
            self.audit(pending.action, "cancelled")
            self.answer_callback(callback_id, "취소했습니다.")
            self.send(f"{pending.action} 요청을 취소했습니다.")
            return
        if verb != "confirm":
            self.answer_callback(callback_id, "잘못된 요청입니다.")
            return
        ok, result = self.execute_control(pending)
        self.audit(pending.action, "success" if ok else f"failed:{result}")
        self.answer_callback(callback_id, "처리했습니다." if ok else "실패했습니다.")
        self.send(f"{pending.action}: {result}")

    def handle_message(self, message: dict[str, object]) -> None:
        text = str(message.get("text", "")).strip().split("@", 1)[0]
        command = text.split(maxsplit=1)[0].lower()
        if command in {"/start", "/help"}:
            self.send(
                "NSMITTY AGY 관리 봇\n\n"
                "조회: /status /progress /log /errors\n"
                "제어(2단계 확인): /pause /resume /stop /restart"
            )
        elif command == "/status":
            self.send(self.status())
        elif command == "/progress":
            self.send(self.progress())
        elif command == "/log":
            self.send(self.recent_log())
        elif command == "/errors":
            self.send(self.errors())
        elif command.lstrip("/") in CONTROL_ACTIONS:
            self.request_control(command.lstrip("/"))
        else:
            self.send("지원하지 않는 명령입니다. /help를 사용하세요.")

    def handle_update(self, update: dict[str, object]) -> None:
        if not self.authorized(update):
            self.audit("unauthorized", "rejected")
            return
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            self.handle_callback(callback)
            return
        message = update.get("message")
        if isinstance(message, dict):
            self.handle_message(message)

    def run(self) -> None:
        self.send("NSMITTY Telegram 관리 봇이 시작되었습니다. /help")
        backoff = 5
        while True:
            try:
                response = self.api(
                    "getUpdates",
                    {
                        "offset": self.offset,
                        "timeout": 45,
                        "allowed_updates": ["message", "callback_query"],
                    },
                )
                for update in response.get("result", []):
                    self.offset = int(update["update_id"]) + 1
                    self.handle_update(update)
                    self._save_offset()
                backoff = 5
            except (OSError, urllib.error.URLError, RuntimeError, ValueError) as exc:
                # urllib exceptions may contain the complete Bot API URL. Never
                # render the exception itself because that URL embeds the token.
                print(
                    f"telegram polling error: {type(exc).__name__}",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 900)


def main() -> int:
    try:
        values = load_env(ENV_FILE)
        token = values["TELEGRAM_BOT_TOKEN"]
        user_id = int(values["TELEGRAM_ALLOWED_USER_ID"])
        chat_id = int(values["TELEGRAM_ALLOWED_CHAT_ID"])
        if not token or user_id <= 0 or chat_id <= 0:
            raise ValueError("empty or invalid Telegram configuration")
    except (OSError, KeyError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    TelegramBot(token, user_id, chat_id).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
