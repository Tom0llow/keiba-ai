---
name: cc-task
description: Run the full Claude-led task lifecycle for a non-trivial implementation or bug fix - design an approved plan, have Codex implement it in an isolated worktree, review it independently with Claude and Codex, and publish a GitHub App-authored PR that only a human can merge.
disable-model-invocation: true
---

# Claude-led Task Lifecycle

Coordinate one task from requirement to a merge-ready PR. Roles, handoff files,
and loop limits are defined in `docs/rules/agent-collaboration.md`; Git and PR
rules are in `docs/rules/git-workflow.md`. Read both before starting.

```text
Human requirement
 -> cc-design     plan.md                         [GATE 1: human approves plan]
 -> cc-implement  Codex implements in worktree, Claude verifies
 -> cc-review     reviewer subagent + Codex read-only review, Claude adjudicates
      (valid P0-P2 -> cc-implement fix round, max 2, then re-review)
 -> cc-ship       commit, App push, App PR, CI (failures -> fix round, max 2)
 -> READY report                                  [GATE 2: human approves + merges on GitHub]
 -> cleanup after the human confirms the merge
```

## Setup

1. Run `git status --short --branch` and `git fetch origin`. Never touch
   unrelated user changes in the main checkout.
2. Choose `TASK_ID` as `YYYYMMDD-<short-kebab-slug>` and use these paths:

   ```bash
   ROOT="$(git rev-parse --show-toplevel)"   # Windows form, e.g. C:/Users/...
   HANDOFF="$ROOT/.handoff/$TASK_ID"
   WT="$ROOT/.worktrees/$TASK_ID"
   BRANCH="agent/$TASK_ID"
   APP_GH="pwsh -NoProfile -File $ROOT/scripts/github-app/github-app.ps1 gh"
   REPO="Tom0llow/keiba-ai"
   ```

   Every agent `gh` call, including issue commands, uses `$APP_GH ... --repo "$REPO"`
   so it runs as the App identity, never with the human's `gh` credentials.

3. Confirm the agent identity is configured: `git remote get-url --push origin`
   starts with `https://x-access-token@github.com/` and
   `pwsh -NoProfile -File "$ROOT/scripts/github-app/github-app.ps1" check`
   prints `ok:`. If not, stop and point the human to the setup section of
   `docs/rules/git-workflow.md`.

## Phases

1. **Design** - follow `cc-design`. Stop at GATE 1 and wait for explicit human
   approval. Do not create the worktree before approval.
2. **Implement** - follow `cc-implement` (round 1).
3. **Review** - follow `cc-review`. For valid P0-P2 findings, run another
   `cc-implement` round with the review file, then review the complete diff
   again. At most two fix rounds.
4. **Ship** - follow `cc-ship`.
5. **READY** - report to the human:
   - PR URL, PR number, and exact HEAD SHA,
   - what changed, mapped to the plan's acceptance criteria,
   - validation that actually ran, and review outcome (fixed / rejected /
     deferred findings),
   - the selected Codex tier and the model and effort printed in each run's
     output header (section 8),
   - remaining risks,
   - Issue candidates for follow-up work and deferred findings (title, body,
     labels) per section 9 of `docs/rules/agent-collaboration.md`; file them
     with `$APP_GH issue create --repo "$REPO" ...` only after the human
     confirms, then add only `Refs #n` (never `Closes #n`) to
     `$HANDOFF/pr-body.md`, update the PR with
     `$APP_GH pr edit <n> --repo "$REPO" --body-file "$HANDOFF/pr-body.md"`,
     and tell the human which issues were filed and that the PR body changed.
   Then stop. Never approve or merge; the human does both on GitHub.
6. **Human feedback** - if the human requests changes (in chat or as PR
   review comments read with `$APP_GH pr view <n> --repo "$REPO" --comments`), treat them as
   findings: `cc-implement` -> `cc-review` -> `cc-ship` (push a new commit).
7. **Cleanup** - only after the human says the PR is merged and
   `$APP_GH pr view <n> --repo "$REPO" --json state` reports `MERGED`:

   ```bash
   git worktree remove "$WT"
   git branch -D "$BRANCH"     # squash merge leaves the branch unmerged locally
   ```

   Keep `.handoff/$TASK_ID/` unless the human asks to delete it.

## Stop conditions

Stop and ask the human instead of continuing when:

- Codex reports `BLOCKED`, or a fix needs a scope, contract, dependency, or
  security decision the plan did not approve;
- a Codex run fails with a usage limit or `model_not_found` (report the error
  and any reset time);
- a loop limit is reached with unresolved P0-P2 findings or failing CI;
- the agent identity check fails, or a push or PR operation is rejected.
