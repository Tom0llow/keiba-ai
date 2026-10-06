# NL_CK_CHAKU（processed snapshot）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_CK_CHAKU` |
| 論理名 | To confirm |
| 層・形式 | `processed snapshot`、Parquet |
| 保存先 | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_CK_CHAKU.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_CK_CHAKU` 表 |
| 取得元 | To confirm |
| 技術的な目的 | raw のユーザー表。入力表の各行・各列を同名のParquetへ保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。学習・分析・予測での個別利用は未確認。 |
| 作成・更新方法 | `uv run python src/main.py preprocess rebuild`。一時領域で完成・検証後に `CURRENT` を切り替える。 |
| 更新頻度 | To confirm。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `UmaChakuKettoNum` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 1,120,403 行・436 列 |
| 確認時のファイルサイズ | 129,879,221 byte |
| 品質確認 | rawとの表名・列名・列順、変換時の行数、Parquetスキーマを照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_CK_CHAKU` 表 → `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_CK_CHAKU.parquet`。
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
| `idYear` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idYear` (`TEXT`; PK#1, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idMonthDay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idMonthDay` (`TEXT`; PK#2, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idJyoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idJyoCD` (`TEXT`; PK#3, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idKaiji` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idKaiji` (`TEXT`; PK#4, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idNichiji` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idNichiji` (`TEXT`; PK#5, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `idRaceNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `idRaceNum` (`TEXT`; PK#6, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `UmaChakuKettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuKettoNum` (`TEXT`; PK#7, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `UmaChakuBamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuBamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuRuikeiHonsyoHeiti` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuRuikeiHonsyoHeiti` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuRuikeiHonsyoSyogai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuRuikeiHonsyoSyogai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuRuikeiFukaHeichi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuRuikeiFukaHeichi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuRuikeiFukaSyogai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuRuikeiFukaSyogai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuRuikeiSyutokuHeichi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuRuikeiSyutokuHeichi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuRuikeiSyutokuSyogai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuRuikeiSyutokuSyogai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuSogoChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuSogoChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuSogoChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuSogoChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuSogoChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuSogoChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuSogoChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuSogoChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuSogoChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuSogoChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuSogoChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuSogoChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuChuoChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuChuoChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuChuoChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuChuoChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuChuoChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuChuoChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuChuoChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuChuoChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuChuoChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuChuoChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuChuoChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuChuoChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa6ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa6ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa6ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa6ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa6ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa6ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa6ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa6ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa6ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa6ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuBa6ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuBa6ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai6ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai6ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai6ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai6ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai6ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai6ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai6ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai6ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai6ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai6ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai6ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai6ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai7ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai7ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai7ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai7ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai7ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai7ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai7ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai7ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai7ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai7ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai7ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai7ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai8ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai8ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai8ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai8ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai8ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai8ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai8ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai8ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai8ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai8ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai8ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai8ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai9ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai9ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai9ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai9ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai9ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai9ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai9ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai9ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai9ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai9ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai9ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai9ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai10ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai10ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai10ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai10ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai10ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai10ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai10ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai10ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai10ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai10ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai10ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai10ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai11ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai11ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai11ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai11ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai11ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai11ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai11ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai11ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai11ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai11ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyotai11ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyotai11ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori6ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori6ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori6ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori6ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori6ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori6ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori6ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori6ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori6ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori6ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori6ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori6ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori7ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori7ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori7ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori7ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori7ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori7ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori7ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori7ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori7ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori7ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori7ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori7ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori8ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori8ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori8ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori8ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori8ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori8ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori8ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori8ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori8ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori8ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuSibaKyori8ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuSibaKyori8ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori6ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori6ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori6ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori6ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori6ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori6ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori6ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori6ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori6ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori6ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori6ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori6ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori7ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori7ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori7ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori7ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori7ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori7ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori7ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori7ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori7ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori7ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori7ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori7ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori8ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori8ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori8ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori8ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori8ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori8ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori8ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori8ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori8ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori8ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuDirtKyori8ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuDirtKyori8ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba6ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba6ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba6ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba6ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba6ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba6ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba6ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba6ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba6ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba6ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba6ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba6ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba7ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba7ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba7ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba7ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba7ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba7ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba7ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba7ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba7ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba7ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba7ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba7ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba8ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba8ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba8ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba8ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba8ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba8ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba8ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba8ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba8ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba8ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba8ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba8ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba9ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba9ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba9ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba9ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba9ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba9ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba9ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba9ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba9ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba9ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSiba9ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSiba9ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt6ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt6ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt6ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt6ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt6ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt6ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt6ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt6ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt6ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt6ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt6ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt6ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt7ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt7ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt7ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt7ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt7ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt7ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt7ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt7ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt7ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt7ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt7ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt7ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt8ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt8ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt8ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt8ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt8ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt8ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt8ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt8ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt8ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt8ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt8ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt8ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt9ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt9ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt9ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt9ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt9ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt9ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt9ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt9ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt9ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt9ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoDirt9ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoDirt9ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai6ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai7ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai8ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuChakuKaisuJyoSyogai9ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuKyakusitu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuKyakusitu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuKyakusitu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuKyakusitu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuKyakusitu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuKyakusitu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuKyakusitu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuKyakusitu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaChakuRaceCount` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaChakuRaceCount` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・件数: 当該snapshot Parquetファイルのメタデータ。
- 表名・列名・列順・出力行数はraw-to-Parquet処理と再照合で一致。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
