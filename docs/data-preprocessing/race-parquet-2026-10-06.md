# `race.db` のParquet再処理記録（2026-10-06）

## 対象と実行方法

- 入力: `data/raw/race.db`（SQLite、39表、7,979列、233,009,507行、41,978,077,184 byte）。入力は読み取り専用で開いた。
- 設定: `config/data.toml`。`raw_db` と `processed_dir` は設定ファイルから解決した。
- 実行: `uv run python src/main.py preprocess rebuild`。
- 出力: `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/`。39表、合計4,723,374,937 byte。
- 公開: 全表の書き込み・スキーマ・行数検証後、`data/processed/CURRENT` をsnapshot IDへ原子的に切り替えた。既存の平置き `data/processed/*.parquet` は上書きしていない。

## 変換規則

| 規則 | Why | Impact | Validation |
| --- | --- | --- | --- |
| SQLiteの全ユーザー表を表名と同じParquetファイルへ1対1で出力する。 | rawの表集合を固定リストで切り捨てず、現行データを完全snapshotにするため。 | archive/stagingを含む39表を公開対象にする。 | rawの表名とsnapshotファイル名を照合する。 |
| 列名・列順を保ち、文字列と`NULL`をParquetの`string`/`NULL`として保存する。 | 業務定義が未承認で、値の意味を変えないため。 | 日時解析、数値化、空白・ゼロ日付の置換、欠損補完、行の除外、結合、集計をしない。 | 各表でParquetスキーマ、列名、列順、実値型を検証する。 |
| 一貫したread-only SQLite snapshotからバッチ単位で書き、一時ディレクトリで全表を完成させてから`CURRENT`を切り替える。 | 部分的な公開を避け、失敗時に公開中のポインタを守るため。 | 追加のディスク容量と処理時間が必要になる。 | コマンド終了コード0、表別行数、Parquetメタデータ、39表の集合を確認する。 |

## 実データの結果

変換コマンドは終了コード0で完了し、`processed snapshot published: 39 tables` を出力した。rawの39表、7,979列、233,009,507行が同名の39 Parquetへ出力された。Parquet合計サイズは4,723,374,937 byteである。

`CURRENT` は `81806ba398bb4fbe9a92eb1dbb75806f` を指している。現行snapshotにはrawの archive 2表と realtime staging 2表も含まれる。realtime推論用のrace-scoped出力は別契約であり、今回作成した完全snapshotとは区別する。

旧平置きParquetはレガシー成果物として保持した。旧平置き35表は現行rawの共通35表と列構造は一致するが、行数が一致しないため、今回のsnapshotの代替・完全コピーとは扱わない。

## 照合結果

| 確認項目 | 結果 |
| --- | --- |
| 表・ファイル | raw通常表39件とsnapshot Parquet39件が同名で対応し、過不足なし。 |
| 列 | 7,979列すべてでrawの名前・順序と一致。 |
| 型 | raw宣言は`TEXT`7,976列、`DATETIME`3列。snapshotは全列`string`。 |
| NULL許容 | snapshotの全7,979列がNULL許容。rawのNOT NULL宣言182列はParquetの強制制約にならない。 |
| 行数 | 各表の変換時行数とParquetメタデータ行数が一致し、合計233,009,507行。 |
| 公開 | 完成後に`CURRENT`を切り替え、平置き既存ファイルは上書きしていない。 |
| 値 | 変換境界で文字列・`NULL`以外の実値を拒否。全セルの独立比較、外部原本との比較は未実施。 |

## 未確認事項

- rawの取得元、原本の版、利用条件、所有者、保持期間。
- archive/stagingを完全snapshotに含める現行実装と業務上の公開契約の整合性。
- 旧平置きParquetの抽出条件と現行rawとの差分理由。
- 全セルの独立比較、SQLiteの`PRAGMA integrity_check`、業務上の品質基準。

## 根拠

- 実行入口: `src/main.py` の `preprocess rebuild`。
- 実装: `src/data/preprocesser/read_sqlite.py`、`src/data/preprocesser/snapshot.py`、`src/data/data_preprocesser.py`。
- 設計: ADR-008。raw-to-Parquetの物理定義は[テーブル定義書](../table-definition/README.md)に記載した。
- 実データはGit管理対象外であり、本記録と定義書には個別レコード値を掲載していない。
