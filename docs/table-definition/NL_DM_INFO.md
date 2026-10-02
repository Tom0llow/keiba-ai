# NL_DM_INFO（processed）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_DM_INFO` |
| 論理名 | To confirm |
| 層・形式 | `processed`、Parquet |
| 保存先 | `data/processed/NL_DM_INFO.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_DM_INFO` 表 |
| 取得元 | To confirm |
| 技術的な目的 | 入力表の各行・各列を同名のParquetへ1対1で保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。現在確認できるdatamartはない。 |
| 作成・更新方法 | `src/convert_race.py` から `src/data/race_data.py` の変換処理を実行する。既存の出力は上書きしない。 |
| 更新頻度 | To confirm。自動更新の設定は確認されていない。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 38,596 行・82 列 |
| 確認時のファイルサイズ | 3,600,149 byte |
| 品質確認 | 入力と出力の表名・列名・列順、変換時の行数とParquetメタデータ行数を照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_DM_INFO` 表 → `data/processed/NL_DM_INFO.parquet`。
全列を同名・同順で保存し、SQLiteの`TEXT`/`DATETIME`宣言列の実値をParquetの`string`へ書き出す。
`NULL`と文字列の空白・日付風の値を保持し、行の除外、結合、重複除去、集計、日時解析、欠損補完は行わない。
変換実装は文字列・`NULL`以外の実値を検出すると停止する。

## 列定義

`NULL可`はParquetスキーマの許容設定であり、実データ中のNULL存在数を示さない。
`raw制約`は入力SQLiteの宣言であり、Parquetでは強制されない。
全列の論理名・業務上の意味・機微区分は[未確定事項](README.md#未確定事項)に従って確認する。

| 物理列名 | 論理名 | 意味 | Parquet型・長さ | NULL可 | 既定値 | processedのキー・制約 | raw列・宣言型・制約 | 加工 | 機微区分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `headRecordSpec` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `headRecordSpec` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `headDataKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `headDataKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `headMakeDate` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `headMakeDate` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `idYear` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idYear` (`TEXT`; PK#1, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idMonthDay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idMonthDay` (`TEXT`; PK#2, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idJyoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idJyoCD` (`TEXT`; PK#3, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idKaiji` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idKaiji` (`TEXT`; PK#4, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idNichiji` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idNichiji` (`TEXT`; PK#5, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idRaceNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idRaceNum` (`TEXT`; PK#6, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `MakeHM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `MakeHM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo0Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo0Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo0DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo0DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo0DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo0DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo0DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo0DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo1Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo1Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo1DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo1DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo1DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo1DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo1DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo1DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo2Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo2Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo2DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo2DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo2DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo2DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo2DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo2DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo3Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo3Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo3DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo3DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo3DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo3DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo3DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo3DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo4Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo4Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo4DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo4DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo4DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo4DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo4DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo4DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo5Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo5Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo5DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo5DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo5DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo5DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo5DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo5DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo6Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo6Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo6DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo6DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo6DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo6DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo6DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo6DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo7Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo7Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo7DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo7DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo7DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo7DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo7DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo7DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo8Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo8Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo8DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo8DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo8DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo8DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo8DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo8DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo9Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo9Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo9DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo9DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo9DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo9DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo9DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo9DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo10Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo10Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo10DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo10DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo10DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo10DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo10DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo10DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo11Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo11Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo11DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo11DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo11DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo11DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo11DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo11DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo12Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo12Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo12DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo12DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo12DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo12DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo12DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo12DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo13Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo13Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo13DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo13DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo13DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo13DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo13DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo13DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo14Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo14Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo14DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo14DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo14DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo14DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo14DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo14DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo15Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo15Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo15DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo15DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo15DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo15DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo15DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo15DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo16Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo16Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo16DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo16DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo16DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo16DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo16DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo16DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo17Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo17Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo17DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo17DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo17DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo17DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMInfo17DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMInfo17DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・NULL許容・件数: 当該Parquetファイルのメタデータ。
- 表名・列名・列順は入力と出力で一致。物理スキーマ上の列差分はない。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
