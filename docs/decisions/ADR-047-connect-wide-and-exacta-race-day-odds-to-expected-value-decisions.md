# ADR-047: ワイド・馬単の当日オッズを期待値の判断へ接続する方式と蓄積の目標を決める

- Status: Accepted
- Date: 2026-11-20
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #67、Refs #57・#35・#36・#37
- Supersedes: N/A
- Superseded by: N/A（決定6の「その年の固定したPLモデル」は、[ADR-048](ADR-048-rebuild-and-retrain-once-a-year-after-the-last-race-day.md)の決定7が「その開催日に結び付いたPLモデル」に改めた）

---

## Context

[ADR-032](ADR-032-capture-race-day-odds-for-all-bet-types.md)により、race-day-oddsは`0B31`〜`0B36`を発走の30・10・5・2分前に取得し、
`ARCHIVE_CAPTURE_O1`〜`O6`と`ARCHIVE_CAPTURE_LOG`へ保存する。ワイド・馬単の過去の締切時点のオッズは取得できず、確定オッズと
払戻だけがある。単勝から組合せのオッズを推定すると、確定時でも誤差の中央値が26〜45%あり、期待値の判断には使えないことは
[単勝オッズからの連勝式オッズ推定誤差と締切後のオッズ変動](../experiments/exotic-odds-estimation-error.md)で確認した。

期待値の方策は[ADR-043](ADR-043-fix-an-expected-value-win-and-place-policy-and-backtest-graded-races.md)、確率の方法は
[ADR-044](ADR-044-select-a-selection-bias-estimate-each-year-from-earlier-graded-flat-results.md)、当日の購入案は
[ADR-045](ADR-045-save-the-betting-estimator-yearly-and-attach-zero-yen-proposals-on-race-day.md)で単勝・複勝だけを扱う。締切時点から
確定オッズを予測する補正は[ADR-042](ADR-042-correct-closing-odds-to-hit-conditional-final-odds.md)にあるが、ワイド・馬単には適用していない。

GATE 1の前に人間が決めた（2026-11-20）:

1. 成果物は、方式と蓄積の目標の決定だけとする。購入案への接続と、補正・評価のコードは実装しない。
2. 最小運用の期待値の判断の対象はワイドと馬単とする。3連複・3連単の取得と保存は続ける。
3. 補正の当てはめと方策の評価は中央の全レースで行う。重賞は、ADR-042と同じく全レースへ縮小して扱う。

設計の前の計測と蓄積の下限の見積もりは、[ワイド・馬単の期待値の判断へ接続するための当日オッズの蓄積目標](../experiments/exotic-ev-accumulation.md)に記録する。

## Decision

1. **対象**: ワイド（`ARCHIVE_CAPTURE_O3_ODDS_WIDE`、`0B33`）と馬単（`ARCHIVE_CAPTURE_O4_ODDS_UMATAN`、`0B34`）を対象にする。
   - 3連複・3連単は、必要な蓄積が数十〜百年以上になるため、最小運用の期待値の判断から外す。race-day-oddsの取得と保存は、ADR-032のまま続ける。
   - 単勝・複勝の方策（ADR-043〜046）は変えない。
2. **freezeのオッズ**: レースのfreezeは、ADR-042と同じく保存した`HassoTime`−300秒とする。次の条件をすべて満たす`0B33`・`0B34`の取得のうち、`HappyoTime`が最も新しいものを、そのレースのfreezeのオッズとする。
   - 取得記録のそのDataSpecの`status`が`archived`である。
   - `HappyoTime`がfreeze以前である。
   - freeze−`HappyoTime`が600秒以下である。これはADR-042の`max_publication_age_seconds`と同じである。

   条件を満たす取得がなければ、そのレース・券種は保留とする。

   - 今の予定では、5分前の取得（発表はfreezeの1分前）が通常の取得になる。それが欠けたときは、10分前の取得（6分前の発表）が代わりになる。
   - 2分前の取得は、発表がfreezeの後なので使わない。
   - 使った取得の`capture_id`・`started_at`・`completed_at`・`HappyoTime`を、時点の証跡として記録する。発表がfreeze以前であることを、採否の基準にする。受信がfreezeの後であることは、予測用の取得（ADR-037）と同じく許す。
3. **基準のオッズ`O_z`**:
   - ワイドは複勝と同じく`wide_low`（下限）と`wide_mid`（下限と上限の幾何平均）の2通りとする。
   - 馬単はそのオッズとする。
   - 気配のない組合せは作らない。
4. **確率**: PLの勝率`p_win`を強さ`s = log p_win`とみなし、PLの組合せ確率を使う。
   - 馬単（i→j）は`p_i · p_j / (1 − p_i)`とする。
   - ワイド（i, j）は、2頭がともに3着以内に入るPLの確率とする。
   - 確率の方法の選択（ADR-044の合成など）は、評価の段階で決める。
5. **補正**: 券種ごとに、ADR-042の決定4と同じ帯の倍率のモデルで、`E[確定オッズ | 的中]`を予測する。
   - 確定オッズは`NL_HR_PAY`の払戻÷100とする。
   - ADR-042決定3の規則（レースの保留: 特払い・不成立など、的中の除外: 同着など、返還は数えて的中は使う）をワイド（同着のない払戻の件数は頭数によらず3件で、3件を超えれば同着とする）と馬単へ当てる。詳細は実装のIssueで決める。
   - 当てはめは中央の全レースで行う。重賞は、`graded`の縮小（`k`）で扱う。
6. **評価**: 方策はADR-043の値（`R ≥ 1.10`かつ`Ô > 1`、ケリーの1/4、1レース5,000円・年100,000円）を変えずに使う。
   - 定額の評価（ADR-044決定4）で、中央の全レースの回収率を、レース単位のbootstrapの95%区間とともに出す。
   - 評価は、開催日の順のwalk-forwardで行う。ある開催日の補正は、その日より前の開催日の的中だけで当てはめる。
   - 全レースのPL確率は、当日に公開した参考特徴量と、その年の固定したPLモデルから、後で計算する。重賞以外の予測は、当日には出さない。
7. **蓄積の目標（ゲート）**:
   - ゲートA（補正の当てはめ）: 券種ごとに、freezeのオッズがある的中が1,000件以上とする。帯を10、帯ごとに`min_hits` 100とする目安である。全レースを取得できた日（36レース）で、ワイドは約10日、馬単は約28日に当たる。
   - ゲートB（方策の評価）: 定額の評価の対象が、必要な買い目の数以上とする。ワイドは6,931、馬単は42,191であり、全レースで1レース1点として、ワイドは約2年、馬単は約12年に当たる。
   - 購入案への接続は、ゲートBに達し、回収率の95%区間の下限が1以上になるまでしない。
8. **運用の要件**:
   - 開催日はrace-day-oddsを全レースで動かし、5分前の取得を欠かさない。
   - 特徴量の常駐CLIの出力（全レースの参考特徴量）を消さずに残す。
   - 払戻は次の`latest`で取り込む。
9. **見直し**: ゲートAに達した時点で、補正の当てはめと評価を実装する。必要な数は、実測の分散で見積もり直す。

## Rationale

保存した当日オッズを使えば、単勝からの推定の構造的な誤差を避けられる。freeze以前に発表された値だけを使い、その取得記録を残すことで、
後の補正と評価で時点を検証できる。

ワイドと馬単は、3連複・3連単より蓄積の下限が短い。全レースのPL確率を後で計算し、補正・評価を開催日の順に分けることで、当日に
公開しないレースも含めつつ未来の情報を使わない評価にする。

## Consequences

### Positive

- ワイド・馬単の期待値の判断に必要なfreezeのオッズ、時点の証跡、補正、評価、蓄積のゲートが一貫する。
- 当日の公開を重賞だけに保ったまま、中央の全レースを補正と評価に使える。

### Negative

- ゲートBまで、ワイドは約2年、馬単は約12年かかる下限の見積もりである。
- 取得が欠ける日や長いオッズを選ぶ方策では、実際の蓄積期間はさらに延びる。
- ゲートAの後に補正が使えないと分かれば、期待値の判断へ接続できない。

### Neutral / Follow-on effects

- 購入案は単勝・複勝のまま提示額0円とする。
- 3連複・3連単は期待値の判断から外すが、race-day-oddsの取得と保存は続ける。

## Alternatives Considered

### Option A: 単勝からの推定

Summary: 単勝のオッズからワイド・馬単のオッズを推定して期待値を判断する。

Advantages: 蓄積を待たずに始められる。

Disadvantages: 確定時でも誤差の中央値がワイドで26%（馬連28%、3連単45%。馬単は計測していない）あり、期待値の判断に使えない。

Reason not selected: 誤差のため不採用とした。

### Option B: 3連複・3連単を含める

Summary: ワイド・馬単と同じ方式で3連複・3連単も期待値の判断の対象にする。

Advantages: 取得した券種をすべて使える。

Disadvantages: 必要な蓄積が数十〜百年以上になる。

Reason not selected: 蓄積の年数のため不採用とした。

### Option C: 重賞だけで評価する

Summary: 補正と方策の評価を重賞だけで行う。

Advantages: 当日の公開対象と評価対象が同じになる。

Disadvantages: 年約130レースで評価できない。

Reason not selected: 評価できないため不採用とした。

### Option D: 今すぐ購入案へ接続する

Summary: 蓄積の前にワイド・馬単を当日の購入案へ加える。

Advantages: 購入案の対象を早く広げられる。

Disadvantages: 補正も評価もない。

Reason not selected: 補正も評価もないため不採用とした。

## Implementation Notes

- この決定では、新しいADRと実験の記録だけを追加する。取得・特徴量・PL・購入案・バックテストのコードは変更しない。
- ゲートAに達した後のIssueで、決定2〜6の実装と蓄積の進み具合の集計を行う。

## Validation

- 文書の相互参照は、ADR-032・ADR-042・ADR-043・ADR-044・ADR-045と実験の記録を指す。
- 実装の検証は、ゲートAの後のIssueで決定2〜6を実装するときに行う。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 必要な買い目の数が下限の目安にとどまる | 方策の評価に必要な蓄積が増える | ゲートAの後に実測の分散で見積もり直す |
| 馬単の蓄積に約12年かかる | 評価が大きく遅れる | ワイドを先に評価する |
| JVLinkAgentの停止などで取得が欠ける | ゲートまでの日数が延びる | 開催日に5分前の取得を欠かさない |
| 補正後も回収率が1に届かない | 購入案へ接続できない | ゲートAの後に補正を測定し、必要ならこのADRを見直す |
| 特徴量の出力を消す | その日は評価に使えない | 全レースの参考特徴量を残す |

## Security / Privacy Impact

取得記録と特徴量の出力にはサービスキーを含めない。外部への送信と自動購入はしない。

## Operational Impact

開催日はrace-day-oddsを全レースで動かし、5分前の取得を欠かさない。特徴量の常駐CLIの出力とrace-day-oddsの取得記録を、
ADR-047の評価のために消さずに残す。払戻は次の`latest`で取り込む。

## Migration / Rollback

### Migration

コード・設定・永続データの変更はない。

### Rollback

この決定を見直す場合は、新しいADRで置き換える。取得済みの`ARCHIVE_CAPTURE_*`と取得記録は残す。

## Documentation Changes

- [x] `docs/decisions/ADR-047-connect-wide-and-exacta-race-day-odds-to-expected-value-decisions.md`
- [x] `docs/experiments/exotic-ev-accumulation.md`
- [x] `docs/decisions/ADR-032-capture-race-day-odds-for-all-bet-types.md`
- [x] `docs/race-day-operation.md`

## Follow-up Actions

- [ ] ゲートAに達した後、ワイド・馬単のfreezeのオッズの選択、補正の当てはめ、定額の評価、蓄積の進み具合の集計を実装する。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-20 | Accepted | 人間が成果物・対象の券種・評価の範囲を決め、GATE 1でfreezeのオッズの選び方・補正・評価・蓄積の目標を承認した（#67） |
| 2026-11-21 | Accepted | ADR-048の決定7が、決定6の「その年の固定したPLモデル」を「その開催日に結び付いたPLモデル」に改めた（年1回の切替・前年の版での運用・臨時の作り直しで、同じ年に複数のモデルがありうるため。#55） |
