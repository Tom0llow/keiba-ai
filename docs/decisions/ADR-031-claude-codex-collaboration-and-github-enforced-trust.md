# ADR-031: Claude CodeとCodexの役割分担とGitHub側で強制する信頼境界

- Status: Accepted
- Date: 2026-11-08
- Decision Owners: Repository maintainers
- Supersedes: ADR-001, ADR-016
- Superseded by: N/A

## Context

ADR-001とADR-016は、Codex専用のguarded workflowを信頼境界としていた。
ハッシュ検証済みPowerShellラッパーをCodexのユーザーguard storeへ導入し、
実行ポリシー、絶対パス、Codex CLIの版と実行ファイルを固定し、
PR番号とHEAD SHAに束縛したMERGE_READYを人間が承認する方式である。

ユーザーはClaude CodeとCodexの併用を求めた。設計とレビューはClaude、
実装はCodexが担当する。既存のguarded workflowはCodexの実行ポリシーと
ローカルラッパーに依存するため、Claude Codeを同じ境界に載せられない。
維持コストも大きく、Windows固有のPowerShell 5.1/7回帰とCodex版の固定が
CIと日常運用を拘束していた。ユーザーは、既存workflowの破壊的な置換と、
GitHub Appによるエージェント識別を明示的に選択した。

## Decision

1. Claude Codeは設計、進行、検証、二系統レビューの裁定、コミット、push、PR作成、
   CI対応を担当する。Codexは、承認済みの計画と指摘ラウンドを
   `.worktrees/<task-id>/`で実装し、読み取り専用レビューを行う。
   Codexは、Git状態の変更、`gh`、ネットワークを使わない。
   人間は計画を承認し、GitHub上でPRを承認してマージする。
2. エージェントのGitHub書き込みは、`keiba-ai-agent` GitHub Appの
   インストールトークンで行う。トークンは1時間有効で、本リポジトリに限定する。
   `scripts/github-app/github-app.ps1`が毎回、秘密鍵でJWT(RS256)を署名し、
   トークンへ交換する。トークンと秘密鍵はファイルや出力に残さない。
   git pushは`x-access-token`のpush URL専用のcredential helperで行う。
   `gh`は許可したサブコマンドだけを実行できる。
   Appには`workflows`権限を与えない。
3. 信頼境界はGitHubのrulesetで強制する。
   - `main-protection`(バイパスなし): PR必須、code ownerによる承認1件、
     最新pushの承認、push時の古い承認の無効化、会話の解決、`Quality`と`Test`
     (GitHub Actions、integration 15368)の厳格な最新状態での成功、線形履歴、
     force pushと削除の禁止、squashのみ。
   - `main-merge-restriction`: `main`の更新を、管理者のPR経由に限る。
     Appは承認後もマージできない。
4. Claude Code専用スキルは`.claude/skills/`に、Codex専用スキルは
   `.agents/skills/`に置く。共用スキルの正本は`.agents/skills/`に置き、
   `.claude/skills/<name>`から相対シンボリックリンクで参照する。
   共用スキルはツール非依存とし、frontmatterは`name`と`description`だけにする。
5. ADR-001とADR-016のguarded workflow一式を削除する。対象は
   `scripts/agent/`、`scripts/guard-tests/`、`scripts/setup/`、`scripts/github/`、
   Codexのサブエージェント定義、guard系スキル、運用文書、CIのguard回帰である。

## Rationale

- 信頼境界を、エージェントやツールの種類に依存しないGitHub側へ移すと、
  Claude CodeとCodexの両方を同じ規則で扱える。
- PR作成者をAppにすると、人間がcode ownerとして承認できる。
  最新pushの承認を必須にすると、承認したHEAD以外はマージできない。
  これはMERGE_READYのSHA束縛をサーバー側で置き換える。
- インストールトークンは短命でリポジトリに限定されるため、
  会話ログや出力への混入による被害期間を1時間に抑えられる。
- Codexを、資格情報もネットワークも持たない作業者に限定すると、
  サンドボックスの外での操作が不要になる。

## Consequences

### Positive

- ラッパー導入、guard再インストール、Codex版固定、PowerShell 5.1回帰が不要になる。
- 承認とマージは、GitHub上の人間の操作だけで完結する。
- 共用スキルは一か所で管理でき、両ツールから参照できる。

### Negative

- エージェントと同じWindowsユーザーには、人間の`gh`とGitの資格情報、
  Appの秘密鍵が残る。悪意のある操作を最終的に防ぐのはサーバー側の規則だけで、
  ローカルのdeny設定は防御の補助にとどまる。
- 人間が作成したPRはcode owner承認を満たせない。人間の変更も
  App作成のPRを経由するか、rulesetを一時的に無効化する必要がある。
- Windowsでシンボリックリンクを扱うには、開発者モードと
  `core.symlinks=true`が必要になる。

### Neutral / Follow-on effects

- `.github/workflows/`の変更は、Appではpushできない。人間が自分の資格情報で
  pushする。
- `.handoff/`と`.worktrees/`は、Git管理外の作業領域になる。

## Alternatives Considered

### Option A: 既存guarded workflowへClaude Codeを追加する

Codexの実行ポリシーとguard storeに依存するため、Claude Codeの権限モデルへ
移植する必要があり、維持コストがさらに増える。採用しない。

### Option B: マシンユーザーとclassic PATを使う

設定は簡単だが、トークンが長命で、権限がWrite role全体に及ぶ。
共同作業者としてfine-grained PATを使える保証もない。採用しない。

### Option C: ボットを使わず人間の資格情報を使う

人間は自分のPRを承認できず、承認必須を外すしかない。
その場合、エージェントがCI通過後にマージできてしまう。採用しない。

## Validation

- `src/tests/integration/test_github_app_helper.py`: JWT署名、
  リポジトリに限定したトークン要求、credential helper、`gh`の許可リストを、
  ローカルの偽APIで検証する。
- `src/tests/integration/test_agent_skills_layout.py`: 共用スキルのリンク、
  専用スキルの重複禁止、frontmatterを検証する。
- 導入後の動作確認では、App作成のPR、追加pushによる承認の無効化、
  Appによるマージの拒否を確認する。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 秘密鍵をエージェントが読める | App権限での任意操作 | 鍵をリポジトリ外に置き、Claude Codeの読取を禁止する。Appの権限を最小にし、`main`の更新を禁止する。必要に応じてエージェントを別ユーザーで動かす |
| rulesetの設定漏れや無効化 | 境界の消失 | JSONを`.github/rulesets/`でレビュー対象にし、導入後に動作確認する |
| Codexの`workspace-write`サンドボックスの挙動差 | 実装段階の失敗 | Claude Codeが毎回、独立に検証し、失敗したら停止する |

## Security / Privacy Impact

認証主体を、人間のトークンからGitHub Appのインストールトークンへ変更する。
秘密鍵は`~/.config/keiba-ai-agent/`に置き、リポジトリと出力には含めない。
トークンの有効期限は1時間、対象は本リポジトリ、`workflows`権限はない。

## Operational Impact

Appの作成とインストール、秘密鍵の保管、`app.json`とcredential helperの設定、
rulesetの適用、旧guardの撤去は、人間が一度だけ行う。
秘密鍵は定期的に作り直す。

## Migration / Rollback

### Migration

本ADRの変更をマージする。続いてrulesetを適用し、旧ブランチ保護を削除し、
Codexのユーザー層から旧guard(ルールファイル、guard store、`.git/codex-guard/`)を
撤去する。

### Rollback

ADR-016時点のコミットからguarded workflowを復元し、guardを再インストールして、
旧ブランチ保護を戻す。

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `AGENTS.md` / `CLAUDE.md`
- [x] `README.md`
- [x] `docs/rules/git-workflow.md`, `docs/rules/testing.md`,
      `docs/rules/agent-collaboration.md`

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-08 | Accepted | Claude CodeとCodexの役割分担、GitHub App、ruleset、スキル分割を採用し、ADR-001とADR-016を置き換え |
