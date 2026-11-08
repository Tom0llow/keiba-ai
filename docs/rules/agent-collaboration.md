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
| `verify-<n>.md` | Claude Code | Verification result for round `n`: Codex tier/model/effort used and failures fed back to Codex |
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

## 8. Codex model tiers

Every `codex exec` run passes an explicit model and reasoning effort from this
table (`-m "$CODEX_MODEL" -c "model_reasoning_effort=\"$CODEX_EFFORT\""`),
except that rule 3 escalates to the `deep` model with effort `max`. `max` is
listed as supported for that model in the Codex model catalog, but has not yet
been confirmed with a run on the account. Skills never hard-code model names;
update only this table when models change, and confirm a new model with one run
on the account before switching.

| Tier | `CODEX_MODEL` | `CODEX_EFFORT` | Use for |
| --- | --- | --- | --- |
| `light` | `gpt-5.6-luna` | `xhigh` | Read-only search, summary, or extraction; mechanical or small changes with an unambiguous expected result (format, lint, typo, rename, one-line doc or config edit) |
| `standard` | `gpt-5.6-terra` | `xhigh` | Implementing an approved plan whose design and bug cause are already settled; adding tests; Codex review of `light` and `standard` tasks |
| `deep` | `gpt-5.6-sol` | `xhigh` | Plan critique; architecture or ADR-level changes; public or persisted contracts (CLI, table schemas, Parquet, model artifacts); trust-boundary files (`.github/`, `.claude/settings.json`, `.codex/`, `scripts/github-app/`); time-ordering and leakage-sensitive feature or data logic; cross-module refactors; bugs or CI failures whose cause is unknown; Codex review of `deep` tasks |

Selection:

1. `cc-design` records `Codex tier: <tier> - <reason>` in `plan.md`, chosen
   by the riskiest part of the plan. When two tiers fit, choose the higher.
   The human may change the tier at GATE 1.
2. Per run:
   - plan critique: `deep`;
   - implementation round 1: the plan tier;
   - fix round: `light` only when every finding is mechanical and the plan
     tier is not `deep`; `deep` when a finding needs diagnosis of an unknown
     cause, otherwise the plan tier;
   - Codex review: the higher of the plan tier and `standard`.
3. Escalate one tier for the next round (`light` -> `standard` -> `deep`;
   at `deep`, use the `deep` model with effort `max`) when the previous round
   failed verification for a non-mechanical reason. This overrides rule 2 for
   that round. Escalation never adds rounds; section 6 still applies.
   `BLOCKED` always goes to the human (section 4); if the human sends the task
   back, the tier may be raised then.
4. Never use effort `ultra`: it starts subagents automatically, which Codex
   must not do (section 1).
5. A run that fails with a usage limit or `model_not_found` is not retried on
   another tier or model; stop and report the error and any reset time to the
   human.
6. Record the selected tier and the model and reasoning effort printed in the
   run's output header (`model:` and `reasoning effort:`) for each run. Record
   implementation and review runs in the round's handoff file
   (`verify-<n>.md`, `review-<n>.md`) and in the READY report. Record a
   plan-critique run in a `Codex runs:` line directly below the plan heading in
   `plan.md`.
