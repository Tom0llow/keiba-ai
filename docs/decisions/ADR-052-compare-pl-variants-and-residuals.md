# ADR-052: 公開済みPL評価からvariant比較と区分別残差を求める

- Status: Accepted
- Date: 2026-11-28
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #120、Refs #83、#121
- Supersedes: N/A
- Superseded by: N/A

---

## Context

[ADR-035](ADR-035-evaluate-top3-plackett-luce-probabilities-on-yearly-folds.md)の
`model evaluate-pl`は、年単位foldでPLを学習・校正し、市場との比較を行い、variantごとの
`report.json`と`predictions.parquet`を公開する。複数variantの候補と基準の差を、固定した
testレースの対応ありbootstrapで比較したり、馬場・距離・枠の位置・馬齢・前走の条件ごとの
残差を求めたりする機能は、そのreportには含まれない。

評価は長時間の学習・校正・test計算であり、既に公開した評価をvariant間の比較のために
やり直すと、同じ入力に対する再計算の負担と結果の取り違えを増やす。比較は評価の実行そのもの
ではなく、評価済みの予測に対する事後の分析である。また、評価の既存のreportと予測表の形式を
変えずに、#83のvariant検討を#120で再現できる必要がある。

区分を設定で自由に受けると、同じ名前の意味が実行ごとに変わり、結果を比較できなくなる。
さらに、馬ごとの勝ち・3着以内の残差を標準化する値は、独立なBernoulli近似に基づく記述量であり、
検定の統計量として扱うと採否を誤る。PR #119でADR-051が使用されているオープンな作業があるため、
この決定ではADR-051の番号や内容を変更しない。

---

## Decision

1. **評価から分離した比較CLI。** 公開済みの`model evaluate-pl`の`report.json`と
   `predictions.parquet`を読み、評価をやり直さずにvariantの比較と区分別残差を計算する
   `model compare-pl-variants`を追加する。`model evaluate-pl`の学習・fold・温度校正・市場比較の
   責務と既存の出力形式は変更しない。比較の組は設定の`comparisons`に明示する
   `[{candidate, baseline}]`のリストとし、候補と基準は異なる名前でなければならない。
2. **固定版付き区分。** 残差分析の区分は、設定で差し替えない固定集合
   `pl_residual_segments_v1`とする。定義は次のとおりであり、1頭が複数区分に入ることを許す。

   | 名前 | 定義 |
   | --- | --- |
   | `all_horses` | 評価対象のtestレースに含まれる全馬。 |
   | `dirt_le1400_inner` | `TrackCD`が`23`または`24`、距離が1400m以下、馬番が頭数の1/3以下。 |
   | `dirt_le1400_outer` | `TrackCD`が`23`または`24`、距離が1400m以下、馬番が頭数の2/3を超える。 |
   | `dirt_gt1400_inner` | `TrackCD`が`23`または`24`、距離が1400m超、馬番が頭数の1/3以下。 |
   | `dirt_gt1400_outer` | `TrackCD`が`23`または`24`、距離が1400m超、馬番が頭数の2/3を超える。 |
   | `turf_inner` | `TrackCD`が`10`〜`22`、馬番が頭数の1/3以下。 |
   | `turf_outer` | `TrackCD`が`10`〜`22`、馬番が頭数の2/3を超える。 |
   | `age_2` | 馬齢が2。 |
   | `age_3` | 馬齢が3。 |
   | `age_4` | 馬齢が4。 |
   | `age_5` | 馬齢が5。 |
   | `age_6` | 馬齢が6。 |
   | `age_7_plus` | 馬齢が7以上。 |
   | `prior_win_margin_ge_0_3s` | 前走1着、かつ前走の符号付き着差が`-0.25`秒以下。0.1秒刻みのデータでは0.3秒以上の差の勝ちに相当する。 |
   | `prior_2to5_within_0_1s` | 前走2〜5着、かつ前走の符号付き着差が`0.1`秒以下。 |

   ダート・芝以外のTrackCDは馬場・距離・枠の位置の区分に入らない。内外の境界は
   `horse_number <= field_size / 3`と`horse_number > 2 * field_size / 3`であり、中間はどちらにも
   入らない。`field_size`は評価予測のレース内行数とする。前走の値が欠損している馬は前走区分に
   入らない。`past_racing_ability__past_signed_gap_sec_lag1`列そのものがdatamartにない場合だけ、
   前走の2区分を`available: false`とし、理由を記録する。他の区分は計算する。
3. **比較と残差の定義。** 各variantについて、保存された`score`とtest年ごとの`temperature`から
   `top3_marginal_probabilities`で勝率・3着以内確率を再計算する。レース単位の指標は、全testレースと
   `jra_flat_graded_stakes_v1`の部分集合について、全体とtest年ごとに求める。variantの組ごとの差は、
   同じレースを対応させたpaired bootstrapで求め、既定値は2,000回、seed 0、信頼水準0.95とする。

   区分ごとの`win`と`top3`について、`actual`は実績数、`expected`は確率の合計、`ratio`は
   `actual / expected`、`z`は`(actual - expected) / sqrt(sum(p * (1 - p)))`とする。ここでの`z`は、
   同じレースの馬の事象を独立なBernoulliとみなした近似の標準化残差であり、検定の統計量ではない。
   多重比較の補正や閾値による採否の規則は、この決定では定めない。
4. **入力の固定と照合。** CLIは計算や全表読込の前に設定と比較の組、出力先を検査し、次の順で入力を固定して照合する。

   - 評価の`report.json`を設定の`pl_report_sha256`で照合し、`format: pl_probability_evaluation`、`format_version: 1`、比較対象variantの存在を確かめる。
   - `predictions.parquet`を設定の`pl_predictions_sha256`で、表を読む前に照合する。
   - reportの`datamart.path`・`datamart.manifest_sha256`からdatamart manifestを固定し、計算契約の`closed_numeric_columns`、必要な距離・前走着順列、test年の期間・会場を照合する。
   - reportのsnapshot出典とdatamart manifestの`snapshot_id`を結び付け、固定snapshotの`NL_RA_RACE`・`NL_SE_RACE_UMA`のhashを先に固定して両方の出典と照合する。`NL_RA_RACE`のhashは評価reportの平地重賞部分集合の出典とも一致させる。
   - 予測表を読み、uniqueなvariant・test年が評価reportと一致することを確かめてから、`(variant, test_year, race_id, horse_id)`を一意にし、variant間でrace・馬・着順・平地重賞の印を一致させる。温度はvariant・test年ごとに一つとし、行位置ではなくキーで同じ順序に正規化する。
   - `score`と`temperature`から再計算した確率が保存済みの`p_win`・`p_top2`・`p_top3`と1e-9以内で一致すること、確率の範囲・大小・レース内の和、および全testレースの校正後平均が評価reportの`pooled.<variant>.all_test_races.calibrated`と相対誤差1e-12以内で一致することを確かめる。続けて`predictions.parquet`のhashをもう一度照合する。
   - その後にdatamartとsnapshotの必要な全行を読み、予測の全行がdatamartの行（着順を含む）とsnapshotの出走表行（`KettoNum`を含む）に一対一で対応することを確かめる。

5. **report形式。** 成果物は新しいディレクトリの`report.json`だけとし、トップレベルを
   `format: pl_variant_comparison`、`format_version: 1`とする。`inputs`には評価2ファイル、datamart
   manifest、snapshotの識別と表hash、`config`には`evaluation_path`を除く設定、`provenance`、
   `test_years`、`variants`、`comparisons`、`segments`を記録する。

   `comparisons`は候補・基準、`all_test_races`、`jra_flat_graded_stakes_v1`を持ち、それぞれに
   `pooled`と`by_test_year`を記録する。空でない`pooled`または年ごとの値では、`race_count`を
   9つの指標キーと同じ階層に1回だけ置く。各指標の比較値は`candidate_mean`、`baseline_mean`、
   `mean_difference`、`confidence_interval_lower`、`confidence_interval_upper`、`conclusion`とする。
   固定する9つの指標キーは、
   `winner_log_loss`、`multiclass_brier`、`exacta_log_loss`、`quinella_log_loss`、
   `trifecta_log_loss`、`trio_log_loss`、`stage1_nll`、`stage2_nll`、`stage3_nll`である。
   部分集合のレースがない年または組の値は`null`とする。

   `variants`はvariant名をキーとするobjectであり、各variantは`all_test_races`と
   `jra_flat_graded_stakes_v1`を持つ。各scopeは`pooled`と`by_test_year`を持ち、空でない値には
   `race_count`と9指標のレース平均を記録する。

   `segments`は`definition_version`、`ratio`と`z`の固定の説明を持つ`residual_definition`、各区分名を
   同じ階層のキーとして持つ。`residual_definition`は`ratio`が`actual / expected`（`expected`が1頭あたり1e-12以下なら
   `expected`を0として`null`）、`z`が`(actual - expected) / sqrt(sum(p * (1 - p)))`（分母の中が1頭あたり1e-12以下なら`null`）であり、独立
   Bernoulli近似であって検定の統計量ではないことを記録する。利用可能な区分には`definition`、
   `available: true`、variantごとの馬数と`win`・`top3`の`actual`・`expected`・`ratio`・`z`を記録し、
   利用できない区分には`definition`、`available: false`、理由を記録する。
6. **採否の責任。** reportのbootstrap区間、`conclusion`、残差、`z`は候補を比較するための材料として
   公開するが、特徴量やvariantを採用するかどうかの決定は人間が行う。CLIは採否の閾値、
   多重比較の補正、モデルの自動切替を行わない。

---

## Rationale

- 評価と比較を分けると、公開済みの評価をhashで固定して再利用でき、長時間の学習・fold・校正を
  やり直さずにvariant間の対応あり比較を再現できる。`model evaluate-pl`の既存のreport・予測表の
  契約も変わらない。
- 区分を版付きのコードで固定し、定義文字列もreportに残すことで、同じ版の結果を比較できる。
  新しい仮説や列が必要になった場合は、既存版の意味を変えずに別版を追加できる。
- report、datamart、snapshot、予測表を複数のhashとキー照合で固定することで、異なる評価・出走表・
  datamartを組み合わせた見かけ上の比較を拒否できる。
- 残差の近似を明示し、検定や採否の規則を自動化しないことで、近似の限界と意思決定の責任を分離できる。

---

## Consequences

### Positive

- 公開済みPL評価から、variantの候補・基準比較と区分別残差を同じ手順で再現できる。
- 出力に入力hash、snapshot、区分の版と定義が残り、後から結果の出所を確認できる。
- 既存の`model evaluate-pl`の出力形式、評価時間、MLflowへの記録方針を変更しない。

### Negative

- 予測表、datamart、snapshotを読み直すため、比較にもメモリと実行時間が必要になる。
- `pl_residual_segments_v1`は固定なので、別の仮説には新しい版と定義が必要になる。
- `z`を検定の統計量と誤解したり、区間を自動採否の規則と解釈したりする余地がある。

### Neutral / Follow-on effects

- `pl_variant_comparison` v1は評価reportとは別の永続化形式として扱う。
- ADR-050の`model track-report`への記録はこの決定の範囲外とし、必要なら別のIssueで扱う。
- ADR-051を使用するオープンなPR #119へmainを取り込む際は、ADR-051の運用文書との競合を人間が解消する。

---

## Alternatives Considered

### Option A: 評価CLIに比較を組み込む

Summary:

`model evaluate-pl`の実行中にvariant同士の比較と区分別残差も計算する。

Advantages:

- 評価と比較を一度の実行で作れる。

Disadvantages:

- 既存の評価の処理時間・出力形式・責務が変わり、公開済みの評価だけを比較する用途で評価を再実行することになる。

Reason not selected:

比較は評価済み成果物に対する事後分析であり、既存の評価契約を維持するため、独立CLIを採用する。

### Option B: 区分を設定で自由に定義する

Summary:

実行ごとに馬場、距離、馬齢、前走条件などの区分を設定ファイルから受け取る。

Advantages:

- 新しい仮説をコード変更なしで試せる。

Disadvantages:

- 区分名と境界の意味が実行ごとに変わり、結果の再現と比較が難しくなる。

Reason not selected:

まずは#120で必要な固定集合を版付きで保存し、意味を変えない永続的な比較単位とする。

### Option C: 既存の保存確率だけで残差を計算する

Summary:

`predictions.parquet`の`p_win`・`p_top3`をそのまま集計する。

Advantages:

- 再計算が不要で実装が単純になる。

Disadvantages:

- score・temperatureからの確率の再現性を検査できず、評価reportとの整合を別の経路で保証することになる。

Reason not selected:

scoreとtemperatureから同じ確率を再計算し、保存値との一致を検査することで、入力の破損や組合せ違いを早く拒否する。

---

## Implementation Notes

- `src/cli/pl_comparison.py`は設定の読込、評価2ファイルのhash照合、reportからのdatamart・snapshotの固定、表の読込、計算呼出し、`report.json`の公開を所有する。
- `src/models/experiments/pl_comparison.py`はI/Oを持たず、予測表の正規化、確率と指標の再計算、対応ありbootstrap、残差、report本文の組立を所有する。
- `src/models/serialization/residual_segments.py`はI/Oを持たず、`pl_residual_segments_v1`の名前・定義と馬ごとの所属判定を所有する。
- 設定の`evaluation_path`、2つのSHA-256、`processed_root`、`comparisons`、`bootstrap`をHydraで合成し、出力は`publish_directory`で新規公開する。
- 評価の入力形式、`pl_variant_comparison`のキー、区分の定義を変更する場合は、既存版を再解釈せず新しいADRまたはformat versionを追加する。

---

## Validation

- `src/tests/unit/test_residual_segments.py`で、TrackCD、1400m、頭数の1/3、馬齢、前走着差の境界と、着差列がない場合の`unavailable`を検証する。
- `src/tests/unit/test_pl_comparison.py`で、variantの正規化、年ごとの温度、9指標の比較、空の重賞部分集合、残差、3頭立ての`top3`の`z: null`を検証する。
- `src/tests/integration/test_pl_comparison_cli.py`で、固定hash、datamart・snapshotの照合、公開report、設定・入力・出力の拒否、help/import、終了コードを検証する。
- 実データでは、評価reportの平均との一致、既存の試行結果との区分残差の一致、着差列がない場合の2区分の`unavailable`を別途確認する。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 独立Bernoulli近似の`z`を検定結果と誤解する | 採否を過大に確信する | reportとこのADRに近似であり検定統計量でないことを記録し、自動採否を行わない |
| 固定区分が別の仮説を表さない | 必要な分析を追加できない | `pl_residual_segments_v1`を変更せず、必要なら新しい版を追加する |
| 評価・datamart・snapshotの組合せがずれる | 比較結果が再現不能になる | SHA-256、manifest、snapshot表hash、キー、確率、report平均を計算前後に照合する |
| ADR-051を使用するオープンなPR #119との統合で文書が競合する | 運用手順やDecision Historyの記録が不整合になる | ADR-051の内容をこの変更で変更せず、main取り込み時に人間が両方の記録を残して解消する |

---

## Security / Privacy Impact

入力のhashとsnapshotの識別をreportへ記録するが、認証情報や秘密情報は扱わない。セキュリティやプライバシーへの重大な影響はない。

---

## Operational Impact

比較は公開済み成果物と固定snapshotを読むだけで、元の評価出力を変更しない。全testレースの予測とdatamartを読むため、評価と同様にメモリ・実行時間を要する。失敗時は新しい出力を公開せず、Ctrl+Cは130、その他の失敗は1とする。

---

## Migration / Rollback

### Migration

既存の評価出力を移行する必要はない。新CLIの設定へ評価ディレクトリと2ファイルのSHA-256、`processed_root`、比較の組を指定して、別の出力ディレクトリへ`pl_variant_comparison` v1を公開する。

### Rollback

新CLIの公開を停止しても、既存の`model evaluate-pl`のreport・予測表と過去の評価結果は変更されない。既に公開した比較reportを利用しないようにするだけで、既存データの変換や削除は行わない。

---

## Documentation Changes

このADRがAcceptedになったら、該当するものを更新する。

- [x] `ARCHITECTURE.md`
- [ ] `docs/rules/architecture.md`
- [ ] `AGENTS.md`
- [x] `README.md`
- [x] APIとユーザー向けの文書
- [ ] 運用文書・運用手順書

---

## Follow-up Actions

- [ ] `pl_residual_segments_v1`以外の区分が必要になった場合は、新しい版の定義とADRを検討する。
- [ ] `pl_variant_comparison`をMLflowへ記録する必要が生じた場合は、ADR-050とは別に範囲と形式を決める。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-28 | Accepted | 公開済みPL評価からvariant比較と`pl_residual_segments_v1`の区分別残差を求める方針を決定 |
