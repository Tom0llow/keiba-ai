---
name: create-pr
description: Create a guarded GitHub PR for an already validated guarded task branch. Internal building block for autonomous-task; never merge.
---


# Create PR

Read `.git/codex-guard/guard-invocation.json` in a separate sandboxed step and
use its exact absolute `shellPath` and
`scripts["scripts/agent/create-pr.ps1"]` values as argv tokens. Never use a
relative guard path or a shell variable for the host invocation.

Use only the guarded wrapper:

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_CREATE_PR_PATH -Title "<title>" -Body "<body>"
```

Before creation ensure:

- local validation passes
- guarded commit exists
- guarded push completed
- working tree is clean

The PR body must include a `Summary` with a changed-file tree containing every
changed file and only the parent directories needed to locate them, the purpose
and motivation of every commit identified by short SHA or subject, and a
per-file description for every changed file. Use this structure:

````markdown
## Summary

### Changed-file tree

```text
<tree containing every changed file>
```

### Commit purpose and motivation

- `<short-sha-or-subject>`: <purpose and motivation>

### Per-file changes

- `path/to/file`: <description>

## Validation

- ...

## Architecture / ADR

- ...

## Risks / Notes

- ...
````

Never merge.

Capture the returned PR number, URL, and exact `headSha`. Subsequent CI,
inspection, final-review, and merge-readiness calls must all receive that same
SHA unless a guarded fix commit creates and returns a new HEAD.

If the wrapper binds the task to a different PR number, it clears any earlier
MERGE_READY record and pre-merge attempt. Evidence or approval for the former PR
must not be reused for the replacement PR.

