# ADR-051: 計算済みの出走表・過去成績の列を閉じた数値列の末尾に加え、年次の作り直しで採否を決める

- Status: Accepted
- Date: 2026-11-26
- Decision Owners: Repository maintainers
- Related Issues/PRs: Refs #83・#57
- Supersedes: N/A（[ADR-043](ADR-043-fix-an-expected-value-win-and-place-policy-and-backtest-graded-races.md)の決定1と[ADR-038](ADR-038-train-and-persist-the-final-top3-pl-model.md)の決定2の「variant`all_columns`」を、同じ列・同じ順の`without_added_columns`と読み替える。決定4）
- Superseded by: N/A

---

## Context

2026-11-15に、運用中のtop-3 PL（`all_columns`、36列）のtest 2016〜2025年の予測と固定snapshotを結合したところ、馬単位の偏りが見つかった（#83）。ダートの短距離で内枠の勝ちが少なく外枠が多い、6歳以上の勝ちが少ない、前走を大差で勝った馬の勝ちが多い、などである。

これらを説明しうる値は、全21群の計算（[ADR-028](ADR-028-calculate-all-feature-groups-from-timestamped-observations.md)）で既に計算している。基本条件の群の枠番（`gate_number`）・頭数（`frozen_field_size`）・馬齢（`horse_age_years`）、近走成績の群の3着内率（`past_top3_rate`）、過去の走力の群の符号付き着差（`past_signed_gap_sec_lag{k}`）である。しかし、モデルへ渡す列は`models/dataset/calculated.py`の閉じた数値列（[ADR-029](ADR-029-project-calculated-features-into-strict-model-inputs.md)）に限られ、これらは入っていなかった。

閉じた数値列は計算契約の`selected_columns`とそのSHA-256になり、学習用datamart（[ADR-034](ADR-034-build-full-period-reference-feature-datamart.md)）の列、PLモデルの入力列の候補、当日の特徴量の列を決める。読込は、計算契約の列がコードの閉じた数値列と一致しなければ拒否する。したがって、列を変えると、それまでの学習用datamartは新しいコードの特徴量の常駐CLI・`model evaluate-pl`・`model train-pl`で読めない（[ADR-048](ADR-048-rebuild-and-retrain-once-a-year-after-the-last-race-day.md)の決定9が想定した変更）。

偏りの検証では、test 2016〜2025年を仮説の選定に使った。同じ期間の評価で採否を決めると、選択の偏りが入る。2026年の結果は、年末の作り直し（ADR-048、2006〜2026年のdatamartとtest 2016〜2026年の評価）で初めて得られる。

馬番（`horse_number`）も偏りの区分に使ったが、計算器は0埋めの文字列（例`"05"`）として出しており、閉じた数値列には文字列を承認しない（ADR-029）。

---

## Decision

1. **加える列と順序**: 閉じた数値列の既存の36列（名前・順序・意味・単位）を変えず、その後に次の8列をこの順で加える（運用の`lag_count`=4で36列から44列）。
   - `basic_conditions_and_weight__gate_number`（freeze時点の枠番、単位`ordinal`）
   - `basic_conditions_and_weight__frozen_field_size`（freeze時点の出馬表の頭数、単位`count`）
   - `basic_conditions_and_weight__horse_age_years`（freeze時点の馬齢、単位`years`）
   - `recent_performance__past_top3_rate`（`past_win_rate`と同じ直近の出走の3着内率、単位`fraction`）
   - `past_racing_ability__past_signed_gap_sec_lag1`〜`lag{lag_count}`（k走前の符号付き着差。勝ち馬は2着との差を負で持つ。単位`seconds`）

   計算器・計算式・計算実装版・`configs/features.toml`・datamartとmanifestの形式・投影のコードは変えない。lagの範囲は既存のlagの系列と同じく`lag_count`以下とする。
2. **馬番は加えない**: 計算器の出力が文字列であり、閉じた数値列は文字列の承認・符号化をしない（ADR-029）。内外の位置は枠番と頭数で表す。
3. **評価のvariant**: `configs/pl_evaluation/measure.yaml`のvariantを次の7つにする。`all_columns`（44列）、`without_market`（市場の単勝オッズ列を除く）、`without_added_columns`（加えた8列を除く。元の36列と同じ列・同じ順）、加えた列の群を1つずつ除く`without_post_position`（枠番・頭数）・`without_horse_age`・`without_signed_gap`（着差の4列）・`without_top3_rate`。除外は列の順を変えないので、`without_added_columns`の入力は変更前の`all_columns`と同じである。
4. **採否まで運用の既定は元の36列**: `configs/betting_backtest/measure.yaml`の`pl_variant`と`configs/pl_training/final.yaml`の`variant`を`without_added_columns`にする。ADR-043決定1とADR-038決定2の`all_columns`（36列）は、この名前に読み替える。列と順が同じなので、ADR-043〜045の計測と最終学習の入力は変わらない。`configs/betting_backtest/measure.yaml`の「計測の後に値を変えない」という注記は、方策・補正・推定の値に限るよう書き直す（ADR-048決定7が初回の作り直し後のPRで予定していた書き直しを、ここで行う）。
5. **採否は年末の作り直しで人間が決める**: 2027年向けの作り直し（ADR-048）の評価の後、test年2026を含む結果で`all_columns`と`without_added_columns`を比べ、人間が加えた列を運用で使うかを決める。使うときは、バックテストと最終学習の`--override`で`all_columns`へ切り替え、作り直し後のPR（ADR-048決定7）で既定を変える。2016〜2025年の結果だけでは決めない。
6. **variantの一致を購入案の起動時に確かめる**: `model propose-bets-live`は、推定器を計測したPLの評価のvariant（`sources.pl_evaluation.variant`）とPLモデルのvariant（`features.variant`）の名前が違えば、出力を作らずに起動を拒否する。推定器は列を記録していないので、名前だけを比べる。
7. **マージと切替の時期**: この変更のコードは36列の学習用datamartを拒否するので、変更のPRは2027年向けの切替の夜にマージする。2027年向けの作り直しは、ADR-048決定9の別checkoutの手順（このブランチのworktreeで、運用のcheckoutの`data/processed`と`output/`を絶対パスで指定する）で行う。このブランチのコードは切替の夜まで当日の運用のcheckoutに入れない（PRのマージ前に、運用のcheckoutでmainを`git pull`するのは差し支えない）。作り直しの前にこのブランチへmainを取り込み、マージの前にmainが進んでいたらもう一度取り込む（rulesetが最新のブランチと最後のpushへの承認を求める）。進んだ変更が特徴量・datamart・学習・予測のコードに関わるなら、作り直す（読込は記録された計算契約を照合するが、動いているコードとの違いは検出しない）。

---

## Rationale

- 列を末尾に加えることで、加えた列を除くvariantが、既存のモデルと同じ列・同じ順の入力になる。採否の比較の基準を新しいdatamartの中で作れ、ADR-043〜045の計測も変わらない。
- 列群ごとのleave-one-outで、どの群が効くかを同じ評価で見られる。ただし、枠番と頭数、3着内率と勝率・着順のlagは互いに似た情報を持つため、1群を除いた差は寄与を小さく見せうる。
- 既定を元の36列にすれば、採否を決める前に運用のモデルが黙って変わらない。
- 採否に2026年を含めることで、仮説の選定に使った期間だけで決める偏りを避ける。
- 文字列の馬番を数値へ変える仕組みを足すより、既に数値の枠番と頭数で位置を表す方が、閉じた数値列の規則（ADR-029）を保てる。

---

## Consequences

### Positive

- Issue #83の偏りに関わる計算済みの値を、評価と最終学習で使える。
- 1回の評価で、加えた列の有無と群ごとの寄与を比べられる。
- 推定器とPLモデルのvariantの取り違えを、購入案の起動時に検出できる。

### Negative

- 評価のvariantが2つから7つになり、評価の時間とピークメモリが増え、年末の作り直しの短い期間を圧迫する。
- 変更のPRを年末までマージできず、その間のmainの変更との衝突を解く必要がある。
- variant名`all_columns`の列が、2026年までの記録（36列）と以後（44列）で違う。前年との比較の相手は`without_added_columns`になる。
- variantの一致の確認は名前だけで、同じ名前で列の違う組み合わせは検出しない。

### Neutral / Follow-on effects

- 採否の結果によって、作り直し後のPRで既定のvariantと、群ごとのvariantを残すかを決める。
- 馬番を数値で使うには、計算器の出力を変える別の判断が要る。

---

## Alternatives Considered

### Option A: 36列のdatamartも読めるように、計算契約に版を持たせる

Summary: 読込が「元の36列」と「44列」の両方の契約を受け入れ、当日の特徴量は固定したdatamartの列で作る。

Advantages: すぐにマージでき、切り戻しも同じコードでできる。

Disadvantages: 閉じた数値列の契約に版の概念が増え、構築・読込・当日の特徴量の各経路とテストが大きくなる。

Reason not selected: 年1回の作り直しに合わせてマージすれば、ADR-048決定9の手順で足りるため（人間の決定、2026-11-26）。

### Option B: 馬番を投影で整数へ変える、または計算器に数値の馬番を足す

Summary: 偏りを測った変数そのものをモデルに入れる。

Advantages: 内外の位置を直接表す。

Disadvantages: 前者は閉じた数値列に文字列の変換を持ち込み（ADR-029の例外）、後者は21群の計算の出力を変える。

Reason not selected: 枠番と頭数で位置を表せ、変更が小さいため（人間の決定、2026-11-26）。

### Option C: 既定をすぐ44列にする

Summary: 加えた列を既定で使い、効かなければ36列へ戻す。

Advantages: 作り直しの手順で`--override`が要らない。

Disadvantages: 採否を決める前に運用のモデルが変わる。

Reason not selected: 採否は2026年の結果を見て人間が決めるため（人間の決定、2026-11-26）。

---

## Implementation Notes

閉じた数値列は`src/models/dataset/calculated.py`の既存の列の後に連結する。運用の設定と閉じた数値列の対応は`src/tests/integration/test_pl_variant_configs.py`が、元の36列の名前と定義は`src/tests/closed_column_fixtures.py`が固定する。variantの一致の確認は`src/cli/pl_prediction.py`にある。

---

## Validation

- 閉じた数値列の先頭36列が変更前と同じで、末尾が上の8列であることをテストで確かめる。
- 固定データのdatamartで、加えた列が出馬表の値・符号付き着差と一致し、初出走の馬で過去成績の列が欠損することを確かめる。
- 事前の試行として、運用と同じ固定snapshotから2006〜2025年のdatamartを構築し、test 2016〜2025年の評価と最終学習を行う（[計算済みの列の追加の試行](../experiments/pl-added-columns.md)）。`without_added_columns`が運用の評価と一致するか、加えた列の欠損と欠損の枝の照合、区分ごとの残差を記録する。この結果は採否に使わない。
- 2027年向けの作り直しで、test年2026を含む評価により採否を決める。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| PRのマージ前に運用のcheckoutを更新する | 特徴量の常駐CLIが今のdatamartを拒否し、予測できない | 切替の夜にマージし、それまでこのブランチのコードを運用のcheckoutに入れない |
| 評価の時間が延びる | 年末の作り直しが最初の開催日に間に合わない | 試行で時間を測り、作り直し後に群ごとのvariantを残すかを決める |
| 加えた出走表の列がvalid年や当日にまれに欠損する | 最終学習の書込み、または当日のそのレースの予測が拒否される | 試行で年ごとの欠損と欠損の枝の照合を確かめる |
| `--override`で片方のvariantだけを切り替える | 推定器のα・βと運用のモデルの入力が違う | 購入案の常駐CLIが名前の違いで起動を拒否し、切替前の確認で列も照合する |

---

## Security / Privacy Impact

セキュリティやプライバシーへの影響はない。既存のローカルデータと成果物だけを扱い、認証情報・個人データ・外部への送信を新たに扱わない。

---

## Operational Impact

2027年向けの作り直しは、このブランチのworktreeで行う。評価の後に、人間が加えた列の採否を決める。切替前の確認に、バックテストとPLモデルのvariantの一致を加える（[年次の再学習手順](../retraining-operation.md)）。

---

## Migration / Rollback

### Migration

作り直しの前に、このブランチへmainを取り込む。2027年向けの切替の夜に、このPRのマージ、運用のcheckoutの更新、3成果物の切替を一緒に行う。運用のcheckoutは、更新の前にそのコミット（`git rev-parse HEAD`）を記録する。マージの前にmainが進んでいたら取り込み、CIと承認をやり直す。進んだ変更が特徴量・datamart・学習・予測のコードに関わるなら、作り直してからマージする。

### Rollback

切り戻しでは、切替の夜にマージの前に記録した運用のcheckoutのコミットを`git checkout`して変更前のコードに戻し、前年のdatamartとPLモデルで特徴量と予測の常駐CLIを動かす（ADR-048決定6）。変更前のコードは36列のdatamartを読める。その後に当日の修正をmainから取り込むには、先にこの変更を取り消すPRが要る。そのPR（または直した版）がマージされたら、運用のcheckoutを`git switch main`と`git pull`でブランチへ戻す（記録したコミットの`git checkout`ではブランチから外れ、`git pull`できない）。

---

## Documentation Changes

- [x] `README.md`
- [x] `ARCHITECTURE.md`（購入案の常駐CLIの起動の検査）
- [x] `docs/race-day-operation.md`
- [x] `docs/retraining-operation.md`
- [x] `docs/experiments/pl-added-columns.md`
- [x] `docs/experiments/reference-feature-datamart.md`（当時の列数の注記）
- [x] `docs/table-definition/NL_SE_RACE_UMA.md`（`TimeDiff`の符号）
- [x] ADR-035・ADR-038・ADR-045・ADR-048のDecision History、ADR-043のヘッダとDecision History

---

## Follow-up Actions

- [ ] 2027年向けの作り直しで、test年2026を含む評価により加えた列の採否を決める（#57）。
- [ ] 作り直し後のPRで、既定のvariantと群ごとのvariantの扱いを更新する（ADR-048決定7）。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-26 | Accepted | GATE 1で人間が、8列の追加（馬番は加えない）、採否まで既定を元の36列、事前の試行、年末の切替の夜のマージ、variantの一致の確認を決定した |
