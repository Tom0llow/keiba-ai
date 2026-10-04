# ADR-003: Export race database tables as Parquet

- Status: Superseded
- Date: 2026-10-01
- Decision Owners: Repository maintainers
- Related Issues/PRs: N/A
- Supersedes: N/A
- Superseded by: ADR-008

## Context

The user requires every table in `data/raw/race.db` to be available as Parquet
under `data/processed/`, with configured paths and a shared loader. The source
is an approximately 18.8 GB SQLite database with 35 tables and 6,387 declared
columns. The existing repository has no product code, configuration, or data
pipeline. Its data assessment found that field definitions and quality rules
are not yet approved. Several date-like values are placeholders, so parsing or
cleaning them during export could change their meaning.

## Decision

This decision originally selected a format-preserving one-file-per-table Parquet
export and a shared loader. It also required the exporter to refuse replacement
of an existing processed directory.

ADR-008 supersedes the publication and module boundaries defined here. The
format-preservation principles remain relevant, but recurring historical,
latest, and realtime retrieval now publish versioned processed data through the
preprocessing layer and loaders read Parquet only.

## Rationale

Parquet is the requested processed format. Streaming keeps memory bounded for
the large source. String preservation avoids assigning domain meaning to
undocumented values. Configuration keeps machine-specific paths out of code.

## Consequences

See ADR-008 for the active preprocessing, snapshot, realtime publication, and
loading contracts.

## Alternatives Considered

- Loading whole tables into pandas before writing Parquet would require another
  dependency and risk exhausting memory.
- Writing files directly to `data/processed/` would expose a partial dataset if
  conversion fails.
- Parsing date-like and numeric text would introduce unapproved data rules and
  could alter blanks or placeholder values.

## Validation / Follow-up

Active validation requirements are defined by ADR-008.

## Security / Privacy Impact

No network service or credential was introduced by this decision.

## Operational Impact

Superseded by ADR-008.

## Migration / Rollback

Superseded by ADR-008.

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-10-01 | Accepted | Introduce a format-preserving Parquet export for the requested race data |
| 2026-10-04 | Superseded | Replaced by ADR-008 for recurring and realtime preprocessing |
