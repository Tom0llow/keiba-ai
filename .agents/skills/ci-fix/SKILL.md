---
name: ci-fix
description: Diagnose and repair failing GitHub Actions checks for the current guarded PR, then commit/push and re-run CI. Intended for the autonomous-task coordinator.
---


# CI Fix

Use only for the current guarded task PR.

Read `.git/codex-guard/guard-invocation.json` in a separate sandboxed step.
Every wrapper call must use the exact absolute `shellPath` and matching
absolute `scripts` value as argv tokens. The command placeholders below mean
those literal values, not shell variables; never use a relative guard path.

## Loop bound

Maximum two CI fixer rounds.

## Procedure

1. Confirm the failing PR number and exact HEAD SHA.
2. As coordinator, capture checks, runs, and failed logs with the trusted
   absolute `inspect-pr.ps1` and `inspect-ci.ps1` paths from the invocation
   metadata. Pass the same exact SHA as `-ExpectedHeadSha` to every mode and
   reject any result whose `headSha` differs. Require `inspect-pr.ps1` results'
   `baseSha`, `diffBaseSha`, and `headSha` to remain stable, and require
   `inspect-ci.ps1` results' `baseSha` and `headSha` to do the same. Check
   evidence is collected from the check-runs and commit-status APIs for that
   exact head.
3. Spawn `ci_analyst` read-only and provide the captured output, exact HEAD,
   and changed code/configuration. The analyst must not invoke host wrappers or
   direct `gh` commands.
4. Validate the diagnosis.
5. If failure is task-related and fixable, spawn `fixer` with only the validated diagnosis.
6. Run focused validation, then repository-level checks.
7. If code changed:
   ```powershell
   ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_COMMIT_TASK_PATH -Message "<fix(...) or ci(...): ...>"
   ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_PUSH_TASK_PATH
   ```
8. Wait again:
   ```powershell
   ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_WAIT_CI_PATH `
     -PrNumber <N> `
     -ExpectedHeadSha "<new-head-sha>"
   ```

If a failure is infrastructure/external and not caused by the patch, do not invent a code change. Report BLOCKED with evidence.

Never disable CI, remove tests, lower coverage, or weaken checks merely to obtain green status.

