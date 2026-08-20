# MVP State

- Status: corrective work required (completion rejected 2026-08-20T15:40:00+09:00)
- Deadline: 2026-08-27T14:55:39+09:00
- Milestone: Completion claim failed independent verification
- Active task: Correct screen parser/definitions and structured argv handling, then verify the real build and package.
- Blockers: Pascal compiler/build availability and the claimed PTY failure must be resolved or documented as an unmet acceptance criterion; they cannot be treated as successful verification.
- Tests passing: 11 of 13 Python tests in the 2026-08-20 independent run.
- Tests failing: `test_injection_prevention` splits a placeholder containing spaces; `test_screen_graph_validates` reports 41 invalid screens, primarily an unsupported `help` item tag. `automation/validate_screens.py` reports 41/42 errors. `git diff --check` reports trailing whitespace.
- Next: Fix the failing tests and validation errors, run `./test.sh`, `./check.sh`, `git diff --check`, perform an actual Pascal build, commit all cohesive changes, and pass `automation/verify-completion.sh --pre-marker` before claiming completion.
