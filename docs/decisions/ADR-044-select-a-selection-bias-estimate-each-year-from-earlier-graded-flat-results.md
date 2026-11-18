# ADR-044: 選ばれる買い目の偏りを減らす推定の方法を、test年ごとに前の年の重賞の定額の回収率で選ぶ

- Status: Accepted
- Date: 2026-11-17
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #92・#94・#95、Refs #57・#36・#82・#91
- Supersedes: N/A（ADR-043の決定1・3・4・8・9を、選択した経路について改める）
- Superseded by: N/A

---

## Context

ADR-043の固定した方策（単勝・複勝、`R = P × Ô ≥ 1.10`、1/4ケリー、予算）は、2016〜2025年の平地重賞で回収率0.810
（95%区間0.670〜0.963）だった。選ばれた買い目では確率とオッズの見積もりが過大だった（選択による偏り）。

- 単勝: 選ばれた2,207の買い目の期待的中97.2に対し、的中は61。約8割が`Ô`20倍以上で、高いオッズの馬の`P`が過大。
- 複勝: 的中した買い目の払戻倍率の和は`Ô`の和の約0.75倍。選ばれる馬は`OddsLow`と`OddsHigh`の幅が広い。

Issue #92は、この偏りを減らす方法を、評価期間（2016〜2025年）を方法の選択に使わない設計で比べ、固定した方策の回収率と
区間の変化を報告することを求める。

## Decision

GATE 1の前に人間が決めた（2026-11-17）: 方法の候補はPLと市場の合成、および幅の帯を加えた複勝の補正。方法は評価期間の中で、
test年`Y`ごとに`Y`より前の年の重賞の定額の回収率で選ぶ（ローリング）。これはADR-043のRationaleと#36の「評価期間を
方策の決定に使わない」から、人間の承認のもとで離れるものである。各年の選択は、その年より前の結果だけを使う。

1. **方法**（4通り、IDの順は同点の順でもある）:

   | ID | 単勝・複勝の確率 | 複勝の`Ô` |
   | --- | --- | --- |
   | `pl_mid` | PLの`p_win`・`p_top2`・`p_top3`（ADR-043の決定3） | `place_mid`の`graded`補正（ADR-043の決定4） |
   | `blend_mid` | PLと市場の合成（決定2） | `place_mid`の`graded`補正 |
   | `pl_width` | PL | 幅の帯を加えた補正（決定3） |
   | `blend_width` | 合成 | 幅の帯を加えた補正 |

   単勝の`Ô`はfreezeの単勝オッズ`O`。候補の規則、複勝の頭数の規則（8頭以上は3着以内、5〜7頭は2着以内）、方策の金額、精算、
   指標はADR-043のまま。方法`m`の年`y`の候補は、`y`より前のデータだけで当てはめた合成・補正で作り、年`y`の結果は1回だけ
   計算してどの`Y > y`の選択にも同じ値を使う。

2. **PLと市場の合成**: 馬`i`の強さ`s_i = α·log p_win_i + β·log q_i`（`q_i = (1/O_i)/Σ_j(1/O_j)`、`O`は予測の
   `market_win_odds`）。勝率は`softmax(s)`、2着以内・3着以内は`s`を強さとするPLの周辺確率。
   - 年`y`の`α`・`β`は、設定のvariantの予測のうち、test年が最初のtest年以上`y−1`以下の全レース（重賞に限らない）で、
     勝者のレース平均の対数尤度を最大にする。全馬の`market_win_odds`が有限で正（`market_incomplete`）、全馬の`p_win > 0`
     （`zero_probability`）、1着がちょうど1頭（`winner_count`）でないレースは除いて数える。
   - Newton法（初期値`α=1, β=0`）。ステップは、対数尤度の減少が丸めの許容（`1e-12 × max(1, |対数尤度|)`）以内になるまで
     半分にする（最大30回）。最適点の近くでは1ステップの増加が対数尤度の丸め誤差より小さいため、許容がないと収束の前に止まる。
     レース平均の対数尤度の勾配の最大絶対値が`blend_tolerance`未満で、Hessianが負定値かつ符号を変えた固有値がすべて`1e-6`以上なら
     収束。勝者が常に特徴の最大の馬である（分離できる）レースでは最大点がなく、係数が発散して対数尤度が平らになるため、曲率が
     `1e-6`を下回ったら負定値でない（`not_concave`）とする。分離できるレースでは勾配と曲率が一緒に小さくなる（曲率は勝者の特徴の
     差と勾配の積の程度）ため、許容が緩いと曲率が下限に達する前に収束と判定される。分離できる合成データ（3〜18頭、勝者の差
     0.01〜100）では、許容`1e-5`で誤って収束し、`1e-6`以下では誤らなかった。このため`blend_tolerance`の上限を`1e-8`とし（100倍の
     余裕）、超える値を設定の検査・`BettingBacktestSettings`・当てはめのすべてで拒む（#94）。曲率の下限は特徴のスケールに依存する
     （実データの最適点の最小の曲率は約0.013）。
     使えるレースが`blend_min_races`未満・負定値でない・収束しない年は、合成の方法を使えない（`available`がfalse）。
     最初のtest年は必ず使えない。
   - 重賞で`market_win_odds`のない馬・`p_win ≤ 0`の馬がいるレースは、合成の方法では保留（`blend_market_incomplete`・
     `blend_zero_probability`）。
3. **幅の帯を加えた複勝の補正**: 幅`w = OddsHigh/OddsLow`を、0.1刻みの整数にした値の有理数で扱う（帯の境界と厳密に比べる）。
   的中の観測では、同じ組合せの`place_low`（`OddsLow`）と`place_mid`から`OddsHigh = round(mid²/low, 1)`を戻す
   （`place_low`の相手がない`place_mid`の的中は例外）。幅の帯`place_width_bands`（左閉右開、最後は上限なし）ごとに、
   2004〜`y−1`の`place_mid`の的中でADR-042と同じ帯・分位点・`min_hits`・`k`の`graded`補正を当てはめる。全レースの的中が
   `min_hits`未満の幅の帯は低い側の帯と順に統合する（最も低い帯は高い側と）。`OddsHigh < OddsLow`の馬は幅の方法では複勝の
   候補を作らず数える（`place_width_invalid`）。
4. **定額の評価と選択**:
   - 定額: 方法・年ごとに、`R ≥ 1.10`かつ`Ô > 1`の買い目を、ケリーの要求額に関係なく各`unit_yen`で買う（予算なし）。
     精算は方策と同じで、精算できないレースは例外。`hits`は払戻が正の買い目、受取は払戻＋返還。
   - 比較の年`C(Y)`は、`Y`より前で4方法がすべて使える年。`C(Y)`が空なら`pl_mid`。そうでなければ、`C(Y)`の重賞の定額の
     受取の和÷購入の和が最大の方法（整数の交差乗算で比べ、同じなら表の順）。購入0円の方法は選ばず、すべて0円なら`pl_mid`。
     選んだ方法が`Y`で使えなければ`pl_mid`。
   - 方法・年ごとにADR-043の方策を当てる（年間の枠は暦年でリセットされ、方法・年ごとの実行は独立）。選択した経路の年`Y`は、
     選ばれた方法の年`Y`の方策の結果と同じ。
5. **入力**（ADR-043の決定1を改める）: PLの予測は、候補用の投影（`finish_position`なし）に加え、合成の当てはめ用に
   `variant`・`test_year`・`race_id`・`horse_id`・`p_win`・`market_win_odds`・`finish_position`の投影を、`predictions.parquet`の
   2回のhashの照合の間で読む。年`y`の当てはめには`y`より前の年のレースだけを渡す。的中の観測は`place_low`と`place_mid`を渡す。
6. **設定**: 必須の`estimation`（`blend_min_races`・`blend_tolerance`・`blend_max_iterations`・`place_width_bands`）。
   `blend_tolerance`は正で`1e-8`以下（決定2）。
   `measure.yaml`は計測の前に`1000`・`1e-10`・`100`・`[1.0, 1.5, 2.0, 3.0, 5.0]`に固定した。
7. **出力**（ADR-043の決定9を改める）: `report.json`はformat `ev_betting_backtest`・**format_version 2**。

   ```text
   report.json
   ├─ format, format_version (2), config, inputs, provenance, policy   # version 1と同じ意味
   ├─ estimation: {methods, blend_min_races, blend_tolerance, blend_max_iterations, place_width_bands}
   ├─ selection: {"<Y>": {method, comparison_years, flat_recovery_rate: {"<m>": float|null}}}
   ├─ counts: {"<Y>": <counts>}            # 選択した経路
   ├─ years: {"<Y>": <metrics>}            # 選択した経路
   ├─ all_test_years: <metrics>            # 選択した経路
   ├─ common_years: {years, selected: <metrics>|null, methods: {"<m>": <metrics>|null}}
   └─ methods: {"<m>": {years: {"<Y>": {available, blend, counts, flat, policy}},
                        available_years, all_available_years: <metrics>|null}}
   ```

   - `<metrics>`はversion 1の`years`の各年と同じキー。`<counts>`はversion 1のキーに`place_width_invalid`を加えたもの。
   - `blend`は合成の方法だけ`{alpha, beta, races, excluded: {market_incomplete, zero_probability, winner_count}, failure}`
     （当てはめに使った前の年の合計、失敗時は`alpha`・`beta`がnull）、他はnull。`available`がfalseの年は`counts`・`flat`・
     `policy`がnull。`flat`は`{bets, hits, stake_yen, receipt_yen, recovery_rate}`。
   - `common_years`は4方法がすべて使える年だけでの、選択した経路と各方法の指標（その年がなければ`years`は空、他はnull）。
   - `bets.parquet`・`races.parquet`は選択した経路で、ADR-043の列の最後に`method`（string、null不可）を加える。

### 計測の結果（2026-11-17、`docs/experiments/ev-betting-backtest.md`）

PLの評価`graded-final3`（test 2016〜2025、`all_columns`）とsnapshot `098ce3f4…`で計測した。`pl_mid`の結果はADR-043の計測と
完全に一致した。合成の係数は`α` 0.68〜0.77・`β` 0.37〜0.45（前の年の全レース2,906〜26,737、除外0件）だった。

- 選ばれた方法: 2016・2017年`pl_mid`（比較の年なし）、2018年`blend_mid`、2019年`blend_width`、2020年`pl_mid`、2021〜2023年
  `blend_mid`、2024・2025年`blend_width`。
- 選択した経路: 331レースを購入し、購入額475,200円・受取額405,760円、全test年の回収率0.854（95%区間0.688〜1.036）。
  ADR-043（`pl_mid`）の0.810（0.670〜0.963）より高いが、区間は1をまたぐ。
- 重賞の定額の回収率（2017〜2025年のpooled）: `pl_mid` 0.529、`blend_mid` 0.668、`pl_width` 0.517、`blend_width` 0.684。
- 4方法が使える2017〜2025年の方策: 選択した経路0.823、`pl_mid` 0.784、`blend_mid` 0.809、`pl_width` 0.706、`blend_width` 0.829。
  合成の方法は単勝をほとんど買わず（3〜4件）、複勝を少数買う。
- 選ばれた複勝の期待的中39.2に対し的中26（`blend_mid`）で、確率の過大さは残る。的中の払戻の和÷`Ô`の和は、選ばれた年が
  異なるが`blend_mid` 0.757、`blend_width` 0.872で、どちらも1を下回る。

偏りは減ったが残り、REQ-02（暦年100%以上）に届くとは判断できない。結果を運用での購入の開始の根拠にしない。

## Rationale

- 合成は、PLの確率が市場より過大なところ（高いオッズの馬）を、市場の確率へ寄せる。係数2つだけを全レースで当てはめるため、
  重賞だけより安定し、重賞の結果を使わない。勝率と2・3着の確率を同じ強さから計算し、券種の間で矛盾しない。
- 複勝の払戻は、同時に3着以内に入る馬で`OddsLow`と`OddsHigh`の間を動く。幅の広い馬では`place_mid`の補正が払戻を
  過大に見積もるため、幅の帯ごとに補正を当てはめる。ADR-042の部品をそのまま使い、帯の統合も同じ規則にする。
- 選択に重賞の定額の回収率を使うのは、方策の対象と同じ母集団で、金額の規則（ケリー・予算）に左右されずに方法の推定の
  良さを比べるためである。
- 前の年だけで選ぶため、各年の判断は後の年の結果に依存しない。最初の年は前の結果がないため、現行の方法になる。

## Consequences

### Positive

- 4方法の年ごとの定額・方策の結果と選択を1回の実行で記録し、事後に各方法を比べられる。
- `pl_mid`はADR-043の結果をそのまま再現する。

### Negative

- 重賞は年に約110レースで、定額の回収率の差は雑音が大きく、選ばれる方法が偶然で決まりうる。
- 2つの候補と幅の帯の値は、2016〜2025年のB4の診断を見た後に決めた。選択した経路の結果は楽観的に偏りうる。
- 2016年は合成を当てはめられず、2016・2017年は必ず`pl_mid`になる。合成の最初の数年は当てはめの年が少ない。
- 実行時間と出力が増える（4方法の候補・定額・方策）。

### Neutral / Follow-on effects

- 当日の購入案への適用（#81）は、どの方法を使うかを含めて別に決める。#82は幅以外の説明変数・学習の窓の比較を続ける。

## Alternatives Considered

### Option A: 評価期間の前（2008〜2015年）のPLの評価を作り、そこで方法を1つに固定する

Summary: PLの評価をtest 2008〜2015年で追加し、その期間で方法を選んでから2016〜2025年に当てる。

Advantages: 評価期間を選択に一切使わない。

Disadvantages: 2008〜2010年は学習の年が短くモデルが弱い。PLの評価の追加の実行が必要。

Reason not selected: GATE 1の前に、評価期間の中で前の年だけで選ぶことを人間が選んだ。

### Option B: 全レースの定額の回収率で選ぶ

Summary: 選択の母集団を中央の全レースにする。

Advantages: 標本が約25倍で、差が出やすい。

Disadvantages: 対象（平地重賞）と母集団が異なる。

Reason not selected: 人間が重賞だけで選ぶことを選んだ。

### Option C: 同時に3着以内に入る馬から複勝の払戻を計算する

Summary: O1の複勝の幅から票の割合を逆算し、PLの3着以内の組合せの確率で、的中したときの払戻の期待値を計算する。

Advantages: 払戻の仕組みに沿う。

Disadvantages: 逆算と丸めの扱いが複雑。

Reason not selected: 人間が幅の帯を加えた補正を選んだ。

## Implementation Notes

- `models/probability/market_blend.py`（新規、numpy）: 合成の当てはめ（Newton法）と確率。
- `models/market/place_width_correction.py`（新規、標準ライブラリ）: 幅・幅の帯・帯ごとの補正。
- `models/serialization/betting_inputs.py`: `FreezeQuotes.place_low`・`place_high`、`PL_BLEND_COLUMNS`、`blend_training_races`。
- `models/experiments/betting_backtest.py`: 年ごとの当てはめ、方法ごとの候補・定額・方策、選択、report version 2、`method`列。
- `configuration/betting_backtest.py`・`configs/betting_backtest/`・`cli/betting_backtest.py`: `estimation`と2つ目の投影。

## Validation

- 単体テスト: 合成の勾配・Hessian（有限差分）・停留点、共線・レース不足、`α=1, β=0`の一致、確率の和。幅の境界の値、
  的中と気配の幅の一致、帯の統合、既存の補正との一致。選択の規則（空・同じ比・0円・使えない方法）、定額（ケリー0円・返還・
  精算できないレース）、合成と幅の保留、後の年の着順・払戻・的中を変えても前の年の当てはめ・定額・方策・選択が変わらないこと。
  `pl_mid`がADR-043（変更前のコード）の固定した結果と一致すること。
- 統合テスト: 2つの投影が予測のhashの照合の間で読まれること、schemaの写し、設定の`estimation`の検査、importの境界。
- 実データでの計測。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 選択の雑音 | 偶然で方法が選ばれる | `common_years`で各方法の固定の結果も並べる。運用の購入の根拠にしない |
| 候補を診断の後に決めた | 結果が楽観的 | 経緯を記録する。運用の購入の根拠にしない |
| 合成の当てはめの失敗 | 合成の方法を使えない | 失敗の理由を`blend.failure`に記録し、選択は使える年だけで行う |
| 幅の帯の値 | 帯が粗い・細かい | 計測の前に固定した。比較は#82 |

## Security / Privacy Impact

外部への送信、認証情報、個人情報は扱わない。

## Operational Impact

評価の経路だけを変え、当日の運用（ADR-041）は変えない。システムは購入を実行しない（REQ-07）。

## Migration / Rollback

### Migration

`model backtest-betting`の設定に`estimation`が必須になる。reportはversion 2になり、表に`method`列が加わる。
このCLIの出力を読むコードはリポジトリにない。

### Rollback

ADR-043のversion 1の実装へ戻す（このADRの変更を取り消す）。

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `docs/rules/architecture.md`
- [x] `README.md`
- [x] `docs/experiments/ev-betting-backtest.md`
- [x] ADR-043（Amendment）

## Follow-up Actions

- [x] 当日の購入案への適用（#81）で、どの推定の方法を使うかを決める（[ADR-045](ADR-045-save-the-betting-estimator-yearly-and-attach-zero-yen-proposals-on-race-day.md)。この規則を当日の年へ延長する）。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-17 | Accepted | GATE 1で人間が候補・選択の規則・ローリングの選択を決め、実データで評価した |
