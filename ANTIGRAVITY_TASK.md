# RHEL 9 NSMITTY MVP Assignment

## Mission

Transform this GPL-3.0 Free Pascal/Lazarus prototype into a safe, testable
SMITTY-style TUI MVP for RHEL 9. Continue autonomously until the definition of
done is verified, the deadline expires, or a genuine external blocker remains.
Stop immediately after verified completion; seven days is a maximum safety
limit and must never be treated as a required duration or a reason for busywork.

## Scope

Include hierarchical menus, FastPaths, F1 help, F4 dynamic lists, fully resolved
and redacted F6 command preview, preview/dry-run semantics, safe execution,
confirmation, audit logging, user/group management, systemd services, DNF/RPM,
NetworkManager, journalctl, hostname, timezone, chrony, automated tests, RHEL 9
build documentation, and RPM packaging.

Exclude SELinux management, firewalld, storage mutation, `/etc/fstab` mutation,
other distributions, remote-host management, deployment, pushing, and releases.

## Safety and engineering requirements

- Inspect git status and preserve user changes before every edit.
- Never use destructive git commands, sudo, su, push, force-push, or host
  administration mutations.
- Replace supported operations' `eval` and shell concatenation with a structured
  executable/argv model. Keep legacy shell actions isolated and visibly marked.
- Validate user-controlled values and test injection strings including shell
  substitutions, quotes, newlines, leading dashes, globs, Unicode, and traversal.
- Never log or export passwords, tokens, or sensitive field contents.
- Detect root requirements; never invoke privilege escalation automatically.
- Test mutations with mocks. Use containers only for read-only integration tests.
- Do not claim completion based only on written code.

## Priority backlog

1. Reproducible build, pinned dependency strategy, stable build/test/check entry
   points, parser tests, and screen-graph validation.
2. Structured command model, validators, renderer, resolved F6 preview, argv
   executor, privilege/risk policy, confirmation, redaction, audit log, script
   export, and legacy adapter.
3. User/group read and safe mutation screens and tests.
4. systemd service read and safe mutation screens and tests.
5. DNF/RPM read and safe mutation screens and tests.
6. journalctl bounded read-only screens and tests.
7. NetworkManager read and safe mutation screens and tests, with remote
   disconnect warnings.
8. Hostname, timezone, and chrony screens and tests.
9. RHEL 9 integration validation, RPM spec, man page, security/architecture/
   screen-format/support documentation, and final acceptance report.

## Per-run loop

Read this file and the state files, inspect the repository, choose one coherent
highest-priority task, define its acceptance condition, implement and test it,
inspect the diff, update `MVP_STATE.md`, `MVP_BACKLOG.md`, and append
`MVP_RUN_LOG.md`. Commit locally only when the change is cohesive and its tests
pass. Continue with another task if time remains. Avoid cosmetic busywork,
placeholder menus, repeated plans, and identical retries.

When blocked, record the exact failure, try up to three materially different
safe approaches, then continue an independent task. Never wait idly for input.

## Definition of done

- Clean RHEL 9-compatible build instructions work.
- Safety foundation and required functional modules above are implemented.
- F6 matches execution semantics and redacts secrets.
- Supported mutations avoid eval and unsafe shell composition.
- Screen graph validates without missing targets or duplicate FastPaths.
- Automated tests, including injection and redaction tests, pass.
- RPM builds and documentation accurately distinguishes tested limitations.
- SELinux management is absent.
- No known high-severity injection or secret-leak defect remains.
- The final acceptance report maps evidence to every criterion.
