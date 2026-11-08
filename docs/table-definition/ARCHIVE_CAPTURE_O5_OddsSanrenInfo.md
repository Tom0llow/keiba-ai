# ARCHIVE_CAPTURE_O5_OddsSanrenInfo（計画・未生成）

[一覧に戻る](README.md)

**設計提案**: [ADR-032](../decisions/ADR-032-capture-race-day-odds-for-all-bet-types.md)で実装した3連複の子表のarchiveである。
2026-11-08時点で実データには未生成であり、最初の`race-day-odds`の取得でraw DBに作成される。
生成後に、実際のDDLとParquet schemaとの照合が必要である。

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `ARCHIVE_CAPTURE_O5_OddsSanrenInfo` |
| 論理名 | 開催日3連複オッズの組合せ別archive |
| 層・形式 | `raw`（SQLite）。完全snapshotの再生成で同名の`processed` Parquetにも出力される。 |
| 保存先 | `data/raw/race.db` |
| 直接の入力 | JVLinkToSQLiteのstaging子表`RT_O5_OddsSanrenInfo`と、同じ取得の親表の唯一の行 |
| 取得元 | JV-Link → JVLinkToSQLite（ADR-005）。DataSpec `0B35`。 |
| 技術的な目的 | 発走前の各時点の3連複の組合せ別オッズを、時点を区別して累積する。 |
| 行粒度 | 1レース×1発表（`headDataKubun`・`HappyoTime`）×1組合せ。2026-11-08の事前確認では1発表で816行。 |
| 利用先 | To confirm。期待値の判断と特徴量への接続は未実装。 |
| 作成・更新方法 | `uv run python src/main.py --retrieve --mode=race-day-odds --date YYYY-MM-DD` |
| 更新頻度 | 開催日の取得ごと |
| データ管理責任者 | To confirm |
| 主キー・外部キー | 宣言なし。親表`ARCHIVE_CAPTURE_O5_ODDS_SANREN`とは6キー列・`headDataKubun`・`HappyoTime`で対応する。 |
| その他の制約 | 全列の宣言型は`TEXT`。6キー列に索引`ARCHIVE_CAPTURE_O5_OddsSanrenInfo_race_key`を持つ。全行で重複除去する。 |
| 機微区分・アクセス権 | To confirm |
| 品質確認 | 子表の全行のレースキーが親表と一致すること。同じレース・区分・発表時刻で既存と行集合が異なる取得は`happyo_conflict`として入れない。 |

## 列の定義

| 物理名 | 意味 | 型 | NULL | 由来 |
| --- | --- | --- | --- | --- |
| `idYear`〜`idRaceNum` | 対象レースの6キー列 | TEXT | To confirm | `RT_O5_OddsSanrenInfo`の同名列 |
| `OddsSanrenInfoIdx` | 組合せの配列位置 | TEXT | To confirm | `RT_O5_OddsSanrenInfo`の同名列 |
| `OddsSanrenInfoKumi` | 組合せ（馬番の連結） | TEXT | To confirm | `RT_O5_OddsSanrenInfo`の同名列 |
| `OddsSanrenInfoOdds` | オッズの原値 | TEXT | To confirm | `RT_O5_OddsSanrenInfo`の同名列。換算はしない。 |
| `OddsSanrenInfoNinki` | 人気順の原値 | TEXT | To confirm | `RT_O5_OddsSanrenInfo`の同名列 |
| `headDataKubun` | 親表のデータ区分 | TEXT | 不可 | 同じ取得の`RT_O5_ODDS_SANREN`親表の唯一の行の値 |
| `HappyoTime` | 親表の発表時刻 | TEXT | 不可 | 同じ取得の`RT_O5_ODDS_SANREN`親表の唯一の行の値 |

子表の列は、staging子表の列をそのまま先頭に置く。2026-11-08の事前確認での子表の列は上表の
`headDataKubun`より前の10列であった。
