# AGENTS.md

## 1. Purpose

This file is the durable working contract for AI coding agents in this
repository. Codex reads it directly; Claude Code imports it from `CLAUDE.md`.
Detailed rules live under `docs/rules/`; reusable procedures belong in skills
rather than being duplicated here.

Instructions apply in this order when they conflict:

1. explicit user instructions,
2. the nearest applicable `AGENTS.md`,
3. repository rules, configuration, and Accepted ADRs,
4. this file.

## 2. Current repository state

This repository is a Python 3.12 project with a Typer CLI, local JRA-VAN data
retrieval, raw-to-Parquet preprocessing, processed-data loading, feature
generation, and ranking-model evaluation. It is not installed as a Python
distribution; `src/tests/test_project_environment.py` verifies that environment
contract. Current module responsibilities are documented in `ARCHITECTURE.md`.

```text
.
├─ src/
│  ├─ main.py
│  ├─ data/
│  ├─ features/
│  ├─ models/
│  └─ tests/
├─ configs/
├─ docs/
│  ├─ decisions/         # architecture decision records
│  └─ rules/             # coding, architecture, Git, testing, and agent rules
├─ .agents/skills/       # Codex skills and shared skills (canonical)
├─ .claude/              # Claude Code settings, Claude-only skills, subagents
├─ .codex/               # Codex project configuration and execution rules
├─ .github/              # CI, CODEOWNERS, and main-branch rulesets
├─ scripts/github-app/   # GitHub App token helper for the agent identity
├─ AGENTS.md
├─ CLAUDE.md
├─ ARCHITECTURE.md
├─ pyproject.toml
└─ uv.lock
```

Do not restore or infer additional product behavior from an earlier prototype.
New behavior and durable architecture must be introduced by an explicit
requirement or an Accepted ADR.

Before making changes, read the rules relevant to the task:

- Code changes: `docs/rules/coding-style.md`
- Architecture or module placement: `ARCHITECTURE.md` and
  `docs/rules/architecture.md`
- Git, branch, commit, or PR work: `docs/rules/git-workflow.md`
- Tests or bug fixes: `docs/rules/testing.md`
- Agent roles, handoffs, and review loops: `docs/rules/agent-collaboration.md`
- Documents and their language: `docs/rules/documentation.md`

If a deeper directory contains another `AGENTS.md`, follow it within that
directory.

## 3. Default implementation workflow

For every implementation task:

1. inspect the existing code, tests, rules, and relevant ADRs before editing;
2. identify the smallest coherent change that satisfies the requirement;
3. avoid speculative product behavior and architecture;
4. add or update tests when observable behavior changes;
5. validate the nearest behavior first, then run the required repository checks;
6. review the diff and remove only accidental changes introduced by the task;
7. report changes, validation, and unresolved risks accurately.

Never discard or overwrite unrelated user or agent changes. Do not perform
opportunistic refactors, dependency changes, or public-contract changes.

## 4. Required commands

Install or synchronize the locked environment:

```bash
uv sync --locked
```

Final validation:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

The agent-workflow integration tests require PowerShell 7 (`pwsh`) and the
shared skill symbolic links (see `docs/rules/testing.md`).

Run focused tests and checks first when a narrower command can provide faster
feedback. Do not claim that a command passed unless it was run successfully.

## 5. Implementation and testing rules

- Prefer existing conventions and standard-library functionality.
- Add dependencies only when the requirement cannot be met reasonably with the
  existing environment; update `pyproject.toml` and `uv.lock` together.
- Keep I/O and external side effects at explicit boundaries.
- Avoid import-time work and hidden global state.
- Use precise types; do not weaken typing merely to silence mypy.
- Catch only exceptions that the boundary can handle meaningfully.
- Never commit secrets or expose them through logs, tests, patches, or examples.
- Test observable behavior with deterministic, isolated tests.
- For a bug fix, reproduce the failure with a test when practical, then verify
  that the regression test passes after the fix.
- Never delete, skip, or weaken a valid test merely to make validation pass.

## 6. Architecture and documentation

`ARCHITECTURE.md` describes only architecture that currently exists. Do not turn
an unimplemented proposal into a current-system statement.

Before a significant or durable architectural change:

1. read `ARCHITECTURE.md` and `docs/rules/architecture.md`;
2. search `docs/decisions/` for a relevant ADR;
3. create an ADR when the decision has meaningful long-term impact;
4. never silently contradict an Accepted ADR;
5. update architecture and user documentation when the implemented contract
   changes.

## 7. Agent roles, Git safety, and the trust boundary

Claude Code and Codex collaborate under ADR-031 and
`docs/rules/agent-collaboration.md`:

- Claude Code designs, coordinates, verifies, reviews, and performs every Git
  and GitHub write for agent work through the `keiba-ai-agent` GitHub App
  identity (`cc-task` skill).
- Codex implements approved plans and findings inside `.worktrees/<task-id>/`
  (`implement-plan` skill) and performs read-only reviews. Codex never mutates
  Git state, uses `gh`, or accesses the network.
- Only the human owner approves and merges PRs, on GitHub.

Before editing, inspect:

```bash
git status --short --branch
```

Never use destructive cleanup, force-push, rewrite published history, or discard
pre-existing work. Outside the `cc-task` lifecycle, do not commit, push, merge,
rebase, create a branch or tag, or open a PR without explicit user instruction.

The trust boundary is enforced on GitHub: the `main` rulesets require an
up-to-date PR with passing `Quality` and `Test` and code-owner approval of the
latest push, and they allow only administrators to update `main`. The App has
no `workflows` permission. Agents must not try to bypass, weaken, or work around
these rules, and must not read the App private key. Changes to `.github/`,
`.claude/settings.json`, `.codex/`, and `scripts/github-app/` need explicit
human review in the PR.

Skills are split by tool (`.agents/skills/README.md`): Codex-only skills live
in `.agents/skills/`, Claude-only skills in `.claude/skills/`, and shared skills
live in `.agents/skills/` with per-skill symbolic links from `.claude/skills/`.
Shared skills stay tool-neutral.

See `docs/rules/git-workflow.md` for branches, commits, PRs, CI, merge policy,
and the one-time agent identity setup.

## 8. Definition of Done

A task is complete only when all applicable items are true:

- the requested behavior is implemented without unrelated changes;
- relevant tests are present and pass;
- Ruff formatting and lint checks pass;
- mypy passes;
- the full relevant pytest suite passes;
- the diff contains no secrets, generated junk, or accidental edits;
- documentation reflects any changed public or architectural contract; and
- the final report states what actually ran and any remaining limitation.
