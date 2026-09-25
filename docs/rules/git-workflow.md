# Git Workflow

## 1. Strategy and activation boundary

`main` is the permanent integration branch. Normal changes use short-lived
branches and Pull Requests.

The first installation of the AI-driven-development foundation is a one-time
human/manual bootstrap. It cannot depend on guarded wrappers, green baseline CI,
or repository protection before those controls have been installed. This
bootstrap may therefore use an explicitly authorized human or local-only
process, but it must not claim `MERGE_READY` or claim that inactive controls were
satisfied.

The guarded workflow is activated after all of the following are true:

1. the bootstrap is present on `main`;
2. `Quality` and `Test` exist and pass on `main`;
3. the configured protection for `main` is verified;
4. a human installs the reviewed wrappers from protected `origin/main` in the
   protected Codex user guard store, writes repository invocation metadata
   under `.git/codex-guard/`, and installs the generated
   repository-and-checkout-bound absolute-path rule in the Codex user layer;
5. Codex has been restarted so that user-layer rule is active; and
6. the installed guarded preflight succeeds.

The exception ends at activation and must not be reused. From that point, every
non-trivial Codex implementation or bug fix uses the guarded `autonomous-task`
workflow unless the user explicitly requests local-only work or read-only
analysis. Local-only work does not authorize Git or GitHub mutations.

Human-owned manual work and guarded autonomous Codex work remain distinct
execution modes. Do not combine their permissions or commands in a way that
bypasses the guarded workflow.

## 2. Branch naming

Manual branches may use:

```text
feat/<topic>
fix/<topic>
refactor/<topic>
test/<topic>
docs/<topic>
chore/<topic>
```

Guarded autonomous branches use only:

```text
agent/<generated-task-name>-<timestamp>
```

Codex must create autonomous branches only through:

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_START_TASK_PATH -TaskName "<task>"
```

The placeholders above and below are values read in a separate sandboxed step
from `.git/codex-guard/guard-invocation.json`. Pass the exact absolute
`shellPath` and matching `scripts` value as argv tokens. They are not shell
variables. Relative `.git/codex-guard/...` commands are forbidden because
execution policy compares argv and does not bind a relative token to this
repository's working directory.

## 3. Before starting work

Inspect:

```bash
git status --short --branch
git log -5 --oneline
```

Never discard pre-existing user work.

The autonomous workflow requires a clean worktree, local `main`, and no existing
guarded task state before creating a task branch.

`start-task.ps1` performs the guarded GitHub/repository/baseline-CI preflight
before creating the branch and refuses to continue if the fetched `origin/main`
SHA differs from the verified baseline SHA.

Before creating or switching the task branch, the wrapper writes a pending
start state. If interrupted, rerun `start-task.ps1` with the same arguments; it
verifies the recorded task, base, branch, and start SHA before resuming. Other
task-state-dependent guarded wrappers fail closed while that pending start
remains.

Files under `scripts/agent/` are reviewable source only. They must not be used
as host-side trust anchors or executed in place. A human installs their reviewed
copies from protected `origin/main` by running
`scripts/setup/install-guarded-wrappers.ps1`; autonomous work executes only the
copies in the protected Codex user guard store through the
repository-and-checkout-bound absolute-path policy that installer writes outside
the repository in the Codex user rules layer. `.git/codex-guard/` contains
discovery metadata, not executable wrapper copies.

Each installer run publishes a new immutable guard directory identified by the
repository policy ID, protected source SHA, and installation ID. Earlier guard
directories are left unchanged. The manifest fixes the canonical absolute
PowerShell, Git, GitHub CLI, and Codex CLI paths and the accepted Codex CLI
version. The Codex path must be the self-contained native `codex.exe`, not a Node
launcher shim such as `codex.cmd` or `codex.ps1`; the installer accepts
`-CodexExecutablePath` when normal discovery resolves a shim. Changing any path
or version requires reinstallation and a Codex restart.

## 4. Commit format

Use Conventional Commits:

```text
<type>(<optional-scope>): <description>
```

Common types:

```text
feat
fix
refactor
test
docs
perf
build
ci
chore
```

## 5. Commit scope

One commit should represent one coherent logical change.

Do not mix unrelated refactors, formatting, dependency upgrades, or generated
content.

## 6. Commit policy

Outside `autonomous-task`, do not create commits unless the user asks or the
surrounding workflow explicitly expects them.

Inside `autonomous-task`, the coordinator is authorized to commit through:

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_COMMIT_TASK_PATH -Message "<message>"
```

The implementation/reviewer/fixer subagents themselves never commit.

Do not amend or rewrite published history in the autonomous workflow.

`commit-task.ps1` records its pending parent, commit message, phase, and staged
tree before the commit becomes authoritative. If interrupted, rerun it with the
same `-Message`; it accepts only the recorded parent/tree/message result and
clears the pending state after verification. Do not run another guarded wrapper
against an incomplete commit.

Guarded Git operations disable local hooks and filesystem monitors. Repository
validation runs separately in the ordinary sandbox and in CI; a hook is not a
substitute for those checks.

## 7. Remote operations

Outside `autonomous-task`, push/PR/merge actions require explicit user intent.

Inside `autonomous-task`, these are authorized without another user turn:

```text
guarded agent/* branch creation
guarded commit
guarded push
guarded PR creation
CI polling / read-only PR inspection
```

Use only the exact absolute wrapper paths recorded in
`.git/codex-guard/guard-invocation.json`. Direct Git or GitHub mutation
commands, relative guard paths, and tracked source wrappers are not substitutes.
The generated policy forbids direct top-level invocation of the recorded GitHub
CLI and Codex CLI executables. Do not use another executable path, raw command,
or environment override to bypass the wrappers.

The autonomous workflow must stop at `MERGE_READY`.

Final merge requires explicit user approval of the exact reviewed PR number and
HEAD SHA, then uses the recorded absolute `merge-task.ps1` path.

The autonomous workflow rejects changes to its trust boundary. This includes
every `AGENTS.md` or `AGENTS.override.md` at any depth,
`.pre-commit-config.yaml`, `.agents/`, `.codex/`, `.github/`,
`scripts/agent/`, `scripts/guard-tests/`, `scripts/github/`, `scripts/setup/`,
`docs/AUTONOMOUS_DEVELOPMENT.md`, `docs/rules/git-workflow.md`,
`docs/decisions/ADR-001-trusted-guarded-wrappers.md`, and repository
interpretation files such as `.gitattributes`, `.gitmodules`, and `.lfsconfig`.
Such changes require an explicitly authorized manual security bootstrap,
followed by guard reinstallation from protected `main`.
This prohibition also covers ignored untracked protected paths. The guard
checks those pathspecs independently of ordinary `git status`, including every
nested `AGENTS.md` and `AGENTS.override.md`.

## 8. Force push

Codex must never force-push in the autonomous workflow.

`main` must reject force pushes.

Manual history repair is an exceptional human operation and is outside the
autonomous contract.

## 9. Pull Requests

Each PR must have one clear purpose.

Before publication:

- validation passes
- diff is scoped
- no secrets/debug junk
- documentation is updated when needed

PR body:

```text
## Summary

## Validation

## Architecture / ADR

## Risks / Notes
```

The `## Summary` section must include all of the following:

- a directory tree containing every changed file and only the parent directories
  needed to locate those files
- the purpose and motivation of each commit, identified by its short SHA or subject
- a per-file description of the changes for every changed file

## 10. CI

Required checks are:

```text
Quality
Test
```

The workflow must not declare CI successful until both required check names
exist and pass. A required check may not be skipped; optional checks may be
skipped, but no check may remain pending or failing. Branch protection binds
both required contexts to the GitHub Actions application ID, not only to their
display names.

The `Quality` job runs the real guard regression for every version in
`scripts/guard-tests/codex-cli-version.txt` using both PowerShell 7 and Windows
PowerShell 5.1. A missing native executable, unsupported version, host-specific
failure, or skipped policy evaluation fails the job.

After a guarded push, pass its exact HEAD SHA as `ExpectedHeadSha` to every CI
wait, PR/CI inspection, merge-readiness, and merge wrapper. Evidence collected
for one SHA is invalid for another SHA. PR inspection reports the observed PR
base as `baseSha`, the recorded task start as `diffBaseSha`, and the expected
head as `headSha`. The complete diff is generated locally as a binary/full-index
diff from `diffBaseSha...headSha`, with external diff and text conversion
disabled. Checks come only from the check-runs and commit-status APIs addressed
to `ExpectedHeadSha`.

Known baseline CI failures are fixed before unrelated autonomous work begins.

## 11. Merge policy

Repository policy is squash-only.

`main` requires:

- Pull Request association
- 0 mandatory GitHub human approvals
- `Quality` and `Test`
- strict/up-to-date status checks
- linear history
- resolved conversations
- no force push
- no deletion

The human safety boundary is the explicit approval of the exact MERGE_READY PR
number and HEAD, not an additional GitHub Approve click. Readiness and merge
attempts belong to that PR/SHA pair. If `create-pr.ps1` binds the task to a
replacement PR, it clears both records and the new PR must complete readiness
again.

`merge-ready.ps1` and the unmerged-PR path in `merge-task.ps1` revalidate the
required contexts, strict status setting, and configured GitHub Actions
application ID for `main`. A mismatch stops readiness or merge. If a remote
merge succeeds before a communication or cleanup failure and task state remains,
rerun `merge-task.ps1` only for the same PR and approved SHA. Cleanup recovery
requires the matching recorded pre-merge squash attempt, current protection,
GitHub `MERGED` state, `mergedAt`, and agreement among PR HEAD, task HEAD,
`mergeReadySha`, attempted SHA, and `ExpectedHeadSha`. Incomplete cleanup keeps
task state and fails for an exact retry; approval never transfers to a different
SHA.

## 12. Parallelism

Writable agents are serialized in the current worktree.

Do not start a second guarded autonomous task while
`.git/codex-task.json` represents an active task.

State-changing wrappers also acquire an exclusive OS file lock under `.git`
before reading or updating task identity or branch state. A concurrent guarded
operation fails closed instead of replacing another task's state.

Pending start or commit write-ahead state also blocks unrelated
task-state-dependent wrappers. Resume only by rerunning the original wrapper
with the same arguments; do not delete or rewrite the state to bypass its
identity checks.

Read-only reviewer/analysis agents may run concurrently when safe.

## 13. Dependencies

Dependency additions/removals are an explicit approval boundary.

When approved, update `pyproject.toml` and `uv.lock` together and rerun the full
validation suite.

## 14. Final review

Before publication/merge, inspect:

```bash
git status --short
git diff --check
git diff
```

Do not claim validation or review passed unless it actually ran on the current
HEAD.
