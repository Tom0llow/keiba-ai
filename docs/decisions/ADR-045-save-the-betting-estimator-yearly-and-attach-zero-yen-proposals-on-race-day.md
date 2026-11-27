# ADR-045: 確定オッズの補正と推定の方法を年ごとの成果物にし、当日の重賞へ0円の購入案を付ける

- Status: Accepted
- Date: 2026-11-17
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #81、Refs #57・#36・#56・#78・#82
- Supersedes: N/A（ADR-042のRollbackの「保存された成果物はない」は、このADRで成果物を保存するため当てはまらなくなる）
- Superseded by: N/A（決定4の最後の項・待ちと保留の理由、決定5のformat_version・`decision.outcome`・stdoutのキーは[ADR-046](ADR-046-record-actual-purchases-and-cap-proposals-by-them.md)が改めた）

---

## Context

ADR-042〜044は、確定オッズの補正とPLと市場の合成を、test年ごとに当てはめて評価するだけで、当てはめた値を保存しない。
当日の予測（ADR-039の`model predict-pl-live`）は重賞の着順確率を公開するが、期待値と購入案を付けない。

バックテストは損失を示した。ADR-043の固定の方策は2016〜2025年の重賞で回収率0.810（95%区間0.670〜0.963）、ADR-044の選択した
経路は0.854（0.688〜1.036）である。ロードマップ（#57）では、購入案は0円（提示のみ）のままとしている。

GATE 1の前に人間が決めた（2026-11-17）:

1. 推定の方法は、ADR-044の規則を当日の年へそのまま延長して選ぶ。
2. 提示する購入額は0円とし、方策の参考の要求額を記録する。年間の残りは扱わない（#56）。
3. 券種は単勝・複勝だけとする（馬連は扱わない）。
4. 当日の適用は新しい常駐CLIとし、`pl_race_prediction`と`model predict-pl-live`の振る舞いは変えない。

## Decision

1. **当日の年と当てはめ**: 当日の年`T`は、バックテストのreportの最後のtest年+1とする。`T`の推定器は、バックテストの
   `fit_year_estimators(T, …)`で当てはめる（`place_mid`の`graded`補正と幅の帯の補正は`train_start_year`〜`T−1`の全レースの的中、
   合成はPLの評価の全test年の予測）。値はバックテストの`config`（hashで固定したreportの記録）からだけ取り、設定ファイルを持たない。
   読む期間は`T−1`の12月31日までに限る。
2. **方法の選択**: ADR-044決定4の規則（`models/betting/methods.py`の`select_method`）を`T`に当てる。比較の年は、reportのtest年の
   うち4方法がすべて使える年で、値はreportの定額の`(receipt_yen, stake_yen)`である。選んだ方法が合成で、`T`の合成が使えなければ
   `pl_mid`とする。reportの各年の`selection`も、reportの定額の結果から計算し直して一致しなければ、成果物を作らない。
3. **成果物`ev_betting_estimator` format_version 1**: ディレクトリにちょうど`manifest.json`を置き、識別はそのバイト列のSHA-256で行う。
   キーは`format`・`format_version`・`target_year`・`method`・`selection`（比較の年と方法・年ごとの定額）・`policy`（ADR-043の6つの値）・
   `final_odds`（ADR-042の値、`train_end_year = T−1`、的中の数）・`place_mid`（`graded`とその`all`補正の全field）・`place_width`
   （0.1刻みの整数の幅の帯・統合した群・群ごとの的中の数と補正）・`blend`（係数・失敗の理由・除外の数・当てはめの年・設定）・`sources`
   （バックテストのreport・PLの評価・snapshotの3表のSHA-256。絶対パスは入れない）・`provenance`である。
   - 書込みは、読込と同じ規則で検証した後にだけ書く（`pl_model.py`と同じ契約）。読込は、キー・型・定数・帯の分割・幅の帯・
     年の順序（すべて`T`より前）・方策の検査に加え、`selection`から決定2で方法を計算し直して一致することを要求する。
   - CLI `model fit-betting-estimator`（`--backtest`・`--backtest-report-sha256`・`--pl-evaluation`・`--processed-root`・`--output`）は、
     reportのhash・`config`（`configuration/betting_backtest.py`と同じ検査）・PLの評価の2ファイルのhash・snapshotの`NL_RA_RACE`・
     `NL_HR_PAY`・O1のhashを照合してから読む。stagingの成果物を読み直し、全的中で推定値と係数が当てはめと完全に一致することを
     確かめてから公開する。失敗時（Ctrl+Cを含む）は何も残さない。`ev_betting_backtest` format_version 2のreportは、この入力の契約になる。
4. **当日の購入案**: 常駐CLI `model propose-bets-live`は、`predict-pl-live`と同じ出馬表の重賞を、freezeの後に
   `<predictions-root>/<race_id>/prediction.json`の公開を待って計算する。発売締切より後になっても予測がなければ
   `prediction_not_published`で保留する。締切の後に見つけた予測は計算し、`after_sales_close: true`を記録する。
   - 起動: 成果物の`target_year`が`--date`の年と違えば、`--output`を作らずに終了する（年ごとに作り直す）。PLのモデル（特徴量の
     列の定義と識別）と固定snapshotを、`predict-pl-live`と同じ値で読む。
   - 1レースの検査（違反はそのレースの保留、段階`proposal`）: 予測の形式・予定・確率の範囲・順序・和（`prediction_invalid`）、
     モデルとsnapshotの識別（`prediction_mismatch`）、市場がレース別の取得であること（`market_source_unsupported`）と、そのレース・
     freezeであること（`market_source_mismatch`）、特徴量の読込（`features_invalid`）、取得のversionのO1の読込（`market_source_unavailable`）と
     hash（`market_source_mismatch`）、ADR-042決定2のfreezeの気配（`stale_publication`・`invalid_publication`など）、その他の解析の誤り
     （`market_invalid`）、公開の失敗（`publish_failed`）。予測の馬番と`horse_id`は、固定した出馬表の対応と一致しなければならない。
   - バックテストと同じ照合と計算: 予測・特徴量・O1の馬の集合（`entrant_mismatch`）、特徴量の`market_win_odds`とfreezeの単勝オッズ
     （`market_odds_mismatch`）、方法ごとの確率（合成は特徴量の`market_win_odds`を使い、`blend_market_incomplete`・
     `blend_zero_probability`）と候補（バックテストの`race_bet_candidates`）。気配のない馬は単勝の候補を作らない。
   - 方策はそのレースの候補だけに当てる（年間の残りは常に`annual_budget_yen`で、1レースの上限だけが効く）。
5. **出力`ev_race_proposal` format_version 1**: `<output>/<race_id>/proposal.json`を`publish_directory`で公開する（キーを並べ替えた
   ASCIIのJSON、NaNなし）。キーは`format`・`format_version`・`computed_at`・`after_sales_close`・`race`・`snapshot`・`prediction`
   （読んだ`prediction.json`のSHA-256、モデルと特徴量の識別）・`estimator`（識別・`target_year`・`method`）・`market`（取得のversion・
   O1のSHA-256・発表の古さ）・`policy`・`horses`（馬ごとの確率・単勝と複勝の`O`・`Ô`・`R`、複勝を作らない理由）・`bets`（要求額が
   正の買い目すべて。`requested_stake_yen`、上限で縮小した`reference_stake_yen`（0円もそのまま残す）、`stake_yen`は常に0）・
   `decision`（`no_eligible_bet`か`reference_bets`、縮小の有無、参考額の合計、`stake_yen` 0）・`provenance`である。stdoutは1レース1行の
   JSON（`race_id`・`status`（`proposed`・`held`・`out_of_scope`）・`stage`・`reason`・`detail`・`output`・`after_sales_close`・`bets`・
   `reference_stake_yen`）、stderrに要約を出す。終了コードは0・1・130で、公開済みのレースは残す。
6. **配置**: 方法の名前と選択は`models/betting/methods.py`（標準ライブラリだけ）。バックテストの当てはめ・確率・候補は
   `models/experiments/betting_backtest.py`の公開名の関数とし、成果物の当てはめ（`models/experiments/betting_estimator.py`）と
   購入案（`models/experiments/bet_proposal.py`）がそれを呼ぶ。成果物は`models/artifacts/betting_estimator.py`。CLIは他のCLIを
   importしないよう、`fit-betting-estimator`を`cli/betting_backtest.py`、`propose-bets-live`を`cli/pl_prediction.py`に置く。

### 計測の結果（2026-11-17、`docs/experiments/ev-betting-backtest.md`）

`output/ev-betting-estimates-2016-2025-r6`（ADR-044の計測）から2026年の成果物を作った（160〜210秒）。方法は`blend_width`（比較の年
2017〜2025、定額の回収率は`pl_mid` 0.529・`blend_mid` 0.668・`pl_width` 0.517・`blend_width` 0.684）、合成の係数は`α` 0.6815・
`β` 0.4534（2016〜2025年の29,754レース）、`place_mid`の的中は226,408件である。2026-11-15の重賞1レースを再生し、複勝1点に
参考額1,800円の購入案（提示額0円）を公開した。

## Rationale

- バックテストの関数と値をそのまま使えば、当日の購入案は評価した方法と同じ計算になる。成果物を作るたびに読み直して推定値を
  照合するため、保存の誤りが当日に持ち込まれない。
- 方法の選択はADR-044の規則を変えずに延長した。各年の判断は前の年の結果だけを使うため、`T`の選択も`T`のデータを使わない。
- 提示額を0円に固定し、参考額を別の列にすると、方策の振る舞いを当日に記録しつつ、損失を示したバックテストの方策で購入を促さない。
- 新しい常駐CLIにすると、`pl_race_prediction`の形式と`predict-pl-live`を変えずに済む。予測と購入案は`race_id`で突き合わせられる。

## Consequences

### Positive

- 当日の重賞ごとに、確率に加えて単勝・複勝の期待受取倍率と方策の参考額が記録され、事後に確定の払戻と比べられる。
- 成果物はhashで固定され、作成に使ったreport・PLの評価・snapshotの表のhashを記録する。

### Negative

- 当日の手順に端末が1つ増える。`predict-pl-live`を別の`--output`で再起動したら、購入案のCLIも再起動する必要がある。
- 合成の係数は、PLの評価のfoldのモデルの予測で当てはめるが、当日は最終モデル（ADR-038）の予測に当てる。
- 成果物は年ごとに作り直す必要がある（年の違う成果物では起動しない）。
- 予測の保留や締切の後の予測は、購入案のCLIでは`prediction_not_published`になり、本当の理由は`predict-pl-live`のstdoutにある。

### Neutral / Follow-on effects

- 実購入額の記録と年間の枠は#56、古い発表（約2割のレースでfreezeの約6分前の発表）の扱いは#78、補正の改良は#82で扱う。

## Alternatives Considered

### Option A: `predict-pl-live`を拡張して`prediction.json`に期待値を加える

Summary: 成果物を任意の引数で受け取り、`pl_race_prediction`をformat_version 2にする。

Advantages: プロセスが増えない。

Disadvantages: 既存の永続形式と常駐CLIを変える。

Reason not selected: GATE 1の前に人間が新しい常駐CLIを選んだ。

### Option B: `pl_mid`に固定する

Summary: ADR-043の現行の方法だけを保存する。

Advantages: 成果物が小さく、合成を当日に当てない。

Disadvantages: バックテストで最も偏りが大きかった方法になる。

Reason not selected: 人間がADR-044の規則の延長を選んだ。

### Option C: 馬連も補正なしで参考に出す

Summary: freezeの馬連オッズとPLの馬連の確率から`R`を出す。

Advantages: 券種が増える。

Disadvantages: ADR-042で補正が未採用で、方策の対象外である。O2の読込が増える。

Reason not selected: 人間が単勝・複勝だけを選んだ。

## Implementation Notes

- `models/betting/methods.py`（新規）、`models/artifacts/betting_estimator.py`（新規）、`models/experiments/betting_estimator.py`（新規）、
  `models/experiments/bet_proposal.py`（新規）。
- `models/experiments/betting_backtest.py`: `fit_year_estimators`・`width_observations`・`method_available`・`method_probabilities`・
  `race_bet_candidates`・`YearEstimators`を公開名にした（振る舞いは変えない）。
- `models/betting/policy.py`: `requested_bet`を公開名にした。`models/market/final_odds_correction.py`: `graded`の`all`補正の読取りと構築。
- `configuration/betting_backtest.py`: `validate_betting_backtest_config`を公開した。
- `cli/betting_backtest.py`: 的中の観測と重賞の集合の読込を関数にし、`fit-betting-estimator`を加えた。`cli/pl_prediction.py`: 監視の
  ループを結果の型と未公開の保留によらない形にし、`propose-bets-live`を加えた。

## Validation

- 単体テスト: 選択の規則（空・同じ比・0円・使えない方法）、`T`の当てはめがバックテストの`T`年の当てはめと一致すること、`T`以後の
  データで成果物が変わらないこと、reportの検査、購入案の候補と参考額がバックテストの候補と方策に一致すること（4方法）、0円に縮小した
  買い目が残ること、保留の理由。
- 統合テスト: 成果物の往復（帯の境界・空の帯・範囲の外の推定値の一致）と拒否、バックテストのCLIの出力からの成果物の作成と拒否、
  `predict-pl-live`の出力に対する`propose-bets-live`（締切の前後、未公開の保留、1レースの保留で他が続くこと、年の違う成果物）、helpと
  importの境界、CLIのモジュールが互いにimportしないこと。
- 実データ: 2026年の成果物の作成と、2026-11-15の重賞の再生。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 参考額を購入の根拠と誤解する | 損失 | `stake_yen`を常に0とし、文書で参考額の扱いを明示する |
| 古い発表（#78） | 補正の当てはめより古いオッズで期待値を計算する | `market.publication_age_seconds`を記録する。閾値は#78で決める |
| foldの予測で当てはめた合成を最終モデルに当てる | 確率の分布が少し違う | 年ごとの作り直しと事後の照合で確かめる |
| 2つの常駐CLIの値の食い違い | 全レースの保留 | 同じ`--snapshot-id`・`--features-root`・`--pl-model`を文書の手順で使う |

## Security / Privacy Impact

外部への送信、認証情報、個人情報は扱わない。購入は実行しない（REQ-07）。

## Operational Impact

前日までに成果物を作り（年に1回、約3〜3.5分）、当日は4つ目の端末で`model propose-bets-live`を起動する（`docs/race-day-operation.md`）。

## Migration / Rollback

### Migration

なし。新しい成果物・CLI・出力だけを加え、既存の出力形式は変えない。

### Rollback

2つのCLIと新しいモジュールを削除し、公開名にした関数を戻せば戻る。

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `docs/rules/architecture.md`
- [x] `README.md`
- [x] `docs/requirements.md`
- [x] `docs/specification.md`
- [x] `docs/race-day-operation.md`
- [x] `docs/experiments/ev-betting-backtest.md`
- [x] ADR-042・043・044のFollow-up

## Follow-up Actions

- [x] 実購入額の記録と年間の枠（#56、[ADR-046](ADR-046-record-actual-purchases-and-cap-proposals-by-them.md)）。
- [ ] 古い発表の扱い（#78）。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-17 | Accepted | GATE 1で人間が方法の延長・0円の提示・券種・常駐CLIを決め、2026年の成果物と2026-11-15の再生で確かめた |
| 2026-11-18 | Accepted | ADR-046が実購入額の台帳による上限と`ev_race_proposal` format_version 2で決定4・5の一部を改めた（人間の承認、#56） |
| 2026-11-26 | Accepted | [ADR-051](ADR-051-add-calculated-card-and-history-columns-and-decide-at-the-yearly-rebuild.md)の決定6が、決定4の起動の検査に、推定器の`sources.pl_evaluation.variant`とPLモデルの`features.variant`の一致を加えた。違えば`--output`を作らずに終了する（#83） |
