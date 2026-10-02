# NL_HN_HANSYOKU（processed）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_HN_HANSYOKU` |
| 論理名 | To confirm |
| 層・形式 | `processed`、Parquet |
| 保存先 | `data/processed/NL_HN_HANSYOKU.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_HN_HANSYOKU` 表 |
| 取得元 | To confirm |
| 技術的な目的 | 入力表の各行・各列を同名のParquetへ1対1で保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。現在確認できるdatamartはない。 |
| 作成・更新方法 | `src/convert_race.py` から `src/data/race_data.py` の変換処理を実行する。既存の出力は上書きしない。 |
| 更新頻度 | To confirm。自動更新の設定は確認されていない。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `HansyokuNum` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 16,424 行・19 列 |
| 確認時のファイルサイズ | 937,781 byte |
| 品質確認 | 入力と出力の表名・列名・列順、変換時の行数とParquetメタデータ行数を照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_HN_HANSYOKU` 表 → `data/processed/NL_HN_HANSYOKU.parquet`。
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
| `HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HansyokuNum` (`TEXT`; PK#1, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `reserved` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `reserved` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KettoNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DelKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DelKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BameiKana` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BameiKana` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BameiEng` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BameiEng` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BirthYear` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BirthYear` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SexCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SexCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HinsyuCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HinsyuCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KeiroCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KeiroCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HansyokuMochiKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HansyokuMochiKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ImportYear` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ImportYear` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SanchiName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SanchiName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HansyokuFNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HansyokuFNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HansyokuMNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HansyokuMNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・NULL許容・件数: 当該Parquetファイルのメタデータ。
- 表名・列名・列順は入力と出力で一致。物理スキーマ上の列差分はない。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
