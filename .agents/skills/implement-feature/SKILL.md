---
name: implement-feature
description: Implement the code-and-test phase of a new feature or intentional behavior change. When repository rules require autonomous-task, use this inside that lifecycle; use it standalone only for explicitly local-only work. Do not use for bug-only fixes or read-only review.
---

# Implement Feature

Implement the requested feature as the smallest coherent change that satisfies the requirement and preserves repository architecture.

This skill owns the implementation phase, not lifecycle coordination. When
repository rules require `autonomous-task`, enter that workflow first and use
this skill for its implementation work. Standalone use is limited to explicitly
local-only work. This skill itself never commits, pushes, opens a pull request,
or merges; the autonomous coordinator performs its guarded Git/GitHub phases.

## 1. Read repository instructions

Before editing:

1. Read the applicable `AGENTS.md`.
2. Read `ARCHITECTURE.md` if present.
3. Read:
   - `docs/rules/coding-style.md`
   - `docs/rules/testing.md`
   - `docs/rules/architecture.md`
4. If the change affects architecture, search `docs/decisions/` for relevant ADRs.
5. Inspect `git status --short --branch` and preserve existing user changes.

A deeper `AGENTS.md` overrides broader instructions within its scope.

## 2. Understand the requested behavior

Identify:

- expected user-visible or API behavior,
- inputs and outputs,
- success criteria,
- important edge cases,
- compatibility constraints,
- affected modules and callers.

If details are missing, infer the smallest behavior consistent with existing code and conventions.
Do not expand scope speculatively.

## 3. Inspect before designing

Search the repository for:

- similar features,
- existing boundaries and data contracts,
- configuration patterns,
- tests covering nearby behavior,
- public APIs that may be affected.

Prefer extending an existing coherent pattern over introducing a new one.

Do not add a new abstraction solely because it might be useful later.

## 4. Check architectural impact

Use `ARCHITECTURE.md`, applicable `AGENTS.md`, repository rules, and Accepted
ADRs as the source of module responsibilities and dependency direction. Treat
the current tree as authoritative: a bootstrap repository may contain only a
minimal skeleton, so do not assume that any product module or behavior already
exists.

Before changing a public API, persistent format, external dependency, security
boundary, or other cross-module contract, identify the affected callers and
compatibility impact. Do not silently contradict an Accepted ADR.

If the feature requires a long-lived architectural decision, create or propose an ADR according to `docs/decisions/README.md`.

## 5. Plan the smallest coherent change

Before editing, define a short implementation plan containing:

1. files/modules to modify,
2. behavioral change,
3. tests to add/update,
4. validation commands.

Keep the plan proportional to the task.

For small changes, 2-4 steps are enough.

## 6. Implement

During implementation:

- keep the diff scoped to the feature,
- preserve existing naming and style,
- prefer explicit types,
- reuse project-owned abstractions,
- avoid unrelated refactors,
- avoid new dependencies unless necessary,
- update all callers when changing a public contract,
- keep backward compatibility unless breaking behavior is explicitly requested.

When adding a dependency:

1. confirm existing dependencies/stdlib are insufficient,
2. stop and obtain explicit user approval for the dependency change,
3. only after approval, update `pyproject.toml`,
4. update `uv.lock`,
5. validate the full relevant test suite.

## 7. Add or update tests

Behavior changes require tests unless testing is genuinely impractical.

Cover the main success path and the important boundary or failure behavior that
could regress. Choose unit or integration coverage according to the affected
contract and existing test conventions.

Do not test implementation details when observable behavior is sufficient.

## 8. Validate incrementally

Run the narrowest useful checks first.

Typical order:

```bash
uv run pytest <relevant-test-path> -q
uv run ruff check <changed-paths>
uv run mypy <changed-paths>
```

Then run repository-level checks when configured:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

If the repository uses different commands, follow repository configuration instead of inventing new tooling.

Do not hide failures by weakening tests, adding unjustified ignores, or suppressing type errors.

## 9. Review the diff

Before completion:

```bash
git status --short
git diff --check
git diff
```

Check that:

- every changed file is relevant,
- no user changes were overwritten,
- no generated junk or secrets were introduced,
- no debug output remains,
- documentation changed when public behavior/setup changed,
- accepted ADRs are not contradicted.

## 10. Completion report

Report concisely:

- what changed,
- important design choices,
- tests/checks run,
- any unresolved risk or limitation.

Do not claim checks passed unless they were actually run successfully.
