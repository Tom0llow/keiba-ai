---
name: cc-implement
description: Have Codex implement an approved plan (or a round of review/CI findings) inside the task worktree, then verify the result independently. Use as the implementation phase of cc-task.
disable-model-invocation: true
---

# Delegate Implementation to Codex

Codex edits files; Claude prepares the worktree, runs Codex, and verifies.
Never accept Codex's report as evidence by itself.

## 1. Prepare the worktree (first round only)

```bash
git fetch origin
git worktree add -b "$BRANCH" "$WT" origin/main
uv sync --locked --directory "$WT"
```

Codex runs with networking disabled, so the environment must be synced first.

## 2. Run Codex

Use the Bash tool with `run_in_background: true`; a run can take many minutes.
`ROUND` starts at 1. `FINDINGS` is `none` in round 1, otherwise the paths of the
review or CI findings files for this round.

Before the command, choose the tier and set `CODEX_MODEL` and `CODEX_EFFORT`
from its row in section 8 of `docs/rules/agent-collaboration.md`: round 1 uses
the plan tier; later rounds use the fix-round and escalation rules.

```bash
UV_NO_SYNC=1 UV_CACHE_DIR="$WT/.uv-cache" codex exec \
  -C "$WT" -s workspace-write \
  -c sandbox_workspace_write.network_access=false \
  -c 'windows.sandbox="unelevated"' \
  -m "$CODEX_MODEL" \
  -c "model_reasoning_effort=\"$CODEX_EFFORT\"" \
  -o "$HANDOFF/codex-impl-$ROUND.md" \
  "Use the implement-plan skill (.agents/skills/implement-plan/SKILL.md). Approved plan: $HANDOFF/plan.md. Findings to address: $FINDINGS." \
  < /dev/null
```

A run succeeds only when its exit code is 0, `codex-impl-$ROUND.md` exists and
is non-empty, and no line starting with `ERROR:` turns out, on inspection, to
be a Codex-level error (usage limit, `model_not_found`, request, or
configuration error) rather than output of a command Codex ran. A usage-limit
or `model_not_found` error stops the task and goes to the human; do not fall
back to another tier or model. For any other failed run, inspect the output and
delete the stale output file before rerunning:

```bash
rm -f "$HANDOFF/codex-impl-$ROUND.md"
```

A rerun counts as a round under section 6.

## 3. Verify independently

1. `Status: BLOCKED` -> stop and take the open question to the human.
2. Codex must not have committed or switched branches:

   ```bash
   git -C "$WT" rev-parse --abbrev-ref HEAD      # must equal $BRANCH
   git -C "$WT" log --oneline origin/main..HEAD  # must list only commits cc-ship made
   git -C "$WT" add --intent-to-add --all        # make new files visible to diffs
   git -C "$WT" status --short
   git -C "$WT" diff --stat
   ```

3. Check the diff against the plan: every changed path is justified by an
   implementation step or a finding; nothing in `.github/`, `.claude/`,
   `.codex/`, `scripts/github-app/`, `AGENTS.md`, or `CLAUDE.md` changed unless
   the plan lists it. Revert accidental files only after inspecting them.
4. Run the full validation yourself from the worktree:

   ```bash
   (cd "$WT" && uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest)
   ```

5. Always write `$HANDOFF/verify-$ROUND.md` after verification. Record the
   selected tier, the `model:` and `reasoning effort:` values printed in the
   run's output header, the verification result, and, when escalating, the
   reason. If validation fails or the diff misses an acceptance criterion,
   record the evidence as the next round's findings and run the next round with
   it. Implementation and fix rounds together are limited to two per phase
   (review or CI); beyond that, stop and report to the human.

Small mechanical corrections (for example a formatting-only fix) may be made by
Claude directly in the worktree; record them in the next review.
