# NL_RA_RACE（processed snapshot）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_RA_RACE` |
| 論理名 | To confirm |
| 層・形式 | `processed snapshot`、Parquet |
| 保存先 | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_RA_RACE.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_RA_RACE` 表 |
| 取得元 | To confirm |
| 技術的な目的 | raw のユーザー表。入力表の各行・各列を同名のParquetへ保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。学習・分析・予測での個別利用は未確認。 |
| 作成・更新方法 | `uv run python src/main.py preprocess rebuild`。一時領域で完成・検証後に `CURRENT` を切り替える。 |
| 更新頻度 | To confirm。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 242,463 行・110 列 |
| 確認時のファイルサイズ | 20,708,585 byte |
| 品質確認 | rawとの表名・列名・列順、変換時の行数、Parquetスキーマを照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_RA_RACE` 表 → `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_RA_RACE.parquet`。
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
| `RaceInfoYoubiCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoYoubiCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoTokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoTokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoHondai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoHondai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoFukudai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoFukudai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoKakko` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoKakko` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoHondaiEng` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoHondaiEng` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoFukudaiEng` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoFukudaiEng` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoKakkoEng` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoKakkoEng` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoRyakusyo10` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoRyakusyo10` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoRyakusyo6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoRyakusyo6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoRyakusyo3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoRyakusyo3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RaceInfoNkai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RaceInfoNkai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `GradeCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `GradeCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `GradeCDBefore` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `GradeCDBefore` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyokenInfoSyubetuCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyokenInfoSyubetuCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyokenInfoKigoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyokenInfoKigoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyokenInfoJyuryoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyokenInfoJyuryoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyokenInfoJyokenCD0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyokenInfoJyokenCD0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyokenInfoJyokenCD1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyokenInfoJyokenCD1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyokenInfoJyokenCD2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyokenInfoJyokenCD2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyokenInfoJyokenCD3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyokenInfoJyokenCD3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyokenInfoJyokenCD4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyokenInfoJyokenCD4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyokenName` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyokenName` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Kyori` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Kyori` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `KyoriBefore` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `KyoriBefore` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TrackCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TrackCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TrackCDBefore` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TrackCDBefore` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CourseKubunCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CourseKubunCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CourseKubunCDBefore` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CourseKubunCDBefore` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Honsyokin0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Honsyokin0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Honsyokin1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Honsyokin1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Honsyokin2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Honsyokin2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Honsyokin3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Honsyokin3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Honsyokin4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Honsyokin4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Honsyokin5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Honsyokin5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Honsyokin6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Honsyokin6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HonsyokinBefore0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HonsyokinBefore0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HonsyokinBefore1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HonsyokinBefore1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HonsyokinBefore2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HonsyokinBefore2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HonsyokinBefore3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HonsyokinBefore3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HonsyokinBefore4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HonsyokinBefore4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Fukasyokin0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Fukasyokin0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Fukasyokin1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Fukasyokin1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Fukasyokin2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Fukasyokin2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Fukasyokin3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Fukasyokin3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `Fukasyokin4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `Fukasyokin4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FukasyokinBefore0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FukasyokinBefore0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FukasyokinBefore1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FukasyokinBefore1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FukasyokinBefore2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FukasyokinBefore2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HassoTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HassoTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HassoTimeBefore` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HassoTimeBefore` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TorokuTosu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TorokuTosu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SyussoTosu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SyussoTosu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `NyusenTosu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `NyusenTosu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TenkoBabaTenkoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TenkoBabaTenkoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TenkoBabaSibaBabaCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TenkoBabaSibaBabaCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TenkoBabaDirtBabaCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TenkoBabaDirtBabaCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime0` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime0` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime1` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime1` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime2` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime2` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime5` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime5` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime7` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime7` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime8` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime8` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime9` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime9` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime10` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime10` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime11` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime11` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime12` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime12` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime13` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime13` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime14` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime14` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime15` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime15` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime16` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime16` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime17` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime17` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime18` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime18` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime19` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime19` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime20` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime20` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime21` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime21` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime22` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime22` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime23` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime23` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `LapTime24` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `LapTime24` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SyogaiMileTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SyogaiMileTime` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTimeS3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTimeS3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTimeS4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTimeS4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTimeL3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTimeL3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `HaronTimeL4` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HaronTimeL4` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo0Corner` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo0Corner` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo0Syukaisu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo0Syukaisu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo0Jyuni` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo0Jyuni` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo1Corner` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo1Corner` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo1Syukaisu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo1Syukaisu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo1Jyuni` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo1Jyuni` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo2Corner` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo2Corner` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo2Syukaisu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo2Syukaisu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo2Jyuni` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo2Jyuni` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo3Corner` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo3Corner` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo3Syukaisu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo3Syukaisu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `CornerInfo3Jyuni` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `CornerInfo3Jyuni` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `RecordUpKubun` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `RecordUpKubun` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・件数: 当該snapshot Parquetファイルのメタデータ。
- 表名・列名・列順・出力行数はraw-to-Parquet処理と再照合で一致。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
