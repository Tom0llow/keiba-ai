---
name: merge-ready
description: Evaluate the current guarded PR and record its exact PR number and merge-ready HEAD for human approval. Never merge or change the working tree.
---


# Merge Ready

Run only after implementation, CI, and final PR review are complete.

This gate updates the guarded task's readiness state under the exclusive
workflow lock. The record is bound to both the supplied PR number and HEAD SHA.
It does not merge the PR or modify the working tree.

Read `.git/codex-guard/guard-invocation.json` in a separate sandboxed step and
use its exact absolute `shellPath` and
`scripts["scripts/agent/merge-ready.ps1"]` values as argv tokens. Never use a
relative guard path or a shell variable for the host invocation.

Execute:

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_MERGE_READY_PATH `
  -PrNumber <N> `
  -ExpectedHeadSha "<reviewed-head-sha>"
```

A successful gate requires:

- guarded task branch/PR identity matches
- clean local working tree
- local HEAD == remote task branch == PR HEAD
- PR open and non-draft
- mergeable and CLEAN
- no blocking GitHub review decision
- at least one CI/status check
- `Quality` and `Test` pass; optional checks pass or skip
- the configured `main` branch protection still matches the reviewed policy

Also require from the coordinator's own workflow state:

- no validated P0/P1/P2 final AI review findings remain
- acceptance criteria are satisfied
- no unresolved architecture/security blocker exists

If ready, present the exact SHA to the user for merge approval.

Present the exact PR number with that SHA. If the task is rebound to a
replacement PR, the wrapper clears this readiness and any merge-attempt record;
the replacement PR must pass this gate again.

Never merge from this skill.

