# keiba-ai

AI-driven development foundation for a Python 3.12 project.

## Current status

The repository is intentionally at the bootstrap stage. It contains the guarded
development workflow and a tracked, importable package skeleton, but no product
behavior has been implemented yet.

```text
src/keiba_ai/__init__.py
tests/test_package.py
```

There is currently no product CLI, configuration contract, data pipeline,
storage format, or external-service integration. Add those only from an explicit
requirement or an Accepted architecture decision record (ADR).

## Setup and validation

Install the locked development environment:

```bash
uv sync --locked
```

Run the repository checks:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Validate the guarded workflow source with `pwsh` (or `powershell.exe` on
Windows PowerShell). This validation requires an installed Codex CLI version
listed in `scripts/guard-tests/codex-cli-version.txt` and its self-contained
native `codex.exe`; Node launcher shims such as `codex.cmd` and `codex.ps1` are
not trusted. The check exercises the real execution-policy evaluator:

```powershell
pwsh -NoProfile -File scripts/guard-tests/guard-regression.ps1
```

## Development workflow

The initial installation of the AI-driven development foundation is a one-time
human/manual bootstrap because its guarded wrappers, CI baseline, and repository
protection cannot be assumed to exist before they are installed.

After the bootstrap is on `main`, the `Quality` and `Test` checks pass there,
the configured protection for `main` is verified, and a maintainer has installed
the reviewed wrappers in the protected Codex user guard store and restarted
Codex with the repository-and-checkout-bound absolute-path policy active,
non-trivial Codex changes use the guarded autonomous workflow described in
[`docs/AUTONOMOUS_DEVELOPMENT.md`](docs/AUTONOMOUS_DEVELOPMENT.md). That workflow
stops at `MERGE_READY`; merging always requires human approval of the exact
reviewed PR number and HEAD SHA.

Files under `scripts/agent/` are source for review and installation. Codex must
never execute those mutable workspace copies as host-side trust anchors.
Each installation publishes a new immutable guard directory and records the
canonical absolute PowerShell, Git, GitHub CLI, and Codex CLI paths plus the
approved Codex CLI version. If ordinary command discovery resolves a Node
launcher shim, the installer accepts `-CodexExecutablePath` pointing to the
native `codex.exe`. Changing one of those paths or the Codex CLI version requires
a guard reinstall and Codex restart. The `Quality` job runs the real guard
regression for every allow-listed Codex version on both PowerShell 7 and Windows
PowerShell 5.1.

Repository instructions are in [`AGENTS.md`](AGENTS.md). Current architectural
facts and the decision boundary are in [`ARCHITECTURE.md`](ARCHITECTURE.md).
