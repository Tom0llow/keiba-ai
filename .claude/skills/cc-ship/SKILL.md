---
name: cc-ship
description: Commit the reviewed worktree changes, push them with the GitHub App identity, open or update the App-authored PR, and drive required CI to green. Never approves or merges. Use as the publication phase of cc-task.
disable-model-invocation: true
---

# Publish with the Agent Identity

All remote writes use the GitHub App: `git push` through the `x-access-token`
push URL and `gh` through `scripts/github-app/github-app.ps1`. The App cannot
merge `main`, approve reviews, or change workflows; do not try to work around
any rejection - stop and report it.

```bash
APP_GH="pwsh -NoProfile -File $ROOT/scripts/github-app/github-app.ps1 gh"
REPO="Tom0llow/keiba-ai"
```

## 1. Commit

1. Precondition: the latest `cc-review` has no open `fix` decisions and the
   full validation passed on the current worktree content.
2. Stage and inspect every path; nothing unintended may be included:

   ```bash
   git -C "$WT" add --all
   git -C "$WT" status --short
   git -C "$WT" diff --cached --check
   ```

3. Commit with a Conventional Commit message (`docs/rules/git-workflow.md`),
   ending with the attribution trailers your session requires. Never amend a
   pushed commit.

## 2. Push and open the PR

```bash
git -C "$WT" push -u origin "$BRANCH"
```

Write `$HANDOFF/pr-body.md` following `.github/pull_request_template.md`
(changed-file tree, commit purposes, per-file details, validation actually run,
ADR notes, risks including deferred findings). Then, first round only:

```bash
$APP_GH pr create --repo "$REPO" --base main --head "$BRANCH" \
  --title "<conventional title>" --body-file "$HANDOFF/pr-body.md"
```

Later rounds push new commits and refresh the body with
`$APP_GH pr edit <n> --repo "$REPO" --body-file "$HANDOFF/pr-body.md"`.

Confirm the PR is App-authored and points at the local HEAD:

```bash
$APP_GH pr view <n> --repo "$REPO" --json url,author,headRefOid,state
git -C "$WT" rev-parse HEAD
```

## 3. Drive CI

Run in the background and wait for the notification:

```bash
$APP_GH pr checks <n> --repo "$REPO" --required --watch --interval 30
```

- Both `Quality` and `Test` must pass on the exact HEAD.
- On failure, collect evidence into `$HANDOFF/ci-$ROUND.md`:

  ```bash
  $APP_GH run list --repo "$REPO" --branch "$BRANCH" --json databaseId,name,conclusion,headSha
  $APP_GH run view <run-id> --repo "$REPO" --log-failed
  ```

  Then `cc-implement` with that file, re-run validation, `cc-review` when the
  fix is more than mechanical, commit, push, and watch again. At most two CI fix
  rounds.
- If `main` advanced and the branch must be updated, use
  `$APP_GH pr update-branch <n> --repo "$REPO"` and then
  `git -C "$WT" pull --ff-only`. If GitHub rejects it (for example because
  `main` changed workflow files the App may not touch), ask the human to click
  "Update branch".

## 4. Hand over

Return the PR URL, number, and exact HEAD SHA to `cc-task` for the READY report.
