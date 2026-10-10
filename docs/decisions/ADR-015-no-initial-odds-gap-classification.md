# ADR-015: 初回台帳作成時のオッズ欠損未判定

- Status: Accepted
- Date: 2026-10-10
- Decision Owners: Repository maintainers
- Supersedes: ADR-013の初回欠損フロンティア分類
- Superseded by: N/A

## Context

`historical-odds`の初回台帳作成時に、アーカイブ行がない組を設定した
レースキーまで`provider_missing`へ分類すると、アーカイブの欠損を提供元の
欠損と推測することになる。`accept_existing_gaps_through`はこの推測を設定へ
持ち込むため、取得対象の判断と提供元欠損の確認を混同していた。

## Decision

1. `historical_odds.batch`は`first_year`、`last_year`、`years_per_run`だけを
   固定方針として持ち、`accept_existing_gaps_through`は削除する。
2. 初回スナップショットでアーカイブ行を観測できた組は`acquired`、行がない組は
   `pending/unrequested`として台帳へ登録する。初期状態だけでは
   `provider_missing`にしない。
3. `provider_missing`は、対象を実際に取得してJVOpen/JVRTOpenの正常な`-1`と
   有効な空RT表を確認した場合、または既存の明示確認コマンドを実行した場合だけ
   記録する。
4. 最古の未完了年を選び、1年の取得が完了したら同じ起動中に次年へ進む既存の
   台帳・派生設定・Parquet公開フローは維持する。新しい候補や別モードで追加された
   アーカイブ行は、次回の照合で`pending`または`acquired`として取り込む。

## Rationale

初回の観測結果と、提供元へ問い合わせた結果を分離することで、欠損の原因を
推測せずに再取得対象を保持できる。取得済みの継続判定は台帳の状態と完全な
`RaceKey`・DataSpecで行うため、既存の年単位の自動継続と再実行の性質を失わない。

## Consequences

- 初回実行では既存アーカイブに行がない組も取得対象となり、過去年を含む取得時間が増える。
- 初回台帳のpolicy hashは変わるが、旧フロンティア設定で作成したruntime台帳は、
  raw SQLiteと旧policy hashを検証した一度限りの移行で欠損を`pending`へ戻せる。
  それ以外のpolicy差分や不整合は自動移行せず停止する。
- `provider_missing`の件数は初期集計ではなく、実取得結果または明示確認の証跡に基づく。

## Alternatives Considered

- 既存フロンティアを残す案は、欠損原因を設定値から推測するため採用しない。
- 初回欠損を全て`provider_missing`へ変更する案は、同じ問題をより広い範囲で固定するため採用しない。

## Validation / Follow-up

一時SQLiteの初回台帳テストで、既存行が`acquired`、行なしが`pending`になること、
旧パラメータを設定へ追加すると拒否されること、既存の年継続・正常な空応答・明示確認の
テストが継続して通ることを確認する。旧フロンティア台帳はraw SQLiteを変更せずに
移行され、変換された初期欠損が再取得対象になることも確認する。
