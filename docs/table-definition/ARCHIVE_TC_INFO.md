# ARCHIVE_TC_INFO（計画・未生成）

[一覧に戻る](README.md)

**設計**: [ADR-049](../decisions/ADR-049-handle-race-day-start-time-changes.md)で実装した、発走時刻変更の蓄積表である。
最初の開催日の`race-day-odds`のTC確認で、変更の行があったときにraw DBに作成される。

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `ARCHIVE_TC_INFO` |
| 論理名 | 発走時刻変更の蓄積 |
| 層・形式 | `raw`（SQLite）。完全snapshotの再生成で同名の`processed` Parquetにも出力される。 |
| 保存先 | `data/raw/race.db` |
| 直接の入力 | `race-day-odds`のTC確認で、JVLinkToSQLiteが`0B14`（日付のキー）から作る`RT_TC_INFO` |
| 技術的な目的 | `RT_TC_INFO`は実行ごとに作り直されるため、その日の発走時刻変更の行を蓄積し、変更後の発走時刻と繰上げの判定、再開時の復元に使う。 |
| 行粒度 | 発走時刻変更の1件（同じ行は1行に重複を除く） |
| 利用先 | `race-day-odds`（その日の行から、レースごとに最も新しい`HappyoTime`の変更後の時刻を採る。どれかの行が出馬表より前なら繰上げとする） |
| 作成・更新方法 | `uv run python src/main.py --retrieve --mode=race-day-odds --date YYYY-MM-DD`。TC確認の結果が`ok`のときに、`RT_TC_INFO`の行を`EXCEPT`で重複なく追記する。 |
| 更新頻度 | 開催日のTC確認ごと |
| データ管理責任者 | To confirm |
| 主キー・外部キー | 宣言なし。 |
| その他の制約 | 列は`RT_TC_INFO`と同じ並びで、全列の宣言型は`TEXT`。`RT_TC_INFO`の列が`TEXT`でなければ追記を拒否する。 |
| 機微区分・アクセス権 | To confirm。認証情報は含めない。 |
| 品質確認 | 追記の後、`RT_TC_INFO`ほか`0B14`の受け皿の表（`RT_AV_INFO`・`RT_WE_WEATHER`・`RT_JC_INFO`・`RT_CC_INFO`）は削除する。TC確認の前にも削除するため、前回の応答を今回の応答として読まない。 |

## 列の定義

| 物理名 | 意味 | 型 | NULL | 値・導出 |
| --- | --- | --- | --- | --- |
| `headRecordSpec` | レコード種別 | TEXT | 可 | `TC` |
| `headDataKubun` | データ区分 | TEXT | 可 | JV-Dataの値。`0`（削除。提供ミス）の行は変更として数えず、同じレース・同じ`HappyoTime`の発表を取り消す |
| `headMakeDate` | データ作成年月日 | TEXT | 可 | `YYYYMMDD`。同じ`HappyoTime`の行の順序に使う |
| `idYear`〜`idRaceNum` | 対象レースの6キー列 | TEXT | 可 | `NL_RA_RACE`のキー列と同じ値 |
| `HappyoTime` | 発表月日時分 | TEXT | 可 | `MMDDhhmm`（JST） |
| `TCInfoAfterJi`・`TCInfoAfterFun` | 変更後の発走時刻の時・分 | TEXT | 可 | 2桁。レースの日付（`idYear`・`idMonthDay`）のJSTの時刻として読む |
| `TCInfoBeforeJi`・`TCInfoBeforeFun` | 変更前の発走時刻の時・分 | TEXT | 可 | 2桁 |
