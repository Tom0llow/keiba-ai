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

The locked environment is defined by `pyproject.toml` and `uv.lock`. The project
has no build system, so `uv sync` installs dependencies without installing this
repository as a Python distribution.

Host-side autonomous Git/GitHub operations run only from hash-verified wrapper
copies installed in the protected Codex user guard store. Repository files under
`scripts/` are reviewable sources rather than host-side trust anchors. PR and CI
observations are bound to the expected HEAD SHA, and merge readiness plus final
merge require the exact reviewed PR and SHA as defined by ADR-001 and the
guarded workflow documentation.

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
│     └─ setting.py
└─ tests/
   ├─ test_data_retriever.py
   ├─ test_historical.py
   ├─ test_jvlinktosqlite.py
   ├─ test_latest.py
   ├─ test_main.py
   ├─ test_project_environment.py
   ├─ test_race_data.py
   └─ test_setting.py
```

`src/main.py` is the user-facing Typer entry point for retrieval. It loads
repository configuration and constructs `DataRetriever`; it does not own XML
transformation or process execution.

`src/data/data_retriever.py` is the application-level orchestration boundary for
race-data acquisition. It composes `HistoricalRetriever` and `LatestRetriever`
around one `JVLinkToSQLiteRunner` and one `JVLinkSettingBuilder`.

`src/data/retriever/jvlinktosqlite.py` owns the local subprocess boundary to
`JVLinkToSQLite.exe`. It passes arguments without a shell, translates process
failures, and does not own JRA-VAN credentials or parse JV-Data directly. This
external-process boundary is recorded in ADR-005.

`src/data/retriever/setting.py` owns validation of `config/jvlink.toml` and the
translation of semantic retrieval profiles into JVLinkToSQLite XML. The local
installed `setting.xml` is treated as a seed and is not modified by keiba-ai.
Normal, setup, and realtime section enablement and DataSpec allow-lists are
applied explicitly; configured DataSpecs missing from the seed fail at this
boundary.

`historical.py` generates base and per-race odds settings in a temporary
directory. The base profile enables setup-data acquisition from the configured
start point. After the base database exists, exact race-key components are read
from `NL_RA_RACE`; the historical-odds profile then generates an exclusive
realtime setting for each eligible race. These executions use
`--skipslastmodifiedupdate`, and all generated historical XML is discarded when
the command finishes.

`latest.py` uses a persistent runtime XML under the configured Git-ignored data
runtime directory. The first run creates it from the seed. Later runs use the
runtime XML as their source, reapply the committed latest profile, and allow
JVLinkToSQLite to persist its updated latest-read positions into that runtime
file. The seed remains unchanged. Profile ownership and the Typer entry point are
recorded in ADR-006.

`config/data.toml` owns storage locations: the raw SQLite database, processed
Parquet directory, and JVLink runtime directory. `config/jvlink.toml` owns the
machine-local executable/seed paths and semantic retrieval profiles. XML tag or
XPath details are intentionally not exposed as configuration; those belong to
the setting adapter.

`src/data/race_data.py` owns read-only SQLite input, bounded Parquet writing, and
the shared processed-table loader. The export stores one Parquet file per SQLite
user table under `data/processed/`, preserving source text and NULL values. It
stages and validates files before publishing and does not replace existing
processed output. This storage and loader contract is recorded in ADR-003.

ADR-004 selects a market-adjusted win-probability model for the prediction MVP,
but no prediction model has been implemented. JRA-VAN acquisition uses the
locally installed JVLinkToSQLite/JV-Link environment on Windows; no HTTP API key
or repository credential is introduced.

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
