# NL_SE_RACE_UMA（processed snapshot）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_SE_RACE_UMA` |
| 論理名 | To confirm |
| 層・形式 | `processed snapshot`、Parquet |
| 保存先 | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_SE_RACE_UMA.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_SE_RACE_UMA` 表 |
| 取得元 | To confirm |
| 技術的な目的 | raw のユーザー表。入力表の各行・各列を同名のParquetへ保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。学習・分析・予測での個別利用は未確認。 |
| 作成・更新方法 | `uv run python src/main.py preprocess rebuild`。一時領域で完成・検証後に `CURRENT` を切り替える。 |
| 更新頻度 | To confirm。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `KettoNum` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 2,898,749 行・73 列 |
| 確認時のファイルサイズ | 138,301,468 byte |
| 品質確認 | rawとの表名・列名・列順、変換時の行数、Parquetスキーマを照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_SE_RACE_UMA` 表 → `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_SE_RACE_UMA.parquet`。
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
| `Wakuban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Wakuban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KettoNum` (`TEXT`; PK#7, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmaKigoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmaKigoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SexCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SexCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HinsyuCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HinsyuCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KeiroCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KeiroCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Barei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Barei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TozaiCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TozaiCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChokyosiCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChokyosiCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChokyosiRyakusyo` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChokyosiRyakusyo` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BanusiCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BanusiCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BanusiName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BanusiName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Fukusyoku` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Fukusyoku` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `reserved1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `reserved1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Futan` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Futan` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FutanBefore` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FutanBefore` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Blinker` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Blinker` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `reserved2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `reserved2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KisyuCode` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KisyuCode` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KisyuCodeBefore` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KisyuCodeBefore` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KisyuRyakusyo` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KisyuRyakusyo` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KisyuRyakusyoBefore` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KisyuRyakusyoBefore` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `MinaraiCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `MinaraiCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `MinaraiCDBefore` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `MinaraiCDBefore` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `BaTaijyu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `BaTaijyu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ZogenFugo` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ZogenFugo` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ZogenSa` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ZogenSa` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `IJyoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `IJyoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `NyusenJyuni` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `NyusenJyuni` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KakuteiJyuni` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KakuteiJyuni` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DochakuKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DochakuKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DochakuTosu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DochakuTosu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Time` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Time` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakusaCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakusaCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakusaCDP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakusaCDP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakusaCDPP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakusaCDPP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Jyuni1c` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Jyuni1c` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Jyuni2c` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Jyuni2c` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Jyuni3c` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Jyuni3c` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Jyuni4c` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Jyuni4c` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Honsyokin` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Honsyokin` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Fukasyokin` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Fukasyokin` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `reserved3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `reserved3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `reserved4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `reserved4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTimeL4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTimeL4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTimeL3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTimeL3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuUmaInfo0KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuUmaInfo0KettoNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuUmaInfo0Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuUmaInfo0Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuUmaInfo1KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuUmaInfo1KettoNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuUmaInfo1Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuUmaInfo1Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuUmaInfo2KettoNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuUmaInfo2KettoNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `ChakuUmaInfo2Bamei` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `ChakuUmaInfo2Bamei` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TimeDiff` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TimeDiff` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecordUpKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecordUpKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMGosaP` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMGosaP` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMGosaM` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMGosaM` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `DMJyuni` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `DMJyuni` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KyakusituKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KyakusituKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・件数: 当該snapshot Parquetファイルのメタデータ。
- 表名・列名・列順・出力行数はraw-to-Parquet処理と再照合で一致。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
