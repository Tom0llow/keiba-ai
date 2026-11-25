# ARCHIVE_TC_CHECK_LOG（計画・未生成）

[一覧に戻る](README.md)

**設計**: [ADR-049](../decisions/ADR-049-handle-race-day-start-time-changes.md)で実装した、TC確認の記録表である。
最初の開催日の`race-day-odds`のTC確認でraw DBに作成される。

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `ARCHIVE_TC_CHECK_LOG` |
| 論理名 | 発走時刻変更の確認記録 |
| 層・形式 | `raw`（SQLite）。完全snapshotの再生成で同名の`processed` Parquetにも出力される。 |
| 保存先 | `data/raw/race.db` |
| 直接の入力 | `race-day-odds`のTC確認（`0B14`の要求、または時間がないための省略） |
| 技術的な目的 | 各時点の前のTC確認の結果と、その後にレースごとに採った変更後の発走時刻を残し、取得時点を事後に説明する。 |
| 行粒度 | 1回のTC確認（または省略） |
| 利用先 | 事後の確認（コードは読まない） |
| 作成・更新方法 | `uv run python src/main.py --retrieve --mode=race-day-odds --date YYYY-MM-DD` |
| 更新頻度 | 開催日の時点ごと |
| データ管理責任者 | To confirm |
| 主キー・外部キー | 宣言なし。`check_id`は1行となる。 |
| その他の制約 | 全列の宣言型は`TEXT`。列の並びの完全一致を検査する。 |
| 機微区分・アクセス権 | To confirm。認証情報は含めない。 |
| 品質確認 | `ok`のときだけ`RT_TC_INFO`の行を`ARCHIVE_TC_INFO`へ追記する。`failed`・`skipped`では直前の予定で取得を続ける。`agent_down`ではその日の残りの取得を実行しない。 |

## 列の定義

| 物理名 | 意味 | 型 | NULL | 値・導出 |
| --- | --- | --- | --- | --- |
| `check_id` | 確認の識別子 | TEXT | 不可 | UUIDの16進文字列 |
| `idYear`・`idMonthDay` | 対象日 | TEXT | 不可 | `YYYY`・`MMDD` |
| `time_point_at` | この確認が前に立つ時点 | TEXT | 不可 | UTCのISO 8601（その時点の最も早い取得予定時刻） |
| `started_at`・`completed_at` | JVLinkToSQLiteの実行の前後の時計 | TEXT | 可 | UTCのISO 8601。`skipped`はNULL |
| `result` | 結果 | TEXT | 不可 | `ok`/`no_data`/`failed`/`agent_down`/`skipped` |
| `reason` | 理由 | TEXT | 不可 | 例: `tc_rows_archived`、`jvopen_no_data`、`no_time_before_time_point`、失敗の文言、`0B14 JVRTOpen -303` |
| `process_returncode` | JVLinkToSQLiteの終了コード | TEXT | 可 | 十進文字列 |
| `api_name`・`api_returncode` | `0B14`のAPI名と戻り値 | TEXT | 可 | 例: `JVRTOpen`・`-1` |
| `tc_rows` | その応答の`RT_TC_INFO`の行数 | TEXT | 不可 | 十進文字列 |
| `earlier_start_races` | 繰上げを検出したレース | TEXT | 不可 | race_idの空白区切り。なければ空 |
| `adopted_starts` | 確認の後に採った変更後の発走時刻 | TEXT | 不可 | race_idをキーにした、`effective_start_at`と`HappyoTime`のJSON（キーで並べる）。変更のないレースは含めない |
