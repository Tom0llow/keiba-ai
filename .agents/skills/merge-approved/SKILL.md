---
name: merge-approved
description: Perform the guarded final squash merge only after the user explicitly approves the exact PR number and HEAD SHA previously presented as MERGE_READY.
---


# Merge Approved

Use only after an explicit user statement approving merge.

The approval must refer to the exact PR number and HEAD SHA most recently
presented as MERGE_READY. Do not silently refresh approval to a newer SHA or
transfer it to a replacement PR.

Read `.git/codex-guard/guard-invocation.json` in a separate sandboxed step and
use its exact absolute `shellPath` and
`scripts["scripts/agent/merge-task.ps1"]` values as argv tokens. Never use a
relative guard path or a shell variable for the host invocation.

Invoke:

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_MERGE_TASK_PATH `
  -PrNumber <approved-pr-number> `
  -ExpectedHeadSha "<approved-head-sha>"
```

For an unmerged PR, the wrapper revalidates PR identity, CI, review state,
mergeability, exact HEAD, and `main` protection immediately before merging. The
protection check includes required contexts, strict status checks, and the
configured GitHub Actions application ID.

If HEAD changed, stop and return to the review/merge-ready workflow.
Do not ask the user to approve an unreviewed replacement SHA.

If GitHub completed the merge but a later communication or cleanup operation
failed while task state remains, rerun the same command only with the same PR
number and approved SHA. The wrapper may recover cleanup only after GitHub
reports `MERGED` with `mergedAt`, current protection verifies, the recorded
pre-merge squash attempt matches, and the PR HEAD, task HEAD,
`mergeReadySha`, attempted SHA, and `ExpectedHeadSha` all agree. Incomplete
cleanup retains task state and fails so this exact command can be retried. Any
mismatch is a blocker; never reinterpret the approval for another SHA and never
use raw Git or `gh pr merge` to bypass recovery checks.

After success, report:
- merged PR URL
- merged SHA reviewed/approved
- squash merge status
- local cleanup status

