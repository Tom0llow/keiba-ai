# ADR-006: Configure JVLink retrieval profiles and expose a Typer CLI

- Status: Accepted
- Date: 2026-10-04

## Context

JVLinkToSQLite stores both execution configuration and mutable latest-read state
in XML. Its local `setting.xml` is also user-owned and may be changed through the
JVLinkToSQLite application. Requiring users to maintain separate historical,
historical-odds, and latest XML files would duplicate that structure and make
keiba-ai depend on manual XML edits.

The retrieval modes need different behavior:

- historical base retrieval uses setup data and must not advance the user's seed
  setting;
- historical time-series odds use only the selected realtime DataSpecs and a
  race-specific `JVRaceKey`;
- latest retrieval must retain the read positions written back by
  JVLinkToSQLite after a successful run.

The repository also needs a stable user-facing command for selecting retrieval
mode without requiring callers to construct `DataRetriever` in ad-hoc Python.

## Decision

Treat the installed JVLinkToSQLite `setting.xml` as a read-only seed from the
perspective of keiba-ai.

Declare retrieval policy in `config/jvlink.toml`. The configuration contains:

- the local JVLinkToSQLite executable path;
- the seed-setting path;
- semantic profiles for historical, historical odds, and latest retrieval;
- explicit DataSpec allow-lists and mode-specific dates where applicable.

`JVLinkSettingBuilder` owns the translation from those semantic profiles to the
JVLinkToSQLite XML structure. For each normal, setup, and realtime section it
sets the section enabled state and treats the configured DataSpec list as an
exclusive allow-list. This prevents DataSpecs enabled in the seed from leaking
into another retrieval mode.

Historical base and historical-odds XML files are generated under a temporary
directory and executed with `--skipslastmodifiedupdate`. They are discarded when
the historical workflow finishes and the seed is never mutated.

Latest retrieval owns a persistent runtime setting under the Git-ignored data
runtime directory. On the first run it is generated from the seed. Later runs
use the runtime XML as their source, reapply the latest profile, and let
JVLinkToSQLite persist updated read positions back into that runtime file.

`config/data.toml` owns the raw database and runtime directory paths.

Expose retrieval through a Typer CLI at `src/main.py`:

```text
uv run python src/main.py retrieve historical
uv run python src/main.py retrieve latest
```

`DataRetriever` remains the application-level orchestration API underneath the
CLI. Typer is an explicit runtime dependency and is locked in `uv.lock`.

## Consequences

- Users configure retrieval policy as TOML instead of editing generated XML.
- The installed JVLinkToSQLite seed remains compatible with its own GUI and is
  not used as keiba-ai mutable state.
- Historical executions are reproducible from the seed plus committed profile.
- Latest retrieval retains incremental state without committing machine-local
  runtime files.
- Adding or removing a DataSpec is an explicit configuration change and missing
  DataSpecs fail at the setting-generation boundary.
- Changes to JVLinkToSQLite's XML schema can require changes in
  `JVLinkSettingBuilder`.
- The CLI introduces Typer and its transitive dependencies to the locked runtime
  environment.

## Alternatives considered

### Maintain three user-owned XML files

Rejected because it duplicates JVLinkToSQLite configuration, requires manual
synchronization, and mixes policy with generated/mutable state.

### Rewrite the installed `setting.xml` in place

Rejected because historical execution could overwrite the user's configuration
and latest-read state. It also makes failures or interrupted runs more likely to
leave the local JVLinkToSQLite installation in an unexpected state.

### Keep only the Python API

Rejected because routine retrieval should have one documented, repeatable CLI
entry point rather than requiring inline Python construction.
