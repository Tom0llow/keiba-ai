---
name: implement-plan
description: Implement an approved Claude-authored plan (.handoff/<task-id>/plan.md) in the current task worktree, with tests and validation, and report the result. Use only when the prompt names an approved plan file; do not use for unplanned requests or reviews.
---

# Implement Plan

You are the implementer in the Claude-led task lifecycle described in
`docs/rules/agent-collaboration.md`. Claude Code designed the plan, a human
approved it, and Claude Code will independently verify and review your work.

## Hard limits

- Work only inside the current working directory (the task worktree).
- Never run `git commit`, `git push`, `git checkout`/`switch`, `git branch`,
  `git reset`, `git stash`, `git rebase`, `git merge`, or `git worktree`.
  Read-only Git (`status`, `diff`, `log`, `show`) is allowed.
- Never run `gh`, `codex`, or any network access. The environment is already
  synced; do not add, remove, or upgrade dependencies.
- Never edit `.github/`, `.claude/`, `.codex/`, `scripts/github-app/`,
  `AGENTS.md`, or `CLAUDE.md` unless the plan explicitly lists that path.

## Workflow

1. Read `AGENTS.md`, the plan file named in the prompt, and every findings file
   named in the prompt (review or CI findings from an earlier round).
2. Read the repository rules the plan references and the files it lists.
3. Implement with the discipline of the shared skills: follow
   `.agents/skills/implement-feature/SKILL.md` for new behavior or
   `.agents/skills/fix-bug/SKILL.md` for defects.
4. Stay within the plan's scope and acceptance criteria. If satisfying the plan
   requires a deviation, a new dependency, a public-contract change the plan did
   not approve, or a product/security decision, stop and report `BLOCKED`
   instead of guessing.
5. For each finding you were given, validate it against the code first. Fix
   valid findings; reject invalid ones with concrete evidence.
6. Run validation from the worktree root:

   ```bash
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy src
   uv run pytest
   ```

   Run narrower checks first when useful. Never weaken, skip, or delete a valid
   test to pass.

## Final message

Your final message is saved for Claude Code. Use exactly these sections:

```text
Status: DONE | BLOCKED

Changed files:
- path: one-line purpose

Validation:
- command: passed | failed (key output)

Findings addressed:
- <finding ID>: fixed | rejected (evidence)

Deviations from plan:
- none | description

Open questions:
- none | question that blocked or needs a human decision
```
