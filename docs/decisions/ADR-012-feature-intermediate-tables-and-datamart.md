# ADR-012: 特徴量単位の中間テーブルとdatamart結合

- Status: Accepted
- Date: 2026-10-06
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

特徴量が一つのbuilderへ集中すると、前レース結果、オッズ比率、血統のように
生成規則・欠損・利用可能時刻が異なる責務を同じ変更単位で扱うことになる。
また、全特徴量を一度に生成してから保存すると、個別特徴量の再計算と検証が
難しくなる。raw SQLiteやJV-Linkの取得境界を特徴量コードへ広げず、取得できて
いないオッズ履歴も欠損のまま後日再生成できる中間成果物の境界が必要である。

## Decision

1. `src/features/`では特徴量ごとにモジュールを分ける。各モジュールはraw SQLite、
   JV-Link、外部通信を直接参照せず、正規化済みの明示入力を受けて一つの
   `IntermediateFeatureTable`を返す。
2. 中間テーブルは`race_id`、`horse_id`、`freeze_at`、`available_at`と、その
   特徴量に固有の値列を持つ。キーは同一テーブル内で一意とし、同じキーの
   `freeze_at`は一つに固定する。時刻はUTC timezone付きのArrow timestampとして
   保存し、値が欠損の場合はNULLのまま保存し、補完・行削除を行わない。
3. 中間テーブルは呼び出し元が明示したParquetパスへ保存・再読込する。保存形式の
   feature名と列契約を検証し、入力成果物を上書きしない責務は呼び出し側で管理する。
4. `src/make_datamart/`は保存済み中間テーブルを読み込み、最初のテーブルの
   `(race_id, horse_id)`と行順を基準にleft joinする。余分なキー、重複キー、
   `freeze_at`不一致、列名衝突は失敗させる。各特徴量の`available_at`は
   `<feature_name>__available_at`へ改名して結合後も時点監査可能にする。
   datamart保存時もfeature名から列順・型・時点・欠損契約を再検証する。
5. 現時点では前レース結果、オッズ比率、血統の中間生成を実装する。血統識別子は
   未承認のカテゴリ符号化を行わず文字列列として保持し、モデルの数値FeatureSchemaへ
   自動投入しない。オッズ履歴の欠損は`None`または`NaN`入力をNULLとして保存する。

## Consequences

### Positive

- 特徴量ごとに規則・テスト・再計算単位を分離できる。
- 中間Parquetを個別に検査・再利用でき、datamartの結合結果を再現できる。
- 未取得期間のオッズ履歴を無理に補完せず、データ取得後に同じ処理を再実行できる。

### Negative and follow-up

- 中間テーブルの生成元であるraw列の業務コード解釈、受信時刻の完全な復元、
  履歴集計の採用規則は別途確定する必要がある。
- 血統のカテゴリ辞書・未知値方策と、モデルへ投入する数値化は未実装である。
- 中間ファイルのライフサイクル、保持期間、共有ディレクトリは呼び出し側の
  データ実行計画で決定する。

## Validation

特徴量ごとの値変換、欠損保持、Parquet round-trip、キー重複・余分キー・時点不一致の
拒否、基準テーブルの行順を保ったleft joinをpytestで検証する。
