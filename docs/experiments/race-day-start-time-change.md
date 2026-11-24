# 発走時刻の変更と速報の到達時点の実測

## 目的と範囲

発走時刻の変更の頻度、変更幅、変更情報がJV-Linkの速報で届く時点を確認し、当日の
race-day-odds、特徴量、予測、購入案の扱いを決める根拠とする。

集計は2026-11-24に`data/raw/race.db`を読取り専用で行った。速報の確認は、通常の取得を
止めた状態で、通常・setupを無効にし、対象の速報DataSpecだけを有効にした一時設定と一時SQLite
データベースでJVLinkToSQLiteを実行した。`data/raw/race.db`と取得のロックは使っていない。

ここでいう「繰上げ」「繰下げ」は、確定したRAの`HassoTime`と`HassoTimeBefore`の差分だけを指す。
当日の途中でさらに変更され、後で戻った状態まではこの集計から分からない。

## `NL_RA_RACE`の集計

### 対象とSQL

対象は、`idJyoCD`が`01`から`10`、`HassoTime`が`0000`でない4桁の数字である
`NL_RA_RACE`の行である。`headDataKubun`は絞っていない。集計時点の内訳は、`7`が140,249行、
`9`が422行、`2`が72行だった。変更は、`HassoTimeBefore`が数字で`0000`ではなく、
`HassoTime`と異なる行とした。時・分を分へ換算し、変更幅を変更後から変更前を引いた値で表す。

```sql
-- 年ごとの全レース数、変更数、変更があった開催日数
SELECT idYear,
       COUNT(*) AS races,
       SUM(HassoTimeBefore GLOB '[0-9]*' AND HassoTimeBefore <> '0000' AND HassoTimeBefore <> HassoTime) AS changed,
       COUNT(DISTINCT CASE WHEN HassoTimeBefore GLOB '[0-9]*' AND HassoTimeBefore <> '0000'
                            AND HassoTimeBefore <> HassoTime THEN idMonthDay END) AS change_days
FROM NL_RA_RACE
WHERE idJyoCD BETWEEN '01' AND '10'
  AND HassoTime GLOB '[0-9][0-9][0-9][0-9]' AND HassoTime <> '0000'
GROUP BY idYear ORDER BY idYear;

-- 2020年以降の変更幅。idYearの条件を外し、delta < 0を使うと過去を含む繰上げも確認できる。
SELECT (CAST(substr(HassoTime,1,2) AS INT)*60 + CAST(substr(HassoTime,3,2) AS INT))
     - (CAST(substr(HassoTimeBefore,1,2) AS INT)*60 + CAST(substr(HassoTimeBefore,3,2) AS INT)) AS delta,
       COUNT(*)
FROM NL_RA_RACE
WHERE idJyoCD BETWEEN '01' AND '10'
  AND HassoTime GLOB '[0-9][0-9][0-9][0-9]' AND HassoTime <> '0000'
  AND HassoTimeBefore GLOB '[0-9]*' AND HassoTimeBefore <> '0000' AND HassoTimeBefore <> HassoTime
  AND idYear >= '2020'
GROUP BY delta ORDER BY delta;

-- 2016年以降の重賞の変更
SELECT idYear, COUNT(*) FROM NL_RA_RACE
WHERE idJyoCD BETWEEN '01' AND '10' AND GradeCD IN ('A','B','C') AND idYear >= '2016'
  AND HassoTime GLOB '[0-9][0-9][0-9][0-9]' AND HassoTime <> '0000'
  AND HassoTimeBefore GLOB '[0-9]*' AND HassoTimeBefore <> '0000' AND HassoTimeBefore <> HassoTime
GROUP BY idYear;
```

### 結果

最初のSQLは全年を返す。次の表は2014年以降の行である（それより前の年には、変更が0件の年もある）。

| 年 | 対象のレース数 | 変更レース数 | 率 | 変更のある開催日 |
| --- | --- | --- | --- | --- |
| 2014 | 3,514 | 326 | 9.3% | 108日 |
| 2015 | 3,454 | 320 | 9.3% | 107日 |
| 2016 | 3,454 | 296 | 8.6% | 107日 |
| 2017 | 3,491 | 302 | 8.7% | 109日 |
| 2018 | 3,491 | 291 | 8.3% | 107日 |
| 2019 | 3,491 | 319 | 9.1% | 106日 |
| 2020 | 3,466 | 311 | 9.0% | 107日 |
| 2021 | 3,456 | 293 | 8.5% | 105日 |
| 2022 | 3,456 | 312 | 9.0% | 107日 |
| 2023 | 3,456 | 305 | 8.8% | 103日 |
| 2024 | 3,456 | 305 | 8.8% | 103日 |
| 2025 | 3,468 | 235 | 6.8% | 98日 |
| 2026（11-15まで。出馬表の段階の72行を含む） | 3,120 | 203 | 6.5% | 82日 |

- 最終の`HassoTime`と`HassoTimeBefore`の差分では、全件が繰下げで、繰上げは0件だった。
- 2020年以降の変更は1,964件で、変更幅（分）ごとの件数は次のとおりだった。+1分が1,714件（約87%）を占め、最大は+110分だった。

  +1: 1,714、+5: 181、+6: 5、+10: 24、+11: 3、+15: 4、+16: 1、+20: 4、+25: 4、+30: 2、+35: 2、+40: 3、+45: 2、+46: 1、+50: 6、+55: 3、+60: 2、+105: 1、+106: 1、+110: 1
- 2016年以降の重賞（`GradeCD`が`A`・`B`・`C`）の変更は5件で、2016年と2017年に各1件、2018年に2件、2025年に1件だった。

2026-11-14・15の`NL_RA_RACE`は`headDataKubun`が`2`の出馬表のままである。そのため、この2日の
変更0件は最終RAを取得した後の差分が0件であることを示さない。集計時点で`NL_RA_RACE`にある最終日の
`headDataKubun`が`7`のRAは2026-11-08であり、その日は3件の変更があった。

## `0B14`の速報開催情報

### 方法と要求時刻

`0B14`は日付のキーで要求した。要求時刻はすべてJSTで、2026-11-08は23:07、
2026-11-21〜23は23:07〜23:08、2026-11-14〜16は約23:09だった。

| 対象日 | 結果 |
| --- | --- |
| 2026-11-08、11-14、11-15、11-16 | `JVOpen`は`RC=-1`。DBは作られなかった。 |
| 2026-11-21 | `RT_AV_INFO` 4行、`RT_TC_INFO` 2行、`RT_WE_WEATHER` 5行。 |
| 2026-11-22 | `RT_AV_INFO` 2行、`RT_TC_INFO` 1行、`RT_WE_WEATHER` 2行。 |
| 2026-11-23 | `RT_JC_INFO` 2行、`RT_WE_WEATHER` 2行。 |

2026-11-24時点では、3日前の11-21までの開催日は取得でき、9日前の11-15と10日前の11-14の開催日は取得できなかった。
11-16は開催のない月曜日（`NL_RA_RACE`に行がない）であり、保持期間の根拠にならない。この観測から言えるのは、
開催日の速報の保持期間が3日以上9日未満ということだけである。

`RT_TC_INFO`の列は次のとおりだった。

```text
headRecordSpec, headDataKubun, headMakeDate, idYear, idMonthDay, idJyoCD, idKaiji,
idNichiji, idRaceNum, HappyoTime, TCInfoAfterJi, TCInfoAfterFun, TCInfoBeforeJi,
TCInfoBeforeFun
```

得られた発走時刻変更の行は次のとおりだった。

| 対象日・レース | 変更前 | 変更後 | `HappyoTime` |
| --- | --- | --- | --- |
| 2026-11-21 京都（08）5回5日 R01 | 10:00 | 10:01 | `11210820` |
| 2026-11-21 京都 R10 | 15:00 | 15:01 | `11210820` |
| 2026-11-22 京都 5回6日 R10 | 15:00 | 15:01 | `11220820` |

この3件の典型的な+1分の変更は、開催日の08:20 JSTに発表されていた。前日夜の`latest`の出馬表を直接比較して
いないため、前日夜には反映されていなかったとみられるが、これは`HappyoTime`からの推測である。開催日の夜に
`0B14`を再要求して日中の遅延を含むすべてのTC行を確認できるかは、この3件だけからは分からない。

### `0B16`

`0B16`は実行していない。キーは`JVWatchEvent`で受けるイベントから作るものであり、日付のキーは適用できない。
このため、`0B16`については表名、列、行の有無、内容を観測していない。

## `0B15`と`NL_RA_RACE`

2026-11-21の`0B15`は約23:09に要求した。`RT_RA_RACE`には最終のRAだけが返り、
`headDataKubun`は`7`、`headMakeDate`は11-24だった。京都R01とR10はそれぞれ
`HassoTime`/`HassoTimeBefore`が`1001`/`1000`、`1501`/`1500`だった。

この結果から、過去日に後から要求した`0B15`では、当日の途中のRA状態を観測できない。
`NL_RA_RACE`は、`latest`が開催日後に取得した最終RAで`HassoTimeBefore`を持つ。

## `latest`の速報設定

JVLinkToSQLiteの初期設定と`data/runtime/jvlink/latest.xml`のいずれも、`0B12`・`0B15`・`0B14`の
`KaisaiDate`を`2026-03-02`、`TimeIntervalUnit`を`P121DT18H`としていた。そのため`latest`は固定された
過去の日付を要求する。raw DBには、速報の`WE`・`AV`・`JC`・`TC`・`CC`に対応する`RT_`または`NL_`の表はない。
この設定は別の後続Issue候補である。

## 限界と未観測範囲

- この記録の「繰上げ0件」と「すべて繰下げ」は、最終RAの`HassoTime`/`HassoTimeBefore`の差分に限る。当日の途中状態を一般化しない。
- `latest`と`0B15`について、開催日の前後で`NL_RA_RACE`がどう変わるかは観測していない。
- 前日夜の`latest`の出馬表と`RT_TC_INFO`を直接比較していない。前日夜に変更が反映されていなかったという記述は、開催日08:20の`HappyoTime`からの推測である。
- `0B14`を開催日の夜に再要求して日中の遅延を含むすべてのTC行を確認できるかは未観測である。得られたTC行はいずれも08:20発表で、同一レースの複数行も観測していない。
- 2026-11-28・29の当日観測は、ADR-049の前には行わなかった。必要になれば後続の実装前に追加で観測する。
- `0B14`の保持期間は、この日の要求結果から3日以上9日未満と分かっただけである。正確な期間は観測しておらず、将来も同じであることを保証するものではない。
