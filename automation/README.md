# NSMITTY automation

Two independent user services manage the seven-day engineering run:

- `nssmitty-antigravity.service`: continuous AGY worker with deadline, lock,
  completion marker, timeout, rate-limit detection, and exponential backoff.
- `nssmitty-telegram.service`: restricted Telegram long-polling control plane.

The Telegram bot accepts only the configured private numeric user and chat IDs.
It exposes `/status`, `/progress`, `/log`, `/errors`, plus confirmed `/pause`,
`/resume`, `/stop`, and `/restart` actions. It never accepts arbitrary shell
commands or AGY prompts.

## Runtime files

All runtime files are ignored by Git:

- `.antigravity-deadline`: Unix timestamp at which the worker stops.
- `.antigravity-stop`: pause/stop marker.
- `.antigravity-complete`: written only after verified MVP completion.
- `.antigravity-runner-status`: current runner state.
- `.antigravity-backoff`: persisted retry class and delay.
- `.antigravity-runs/`: per-session output and runner errors.
- `.telegram-update-offset`: prevents replaying Telegram updates.
- `.telegram-control-audit.log`: control-plane audit trail.

Telegram credentials are read from
`/home/nytr/.config/nssmitty-telegram/env`, which must be mode `0600` and must
not be committed.

Version-controlled unit templates are stored in `automation/systemd/`. Install
them into `~/.config/systemd/user/`, run `systemctl --user daemon-reload`, and
enable only the Telegram service until the final worker smoke test and deadline
setup are complete.

The worker launches every headless turn with `--new-project` so the workspace is
the NSMITTY repository rather than the broader trusted home directory. Progress
continues through Git history and the tracked MVP state files.

## Start a seven-day run

Review the repository, prompt, permissions, and RHEL 9 test environment first.
Then set the deadline and start the worker:

```sh
date -d '+7 days' +%s > /home/nytr/nssmitty/.antigravity-deadline
rm -f /home/nytr/nssmitty/.antigravity-stop
systemctl --user start nssmitty-antigravity.service
```

Do not create the deadline until the final smoke test has passed.
The deadline is a maximum safety limit. A verified completion marker stops the
worker immediately, even when substantial time remains.

## Local verification

```sh
bash -n automation/run-antigravity-stream.sh
python3 -m py_compile automation/telegram_bot.py
python3 -m unittest discover -s tests -v
```
