# Git Workflow

## 1. Strategy and trust boundary

`main` is the permanent integration branch. Every change reaches `main` through
a squash-merged Pull Request.

The trust boundary is enforced by GitHub, not by local wrappers (ADR-031):

- agent pushes and PRs use the `keiba-ai-agent` GitHub App identity;
- the `main-protection` ruleset requires a PR, an approving review from the
  code owner on the most recent push, resolved conversations, `Quality` and
  `Test` on an up-to-date branch, linear history, and no force push or
  deletion, with no bypass;
- the `main-merge-restriction` ruleset lets only repository administrators
  update `main`, and only through a PR, so the App cannot merge even after
  approval;
- the App has no `workflows` permission, so agent pushes cannot change
  `.github/workflows/`.

Local Claude Code permissions and Codex execution rules are defense in depth;
they do not replace the server-side rules.

## 2. Branch naming

Agent task branches:

```text
agent/<task-id>          # task-id = YYYYMMDD-<short-kebab-slug>
```

Human branches may use:

```text
feat/<topic>
fix/<topic>
refactor/<topic>
test/<topic>
docs/<topic>
chore/<topic>
```

## 3. Before starting work

Inspect:

```bash
git status --short --branch
git log -5 --oneline
```

Never discard pre-existing user work. Agent tasks run in
`.worktrees/<task-id>/` so the main checkout stays untouched.

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

## 5. Commit scope and policy

One commit should represent one coherent logical change. Do not mix unrelated
refactors, formatting, dependency upgrades, or generated content.

- Claude Code commits only inside the `cc-task` lifecycle or when the user asks.
- Codex never commits.
- Do not amend or rewrite pushed commits; push a new commit instead.

## 6. Remote operations

- Agent pushes use the `x-access-token` push URL, which the GitHub App
  credential helper serves (see section 13).
- Agent `gh` calls go through `scripts/github-app/github-app.ps1 gh ...`, which
  allows only PR creation, inspection, comments, edits, branch updates, and
  CI inspection.
- Outside `cc-task`, push and PR actions require explicit user intent.
- Agents never approve reviews, merge PRs, change rulesets, or edit repository
  settings.

## 7. Force push

Never force-push. `main` rejects force pushes and deletion.

## 8. Pull Requests

Each PR must have one clear purpose.

Before publication:

- validation passes,
- the diff is scoped,
- no secrets or debug junk,
- documentation is updated when needed.

PR body (`.github/pull_request_template.md`):

```text
## Summary

## Validation

## Architecture / ADR

## Risks / Notes
```

The `## Summary` section must include:

- a directory tree containing every changed file and only the parent
  directories needed to locate those files,
- the purpose and motivation of each commit, identified by its short SHA or
  subject,
- a per-file description of the changes for every changed file.

## 9. CI

Required checks are:

```text
Quality
Test
```

Both are bound to the GitHub Actions app (`integration_id` 15368) in the
ruleset. CI is successful only when both exist and pass on the PR's current
HEAD. Known baseline CI failures are fixed before unrelated work begins.

## 10. Merge policy

Repository policy is squash-only. The human owner:

1. reviews the App-authored PR at its current HEAD,
2. approves it on GitHub,
3. merges it on GitHub.

A new push dismisses earlier approvals and requires approval of the latest
push. Human-authored PRs cannot satisfy the code-owner approval rule; route
human changes through an App-authored PR or temporarily disable the ruleset in
repository settings, then re-enable it.

## 11. Parallelism

Only one writer per worktree. Independent tasks use separate worktrees and
branches. Read-only reviewers may run in parallel.

## 12. Dependencies

Dependency additions and removals are an explicit approval boundary. When
approved, update `pyproject.toml` and `uv.lock` together and rerun the full
validation suite.

## 13. Agent identity setup

One-time machine setup by the human owner (the App, its private key, and its
installation on this repository already exist):

1. Create `~/.config/keiba-ai-agent/app.json` with `appId`, `installationId`,
   `privateKeyPath`, and `repository` (`keiba-ai`). The private key stays
   outside the repository and is never shown to an agent.
2. Configure the push identity in this clone:

   ```bash
   git remote set-url --push origin https://x-access-token@github.com/Tom0llow/keiba-ai.git
   git config credential.https://x-access-token@github.com.helper ""
   git config --add credential.https://x-access-token@github.com.helper \
     "!pwsh -NoProfile -File <absolute repo path>/scripts/github-app/github-app.ps1 credential"
   ```

3. Verify: `pwsh -NoProfile -File scripts/github-app/github-app.ps1 check`.

Pushing as yourself requires an explicit URL, for example
`git push https://github.com/Tom0llow/keiba-ai.git <branch>`; this is needed
for workflow-file changes, which the App cannot push.

## 14. Final review

Before publication or merge, inspect:

```bash
git status --short
git diff --check
git diff
```

Do not claim validation or review passed unless it actually ran on the current
HEAD.
