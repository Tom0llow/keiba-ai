# `data/processed` テーブル定義書

2026-10-02時点の`data/raw/race.db`と`data/processed/*.parquet`の実体を照合した物理定義。
35表、6,387列、122,183,431行、Parquet合計1,818,596,066 byte。
論理名、業務上の項目意味、品質基準は未承認のため、物理名から推測していない。

## データ経路と変換規則

| 段階 | 実体・状態 |
| --- | --- |
| source | To confirm（取得元、原本の版、取得条件）。 |
| raw | `data/raw/race.db`。取得元に対する無加工性は未確認。 |
| processed | `data/processed/<表名>.parquet`。35表を同名で1対1に保存。 |
| datamart | 現在確認できる実装はない。利用先はTo confirm。 |

`config/data.toml`が入力と出力のパスを定める。変換は`src/convert_race.py`から
`src/data/race_data.py`を呼び出す。入力の全列・行を保持し、`TEXT`/`DATETIME`宣言列の
文字列/NULLをParquetの`string`/NULLとして保存する。列名・列順を維持し、
空白や日付風の値を置換しない。行の除外、結合、重複除去、集計は行わない。
出力は一時ディレクトリで完成させ、既存の`data/processed`は上書きしない。

## 表一覧

行数・列数・サイズは2026-10-02時点のParquetメタデータとファイルから取得した。
raw側の主キーは参考情報であり、Parquet側の制約ではない。

| 表 | 行数 | 列数 | サイズ (byte) | raw側の宣言主キー |
| --- | ---: | ---: | ---: | --- |
| [NL_BN_BANUSI](NL_BN_BANUSI.md) | 8,663 | 27 | 711,927 | `BanusiCode` |
| [NL_BR_BREEDER](NL_BR_BREEDER.md) | 10,711 | 27 | 775,916 | `BreederCode` |
| [NL_BT_KEITO](NL_BT_KEITO.md) | 92 | 7 | 119,282 | `HansyokuNum` |
| [NL_CH_CHOKYOSI](NL_CH_CHOKYOSI.md) | 1,474 | 576 | 660,825 | `ChokyosiCode` |
| [NL_CK_BanusiChaku](NL_CK_BanusiChaku.md) | 543,657 | 29 | 16,994,468 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum`, `BanusiChakuIdx` |
| [NL_CK_BreederChaku](NL_CK_BreederChaku.md) | 543,657 | 29 | 16,307,079 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum`, `BreederChakuIdx` |
| [NL_CK_CHAKU](NL_CK_CHAKU.md) | 543,657 | 436 | 62,600,511 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum` |
| [NL_CK_ChokyoChaku](NL_CK_ChokyoChaku.md) | 543,657 | 632 | 234,543,755 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum`, `ChokyoChakuIdx` |
| [NL_CK_KisyuChaku](NL_CK_KisyuChaku.md) | 543,657 | 632 | 225,471,888 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum`, `KisyuChakuIdx` |
| [NL_CS_COURSE](NL_CS_COURSE.md) | 119 | 8 | 107,693 | `JyoCD`, `Kyori`, `TrackCD`, `KaishuDate` |
| [NL_DM_INFO](NL_DM_INFO.md) | 38,596 | 82 | 3,600,149 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_HC_HANRO](NL_HC_HANRO.md) | 5,285,052 | 14 | 53,170,217 | `TresenKubun`, `ChokyoDate`, `ChokyoTime`, `KettoNum` |
| [NL_HN_HANSYOKU](NL_HN_HANSYOKU.md) | 16,424 | 19 | 937,781 | `HansyokuNum` |
| [NL_HR_PAY](NL_HR_PAY.md) | 38,596 | 199 | 2,541,604 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_HS_SALE](NL_HS_SALE.md) | 53,008 | 14 | 921,667 | `KettoNum`, `SaleCode`, `FromDate` |
| [NL_HY_BAMEIORIGIN](NL_HY_BAMEIORIGIN.md) | 174,036 | 6 | 6,785,827 | `KettoNum` |
| [NL_JG_JOGAIBA](NL_JG_JOGAIBA.md) | 601,602 | 14 | 4,515,301 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `KettoNum`, `ShutsubaTohyoJun` |
| [NL_KS_KISYU](NL_KS_KISYU.md) | 1,559 | 621 | 801,915 | `KisyuCode` |
| [NL_O1_ODDS_TANFUKUWAKU](NL_O1_ODDS_TANFUKUWAKU.md) | 38,654 | 323 | 13,402,241 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O2_ODDS_UMAREN](NL_O2_ODDS_UMAREN.md) | 38,654 | 473 | 32,712,554 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O3_ODDS_WIDE](NL_O3_ODDS_WIDE.md) | 38,654 | 626 | 49,885,808 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O4_ODDS_UMATAN](NL_O4_ODDS_UMATAN.md) | 38,654 | 932 | 77,936,529 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O5_ODDS_SANREN](NL_O5_ODDS_SANREN.md) | 38,654 | 14 | 389,677 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O5_OddsSanrenInfo](NL_O5_OddsSanrenInfo.md) | 15,864,298 | 10 | 110,587,399 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `OddsSanrenInfoIdx` |
| [NL_O6_ODDS_SANRENTAN](NL_O6_ODDS_SANRENTAN.md) | 38,654 | 14 | 392,518 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_O6_OddsSanrentanInfo](NL_O6_OddsSanrentanInfo.md) | 95,185,788 | 10 | 784,912,837 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `OddsSanrentanInfoIdx` |
| [NL_RA_RACE](NL_RA_RACE.md) | 71,232 | 110 | 8,415,721 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_RC_RECORD](NL_RC_RECORD.md) | 2,118 | 48 | 115,077 | `RecInfoKubun`, `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `TokuNum`, `SyubetuCD`, `Kyori`, `TrackCD` |
| [NL_SE_RACE_UMA](NL_SE_RACE_UMA.md) | 865,016 | 73 | 44,399,914 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `KettoNum` |
| [NL_SK_SANKU](NL_SK_SANKU.md) | 59,073 | 26 | 2,038,895 | `KettoNum` |
| [NL_TM_INFO](NL_TM_INFO.md) | 37,187 | 46 | 1,003,375 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| [NL_UM_UMA](NL_UM_UMA.md) | 211,920 | 227 | 45,588,800 | `KettoNum` |
| [NL_WC_WOOD](NL_WC_WOOD.md) | 699,603 | 29 | 15,041,854 | `TresenKubun`, `ChokyoDate`, `ChokyoTime`, `KettoNum` |
| [NL_YS_SCHEDULE](NL_YS_SCHEDULE.md) | 3,179 | 45 | 53,165 | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji` |
| [SY_PROC_FILES](SY_PROC_FILES.md) | 3,876 | 9 | 151,897 | `FileName` |
| **合計** | **122,183,431** | **6,387** | **1,818,596,066** | — |

## 物理スキーマの照合

| 確認項目 | 結果 |
| --- | --- |
| 表・ファイル | SQLiteの通常表35件とParquetファイル35件が同名で対応し、過不足なし。 |
| 列 | 6,387列すべてで名前・順序が一致。隠し列なし。 |
| 型 | SQLite宣言は`TEXT`6,384列、`DATETIME`3列。Parquetは全列`string`。後者3列の宣言型は同一でないが、文字列値を保持する変換仕様どおり。 |
| NULL許容 | Parquetは全6,387列がNULL許容。SQLiteの明示`NOT NULL`168列もParquetでは強制しない。これは物理制約の差であり、実値にNULLがあることを示さない。 |
| キー・その他制約 | SQLiteは35表に主キー宣言、主キー列計169、FK/CHECK/既定値なし。ParquetファイルはPK/FK/CHECK/既定値を強制しない。 |
| 行数 | 変換中の入力行カウントと各Parquetメタデータの行数が一致。合計122,183,431行。 |
| 値 | 変換後の独立検証で全35表の先頭・末尾行の全列値が入力と一致。全セルの独立比較は未実施。 |

## 未確定事項

`To confirm`は確認済み事実ではない。担当者が未特定のため、以下の確認先は役割の候補であり、
実際の責任者を示さない。これらの質問は各表・各列に適用する。

| 対象 | 確認先の候補 | 確認する質問 |
| --- | --- | --- |
| 取得元・利用条件・所有者 | データ提供元、業務責任者 | 正式な提供元、原本の版、利用権限、各表の管理責任者は誰か。 |
| 表の論理名・目的・粒度・利用先 | 業務責任者、利用者 | 各表は何を1行として表し、何に使用し、どこへ提供するか。 |
| 各列の論理名・意味・単位・コード値・長さ | データ提供元、業務責任者 | 各物理列の正式名称、意味、許容値、長さ、空白/ゼロ日付の扱いは何か。 |
| 更新・保持 | データ提供元、運用責任者 | 取得と再変換の頻度、提供期限、原本と出力の保持・更新方法は何か。 |
| キー・関係・品質規則 | 業務責任者、データ品質責任者 | 宣言主キーが業務キーか、表間関係が必須か、欠損・重複・妥当性の合格基準は何か。 |
| 機微区分・アクセス権 | データ管理責任者、セキュリティ責任者 | 各表・列の機微区分と必要なアクセス制御は何か。 |

## 根拠と制限

- 実物: `data/raw/race.db`の`sqlite_schema`/`PRAGMA table_info`、各Parquetファイルのメタデータ。データの値は定義書に掲載しない。
- 実装・設定: `config/data.toml`、`src/convert_race.py`、`src/data/race_data.py`。
- 変換記録: `docs/data-preprocessing/race-parquet-2026-10-02.md`。評価時の未確認事項: `docs/data-assessment/race-db-2026-10-01.md`。`data/`とローカル検証用の`output/`はGit管理対象外。
- 業務仕様書、提供元の仕様、所有者への確認は得られていない。業務上の型・意味・必須性・品質合否は定義していない。
