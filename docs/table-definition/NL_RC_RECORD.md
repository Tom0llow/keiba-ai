# NL_RC_RECORD（processed）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_RC_RECORD` |
| 論理名 | To confirm |
| 層・形式 | `processed`、Parquet |
| 保存先 | `data/processed/NL_RC_RECORD.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_RC_RECORD` 表 |
| 取得元 | To confirm |
| 技術的な目的 | 入力表の各行・各列を同名のParquetへ1対1で保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。現在確認できるdatamartはない。 |
| 作成・更新方法 | `src/convert_race.py` から `src/data/race_data.py` の変換処理を実行する。既存の出力は上書きしない。 |
| 更新頻度 | To confirm。自動更新の設定は確認されていない。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `RecInfoKubun`, `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `TokuNum`, `SyubetuCD`, `Kyori`, `TrackCD` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 2,118 行・48 列 |
| 確認時のファイルサイズ | 115,077 byte |
| 品質確認 | 入力と出力の表名・列名・列順、変換時の行数とParquetメタデータ行数を照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_RC_RECORD` 表 → `data/processed/NL_RC_RECORD.parquet`。
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
| `RecInfoKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecInfoKubun` (`TEXT`; PK#1, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idYear` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idYear` (`TEXT`; PK#2, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idMonthDay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idMonthDay` (`TEXT`; PK#3, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idJyoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idJyoCD` (`TEXT`; PK#4, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idKaiji` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idKaiji` (`TEXT`; PK#5, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idNichiji` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idNichiji` (`TEXT`; PK#6, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idRaceNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idRaceNum` (`TEXT`; PK#7, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `TokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokuNum` (`TEXT`; PK#8, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `Hondai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Hondai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `GradeCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `GradeCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SyubetuCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SyubetuCD` (`TEXT`; PK#9, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `Kyori` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Kyori` (`TEXT`; PK#10, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `TrackCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TrackCD` (`TEXT`; PK#11, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `RecKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TenkoBabaTenkoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TenkoBabaTenkoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TenkoBabaSibaBabaCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TenkoBabaSibaBabaCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TenkoBabaDirtBabaCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TenkoBabaDirtBabaCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo0KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo0KettoNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo0Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo0Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo0UmaKigoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo0UmaKigoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo0SexCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo0SexCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo0ChokyosiCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo0ChokyosiCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo0ChokyosiName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo0ChokyosiName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo0Futan` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo0Futan` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo0KisyuCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo0KisyuCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo0KisyuName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo0KisyuName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo1KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo1KettoNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo1Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo1Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo1UmaKigoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo1UmaKigoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo1SexCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo1SexCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo1ChokyosiCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo1ChokyosiCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo1ChokyosiName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo1ChokyosiName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo1Futan` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo1Futan` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo1KisyuCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo1KisyuCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo1KisyuName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo1KisyuName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo2KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo2KettoNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo2Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo2Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo2UmaKigoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo2UmaKigoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo2SexCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo2SexCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo2ChokyosiCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo2ChokyosiCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo2ChokyosiName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo2ChokyosiName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo2Futan` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo2Futan` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo2KisyuCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo2KisyuCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecUmaInfo2KisyuName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecUmaInfo2KisyuName` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・NULL許容・件数: 当該Parquetファイルのメタデータ。
- 表名・列名・列順は入力と出力で一致。物理スキーマ上の列差分はない。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
