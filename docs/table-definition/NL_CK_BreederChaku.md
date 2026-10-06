# NL_CK_BreederChaku（processed snapshot）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_CK_BreederChaku` |
| 論理名 | To confirm |
| 層・形式 | `processed snapshot`、Parquet |
| 保存先 | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_CK_BreederChaku.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_CK_BreederChaku` 表 |
| 取得元 | To confirm |
| 技術的な目的 | raw のユーザー表。入力表の各行・各列を同名のParquetへ保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。学習・分析・予測での個別利用は未確認。 |
| 作成・更新方法 | `uv run python src/main.py preprocess rebuild`。一時領域で完成・検証後に `CURRENT` を切り替える。 |
| 更新頻度 | To confirm。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum`, `BreederChakuIdx` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 1,120,403 行・29 列 |
| 確認時のファイルサイズ | 33,803,014 byte |
| 品質確認 | rawとの表名・列名・列順、変換時の行数、Parquetスキーマを照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_CK_BreederChaku` 表 → `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_CK_BreederChaku.parquet`。
全列を同名・同順で保存し、SQLiteの文字列値と`NULL`をParquetの`string`/`NULL`として書き出す。
空白・日付風の値を置換せず、行の除外、結合、重複除去、集計、日時解析、欠損補完は行わない。

## 列定義

`NULL可`はParquetスキーマの許容設定であり、実データ中のNULL存在数を示さない。
`raw制約`は入力SQLiteの宣言であり、Parquetでは強制されない。

| 物理列名 | 論理名 | 意味 | Parquet型・長さ | NULL可 | 既定値 | processedのキー・制約 | raw列・宣言型・制約 | 加工 | 機微区分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `idYear` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idYear` (`TEXT`; PK#1, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idMonthDay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idMonthDay` (`TEXT`; PK#2, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idJyoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idJyoCD` (`TEXT`; PK#3, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idKaiji` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idKaiji` (`TEXT`; PK#4, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idNichiji` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idNichiji` (`TEXT`; PK#5, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idRaceNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idRaceNum` (`TEXT`; PK#6, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `UmaChakuKettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuKettoNum` (`TEXT`; PK#7, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `BreederChakuIdx` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuIdx` (`TEXT`; PK#8, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `BreederChakuBreederCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuBreederCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuBreederName_Co` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuBreederName_Co` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuBreederName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuBreederName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei0SetYear` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei0SetYear` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei0HonSyokinTotal` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei0HonSyokinTotal` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei0FukaSyokin` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei0FukaSyokin` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei1SetYear` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei1SetYear` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei1HonSyokinTotal` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei1HonSyokinTotal` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei1FukaSyokin` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei1FukaSyokin` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederChakuHonRuikei1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederChakuHonRuikei1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・件数: 当該snapshot Parquetファイルのメタデータ。
- 表名・列名・列順・出力行数はraw-to-Parquet処理と再照合で一致。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
