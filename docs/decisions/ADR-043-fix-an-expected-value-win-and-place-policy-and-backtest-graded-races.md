# ADR-043: 期待値による単勝・複勝の購入方策を固定し、平地重賞の購入時点を再現して評価する

- Status: Accepted
- Date: 2026-11-17
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #36、Refs #57・#35・#67・#81・#56・#82
- Supersedes: N/A
- Superseded by: N/A（決定1・3・4・8・9は[ADR-044](ADR-044-select-a-selection-bias-estimate-each-year-from-earlier-graded-flat-results.md)が選択した経路について改めた。Amendment 1）

---

## Context

REQ-04〜06は、暦年10万円・1レース5,000円の予算の中で、期待利益が見込めないレースを見送れる購入判断を求める。
SPEC-15とspec 4.3は、過去の購入時点を再現した仮想購入を確定の払戻で精算し、暦年ごとに回収率・収支・購入レース数・
的中率・最大ドローダウン・最大連敗・資金推移を報告することを求める。#36は、方策の決定に評価期間を使わないことを求める。

材料は2つある。

- PLの着順確率: ADR-035の`model evaluate-pl`は、test年`Y`ごとにtrain〜`Y−2`・valid `Y−1`で学習・校正したモデルの
  testの馬ごとの確率を`predictions.parquet`に書く。実データの結果（test 2016〜2025、variant`all_columns`）は、
  平地重賞1,289レースのうち1,103レースの確率を持つ。残りの186レースはdatamartの保留で確率がない
  （139レースは同着・異常区分などの結果に基づく保留、47レースはfreeze時点の取消などの保留）。
- 確定オッズの補正: ADR-042は、freezeのオッズから的中したときの確定オッズ`Ô`を予測する補正を評価し、
  複勝`place_mid`（`√(OddsLow·OddsHigh)`）の`graded`だけを採用した。単勝・馬連は未採用で、重賞で補正しない単勝の
  `payout_ratio`は1.001、馬連は0.919だった。

## Decision

方策は計測の前に固定し、評価期間（2016〜2025年）の結果で値を変えない（GATE 1の人間の決定、2026-11-16）。

1. **入力**:
   - PLの予測: `pl_evaluation_path`の`predictions.parquet`と`report.json`。どちらもSHA-256を設定で固定し、読む前に照合する。
     reportのformatは`pl_probability_evaluation`・version 1、variantは`all_columns`、reportの`test_years`は設定と一致すること。
     `finish_position`は読まない（列の投影）。
   - 固定snapshot: PLのreportの`race_subsets.jra_flat_graded_stakes_v1.source.snapshot_id`を使い、その`NL_RA_RACE`の
     SHA-256がreportの値と一致することを要求する。`NL_RA_RACE`・`NL_SE_RACE_UMA`・`NL_HR_PAY`・`ARCHIVE_O1_ODDS_TANFUKUWAKU`
     のhashを読む前に固定し、最後に再確認する。O2は読まない。
   - datamartの保留の理由: PLのreportの`config.datamart_path`（相対パスは実行時のカレントディレクトリからの解決）の
     `manifest.json`のSHA-256が`datamart.manifest_sha256`と一致し、manifestが記録する`held_races.json`のhash・形式と
     一致することを要求し、`role="target"`の項目を使う。datamartがない・一致しない場合は実行を止める。
2. **対象**: test年の`jra_flat_graded_stakes_v1`（snapshotの`NL_RA_RACE`のGradeCD A・B・CかつTrackCD 10〜24）の全レース。
   確率がないレースは`no_prediction`として、heldの段階（`target_outcome`・`target_pre_freeze`・その他の段階の`other_held`）と、
   heldにない`unattributed`に分けて数え、購入しない。
3. **確率と出走馬**:
   - 出走馬は`NL_SE_RACE_UMA`の`card_entrants`の馬番で、`horse_id`は同じレースの`KettoNum`で馬番に対応させる。
     予測の馬・SEの出走馬・freezeのO1の単勝の気配の馬の3つの集合が一致しないレースは`entrant_mismatch`で保留する。
   - 予測の検査（違反は例外）: 確率が有限で0〜1、`p_win ≤ p_top2 ≤ p_top3`、レース内の和が1・2・3（許容1e-6）、
     `test_year`がレースの年と一致、`temperature`が正、レース内の`horse_id`が一意。
   - `market_win_odds`がfreezeのO1の単勝オッズと一致しないレースは`market_odds_mismatch`で保留する。
   - 単勝は`p_win`。複勝は頭数`n`（一致した出走馬の数）が8以上なら`p_top3`、5〜7なら`p_top2`、4以下は複勝を買わない
     （ADR-042決定7。freeze前の取消のあるレースは予測がないため、`n`は発売開始時の頭数に等しい）。
4. **オッズ**: freezeは保存した`HassoTime`−300秒。O1は`latest_o1`でfreeze以前の最新の中間発表を選ぶ。発表がない・衝突・
   時刻不正・600秒より古い・気配が不正なレースは、ADR-042決定2と同じ理由で保留し、購入しない。
   単勝の`Ô`はfreezeの単勝オッズ`O`そのまま。複勝の`Ô`は`O = √(OddsLow·OddsHigh)`にtest年`Y`の`place_mid`の`graded`補正
   （train 2004〜`Y−1`の全レースの的中、ADR-042の`measure.yaml`と同じ値）を当てた値。気配のない買い目は作らない。
5. **買い目と金額**（1レースごと）:
   - 期待受取倍率`R = P × Ô`（specの期待純収益率は`EV = R − 1`）。`R ≥ 1.10`かつ`Ô > 1`の買い目だけを候補とする。
   - ケリーの比`f = (P·Ô − 1)/(Ô − 1)`、要求額`= floor100(0.25 × f × 100,000)`。0円の買い目は作らない。
   - レースの要求額の合計が`C = min(5,000, 年間の残り)`を超えるときは、各買い目に`C/合計`を掛けて100円単位で切り捨て、
     0円になった買い目を除く。年間の残りが100円未満なら購入しない。
   - 年間の残りは`100,000 −`同じ暦年（freezeのJSTの年）の先のレースの購入額の合計。払戻・返還で増やさない。
   - レースはfreezeの昇順、同時刻は`race_id`の昇順に処理する。同じ馬に単勝と複勝を買うことを許す。
6. **精算**: `NL_HR_PAY`（`headDataKubun` 2）で、的中した買い目は`購入額 × 払戻 ÷ 100`円を受け取る。同着は払戻の行どおりに
   精算する。返還馬（`HenkanUma{i}=1`は馬番`i+1`）の買い目は購入額を返還として受け取る。
   特払い・不成立の旗があるレースと、払戻の行がない・複数ある・確定でないレースに買い目があれば例外とする。
   2004〜2025年の中央で特払い・不成立の旗のレースは0件で、その払戻の列の形式を確かめられないため、推測で精算しない。
   spec 4.3の受取額の定義は変えず、該当が出たときに精算の規則を決める。
7. **指標**（暦年ごとと、全test年）:
   - 購入額・払戻額・返還額・受取額（払戻＋返還）、回収率（受取÷購入。購入0円ならnull）、収支（受取−購入。手数料を含まない）、
     購入レース数、的中レース数（払戻が1件以上ある購入レース）、的中率（的中レース÷購入レース。購入0なら
     null）。
   - 最大ドローダウン: 年初0円からの累積収支の過去最高値（最初は0円）からの最大下落額。暦年ごとに0円から始める。
     全test年の値は各年の最大とする。
   - 最大連敗: 払戻のない購入レース（返還だけのレースを含む）の最長の連続。暦年をまたいで続けない。全test年の値は各年の最大。
   - 回収率の95%区間: 購入レースを単位とする復元抽出（2,000回、seed 0、パーセンタイル、受取の和÷購入の和）。
     予算の経路は再現しない。
   - 券種ごとの買い目数・的中数・購入額・受取額・回収率。
8. **件数**（年ごと）: 対象の重賞、予測あり、`no_prediction`の内訳、保留の理由ごとの数、候補がなく見送ったレース、
   購入したレース、上限で縮小したレース、年間の枠が尽きて買えなかったレース、返還のあった買い目、複勝を買えない頭数のレース。
9. **出力**: 新しいCLI `model backtest-betting`が、新しいディレクトリへstagingから次の3ファイルだけを公開する。失敗時
   （Ctrl+Cを含む）は何も残さない。出力先が既存・シンボリックリンク・親なし、または`processed_root`・PLの評価のディレクトリと
   同じかその中（解決後）なら、どの入力も読む前に拒否する。datamartと固定snapshotはPLの評価の`report.json`が指すため、
   その中の出力は、hashで固定したreportを読んだ後、`predictions.parquet`とsnapshotの表を読む前に拒否する。
   - `report.json`: format `ev_betting_backtest`、format_version 1。キーは`format`・`format_version`・`config`・`inputs`
     （PLの評価・datamart・snapshotの識別）・`provenance`・`policy`（決定5の固定値）・`counts`（年ごと）・`years`
     （年ごとの指標）・`all_test_years`（全test年の指標）。
     - `counts`の各年: `graded_races`・`predicted`・`no_prediction`（`target_outcome`・`target_pre_freeze`・`other_held`・
       `unattributed`）・`holds`（理由ごとの数）・`place_unavailable`・`no_eligible_bet`・`purchased`・`scaled`・
       `budget_exhausted`・`refunded_bets`。
     - `years`の各年と`all_test_years`: `stake_yen`・`payout_yen`・`refund_yen`・`receipt_yen`・`recovery_rate`・`net_yen`・
       `purchased_races`・`hit_races`・`hit_rate`・`maximum_drawdown_yen`・`maximum_consecutive_losses`・
       `recovery_rate_interval`（`lower`・`upper`）・`bet_types`（`win`・`place`ごとに`bets`・`hits`・`stake_yen`・
       `receipt_yen`・`recovery_rate`）。比は購入0のときnull。
   - `bets.parquet`（購入額が正の買い目。freeze・`race_id`・券種（win、place）・馬番の昇順）:

     | 列 | 型 | null |
     | --- | --- | --- |
     | `test_year` | int64 | 不可 |
     | `race_id` | string | 不可 |
     | `freeze_at` | timestamp[us, UTC] | 不可 |
     | `bet_type` | string（`win`・`place`） | 不可 |
     | `horse_number` | string（2桁） | 不可 |
     | `probability` | double（`P`） | 不可 |
     | `freeze_odds` | double（`O`） | 不可 |
     | `estimated_odds` | double（`Ô`） | 不可 |
     | `expected_return` | double（`R`） | 不可 |
     | `kelly_fraction` | double（`f`、係数を掛ける前） | 不可 |
     | `requested_stake_yen` | int64（縮小前） | 不可 |
     | `stake_yen` | int64（縮小後、正） | 不可 |
     | `payout_yen` | int64 | 不可 |
     | `refund_yen` | int64 | 不可 |
     | `receipt_yen` | int64 | 不可 |

   - `races.parquet`（購入したレース。freeze・`race_id`の昇順）:

     | 列 | 型 | null |
     | --- | --- | --- |
     | `test_year` | int64 | 不可 |
     | `race_id` | string | 不可 |
     | `freeze_at` | timestamp[us, UTC] | 不可 |
     | `stake_yen` | int64 | 不可 |
     | `receipt_yen` | int64 | 不可 |
     | `net_yen` | int64 | 不可 |
     | `cumulative_net_yen` | int64（その暦年の累積） | 不可 |
     | `annual_stake_yen` | int64（その暦年のこのレースまでの購入額の累計） | 不可 |
     | `hit` | bool | 不可 |

### 計測の結果（2026-11-17、`docs/experiments/ev-betting-backtest.md`）

PLの評価`graded-final3`（test 2016〜2025、`all_columns`）とsnapshot `098ce3f4…`で、平地重賞1,289レースのうち
予測のある1,103レースを評価した（予測のない186レースは結果に基づく保留139・freeze前の保留47）。926レースを購入し、
購入額678,000円・受取額549,100円、全test年の回収率は0.810（95%区間0.670〜0.963）で、2016年と2022年を除く年は1を下回った。
単勝は2,207の買い目で回収率0.815、複勝は273の買い目で0.803だった。選ばれた単勝の期待的中数97.2に対し的中は61、
的中した複勝の払戻倍率の和は`Ô`の和の約0.75倍で、期待値の高い買い目を選ぶと確率とオッズの見積もりが過大な買い目が集まる。
この方策での購入は損失になると判断し、結果を運用での購入の開始の根拠にしない。

### Amendment 1: 推定の方法の年ごとの選択（2026-11-17、ADR-044）

- [ADR-044](ADR-044-select-a-selection-bias-estimate-each-year-from-earlier-graded-flat-results.md)は、方策（決定5〜7）を
  変えずに、確率とオッズの推定の方法を4通り用意し、test年ごとに前の年の重賞の定額の回収率で選ぶ。人間の承認のもとで、
  評価期間の中で前の年だけを使って方法を選ぶ（下のRationaleの「評価期間を使わない」から離れる）。
- 改めた決定: 決定1（合成の当てはめのため、`finish_position`を2つ目の投影で読む）、決定3・4（選択した経路の確率と複勝の`Ô`）、
  決定8（件数に`place_width_invalid`と合成の保留の理由`blend_market_incomplete`・`blend_zero_probability`を加える）、
  決定9（reportはformat_version 2、2つの表に`method`列）。この決定3・4は方法`pl_mid`としてそのまま残り、`pl_mid`の結果は
  このADRの計測と同じ値を再現する。
- `model backtest-betting`はversion 1を書かない。

## Rationale

- 方策を計測の前に1つに固定すれば、評価期間を方策の選択に使わない（#36）ことを、内側の期間の設計なしに守れる。
  PLの確率は2016年からしかfoldの予測がなく、年ごとに過去から値を選ぶ方法は最初の数年が既定値になる。
- 単勝と複勝だけを買う。複勝はADR-042で補正を採用した。単勝は補正を採用しなかったが、補正しないオッズの重賞での
  `payout_ratio`が1.001で偏りが小さい。馬連は補正しないと約8%高く見積もり、PLの馬連の確率も購入の帯で検証していない。
- 1/4ケリーは、期待利益（`R`）と損失のリスク（オッズが高いほど小さい比）の両方を金額に反映する（SPEC-07）。
  係数を小さくすると、確率の誤差による過大な購入を抑える。`R ≥ 1.10`は、確率とオッズの補正の誤差に対する余裕である。
- 買い目の判断と精算を分ける（spec 4.3）。購入にはfreezeのオッズ、精算には確定の払戻だけを使う。
- 予測がない重賞は、予測を作る経路（ラベルなしの特徴量とfoldのモデル）がないため、今回は外して件数と理由を記録する。

## Consequences

### Positive

- 予算・見送り・精算・暦年の指標を、過去の購入時点を再現して1つのコマンドで測れる。
- 買い目ごと・レースごとの表から、事後に方策の振る舞いを確かめられる。

### Negative

- 予測がない重賞（約14%）を外すため、運用で買うはずのレース（同着・締切後の取消など）が欠け、評価が偏る。
- 1/4ケリーは買い目を独立に扱い、同じレースの単勝と複勝の相関や、年間の枠の配分を最適化しない。
- 手数料を含まない。収支は純利益ではない。

### Neutral / Follow-on effects

- 当日の購入案の提示と補正の成果物の保存は#81、実購入額の記録と上限の管理は#56で扱う。
- 方策の値の比較・改良は、評価期間を使わない設計とともに別のIssueで扱う。

## Alternatives Considered

### Option A: 年ごとに過去の結果から方策の値を選ぶ

Summary: 候補の値を用意し、test年`Y`では`Y`より前のtest年の結果で選ぶ。

Advantages: 方策の値をデータで調整できる。

Disadvantages: 2016年からしか予測がなく、最初の数年は既定値になる。設計と報告が複雑になる。

Reason not selected: GATE 1で、計測の前に1つに固定することを人間が選んだ。

### Option B: 定額（買い目ごとに100円）

Summary: `R ≥ 1.10`の買い目に一律100円を買う。

Advantages: 単純で、確率の誤差の影響を受けにくい。

Disadvantages: 損失のリスクを金額に反映しない（SPEC-07）。

Reason not selected: GATE 1で1/4ケリーを人間が選んだ。

### Option C: 馬連も買う

Summary: 馬連の確率をPLのスコアと温度から計算し、補正しないオッズで買う。

Advantages: 券種が増え、購入の機会が増える。

Disadvantages: 補正しないオッズは約8%高く見積もる。PLの馬連の確率は購入の帯で検証していない。

Reason not selected: GATE 1で単勝と複勝だけを人間が選んだ。

## Implementation Notes

- `models/betting/`（新しい純粋なパッケージ。I/O・CLI・`data`をimportしない）: `policy.py`（買い目・金額・上限）、
  `settlement.py`（精算）。
- `models/evaluation/betting_metrics.py`: 暦年の指標とbootstrap。
- `models/serialization/betting_inputs.py`: PLの予測・SE・O1・HRの整形と検査。ADR-042の`final_odds_observations.py`の
  freezeの行の選択・O1の気配・払戻の解析を公開名にして再利用する。
- `models/experiments/betting_backtest.py`: 複勝の補正の当てはめ（`fit_all_correction`・`fit_graded_correction`を`place_mid`だけに
  使う）、時刻順の購入と精算、件数、report・表の組立。I/Oなし。
- `make_datamart/tables/reference.py`: `held_races.json`をmanifestで検証して`role="target"`の項目を返す読込口。
- `configuration/betting_backtest.py`、`configs/betting_backtest/`、`cli/betting_backtest.py`。

## Validation

- 単体テスト: 期待受取倍率・ケリー・上限・切り捨て・暦年の境界、精算（的中・外れ・同着・返還・例外）、指標の手計算、
  予測の検査、O1だけでの複勝の補正、test年以後の払戻と`finish_position`を変えても買い目が変わらないこと。
- 統合テスト: 小さな複数年の固定snapshotとPLの評価の出力で、CLIが3ファイルを公開し、schemaと合計が一致すること。
- 実データでの計測（`docs/experiments/ev-betting-backtest.md`）。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| PLの確率の校正の誤り | 期待値を高く見積もり、損失になる | `R ≥ 1.10`の余裕と1/4ケリー。結果を運用での購入の開始の根拠にしない |
| 予測がない重賞を外す | 評価が偏る | 件数と理由を年ごとに記録する。予測を作る対応を別Issueにする |
| 選ばれる買い目での補正の偏り | `Ô`が確定とずれる | `bets.parquet`の`freeze_odds`・`estimated_odds`と払戻から事後に確かめる |
| PLのsnapshot（`098ce3f4…`）がADR-042の計測（`034f3ff2…`）と異なる | 補正の値がわずかに異なる | 同じ規則と固定値で当てはめ直し、snapshotを記録する |

## Security / Privacy Impact

外部への送信、認証情報、個人情報は扱わない。固定snapshotとPLの評価の出力を読み、新しい出力ディレクトリへ3ファイルだけを書く。

## Operational Impact

評価の経路だけを加え、当日の運用の手順（ADR-041）は変えない。システムは購入を実行しない（REQ-07）。

## Migration / Rollback

### Migration

なし。新しいCLIと出力だけを加える。

### Rollback

CLIと`models/betting/`などの新しいモジュールを削除すれば戻せる。ADR-042の部品の公開名の変更は振る舞いを変えない。

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `docs/rules/architecture.md`
- [x] `README.md`
- [x] `docs/specification.md`（第4.3節・第5節）
- [x] `docs/experiments/ev-betting-backtest.md`
- [x] `docs/table-definition/NL_HR_PAY.md`（`HenkanUma{i}`の馬番の対応）

## Follow-up Actions

- [ ] 予測がない重賞への予測の作成（#91）。
- [x] 選ばれる買い目での確率（単勝の高いオッズ帯）とオッズ（複勝）の見積もりの改善（#92、ADR-044。#82は継続）。
- [x] 当日の購入案の提示（#81、[ADR-045](ADR-045-save-the-betting-estimator-yearly-and-attach-zero-yen-proposals-on-race-day.md)。提示額は0円）。
- [ ] 実購入額の管理（#56）。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-16 | Proposed | GATE 1で人間が決めた方策を計測の前に固定した |
| 2026-11-17 | Accepted | 実データで評価し、全test年の回収率0.810（95%区間0.670〜0.963）を記録した |
| 2026-11-17 | Accepted（Amendment 1） | ADR-044が決定1・3・4・8・9を選択した経路について改めた（人間の承認、#92） |
