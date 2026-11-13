# ADR-038: top-3 PLの最終モデルを学習し、成果物として保存する

- Status: Accepted
- Date: 2026-11-12
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #52、Refs #57・#53・#54・#55・#35・#36・#48・#49
- Supersedes: ADR-035のDecision 3のうち「モデルは永続化しない」のみ
- Superseded by: N/A

---

## Context

ADR-035の`model evaluate-pl`は、年単位のfoldでtop-3 PLの学習・温度の推定・採点を行うが、学習したモデルを永続化しない。
当日の予測（#53）には、学習済みのモデルを一式で保存し、検証して読める成果物が必要である。

既存のLambdaRankの成果物（`models/artifacts/native_model.py`、format 3）は、objectiveとlabel_gainをLambdaRankの契約に固定して
検証し、MLflow（ADR-027）で版を管理する。PLはcallable objectiveで学習するので、この契約では保存できない。

[ADR-009](ADR-009-use-lambdarank-mvp-and-top3-pl-extension.md)は、PLをランキングの検証の後の拡張と位置付ける。
同じfoldでのLambdaRankとの比較（Validation 4）は#48に先送りされたまま（ADR-035 Decision 11）であり、連勝式の確率の採用には
券種ごとの確認（Validation 5）が必要である。

当日の予測の特徴量（ADR-036/037）は、ラベル（着順・`label_usable_after`）を持たない。一方、評価で使う`RaceArrays`はラベルを必須とする。
また、LightGBMは、欠損の扱いのない分岐（missing type `None`）で、予測の欠損を黙って0と同じ枝に入れる（2026-11-12に確かめた）。
欠損の扱いは、全行ではなく、ビンを作る標本（`bin_construct_sample_cnt`、既定20万行）から列ごとに決まる。そのため、学習で欠損の
なかった列だけでなく、欠損のまれな列も、この分岐になりうる。学習用datamartでは、市場の単勝オッズ列を含む4列が欠損を持たない。

---

## Decision

1. **testのない最終学習の分割。** `plan_final_fit`は、trainを`train_start_year`〜`valid_year − 1`、validを`valid_year`とする。
   - validの最初のfreeze以後に`label_usable_after`があるtrainのレースを除く（ADR-035と同じ厳密な比較）。testがないので、validは除かない。
   - モデルのラベルの利用境界`label_usable_through`は、trainとvalidの最大`label_usable_after`のうち大きい方とする。
     validのラベルもearly stoppingと温度に使うからである。
2. **最終学習の手順。** `train_final_pl`は、ADR-035のfoldと同じ`fit_native_pl_booster`と`calibrate_temperature`を使う。
   運用のモデルは、train 2006〜2024年・valid 2025年・variant`all_columns`（市場の単勝オッズ列を含む36列）で学習し、
   そのまま使う（validを含めて学習し直さない。温度を推定するデータがなくなるため）。LightGBMの引数・反復数・温度の範囲は、
   評価（`configs/pl_evaluation/measure.yaml`）と同じにする（`configs/pl_training/final.yaml`）。
3. **成果物`pl_top3_model` format_version 1。** 1つのディレクトリに、ちょうど`model.txt`と`manifest.json`を置く。
   - `model.txt`: LightGBMのnativeのテキスト。`best_iteration`までの木だけを保存する。callable objectiveのモデルは`objective`の行を持たない。
   - `manifest.json`: 入れ子のキーと型を固定する。キーの並びを固定したASCIIのJSONで、NaNを含まない。成果物の識別は、このバイト列のSHA-256で行う。
     - `model`: ファイル名・SHA-256・`objective`（`top3_plackett_luce`）・`best_iteration`・`best_valid_nll`・反復数・LightGBMの引数・
       LightGBMとnumpyのversion
     - `features`: 列順・variant・除いた列・列ごとの`nullable_in_training`
     - `temperature`: 値・範囲・validのraw/校正後のNLL・`at_bound`
     - `training`: 学習期間・レース数と馬数・除いたtrainのレース数・validの最初のfreeze・trainとvalidの最大・`label_usable_through`
       （時刻はUTCのISO 8601）
     - `source_datamart`: 予測の特徴量（ADR-036）と同じキー（`manifest_sha256`・`contract_sha256`・`target_period`・
       datamart全体の`label_usable_through`・`provenance_source_sha256`）と、閉じた数値列の定義
     - `provenance`（学習の前に取得する）と`config`（`datamart_path`を含めない）
   - 読込`read_pl_model`は、manifestのSHA-256・ファイルの集合・形式と入れ子のキー・定数・LightGBMの予約キー・反復数と温度の範囲・
     列とdatamartの定義の対応・時刻とラベルの境界の整合を検証する。さらに、`model.txt`のSHA-256を確かめたバイト列から
     boosterを読み、列名と反復数を照合する。
   - 書込みは、ファイルを書く前に、recordから作るmanifestを読込と同じ規則で検証してASCIIのJSONへ変換する。読込がmanifestを拒否するrecordでは、ディレクトリを空のまま残す。
     recordとboosterの反復数・列名の照合は、書いた成果物を読み直す呼出し側（CLI）が持つ。
     書込みの途中の失敗で残ったファイルの後始末と公開は、呼出し側（CLIのstaging）が持つ（#71）。
   - 書込みと読込は、`nullable_in_training`が真の列のすべての分岐が、欠損の枝（missing type `NaN`）を持つことを確かめる。
     満たさなければ拒否する（`bin_construct_sample_cnt`を学習の行数以上にして学習し直す）。
   - 実行中のLightGBMのversionが学習時と異なれば、読込を拒否する。依存を更新したら、モデルを学習し直す。
4. **ラベルなしの予測のAPI。** `PLModel`は次の関数を持つ。
   - `predict_scores(features, feature_names)`: 列名と列順の一致を要求する。学習で欠損のなかった列に欠損があれば、
     呼出し全体を拒否する（市場の単勝オッズ列が欠けたレースを除くか保留にするのは、呼出し側の#53である）。
     ±infを含む列があれば、欠損を許す列でも、列名を示して呼出し全体を拒否する（学習の入力も±infを拒否する。#71）。
   - 欠損の検査は、NaNをLightGBMの欠損として扱う既定の動作を前提とする。そのため、`use_missing`と`zero_as_missing`を
     PLの予約キーとする（評価の`evaluate-pl`にも同じく効く）。validの年に、trainで欠損のなかった列の欠損があれば学習を拒否する。
   - `probabilities(scores, group_sizes)`: 温度を掛けた勝率・2着以内・3着以内を返す。
   - `require_compatible_features(prediction_manifest)`: 予測の特徴量の`source_datamart`と列の定義が、モデルのものと一致することを要求する。
     `label_usable_through`は、タイムゾーン付きの時刻として比較する。
   - `require_prediction_after(freeze_at)`: freezeが`label_usable_through`より後であることを要求する。比較は、ADR-035と同じ
     厳密な`>`である（ADR-036の「以後」という書き方より厳しい）。
   - 予測の特徴量のParquetを行列へ変換する処理は、#53が持つ。
5. **CLI `model train-pl`。** `configs/pl_training/`の設定（`train.yaml`は全キー必須、`final.yaml`は運用の値）を読む。
   - 安い検査を全体の読込より先に行う。順序は、出力、設定、固定したmanifest、列とvariant、年、LightGBMの予約キー、出典である。
   - 全体の読込と学習の後、stagingに書いた成果物を読み直し、validのスコアが学習直後と一致することを確かめてから公開する。
6. **MLflowとの関係。** PLのモデルはMLflowで管理しない。manifestのSHA-256で固定するファイルの成果物とする。これは、
   ADR-027の「モデルの版をMLflowで管理する」に対する、人間が承認した意図した例外である（2026-11-12）。ADR-027は置き換えない。

---

## Rationale

- 評価と同じ関数で学習するので、評価の結果がそのまま運用のモデルに対応する。実データで、valid 2024年の最終学習が
  評価のtest 2025年のfoldと同じ`best_iteration`・NLL・温度を再現した（`docs/experiments/pl-final-model.md`）。
- manifestのSHA-256で固定する方式は、学習用datamart・予測の特徴量と同じであり、#53が1対1で照合できる。
- 欠損の拒否と、LightGBMのversionの一致は、予測が学習と同じ意味で計算されることを守る。

---

## Consequences

### Positive

- 当日の予測（#53）が、学習済みのPLモデルを検証して読み、ラベルなしで確率を出せる。
- 予測の特徴量とモデルが、同じ学習用datamartから作られたことを機械的に確かめられる。

### Negative

- 運用のモデルは2025年までのデータで学習しており、2026年のレースを学習していない。学習データの更新は#55で行う。
- PLを運用のモデルとするのは、ADR-009のValidation 4（LambdaRankとの同じfoldでの比較、#48）より前である。段階1の
  確率の提示（購入額0円）に限って使い、比較は#48で行う。単勝・連勝式の確率を購入判断に使うことは、ADR-009 Validation 5の
  券種ごとの確認（#49・#36）を経てから決める。
- 市場の単勝オッズ列が欠けたレースは予測できない。
- LightGBMを更新すると、成果物を読めなくなる（学習し直しが必要）。

### Neutral / Follow-on effects

- `models/artifacts/pl_model.py`は、`native_model.py`と同じく成果物の小さなバイトI/Oを自分で持ち、`data`をimportしない。

---

## Alternatives Considered

### Option A: validを含めて同じ反復数で学習し直す

Summary:

validで決めた反復数で、train+validを学習し直す。

Advantages:

- 直近の1年を学習に含められる。

Disadvantages:

- 温度を推定するデータがなくなる。評価のfoldの手順とも一致しなくなる。

Reason not selected:

人間の決定（2026-11-12）。

### Option B: MLflowへ登録する

Summary:

ADR-027と同じく、MLflowのrunとregistryでPLのモデルを管理する。

Advantages:

- LambdaRankと同じ管理の方式になる。

Disadvantages:

- 学習用datamart・予測の特徴量はSHA-256で固定しており、照合の方式が二重になる。実装の範囲も広がる。

Reason not selected:

人間の決定（2026-11-12）。

### Option C: 既存のLambdaRankの成果物（native format 3）を拡張する

Summary:

`native_model.py`に、PLのobjectiveを許す分岐を加える。

Advantages:

- 成果物の種類が増えない。

Disadvantages:

- LambdaRankの契約（objective・label_gain）の検証を弱める。温度・欠損・ラベルの境界・datamartとの結び付きを持たない。

Reason not selected:

既存の契約を変えずに、PLに必要な情報を持つため。

---

## Implementation Notes

- 分割: `models/evaluation/yearly_folds.py`（`plan_final_fit`）。
- 学習: `models/experiments/pl_training.py`（`PLTrainingSettings`・`train_final_pl`・`variant_columns`・`pl_model_record`）。
- 成果物: `models/artifacts/pl_model.py`（`write_pl_model`・`read_pl_model`・`PLModel`）。
- LightGBMの読込: `models/backends/lightgbm.py`（`load_pl_booster`、`model_str`で読む）。
- CLI: `cli/pl_training.py`、設定: `configuration/pl_training.py`・`configs/pl_training/`。

---

## Validation

- fixtureで、最終学習の結果が同じ分割で評価の関数を直接呼んだ結果と一致し、決定的であることを確かめる。
- 保存と読込の往復で、ラベルなしの行列からのスコアと確率が完全に一致することを確かめる。
- 読込が、manifest・ファイル・バイト列・versionの不整合を拒否することを確かめる。
- 予測が、列の不一致・学習で欠損のなかった列の欠損・結び付きの不一致・境界以前のfreezeを拒否することを確かめる。
- CLIの公開・検査の順序・失敗・中断・helpを確かめる。
- 実データで、評価のfoldの再現と、運用のモデルの学習を記録した。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 学習データが約1年古い | 2026年の傾向を学習していない | #55で学習データを更新する |
| 当日の市場の欠損 | そのレースを予測できない | #53で保留として示す |
| LightGBMのversionの変更 | 成果物を読めない | 依存の更新時に学習し直す |

---

## Security / Privacy Impact

セキュリティやプライバシーへの影響はない。成果物は認証情報も絶対パスも含まない。

---

## Operational Impact

- 運用のモデルは`model train-pl --config-name final`で学習する。datamartのパスとmanifestのSHA-256は`--override`で渡す。
- #53の予測は、成果物のmanifestのSHA-256で読む。

---

## Migration / Rollback

### Migration

既存の成果物・CLIは変わらない。

### Rollback

新しいCLIと成果物を使わなければよい。

---

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `docs/rules/architecture.md`
- [ ] `AGENTS.md`
- [x] `README.md`
- [x] APIとユーザー向けの文書（`docs/experiments/pl-final-model.md`）
- [ ] 運用文書・運用手順書（#54）

---

## Follow-up Actions

- [ ] 当日の予測のCLIで、このモデルを使う（#53）。
- [ ] 学習データの更新と再学習の手順を定める（#55）。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-12 | Accepted | top-3 PLの最終モデルの学習・成果物・ラベルなしの予測のAPIを決定。ADR-035のDecision 3の非永続化だけを置き換える |
| 2026-11-12 | Accepted | #71: `predict_scores`の±infの拒否と、書込みの前のmanifestの検証を追記。成果物の形式は変えない |
