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
the supported boundary. This boundary also uses a protected system
PowerShell host and an exclusive repository workflow lock as defined by
ADR-001.

PR and CI observations are bound to one explicit expected HEAD SHA through
merge readiness and human approval. PR inspection observes the current PR base
object ID as `baseSha`, then creates the complete local binary diff from the
recorded task `startSha` (`diffBaseSha`) through the expected head with external
diff and text conversion disabled. Checks use the check-runs and commit-status
APIs for that expected head. Every observation reports `baseSha` and `headSha`;
PR inspection also reports `diffBaseSha`. Merge readiness is bound to the PR
number
and HEAD SHA; rebinding the task to a replacement PR clears prior readiness and
merge-attempt evidence. Merge readiness and the final unmerged-PR
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
src/
├─ convert_race.py
├─ data/
│  ├─ data_retriever.py
│  ├─ race_data.py
│  └─ retriever/
│     ├─ __init__.py
│     ├─ historical.py
│     ├─ jvlinktosqlite.py
│     └─ latest.py
└─ tests/
   ├─ test_data_retriever.py
   ├─ test_historical.py
   ├─ test_jvlinktosqlite.py
   ├─ test_latest.py
   ├─ test_project_environment.py
   └─ test_race_data.py
```

`src/tests/test_project_environment.py` verifies that the synced project is not
installed as a Python distribution. `src/convert_race.py` invokes the race-data
export; `src/data/race_data.py` owns config parsing, read-only SQLite input,
bounded Parquet writing, and the shared processed-table loader. The module is
importable by scripts under `src/`, but the project has no build system or
installed distribution.

`src/data/data_retriever.py` is the public orchestration boundary for race-data
acquisition. It composes `HistoricalRetriever` and `LatestRetriever` around one
`JVLinkToSQLiteRunner`. `src/data/retriever/jvlinktosqlite.py` owns the local
subprocess boundary to `JVLinkToSQLite.exe`; it does not own JRA-VAN credentials
or parse JV-Data directly. `historical.py` performs the base historical import,
reads exact race-key components from `NL_RA_RACE`, and executes time-series odds
retrieval for data specs `0B41` and `0B42` from 2003-10-04 onward using temporary
per-race XML settings. `latest.py` runs the configured incremental update and
allows JVLinkToSQLite to persist its own latest-read position. This external
process boundary is recorded in ADR-005.

`config/data.toml` owns the raw SQLite path and processed directory. The export
stores one Parquet file per user table under `data/processed/`, with source text
and NULL values preserved. It stages files and validates row and column metadata
before publishing; it does not replace existing processed output. This storage
and loader contract is recorded in ADR-003. ADR-004 selects a market-adjusted
win-probability model for the prediction MVP, but no model has been implemented.
The repository now has one external acquisition integration: a locally installed
JVLinkToSQLite/JV-Link environment on Windows. No HTTP API key or repository
credential is introduced for JRA-VAN acquisition.

## Architectural constraints during bootstrap

- Keep imports free of runtime side effects.
- Keep tests under `src/tests/`. Select the placement and packaging of future
  product code from an explicit requirement or Accepted ADR.
- Do not introduce speculative layers, plugin systems, storage formats, or
  service boundaries.
- Keep external I/O, process execution, time, and randomness explicit and
  testable when those capabilities are introduced.
- Do not add a runtime dependency before confirming that the standard library
  and current dependencies are insufficient.
- Treat external input as untrusted and never commit secrets.

These constraints guide implementation quality; they do not decide the product's
features or shape in advance.

## Evolving the architecture

For each product requirement:

1. inspect the current code, tests, and Accepted ADRs;
2. identify the smallest coherent architecture needed for that requirement;
3. record a durable or difficult-to-reverse decision in an ADR before relying on
   it broadly;
4. implement and test the requirement without speculative adjacent features;
5. update this document to describe the resulting current system.

An ADR is normally appropriate for decisions that establish or materially
change:

- a public entry point or interface contract;
- top-level module responsibilities or dependency direction;
- persisted data, artifact, or compatibility formats;
- configuration ownership and precedence;
- a database, network service, scheduler, or other external-system boundary;
- a security or trust boundary;
- a runtime dependency with long-term architectural impact.

Accepted ADRs take precedence over assumptions in this document. Replacing an
Accepted decision requires a new ADR that explicitly supersedes it.
