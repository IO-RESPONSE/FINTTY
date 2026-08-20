/goal

Work autonomously on the RHEL 9 NSMITTY MVP in the current repository.

Read `ANTIGRAVITY_TASK.md` completely and obey it. Then read `MVP_STATE.md`,
`MVP_BACKLOG.md`, and `MVP_RUN_LOG.md` if they exist. Inspect git status and
recent commits before editing. Preserve user-owned changes.

Select the highest-priority unblocked task that materially advances an unmet
acceptance criterion. Implement it, test it, inspect the diff, update state and
backlog files, and create a cohesive local commit only when relevant tests pass.
Never push, publish, deploy, use sudo, mutate the host, perform destructive
operations, or manage SELinux.

Do not stop after one small task. Continue with the next eligible task while
session time remains. Before exit, always leave exact continuation evidence in
`MVP_STATE.md` and append the run result to `MVP_RUN_LOG.md`.

Only when every Definition of Done criterion in `ANTIGRAVITY_TASK.md` has
verified evidence, create `.antigravity-complete` containing the timestamp,
final commit hash, test commands and results, and acceptance-report path.
