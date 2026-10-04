# keiba-ai

Python 3.12 project with local JRA-VAN race-data retrieval, a race-data Parquet
export, and an AI-driven development foundation.

## Current status

The repository contains a local JRA-VAN acquisition boundary through
JVLinkToSQLite and a local SQLite-to-Parquet exporter. It remains a
non-distributed Python project.

```text
config/
├─ data.toml
└─ jvlink.toml
src/
├─ main.py
├─ convert_race.py
└─ data/
   ├─ config.py
   ├─ data_retriever.py
   ├─ race_data.py
   └─ retriever/
```

The project has no build system. `uv sync` installs its locked dependencies
without installing this repository as a Python distribution.

The race-data export and loader are described in
[`ADR-003`](docs/decisions/ADR-003-export-race-tables-as-parquet.md). The local
JRA-VAN acquisition boundary is described in
[`ADR-005`](docs/decisions/ADR-005-use-jvlinktosqlite-acquisition-boundary.md),
config-driven settings plus the Typer CLI are described in
[`ADR-006`](docs/decisions/ADR-006-config-driven-jvlink-settings-and-typer-cli.md),
and cumulative realtime-odds storage is described in
[`ADR-007`](docs/decisions/ADR-007-archive-realtime-odds-for-training-and-inference.md).
No modeling pipeline is implemented yet.

## Race data retrieval

Race data is acquired through a locally installed JVLinkToSQLite executable.
JV-Link and JVLinkToSQLite must already be installed and configured on the
Windows machine. The Python code does not call JV-Link COM directly and does not
store the JRA-VAN service key.

The user-owned `C:\JVLinkToSQLite\setting.xml` is treated as a **seed**. Do not
create or maintain separate `historical.xml`, `historical-odds.xml`, `latest.xml`,
or realtime XML files manually. Retrieval behavior is declared in
`config/jvlink.toml`, and Python generates the XML used for each execution.

Configure machine-specific paths and retrieval profiles in `config/jvlink.toml`:

```toml
[jvlink]
executable = "C:/JVLinkToSQLite/JVLinkToSQLite.exe"
seed_setting = "C:/JVLinkToSQLite/setting.xml"

[historical]
normal_update = false
setup_update = true
realtime_update = false
# DataSpec lists and the initial start_datetime follow in the committed config.

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

[realtime_history]
normal_update = false
setup_update = false
realtime_update = true
realtime_data_specs = ["0B41", "0B42"]

[realtime_current]
normal_update = false
setup_update = false
realtime_update = true
realtime_data_specs = ["0B31", "0B32"]
```

Storage paths are configured in `config/data.toml`:

```toml
[paths]
raw_db = "../data/raw/race.db"
processed_dir = "../data/processed"
jvlink_runtime_dir = "../data/runtime/jvlink"
```

Install the locked environment:

```powershell
uv sync --locked
```

The public retrieval interface is the Typer CLI in `src/main.py`.

Initial historical retrieval:

```powershell
uv run python src/main.py retrieve historical
```

Latest incremental/realtime retrieval:

```powershell
uv run python src/main.py retrieve latest
uv run python src/main.py retrieve realtime `
  --date 2026-10-04 `
  --jyo 05 `
  --kaiji 04 `
  --nichiji 08 `
  --race 11
```

Alternative config files can be supplied explicitly with `--data-config` and
`--jvlink-config`.

### Setting lifecycle

`JVLinkSettingBuilder` reads the seed XML and applies the selected profile
exclusively: DataSpecs not listed for that section are disabled.

For `historical`, the generated base setting enables setup-data retrieval and is
stored only in a temporary directory. After the base database exists, the
retriever reads race keys from `NL_RA_RACE` and generates a temporary per-race
setting for the configured historical odds DataSpecs (`0B41` and `0B42` by
default). Historical generated settings are deleted when the command finishes.
The seed XML is never modified by this flow.

For `latest`, the first run creates
`data/runtime/jvlink/latest.xml` from the seed and applies the `[latest]`
profile. JVLinkToSQLite is then allowed to update that runtime XML with its
latest-read positions. Later runs use the same runtime XML as their source,
reapply the profile, and preserve the accumulated read state. The runtime file
is under the Git-ignored `data/` directory; the user-owned seed remains
unchanged.

JVLinkToSQLite realtime O1/O2 tables are transient staging tables and can be
recreated by the next realtime execution. Therefore historical odds are copied
immediately into cumulative raw tables:

```text
ARCHIVE_O1_ODDS_TANFUKUWAKU
ARCHIVE_O2_ODDS_UMAREN
```

The archive tables preserve the staging-table column names and order and use
full-row set deduplication. Distinct `HappyoTime` observations are retained while
repeating an identical retrieval is idempotent.

`latest` creates `data/runtime/jvlink/latest.xml` from the seed on its first run.
JVLinkToSQLite may update that runtime XML with its latest-read positions. Later
runs reuse the runtime XML as their source, reapply the `[latest]` profile, and
preserve the accumulated read state. `data/` is Git-ignored, so this mutable
machine-local state is not committed.

`realtime` is the prediction-time path for one explicit race. It first executes
`0B41` / `0B42` to obtain the time-series O1/O2 history available at the
retrieval point, archives those rows, then executes `0B31` / `0B32` for the
current O1/O2 snapshot and archives that result as well. The two-digit venue,
meeting, meeting-day, and race-number components become one `JVRaceKey`. Both
realtime executions use temporary XML and do not advance persistent read state.

Historical and prediction-time O1/O2 data therefore converge on the same
`ARCHIVE_*` column contract. Feature generation should consume the archive rather
than the ephemeral JVLinkToSQLite `RT_*` tables.

## Race data export

Put the source SQLite file at `data/raw/race.db`, or change `raw_db` in
`config/data.toml`. The configured paths are relative to that config file.
Export all source tables with:

```bash
uv run python src/convert_race.py --config config/data.toml
```

The export writes one `<table>.parquet` file per SQLite user table under the
configured `data/processed/` directory. It preserves text, whitespace, NULLs,
and date-like placeholders without parsing or cleaning them. It streams the
large database in batches and refuses to overwrite an existing processed
directory. The source database is opened read-only.

`RaceDataLoader` in `src/data/race_data.py` uses the same config to list
processed tables, read one table as a PyArrow table, or iterate through record
batches. The processed table inventory and column definitions are in
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
Windows PowerShell):

```powershell
pwsh -NoProfile -File scripts/guard-tests/guard-regression.ps1
```

## Development workflow

Non-trivial Codex changes use the guarded autonomous workflow described in
[`docs/AUTONOMOUS_DEVELOPMENT.md`](docs/AUTONOMOUS_DEVELOPMENT.md). That workflow
stops at `MERGE_READY`; merging always requires human approval of the exact
reviewed PR number and HEAD SHA.

Repository instructions are in [`AGENTS.md`](AGENTS.md). Current architectural
facts and the decision boundary are in [`ARCHITECTURE.md`](ARCHITECTURE.md).
