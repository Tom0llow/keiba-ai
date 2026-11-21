# ワイド・馬単の期待値の判断へ接続するための当日オッズの蓄積目標

状態: 2026-11-20の設計の前の読み取り専用の計測。方式と蓄積の目標を決めるため、払戻と取得記録を集計した。
個別レースの値は記録しない。結果は購入方策の採用判断ではなく、[ADR-047](../decisions/ADR-047-connect-wide-and-exacta-race-day-odds-to-expected-value-decisions.md)の
蓄積のゲートの下限を見積もる記録である。

## 測定条件

- 入力は、snapshot `034f3ff22f5c459abecef756bc0ecc2c`の`NL_HR_PAY`と、raw DBの`ARCHIVE_CAPTURE_LOG`である。
- 対象は、2016〜2025年の中央01〜10場、`headDataKubun` 2の34,548レースである。
- 1レース1点を市場の確率に比例して選ぶと仮定した。回収率の95%区間を±10ポイントにする必要な買い目の数は、
  `n = (1.96/0.10)² × (E[的中のオッズ] − 1)`で近似した。1点の受取の分散を`E[的中のオッズ] − 1`とみなす。
- 中央は年約3,450レース（34,548レース÷10年）とした。期待値の方策が長いオッズを選ぶほど必要な数は増えるため、この値は下限の目安である。
- 取得は2026-11-14・15に各日36レースを対象にした。`archived`の取得は、36レースのうち、発走30分前が15・11、10分前が15・14、5分前が16・15、2分前が16・15レースだけだった（11-14・11-15の順）。多くはrace-day-oddsの起動・再起動より前に予定した取得の`skipped_late`で、残りはJVLinkAgentの停止による（[当日の運用の実測（2026-11-14・15）](race-day-operation.md)）。
- `0B33`〜`0B36`の`HappyoTime`は、発走前の分数で一定だった。5分前の取得は発走の6分前（freezeの1分前）、10分前は11分前、30分前は30・31分前、2分前は3分前（freezeの後）だった。
- 同じ日の払戻（`NL_HR_PAY`）は、raw DBにまだない。次の`latest`で入る。

## 結果

### 払戻からの蓄積の下限

| 券種 | 的中/レース | オッズの中央値 | 平均 | 90%点 | 必要な買い目の数 | 全レースで1レース1点の年数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 単勝 | 1.00 | 4.7 | 10.0 | 20.3 | 3,466 | 1.0 |
| 複勝 | 2.98 | 2.0 | 3.4 | 6.5 | 920 | 0.3 |
| 馬連 | 1.00 | 18.3 | 55.9 | 118.8 | 21,100 | 6.1 |
| ワイド | 3.00 | 8.1 | 19.0 | 41.3 | 6,931 | 2.0 |
| 馬単 | 1.00 | 34.3 | 110.8 | 230.5 | 42,191 | 12.2 |
| 3連複 | 1.00 | 50.0 | 212.4 | 427.0 | 81,220 | 23.5 |
| 3連単 | 1.01 | 262.2 | 1,325.0 | 2,632.4 | 508,626 | 147.4 |

### 当日の取得

発走5分前の取得は、freezeの1分前に発表されたオッズを持つ。10分前の取得はfreezeの6分前に発表されたオッズを持つ。
2分前の取得はfreezeの後に発表されたオッズを持つ。

## 解釈

- ワイドは、全レースを取得できた日であれば、freezeのオッズがある的中を1,000件にするゲートAまで約10日、定額の評価の下限である6,931点まで約2年に当たる。
- 馬単は、同じゲートAまで約28日、定額の評価の下限である42,191点まで約12年に当たる。
- 3連複・3連単は、定額の評価の下限までそれぞれ約23.5年・約147.4年となるため、最小運用の期待値の判断から外す。
- 5分前の取得を欠かさなければ、freeze以前に発表されたオッズを選べる。5分前の取得が欠けたときは、10分前の取得が代わりになる。
- 取得の方式は[ADR-032](../decisions/ADR-032-capture-race-day-odds-for-all-bet-types.md)、補正は[ADR-042](../decisions/ADR-042-correct-closing-odds-to-hit-conditional-final-odds.md)、方策は[ADR-043](../decisions/ADR-043-fix-an-expected-value-win-and-place-policy-and-backtest-graded-races.md)、確率は[ADR-044](../decisions/ADR-044-select-a-selection-bias-estimate-each-year-from-earlier-graded-flat-results.md)、購入案は[ADR-045](../decisions/ADR-045-save-the-betting-estimator-yearly-and-attach-zero-yen-proposals-on-race-day.md)を参照する。

## 制約

- 必要な買い目の数は、1レース1点を市場の確率に比例して選ぶ仮定での下限の目安である。期待値の方策は長いオッズを選びやすく、実際はもっと多くなる。
- 2026-11-14・15は、race-day-oddsの起動の遅れ・再起動とJVLinkAgentの停止により、どの時点の取得も全レースにはない。
- 同じ日の払戻は次の`latest`までraw DBにないため、当日の取得と払戻をまだ照合できない。
- 単勝から組合せのオッズを推定する誤差は、[単勝オッズからの連勝式オッズ推定誤差と締切後のオッズ変動](exotic-odds-estimation-error.md)を参照する。

## 再現

スクリプトと結果は、git管理外の`output/exotic-ev-accumulation-20261120/`に置いた。

| ファイル | SHA-256 |
| --- | --- |
| `measure.py` | `46d11ad77d8d5df6bd3aed6207b02dc4a1aa073bb9f34983629ee40017e0d68e` |
| `results.json` | `92cbb2a71cc293a6ce8a527b79c93d17bd9c99ba210cf49233b87e02343ad548` |
| `run.log` | `94cf904da4e9c59b333ad06fe3044e5c0d18effdddec490649a59eaa3d8a26b9` |

```powershell
uv run python -I output/exotic-ev-accumulation-20261120/measure.py <processed>/snapshots/034f3ff22f5c459abecef756bc0ecc2c data/raw/race.db <出力先> > run.log
```

`<出力先>`には、上の証跡と別のフォルダを渡す。同じフォルダを渡すと`results.json`を上書きする。`run.log`は標準出力を保存したものである。

払戻の部分は固定のsnapshotから再現できる。取得の部分はraw DBの実行時点（2026-11-20、取得は2026-11-14・15だけ）の`ARCHIVE_CAPTURE_LOG`を読むため、後の開催日の取得が増えると`results.json`のハッシュは一致しない。
