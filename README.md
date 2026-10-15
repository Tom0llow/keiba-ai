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
├─ jvlink.toml
└─ features.toml

src/
├─ main.py                       # run.app.appの起動
├─ run/                          # CLI登録・実行・入力変換・JSON出力
├─ retriever/                    # JV-Link取得と台帳・ロック
├─ preprocesser/                 # raw SQLiteからParquetへの公開
├─ utils/
│  ├─ data_loader.py              # 処理済みデータ読込API
│  └─ loader/                     # Parquet・JSON読込
├─ settings/data_paths.py         # 共有パス設定
├─ domain/race_key.py             # 共有レース識別型
├─ features/
│  ├─ catalog/                    # TOML読込・実装登録
│  ├─ contracts/                  # 入力・中間行・結果の型
│  ├─ validation/                 # 入力・時点・テーブル検証
│  ├─ generation/                 # 共通生成手順・正規化
│  ├─ tables/                     # スキーマ・構築・Parquet保存
│  └─ ...                         # 説明変数固有の入力・生成
├─ make_datamart/
│  ├─ builder.py                  # 中間テーブル読込・純粋な結合
│  ├─ validation/table.py         # 結合後のスキーマ・行検証
│  └─ tables/                    # 列・metadata契約とParquet保存
├─ models/                        # モデル入力・学習・評価
└─ tests/
   └─ ...
```

The project has no build system. `uv sync` installs its locked dependencies
without installing this repository as a Python distribution.

The active data boundaries are described by ADR-005 through ADR-008. ADR-008
supersedes the earlier ADR-003 publication boundary and records the split between
raw SQLite preprocessing and processed Parquet loading. ADR-020 records the
current source placement, runtime boundary and declarative feature registration.

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
it directly. SQLite reads live under `src/preprocesser/`, while
`src/utils/loader/` reads processed Parquet only.

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

`src/utils/data_loader.py` is the public loading facade.
`src/utils/loader/read_parquet.py` is the concrete reader.

The loader can:

- list and read complete tables from the active snapshot;
- iterate large Parquet tables in bounded Arrow record batches;
- read prediction-time O1/O2 Parquet for a specified `RaceKey`.

There is intentionally no `loader/read_sqlite.py`. Raw `race.db` access belongs
to preprocessing and is implemented by
`src/preprocesser/read_sqlite.py`. Realtime is also loaded through
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
$guardInvocation = Get-Content -LiteralPath .git/codex-guard/guard-invocation.json -Raw | ConvertFrom-Json
pwsh -NoProfile -File scripts/guard-tests/guard-regression.ps1 -CodexExecutablePath $guardInvocation.codexPath
```

Without installed invocation metadata, supply a verified native `codex.exe`
whose version is listed in `scripts/guard-tests/codex-cli-version.txt`.

## Development workflow

Non-trivial autonomous changes use the guarded workflow described in
`docs/AUTONOMOUS_DEVELOPMENT.md`. Host-side Git/GitHub operations use installed,
hash-verified wrappers; mutable repository copies under `scripts/agent/` are
reviewable sources rather than trust anchors. The workflow stops at
`MERGE_READY`; merging requires explicit human approval of the exact PR and HEAD
SHA.

Guard source repairs require review and reinstallation from protected `main`.
See [guarded workflow repair and manual setup](docs/GUARDED_WORKFLOW_REPAIR.md)
for the PowerShell MSI migration, pinned CLI regression, guard reinstallation,
and execution-tool integration checks.

Repository instructions are in `AGENTS.md`. Current architectural facts are in
`ARCHITECTURE.md`.

## Feature registration and Python API migration

`config/features.toml` owns the F01-F21 group IDs, names and declaration order.
These are stable JSON identifiers, independent of the numeric model allow-list.
Each `[[features]]` entry contains only `id` and `name`. The catalog must match
all implemented groups; duplicate IDs/names, malformed entries, unknown names
and missing implementations are rejected. Changing an ID requires considering
existing JSON consumers. Importing modules or requesting CLI help never reads it.

```bash
uv run python src/main.py model explanatory-variables --input inputs.json --output features.json --features-config config/features.toml
```

`--features-config` defaults to `config/features.toml`. Other commands and their
existing arguments, JSON keys and exit codes retain their contracts.

Python callers load the catalog explicitly once and reuse the same registry:

```python
from features.catalog.loader import load_feature_definitions
from features.catalog.registry import create_feature_registry
from features.explanatory_variables import build_explanatory_variables
from features.jockey_combination import build_jockey_combination
from features.tables.parquet import read_feature_table, write_feature_table

registry = create_feature_registry(load_feature_definitions("config/features.toml"))
result = build_explanatory_variables(batch_inputs, registry=registry)
definition = registry.by_name("jockey_combination").definition
table = build_jockey_combination(
    jockey_inputs, definition=definition, column_types=column_types
)
write_feature_table(table, "jockey.parquet", registered_names=registry.names)
restored = read_feature_table("jockey.parquet", registered_names=registry.names)
```

`batch_inputs`, `jockey_inputs`, and `column_types` above are caller-provided
validated inputs and explicit Arrow scalar types. Registration does not approve
new calculation rules or add columns to model training.

The `features` package no longer re-exports implementations. Import individual
build APIs from their feature modules, `FeatureTableRow` from
`features.contracts.rows`, input/result types from `features.contracts.types`,
table construction from `features.tables.build`, table validation from
`features.validation.table`, and persistence from `features.tables.parquet`.
The original previous-race result, odds ratio and pedigree build APIs keep their
arguments and metadata and receive no F identifiers. Other individual build APIs
now require `definition`; batch generation/audit require `registry`. Table and
datamart APIs require `registered_names=registry.names` for those groups and
retain fixed validation for the original three when omitted.

Import `DataRetriever` from `retriever.data_retriever`, `DataPreprocesser` from
`preprocesser.data_preprocesser`, `DataLoader` from `utils.data_loader`,
`DataPaths` from `settings.data_paths`, and `RaceKey` from `domain.race_key`.
Raw race-key rows are converted by `retriever.race_key_parser.race_key_from_row`.
Import datamart construction from `make_datamart.builder`, validation from
`make_datamart.validation.table`, and persistence from
`make_datamart.tables.parquet`. All five existing public functions remain
available from both `make_datamart` and `make_datamart.builder`. The former
`src/data/`, `features/common/`, `features/make_features.py` and module `SPEC`
constants are removed. Acquired data and existing Parquet artifacts remain in
their original locations and formats. `docs/GUARDED_WORKFLOW_REPAIR.md` remains
available because removing its guarded workflow references requires a separate
manual authorization.
