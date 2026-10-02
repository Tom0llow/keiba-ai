# ADR-003: Export race database tables as Parquet

- Status: Accepted
- Date: 2026-10-01
- Decision Owners: Repository maintainers
- Related Issues/PRs: N/A
- Supersedes: N/A
- Superseded by: N/A

## Context

The user requires every table in `data/raw/race.db` to be available as Parquet
under `data/processed/`, with configured paths and a shared loader. The source
is an approximately 18.8 GB SQLite database with 35 tables and 6,387 declared
columns. The existing repository has no product code, configuration, or data
pipeline. Its data assessment found that field definitions and quality rules
are not yet approved. Several date-like values are placeholders, so parsing or
cleaning them during export could change their meaning.

## Decision

- Keep the SQLite source unchanged. Export every user table to one file named
  `<table>.parquet` inside the configured processed directory. Preserve column
  names, order, rows, NULL values, whitespace, and date-like text. Do not
  filter, deduplicate, join, aggregate, or parse values.
- Store the source database path and processed directory in `config/data.toml`.
  Resolve relative paths against that configuration file. Product code under
  `src/data/` owns configuration parsing, export, and the common Parquet
  loader. The CLI script at `src/convert_race.py` invokes the export. The
  project remains uninstalled as a Python distribution under ADR-002.
- Use PyArrow as the runtime Parquet reader and writer. Represent the source's
  declared TEXT and DATETIME columns as Arrow strings, leaving NULL as NULL.
  Fail if a row contains a different SQLite value type; do not silently cast
  it. This rule reflects the observed source values, not an approved domain
  type definition.
- Read SQLite through a read-only connection and stream bounded batches. Build
  all files in a temporary sibling directory, validate output metadata, then
  publish the directory. Refuse to replace an existing processed directory.
  The common loader reads tables by name and supports batch iteration.

## Rationale

Parquet is the requested processed format. Streaming keeps memory bounded for
the large source. String preservation avoids assigning domain meaning to
undocumented values. Configuration keeps machine-specific paths out of code.
Publishing the completed directory together prevents a failed run from leaving
an apparently complete processed dataset. The current requirement does not
need a distributable package or a broader data platform.

## Consequences

- The processed dataset is a format-preserving copy, not cleaned data. Consumers
  must apply approved type and quality rules separately.
- Parquet files require additional disk space and PyArrow at runtime. A full
  export requires a complete SQLite scan and can take substantial time.
- An existing processed directory is never overwritten by the export. To
  refresh it, an owner must decide how to archive or replace that directory.
- The common loader's full-table read can use substantial memory; batch
  iteration is available for large tables.
- `data/` is Git-ignored, so the Parquet files are local artifacts rather than
  repository contents.

## Alternatives Considered

- Loading whole tables into pandas before writing Parquet would require another
  dependency and risk exhausting memory.
- Writing files directly to `data/processed/` would expose a partial dataset
  if conversion fails.
- Parsing date-like and numeric text would introduce unapproved data rules and
  could alter blanks or placeholder values.

## Validation / Follow-up

Tests use a temporary SQLite database to compare names, order, values, NULLs,
row counts, empty tables, loader behavior, and failure handling. The full export
compares each Parquet file's metadata with the rows and columns read from the
SQLite snapshot. The source database remains unchanged. Domain types,
relationships, and quality thresholds require a separate approved decision.

## Security / Privacy Impact

The exporter accesses the raw database read-only and does not log row values.
The configured destination must be access-controlled according to the source
data's as-yet-unconfirmed sensitivity. No network service or credential is
introduced by this decision.

## Operational Impact

The export needs enough free disk space for the completed Parquet dataset and
its temporary build. Failure removes the temporary build; no published output
is replaced. An interrupted process may leave a temporary directory that an
operator should inspect before removing.

## Migration / Rollback

There is no existing processed dataset to migrate. Rollback consists of
removing the newly generated processed directory after confirming its path and
that no consumer uses it; the raw SQLite source is unaffected.

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-10-01 | Accepted | Introduce a format-preserving Parquet export for the requested race data |
