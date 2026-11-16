# ADR-042: 締切時点のオッズを、的中したときの確定オッズへ補正し、年単位で評価する

- Status: Accepted
- Date: 2026-11-16
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #35、Refs #57・#36・#67・#78・#81・#82
- Supersedes: N/A
- Superseded by: N/A

---

## Context

期待値による購入判断（B4、#36）は、購入時点（freeze、発走5分前、ADR-041）のオッズしか使えない。払戻は確定オッズで決まり、
freezeの後の票で変わる。1円あたりの期待値は`P(的中) × E[確定オッズ | 的中]`なので、B4に必要なのは、組合せが的中したときの
確定オッズの期待値である。

固定snapshot `034f3ff22f5c459abecef756bc0ecc2c`の2021〜2025年（中央01〜10場、17,277レース）で単勝の締切時点のオッズと確定を比べると、
全馬では確定でオッズが上がる（年ごとの中央値1.09〜1.13）が、的中した馬だけでは平均0.97〜0.98で下がる。締切後の票は勝つ馬へ
偏るため、全馬の変動で補正すると期待値を高く見積もる。重賞は全馬の変動が小さい。

締切時点の単勝・複勝・馬連は`ARCHIVE_O1_ODDS_TANFUKUWAKU`・`ARCHIVE_O2_ODDS_UMAREN`の中間発表（`headDataKubun=1`）にあり、
確定の払戻は`NL_HR_PAY`にある。2表は各約1,056万行で、レースごとの述語では読込が遅い。ワイド・馬単・3連複・3連単は発走前の
過去の時系列がない（#67）。

---

## Decision

1. **予測の対象**: 券種`b`・組合せ`c`について、freezeの時点の情報で`E[確定オッズ | cが的中]`を予測する。確定オッズは`NL_HR_PAY`の
   払戻÷100（B4の精算と同じ出典）とする。全組合せの変動ではなく、的中した組合せで学習・評価する。
2. **締切時点のオッズ**: freeze（保存した`HassoTime`−300秒、`REFERENCE_BASES`）以前の最新の中間発表を`latest_o1`で選ぶ。
   freeze−発表が`max_publication_age_seconds`（計測は600）を超える、発表がない、同じ時刻で行が異なる、発表時刻やオッズの形式が
   不正な場合は、
   その(レース, 表)を保留する（O1は単勝・複勝、O2は馬連）。基準のオッズ`O_z`は、単勝は単勝、馬連は馬連、複勝は
   `place_low`（`OddsLow`）と`place_mid`（`√(OddsLow·OddsHigh)`）の2通りとする。
3. **例外**:
   - レースの保留（全券種）: `NL_RA_RACE`の行がない・複数ある、`headDataKubun`が`9`（中止）・`0`（削除）、`HassoTime`の不正、
     freezeが別のJST日付、`NL_HR_PAY`の行がない・複数ある、その`headDataKubun`が`2`以外、`TokubaraiFlag*`・`FuseirituFlag*`の
     どれかが`0`以外（添字と券種の対応は仮定しない）。
   - 的中の除外（理由ごとに数える）: 同着（券種の払戻の件数が通常の件数を超える。単勝・馬連は1件、複勝は出走頭数`SyussoTosu`が
     8頭以上なら3件、5〜7頭なら2件）、`O_z`がない（単勝は`win_quotes`の理由、複勝・馬連は`unquoted`、`OddsHigh`だけない
     `place_mid`は`unquoted_high`）、払戻の組合せがfreezeの発表にない（`no_freeze_quote`）。
   - `HenkanFlag*`（返還）は数えるだけで、的中は使う。払戻の列の形式の誤りは例外とし、保留にしない。
4. **モデル**: 券種ごとに、固定した`O_z`の帯（左閉右開、最後は上限なし）で、学習の的中の比`r = 払戻÷100 ÷ O_z`の算術平均`m_k`と、
   帯の`log O_z`の平均`x_k`（節点）を求める。予測は`log O_z`について節点の間を線形補間した`m(O_z)`で、外側は端の値とし、
   `Ô = m(O_z) × O_z`とする。分位点は帯ごとの`r`の経験分位点（補間しない）とする。
   - `all`（中央の全レースで当てはめ）: 学習の的中が`min_hits`未満の帯は、低い側の帯と順に統合する（最も低い帯は高い側と）。
   - `graded`（平地重賞`jra_flat_graded_stakes_v1`だけで当てはめ）: 同じ帯で`m = (n·m_g + k·m_all(x_k)) / (n + k)`
     （`m_all`は同じfoldの`all`の補間値）。分位点は`n < min_hits`なら`all`の値とする。重賞の的中がない帯のオッズには`all`の倍率と分位点を使い
     （foldに重賞の的中がなければ全体が`all`になる）、ほかのオッズは重賞の的中がある帯の点の間で補間する。
   - `none`は`Ô = O_z`（補正しない）とする。
5. **検証**: test年`Y`ごとに`train_start_year`〜`Y−1`で当てはめ（拡大型）、`Y`で評価する。testの払戻は採点だけに使う。
   評価の部分集合は全レースと`jra_flat_graded_stakes_v1`とする。主指標は`payout_ratio = Σ(払戻÷100) / ΣÔ`と
   `mean_payout_ratio = mean(払戻÷100 ÷ Ô)`で、区間はレース単位のbootstrapで求める。
6. **採否の規則（計測の前に固定）**: 券種ごとに、重賞の全test年（2016〜2025）のpooledで、`payout_ratio`と`mean_payout_ratio`の
   95%区間がともに1を含むvariantを「適合」とする。`graded`は、適合し`all`が適合しないときだけ採る。それ以外は`all`が適合すれば
   `all`を採る。どちらも適合しなければ、その券種は「未採用」とし、B4はそのまま使わない。2016〜2020年の値も併記し、規則の結果が
   変わる場合は計測の記録に明記する。
7. **B4での使い方**: 組合せの1円あたりの期待値は`P(的中) × Ô`とする。`P(的中)`はPLの確率（ADR-039）で、複勝はfreezeの出走頭数が
   8頭以上なら3着以内、5〜7頭なら2着以内の確率を使い、4頭以下は対象外とする。分位点`r_q × O_z`は払戻のばらつきの目安とする。
   #36のバックテストは、各foldで同じ当てはめの関数をそのfoldの学習年だけに使う。成果物の保存と当日の適用は#81で決める。
8. **範囲と境界**: 単勝・複勝・馬連だけを扱う。`models/market/`は市場オッズそのものを対象とする純粋な推定だけを置き、
   I/O・CLI・`data`をimportしない。評価の経路は`model evaluate-final-odds`とし、出力は`report.json`
   （`format: "final_odds_evaluation"`、`format_version: 1`）だけとする。

### 計測の結果（2026-11-16、`docs/experiments/final-odds-correction.md`）

決定6の規則で、複勝`place_mid`は`graded`を採用し、単勝・複勝`place_low`・馬連は未採用とした。重賞の全test年の`payout_ratio`は、
単勝`all` 0.961 [0.946, 0.976]、`place_low` `graded` 0.983 [0.972, 0.996]、`place_mid` `graded` 0.996 [0.984, 1.008]、
馬連`all` 0.926 [0.895, 0.953]である。2016〜2020年だけでは、`place_low`・`place_mid`とも`all`が採用になり、結果が期間で変わる。

---

## Rationale

的中を条件とする比は、B4の期待値の式にそのまま入る。全馬の変動で補正すると、勝たない馬のオッズの上昇を的中の払戻に持ち込む。
帯ごとの平均と節点の補間は、少ない仮定で`O_z`に対する偏りを表し、当てはめの表をreportに残して検査できる。重賞は全レースと
変動が違うが的中が少ないため、全レースの値へ縮小する。採否の規則を計測の前に固定し、設計で見た期間（2021〜2025年の単勝）と
見ていない期間を分けて示すことで、規則を結果に合わせて選ぶことを防ぐ。

読込は、年ごとにキー・区分・発表時刻だけを読み（pass 1）、各レースのfreeze以前の最新の時刻と、`latest_o1`の結果を変えうる時刻
（同じ時刻の複数行、不正な時刻）を選び、その行だけを読む（pass 2）。全行を読んだ場合と同じ選択・保留になり、22年分の読込（pass 1・2）は約261秒だった。

---

## Consequences

### Positive

- B4は、購入時点のオッズを、券種ごとに偏りを検査した確定オッズの予測へ置き換えられる（採用した券種）。
- 補正しない複勝`OddsLow`の大きな偏り（重賞で確定を約18%低く見積もる）を、計測で示した。

### Negative

- 単勝・馬連は、補正しても重賞で`payout_ratio`が1より小さく（期待値を4〜8%高く見積もる）、規則で未採用となった。
  高いオッズの帯で、重賞の確定までの変動が全レースと違うことによる。
- 採否の結果が期間で変わる。採用した`place_mid`の`graded`と`all`の差は小さい。
- 10〜90%区間の被覆が、test年で目標の0.8より低い券種がある（全レースの馬連で0.57）。

### Neutral / Follow-on effects

- 未採用の券種をB4でどう扱うか（補正しない`O_z`を使う、安全余裕を置く、使わない）は#36で決める。
- 成果物の保存と当日の適用は#81、説明変数・発表の古さ・学習の窓の比較は#82で扱う。

---

## Alternatives Considered

### Option A: 全組合せの確定オッズの変動を予測する

- 利点: 的中しない組合せも使え、学習の件数が多い。
- 欠点: 締切後の票が勝つ組合せへ偏るため、期待値を高く見積もる（Context）。
- 不採用理由: B4に必要なのは的中を条件とする値である。

### Option B: 勾配ブースティングなどで説明変数を増やす

- 利点: 頭数・票数・オッズの推移・モデルと市場の差を使える。
- 欠点: 当てはめの検査が難しく、重賞の的中が少ない。最初の採否の基準がない。
- 不採用理由: まず帯の補正の偏りを測る。比較は#82で行う。

### Option C: 補正せずに締切時点のオッズを使う

- 利点: 当てはめが要らない。
- 欠点: 複勝は`OddsLow`・`OddsHigh`のどちらを使っても偏り、単勝・馬連も帯ごとに偏る。
- 不採用理由: `none`として毎回同じ評価で比べ、採否の判断材料に残す。

---

## Implementation Notes

- `models/serialization/final_odds_observations.py`: freeze、pass 2で読む対の選択、1レースの的中・保留・除外の組立（純粋）。
- `models/market/final_odds_correction.py`: 帯の当てはめ・統合・縮小・補間・分位点（純粋、標準ライブラリだけ）。
- `models/evaluation/final_odds_metrics.py`: 指標、帯ごとの集計、レース単位のbootstrapと対応ありの差。
- `models/experiments/final_odds_evaluation.py`: 年fold、variant×部分集合×券種の指標、採否、`report.json`の内容（I/Oなし）。
- `data/loader/fixed_snapshot.py`の`publication_reader`: datasetを1回だけ開き、`scan(year)`と`read_pairs(year, pairs)`を持つ。
- `configuration/final_odds_evaluation.py`、`configs/final_odds_evaluation/`、`cli/final_odds_evaluation.py`。
- `make_features/reference_snapshot.py`の`_quote`を`decimal_odds`として公開した（動作は変えていない）。

---

## Validation

- 単体テスト: 観測の組立（freezeの分ちょうど、区分、12月の発表、保留と除外、pass 2の選択が全行と同じ`latest_o1`の結果になること）、
  当てはめ（補間、統合、縮小、分位点の切替え）、指標とbootstrap（レース単位、対応あり）、年fold（`Y`以後の払戻で当てはめが変わらない）、
  採否の4通り。
- 統合テスト: 年を混ぜた小さなrow groupのParquetでの`scan`・`read_pairs`、小さな複数年の固定snapshotでのCLIの`report.json`が
  純粋関数を直接呼んだ結果と一致すること、helpとimportの境界、設定と出力の拒否、失敗時にstagingを残さないこと。
- 実データの計測: `docs/experiments/final-odds-correction.md`。

---

## Risks

- 帯の補間は頭数・票数などの違いを無視する。重賞だけの当てはめは的中が少なく、縮小に頼る。
- freezeは保存した`HassoTime`、発表時刻は`HappyoTime`（分の分解能、受信時刻ではない）に基づく（ADR-030と同じ仮定）。
- 過去の締切時点のオッズはほぼ6分前の発表だが、当日は11分前の発表になることがある（#78）。古い発表からの変動は大きく、
  補正が足りない場合がある（#82）。
- 的中を条件とした比は、モデルが選ぶ買い目での比と同じとは限らない（選択による偏り）。#36のバックテストで確かめる。
- 特払い・不成立の旗があるレースは全券種を保留する。計測では該当がなかった。
- 複勝の通常の払戻の件数は確定の出走頭数`SyussoTosu`で決めるため、発売後の取消・除外で頭数が減ったレースでは
  通常の払戻を同着として除く（計測では42レース、複勝の的中の約0.05%）。
- 年の述語によるrow groupの読み飛ばしは、ファイルが年ごとにまとまっていることに依存する。計測では1年あたりO1が3.5〜6.4秒、O2が4.0〜7.5秒だった。

---

## Security / Privacy Impact

外部への送信、認証情報、個人情報は扱わない。固定snapshotを読み、新しい出力ディレクトリへ`report.json`だけを書く。

---

## Operational Impact

評価の経路だけを加え、当日の運用の手順（ADR-041）は変えない。実データの計測は約7分（433秒）かかった。

---

## Migration / Rollback

### Migration

不要。既存のCLI・出力形式・datamart・モデルは変えない。

### Rollback

追加したモジュール・設定・CLIの登録を取り除けば戻る。保存された成果物はない。

---

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `docs/rules/architecture.md`
- [x] `docs/specification.md`
- [x] `README.md`
- [x] `docs/table-definition/NL_HR_PAY.md`
- [x] 実験の記録（`docs/experiments/final-odds-correction.md`）

---

## Follow-up Actions

- [ ] 補正の成果物の保存と、当日の購入案への適用（#81、#36と合わせて設計）。
- [ ] 発表の古さ・説明変数・学習の窓の比較（#82）。
- [ ] 未採用の券種のB4での扱いを決める（#36）。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-16 | Accepted | 的中を条件とした帯ごとの補正と採否の規則を定め、実データで`place_mid`の`graded`だけを採用した |
