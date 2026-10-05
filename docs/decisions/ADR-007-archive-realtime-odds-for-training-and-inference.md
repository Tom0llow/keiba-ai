# ADR-007: Archive realtime odds for training and inference

- Status: Accepted
- Date: 2026-10-04

## Context

Prediction-time inference needs odds for one target race immediately before the
model runs. The same O1/O2 record families are also used to build historical
training features through JVLink DataSpecs `0B41` and `0B42`.

JVLinkToSQLite treats realtime O1/O2 tables as transient staging tables. Its
realtime data bridges create `RT_O1_ODDS_TANFUKUWAKU` and
`RT_O2_ODDS_UMAREN`, and recreate those tables for subsequent realtime
executions. Therefore those `RT_*` tables cannot themselves be the cumulative
odds history for either historical backfill or production inference.

Prediction also needs two related views of the market:

- `0B41` / `0B42`: time-series O1/O2 odds from sale start through the current
  retrieval point;
- `0B31` / `0B32`: the current O1/O2 realtime snapshot for the target race.

Both sets require a race-specific `JVRaceKey`.

## Decision

Treat JVLinkToSQLite `RT_*` O1/O2 tables as staging only.

After every historical or prediction-time O1/O2 execution, copy the staging
rows into cumulative tables in the same raw SQLite database:

- `ARCHIVE_O1_ODDS_TANFUKUWAKU`
- `ARCHIVE_O2_ODDS_UMAREN`

The archive tables are created from the staging tables with the same column
names and order. Rows are copied with full-row set deduplication so repeating an
identical retrieval is idempotent while distinct `HappyoTime` observations are
retained.

Historical retrieval archives `0B41` / `0B42` immediately after every race,
before the next race execution can recreate the staging tables.

Prediction-time retrieval is implemented by `RealtimeRetriever`. For one
validated race key it:

1. executes the `[realtime_history]` profile (`0B41`, `0B42`);
2. archives the resulting O1/O2 staging rows;
3. executes the `[realtime_current]` profile (`0B31`, `0B32`);
4. archives the resulting current O1/O2 rows.

Both executions use temporary XML and `--skipslastmodifiedupdate`; no mutable
read position is required for a race-keyed prediction request.

The target race may be declared in the `[realtime]` section of
`config/jvlink.toml`. Supplying all race-key options on the CLI overrides that
configured target for one invocation.

Expose this path through the Typer CLI:

```text
uv run python src/main.py --retrieve --mode=realtime
```

All race-key components other than the date are required to be two-digit
strings. The archive is part of the raw local dataset under `data/` and is not
committed to Git.

## Consequences

- Historical and production O1/O2 rows share one persisted column contract.
- Realtime staging-table replacement cannot erase previously collected odds.
- Repeating the same realtime retrieval does not duplicate identical rows.
- Distinct time-series observations remain distinguishable through their source
  columns, including `HappyoTime`.
- Feature generation can read the cumulative archive instead of depending on the
  ephemeral JVLinkToSQLite `RT_*` tables.
- Schema changes in a future JVLinkToSQLite/JV-Data version must be detected and
  handled before appending incompatible rows to an existing archive table.

## Alternatives considered

### Read `RT_*` tables directly during inference only

Rejected because it does not preserve prediction-time observations and does not
solve historical backfill, where every next race execution can replace the
previous staging rows.

### Put `0B31` / `0B32` / `0B41` / `0B42` into `latest`

Rejected because `latest` owns incremental machine state, while these DataSpecs
are explicitly race-keyed prediction requests. Mixing them would blur lifecycle
and failure semantics and would not solve transient staging-table replacement.

### Store history and current snapshots in separate schemas

Rejected for the current scope because JVLinkToSQLite maps realtime O1/O2 to the
same conditional record schema. Keeping one archive contract minimizes
training-serving skew while retaining the original record fields.
