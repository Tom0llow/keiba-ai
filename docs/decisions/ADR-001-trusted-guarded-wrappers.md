# ADR-001: Install guarded wrappers outside the writable workspace

- Status: Accepted
- Date: 2026-09-22
- Decision Owners: Repository maintainers
- Related Issues/PRs: N/A
- Supersedes: N/A
- Superseded by: N/A

---

## Context

Codex normally edits the repository inside a network-disabled workspace sandbox.
Git metadata and authenticated GitHub operations require narrowly scoped host
access. An execution-policy rule can match command arguments, but it cannot
verify the contents of a PowerShell script before allowing that script to run
outside the sandbox.

Execution policy also does not bind a relative script argument to a particular
working directory. Allowing `.git/codex-guard/...` by relative token would let
the same argv resolve to a different file from an attacker-controlled current
directory before any self-check runs.

Allowing a tracked `scripts/agent/*.ps1` file directly would therefore make a
writable task file a host-execution trust anchor. Git hooks create the same
problem: a guarded host-side `git commit` or `git push` could execute a hook that
loads branch-controlled configuration or code.

## Decision

Tracked wrappers under `scripts/agent/` are reviewable source only. A maintainer
installs their reviewed `origin/main` blobs inside the protected Codex user home
with
`scripts/setup/install-guarded-wrappers.ps1`. `.git/codex-guard/` contains only
repository invocation metadata. The installer writes a
repository-and-checkout-keyed Codex user-layer rule containing the exact
absolute PowerShell executable and installed script paths. It also writes
`guard-invocation.json` for sandboxed discovery. Codex passes those literal
absolute values as argv tokens; relative guard paths are forbidden. Direct
top-level use of the recorded GitHub CLI and Codex CLI executables is forbidden,
and raw Git/GitHub operations cannot substitute for a guarded wrapper.
Workspace copies and installation/admin scripts are not host executable by
Codex.

Each installer run creates a new immutable guard directory whose identity
combines a repository policy ID, the protected `origin/main` source SHA, and a
new installation ID. Publishing fails if that destination already exists. An
installation never modifies an earlier immutable guard directory.

The installation contains a manifest binding each source blob to the SHA-256 of
its installed file. It also binds the installation to canonical absolute paths
for the protected PowerShell host, Git, GitHub CLI, and Codex CLI, plus the Codex
CLI version accepted by `scripts/guard-tests/codex-cli-version.txt`. Every
guarded entry point verifies the complete installed set, executable paths, and
Codex CLI version before continuing. A path or version change requires
reinstallation. The Codex executable must be the self-contained native
`codex.exe`; Node launcher shims such as `codex.cmd` and `codex.ps1` are not
supported. The installer accepts `-CodexExecutablePath` when normal discovery
does not resolve the native file. Preflight also verifies that installed source
blob IDs still match current `origin/main` and requires reinstallation after a
guarded source change.
The Codex home, user-rule directory, guard store, and installed guard are
rejected when they fall under either the writable repository or the system
temporary directory. Security-critical subprocess output is captured under the
protected `.git` directory rather than the sandbox-writable temporary area.

All Git invocations made by guarded wrappers override `core.hooksPath` with an
installed empty directory and disable external fsmonitor. Repository validation
runs separately inside the ordinary sandbox and in CI. Autonomous commits are
rejected if they change workflow trust-boundary paths, including agent/Codex
rules, workflows, guarded sources, guard regression tests, setup scripts, or
Git attribute files.
The guard enumerates ignored untracked trust-boundary pathspecs separately, so
repository, info, or global excludes cannot conceal nested agent instructions,
skills, policies, workflows, or guarded sources from clean-tree and commit
validation.

Guarded GitHub operations clear ambient repository/host selectors, derive the
GitHub repository from `origin`, and pass that repository explicitly to every
PR and workflow command. Task state records the repository and owner; PR checks
also require the same head repository, owner, branch, number, and SHA.
The single resolved push URL must name that same repository and is passed
literally to every push or remote deletion. State-changing wrappers use an
exclusive `.git` lock, and the installer uses that same lock while activating
new metadata and policy state. CI waiting, PR/CI inspection, readiness, and
merge are bound to one explicit expected HEAD SHA; they re-read PR, local, and
remote HEAD after check collection. PR inspection observes the current PR base
object ID but produces its complete local binary diff from the recorded task
start SHA through the expected head with external diff and text conversion
disabled. Check evidence comes from the check-runs and commit-status APIs for
the expected head. Every observation result includes the observed base and head
SHAs; PR inspection also includes the diff base. Merge readiness is bound to
the PR number and HEAD SHA; binding a task to a replacement PR clears readiness
and merge-attempt evidence. Both merge readiness and the final path
immediately before merging an unmerged PR revalidate that branch protection has
the required contexts, strict status checks, and the configured GitHub Actions
application ID. Trust paths must use canonical physical Windows paths; aliases
and reparse-point traversal fail closed.

Task start and commit are write-ahead state transitions. The wrappers record
their pending identity before the corresponding Git mutation and permit recovery
only by rerunning the same wrapper with the same arguments. Other
task-state-dependent guarded operations fail closed until the pending transition
is verified and cleared.

If the remote merge succeeds before a later communication or cleanup failure,
the preserved task state permits a retry only for the same PR and approved SHA.
The wrapper records the PR, SHA, method, and time immediately before requesting
the squash merge. Recovery requires that matching attempt record, current
branch-protection verification, GitHub `MERGED` state with a recorded merge
timestamp, and agreement among the PR HEAD, task HEAD, merge-ready SHA,
attempted SHA, and approved SHA. Incomplete cleanup retains task state and fails
so the same guarded command can resume. Approval cannot be transferred to a
replacement SHA.

## Rationale

The installed directory and its execution policy are in the Codex user layer,
outside the writable repository. The repository's `.git` directory holds only
discovery metadata and task state. This removes tracked task files and local
Git hooks from the host-execution chain while preserving a two-interaction
workflow: requirement input and exact-PR/exact-HEAD merge approval.

Argument-only allow rules, self-checks performed by a mutable workspace script,
and `--no-verify` were rejected because they do not prevent code from running
before verification or do not disable every Git hook.

## Consequences

### Positive

- Branch-controlled scripts, hooks, and CI definitions cannot silently widen
  autonomous host execution.
- GitHub inspection is bound to the recorded repository task and PR.
- CI, review, readiness, and merge evidence cannot be reused for another HEAD.
- Guard source changes become an explicit manual security-bootstrap event.

### Negative

- Each standard clone requires a one-time manual guard installation after the
  bootstrap reaches protected `main`, followed by a Codex restart.
- Guard source changes require reinstallation before another autonomous task.
- Old immutable guard directories remain until a maintainer removes them.
- The current installer supports a standard checkout with a `.git` directory,
  not linked worktrees where `.git` is a file.
- The checkout and user-layer trust paths must not traverse symbolic links,
  junctions, or other reparse points.
- Trust paths cannot reside under the writable repository or system temporary
  directory.
- The installer must run under the system PowerShell executable beneath the
  protected Windows or Program Files directory; portable/user-writable copies
  are not supported.
- A Node launcher shim cannot serve as the trusted Codex executable; installation
  requires the package's native `codex.exe`.

## Validation

- Parse all PowerShell sources before installation.
- Run `scripts/guard-tests/guard-regression.ps1` in local validation with a
  Codex CLI version explicitly listed in
  `scripts/guard-tests/codex-cli-version.txt`; missing, shimmed, or unlisted
  versions fail validation. The `Quality` CI job runs the real regression for
  every listed version on both PowerShell 7 and Windows PowerShell 5.1.
- Extract only committed `origin/main` blobs and verify their Git blob IDs.
- Verify every installed SHA-256 against the manifest on each entry point.
- Verify installed source blob IDs against current `origin/main` during
  preflight.
- Exercise real Codex CLI execution-policy decisions: only
  repository-and-checkout-bound absolute installed wrappers are allowed,
  relative and workspace wrappers are forbidden, direct recorded GitHub CLI and
  Codex CLI access is forbidden, and raw mutations are forbidden.

## Migration / Rollback

Install or refresh the guard from a clean local `main` that exactly matches
`origin/main`. The installer publishes a fresh immutable directory, retains any
previous immutable directories unchanged, and keeps only the prior
`.git/codex-guard/` metadata at a timestamped `.git/codex-guard.backup-*` path.
It activates the new user-layer policy and repository metadata only after the
new directory has passed validation. If either activation fails, it restores
the prior policy and metadata and removes the newly published directory. If the
old policy cannot be restored, its rollback copy is retained at the reported
path for manual recovery.
Restart Codex after a successful installation. A maintainer may remove obsolete
immutable directories only after confirming that neither active metadata nor
policy refers to them.

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `AGENTS.md`
- [x] `README.md`
- [x] `docs/AUTONOMOUS_DEVELOPMENT.md`
- [x] `docs/rules/git-workflow.md`

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-09-22 | Accepted | Adopted for the AI-driven-development bootstrap |
| 2026-09-23 | Accepted | Bound execution to protected user-layer absolute paths, repository identity, and checkout identity |
| 2026-09-24 | Accepted | Added immutable per-run installations, executable/version binding, SHA-bound observation, protection rechecks, and exact-SHA merge recovery |
| 2026-09-25 | Accepted | Required native Codex execution, cross-host/version guard validation, complete SHA-bound local diffs and check-API observations, PR-bound readiness, and recoverable write-ahead task transitions |
