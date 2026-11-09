# ADR-029: 計算した数値特徴量と結果時点をモデル入力へ接続する

- Status: Accepted
- Date: 2026-10-23
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: ADR-034（参考datamartの経路でのlabel_sources必須と読込時の再監査のみ。prepared JSONの経路は継続）

## Context

ユーザーは全21群の計算を先に実装し、厳格な時点証拠がそろってから実データ学習する方針を選択した。
ADR-028の計算結果からADR-027の学習へ渡す数値列と、学習結果を知った時刻の契約が必要である。

## Decision

models/datasetがコード上の閉じた数値列一覧と計算契約を所有する。群名で修飾した列をHydraで
明示選択し、文字列・真偽値・当該結果・任意数値列を承認しない。必要なlag列は設定上限までに限定する。
計算実装版、型と意味を検証したparameters（出典evidenceを除く）、順序付き選択列をcanonical JSONの
SHA-256で固定し、schema_idと各列の単位・欠損・生成規則を再検証する。

追加するmodel prepare-inputは正規化観測から全21群を計算した後、選択数値だけを純粋adapterで
既存FeatureInput JSONへ投影する。Noneは保持し、補完・除外・丸め・符号化は行わない。
全計算payload、元parameters/evidence、出典manifestも入力JSONへ保存する。
全21群の定義とID対応も保存し、読込時に共通監査を再実行して、計算値・全依存時計・
規則・選択されたモデル値と利用可能時刻の対応を再検証する。
結果は別の完全通常HistoricalRace入力から計算後に結合し、馬集合・時計・着順を検証する。
ラベル出典はrace単位label_sourcesとして元の証拠と対応馬集合を保持する。

計算契約を持つ学習ではlabel_sourcesを必須とする。分割後のtrain結果available_at最大値は
最初のholdout freezeより厳密に前でなければならない。その値label_known_throughとtrain結果出典、
保証区分をtraining.jsonとMLflowへ保存し、予測freezeは学習末freezeとlabel_known_through両方より後とする。
旧2列入力とnative format_version=3は維持する。旧入力/成果物の結果時点は未保証と明記し、
新計算契約の厳格経路へ代用しない。新計算列のartifactは旧コードでは読み込めない。

## Consequences

列順・単位・計算設定の違う入力を同じモデルへ誤接続することを防ぐ。宣言された証拠の検証は
原本との照合や過去受信の証明そのものではない。現存raw/Parquetの不足時計を推定しない。
実データ学習は証拠がそろうまで実行せず、合成入力による全経路の検証とは区別する。

## Validation

全21群の数値投影、JSON、実LightGBM、MLflow版登録、別processの厳密版予測を接続する。
旧形式互換、契約改変、許可外値、ラベル集合・時計、holdout/予測の同時刻境界、上書き拒否を検証する。
