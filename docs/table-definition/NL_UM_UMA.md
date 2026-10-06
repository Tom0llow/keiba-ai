# NL_UM_UMA（processed snapshot）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_UM_UMA` |
| 論理名 | To confirm |
| 層・形式 | `processed snapshot`、Parquet |
| 保存先 | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_UM_UMA.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_UM_UMA` 表 |
| 取得元 | To confirm |
| 技術的な目的 | raw のユーザー表。入力表の各行・各列を同名のParquetへ保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。学習・分析・予測での個別利用は未確認。 |
| 作成・更新方法 | `uv run python src/main.py preprocess rebuild`。一時領域で完成・検証後に `CURRENT` を切り替える。 |
| 更新頻度 | To confirm。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `KettoNum` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 215,202 行・227 列 |
| 確認時のファイルサイズ | 46,252,132 byte |
| 品質確認 | rawとの表名・列名・列順、変換時の行数、Parquetスキーマを照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_UM_UMA` 表 → `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_UM_UMA.parquet`。
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
| `KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KettoNum` (`TEXT`; PK#1, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `DelKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DelKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RegDate` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RegDate` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DelDate` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DelDate` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BirthDate` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BirthDate` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BameiKana` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BameiKana` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BameiEng` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BameiEng` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ZaikyuFlag` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ZaikyuFlag` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Reserved` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Reserved` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaKigoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaKigoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SexCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SexCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HinsyuCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HinsyuCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KeiroCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KeiroCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info0HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info0HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info0Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info0Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info1HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info1HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info1Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info1Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info2HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info2HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info2Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info2Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info3HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info3HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info3Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info3Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info4HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info4HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info4Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info4Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info5HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info5HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info5Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info5Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info6HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info6HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info6Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info6Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info7HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info7HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info7Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info7Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info8HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info8HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info8Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info8Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info9HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info9HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info9Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info9Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info10HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info10HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info10Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info10Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info11HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info11HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info11Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info11Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info12HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info12HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info12Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info12Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info13HansyokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info13HansyokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ketto3Info13Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ketto3Info13Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TozaiCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TozaiCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChokyosiCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChokyosiCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChokyosiRyakusyo` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChokyosiRyakusyo` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Syotai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Syotai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BreederName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BreederName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SanchiName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SanchiName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BanusiCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BanusiCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BanusiName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BanusiName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RuikeiHonsyoHeiti` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RuikeiHonsyoHeiti` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RuikeiHonsyoSyogai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RuikeiHonsyoSyogai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RuikeiFukaHeichi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RuikeiFukaHeichi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RuikeiFukaSyogai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RuikeiFukaSyogai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RuikeiSyutokuHeichi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RuikeiSyutokuHeichi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RuikeiSyutokuSyogai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RuikeiSyutokuSyogai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuSogoChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuSogoChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuSogoChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuSogoChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuSogoChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuSogoChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuSogoChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuSogoChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuSogoChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuSogoChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuSogoChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuSogoChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuChuoChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuChuoChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuChuoChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuChuoChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuChuoChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuChuoChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuChuoChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuChuoChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuChuoChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuChuoChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuChuoChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuChuoChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa6ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa6ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa6ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa6ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa6ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa6ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa6ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa6ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa6ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa6ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuBa6ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuBa6ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai6ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai6ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai6ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai6ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai6ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai6ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai6ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai6ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai6ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai6ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai6ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai6ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai7ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai7ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai7ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai7ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai7ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai7ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai7ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai7ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai7ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai7ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai7ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai7ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai8ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai8ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai8ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai8ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai8ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai8ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai8ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai8ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai8ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai8ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai8ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai8ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai9ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai9ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai9ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai9ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai9ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai9ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai9ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai9ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai9ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai9ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai9ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai9ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai10ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai10ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai10ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai10ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai10ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai10ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai10ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai10ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai10ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai10ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai10ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai10ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai11ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai11ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai11ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai11ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai11ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai11ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai11ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai11ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai11ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai11ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuJyotai11ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuJyotai11ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori0ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori0ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori0ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori0ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori0ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori0ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori0ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori0ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori0ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori0ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori0ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori0ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori1ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori1ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori1ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori1ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori1ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori1ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori1ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori1ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori1ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori1ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori1ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori1ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori2ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori2ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori2ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori2ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori2ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori2ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori2ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori2ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori2ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori2ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori2ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori2ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori3ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori3ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori3ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori3ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori3ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori3ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori3ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori3ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori3ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori3ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori3ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori3ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori4ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori4ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori4ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori4ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori4ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori4ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori4ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori4ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori4ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori4ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori4ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori4ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori5ChakuKaisu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori5ChakuKaisu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori5ChakuKaisu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori5ChakuKaisu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori5ChakuKaisu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori5ChakuKaisu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori5ChakuKaisu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori5ChakuKaisu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori5ChakuKaisu4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori5ChakuKaisu4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuKaisuKyori5ChakuKaisu5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuKaisuKyori5ChakuKaisu5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Kyakusitu0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Kyakusitu0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Kyakusitu1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Kyakusitu1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Kyakusitu2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Kyakusitu2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Kyakusitu3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Kyakusitu3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceCount` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceCount` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・件数: 当該snapshot Parquetファイルのメタデータ。
- 表名・列名・列順・出力行数はraw-to-Parquet処理と再照合で一致。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
