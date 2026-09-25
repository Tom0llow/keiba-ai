# Autonomous Development Workflow

## Goal

After activation, a normal successful task requires human interaction at two
points:

```text
1. Human: provide the requirement
2. Human: approve or reject the exact MERGE_READY PR number and HEAD
```

The guarded workflow performs bounded implementation, review, validation, Git,
Pull Request, and CI work between those points.

## One-time bootstrap and activation

The first installation of this workflow is necessarily a one-time human/manual
bootstrap. The branch wrappers, CI baseline, and repository protection cannot be
treated as prerequisites before they have been installed and verified.

During that initial bootstrap, work may use an explicitly authorized human or
local-only process. It must not claim to have completed the guarded lifecycle,
produced `MERGE_READY`, or satisfied protections that are not active yet.

The guarded autonomous workflow becomes the default only after all of these
conditions are met:

1. the bootstrap files are present on `main`;
2. the `Quality` and `Test` checks exist and pass on `main`;
3. the configured protection for `main` has been verified;
4. the reviewed guard has been installed in the protected Codex user guard
   store and its invocation metadata written under `.git/codex-guard/`;
5. the installer's repository-and-checkout-bound absolute-path rule is active
   in the Codex user layer after a Codex restart; and
6. the installed guarded preflight succeeds against the repository.

This is a one-time activation boundary, not a reusable exception. After
activation, every non-trivial Codex implementation or bug fix uses the
`autonomous-task` workflow unless the user explicitly requests local-only work
or read-only analysis. Local-only authorization does not authorize a commit,
push, PR, or merge.

## Security model

Ordinary `workspace-write` sandbox commands have shell network access disabled.
Autonomous Git/GitHub operations that need host credentials or Git metadata run
outside the sandbox only through hash-verified wrapper copies installed in the
protected Codex user guard store. `.git/codex-guard/` contains only the
repository's invocation metadata.

Codex execution policy compares command argument tokens, not their working
directory. It therefore never auto-allows a relative `.git/codex-guard/...`
path. The human-run installer writes a repository-and-checkout-bound user-layer
rule containing the exact absolute PowerShell executable and installed script
paths, plus
`.git/codex-guard/guard-invocation.json` for sandboxed discovery. Autonomous
calls read that JSON separately and then pass those literal absolute values as
argv tokens; they do not use shell variables, `-Command`, or relative paths.
The installed manifest and every runtime entry point also bind and verify the
canonical absolute PowerShell, Git, GitHub CLI, and Codex CLI executables and
the installed Codex CLI version. The accepted Codex CLI versions are maintained
in `scripts/guard-tests/codex-cli-version.txt`. The trusted Codex executable is
the self-contained native `codex.exe`; Node launcher shims such as `codex.cmd`
and `codex.ps1` are unsupported. Changing an executable path or version requires
reinstallation. The generated policy forbids top-level use of the recorded
GitHub CLI and Codex CLI executables. Raw Git or GitHub commands are not a
substitute for a guarded wrapper.
The Codex home, user-rule directory, guard store, and installed guard must be
outside both the writable repository and the system temporary directory.
Security-critical command output is captured under the protected `.git`
directory rather than a sandbox-writable temporary location.

Tracked files under `scripts/agent/` are reviewable installation sources. They
are writable during a task and therefore are never host-executable trust
anchors. Direct `gh` inspection requires approval because its repository flags
can escape the current task; trusted `inspect-pr.ps1` and `inspect-ci.ps1` bind
inspection to the recorded repository PR and HEAD. Guarded GitHub calls ignore
ambient `GH_REPO` / `GH_HOST`, derive the repository from `origin`, and reject a
PR whose head repository, owner, branch, number, or SHA differs from task state.
The fetch URL and the single resolved push URL must identify the same GitHub
repository; every push and remote deletion uses the validated literal push URL.
CI waiting and merge-readiness gates re-read PR, local, and remote HEAD after
collecting checks and reject any HEAD change during that observation window.
Every `wait-ci.ps1`, `inspect-pr.ps1`, `inspect-ci.ps1`, and
`merge-ready.ps1` call receives the same explicit `ExpectedHeadSha` selected
after the guarded push. A later SHA starts a new CI and review cycle; it cannot
inherit earlier evidence. PR inspection records the current PR base object ID
as `baseSha` and the task's recorded `startSha` as `diffBaseSha`. Its complete
diff is produced locally with `--no-ext-diff`, `--no-textconv`, `--binary`, and
`--full-index` from `diffBaseSha...ExpectedHeadSha`; it does not execute external
diff or text-conversion drivers. Check inspection calls the check-runs and
commit-status APIs for `ExpectedHeadSha`. Every observation result carries
`baseSha` and `headSha`, and PR inspection also carries `diffBaseSha`, so callers
can reject mismatched evidence.

Guarded Git commands override `core.hooksPath` with an installed empty directory
and disable external fsmonitor. Local pre-commit/pre-push hooks are conveniences
for human Git only. Ruff, mypy, and pytest run in the ordinary sandbox before a
guarded commit and again in CI.

Autonomous commits cannot change the workflow trust boundary: `.agents/`,
`.codex/`, `.github/`, `scripts/agent/`, `scripts/guard-tests/`,
`scripts/github/`, `scripts/setup/`,
the protected workflow documents, every `AGENTS.md` or `AGENTS.override.md` at
any depth, or Git attribute/module control files. Such work requires an
explicitly authorized manual security bootstrap.
Protected untracked paths remain forbidden when `.gitignore`, `.git/info/exclude`,
or a global Git exclude hides them. In particular, ignored `.agents/` content
and nested `AGENTS.md` / `AGENTS.override.md` files make guarded clean-tree and
commit checks fail closed.

Do not solve connectivity by broadly opening the workspace sandbox or exposing
TOKEN/SECRET environment variables.

If a guarded GitHub wrapper reports:

```text
proxyconnect tcp: dial tcp 127.0.0.1:9
```

the wrapper may not have matched the active execution policy and may have fallen
back into the offline sandbox. Read `.git/codex-guard/guard-invocation.json`
without executing it and confirm that its `policyPath` exists. If the generated
user-layer policy is missing or stale, reinstall the guard manually from clean
protected `main`. Restart Codex after a reinstall or after changing reviewed
project configuration/rules, then retry through the recorded absolute guarded
path. Do not treat this message alone as proof that GitHub credentials are
invalid.

## Runtime lifecycle

```text
requirement
  ↓
host-side GitHub/repository/baseline-CI preflight
  ↓
guarded agent/* branch from fresh origin/main
  ↓
implementer
  ↓
independent reviewer
  ↓
bounded fixer / fresh review
  ↓
Ruff / mypy / pytest
  ↓
guarded commit + push + PR
  ↓
Quality + Test
  ├─ fail → CI analyst → bounded fixer → repush
  └─ pass
  ↓
fresh full-PR reviewer
  ├─ P0/P1/P2 → fixer → CI → fresh review
  └─ clean
  ↓
MERGE_READY exact PR + HEAD
  ↓
human exact-PR/exact-HEAD approval
  ↓
guarded squash merge
```

`origin/main` CI must already be green before an unrelated autonomous task
starts. This prevents a task from treating pre-existing infrastructure failures
as its own regressions or silently inheriting them.

The branch-creation wrapper runs the guarded preflight itself and binds task
creation to the verified `origin/main` SHA. Running the preflight separately is
useful for early diagnosis, but its output is not a reusable authorization
token.

## GitHub authentication

Do not use sandboxed `gh auth status` as the workflow's source of truth. The
guarded preflight performs a real `gh api user` request from the allow-listed
host execution context.

Authenticate once from a trusted host terminal:

```powershell
gh auth login
gh auth setup-git
gh api user --jq .login
```

## Repository policy

Expected server-side policy for `main`:

- changes require a Pull Request;
- required checks are `Quality` and `Test`, each bound to the GitHub Actions
  application ID;
- required checks are strict and up to date;
- administrators are protected;
- linear history and resolved conversations are required;
- force pushes and branch deletion are disabled;
- squash merge is enabled;
- merge commits and rebase merges are disabled; and
- merged task branches are deleted automatically.

Configure and verify the policy from a trusted administrator terminal:

```powershell
pwsh -NoProfile -File scripts/github/configure-main-protection.ps1
pwsh -NoProfile -File scripts/github/verify-main-protection.ps1
```

These administrator scripts are intentionally forbidden to Codex execution.

## Trusted guard installation

After the bootstrap is on protected `main` and its CI is green, use a trusted
human terminal from a clean standard checkout whose local `main` exactly matches
`origin/main`:

```powershell
pwsh -NoProfile -File scripts/setup/install-guarded-wrappers.ps1
```

If normal command discovery resolves `codex.cmd`, `codex.ps1`, or another Node
launcher shim, pass the native executable explicitly:

```powershell
pwsh -NoProfile -File scripts/setup/install-guarded-wrappers.ps1 `
  -CodexExecutablePath "C:\path\to\native\codex.exe"
```

Restart Codex after installation. Then read
`.git/codex-guard/guard-invocation.json` in a sandboxed step and invoke the
preflight with the exact literal `shellPath` and
`scripts["scripts/agent/github-preflight.ps1"]` values:

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_GITHUB_PREFLIGHT_PATH
```

The installer extracts the reviewed wrapper blobs from `origin/main`, verifies
their Git object IDs and PowerShell syntax, records SHA-256 hashes, and installs
an empty hooks directory. Each run publishes a fresh immutable guard directory
whose name includes the repository policy ID, source SHA, and a new installation
ID. It never overwrites or removes an earlier immutable guard directory and
never copies mutable working-tree files.

After publishing the new directory, the installer activates its
repository-and-checkout-keyed user-layer rule and read-only discovery metadata
under `.git/codex-guard/`. Only prior repository metadata is retained under a
timestamped `.git/codex-guard.backup-*` path. If policy or metadata activation
fails, the installer restores the previous policy and metadata and removes only
the newly published guard directory. Older immutable guard directories remain
available for explicit maintainer cleanup. If restoring the old policy itself
fails, its rollback copy is retained at the path reported by the installer for
manual recovery instead of being deleted.

Every entry point verifies all installed hashes. Preflight additionally checks
that the installed source blob IDs still match current `origin/main`. After any
trust-boundary source change is manually merged, a maintainer must review and
rerun the installer before another autonomous task.

The current installation layout requires a normal checkout with a `.git`
directory. Linked worktrees, where `.git` is a file, are not supported by this
guard version. The checkout, `.git`, PowerShell executable, Codex home, user
rules directory, and guard store must not traverse symbolic links, junctions,
or other reparse points, and must be addressed by their canonical physical
paths rather than extended, substituted-drive, short-name, or other aliases.
The Codex home, user rules directory, guard store, and installation target must
also be outside the repository and the system temporary directory because both
are writable from the ordinary sandbox.
The installer accepts only `pwsh.exe` or `powershell.exe` under the protected
Windows or Program Files directory. It resolves Git, GitHub CLI, and Codex CLI
to canonical absolute regular-file paths outside the repository's writable
trust boundary. The Codex file must be the self-contained native `codex.exe`,
never a Node launcher shim; `-CodexExecutablePath` supplies that file when
normal discovery does not. The installer records those paths and the accepted
Codex CLI version in the manifest and serializes installation with guarded
workflow operations through the same `.git` lock.

## Machine setup

Required tools:

- Git
- tar (the Windows 11 built-in implementation is sufficient)
- GitHub CLI
- PowerShell 7 (`pwsh.exe`) or Windows PowerShell (`powershell.exe`); the
  installer binds the exact regular executable used for installation
- Python 3.12
- uv
- VS Code and Codex

Guard installation and `scripts/guard-tests/guard-regression.ps1` require the
native `codex.exe` for a Codex CLI version listed in
`scripts/guard-tests/codex-cli-version.txt`. Guard regression validation always
runs real `codex execpolicy check` cases; a missing, shimmed, or unlisted CLI is
a validation failure, not a skipped check. The `Quality` CI job installs every
listed version and runs the regression with both PowerShell 7 and Windows
PowerShell 5.1.

After changing Codex project configuration or execution rules through the
manual security-bootstrap process, reinstall the guard and reload the Codex
session from protected `main` so the reviewed rules are read again.

## Repair-loop limits

| Loop | Maximum fixer rounds |
| --- | ---: |
| Local review | 2 |
| CI repair | 2 |
| Final PR review | 2 |

Exhausting a loop returns `BLOCKED` with evidence instead of weakening checks or
continuing indefinitely.

## Task state and parallelism

One writable guarded task may be active per worktree. Do not overwrite an
existing task state or start a second writable task in the same worktree.
State-changing wrappers acquire an exclusive OS file lock under `.git`, so
concurrent guarded operations fail before they can replace task or branch
identity.

Task start and commit are recoverable write-ahead transitions. `start-task.ps1`
records the intended task identity before creating or switching the branch;
`commit-task.ps1` records the parent, message, phase, and staged tree before the
commit becomes authoritative. If either wrapper is interrupted, rerun that same
wrapper with the same arguments. It verifies the recorded identity and resumes
or confirms the transition before clearing the pending operation. Other
task-state-dependent guarded wrappers fail closed while that pending state
remains.

Only after confirming that no task is active may a human remove the stale state
path returned by:

```powershell
git rev-parse --git-path codex-task.json
```

Independent read-only review or analysis may run concurrently when it cannot
interfere with the writable task.

## Final merge

The workflow stops at `MERGE_READY`. Readiness is recorded for one exact PR
number and HEAD SHA. If `create-pr.ps1` binds the task to a replacement PR, it
clears all prior readiness and merge-attempt evidence. The installed
`merge-task.ps1` may run only after the user explicitly approves the exact PR
and HEAD SHA that were presented as merge-ready.

The wrapper rechecks:

- recorded PR identity;
- exact approved and merge-ready SHA;
- unchanged PR HEAD;
- mergeability;
- `Quality` and `Test` are present and have passed;
- `main` still requires those contexts with strict status checks and the
  configured GitHub Actions application ID;
- local task HEAD and the validated literal push target still equal the
  approved SHA; and
- the guarded task state.

`merge-ready.ps1` performs the same branch-protection verification before it
records readiness, and `merge-task.ps1` repeats it immediately before merging
an unmerged PR. Recovery of an already merged PR also requires the current
protection to verify. A mismatch stops the workflow.

The wrapper then performs the configured squash merge. Remote and local task
refs are deleted only while they still equal the approved SHA; concurrently
changed refs are preserved for manual handling. If the remote merge succeeds
but a subsequent communication or cleanup step fails while task state remains,
rerun `merge-task.ps1` only with the same PR number and approved SHA. Recovery
continues only when the task state contains the matching pre-merge squash
attempt and GitHub reports `MERGED` with `mergedAt`; the PR HEAD, task HEAD,
recorded `mergeReadySha`, attempted SHA, and supplied `ExpectedHeadSha` must all
agree. Incomplete cleanup keeps task state and returns a failure so the same
guarded command can resume. Any difference is rejected; approval never
transfers to another SHA. Never bypass this boundary with raw Git or
`gh pr merge` commands.
