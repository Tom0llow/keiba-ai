# NL_HR_PAY（processed）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_HR_PAY` |
| 論理名 | To confirm |
| 層・形式 | `processed`、Parquet |
| 保存先 | `data/processed/NL_HR_PAY.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_HR_PAY` 表 |
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
| 確認時の行数・列数 | 38,596 行・199 列 |
| 確認時のファイルサイズ | 2,541,604 byte |
| 品質確認 | 入力と出力の表名・列名・列順、変換時の行数とParquetメタデータ行数を照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_HR_PAY` 表 → `data/processed/NL_HR_PAY.parquet`。
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
| `TorokuTosu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TorokuTosu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SyussoTosu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SyussoTosu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FuseirituFlag0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FuseirituFlag0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FuseirituFlag1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FuseirituFlag1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FuseirituFlag2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FuseirituFlag2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FuseirituFlag3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FuseirituFlag3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FuseirituFlag4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FuseirituFlag4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FuseirituFlag5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FuseirituFlag5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FuseirituFlag6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FuseirituFlag6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FuseirituFlag7` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FuseirituFlag7` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FuseirituFlag8` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FuseirituFlag8` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TokubaraiFlag0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokubaraiFlag0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TokubaraiFlag1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokubaraiFlag1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TokubaraiFlag2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokubaraiFlag2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TokubaraiFlag3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokubaraiFlag3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TokubaraiFlag4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokubaraiFlag4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TokubaraiFlag5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokubaraiFlag5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TokubaraiFlag6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokubaraiFlag6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TokubaraiFlag7` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokubaraiFlag7` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TokubaraiFlag8` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TokubaraiFlag8` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanFlag0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanFlag0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanFlag1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanFlag1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanFlag2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanFlag2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanFlag3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanFlag3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanFlag4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanFlag4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanFlag5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanFlag5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanFlag6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanFlag6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanFlag7` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanFlag7` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanFlag8` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanFlag8` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma7` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma7` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma8` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma8` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma9` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma9` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma10` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma10` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma11` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma11` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma12` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma12` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma13` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma13` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma14` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma14` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma15` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma15` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma16` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma16` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma17` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma17` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma18` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma18` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma19` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma19` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma20` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma20` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma21` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma21` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma22` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma22` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma23` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma23` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma24` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma24` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma25` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma25` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma26` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma26` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanUma27` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanUma27` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanWaku0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanWaku0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanWaku1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanWaku1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanWaku2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanWaku2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanWaku3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanWaku3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanWaku4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanWaku4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanWaku5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanWaku5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanWaku6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanWaku6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanWaku7` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanWaku7` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanDoWaku0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanDoWaku0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanDoWaku1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanDoWaku1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanDoWaku2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanDoWaku2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanDoWaku3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanDoWaku3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanDoWaku4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanDoWaku4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanDoWaku5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanDoWaku5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanDoWaku6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanDoWaku6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HenkanDoWaku7` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HenkanDoWaku7` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayTansyo0Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayTansyo0Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayTansyo0Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayTansyo0Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayTansyo0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayTansyo0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayTansyo1Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayTansyo1Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayTansyo1Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayTansyo1Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayTansyo1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayTansyo1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayTansyo2Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayTansyo2Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayTansyo2Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayTansyo2Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayTansyo2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayTansyo2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo0Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo0Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo0Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo0Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo1Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo1Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo1Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo1Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo2Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo2Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo2Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo2Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo3Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo3Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo3Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo3Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo3Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo3Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo4Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo4Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo4Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo4Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayFukusyo4Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayFukusyo4Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWakuren0Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWakuren0Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWakuren0Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWakuren0Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWakuren0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWakuren0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWakuren1Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWakuren1Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWakuren1Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWakuren1Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWakuren1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWakuren1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWakuren2Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWakuren2Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWakuren2Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWakuren2Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWakuren2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWakuren2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmaren0Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmaren0Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmaren0Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmaren0Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmaren0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmaren0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmaren1Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmaren1Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmaren1Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmaren1Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmaren1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmaren1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmaren2Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmaren2Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmaren2Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmaren2Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmaren2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmaren2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide0Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide0Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide0Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide0Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide1Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide1Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide1Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide1Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide2Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide2Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide2Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide2Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide3Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide3Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide3Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide3Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide3Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide3Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide4Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide4Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide4Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide4Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide4Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide4Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide5Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide5Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide5Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide5Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide5Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide5Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide6Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide6Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide6Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide6Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayWide6Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayWide6Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayReserved10Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayReserved10Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayReserved10Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayReserved10Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayReserved10Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayReserved10Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayReserved11Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayReserved11Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayReserved11Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayReserved11Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayReserved11Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayReserved11Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayReserved12Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayReserved12Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayReserved12Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayReserved12Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayReserved12Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayReserved12Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan0Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan0Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan0Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan0Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan1Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan1Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan1Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan1Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan2Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan2Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan2Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan2Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan3Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan3Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan3Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan3Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan3Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan3Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan4Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan4Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan4Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan4Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan4Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan4Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan5Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan5Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan5Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan5Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PayUmatan5Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PayUmatan5Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrenpuku0Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrenpuku0Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrenpuku0Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrenpuku0Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrenpuku0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrenpuku0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrenpuku1Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrenpuku1Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrenpuku1Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrenpuku1Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrenpuku1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrenpuku1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrenpuku2Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrenpuku2Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrenpuku2Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrenpuku2Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrenpuku2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrenpuku2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan0Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan0Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan0Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan0Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan1Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan1Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan1Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan1Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan2Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan2Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan2Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan2Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan3Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan3Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan3Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan3Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan3Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan3Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan4Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan4Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan4Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan4Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan4Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan4Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan5Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan5Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan5Pay` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan5Pay` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `PaySanrentan5Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `PaySanrentan5Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・NULL許容・件数: 当該Parquetファイルのメタデータ。
- 表名・列名・列順は入力と出力で一致。物理スキーマ上の列差分はない。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
