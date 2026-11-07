---
name: cc-review
description: Independently review the task diff with a fresh Claude reviewer subagent and a read-only Codex review, then adjudicate findings into .handoff/<task-id>/review-<n>.md. Use as the review phase of cc-task.
---

# Dual Independent Review

Two reviewers with no implementation context look at the complete diff. Claude
then validates every finding; reviewers can be wrong.

## 1. Fix the review target

- Before the PR exists: the worktree diff against `origin/main`
  (`git -C "$WT" diff origin/main`, after `git add --intent-to-add --all`).
- After the PR exists: the committed diff at the exact head
  (`git -C "$WT" diff origin/main...HEAD`), recording `git rev-parse HEAD`.

Always review the complete diff, not only the latest round's changes.

## 2. Run both reviewers in parallel

- **Claude**: launch the `reviewer` subagent (`.claude/agents/reviewer.md`)
  with the worktree path, the plan path, and the diff command. It must not see
  earlier review files or Codex's implementation reports.
- **Codex** (Bash tool, `run_in_background: true`):

  ```bash
  codex exec -C "$WT" -s read-only -c 'windows.sandbox="unelevated"' \
    -o "$HANDOFF/codex-review-$ROUND.md" \
    "Review the changes in this worktree against origin/main (include uncommitted and intent-to-add files). Read-only. Follow .agents/skills/review-rubric/SKILL.md. The approved plan is $HANDOFF/plan.md; also report unmet acceptance criteria. Prefix finding IDs with CX-." \
    < /dev/null
  ```

## 3. Adjudicate

For every finding from either reviewer:

1. Trace the code path and confirm the issue against the current diff.
2. Merge duplicates. When both reviewers independently report the same issue,
   raise its severity by one level.
3. Decide: `fix` (valid P0-P2, or a P3 that is cheap and in scope),
   `reject` (with evidence), or `defer` (valid but out of plan scope; list it in
   the PR body under Risks / Notes).

Write `$HANDOFF/review-$ROUND.md`:

```text
Target: <diff command> @ <HEAD SHA or "uncommitted">
Plan: <plan path>

ID | Severity | Location | Decision | Summary / evidence
REV-1 | P1 | src/x.py:10-20 | fix | ...
CX-2 | P2 | ... | reject | ...
```

## 4. Outcome

- Any `fix` decision -> `cc-implement` with this file as the findings, then
  repeat this skill on the complete diff. At most two fix rounds; then stop and
  report to the human.
- No `fix` decisions -> proceed to `cc-ship`.
