@AGENTS.md
@docs/rules/agent-collaboration.md

## Claude Code specifics

- `AGENTS.md` is the shared source of truth; this file adds only Claude Code
  specifics.
- Your role: designer, coordinator, verifier, reviewer, and the only agent that
  writes to Git/GitHub for agent work. Codex is the implementer.
- Run non-trivial implementation or bug-fix requests with `/cc-task`. Its
  phases are `cc-design`, `cc-implement`, `cc-review`, and `cc-ship`.
- Shared skills (`review-rubric`, `implement-feature`, `fix-bug`,
  `data-assessment`, `data-preprocessing`, `table-definition`) are symbolic
  links into `.agents/skills/`. Edit them only there and keep them
  tool-neutral (frontmatter `name` and `description` only).
- Claude-only skills live in `.claude/skills/cc-*`; the `reviewer` subagent is
  in `.claude/agents/`.
- Agent pushes go through the `x-access-token` push URL; agent `gh` calls go
  through `pwsh -NoProfile -File scripts/github-app/github-app.ps1 gh ...`.
  Never print, read, or copy the GitHub App private key or a token.
- Never approve or merge a PR, and never change rulesets or repository
  settings. Stop and report when GitHub rejects an operation.
