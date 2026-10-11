# guarded workflow 修正の導入手順

今回のローカル修正は、引数・UTF-8 出力・レビュー差分の保持、基準 CI の
必須チェック確認、タスクブランチの更新、PR の更新、マージ済みタスクの
終了経路を対象とする。通常サンドボックスの PowerShell 起動と、Codex の
実行ツールが guard に渡す引数列は、以下の手動確認が必要である。

| 調査で確認した問題 | リポジトリ内の修正 | 導入時の対応 |
| --- | --- | --- |
| 通常サンドボックスの PowerShell 起動拒否 | ソース変更だけで根因を解消できない | MSI の導入と実際の起動先・起動成功を確認する |
| 実行ツールの `-Command` と guard の直接引数列の不一致 | guard の厳密な契約を維持する | 正しい引数列を提供する実行手段の統合確認が必要 |
| 5.1 での引用符欠落・UTF-8 出力変質 | 外部実行の引数と出力を共通処理で保持する | 両 PowerShell の実引数・日本語回帰を確認する |
| レビュー差分の末尾空白・改行消失 | 差分を `RawOutput` で取得する | 新しい guard を再導入する |
| main 進行後の `BEHIND` 停止 | `update-task-base.ps1` を追加する | 衝突時は人手で対応する |
| 既存 PR の説明更新・draft 解除経路不足 | `update-pr.ps1` を追加する | 更新後のレビュー・マージ準備をやり直す |
| 人手マージ後のタスク状態残留 | 確認を要求する `close-task.ps1` を追加する | 正確な PR/SHA を指定して終了する |
| PATH の別 Codex CLI による回帰検証 | 回帰コマンドで native 実体を明示する | マニフェストの CLI を固定して検証する |
| 基準 CI の必須チェック未確認 | 対象 SHA の必須名・成功・実行元を確認する | main の `Quality` と `Test` を確認する |
| 古い製品機能未実装という規約 | 実装済み CLI と各モジュール境界へ説明を更新する | 新しい規約を読み、実装済み構成を前提にする |
| 回帰テストと実行ツール統合確認の混同 | 導入後の統合確認手順を追加する | 第 6 節の二つの確認を完了する |

## 1. MSI 版 PowerShell を導入する

調査時には、通常サンドボックスで `Get-Location` の起動が
`CreateProcessAsUserW failed: 5` となり、起動先が
`AppData\Local\Microsoft\WindowsApps\pwsh.exe` だった。サンドボックス外の
同じコマンドは成功した。Store 版の実行エイリアスと制限付き起動の組み合わせが
原因候補だが、MSI 版への変更で解消するかは実環境で確認する必要がある。

Windows の通常のターミナルで MSI 版を導入する。Microsoft の
[PowerShell 導入資料](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows?view=powershell-7.6)
では、7.6 以降の WinGet の既定が MSIX になっているため、MSI を明示する。

```powershell
winget install --id Microsoft.PowerShell --source winget --installer-type wix
```

WinGet が既存導入を理由に MSI を追加できない場合は、上記の Microsoft 資料から
MSI を取得し、インストーラーで導入する。導入後、新しいターミナルで実体を確認する。

```powershell
$repairShellPath = Join-Path $env:ProgramFiles 'PowerShell\7\pwsh.exe'
Get-Item -LiteralPath $repairShellPath
& $repairShellPath -NoProfile -Command '$PSVersionTable.PSVersion; [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName'
Get-Command pwsh -All | Select-Object CommandType, Source
```

PowerShell 7.3 以上で、実体が通常の `Program Files\PowerShell\7` 配下にあることを
確認する。コマンド探索が Store 版を先に選ぶ場合は、Windows の環境変数設定で
MSI のディレクトリが先に探索されるよう PATH を調整して、新しいターミナルで
再確認する。WindowsApps の所有者・ACL やサンドボックス全体の権限は変更しない。

## 2. Codex の通常サンドボックスを確認する

Codex を完全に終了し、再起動する。通常のサンドボックスで次を実行し、
成功結果と実際に起動した PowerShell のパスを確認する。

```powershell
Get-Location
[System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
```

`exec_command` の `shell` 指定だけで実体が変更されると仮定しない。
今回の実環境では絶対パスを指定しても WindowsApps のエイリアスが起動された。
MSI 導入後も同じエラーが続く場合は、Codex の実際の起動パスと sandbox 実装を
確認する。未確認の `config.toml` キーを追加しない。

OpenAI の[Windows sandbox 資料](https://learn.chatgpt.com/docs/windows/windows-sandbox)に
従い、解消しない場合は Windows build、Codex の版、選択された sandbox 実装、
エラーと実際の起動コマンドを添えて診断する。ログを共有する際は必要なエラー周辺を
選び、秘密情報を除く。認証設定と `.sandbox-secrets` は共有しない。

## 3. 修正を人手でレビューし、保護された main へ反映する

今回の変更には guard 自身の信頼境界が含まれる。自律タスクで guard のソースを
変更したり、そのソースを host 側の実行許可対象にしたりしてはならない。
今回明示されたローカル修正・commit の許可を、今後の一般的な迂回許可へ広げない。

ローカル commit を確認した後、人手の通常ターミナルで現在のブランチを確認する。
ブランチ名が `bugfix/guarded-workflow` で、未コミット変更がないことを確認してから
push する。作業中の別の変更がある場合はその変更を保持し、以下の操作を続けない。

```powershell
git status --short --branch
git log -1 --oneline
git push origin bugfix/guarded-workflow
```

GitHub の画面で `bugfix/guarded-workflow` から `main` への PR を作成し、変更全体を
レビューする。`Quality` と `Test` の成功、許可された各 Codex CLI と
PowerShell 7 / Windows PowerShell 5.1 の回帰検証成功を確認する。
保護設定を維持したまま人手で squash merge する。

マージ後、通常ターミナルで clean な `main` を更新する。

```powershell
git status --short --branch
git switch main
git pull --ff-only origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

最後の二つの SHA が一致し、未コミット変更がないことを確認する。既存の変更や
履歴の相違で停止した場合は、reset、強制更新、変更破棄を行わず原因を確認する。

## 4. Codex CLI の実体を固定して回帰検証する

以下はリポジトリ直下で人手が実行する。既存の呼び出しメタデータは秘密情報を
含まない。PATH で見つかるアプリ版や Node launcher shim の `codex` を選ばず、
既存 guard が固定した native `codex.exe` を明示する。

```powershell
$repairInvocation = Get-Content -LiteralPath .git/codex-guard/guard-invocation.json -Raw | ConvertFrom-Json
$repairCodexPath = [string]$repairInvocation.codexPath
$repairShellPath = Join-Path $env:ProgramFiles 'PowerShell\7\pwsh.exe'
$repairLegacyShellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$repairRegressionPath = Join-Path (Get-Location).Path 'scripts\guard-tests\guard-regression.ps1'
& $repairShellPath -NoProfile -File $repairRegressionPath -CodexExecutablePath $repairCodexPath
& $repairLegacyShellPath -NoProfile -File $repairRegressionPath -CodexExecutablePath $repairCodexPath
```

調査時のマニフェストは Codex CLI `0.151.0` を固定していた。実体がない場合や
版が変わった場合は、許可版一覧 `scripts/guard-tests/codex-cli-version.txt` に
一致する self-contained native 実体を人手で用意する。CLI の最新版へ置き換える
だけで回帰成功と扱わない。上記のローカル検証は指定した一つの CLI 版の検証であり、
全許可版の組み合わせは CI で確認する。ポリシー評価を省略して通さない。

## 5. clean な main から guard を再導入する

全検証とレビューが完了した clean な `main` で、導入スクリプトを人手で実行する。
これにより MSI 版 PowerShell の実体と承認済み Codex CLI が新しいマニフェストへ
記録される。通常の自律操作に tracked な `scripts/agent/` を直接使わない。

```powershell
$repairInstallerPath = Join-Path (Get-Location).Path 'scripts\setup\install-guarded-wrappers.ps1'
& $repairShellPath -NoProfile -File $repairInstallerPath -CodexExecutablePath $repairCodexPath
```

導入が active task の存在などで停止したら、タスク状態を削除して進めない。
対象 PR・SHA の状態を確認し、対応する正式な終了・復旧経路を使う。
導入後、以下のメタデータを確認して Codex を再起動する。

```powershell
$repairInvocation = Get-Content -LiteralPath .git/codex-guard/guard-invocation.json -Raw | ConvertFrom-Json
$repairInvocation | Select-Object sourceSha, shellPath, codexPath, codexVersion, guardRoot, policyPath
$repairInvocation.scripts
```

`sourceSha` がレビュー済みの `main`、`shellPath` が MSI の実体であること、新しい
ラッパーが `scripts` に含まれることを確認する。導入先ファイルや user-layer policy を
手で書き換えない。パスまたは CLI 版の変更時には再導入と Codex 再起動が必要になる。

## 6. 人手の preflight と実行ツールの統合を別々に確認する

まず、通常ターミナルで導入済み preflight の正しい実体を確認する。

```powershell
$repairPreflightPath = [string]$repairInvocation.scripts.'scripts/agent/github-preflight.ps1'
& $repairInvocation.shellPath -NoProfile -File $repairPreflightPath
```

その後、Codex の実行ツールで、メタデータの絶対パスを評価せず読み取り、
以下の各要素を直接の引数として渡せることを確認する。

```text
ABSOLUTE_SHELL_PATH -NoProfile -File ABSOLUTE_GITHUB_PREFLIGHT_PATH
```

実際の `argv[0]` が `shellPath`、以降が `-NoProfile`、`-File`、記録された
preflight の絶対パスである必要がある。相対パス、`-Command` 内の `&` 呼び出し、
シェル変数、別の launcher による包み込みは代用にならない。

現在の会話で使われた `exec_command` は `-Command` で包むため、厳密な契約を
満たしていない。この場合、guard の allow rule を広げず、正しい引数列を
提供する実行手段が利用可能になるまで、自律の Git/GitHub 操作は開始しない。
人手の preflight 成功や `codex execpolicy check` の成功だけを、Codex からの
起動成功と混同しない。

通常サンドボックスでは、環境同期と Python の確認も実施する。

```powershell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

## 7. main 進行後のブランチ更新

タスク作成後に `main` が進んだ場合は、導入済みの `update-task-base.ps1` に
更新前の完全な HEAD SHA を `-ExpectedHeadSha` として渡す。衝突のないマージを
作業ツリーと index の外で準備し、状態を記録してからタスクブランチを進める。
中断時は同じ更新前 SHA で同じラッパーを再実行する。

衝突がある場合は作業ツリーと index を変更せず停止するため、人手で差分を
確認して対応する。別の自律コマンドで rebase、reset、force push を実行して
続行しない。導入済み guard と最新 main のソースが不一致なら、先に人手で
guard を再導入する。

更新後の新しい HEAD SHA で検証、レビュー、push、CI、マージ準備をやり直す。
更新前 SHA の承認・成功結果を再利用しない。

## 8. PR の更新と人手マージ後の終了

再導入後、PR のタイトル・本文の更新や draft 解除には、導入済みの
`update-pr.ps1` を使う。`-PrNumber` と `-ExpectedHeadSha` を必ず指定し、
本文更新は `-Body`、draft 解除は明示された `-Ready` で行う。更新後は
マージ準備の証拠が無効になるため、レビューと readiness を再実施する。
`create-pr.ps1` の再実行は説明更新の代用にしない。

人手でマージした PR のローカルタスクを終了する際は、導入済みの
`close-task.ps1` に同じ PR 番号とマージ対象 HEAD SHA を指定し、確認して実行する。
この経路は GitHub 側のマージ済み状態を確認してタスクファイルを退避する。
ブランチや Git 参照は変更しない。同じ PR/SHA での再実行は、終了記録と退避ファイルの
一致を検証する。マージ済み SHA が不明な場合は状態ファイルを削除せず確認する。

通常の `merge-task.ps1` によるマージ復旧は、既存のマージ試行記録と完全な
PR/SHA の一致がある場合に限る。人手マージをこの復旧経路の承認へ読み替えない。
