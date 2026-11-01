# 計算結果を学習・予測入力へ接続する

`model prepare-input`は証跡付き正規化観測から全21群を計算し、Hydraで明示した承認済み数値列を
モデル入力JSONへ投影する。計算後に、別ファイルの完全通常結果を学習ラベルとして結合できる。
予測では`--results`を省く。出力は新規ファイルへ排他的に作成し、既存ファイルとリンクを拒否する。

```powershell
uv run python src/main.py model prepare-input --input output/inputs/normalized.json --results output/inputs/results.json --output output/inputs/training.json --config-dir output/projection-config
uv run python src/main.py model train --override "data.input=output/inputs/training.json"
uv run python src/main.py model prepare-input --input output/inputs/latest-normalized.json --output output/inputs/prediction.json --config-dir output/projection-config
uv run python src/main.py model predict --override "data.input=output/inputs/prediction.json" --override "model.version=1" --override "data.selection=latest_date"
```

`output/projection-config/prepare.yaml`は`configs/model_projection/prepare.yaml`を元に、
`parameters`へ[計算設定](feature-calculation.md)の全項目とその選定証跡を指定し、
`selected_columns`へ順序付きの列名を必ず指定する。例として距離と過去出走数を明示する場合は次になる。
この例は列名の記述方法であり、運用での採用列や学習設定の推奨値ではない。

```yaml
parameters:
  # configs/feature_calculation/calculate.yaml の全項目を明示する。
selected_columns:
  - basic_conditions_and_weight__race_distance_m
  - history_volume_and_missingness__past_observed_start_count
```

コード上の[数値列解決器](../src/models/dataset/calculated.py)が承認するexact列だけを使える。
全21群に代表数値列を用意するが、自動採用は行わない。群名と列名は`__`で結び、
許可したlag系列だけを正整数かつ`lag_count`以下として解決する。先頭ゼロのlag、任意列、
当該結果、文字列・真偽値を拒否し、カテゴリ符号化は行わない。
選択値が正当に`None`なら保持し、欠損した列そのものはエラーとする。補完・除外・丸めは行わない。

計算契約は固定実装版、型と意味を検証した設定、選択列の順序をcanonical JSONのSHA-256で固定する。
設定内の`evidence`は意味上の設定から除き、元の計算payloadへ保持する。freeze時刻や原観測の
版が変わっても計算方法が同じならschemaは変わらない。計算方法・列順・単位・生成規則が異なる
入力や成果物は読み込まない。prepared JSONには全計算値・元parameters・欠損理由・依存manifestを
保持し、MLflowへ記録する入力ファイルhashでその一式を識別する。
全21群の定義を`calculation.feature_definitions`へ明示し、設定で変更した群IDも保持する。
読込時に計算値の共通監査を再実行し、モデル行とのレース・馬・freeze・選択値、規則IDと設定、
全依存の時計と群・列の最大利用可能時刻を照合する。保存された監査の`valid`だけで受理しない。

結果入力は`{"schema_version":1,"results":[...]}`で、各要素は
`HistoricalRace`（[正規化型](../src/make_features/contracts/observations.py)）の全項目を持つ。
結果の出典時計を検証し、結果事象が開始より後、特徴量freezeが開始より前であることを要求する。
完全通常結果、レースと馬集合の一致、一意連続着順を検証する。例外・不完全レースを黙って落とさない。
出力の`label_sources`は原結果と原観測ID・版・hash・発表/受信/事象時計・対応馬集合を保存する。

計算契約のある学習入力は全ラベルの出典を必須とする。時系列分割後、学習側の結果available_at
（発表と実受信の遅い方）の最大値`label_known_through`が、最初のholdout freezeより厳密に前で
なければ学習を拒否する。同時刻も拒否する。holdout結果は評価用なのでこの制約は課さない。
`training.json`とMLflowへ学習結果出典、`label_known_through`、保証区分を記録する。
そのモデルを使う予測freezeは、学習末freezeと`label_known_through`の両方より後でなければならない。
計算契約付き入力は旧`model walk-forward`では受け付けず、結果出典と利用時点を監査する
`model train`を使う。計算契約のない既存2列入力のwalk-forwardは維持する。

旧`ability`/`historical_odds`入力と既存native format_version=3は引き続き読める。
旧入力や旧登録成果物は`legacy_label_time_unverified`として結果時点が未保証であることを示す。
新しい計算契約の厳格経路を旧入力へ置き換えない。新計算列もnative形式番号は3だが、
拡張schemaを持つため旧コードでは読めない。

保証区分`declared_timestamp_evidence_not_external_certification`は、渡された宣言の整合性を
検証したことを示す。外部原本との照合や、過去受信証拠の真正性を認証するものではない。
現存raw/Parquetの不足時刻は推定せず、証拠がそろうまで実データ学習・最新予測を開始しない。
合成fixtureによる実LightGBM・MLflow・別process予測の成功は、実データの学習実績ではない。
判断は[ADR-029](decisions/ADR-029-project-calculated-features-into-strict-model-inputs.md)に記録する。
