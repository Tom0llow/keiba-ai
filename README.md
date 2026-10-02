# keiba-ai

Python 3.12 project with a local race-data Parquet export and an AI-driven
development foundation.

## Current status

The repository contains the guarded development workflow and a local exporter
for the race SQLite database. It remains a non-distributed Python project.

```text
config/data.toml
src/convert_race.py
src/data/race_data.py
src/tests/
```

The project has no build system. `uv sync` installs its locked dependencies
without installing this repository as a Python distribution.

The race-data export and loader are described in
[`ADR-003`](docs/decisions/ADR-003-export-race-tables-as-parquet.md). No modeling
pipeline or external-service integration is implemented.

## Race data export

Put the source SQLite file at `data/raw/race.db`, or change `raw_db` in
`config/data.toml`. The configured paths are relative to that config file.
Install the locked dependencies and export all source tables:

```bash
uv sync --locked
uv run python src/convert_race.py --config config/data.toml
```

The export writes one `<table>.parquet` file per SQLite user table under the
configured `data/processed/` directory. It preserves text, whitespace, NULLs,
and date-like placeholders without parsing or cleaning them. It streams the
large database in batches and publishes the directory after validating the
files. The command refuses to overwrite an existing processed directory.
`data/` is Git-ignored. The source database is opened read-only.

`RaceDataLoader` in `src/data/race_data.py` uses the same config to list
processed tables, read one table as a PyArrow table, or iterate through record
batches. Use batch iteration for large tables because a full-table read loads
the table into memory. Source modules are not installed as a Python distribution;
scripts under `src/` can import `data` directly.

The processed table inventory and column definitions are in
[`docs/table-definition/`](docs/table-definition/README.md).

## Setup and validation

Install the locked development environment:

```bash
uv sync --locked
```

Run the repository checks:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
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
