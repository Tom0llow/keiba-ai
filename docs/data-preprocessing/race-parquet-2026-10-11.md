# `race.db` のParquet再処理記録（2026-10-11）

## 対象と確認方法

- 入力: `data/raw/race.db`（SQLite、39表、7,979列、251,654,382行、80,312,610,816 byte）。最終更新日時は 2026-10-11 19:35:30 JST。raw は `mode=ro` + `PRAGMA query_only=ON` で扱い、データ値は出力していない。
- 現行出力: `data/processed/CURRENT` が指す snapshot `098ce3f4b5d7480282269218d80cef05`。39ファイル、合計 12,721,941,245 byte。全列は nullable `string` である。
- 設定: `config/data.toml`。`raw_db` と `processed_dir` は設定ファイルから解決する。
- 実装: `uv run python src/main.py preprocess rebuild` が、rawの全ユーザー表を一貫したread-only snapshotからバッチ出力し、全表の検証後に `CURRENT` を切り替える。
- 照合: raw と現行 Parquet の表名、表別の行数・列数、列名・列順、保存型、snapshot のファイルサイズを確認した。全セル値の独立比較、外部原本との照合は行っていない。

## 変換規則

| 規則 | Why | Impact | Validation |
| --- | --- | --- | --- |
| SQLiteの全ユーザー表を表名と同じParquetファイルへ1対1で出力する。 | rawの表集合を固定リストで切り捨てず、現行データを完全snapshotにするため。 | archive/stagingを含む39表を公開対象にする。 | rawの表名とsnapshotファイル名を照合する。 |
| 列名・列順を保ち、文字列と`NULL`をParquetの`string`/`NULL`として保存する。 | 業務定義が未承認で、値の意味を変えないため。 | 日時解析、数値化、空白・ゼロ日付の置換、欠損補完、行の除外、結合、集計をしない。 | 各表でParquetスキーマ、列名、列順、実値型を検証する。 |
| 一貫したread-only SQLite snapshotからバッチ単位で書き、一時ディレクトリで全表を完成させてから`CURRENT`を切り替える。 | 部分的な公開を避け、失敗時に公開中のポインタを守るため。 | 追加のディスク容量と処理時間が必要になる。 | 表別の入力行数、Parquetメタデータ、39表の集合を照合する。 |

## 現行 snapshot の結果

現行 snapshot は raw の39表と同名で対応し、表別の行数・列数が一致する。合計は39ファイル、7,979列、251,654,382行、12,721,941,245 byteである。raw の宣言型は `TEXT` 7,976列、`DATETIME` 3列で、Parquetでは全列を nullable `string` として保存する。raw の主キー183列、`NOT NULL`182列、外部キー0の制約はParquet側で強制しない。

| 表 | 行数 | 列数 | Parquetサイズ(byte) |
| --- | ---: | ---: | ---: |
| ARCHIVE_O1_ODDS_TANFUKUWAKU | 10,577,423 | 323 | 2,552,696,952 |
| ARCHIVE_O2_ODDS_UMAREN | 10,552,822 | 473 | 6,545,473,569 |
| NL_BN_BANUSI | 8,762 | 27 | 732,599 |
| NL_BR_BREEDER | 10,769 | 27 | 790,831 |
| NL_BT_KEITO | 92 | 7 | 119,282 |
| NL_CH_CHOKYOSI | 1,477 | 576 | 673,948 |
| NL_CK_BanusiChaku | 1,120,403 | 29 | 34,825,896 |
| NL_CK_BreederChaku | 1,120,403 | 29 | 33,803,014 |
| NL_CK_CHAKU | 1,120,403 | 436 | 129,879,221 |
| NL_CK_ChokyoChaku | 1,120,403 | 632 | 477,948,602 |
| NL_CK_KisyuChaku | 1,120,403 | 632 | 461,241,833 |
| NL_CS_COURSE | 119 | 8 | 107,693 |
| NL_DM_INFO | 85,378 | 82 | 7,876,113 |
| NL_HC_HANRO | 11,957,829 | 14 | 120,177,292 |
| NL_HN_HANSYOKU | 161,995 | 19 | 8,371,929 |
| NL_HR_PAY | 139,833 | 199 | 6,823,421 |
| NL_HS_SALE | 55,360 | 14 | 958,451 |
| NL_HY_BAMEIORIGIN | 179,278 | 6 | 7,004,394 |
| NL_JG_JOGAIBA | 839,602 | 14 | 6,424,086 |
| NL_KS_KISYU | 1,566 | 621 | 818,581 |
| NL_O1_ODDS_TANFUKUWAKU | 115,228 | 323 | 38,800,698 |
| NL_O2_ODDS_UMAREN | 112,565 | 473 | 92,639,430 |
| NL_O3_ODDS_WIDE | 92,326 | 626 | 118,827,308 |
| NL_O4_ODDS_UMATAN | 83,985 | 932 | 170,662,322 |
| NL_O5_ODDS_SANREN | 84,009 | 14 | 842,629 |
| NL_O5_OddsSanrenInfo | 35,311,083 | 10 | 243,222,473 |
| NL_O6_ODDS_SANRENTAN | 67,533 | 14 | 690,974 |
| NL_O6_OddsSanrentanInfo | 170,970,762 | 10 | 1,419,781,599 |
| NL_RA_RACE | 242,535 | 110 | 20,710,667 |
| NL_RC_RECORD | 2,151 | 48 | 116,799 |
| NL_SE_RACE_UMA | 2,899,729 | 73 | 138,327,742 |
| NL_SK_SANKU | 427,328 | 26 | 15,344,298 |
| NL_TM_INFO | 54,909 | 46 | 1,489,688 |
| NL_UM_UMA | 215,202 | 227 | 46,252,132 |
| NL_WC_WOOD | 784,552 | 29 | 16,956,890 |
| NL_YS_SCHEDULE | 7,526 | 45 | 93,864 |
| RT_O1_ODDS_TANFUKUWAKU | 0 | 323 | 37,960 |
| RT_O2_ODDS_UMAREN | 0 | 473 | 54,893 |
| SY_PROC_FILES | 8,639 | 9 | 341,172 |
| **合計** | **251,654,382** | **7,979** | **12,721,941,245** |

## 照合結果と制限

| 確認項目 | 結果 |
| --- | --- |
| 表・ファイル | raw通常表39件とsnapshot Parquet39件が同名で対応し、過不足なし。 |
| 列 | 表別の列数、列名・列順を確認した。旧定義書の物理列定義と差分はない。 |
| 型 | raw宣言は`TEXT`7,976列、`DATETIME`3列。snapshotは全列`string`。 |
| NULL許容 | snapshotの全7,979列がNULL許容。rawのNOT NULL宣言182列もParquetでは強制しない。 |
| 行数 | rawとsnapshotの表別行数が一致し、合計251,654,382行。 |
| 値 | 変換境界では文字列・`NULL`を保持する。個別値の報告、全セルの独立比較、外部原本との比較は未実施。 |
| 公開 | `CURRENT` は完成済みの snapshot `098ce3f4b5d7480282269218d80cef05` を指す。 |

業務上の論理名、項目意味、コード値、欠損・空白・ゼロ日付の扱い、品質合否、取得元、所有者、保持期間は未確認である。旧 2026-10-06 の再処理記録は履歴として残し、今回の記録は更新後の現行 snapshot を対象とする。raw DB 本体、個別レコード値、秘密情報は変更・掲載していない。

## 根拠

- 実行入口・設定: `src/main.py` の `preprocess rebuild`、`config/data.toml`。
- 実装: `src/data/preprocesser/read_sqlite.py`、`src/data/preprocesser/snapshot.py`。
- 現物: `data/raw/race.db` の read-only メタデータ、`data/processed/CURRENT`、snapshot Parquet のメタデータ。
- 業務仕様書、提供元の仕様、所有者への確認、全セル値の独立比較、SQLiteの `PRAGMA integrity_check` は未実施である。
