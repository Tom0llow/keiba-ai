# ARCHIVE_CAPTURE_LOG（計画・未生成）

[一覧に戻る](README.md)

**設計提案**: [ADR-032](../decisions/ADR-032-capture-race-day-odds-for-all-bet-types.md)で実装した取得記録表である。
2026-11-08時点で実データには未生成であり、最初の`race-day-odds`の取得でraw DBに作成される。
生成後に、実際のDDLとParquet schemaとの照合が必要である。

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `ARCHIVE_CAPTURE_LOG` |
| 論理名 | 開催日オッズ取得記録 |
| 層・形式 | `raw`（SQLite）。完全snapshotの再生成で同名の`processed` Parquetにも出力される。ADR-037以降、レース別のParquet（`data/processed/realtime/<race-id>/versions/<id>/`）にも、そのレースの行が出力される。 |
| 保存先 | `data/raw/race.db` |
| 直接の入力 | `race-day-odds`の取得計画（0B31〜0B36の取得と、ADR-032 Amendment 2の予測用の0B41/0B42の取得）、JVLinkToSQLiteの実行結果、`RT_O1`〜`RT_O6`のstaging観測 |
| 技術的な目的 | 取得×DataSpecごとの実測時計・状態・API結果・観測行数を残し、中断を検出する。 |
| 行粒度 | 1回の取得（1レース×1時点）×1 DataSpec |
| 利用先 | `AcquisitionLock`の未解決検査、`race-day-odds`の起動時復旧と再開時の終了済みの判定（レース・分前・種類）、取得時点の事後確認、`datamart build-reference-prediction-live`（レース別のParquetから、予測用の取得の状態と開始時刻を読む。ADR-037） |
| 作成・更新方法 | `uv run python src/main.py --retrieve --mode=race-day-odds --date YYYY-MM-DD` |
| 更新頻度 | 開催日の取得ごと |
| データ管理責任者 | To confirm |
| 主キー・外部キー | 宣言なし。`capture_id`と`data_spec`の組は1行となる。 |
| その他の制約 | 全列の宣言型は`TEXT`。`status`列に索引`ARCHIVE_CAPTURE_LOG_status`を持つ。 |
| 機微区分・アクセス権 | To confirm。認証情報は含めない。 |
| 品質確認 | 成功と無データはarchiveと同じSQLite取引で確定する。退避が必要な失敗は、archiveを取り消して退避した後の別の取引で確定する。`skipped_late`と`interrupted`はarchiveを伴わない。`running`の行は未解決の取得を示す。`reason`は追記され、先の証拠を上書きしない。予測用の取得（`0B41`/`0B42`）に限り、確定の後にレース別のParquetの公開が失敗すると、`reason`に`publish_failed: ...`を追記する（`status`は変えない。ADR-032 Amendment 2）。 |

## 列の定義

| 物理名 | 意味 | 型 | NULL | 値・導出 |
| --- | --- | --- | --- | --- |
| `capture_id` | 取得の識別子 | TEXT | 不可 | UUIDの16進文字列。1回の取得の全DataSpecで共通。 |
| `idYear`〜`idRaceNum` | 対象レースの6キー列 | TEXT | 不可 | `NL_RA_RACE`のキー列と同じ値。 |
| `data_spec` | DataSpec | TEXT | 不可 | `0B31`〜`0B36`、または予測用の取得の`0B41`/`0B42` |
| `scheduled_start_at` | 基準にした発走予定時刻 | TEXT | 不可 | `NL_RA_RACE.HassoTime`からのJSTのISO 8601。 |
| `offset_minutes` | 発走前の分数 | TEXT | 不可 | 十進文字列。 |
| `planned_at` | 取得予定時刻 | TEXT | 不可 | UTCのISO 8601。 |
| `started_at` | JVLinkToSQLite実行の直前の時計 | TEXT | 可 | UTCのISO 8601。未実行はNULL。 |
| `completed_at` | 実行後または状態確定の時計 | TEXT | 可 | UTCのISO 8601。未実行（`running`、`skipped_late`）はNULL。 |
| `status` | 状態 | TEXT | 不可 | `running`/`archived`/`no_data`/`failed`/`skipped_late`/`interrupted` |
| `reason` | 理由と退避の証拠 | TEXT | 可 | セミコロンと空白で区切って追記する。例: `preexisting_staging: [...]; capture_archive_committed`、`happyo_conflict: quarantined [...]`、`interrupted_recovery`、予測用の取得の確定後の`capture_archive_committed; publish_failed: ...` |
| `process_returncode` | JVLinkToSQLiteの終了コード | TEXT | 可 | 十進文字列。 |
| `api_name` | DataSpec別のJV-Link API名 | TEXT | 可 | 例: `JVRTOpen` |
| `api_returncode` | DataSpec別のAPI戻り値 | TEXT | 可 | 十進文字列。 |
| `headDataKubun` | 親表の唯一の行のデータ区分 | TEXT | 可 | staging親表の値。予測用の取得（`0B41`/`0B42`）では、stagingに`headDataKubun="1"`の行があれば`"1"`、なければNULL。 |
| `HappyoTime` | 親表の唯一の行の発表時刻 | TEXT | 可 | staging親表の値。予測用の取得では、stagingの`headDataKubun="1"`の行の`HappyoTime`の最大値（なければNULL）。 |
| `observed_rows` | 対象レースの親表（単一表）の観測行数 | TEXT | 可 | 十進文字列。6キー列が対象レースと一致する行だけを数える。予測用の取得では時系列の全行（複数行）。 |
| `inserted_rows` | 重複除去後に新しく入った親表の行数 | TEXT | 可 | 十進文字列。 |
| `child_observed_rows` | 対象レースの子表の観測行数 | TEXT | 可 | `0B35`/`0B36`以外は`0`。 |
| `child_inserted_rows` | 重複除去後に新しく入った子表の行数 | TEXT | 可 | `0B35`/`0B36`以外は`0`。 |
