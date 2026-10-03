# ADR-005: Use JVLinkToSQLite as the local JRA-VAN acquisition boundary

- Status: Accepted
- Date: 2026-10-03
- Decision Owners: Repository maintainers
- Related Issues/PRs: N/A
- Supersedes: N/A
- Superseded by: N/A

## Context

The project needs to acquire JRA-VAN race data, including historical odds, into the existing raw SQLite data stage. On the target Windows 11 machine, JVLinkToSQLite is already installed under `C:\JVLinkToSQLite`. The project should not reimplement JV-Link COM communication or store JRA-VAN credentials in repository configuration when a maintained local importer already owns that boundary.

The current repository keeps raw SQLite data separate from derived Parquet output. Introducing race-data acquisition adds a local external-process boundary that must remain explicit and testable without requiring JRA-VAN access in the normal test suite.

## Decision

- Use the locally installed `JVLinkToSQLite.exe` as the acquisition boundary between this repository and JRA-VAN/JV-Link.
- Add a small Python runner under `src/data/retriever/` that invokes JVLinkToSQLite with argv tokens through `subprocess.run`. Do not use a shell or construct a command string.
- Pass the executable path, SQLite destination path, XML setting path, timeout, and `skipslastmodifiedupdate` choice explicitly. Do not read credentials from environment variables or repository files.
- Run JVLinkToSQLite in `Exec` mode for this adapter. Higher-level historical/latest orchestration and configuration ownership remain separate implementation tasks.
- Treat a non-zero exit status, launch failure, or timeout as an explicit Python exception. Validate required filesystem paths before process launch.
- Keep unit tests independent of Windows, JV-Link, JRA-VAN, and user-owned files by mocking only the subprocess boundary.

## Rationale

JVLinkToSQLite already encapsulates JRA-VAN authentication, JV-Link access, record parsing, and SQLite writes. Reusing it avoids duplicating a platform-specific integration inside the modeling repository and keeps the Python boundary small enough to test deterministically. Passing argv directly avoids shell-injection risks and makes path handling explicit.

## Consequences

- Data acquisition requires a Windows host with a functioning JV-Link/JRA-VAN setup and a compatible JVLinkToSQLite executable.
- The repository does not own or persist the JRA-VAN service key.
- Acquisition can fail because of the local executable, JV-Link, JRA-VAN availability, XML settings, or filesystem permissions; callers receive a boundary exception rather than silent partial success.
- The raw SQLite destination may be created or updated by JVLinkToSQLite. The runner itself does not parse or mutate SQLite content.
- Historical and latest-data policies are intentionally not encoded in this runner.

## Alternatives Considered

- Calling JV-Link COM directly from Python would duplicate platform-specific protocol, parsing, and error-handling responsibilities that JVLinkToSQLite already provides.
- Calling a hypothetical HTTP API with an environment-variable API key does not match the selected JRA-VAN Data Lab/JV-Link integration model.
- Embedding acquisition logic into `race_data.py` would mix external data ingestion with the existing SQLite-to-Parquet conversion responsibility.

## Validation / Follow-up

Unit tests verify argv construction, shell-free execution, optional read-position preservation, missing path handling, timeout translation, and non-zero exit translation. Later historical/latest retrievers should depend on this runner rather than invoking subprocesses themselves.

## Security / Privacy Impact

No credentials are committed, logged, or passed by this adapter. Subprocess invocation uses a list of argv tokens with `shell=False`. Executable and setting paths are treated as local filesystem inputs and validated before use.

## Operational Impact

Operators must install and configure JV-Link/JVLinkToSQLite outside the repository. Long-running imports can opt out of a timeout; scheduled or interactive callers may provide a positive timeout appropriate to their workflow.

## Migration / Rollback

There is no existing acquisition implementation to migrate. Rollback consists of removing the runner and its callers; existing raw SQLite and processed Parquet artifacts remain unchanged.

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-10-03 | Accepted | Select local JVLinkToSQLite process as the JRA-VAN acquisition boundary |
