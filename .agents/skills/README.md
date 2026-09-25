# Repository Skills

This repository provides focused Codex workflows under `.agents/skills/`.

## User-facing skills

| Skill | Use |
| --- | --- |
| `autonomous-task` | Full guarded implementation lifecycle through an exact-HEAD `MERGE_READY` gate |
| `implement-feature` | Code-and-test phase for new behavior; standalone only for explicit local-only work |
| `fix-bug` | Diagnosis and code-and-test fix phase; standalone only for explicit local-only work |
| `code-review` | Read-only defect-first review of diffs/branches/commits/PRs |
| `merge-approved` | Guarded squash merge after explicit approval of the exact reviewed HEAD |

Codex may select a user-facing skill implicitly from its description, or it can
be invoked explicitly from the Codex IDE/CLI. When `AGENTS.md` requires the
guarded lifecycle, `autonomous-task` remains the top-level coordinator and uses
`implement-feature` or `fix-bug` only for the local implementation phase.

## Internal workflow skills

These skills are building blocks used by `autonomous-task`, not general entry
points for ordinary user requests:

| Skill | Workflow responsibility |
| --- | --- |
| `create-pr` | Create a PR from an already validated and pushed guarded task branch |
| `ci-fix` | Analyze and repair task-related CI failures within the bounded retry policy |
| `review-fix-loop` | Coordinate bounded local review and validated fixes |
| `pr-review` | Review the complete PR at its current exact HEAD |
| `merge-ready` | Verify and present the final exact-HEAD readiness gate |

Keep skills focused. If a workflow becomes materially different, prefer a separate skill rather than turning one skill into a catch-all process.
