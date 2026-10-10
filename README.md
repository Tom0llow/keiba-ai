# keiba-ai

Python 3.12 project with local JRA-VAN race-data retrieval, raw-to-Parquet
preprocessing, processed-data loading, and an AI-driven development foundation.

## Current status

The repository contains the guarded development workflow, a local JRA-VAN data
retrieval boundary through JVLinkToSQLite, versioned Parquet publication, and a
Parquet-only loader boundary. It remains a non-distributed Python project.

```text
config/
├─ data.toml
└─ jvlink.toml
src/
├─ main.py
└─ data/
   ├─ config.py
   ├─ data_retriever.py
   ├─ data_preprocesser.py
   ├─ data_loader.py
   ├─ race_key.py
   ├─ retriever/
   ├─ preprocesser/
   │  ├─ read_sqlite.py
   │  └─ snapshot.py
   └─ loader/
      └─ read_parquet.py
```

The project has no build system. `uv sync` installs its locked dependencies
without installing this repository as a Python distribution.

The active data boundaries are described by ADR-005 through ADR-008. ADR-008
supersedes the earlier ADR-003 publication boundary and records the split between
raw SQLite preprocessing and processed Parquet loading.

## Data flow

All data paths converge on one storage dependency direction:

```text
JV-Link
  -> JVLinkToSQLite
  -> data/raw/race.db
  -> DataPreprocesser
  -> Parquet
  -> DataLoader
  -> training / analysis / prediction
```

`race.db` is the mutable raw acquisition store. Model-facing code does not read
it directly. SQLite reads live under `src/data/preprocesser/`, while
`src/data/loader/` reads processed Parquet only.

Storage paths are configured in `config/data.toml`:

```toml
[paths]
raw_db = "../data/raw/race.db"
processed_dir = "../data/processed"
jvlink_runtime_dir = "../data/runtime/jvlink"
```

## Race data retrieval

Race data is acquired through a locally installed JVLinkToSQLite executable.
JV-Link and JVLinkToSQLite must already be installed and configured on Windows.
The Python code does not call JV-Link COM directly and does not store the
JRA-VAN service key.

The user-owned `C:\JVLinkToSQLite\setting.xml` is treated as a seed. Retrieval
behavior is declared in `config/jvlink.toml`, and Python generates execution XML
for historical-basic, historical-odds, latest, and realtime modes.

Important profiles include:

```toml
[historical_odds]
realtime_data_specs = ["0B41", "0B42"]
race_start_date = 2003-10-04
skip_existing = true

[realtime_history]
realtime_data_specs = ["0B41", "0B42"]

[realtime_current]
realtime_data_specs = ["0B31", "0B32"]
```

`historical-odds` requires `[historical_odds].skip_existing = true` and requests
only the missing O1/O2 DataSpecs for each complete race key in `NL_RA_RACE`.
`0B41` is skipped when that race has rows in `ARCHIVE_O1_ODDS_TANFUKUWAKU`;
`0B42` is skipped when it has rows in `ARCHIVE_O2_ODDS_UMAREN`. Missing or empty
archive tables are retrieved. Row presence does not prove that every time-series
observation was acquired, so this workflow intentionally does not support
refetching already archived race/spec pairs. This option does not change realtime
retrieval.

The checked-in `[historical]` profile enables `setup_update`, so the
`historical-basic` command retrieves the configured base-data DataSpecs before
publishing the complete Parquet snapshot. Set the update flags to `false` only
when the corresponding base-data retrieval is intentionally disabled. A missing
database still fails before retrieval.

The target race for realtime retrieval can also be configured in
`config/jvlink.toml`:

```toml
[realtime]
date = 2026-10-04
jyo = "05"
kaiji = "04"
nichiji = "08"
race = "11"
```

When `[realtime]` is configured, the target race options can be omitted from
the CLI. Supplying all five CLI options overrides the configured target race.

JVLinkToSQLite realtime O1/O2 tables are transient staging tables. They are
copied immediately into cumulative raw tables:

```text
ARCHIVE_O1_ODDS_TANFUKUWAKU
ARCHIVE_O2_ODDS_UMAREN
```

Repeated identical rows are deduplicated while distinct `HappyoTime`
observations are retained.

## CLI

Install dependencies and run commands from the repository root:

```powershell
uv sync --locked

uv run python src/main.py --retrieve --mode=historical-basic
uv run python src/main.py --retrieve --mode=historical-odds
uv run python src/main.py --retrieve --mode=latest
uv run python src/main.py --retrieve --mode=realtime
```

Retrieval and complete Parquet publication are separated by workflow:

- `--retrieve --mode=historical-basic`: run the enabled base-data updates, then publish one
  complete Parquet snapshot. This mode does not retrieve historical O1/O2 odds.
- `--retrieve --mode=historical-odds`: retrieve the oldest unfinished year of historical
  O1/O2 odds, record per-race progress, and continue year by year. Complete Parquet
  publication is deferred until every managed year is raw-complete, then performed once.
  If retrieval or publication fails, the raw database and progress ledger remain available
  for the next manual run. The command stops when the operator interrupts it or no target
  years remain.
  Use `--plan-only` to inspect the next year without writing or starting JVLinkToSQLite.
  The command starts one continuous process; it does not register Task Scheduler
  jobs or apply a weekday rule. A successful run with a valid empty realtime table is recorded
  as `provider_missing/jvopen_no_data` only when the captured JVOpen/JVRTOpen return code is
  `-1`; it is not retried. If the API code is unavailable, the result remains
  `failed/empty_response_unverified`. Missing tables, invalid schemas, archive failures, and
  process failures remain `failed` and stop the run. The official JV-Link API error-code list
  is published by [JRA-VAN](https://developer.jra-van.jp/t/topic/822).
  The progress ledger preserves the process exit code separately from the captured
  DataSpec-specific API name and return code.
  After all managed years are complete, the CLI prints an English message before the full
  Parquet rebuild, then prints whether the rebuild completed or failed. The rebuild can take
  a long time for a large raw database.
  When an older v1 ledger has a previously classified `provider_missing/jvopen_no_data`
  row without API columns, the first write migrates it to
  `provider_missing/legacy_provider_missing`; new automatic `jvopen_no_data` rows always
  require captured `JVOpen`/`JVRTOpen = -1` evidence.
  After confirming a JRA-VAN-side gap, confirm that exact failed race without starting
  JVLinkToSQLite:

  ```powershell
  uv run python src/main.py --retrieve --mode=historical-odds `
    --confirm-provider-missing --date 2008-02-03 --jyo 05 --kaiji 01 --nichiji 02 --race 01
  ```

  Both O1/O2 (`0B41`/`0B42`) are confirmed by default. Use `--data-spec 0B41` or
  `--data-spec 0B42` to confirm only one. The command accepts only failed
  `empty_response_unverified` entries whose current archive count is still zero.
- `--retrieve --mode=latest`: update raw data, then publish a refreshed complete Parquet
  snapshot.
- `--retrieve --mode=realtime`: retrieve and archive the target race's history/current
  odds, then publish race-scoped Parquet for that same `RaceKey`.

All retrieval modes use the flag-based interface. The separate `preprocess`
command remains available for publishing processed data from existing raw data.

If raw data already exists, a complete processed snapshot can be rebuilt without
new JRA-VAN retrieval:

```powershell
uv run python src/main.py preprocess rebuild
```

Alternative config files can be supplied with `--data-config` and
`--jvlink-config` where applicable.

## Processed Parquet layout

Complete historical/latest datasets are immutable snapshots:

```text
data/processed/
├─ CURRENT
└─ snapshots/
   └─ <snapshot-id>/
      ├─ NL_RA_RACE.parquet
      ├─ ARCHIVE_O1_ODDS_TANFUKUWAKU.parquet
      ├─ ARCHIVE_O2_ODDS_UMAREN.parquet
      └─ ...
```

`CURRENT` is replaced atomically only after every table in a new snapshot has
been written and validated. A failed rebuild therefore leaves the previous
snapshot active.

Prediction-time realtime Parquet is race-scoped:

```text
data/processed/realtime/<race-id>/
├─ CURRENT
└─ versions/
   └─ <version-id>/
      ├─ ARCHIVE_O1_ODDS_TANFUKUWAKU.parquet
      └─ ARCHIVE_O2_ODDS_UMAREN.parquet
```

Realtime preprocessing filters the cumulative raw archive to the exact race and
publishes the two O1/O2 files as one version before switching the race-local
`CURRENT` pointer. It does not rebuild all historical Parquet before inference.

Old snapshots and realtime versions are intentionally retained for rollback and
reproducibility until a separate retention policy is introduced.

## Data loader

`src/data/data_loader.py` is the public loading facade.
`src/data/loader/read_parquet.py` is the concrete reader.

The loader can:

- list and read complete tables from the active snapshot;
- iterate large Parquet tables in bounded Arrow record batches;
- read prediction-time O1/O2 Parquet for a specified `RaceKey`.

There is intentionally no `loader/read_sqlite.py`. Raw `race.db` access belongs
to preprocessing and is implemented by
`src/data/preprocesser/read_sqlite.py`. Realtime is also loaded through
`read_parquet.py` after its race-scoped Parquet version has been published.

## Planned racing AI

The agreed product requirements are in `docs/requirements.md`, and decided
behavior is in `docs/specification.md`. Design proposals and open questions
remain in `docs/discussions/`; no prediction or betting model pipeline has been
implemented yet.

The detailed LambdaRank MVP implementation proposal is in
[implementation design](docs/implementation-design.md).

The current explanatory-variable contracts are listed in the
[explanatory variable list](docs/feature-list.md).

## Setup and validation

Install the locked development environment:

```bash
uv sync --locked
```

Run repository checks:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Guard trust-boundary validation is run separately by the Quality workflow and can
also be invoked with:

```powershell
pwsh -NoProfile -File scripts/guard-tests/guard-regression.ps1
```

## Development workflow

Non-trivial autonomous changes use the guarded workflow described in
`docs/AUTONOMOUS_DEVELOPMENT.md`. Host-side Git/GitHub operations use installed,
hash-verified wrappers; mutable repository copies under `scripts/agent/` are
reviewable sources rather than trust anchors. The workflow stops at
`MERGE_READY`; merging requires explicit human approval of the exact PR and HEAD
SHA.

Repository instructions are in `AGENTS.md`. Current architectural facts are in
`ARCHITECTURE.md`.
