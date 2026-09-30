# ADR-002: Use a non-package bootstrap layout

- Status: Accepted
- Date: 2026-09-30
- Decision Owners: Repository maintainers
- Related Issues/PRs: N/A
- Supersedes: N/A
- Superseded by: N/A

## Context

The initial bootstrap included an importable `keiba_ai` package solely to give
the Python test suite something to import. The directory update removes that
package and places tests under `src/tests/`. No product behavior depends on the
package. Keeping the build backend while its required module is absent would
make environment synchronization fail.

## Decision

Until a product requirement establishes Python code, this repository is a
non-package project. It has no build system and is not installed as a Python
distribution during `uv sync`. The test suite lives under `src/tests/` and
checks that the synced environment does not install this project. Product
module names and packaging will be selected when product behavior is introduced.

## Rationale

The repository should describe and validate the code that exists. Removing the
unused package avoids presenting a placeholder import path as a product contract.
The environment test preserves a concrete `Test` check without inventing
product behavior.

## Consequences

- `uv sync` installs the locked development dependencies, but no project wheel.
- The project cannot currently be imported as `keiba_ai` or distributed as a
  Python package.
- Python checks target `src/`, and pytest discovers tests in `src/tests/`.
- Product-code coverage is not reported while there is no product code to
  measure. A coverage target and threshold must be chosen when it exists.
- Introducing a product package later requires a deliberate architecture and
  build-configuration update.

## Alternatives Considered

Retaining the importable package skeleton would preserve the existing build and
smoke test, but would keep a placeholder package boundary with no product need.

## Validation

Run `uv sync --locked`, the environment test, Ruff, mypy, the full pytest suite,
and the guard regression. `Quality` and `Test` must pass in CI. The environment
test must fail if the project is installed as a distribution again.

## Security / Privacy Impact

No product data or external service boundary changes. The related agent, CI,
and instruction-file edits are guarded-workflow trust-boundary changes and use
the repository's authorized manual security-bootstrap process.

## Migration / Rollback

Remove the build system and package-import test, update the lockfile and
validation paths, and update current-architecture documentation. Reinstating a
package requires restoring its source module and build configuration together
with an appropriate test and documentation.

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-09-30 | Accepted | Adopted the non-package bootstrap directory structure |
