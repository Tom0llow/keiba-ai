# ADR-008: Separate raw preprocessing from Parquet loading

- Status: Accepted
- Date: 2026-10-04
- Decision Owners: Repository maintainers
- Related Issues/PRs: PR #8
- Supersedes: ADR-003
- Superseded by: N/A

## Context

JRA-VAN acquisition now updates a mutable raw SQLite database through historical,
latest, and prediction-time realtime workflows. The earlier Parquet exporter
combined configuration parsing, raw SQLite reads, Parquet writes, and processed
Parquet reads in one `race_data.py` module and refused to refresh an existing
processed directory. That boundary no longer supports recurring retrieval or
prediction-time updates cleanly.

The application also needs one processed-data read path for both training and
inference. Allowing models to read SQLite during realtime inference while training
reads Parquet would create a second serving path and increase the risk of schema,
filtering, and preprocessing drift.

## Decision

- Keep `data/raw/race.db` as the authoritative mutable acquisition store.
- Raw SQLite reads belong to preprocessing, not loading. They are implemented
  under `src/data/preprocesser/`, currently `read_sqlite.py`.
- `src/data/data_preprocesser.py` is the public preprocessing facade. It owns:
  - complete processed snapshot publication for historical and latest data;
  - race-scoped prediction-time Parquet publication after realtime retrieval.
- `src/data/loader/` contains processed-data readers only. The Parquet reader is
  `src/data/loader/read_parquet.py`; it never opens `race.db`.
- `src/data/data_loader.py` is the public loading facade for training, analysis,
  and inference.
- Complete processed datasets are immutable version directories under
  `data/processed/snapshots/<snapshot-id>/`. `data/processed/CURRENT` is a small
  pointer atomically replaced only after a complete snapshot has been written
  and validated.
- Prediction-time odds are published by `RaceKey` under
  `data/processed/realtime/<race-id>/versions/<version-id>/`. A race-local
  `CURRENT` pointer is atomically replaced only after both archive O1/O2 Parquet
  files are written and validated.
- Realtime preprocessing filters the cumulative raw archive tables to the exact
  race key and writes only that race's O1/O2 processed files. It does not rebuild
  the complete historical snapshot before inference.
- Historical and latest retrieval only update raw SQLite. Complete processed
  snapshots are published by the standalone `preprocess rebuild` CLI.
- Realtime retrieval only archives the target race. The separate
  `preprocess realtime` command publishes its race-scoped Parquet.
- `preprocess historical-weekly` publishes a raw-complete weekly year and records
  its publication state in the weekly ledger.

## Rationale

This creates one dependency direction:

```text
JV-Link -> JVLinkToSQLite -> raw SQLite -> preprocessing -> Parquet -> loader -> model
```

Training and inference therefore consume Parquet through the same loading layer.
Atomic pointer publication prevents failed preprocessing from replacing the last
known-good processed data. Race-scoped realtime output keeps prediction-time I/O
bounded without forcing a full historical Parquet rebuild for every odds refresh.

## Consequences

- Processed data uses version directories and small `CURRENT` pointer files rather
  than one mutable directory of Parquet files.
- Old snapshot/version directories are retained until a separate retention policy
  removes them; this favors rollback and reproducibility over minimum disk usage.
- `latest` retrieval and complete snapshot publication are separate operations.
  Run `preprocess rebuild` after retrieval when the complete snapshot must be
  refreshed. Any later table- or partition-level incremental publication must
  preserve the same public loader contract and atomic publication semantics.
- Realtime inference must call preprocessing successfully before the model reads
  the corresponding race-scoped Parquet version.
- The raw SQLite database remains Git-ignored and mutable. Processed Parquet is
  also Git-ignored; code and configuration, not datasets, are version-controlled
  by Git.

## Alternatives Considered

- Letting inference read SQLite directly was rejected because it would create a
  second data-serving path distinct from training.
- Rewriting every Parquet table for every realtime odds request was rejected as
  unnecessarily expensive.
- Appending blindly by SQLite `rowid` was rejected because upstream rows may be
  updated, so a rowid-only delta can miss changes.
- Keeping SQLite readers under `loader/` was rejected because loaders are the
  consumer-facing processed-data boundary, while SQLite is raw preprocessing
  input.

## Validation / Follow-up

Tests cover complete snapshot publication, rollback to the previous `CURRENT`
pointer when conversion fails, race-key filtering for realtime O1/O2, and loading
processed data after the raw SQLite file is removed. Future preprocessing modules
may be added under `src/data/preprocesser/`; future processed formats/readers may
be added under `src/data/loader/` without changing the raw acquisition boundary.

## Security / Privacy Impact

No new network boundary or credential is introduced. Raw and processed data stay
on the local filesystem and remain outside Git.

## Operational Impact

Retrieval commands do not perform Parquet publication. The corresponding
preprocess command must be run after raw retrieval. A preprocessing failure
leaves the previous published pointer unchanged and causes the command to fail
rather than exposing partial processed data.

## Migration / Rollback

The old `src/data/race_data.py` and `src/convert_race.py` entry point are removed.
Existing legacy `data/processed/*.parquet` files are not treated as a valid new
snapshot because the new loader requires a `CURRENT` pointer. Run
`uv run python src/main.py preprocess rebuild` once to publish the first new-format
snapshot. Rollback of a published dataset can be performed by restoring a
previous valid pointer value while its version directory remains present.

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-10-04 | Accepted | Separate raw preprocessing from Parquet loading and add atomic complete/realtime publication |
