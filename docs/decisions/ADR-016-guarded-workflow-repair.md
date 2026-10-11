# ADR-016: guarded workflow の引数保持と状態更新・終了経路

- Status: Accepted
- Date: 2026-10-11
- Decision Owners: Repository maintainers
- Supersedes: N/A（ADR-001 の信頼境界を維持し、運用経路を補足）
- Superseded by: N/A

## Context

Windows PowerShell 5.1 の外部コマンド呼び出しでは、引用符を含む引数が
変質し、既定の文字コードによって UTF-8 出力も変質する。コミット後の
メッセージ照合が失敗すると、保留状態の正しい再試行を完了できなくなる。
PR レビュー差分に対する `Trim()` は末尾の空白と改行を削除する。

厳密な最新状態を要求する保護設定に対して、タスクブランチを最新の
`origin/main` へ追従させる経路が不足していた。作成済み PR の説明更新、
draft 解除、人手でマージした PR のローカルタスク終了にも専用経路がない。
基準となる workflow 全体の成功だけでは、必須の `Quality` と `Test` が
対象 SHA で実行・成功したことを示せない。

通常のサンドボックスでは Store 版 PowerShell の実行エイリアスの起動が
エラー 5 で拒否された。また、現在の実行ツールは PowerShell の `-Command`
でコマンドを包むため、guard が要求する絶対パスと `-NoProfile -File` の
直接の引数列に一致しない。この二つはリポジトリのソース変更だけでは
解決できない。

## Decision

1. 外部実行は共通処理で Windows の引数を正確に渡し、標準出力・標準エラーを
   UTF-8 として取得する。文字列を PowerShell の評価対象へ連結しない。
   PR 本文は保護された `.git` 配下の一時 UTF-8 ファイルを `--body-file` で
   渡す。完全な差分は `RawOutput` を使って空白と改行を保持する。
2. 基準となる SHA の必須チェックは check-runs と commit-status API の証拠で
   確認する。`Quality` と `Test` の存在、成功、GitHub Actions の実行元を
   保護設定と照合する。
3. `update-task-base.ps1 -ExpectedHeadSha <更新前の完全な SHA>` で、タスクを
   検証済みの最新 `origin/main` へ追従させる。`merge-tree --write-tree` と
   `commit-tree` で作業ツリーと index を変更せずマージを準備し、更新前・
   更新先・結果の SHA を write-ahead 状態へ保存してから `merge --ff-only` で
   タスクブランチを進める。衝突時は作業ツリーと index を変更せず停止し、
   外部マージドライバーの設定がある場合も、実行前に停止する。
   人手へ引き継ぐ。中断時は同じ更新前 SHA で再実行する。
   `initialStartSha` に元の開始 SHA を残し、`startSha` は更新先の main へ進める。
   公開履歴の書き換えや force push は行わず、main の squash 方針も維持する。
   更新後の SHA に対してローカル検証、レビュー、push、CI、マージ準備を
   やり直す。以前の `MERGE_READY` とマージ試行記録を更新後の SHA へ流用しない。
4. PR の説明更新と draft 解除は `update-pr.ps1` に分離する。対象 PR 番号と
   明示された完全な HEAD SHA を操作の前後で検証し、以前のマージ準備と
   試行記録を更新前に無効化する。draft 解除は明示された `-Ready` のみで行う。
5. 人手でマージ済みのタスクは、確認を要求する `close-task.ps1` で終了する。
   PR 番号と完全な HEAD SHA、GitHub 側の `MERGED` と `mergedAt`、タスクの
   対応関係、保留操作がないことを確認する。タスク状態を SHA-256 で検証して
   退避し、write-ahead の終了記録を残す。この処理で Git の参照を変更したり、
   branch 削除、merge、push を実行したりしない。
6. ADR-001 の保護された導入先、ハッシュ検証、絶対パス、厳密な引数列、
   フック無効化、PR/SHA 単位のマージ承認を維持する。通常サンドボックスの
   起動と guard の直接呼び出しを導入後に別々に検証する。ポリシー判定の
   回帰テストだけで実行ツールとの統合成功を宣言しない。

## Rationale

外部実行時の変換を一箇所で制御することで、PowerShell 7 と 5.1 の差が
Git/GitHub の入力やレビュー証拠を変えないようにする。状態の更新と終了を
専用経路にすることで、信頼境界を迂回した手動編集や古い承認の流用を防ぐ。
人手のマージ終了を通常のマージ復旧から分離すれば、マージ試行記録のない
操作を既存の復旧許可として扱わずに済む。

## Consequences

- 新しいラッパーも保護された `main` から再導入し、Codex を再起動してから使う。
- PR の説明や draft 状態を更新した場合も、レビューとマージ準備を再実施する。
- 完了状態の退避ファイルと終了記録は、ローカルの監査・再試行証拠として残る。
- 既存の version 6 のタスク状態を読み取り可能に保ち、状態を更新する際に
  base 更新時に version 7 へ移行する。新しい main と導入済み guard のソースが一致しない
  場合は、ブランチ更新を停止して人手による再導入を求める。
- MSI 版 PowerShell の導入後も、実行ツールが直接の引数列を提供しなければ
  guarded 自律操作を開始できない。実行許可を広げる修正で回避しない。

## Validation / Follow-up

両 PowerShell と許可済み Codex CLI の組み合わせで、実際の引用符・空引数・
日本語・改行・末尾空白、必須チェック欠落、PR/SHA 不一致、draft 解除、
マージ済み状態の終了と再試行を回帰検証する。通常サンドボックスの起動と
正しい直接引数列による導入済み preflight の成功を、人手の導入後に確認する。

手動の導入・復旧手順は
[guarded workflow 修正の導入手順](../GUARDED_WORKFLOW_REPAIR.md)を参照する。
