# Testing

## 1. Principles

Tests provide deterministic evidence about observable behavior. Prefer focused
unit tests, use integration tests at real boundaries, and add end-to-end tests
only when lower-level coverage cannot demonstrate a critical user flow.

The repository is currently a package skeleton. `tests/test_package.py` verifies
that the package can be imported; it does not imply any product behavior or
architecture.

## 2. Framework and commands

Use pytest:

```bash
uv run pytest
```

Run the nearest test first when changing behavior:

```bash
uv run pytest tests/test_package.py -q
```

Final repository validation is:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Trust-boundary PowerShell validation is also required:

```powershell
pwsh -NoProfile -File scripts/guard-tests/guard-regression.ps1
```

This command requires the self-contained native `codex.exe` for a Codex CLI
version explicitly listed in `scripts/guard-tests/codex-cli-version.txt` and
runs real `codex execpolicy check` cases. Node launcher shims such as
`codex.cmd` and `codex.ps1` are unsupported. A missing, shimmed, or unlisted CLI
is a failed validation, not a reason to skip execution-policy coverage.

The `Quality` CI job repeats this real regression for every allow-listed Codex
version under both PowerShell 7 and Windows PowerShell 5.1.
The regression also verifies with a temporary Git repository that ignored
untracked agent instructions and skill paths cannot bypass protected-path or
clean-tree checks.

## 3. Behavior changes

New behavior should cover:

- the main success path;
- important boundaries and edge cases; and
- meaningful failure behavior.

For a bug fix:

1. write or identify a test that reproduces the defect;
2. confirm that it fails for the expected reason when practical;
3. implement the smallest fix;
4. confirm that the regression test passes; and
5. run related and repository-level checks.

Do not write tests for speculative features. Tests and fixtures must follow the
explicit requirement and any Accepted ADR.

## 4. Test design

- Name tests after the behavior they demonstrate.
- Assert public or otherwise observable results instead of private
  implementation details.
- Keep fixtures small, explicit, composable, and narrowly scoped.
- Use parametrization for multiple cases exercising the same behavior.
- Mock system boundaries, not internal collaborators merely to mirror the
  implementation.
- Include type annotations when they improve fixture or helper clarity.

Arrange / Act / Assert is useful when it makes setup and expectations clearer,
but comments need not label obvious phases.

## 5. Isolation and determinism

Tests must not depend on execution order, machine-specific paths, public network
access, external credentials, or user-owned data.

- Use `tmp_path` for filesystem output.
- Use controlled time and fixed randomness when those affect assertions.
- Avoid sleep-based synchronization.
- Use test-owned databases or services, never production resources.
- Clean up external state created by an integration test.
- Keep the default suite runnable in the repository's documented development
  environment.

If a future requirement introduces chronology, concurrency, randomness,
compatibility, or another important invariant, add a test that would fail if
that invariant were violated. Do not establish the contract only in prose.

## 6. External boundaries

Unit tests must not require arbitrary public network access. Replace external
services at the adapter boundary and reserve real-service checks for explicitly
configured integration tests.

For filesystem, database, serialization, subprocess, or network integrations,
test both successful behavior and relevant failure handling. Validate that tests
cannot overwrite source or user data.

Mark tests that require a special environment or are materially slow when the
repository configuration supports such markers.

## 7. Validation workflow

Validate incrementally:

1. the changed test or nearest test module;
2. the related test group;
3. formatting, lint, and type checks; and
4. the full pytest suite.

Review failures rather than hiding them. Do not make a suite pass by deleting a
valid test, weakening an assertion, adding an unjustified `skip` or `xfail`,
swallowing an unexpected exception, or increasing a timeout without identifying
the cause.

Coverage is a diagnostic, not the goal. Do not add meaningless assertions or
lower a configured threshold merely to increase the reported result.

## 8. Review checklist

- Does the test describe required behavior?
- Would it fail if the defect or contract violation returned?
- Is it deterministic and isolated?
- Is setup understandable and no larger than necessary?
- Does it avoid coupling to private implementation details?
- Are important boundaries and errors covered?
- Does it leave the worktree and external state clean?
