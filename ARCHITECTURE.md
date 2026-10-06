# Architecture — keiba-ai

## Status

This repository contains development automation, local JRA-VAN race-data
retrieval, raw-to-processed preprocessing, and Parquet loading for training and
prediction. It remains uninstalled as a Python distribution.

An earlier local prototype is not a source of current requirements or design
authority. Product behavior and durable architectural decisions must come from
an explicit requirement or an Accepted architecture decision record (ADR).

## Current runtime and tooling

- Python: 3.12
- Environment and dependency manager: uv
- Data CLI: Typer
- Formatter and linter: Ruff
- Type checker: mypy
- Test framework: pytest
- Automation: GitHub Actions and guarded PowerShell wrappers

The locked development environment is defined by `pyproject.toml` and `uv.lock`.
The project has no build system, so `uv sync` installs its dependencies without
installing this repository as a Python distribution.

Host-side autonomous Git/GitHub operations run only from hash-verified wrapper
copies installed in the protected Codex user guard store. Every installation
publishes a new immutable directory identified by repository policy ID, source
SHA, and installation ID; earlier immutable directories remain untouched.
`.git/codex-guard/` contains only invocation metadata, and tracked files under
`scripts/` are reviewable sources, not executable trust anchors. A
repository-and-checkout-bound user-layer execution rule permits only the
installed wrappers' absolute paths. The manifest and runtime verification bind
the canonical physical PowerShell, Git, GitHub CLI, and Codex CLI paths and the
approved Codex CLI version. The trusted Codex path is a self-contained native
`codex.exe`; Node launcher shims such as `codex.cmd` and `codex.ps1` are outside
the supported boundary. This boundary also uses a protected system PowerShell
host and an exclusive repository workflow lock as defined by ADR-001.

PR and CI observations are bound to one explicit expected HEAD SHA through
merge readiness and human approval. PR inspection observes the current PR base
object ID as `baseSha`, then creates the complete local binary diff from the
recorded task `startSha` (`diffBaseSha`) through the expected head with external
diff and text conversion disabled. Checks use the check-runs and commit-status
APIs for that expected head. Every observation reports `baseSha` and `headSha`;
PR inspection also reports `diffBaseSha`. Merge readiness is bound to the PR
number and HEAD SHA; rebinding the task to a replacement PR clears prior
readiness and merge-attempt evidence. Merge readiness and the final unmerged-PR
merge path revalidate the protected `main` branch's required contexts, strict
status setting, and GitHub Actions application ID. If the remote merge succeeds
before a communication or cleanup failure, the remaining task state permits
recovery only after the same PR, task HEAD, merge-ready SHA, approved SHA, and
recorded pre-merge attempt and merge timestamp agree. Incomplete cleanup keeps
the guarded task state for an exact-PR/exact-SHA retry. User-layer trust paths
are rejected under both the writable repository and system temporary directory.

Repository-wide verification uses:

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Guard trust-boundary validation runs separately:

```powershell
pwsh -NoProfile -File scripts/guard-tests/guard-regression.ps1
```

The `Quality` CI job performs that real regression for every allow-listed Codex
CLI version with both PowerShell 7 and Windows PowerShell 5.1.

Task start and commit use write-ahead state under `.git`: an interrupted
operation can be resumed only by invoking the same wrapper with the same
arguments, while unrelated task-state-dependent guarded operations fail closed.

## Current code boundary

```text
config/
├─ data.toml
└─ jvlink.toml

src/
├─ main.py
├─ data/
│  ├─ config.py
│  ├─ data_retriever.py
│  ├─ data_preprocesser.py
│  ├─ data_loader.py
│  ├─ race_key.py
│  ├─ retriever/
│  │  ├─ historical.py
│  │  ├─ jvlinktosqlite.py
│  │  ├─ latest.py
│  │  ├─ odds_archive.py
│  │  ├─ realtime.py
│  │  └─ setting.py
│  ├─ preprocesser/
│  │  ├─ __init__.py
│  │  ├─ read_sqlite.py
│  │  └─ snapshot.py
│  └─ loader/
│     ├─ __init__.py
│     └─ read_parquet.py
└─ tests/
   └─ ...
```

The user-facing data dependency direction is intentionally one-way:

```text
JV-Link
  -> JVLinkToSQLite
  -> data/raw/race.db
  -> DataPreprocesser / preprocesser/*
  -> versioned Parquet
  -> DataLoader / loader/read_parquet.py
  -> training / analysis / prediction
```

The raw SQLite database is an acquisition store and is never a model-facing
loader source. Training and realtime inference both consume processed Parquet.
This boundary is recorded in ADR-008.

## Retrieval boundary

`src/main.py` is the user-facing Typer entry point for historical, latest, and
prediction-time realtime retrieval and for standalone preprocessing. XML
transformation and process execution remain below the CLI boundary.

`src/data/data_retriever.py` composes `HistoricalRetriever`, `LatestRetriever`,
and `RealtimeRetriever` around one `JVLinkToSQLiteRunner`, one
`JVLinkSettingBuilder`, and one `OddsArchive`.
`src/data/retriever/jvlinktosqlite.py` owns the local subprocess boundary to
`JVLinkToSQLite.exe`, passes arguments without a shell, and does not own JRA-VAN
credentials or parse JV-Data directly. This external process boundary is
recorded in ADR-005.

`src/data/retriever/setting.py` validates `config/jvlink.toml` and translates
semantic retrieval profiles into JVLinkToSQLite XML. The installed `setting.xml`
is treated as a seed and is not modified by keiba-ai. Normal, setup, and realtime
section enablement plus DataSpec allow-lists are applied explicitly; configured
DataSpecs missing from the seed fail at this boundary.

`historical.py` generates base and per-race odds settings in a temporary
directory. After the base database exists, it snapshots JRA-compatible race keys
from `NL_RA_RACE` and closes that SQLite reader before JVLinkToSQLite begins
realtime odds writes. Non-JRA race records remain in the base database but are
not sent to the JRA-specific historical-odds DataSpecs. The historical-odds
profile then generates an exclusive realtime setting for each eligible race.
Because JVLinkToSQLite recreates realtime O1/O2 staging tables on subsequent
realtime executions, each race's result is archived before the next race is
requested.

`latest.py` uses a persistent runtime XML under the configured Git-ignored data
runtime directory. The first run creates it from the seed. Later runs use the
runtime XML as their source, reapply the latest profile, and allow
JVLinkToSQLite to persist updated latest-read positions into that runtime file.
The seed remains unchanged. This configuration ownership and the Typer entry
point are recorded in ADR-006.

`realtime.py` owns prediction-time retrieval for one explicit `RaceKey`. It first
runs the `realtime_history` profile (`0B41`, `0B42`) and archives the O1/O2
staging rows, then runs `realtime_current` (`0B31`, `0B32`) and archives the
current rows. Both settings are temporary and execute with
`--skipslastmodifiedupdate`; prediction-time retrieval therefore does not share
mutable latest-read state.

`odds_archive.py` treats `RT_O1_ODDS_TANFUKUWAKU` and `RT_O2_ODDS_UMAREN` as
staging tables and copies them into cumulative
`ARCHIVE_O1_ODDS_TANFUKUWAKU` and `ARCHIVE_O2_ODDS_UMAREN` tables. Archive
tables preserve source column names/order and use full-row set deduplication.
This gives historical training and production inference one raw O1/O2 column
contract. The staging/archive boundary is recorded in ADR-007.

## Preprocessing boundary

`src/data/data_preprocesser.py` is the public raw-to-processed orchestration
facade. `src/data/preprocesser/read_sqlite.py` exclusively owns read-only access
to `race.db`; it opens a consistent SQLite snapshot, streams bounded batches,
preserves source column names/order/text/NULLs, writes Parquet, and validates the
resulting schema and row count.

`src/data/preprocesser/snapshot.py` owns publication. Complete historical/latest
processed datasets are immutable directories under:

```text
data/processed/snapshots/<snapshot-id>/
```

A complete snapshot becomes visible only when `data/processed/CURRENT` is
atomically replaced with that snapshot ID. A failed rebuild leaves the previous
pointer unchanged.

Prediction-time realtime data is published separately by exact `RaceKey`:

```text
data/processed/realtime/<race-id>/
├─ CURRENT
└─ versions/
   └─ <version-id>/
      ├─ ARCHIVE_O1_ODDS_TANFUKUWAKU.parquet
      └─ ARCHIVE_O2_ODDS_UMAREN.parquet
```

The realtime publisher filters the cumulative archive tables by year, month/day,
venue, meeting, meeting day, and race number. It writes both O1/O2 files to a
new version and atomically switches the race-local `CURRENT` pointer only after
both files validate. Realtime preprocessing therefore stays race-scoped rather
than rebuilding the complete historical dataset for each prediction refresh.

Historical retrieval automatically calls a complete `rebuild`. Latest retrieval
automatically calls a complete `update` (currently implemented as a complete
snapshot refresh). Realtime retrieval automatically calls `update_race` for the
target race. A standalone `preprocess rebuild` command is also available when
raw data already exists.

ADR-008 supersedes ADR-003 for this preprocessing/publication contract.

## Loader boundary

`src/data/data_loader.py` is the public processed-data facade.
`src/data/loader/read_parquet.py` is the concrete Parquet reader. Loader modules
never open raw SQLite.

The loader can:

- list and read tables from the complete snapshot selected by
  `data/processed/CURRENT`;
- iterate large complete tables in bounded Arrow record batches;
- read race-scoped realtime O1/O2 tables from the race-local `CURRENT` version.

This means model code has one storage contract—Parquet—regardless of whether the
source data arrived through historical, latest, or realtime retrieval.

## Configuration and persisted state

`config/data.toml` owns the raw SQLite path, processed directory, and JVLink
runtime directory. `config/jvlink.toml` owns the local executable/seed paths,
semantic retrieval profiles, and the optional target race for realtime retrieval;
XML tag details remain inside the adapter.

`data/` is Git-ignored. Mutable raw SQLite, JVLink runtime XML, complete Parquet
snapshots, and realtime Parquet versions are local artifacts rather than Git
contents. Git versions the code and declarative retrieval/preprocessing policy,
not the acquired datasets.

ADR-009 selects LightGBM LambdaRank for the ranking MVP and a later top-3
Plackett–Luce custom objective for finishing-order probabilities. The current
MVP implementation lives under `src/models/`: it accepts an explicit ordered
feature schema, trains `LGBMRanker(objective="lambdarank")`, and returns finite
race-local scores and ranks. It does not produce probabilities, expected value,
or purchase recommendations. LightGBM and its scikit-learn runtime dependency
are locked project dependencies.

Model artifacts use the LightGBM native format plus JSON metadata containing the
fixed objective, label gain, feature schema, and hashes. A readiness marker is
published only after the native model and metadata are complete. Model code
does not read raw SQLite or initiate data acquisition; it receives processed
feature rows from its caller. ADR-010 records this model boundary and artifact
contract. Missing feature values, including unavailable
odds history, remain missing and are passed through without final-odds
fallback or imputation. Equal scores are ordered by horse ID, independently of
input row order. Feature construction, temporal availability auditing,
walk-forward orchestration, and model CLI integration remain future work.
JRA-VAN acquisition uses the locally installed JVLinkToSQLite/JV-Link environment
on Windows; no HTTP API key or repository credential is introduced.

## Architectural constraints during bootstrap

- Keep imports free of runtime side effects.
- Keep tests under `src/tests/`.
- Do not introduce speculative plugin systems or service boundaries.
- Keep external I/O, process execution, time, and randomness explicit and
  testable.
- Do not add a runtime dependency before confirming that the standard library
  and current dependencies are insufficient.
- Treat external input as untrusted and never commit secrets.

## Evolving the architecture

For each product requirement:

1. inspect the current code, tests, and Accepted ADRs;
2. identify the smallest coherent architecture needed for that requirement;
3. record a durable or difficult-to-reverse decision in an ADR before relying on
   it broadly;
4. implement and test the requirement without speculative adjacent features;
5. update this document to describe the resulting current system.

An ADR is normally appropriate for decisions that establish or materially
change a public interface, dependency direction, persisted format, configuration
ownership, external-system boundary, security boundary, or long-lived runtime
dependency. Accepted ADRs take precedence over assumptions in this document.
