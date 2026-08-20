import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "automation" / "telegram_bot.py"
SPEC = importlib.util.spec_from_file_location("telegram_bot", MODULE_PATH)
telegram_bot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = telegram_bot
SPEC.loader.exec_module(telegram_bot)


class TelegramBotHelpersTest(unittest.TestCase):
    def test_load_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env"
            path.write_text(
                "TELEGRAM_BOT_TOKEN=secret\n"
                "TELEGRAM_ALLOWED_USER_ID=123\n"
                "# comment\n",
                encoding="utf-8",
            )
            values = telegram_bot.load_env(path)
            self.assertEqual(values["TELEGRAM_BOT_TOKEN"], "secret")
            self.assertEqual(values["TELEGRAM_ALLOWED_USER_ID"], "123")

    def test_load_env_rejects_invalid_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env"
            path.write_text("BAD KEY=value\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                telegram_bot.load_env(path)

    def test_tail_text_bounds_and_strips_ansi(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "log"
            path.write_text("old\n\x1b[31msecret\x1b[0m\nlast\n", encoding="utf-8")
            self.assertEqual(telegram_bot.tail_text(path, lines=2), "secret\nlast")

    def test_redacts_credentials(self):
        text = (
            "token=hidden-value "
            "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi_123 "
            "Bearer abc.def.ghi"
        )
        redacted = telegram_bot.redact_text(text)
        self.assertNotIn("hidden-value", redacted)
        self.assertNotIn("ABCDEFGHIJ", redacted)
        self.assertNotIn("abc.def.ghi", redacted)

    def test_control_actions_are_fixed(self):
        self.assertEqual(
            set(telegram_bot.CONTROL_ACTIONS),
            {"pause", "resume", "stop", "restart"},
        )

    def test_read_fields_and_shorten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.md"
            path.write_text("# State\n\n- Status: running\n- Next: fix tests\n")
            self.assertEqual(
                telegram_bot.read_fields(path),
                {"status": "running", "next": "fix tests"},
            )
        self.assertEqual(telegram_bot.shorten("a   b"), "a b")
        self.assertEqual(telegram_bot.shorten("abcdef", 4), "abc…")

    def test_checklist_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backlog.md"
            path.write_text("- [x] done\n- [ ] todo\n- [X] done too\n")
            self.assertEqual(telegram_bot.checklist_progress(path), (2, 3))

    def test_button_commands_are_fixed(self):
        self.assertEqual(telegram_bot.BUTTON_COMMANDS["📍 상태"], "/status")
        self.assertEqual(telegram_bot.BUTTON_COMMANDS["▶️ 재개"], "/resume")
        self.assertTrue(telegram_bot.MAIN_KEYBOARD["is_persistent"])


if __name__ == "__main__":
    unittest.main()
