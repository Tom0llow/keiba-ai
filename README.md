# keiba-ai

Python 3.12 project with local JRA-VAN race-data retrieval, a local race-data
Parquet export, and an AI-driven development foundation.

## Current status

The repository contains the guarded development workflow, a local JRA-VAN data
retrieval boundary through JVLinkToSQLite, and a local exporter for the race
SQLite database. It remains a non-distributed Python project.

```text
config/
├─ data.toml
└─ jvlink.toml
src/
├─ main.py
├─ convert_race.py
├─ data/
│  ├─ config.py
│  ├─ data_retriever.py
│  ├─ race_data.py
│  └─ retriever/
└─ tests/
```

The project has no build system. `uv sync` installs its locked dependencies
without installing this repository as a Python distribution.

The race-data export and loader are described in
[`ADR-003`](docs/decisions/ADR-003-export-race-tables-as-parquet.md). The local
JRA-VAN acquisition boundary is described in
[`ADR-005`](docs/decisions/ADR-005-use-jvlinktosqlite-acquisition-boundary.md),
and config-driven settings plus the Typer CLI are described in
[`ADR-006`](docs/decisions/ADR-006-config-driven-jvlink-settings-and-typer-cli.md).
No modeling pipeline is implemented yet.

## Race data retrieval

Race data is acquired through a locally installed JVLinkToSQLite executable.
JV-Link and JVLinkToSQLite must already be installed and configured on the
Windows machine. The Python code does not call JV-Link COM directly and does not
store the JRA-VAN service key.

The user-owned `C:\JVLinkToSQLite\setting.xml` is treated as a seed. Do not
create or maintain separate `historical.xml`, `historical-odds.xml`, and
`latest.xml` files manually. Retrieval behavior is declared in
`config/jvlink.toml`, and Python generates the XML used for each execution.

Configure the JVLink paths and retrieval profiles in `config/jvlink.toml`:

```toml
[jvlink]
executable = "C:/JVLinkToSQLite/JVLinkToSQLite.exe"
seed_setting = "C:/JVLinkToSQLite/setting.xml"

[historical]
normal_update = false
setup_update = true
realtime_update = false

[historical_odds]
normal_update = false
setup_update = false
realtime_update = true
realtime_data_specs = ["0B41", "0B42"]
race_start_date = 2003-10-04

[latest]
normal_update = true
setup_update = false
realtime_update = true
```

The committed file also contains the explicit DataSpec allow-lists and the
historical setup start datetime. DataSpecs not listed for a section are disabled
when an execution setting is generated.

Storage paths are configured in `config/data.toml`:

```toml
[paths]
raw_db = "../data/raw/race.db"
processed_dir = "../data/processed"
jvlink_runtime_dir = "../data/runtime/jvlink"
```

Install the locked dependencies and run the Typer CLI from the repository root:

```powershell
uv sync --locked
uv run python src/main.py retrieve historical
uv run python src/main.py retrieve latest
```

Alternative config files can be supplied explicitly:

```powershell
uv run python src/main.py retrieve historical `
  --data-config config/data.toml `
  --jvlink-config config/jvlink.toml
```

`historical` generates its base and per-race odds settings under a temporary
directory and removes them when the command finishes. The seed XML is not
modified. After the base database exists, the retriever reads exact race keys
from `NL_RA_RACE` and requests the configured historical odds DataSpecs for each
eligible race.

`latest` creates `data/runtime/jvlink/latest.xml` from the seed on its first run.
JVLinkToSQLite may update that runtime XML with its latest-read positions. Later
runs reuse the runtime XML as their source, reapply the `[latest]` profile, and
preserve the accumulated read state. `data/` is Git-ignored, so this mutable
machine-local state is not committed.

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
