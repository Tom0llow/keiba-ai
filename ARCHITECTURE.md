# Architecture — keiba-ai

## Status

This repository contains development automation, local JRA-VAN race-data
retrieval, and a local race-data Parquet export. It remains uninstalled as a
Python distribution.

An earlier local prototype is not a source of current requirements or design
authority. Product behavior and durable architectural decisions must come from
an explicit requirement or an Accepted architecture decision record (ADR).

## Current runtime and tooling

- Python: 3.12
- Environment and dependency manager: uv
- Retrieval CLI: Typer
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

Guard trust-boundary validation runs separately through
`scripts/guard-tests/guard-regression.ps1` on the supported PowerShell hosts.

## Current code boundary

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
│     ├─ __init__.py
│     ├─ historical.py
│     ├─ jvlinktosqlite.py
│     ├─ latest.py
│     ├─ odds_archive.py
│     ├─ realtime.py
│     └─ setting.py
└─ tests/
   ├─ test_data_retriever.py
   ├─ test_historical.py
   ├─ test_jvlinktosqlite.py
   ├─ test_latest.py
   ├─ test_main.py
   ├─ test_odds_archive.py
   ├─ test_project_environment.py
   ├─ test_race_data.py
   ├─ test_realtime.py
   └─ test_setting.py
```

`src/tests/test_project_environment.py` verifies that the synced project is not
installed as a Python distribution. `src/convert_race.py` invokes the race-data
export; `src/data/race_data.py` owns config parsing, read-only SQLite input,
bounded Parquet writing, and the shared processed-table loader. The module is
importable by scripts under `src/`, but the project has no build system or
installed distribution.

`src/main.py` is the user-facing Typer entry point for historical, latest, and
prediction-time realtime retrieval. It loads repository configuration and
constructs `DataRetriever`; XML transformation and process execution remain
below the CLI boundary.

`src/data/data_retriever.py` composes `HistoricalRetriever`, `LatestRetriever`,
and `RealtimeRetriever` around one `JVLinkToSQLiteRunner`, one
`JVLinkSettingBuilder`, and one `OddsArchive`. `src/data/retriever/jvlinktosqlite.py`
owns the local subprocess boundary to `JVLinkToSQLite.exe`, passes arguments
without a shell, and does not own JRA-VAN credentials or parse JV-Data directly.
This external process boundary is recorded in ADR-005.

`src/data/retriever/setting.py` validates `config/jvlink.toml` and translates
semantic retrieval profiles into JVLinkToSQLite XML. The installed `setting.xml`
is treated as a seed and is not modified by keiba-ai. Normal, setup, and realtime
section enablement plus DataSpec allow-lists are applied explicitly; configured
DataSpecs missing from the seed fail at this boundary.

`historical.py` generates base and per-race odds settings in a temporary
directory. The base profile enables setup-data acquisition from the configured
start point. After the base database exists, exact race-key components are read
from `NL_RA_RACE`; the historical-odds profile then generates an exclusive
realtime setting for each eligible race. These executions use
`--skipslastmodifiedupdate`. Because JVLinkToSQLite recreates realtime O1/O2
staging tables on subsequent realtime executions, each race's result is archived
immediately before the next race is requested.

`latest.py` uses a persistent runtime XML under the configured Git-ignored data
runtime directory. The first run creates it from the seed. Later runs use the
runtime XML as their source, reapply the committed latest profile, and allow
JVLinkToSQLite to persist its updated latest-read positions into that runtime
file. The seed remains unchanged. Profile ownership and the Typer entry point are
recorded in ADR-006.

`realtime.py` owns prediction-time retrieval for one explicit race key. It first
runs the `realtime_history` profile (`0B41`, `0B42`) and archives the O1/O2
staging rows, then runs `realtime_current` (`0B31`, `0B32`) and archives the
current rows. Both settings are temporary and execute with
`--skipslastmodifiedupdate`; prediction-time retrieval therefore does not share
mutable latest-read state.

`odds_archive.py` treats `RT_O1_ODDS_TANFUKUWAKU` and `RT_O2_ODDS_UMAREN` as
staging tables and copies them into cumulative
`ARCHIVE_O1_ODDS_TANFUKUWAKU` and `ARCHIVE_O2_ODDS_UMAREN` tables. Archive
tables preserve source column names/order and use full-row set deduplication.
This gives historical training and production inference one persisted O1/O2
column contract. The staging/archive boundary is recorded in ADR-007.

`config/data.toml` owns the raw SQLite path, processed directory, and JVLink
runtime directory. `config/jvlink.toml` owns the local executable/seed paths and
semantic retrieval profiles; XML tag details remain inside the adapter. The
export stores one Parquet file per user table under `data/processed/`, with
source text and NULL values preserved. It stages files and validates row and
column metadata before publishing; it does not replace existing processed
output. This storage and loader contract is recorded in ADR-003. ADR-004 selects
a market-adjusted win-probability model for the prediction MVP, but no model has
been implemented. JRA-VAN acquisition uses the locally installed
JVLinkToSQLite/JV-Link environment on Windows; no HTTP API key or repository
credential is introduced.

## Architectural constraints during bootstrap

- Keep imports free of runtime side effects.
- Keep tests under `src/tests/`.
- Do not introduce speculative layers, plugin systems, storage formats, or
  service boundaries.
- Keep external I/O and process execution explicit and testable.
- Keep configuration limited to behavior or paths that can legitimately vary;
  XML implementation details stay in the adapter.
- Do not add a runtime dependency before confirming it is required by an
  explicit product or interface decision.
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
change a public entry point, top-level responsibility, persisted format,
configuration ownership, external-system boundary, security boundary, or
runtime dependency. Accepted ADRs take precedence over assumptions in this
document; replacing an Accepted decision requires a new ADR that explicitly
supersedes it.
