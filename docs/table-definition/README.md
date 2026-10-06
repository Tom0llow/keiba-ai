# `data/processed` テーブル定義書

2026-10-06時点の`data/raw/race.db`と`data/processed/CURRENT`が指すsnapshotの実体を照合した物理定義。
snapshot IDは`81806ba398bb4fbe9a92eb1dbb75806f`。39表、7,979列、233,009,507行、Parquet合計4,723,374,937 byte。
論理名、業務上の項目意味、品質基準は未承認のため、物理名から推測していない。

## データ経路と変換規則

| 段階 | 実体・状態 |
| --- | --- |
| source | To confirm（取得元、原本の版、取得条件）。 |
| raw | `data/raw/race.db`。39表の取得・アーカイブ・staging表を含む。 |
| processed | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/`。rawの全ユーザー表を同名で1対1に保存。`CURRENT`が公開対象を選ぶ。 |
| realtime processed | `data/processed/realtime/<race-id>/`。今回の評価対象外。 |
| datamart | 現在確認できる実装はない。利用先はTo confirm。 |

`config/data.toml`が入力と出力のルートを定める。`src/main.py preprocess rebuild`は、rawの全ユーザー表を一貫したread-only snapshotからバッチ出力し、全表の検証後に`CURRENT`を切り替える。
列名・列順を維持し、SQLiteの文字列値と`NULL`をParquetの`string`/`NULL`として保存する。空白・日付風の値を置換せず、行の除外、結合、重複除去、集計、日時解析、欠損補完は行わない。

## 表一覧

行数・列数・サイズは2026-10-06のsnapshot Parquetメタデータとファイルから取得した。raw側の主キーは参考情報であり、Parquet側の制約ではない。

| 表 | 行数 | 列数 | サイズ (byte) | raw側の宣言主キー |
| --- | ---: | ---: | ---: | --- |
| [ARCHIVE_O1_ODDS_TANFUKUWAKU](ARCHIVE_O1_ODDS_TANFUKUWAKU.md) | 1,252,984 | 323 | 314,825,454 | 宣言なし |
| [ARCHIVE_O2_ODDS_UMAREN](ARCHIVE_O2_ODDS_UMAREN.md) | 1,240,661 | 473 | 784,701,407 | 宣言なし |
| [NL_BN_BANUSI](NL_BN_BANUSI.md) | 8,762 | 27 | 732,599 | `BanusiCode` |
| [NL_BR_BREEDER](NL_BR_BREEDER.md) | 10,769 | 27 | 790,831 | `BreederCode` |
| [NL_BT_KEITO](NL_BT_KEITO.md) | 92 | 7 | 119,282 | `HansyokuNum` |
| [NL_CH_CHOKYOSI](NL_CH_CHOKYOSI.md) | 1,477 | 576 | 673,948 | `ChokyosiCode` |
| [NL_CK_BanusiChaku](NL_CK_BanusiChaku.md) | 1,120,403 | 29 | 34,825,896 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum`, `BanusiChakuIdx` |
| [NL_CK_BreederChaku](NL_CK_BreederChaku.md) | 1,120,403 | 29 | 33,803,014 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum`, `BreederChakuIdx` |
| [NL_CK_CHAKU](NL_CK_CHAKU.md) | 1,120,403 | 436 | 129,879,221 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum` |
| [NL_CK_ChokyoChaku](NL_CK_ChokyoChaku.md) | 1,120,403 | 632 | 477,948,602 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum`, `ChokyoChakuIdx` |
| [NL_CK_KisyuChaku](NL_CK_KisyuChaku.md) | 1,120,403 | 632 | 461,241,833 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum`, `KisyuChakuIdx` |
| [NL_CS_COURSE](NL_CS_COURSE.md) | 119 | 8 | 107,693 | `JyoCD`, `Kyori`, `TrackCD`, `KaishuDate` |
| [NL_DM_INFO](NL_DM_INFO.md) | 85,378 | 82 | 7,876,113 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_HC_HANRO](NL_HC_HANRO.md) | 11,953,682 | 14 | 120,136,223 | `TresenKubun`, `ChokyoDate`, `ChokyoTime`, `KettoNum` |
| [NL_HN_HANSYOKU](NL_HN_HANSYOKU.md) | 161,995 | 19 | 8,371,929 | `HansyokuNum` |
| [NL_HR_PAY](NL_HR_PAY.md) | 139,833 | 199 | 6,823,421 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_HS_SALE](NL_HS_SALE.md) | 55,360 | 14 | 958,451 | `KettoNum`, `SaleCode`, `FromDate` |
| [NL_HY_BAMEIORIGIN](NL_HY_BAMEIORIGIN.md) | 179,265 | 6 | 7,003,993 | `KettoNum` |
| [NL_JG_JOGAIBA](NL_JG_JOGAIBA.md) | 838,548 | 14 | 6,415,746 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `KettoNum`, `ShutsubaTohyoJun` |
| [NL_KS_KISYU](NL_KS_KISYU.md) | 1,566 | 621 | 818,581 | `KisyuCode` |
| [NL_O1_ODDS_TANFUKUWAKU](NL_O1_ODDS_TANFUKUWAKU.md) | 115,228 | 323 | 38,800,698 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O2_ODDS_UMAREN](NL_O2_ODDS_UMAREN.md) | 112,565 | 473 | 92,639,430 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O3_ODDS_WIDE](NL_O3_ODDS_WIDE.md) | 92,326 | 626 | 118,827,308 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O4_ODDS_UMATAN](NL_O4_ODDS_UMATAN.md) | 83,985 | 932 | 170,662,322 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O5_ODDS_SANREN](NL_O5_ODDS_SANREN.md) | 84,009 | 14 | 842,629 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O5_OddsSanrenInfo](NL_O5_OddsSanrenInfo.md) | 35,311,083 | 10 | 243,222,473 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `OddsSanrenInfoIdx` |
| [NL_O6_ODDS_SANRENTAN](NL_O6_ODDS_SANRENTAN.md) | 67,533 | 14 | 690,974 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O6_OddsSanrentanInfo](NL_O6_OddsSanrentanInfo.md) | 170,970,762 | 10 | 1,419,781,599 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `OddsSanrentanInfoIdx` |
| [NL_RA_RACE](NL_RA_RACE.md) | 242,463 | 110 | 20,708,585 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_RC_RECORD](NL_RC_RECORD.md) | 2,151 | 48 | 116,799 | `RecInfoKubun`, `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `TokuNum`, `SyubetuCD`, `Kyori`, `TrackCD` |
| [NL_SE_RACE_UMA](NL_SE_RACE_UMA.md) | 2,898,749 | 73 | 138,301,468 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `KettoNum` |
| [NL_SK_SANKU](NL_SK_SANKU.md) | 427,328 | 26 | 15,344,298 | `KettoNum` |
| [NL_TM_INFO](NL_TM_INFO.md) | 54,909 | 46 | 1,489,688 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_UM_UMA](NL_UM_UMA.md) | 215,202 | 227 | 46,252,132 | `KettoNum` |
| [NL_WC_WOOD](NL_WC_WOOD.md) | 783,024 | 29 | 16,923,537 | `TresenKubun`, `ChokyoDate`, `ChokyoTime`, `KettoNum` |
| [NL_YS_SCHEDULE](NL_YS_SCHEDULE.md) | 7,526 | 45 | 93,864 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji` |
| [RT_O1_ODDS_TANFUKUWAKU](RT_O1_ODDS_TANFUKUWAKU.md) | 77 | 323 | 115,311 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `HappyoTime` |
| [RT_O2_ODDS_UMAREN](RT_O2_ODDS_UMAREN.md) | 77 | 473 | 192,106 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `HappyoTime` |
| [SY_PROC_FILES](SY_PROC_FILES.md) | 8,004 | 9 | 315,479 | `FileName` |
| **合計** | **233,009,507** | **7,979** | **4,723,374,937** | — |

## 物理スキーマの照合

| 確認項目 | 結果 |
| --- | --- |
| 表・ファイル | SQLiteの通常表39件とsnapshot Parquet39件が同名で対応し、過不足なし。 |
| 列 | 7,979列すべてで名前・順序が一致。 |
| 型 | SQLite宣言は`TEXT`7,976列、`DATETIME`3列。Parquetは全列`string`。 |
| NULL許容 | Parquetは全7,979列がNULL許容。rawの明示NOT NULL182列もParquetでは強制しない。 |
| キー | SQLiteの主キー列は183列。ParquetファイルはPK/FK/CHECK/既定値を強制しない。 |
| 行数 | raw-to-Parquet処理の表別行数検証とsnapshotメタデータが一致し、合計233,009,507行。 |
| 値 | 文字列/NULL以外の実値は変換境界で停止する。全セルの独立比較は未実施。 |

## 未確定事項

`To confirm`は確認済み事実ではない。以下は業務責任者・データ提供元・運用責任者・セキュリティ責任者への確認事項である。

| 対象 | 確認する質問 |
| --- | --- |
| 取得元・利用条件・所有者 | 正式な提供元、原本の版、利用権限、各表の管理責任者は誰か。 |
| 表の論理名・目的・粒度・利用先 | 各表は何を1行として表し、何に使用し、どこへ提供するか。 |
| 各列の論理名・意味・単位・コード値・長さ | 各物理列の正式名称、意味、許容値、長さ、空白/ゼロ日付の扱いは何か。 |
| 更新・保持 | 取得と再変換の頻度、提供期限、snapshotとrawの保持・更新方法は何か。 |
| キー・関係・品質規則 | 宣言主キーが業務キーか、表間関係が必須か、欠損・重複・妥当性の合格基準は何か。 |
| 機微区分・アクセス権 | 各表・列の機微区分と必要なアクセス制御は何か。 |

## 根拠と制限

- 実物: `data/raw/race.db`の`sqlite_schema`/`PRAGMA table_info`、`data/processed/CURRENT`、snapshot Parquetのメタデータ。データの値は定義書に掲載しない。
- 実装・設定: `config/data.toml`、`src/main.py`、`src/data/preprocesser/read_sqlite.py`、`src/data/preprocesser/snapshot.py`。
- 再作成日: 2026-10-06。既存の平置き`data/processed/*.parquet`はレガシー成果物として上書きせず、今回の定義書はCURRENTのsnapshotを対象とした。
- 業務仕様書、提供元の仕様、所有者への確認は得られていない。業務上の型・意味・必須性・品質合否は定義していない。
