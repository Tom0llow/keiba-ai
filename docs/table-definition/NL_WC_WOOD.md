# NL_WC_WOOD（processed snapshot）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_WC_WOOD` |
| 論理名 | To confirm |
| 層・形式 | `processed snapshot`、Parquet |
| 保存先 | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_WC_WOOD.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_WC_WOOD` 表 |
| 取得元 | To confirm |
| 技術的な目的 | raw のユーザー表。入力表の各行・各列を同名のParquetへ保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。学習・分析・予測での個別利用は未確認。 |
| 作成・更新方法 | `uv run python src/main.py preprocess rebuild`。一時領域で完成・検証後に `CURRENT` を切り替える。 |
| 更新頻度 | To confirm。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `TresenKubun`, `ChokyoDate`, `ChokyoTime`, `KettoNum` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 783,024 行・29 列 |
| 確認時のファイルサイズ | 16,923,537 byte |
| 品質確認 | rawとの表名・列名・列順、変換時の行数、Parquetスキーマを照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_WC_WOOD` 表 → `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_WC_WOOD.parquet`。
全列を同名・同順で保存し、SQLiteの文字列値と`NULL`をParquetの`string`/`NULL`として書き出す。
空白・日付風の値を置換せず、行の除外、結合、重複除去、集計、日時解析、欠損補完は行わない。

## 列定義

`NULL可`はParquetスキーマの許容設定であり、実データ中のNULL存在数を示さない。
`raw制約`は入力SQLiteの宣言であり、Parquetでは強制されない。

| 物理列名 | 論理名 | 意味 | Parquet型・長さ | NULL可 | 既定値 | processedのキー・制約 | raw列・宣言型・制約 | 加工 | 機微区分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `headRecordSpec` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `headRecordSpec` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `headDataKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `headDataKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `headMakeDate` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `headMakeDate` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TresenKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TresenKubun` (`TEXT`; PK#1, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `ChokyoDate` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChokyoDate` (`TEXT`; PK#2, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `ChokyoTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChokyoTime` (`TEXT`; PK#3, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KettoNum` (`TEXT`; PK#4, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `Course` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Course` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BabaAround` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BabaAround` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `reserved` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `reserved` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTime10` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTime10` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime10` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime10` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTime9` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTime9` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime9` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime9` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTime8` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTime8` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime8` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime8` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTime7` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTime7` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime7` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime7` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTime6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTime6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTime5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTime5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTime4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTime4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTime3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTime3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTime2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTime2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime1` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・件数: 当該snapshot Parquetファイルのメタデータ。
- 表名・列名・列順・出力行数はraw-to-Parquet処理と再照合で一致。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
