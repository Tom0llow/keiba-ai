# ADR-003: レースデータベースの表をParquetとしてエクスポートする

- Status: Superseded
- Date: 2026-10-01
- Decision Owners: Repository maintainers
- Related Issues/PRs: N/A
- Supersedes: N/A
- Superseded by: ADR-008

## Context

ユーザーは、`data/raw/race.db`のすべての表を、設定したパスと共通のローダーを使って、
`data/processed/`配下でParquetとして利用できることを求めている。入力元は約18.8 GBのSQLite
データベースで、35の表と6,387の宣言済みの列を持つ。既存のリポジトリには、製品コード、設定、
データパイプラインがない。そのデータアセスメントでは、項目の定義と品質規則がまだ承認されて
いないことがわかった。いくつかの日付風の値は仮置きの値であるため、エクスポートの際に解析や
クリーニングを行うと、その意味が変わる可能性がある。

## Decision

この決定は当初、形式を保持して表ごとに1ファイルとするParquetのエクスポートと、共通のローダーを
選んだ。また、既存のprocessedディレクトリの置換をエクスポーターが拒否することも求めていた。

ADR-008は、ここで定めた公開とモジュールの境界を置き換える。形式保持の原則は引き続き有効だが、
繰り返し行うhistorical、latest、realtimeの取得は、現在は前処理層を通じて版管理されたprocessedデータを
公開し、ローダーはParquetだけを読む。

## Rationale

Parquetは、要求されたprocessedの形式である。ストリーミングにより、大きな入力元でもメモリの
使用量に上限を保てる。文字列を保持すると、文書化されていない値にドメイン上の意味を割り当てずに
済む。設定により、マシン固有のパスをコードの外に置ける。

## Consequences

有効な前処理、snapshot、realtimeの公開、読込の契約は、ADR-008を参照する。

## Alternatives Considered

- Parquetを書き込む前に表全体をpandasへ読み込むと、別の依存関係が必要となり、メモリを使い
  果たすおそれがある。
- `data/processed/`へ直接ファイルを書き込むと、変換に失敗したときに、不完全なデータセットが
  見えてしまう。
- 日付風や数値のテキストを解析すると、承認されていないデータ規則を持ち込み、空白や仮置きの値を
  変えてしまう可能性がある。

## Validation / Follow-up

有効な検証の要件は、ADR-008で定める。

## Security / Privacy Impact

この決定では、ネットワークサービスも資格情報も導入していない。

## Operational Impact

ADR-008で置き換えた。

## Migration / Rollback

ADR-008で置き換えた。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-10-01 | Accepted | 要求されたレースデータのために、形式を保持するParquetのエクスポートを導入 |
| 2026-10-04 | Superseded | 繰り返し行う前処理とrealtimeの前処理のために、ADR-008で置き換え |
