# `race.db` のParquet処理記録（2026-10-20）

## 入出力と実施結果

- 入力: `data/raw/race.db`、80,312,610,816 byte、39表、7,979列、251,654,382行。read-onlyの単一取引から読み取った。
- 既存公開版: `data/processed/snapshots/098ce3f4b5d7480282269218d80cef05/`。全件数・スキーマと先頭標本を今回再照合した。
- 事前試行: 全39表の先頭最大1,000行、計35,211行を`output/data-assessment-2026-10-20/trial-a/`と`trial-b/`へ保存。raw標本・再読込値・現行版の先頭値が一致した。これを全セル照合とは扱わない。
- 全量出力: `output/data-assessment-2026-10-20/full-processed/snapshots/cb9f958f118944a9bf4809791b5e37a8/`。251,654,382行、12,721,941,245 byte。新規ルートのCURRENTは`cb9f958f118944a9bf4809791b5e37a8`。
- 実行時間: `2026-10-20T21:22:11.875649+09:00`〜`2026-10-20T22:37:40.316604+09:00`、4,528.44秒。
- 全39表の件数、全列の名前・順序・nullable stringを検証。rawサイズ・更新時刻と`data/processed/CURRENT`は実行前後で不変だった。
- 現行版と再生成版の保存ファイルを全体で比較し、39/39ファイルで全バイトのサイズ・SHA-256が一致。rawとの全セル独立比較は別の未実施項目である。

## 適用した規則

| 規則 | Why | Impact | Validation | 例外・決定根拠 |
| --- | --- | --- | --- | --- |
| 全ユーザー表を同名Parquetへ1対1出力する。 | 現行の完全snapshot契約を再現する。 | archive/stagingを含む39表、251,654,382行を保存する。 | 表集合・表別行数を全件照合。 | ADR-008、現行SnapshotBuilder。表の任意除外なし。 |
| TEXT/DATETIME宣言の実値をnullable string/NULLで保存する。 | 未承認の業務解釈を混入させない。 | 列名・順序、文字列、先頭ゼロ、空白、NULLを保持。日時解析、数値化、補完、除外、丸め、重複除去、結合、集計なし。 | 全スキーマ、変換境界の実値型、標本の再読込比較。 | 未対応宣言型・非文字列実値は既存実装が停止する。 |
| 1読取取引・バッチ出力・完成後公開を使う。 | 途中状態の公開を避ける。 | 今回は既存公開先と独立した新規ルートを作る。 | 保存後の件数・スキーマ、CURRENT、rawの前後状態を確認。 | 既存SnapshotBuilder/publish_snapshotをそのまま使用。 |

取得時archiveの完全一致行の重複除去（ADR-007）は別契約であり、今回のraw→processedでは重複除去を追加していない。

## 保留した判断

欠損補完、空白やゼロ日付の置換、外れ値処理、行の除外、数値化・丸め、結合、業務重複除去、集計粒度変更は未承認のため適用していない。標本のNULL 0、空文字1,153,639、空白のみ0セルは観測値であり、不良件数とはしない。
Datamart構築APIは実装済みだが、raw列から正規化入力・利用可能時点を作る承認済み変換はないため、任意の対応付けでDatamartを生成しない。

## 公開と復旧

既存の`data/processed/CURRENT`は`098ce3f4b5d7480282269218d80cef05`を維持している。新しい生成物は独立ルートへ置いたため、既存利用者の参照先は変わらない。
既存公開先を切り替える場合は、新版の検証結果・正確な対象・影響・従前版への復旧方法を提示して別途承認を得る。既存snapshot、平置きParquet、stagingの削除は行っていない。

## 再現と検証の限界

- 実行証跡は`output/data-assessment-2026-10-20/assessment.json`と`full-rebuild.json`。再生成には`rebuild_full.py`が`SnapshotBuilder(DataPaths(...)).rebuild()`を呼ぶ。新規出力先が既に存在すれば停止する。
- 実装は`src/data/loader/read_sqlite.py`、`src/data/preprocessor/sqlite_to_arrow.py`、`src/data/saver/write_parquet.py`、`src/data/storage/snapshot_builder.py`と`snapshot_publisher.py`。通常の既存公開先へのCLIは`uv run python src/main.py preprocess rebuild`だが、今回はそのCURRENTを切り替えるコマンドを実行していない。
- 元データを変えず、承認済みの変換を実データで試行・全量再実行した。製品コード・設定・DBスキーマの変更はないため、新しい製品コード用テストは追加していない。全セルの独立比較、外部原本との照合、DB全件integrity_check、業務品質の合否判定は未実施。
