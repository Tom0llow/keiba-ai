# Agent Collaboration (Claude Code + Codex)

This file defines how Claude Code, Codex, and the human owner share work.
ADR-031 records the decision. Git, PR, and CI rules are in
`docs/rules/git-workflow.md`.

## 1. Roles

| Actor | Responsibilities | Never |
| --- | --- | --- |
| Human owner | States requirements, approves plans, reviews and approves PRs, merges on GitHub | — |
| Claude Code | Designs plans, coordinates the lifecycle, verifies Codex output, runs independent reviews, commits, pushes, opens PRs, and drives CI with the GitHub App identity | Approves or merges PRs; edits trust settings without a human request |
| Codex | Implements an approved plan or a findings round inside a task worktree, writes tests, runs local validation, performs read-only reviews when asked | Mutates Git state, uses `gh` or the network, starts nested agents |

Roles can be swapped for a task only when the human asks; the handoff files
below stay the same.

## 2. Lifecycle

```text
requirement -> plan (GATE 1: human approval) -> Codex implementation
-> Claude verification -> dual review -> fixes -> App-authored PR -> CI
-> READY report -> GATE 2: human approval and merge on GitHub -> cleanup
```

Claude Code runs this lifecycle with the `cc-task` skill and its phase skills
`cc-design`, `cc-implement`, `cc-review`, and `cc-ship`. Codex runs its part
with the `implement-plan` skill.

## 3. Handoff files

Handoffs are git-ignored and live in `.handoff/<task-id>/`, where `<task-id>`
is `YYYYMMDD-<short-kebab-slug>`:

| File | Writer | Purpose |
| --- | --- | --- |
| `plan.md` | Claude Code | Approved requirement: goal, design, steps, acceptance criteria, test plan |
| `codex-plan-review-<n>.md` | Codex | Optional read-only plan critique |
| `codex-impl-<n>.md` | Codex | Implementation report for round `n` |
| `verify-<n>.md` | Claude Code | Verification failures fed back to Codex |
| `codex-review-<n>.md` | Codex | Read-only review for round `n` |
| `review-<n>.md` | Claude Code | Adjudicated findings for round `n` |
| `ci-<n>.md` | Claude Code | CI failure evidence for round `n` |
| `pr-body.md` | Claude Code | Current PR description |

Task code lives in the git-ignored worktree `.worktrees/<task-id>/` on branch
`agent/<task-id>`. Do not put secrets or credentials in handoff files.

## 4. Scope and decisions

- An approved plan bounds the task. A needed deviation, dependency change,
  unapproved public-contract change, or product/security decision stops the
  task and goes to the human.
- Codex reports `BLOCKED` instead of guessing; Claude Code takes the question
  to the human.

## 5. Review and findings

- Reviews always cover the complete diff against `origin/main`.
- Two independent reviewers run for each review round: a fresh Claude
  `reviewer` subagent and a read-only Codex review. Both follow
  `.agents/skills/review-rubric/SKILL.md`.
- Findings carry an ID (`REV-` for Claude, `CX-` for Codex), P0-P3 severity,
  a narrow location, and evidence.
- Claude Code validates every finding before acting. The same issue found
  independently by both reviewers is raised one severity level.
- Each finding is decided as `fix`, `reject` (with evidence), or `defer`
  (recorded in the PR body).
- Codex validates each finding it receives and may reject one with evidence.

## 6. Loop limits

- Plan critique: at most two rounds.
- Review fixes: at most two fix rounds, each followed by a complete re-review.
- CI fixes: at most two fix rounds.

When a limit is reached with unresolved P0-P2 findings or failing CI, stop and
report to the human.

## 7. Concurrency

- Only one writer per worktree at a time.
- Read-only reviewers may run in parallel.
- Independent tasks use separate worktrees and branches.
