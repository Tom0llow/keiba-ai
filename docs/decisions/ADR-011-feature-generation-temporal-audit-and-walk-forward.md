# ADR-011: 明示入力による特徴量生成・時点監査・Walk-forward

- Status: Accepted
- Date: 2026-10-06
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ADR-010で、モデルは処理済み特徴量と明示的な`FeatureSchema`だけを受け取り、欠損オッズ履歴を補完しない境界を決めた。モデルを実行可能にするには、特徴量の利用可能時刻を固定時刻と比較し、未来の値を拒否する処理と、レースを単位とした時間順評価が必要である。オッズ履歴など一部のデータは全期間で取得できないため、入力が欠損していても同じ処理を後日再実行できなければならない。

## Decision

1. `src/features/builder.py`は、`FeatureInput`として`race_id`、`horse_id`、timezone-awareな`freeze_at`、特徴量値、特徴量ごとの`available_at`、任意の確定着順を受け取る。raw SQLite、JV-Link、外部通信は呼び出さない。
2. 非欠損値には`available_at`を必須とし、`available_at > freeze_at`を監査違反として拒否する。欠損値は監査で件数を記録するが、時刻を要求せず、`None`/`NaN`のまま出力する。行の除外や別期間・最終オッズによる補完は行わない。
3. `FeatureSchema`の承認済みallow-listと列順を生成結果にも適用し、監査違反は`FeatureGenerationError`と構造化された違反一覧で返す。部分的な着順入力や、同じレースの非連続行は拒否する。
4. `src/models/walk_forward.py`は、各レースの共通`freeze_at`を時間順序として、train、validation、testをレース単位で分割する。初期学習レース数、validation/testレース数、stepを設定で固定し、同じレースの馬を複数区間へ分割しない。学習器へ渡すのはtrain区間だけとする。
5. `src/main.py`に`model audit`、`model features`、`model walk-forward`を追加する。入力と結果は、schema ID、feature names、時刻付きレコード、監査結果を含むUTF-8 JSONとする。入力JSONから外部取得やraw SQLite読取を暗黙に開始しない。
   欠損`NaN`はCLI出力で標準JSONの`null`へ変換し、入力契約違反は構造化エラーと終了コード1で返す。

## Consequences

### Positive

- 欠損オッズ履歴を保持したまま、利用可能性違反を学習前に検出できる。
- Walk-forwardの境界がレース単位で固定され、未来の行が学習へ混入しない。
- JSON CLIにより、同一入力を監査・特徴量生成・評価で再実行できる。
- スキーマ列が入力レコードから欠けている場合も、欠損件数を過少計上せず監査できる。

### Negative and follow-up

- 現在の特徴量生成は承認済みの数値入力を明示スキーマへ投影する境界であり、JRA-VAN各テーブルの業務コード解釈や過去成績集計は別途実装する。
- Walk-forwardは拡大型の単純なtrain/validation/test分割であり、nestedな特徴量・ハイパーパラメータ選定は別途実装する。
- 発走前の余裕時間、訂正履歴、取消・同着などの運用規則は別の監査契約として残る。

## Validation

特徴量生成、欠損保持、未来時刻拒否、timezone-aware制約、レース単位の分割、時系列順、学習区間限定、CLI JSON出力をpytestで検証する。既存のLambdaRank、Parquet、取得CLIのテストも全体検証で実行する。
