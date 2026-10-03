# keiba-ai

Python 3.12 project with local JRA-VAN race-data retrieval, a race-data Parquet
export, and an AI-driven development foundation.

## Current status

The repository contains the guarded development workflow, a local JRA-VAN data
retrieval boundary through JVLinkToSQLite, and a local exporter for the race
SQLite database. It remains a non-distributed Python project.

```text
config/data.toml
src/convert_race.py
src/data/data_retriever.py
src/data/race_data.py
src/data/retriever/
src/tests/
```

The project has no build system. `uv sync` installs its locked dependencies
without installing this repository as a Python distribution.

The race-data export and loader are described in
[`ADR-003`](docs/decisions/ADR-003-export-race-tables-as-parquet.md). The local
JRA-VAN acquisition boundary is described in
[`ADR-005`](docs/decisions/ADR-005-use-jvlinktosqlite-acquisition-boundary.md).
No modeling pipeline is implemented yet.

## Race data retrieval

Race data is acquired through a locally installed JVLinkToSQLite executable.
The Python code does not call JV-Link COM directly and does not store the
JRA-VAN service key. JV-Link and JVLinkToSQLite must already be installed and
configured on the Windows machine before running the retriever.

`DataRetriever` needs these local files:

- `JVLinkToSQLite.exe`: the importer executable, for example
  `C:\JVLinkToSQLite\JVLinkToSQLite.exe`;
- a historical setting XML used for the normal historical/base import;
- a historical-odds setting XML containing `0B41` and `0B42` entries with
  `JVRaceKey` children;
- a latest setting XML whose latest-read position JVLinkToSQLite may update;
- the raw SQLite destination, normally `data/raw/race.db`.

The historical-odds template itself is not modified. For each race on or after
2003-10-04, the retriever creates a temporary copy with that race's key and
executes `0B41` and `0B42`. The latest setting is persistent because
JVLinkToSQLite uses it to advance the next incremental read position.

Install the locked environment first:

```powershell
uv sync --locked
```

The current interface is a Python API rather than a dedicated command-line
entry point. From the repository root in PowerShell, set `PYTHONPATH` to `src`
and construct one `DataRetriever`:

```powershell
$env:PYTHONPATH = "src"

@'
from pathlib import Path

from data.data_retriever import DataRetriever

retriever = DataRetriever(
    executable=Path(r"C:\JVLinkToSQLite\JVLinkToSQLite.exe"),
    database=Path(r"data\raw\race.db"),
    historical_setting=Path(r"C:\JVLinkToSQLite\historical.xml"),
    historical_odds_setting=Path(r"C:\JVLinkToSQLite\historical-odds.xml"),
    latest_setting=Path(r"C:\JVLinkToSQLite\latest.xml"),
)

count = retriever.retrieve_historical()
print(f"historical odds retrieved for {count} races")
'@ | uv run python -
```

`retrieve_historical()` first executes the normal historical import, reads the
race-key components from `NL_RA_RACE`, and then requests the available `0B41`
and `0B42` time-series odds for each eligible race. It can therefore take a
long time on an initial full import.

For normal incremental updates, use the same paths and call
`retrieve_latest()` instead:

```powershell
$env:PYTHONPATH = "src"

@'
from pathlib import Path

from data.data_retriever import DataRetriever

retriever = DataRetriever(
    executable=Path(r"C:\JVLinkToSQLite\JVLinkToSQLite.exe"),
    database=Path(r"data\raw\race.db"),
    historical_setting=Path(r"C:\JVLinkToSQLite\historical.xml"),
    historical_odds_setting=Path(r"C:\JVLinkToSQLite\historical-odds.xml"),
    latest_setting=Path(r"C:\JVLinkToSQLite\latest.xml"),
)

retriever.retrieve_latest()
'@ | uv run python -
```

The three XML file names above are examples; pass the actual JVLinkToSQLite
setting files used on the local machine. Do not commit JRA-VAN credentials or
machine-specific setting files containing sensitive information.

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

## Planned racing AI

The agreed product requirements are in [`docs/requirements.md`](docs/requirements.md),
and the decided portion of its behavior is in
[`docs/specification.md`](docs/specification.md). Design proposals and open
questions remain in `docs/discussions/`; no prediction or betting system is
implemented yet.

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
