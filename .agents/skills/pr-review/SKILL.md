---
name: pr-review
description: Run the final independent read-only review of the complete current pull request; fix validated P0/P1/P2 findings with bounded re-review. Intended for autonomous-task.
---


# Final PR Review

The PR review is independent from the initial local review.

## Loop bound

Maximum two fixer rounds.

Read `.git/codex-guard/guard-invocation.json` in a separate sandboxed step.
Coordinator wrapper calls use only its exact absolute `shellPath` and matching
absolute `scripts` values as argv tokens; relative guard paths are forbidden.

## Procedure

1. Capture current PR number and HEAD SHA.
2. Ensure CI for that HEAD is passing.
3. As coordinator, capture metadata, the complete PR diff, and checks with the
   trusted absolute `inspect-pr.ps1` path from the invocation metadata. Invoke
   its `Metadata`, `Diff`, and `Checks` modes separately with the same
   `-PrNumber` and `-ExpectedHeadSha` values, and require every result's
   `baseSha`, `diffBaseSha`, and `headSha` to agree. `headSha` must equal the
   expected SHA. The supplied diff is the complete local binary/full-index diff
   from recorded task `diffBaseSha` through `headSha`, with external diff and
   text conversion disabled; do not substitute a file-limited API diff.
4. Spawn a fresh `pr_reviewer` read-only with:
   - original requirement and acceptance criteria
   - PR number
   - exact HEAD SHA
   - captured PR metadata, complete diff, and checks
   - relevant architecture/ADR context
5. The reviewer must inspect the supplied complete PR diff and current code; it
   must not invoke host wrappers or direct `gh` commands.
6. Coordinator validates each finding.

Classification:

```text
validated P0/P1/P2 -> must fix before MERGE_READY
P3 -> may remain if non-blocking and reported
incorrect/not reproducible -> reject with evidence
needs product decision -> BLOCKED
```

For validated blocking findings:

1. spawn `fixer`
2. run focused + repository validation
3. guarded commit
4. guarded push
5. capture the new exact HEAD and wait for CI with that SHA passed as
   `-ExpectedHeadSha`
6. spawn a fresh `pr_reviewer` for the complete PR

Never treat an old review as approval for a new HEAD.

