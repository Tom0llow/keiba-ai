---
name: autonomous-task
description: >-
  Run the full guarded coding lifecycle from a user requirement to MERGE_READY:
  preflight, branch, implementation, independent review/fix, commit, push, PR,
  CI remediation, final PR review, and readiness gate. Use for non-trivial
  implementation or bug-fix requests unless the user explicitly asks for
  local-only work.
---

# Autonomous Task Orchestrator

The intended successful lifecycle is:

```text
Human: requirement
AI: preflight -> agent/* -> implement/review/fix -> validate -> commit/push/PR
    -> CI/fix -> final PR review/fix -> MERGE_READY
Human: approve exact MERGE_READY PR + HEAD
AI: guarded squash merge
```

Do not merge in this skill.

## Hard bounds

- writable agents run sequentially
- local review/fix: max 2 fixer rounds
- CI fix: max 2 fixer rounds per PR HEAD lineage
- final PR review fix: max 2 fixer rounds
- never recursively start another `autonomous-task`
- do not overwrite an existing guarded task state
- never modify the workflow trust boundary through an autonomous task
- stop as BLOCKED instead of guessing when a material product/security decision is required

## Phase 0 — guarded host preflight

In a separate sandboxed read, load
`.git/codex-guard/guard-invocation.json`. For every guarded call, pass its exact
absolute `shellPath` as argv[0] and the exact absolute value from `scripts` as
the `-File` argument. Never invoke a relative guard path, reconstruct a path
from the current directory, or wrap the call in `-Command`. The placeholders
below mean those literal JSON values; they are not shell variables.

Run exactly one standalone command:

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_GITHUB_PREFLIGHT_PATH
```

Do not replace it with `gh auth status`.

Do not chain it with `&&`, `;`, pipes, or another command.

The preflight verifies:

- GitHub API access through the host-side allow-listed wrapper
- origin/main existence
- installed guard hashes match the guarded sources on current origin/main
- repository/main protection policy
- current main baseline CI is green

If the error mentions `proxyconnect` or `127.0.0.1:9`, treat that as an
exec-policy/rule-loading problem, not as proof of invalid GitHub credentials.
Stop and inspect `.git/codex-guard/guard-invocation.json` in a sandboxed step.
Confirm that its `policyPath` names an existing user-layer rule. If that policy
is missing or stale, instruct the user to reinstall the guard manually from
clean protected `main`; then reload/restart Codex before retrying.

If baseline main CI is failing, stop. Do not start an unrelated task on a known
broken baseline.

## Phase 1 — guarded task branch

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_START_TASK_PATH -TaskName "<short task name>"
```

Startup requires:

- clean working tree
- current local branch is `main`
- no unrelated active/stale guarded task state
- branch is created from fresh `origin/main`

`start-task.ps1` repeats the guarded preflight immediately before branch
creation and requires the fetched `origin/main` SHA to match the verified
baseline SHA. The standalone Phase 0 command is an early diagnostic; Phase 1
does not trust or reuse its earlier output.

The wrapper records a pending start before creating or switching the branch. If
the call is interrupted, rerun this same command with the same arguments; the
wrapper verifies and resumes that transition. Do not invoke another guarded
wrapper or remove the pending state.

## Phase 2 — implement + independent local review

Read the applicable `AGENTS.md`, `ARCHITECTURE.md`, repository rules, and
relevant Accepted ADRs before deciding where or how to change code. Treat those
files and the current repository as authoritative; do not assume that a
particular product architecture has already been implemented.

Spawn `implementer` with:

- full requirement
- explicit acceptance criteria
- relevant architecture/ADR constraints
- instruction not to commit/push/PR/merge

Inspect the complete diff.

Spawn a fresh read-only `reviewer`.

Require the reviewer to assess correctness, security, compatibility, state and
data integrity, architecture/ADR compliance, and effective tests as applicable
to the change.

Validate reviewer findings yourself.

For validated P0/P1/P2 findings, spawn `fixer`, then re-review the complete
current diff with a fresh reviewer. Maximum two fixer rounds.

P3 may remain only when non-blocking and reported.

## Phase 3 — repository validation

Run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Run the trust-boundary regression with PowerShell 7 (`pwsh`) or Windows
PowerShell (`powershell.exe`):

```powershell
pwsh -NoProfile -File scripts/guard-tests/guard-regression.ps1
```

The regression requires an allow-listed self-contained native `codex.exe`;
`codex.cmd` and `codex.ps1` Node launcher shims are unsupported. CI additionally
runs every allow-listed version under both PowerShell hosts.

Do not publish known task-related failures.

## Phase 4 — commit / push / PR

Use only:

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_COMMIT_TASK_PATH -Message "<type(scope): description>"
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_PUSH_TASK_PATH
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_CREATE_PR_PATH -Title "<title>" -Body "<body>"
```

`commit-task.ps1` records a write-ahead commit intent. If it is interrupted,
rerun the same wrapper with the same `-Message`; unrelated task-state-dependent
guarded wrappers must not run until recovery verifies the recorded parent, tree,
and message.

PR body must include:

- `Summary`
  - a changed-file tree containing every changed file and only the parent directories needed to locate them,
  - the purpose and motivation of every commit, identified by short SHA or subject,
  - a per-file description for every changed file,
- `Validation`,
- `Architecture / ADR impact`,
- `Risks / Notes`.

Capture PR number, URL, and exact `headSha` from the guarded result. Use that
same SHA for every CI and inspection call until another guarded commit changes
HEAD; after a fix commit, capture and propagate the replacement SHA instead. If
PR creation rebinds the task to a replacement PR, all prior readiness and merge
attempt evidence is cleared.

## Phase 5 — CI stabilization

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_WAIT_CI_PATH `
  -PrNumber <N> `
  -ExpectedHeadSha "<current-head-sha>"
```

Required checks are exactly:

- `Quality`
- `Test`

If CI fails, follow `ci-fix`. After each fix commit/push, wait again.

Stop as BLOCKED after two CI fixer rounds.

## Phase 6 — final PR review

Follow `pr-review`.

The final reviewer must inspect the complete PR at the latest exact HEAD. The
inspection result must agree on its observed `baseSha`, recorded task
`diffBaseSha`, and expected `headSha`; the diff is the complete local
binary/full-index diff from `diffBaseSha...headSha` with external diff and text
conversion disabled.

Validated P0/P1/P2 findings require fix -> validation -> guarded commit/push ->
CI -> fresh full-PR review.

Never reuse a review from an older HEAD.

## Phase 7 — MERGE_READY

```powershell
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_MERGE_READY_PATH `
  -PrNumber <N> `
  -ExpectedHeadSha "<reviewed-head-sha>"
```

Only when ready, present:

- exact PR number/title/URL
- exact `headSha`
- `Quality` / `Test` status
- final AI review P0/P1/P2 = 0
- remaining P3, if any

Readiness is bound to that PR number and SHA. Then ask:

```text
May I squash-merge PR #<N> at this exact HEAD (<sha>) into main?
```

Do not invoke `merge-task.ps1` until the user explicitly approves that exact SHA.

## BLOCKED conditions

Return BLOCKED for:

- pre-existing/stale guarded task state
- dirty worktree
- missing, stale, or hash-invalid installed guard
- attempted workflow trust-boundary change
- GitHub host preflight failure
- baseline main CI failure
- missing/incorrect repository protection
- materially ambiguous requirements
- required dependency addition awaiting approval
- exhausted local/CI/PR-review repair bounds
- branch/PR/HEAD identity mismatch
- security-sensitive decision requiring a human
