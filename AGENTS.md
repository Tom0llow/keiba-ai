# AGENTS.md

## 1. Purpose

This file is the durable working contract for AI coding agents in this
repository. Detailed rules live under `docs/rules/`; reusable procedures belong
in skills rather than being duplicated here.

Instructions apply in this order when they conflict:

1. explicit user instructions,
2. the nearest applicable `AGENTS.md`,
3. repository rules, configuration, and Accepted ADRs,
4. this file.

## 2. Current repository state

This repository is a Python 3.12 project at the bootstrap stage. The tracked
product surface is deliberately limited to an importable package skeleton and
its smoke test:

```text
.
├─ src/
│  └─ keiba_ai/
│     └─ __init__.py
├─ tests/
│  └─ test_package.py
├─ docs/
│  ├─ decisions/         # architecture decision records
│  └─ rules/             # coding, architecture, Git, and testing rules
├─ .codex/               # guarded command policy
├─ .github/              # CI and repository automation
├─ scripts/agent/        # reviewed source for guarded wrappers
├─ scripts/guard-tests/  # trust-boundary regression validation
├─ scripts/setup/        # manual trust-boundary installation
├─ AGENTS.md
├─ ARCHITECTURE.md
├─ pyproject.toml
└─ uv.lock
```

No product entry point, CLI contract, configuration layout, domain module,
storage format, or external integration is implemented. Do not restore or infer
one from an earlier prototype. Product behavior and durable architecture must be
introduced by an explicit requirement or an Accepted ADR.

Before making changes, read the rules relevant to the task:

- Code changes: `docs/rules/coding-style.md`
- Architecture or module placement: `ARCHITECTURE.md` and
  `docs/rules/architecture.md`
- Git, branch, commit, or PR work: `docs/rules/git-workflow.md`
- Tests or bug fixes: `docs/rules/testing.md`

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
uv run mypy src tests
uv run pytest
```

Validate the guarded workflow source with PowerShell 7 (`pwsh`) or Windows
PowerShell (`powershell.exe`). The command requires a Codex CLI version listed
in `scripts/guard-tests/codex-cli-version.txt` and a self-contained native
`codex.exe`; Node launcher shims such as `codex.cmd` and `codex.ps1` are not
supported. It evaluates the policy with that CLI and must not skip policy
evaluation:

```powershell
pwsh -NoProfile -File scripts/guard-tests/guard-regression.ps1
```

The `Quality` CI job runs that real regression for every allow-listed Codex
version under both PowerShell 7 and Windows PowerShell 5.1.

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

## 7. Git safety and autonomous workflow

Before editing, inspect:

```bash
git status --short --branch
```

Never use destructive cleanup, force-push, rewrite published history, or discard
pre-existing work. Outside an authorized workflow, do not commit, push, merge,
rebase, create a branch or tag, or open a PR without explicit user instruction.

The first installation of the AI-driven development foundation is a one-time
human/manual bootstrap. Its guarded wrappers, green baseline CI, and repository
protection do not yet exist as usable prerequisites, so this initial change may
be prepared through an explicitly authorized manual or local-only process. This
exception ends after all of the following are true:

1. the bootstrap is present on `main`;
2. `Quality` and `Test` exist and pass on `main`;
3. the configured protection for `main` has been verified;
4. the reviewed wrappers are installed in the protected Codex user guard store
   together with their repository-and-checkout-bound user-layer policy and
   `.git` invocation metadata;
5. Codex has been restarted so that policy is active; and
6. the installed guarded workflow preflight succeeds.

The bootstrap exception is not a general bypass. After activation, every
non-trivial Codex implementation or bug fix must use the `autonomous-task`
workflow unless the user explicitly requests local-only work or read-only
analysis.

Files under `scripts/agent/` are reviewable source and must never be executed as
host-side trust anchors. Autonomous Git/GitHub operations use only their
reviewed copies installed in the protected Codex user guard store. Guarded Git
commands disable all local hooks. Invoke guarded copies only through the exact
absolute executable and script paths recorded in `guard-invocation.json`;
relative guard paths are forbidden. The manifest fixes the canonical absolute
PowerShell, Git, GitHub CLI, and Codex CLI paths and the approved Codex CLI
version. The Codex path must identify a self-contained native `codex.exe`, not a
Node launcher shim; installation may receive it through
`-CodexExecutablePath`. Any path or version change requires guard
reinstallation. Direct use
of the recorded GitHub CLI or Codex CLI executable is forbidden by the generated
policy, and raw Git/GitHub operations must not bypass the wrappers. Ruff, mypy,
and pytest run separately inside the ordinary sandbox and in CI.

The autonomous workflow rejects changes to its trust boundary, including
`.agents/`, `.codex/`, `.github/`, `scripts/agent/`, `scripts/guard-tests/`,
`scripts/github/`, and `scripts/setup/`, plus every `AGENTS.md` or
`AGENTS.override.md` at any depth.
Such changes require an explicitly authorized manual security bootstrap and
guard reinstallation from protected `main`.
Ignored untracked files do not bypass this boundary: protected directories and
every nested `AGENTS.md` / `AGENTS.override.md` are checked explicitly even when
repository, info, or global ignore rules hide them from ordinary status output.

CI waiting, PR/CI inspection, merge readiness, and merge use the same explicit
expected HEAD SHA. PR inspection observes the current PR base as `baseSha` and
uses the recorded task `startSha` as `diffBaseSha` for a complete local binary
diff through the expected head, with external diff and text conversion disabled.
Check evidence comes from the check-runs and commit-status APIs for that expected
head. Observation results include `baseSha` and `headSha`; PR inspection also
includes `diffBaseSha`.
`merge-ready.ps1` and `merge-task.ps1` immediately before an unmerged PR merge
revalidate required contexts, strict status checks, and the
GitHub Actions application ID for `main`. Readiness is bound to both the PR
number and HEAD SHA; binding the task to a replacement PR clears prior readiness
and merge-attempt evidence. The workflow stops at `MERGE_READY`.
A merge requires explicit human approval of the exact reviewed PR number and
HEAD SHA and must use the installed `merge-task.ps1`. If a merge succeeded
remotely but a subsequent communication or cleanup step failed, only a rerun for
the same PR and approved SHA may reconcile the recorded merged PR and finish
cleanup. Never reinterpret the approval for another SHA. Recovery additionally
requires the matching pre-merge attempt record and retains task state while
cleanup remains incomplete.

`start-task.ps1` and `commit-task.ps1` persist write-ahead task state before
their Git state transitions. If either is interrupted, retry the same wrapper
with the same arguments; other task-state-dependent guarded wrappers fail closed
until that retry finishes and clears the pending operation.

See `docs/AUTONOMOUS_DEVELOPMENT.md` and `docs/rules/git-workflow.md`.

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
