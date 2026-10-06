# RT_O2_ODDS_UMAREN（processed snapshot）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `RT_O2_ODDS_UMAREN` |
| 論理名 | To confirm |
| 層・形式 | `processed snapshot`、Parquet |
| 保存先 | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/RT_O2_ODDS_UMAREN.parquet` |
| 直接の入力 | `data/raw/race.db` の `RT_O2_ODDS_UMAREN` 表 |
| 取得元 | To confirm |
| 技術的な目的 | realtime staging 表。入力表の各行・各列を同名のParquetへ保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。学習・分析・予測での個別利用は未確認。 |
| 作成・更新方法 | `uv run python src/main.py preprocess rebuild`。一時領域で完成・検証後に `CURRENT` を切り替える。 |
| 更新頻度 | To confirm。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji`, `idRaceNum`, `HappyoTime` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 77 行・473 列 |
| 確認時のファイルサイズ | 192,106 byte |
| 品質確認 | rawとの表名・列名・列順、変換時の行数、Parquetスキーマを照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `RT_O2_ODDS_UMAREN` 表 → `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/RT_O2_ODDS_UMAREN.parquet`。
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
| `HappyoTime` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `HappyoTime` (`TEXT`; PK#7, NOT NULL) | 文字列/NULLを保持 | To confirm |
| `TorokuTosu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TorokuTosu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `SyussoTosu` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `SyussoTosu` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `UmarenFlag` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `UmarenFlag` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo0Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo0Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo0Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo0Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo1Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo1Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo1Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo1Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo2Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo2Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo2Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo2Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo3Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo3Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo3Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo3Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo3Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo3Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo4Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo4Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo4Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo4Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo4Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo4Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo5Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo5Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo5Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo5Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo5Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo5Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo6Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo6Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo6Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo6Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo6Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo6Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo7Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo7Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo7Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo7Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo7Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo7Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo8Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo8Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo8Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo8Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo8Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo8Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo9Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo9Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo9Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo9Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo9Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo9Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo10Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo10Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo10Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo10Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo10Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo10Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo11Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo11Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo11Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo11Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo11Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo11Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo12Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo12Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo12Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo12Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo12Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo12Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo13Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo13Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo13Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo13Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo13Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo13Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo14Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo14Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo14Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo14Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo14Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo14Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo15Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo15Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo15Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo15Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo15Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo15Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo16Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo16Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo16Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo16Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo16Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo16Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo17Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo17Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo17Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo17Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo17Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo17Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo18Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo18Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo18Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo18Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo18Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo18Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo19Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo19Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo19Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo19Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo19Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo19Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo20Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo20Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo20Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo20Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo20Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo20Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo21Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo21Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo21Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo21Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo21Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo21Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo22Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo22Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo22Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo22Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo22Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo22Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo23Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo23Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo23Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo23Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo23Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo23Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo24Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo24Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo24Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo24Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo24Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo24Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo25Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo25Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo25Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo25Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo25Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo25Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo26Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo26Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo26Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo26Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo26Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo26Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo27Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo27Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo27Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo27Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo27Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo27Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo28Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo28Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo28Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo28Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo28Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo28Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo29Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo29Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo29Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo29Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo29Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo29Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo30Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo30Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo30Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo30Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo30Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo30Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo31Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo31Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo31Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo31Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo31Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo31Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo32Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo32Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo32Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo32Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo32Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo32Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo33Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo33Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo33Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo33Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo33Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo33Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo34Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo34Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo34Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo34Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo34Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo34Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo35Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo35Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo35Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo35Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo35Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo35Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo36Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo36Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo36Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo36Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo36Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo36Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo37Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo37Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo37Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo37Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo37Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo37Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo38Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo38Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo38Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo38Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo38Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo38Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo39Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo39Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo39Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo39Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo39Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo39Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo40Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo40Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo40Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo40Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo40Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo40Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo41Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo41Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo41Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo41Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo41Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo41Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo42Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo42Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo42Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo42Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo42Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo42Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo43Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo43Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo43Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo43Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo43Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo43Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo44Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo44Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo44Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo44Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo44Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo44Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo45Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo45Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo45Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo45Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo45Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo45Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo46Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo46Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo46Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo46Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo46Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo46Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo47Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo47Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo47Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo47Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo47Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo47Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo48Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo48Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo48Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo48Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo48Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo48Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo49Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo49Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo49Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo49Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo49Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo49Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo50Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo50Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo50Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo50Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo50Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo50Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo51Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo51Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo51Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo51Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo51Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo51Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo52Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo52Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo52Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo52Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo52Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo52Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo53Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo53Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo53Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo53Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo53Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo53Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo54Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo54Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo54Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo54Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo54Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo54Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo55Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo55Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo55Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo55Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo55Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo55Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo56Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo56Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo56Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo56Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo56Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo56Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo57Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo57Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo57Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo57Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo57Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo57Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo58Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo58Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo58Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo58Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo58Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo58Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo59Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo59Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo59Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo59Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo59Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo59Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo60Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo60Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo60Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo60Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo60Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo60Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo61Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo61Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo61Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo61Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo61Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo61Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo62Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo62Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo62Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo62Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo62Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo62Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo63Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo63Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo63Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo63Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo63Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo63Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo64Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo64Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo64Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo64Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo64Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo64Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo65Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo65Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo65Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo65Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo65Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo65Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo66Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo66Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo66Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo66Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo66Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo66Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo67Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo67Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo67Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo67Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo67Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo67Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo68Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo68Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo68Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo68Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo68Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo68Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo69Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo69Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo69Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo69Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo69Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo69Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo70Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo70Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo70Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo70Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo70Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo70Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo71Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo71Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo71Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo71Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo71Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo71Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo72Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo72Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo72Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo72Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo72Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo72Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo73Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo73Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo73Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo73Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo73Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo73Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo74Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo74Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo74Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo74Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo74Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo74Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo75Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo75Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo75Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo75Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo75Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo75Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo76Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo76Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo76Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo76Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo76Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo76Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo77Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo77Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo77Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo77Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo77Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo77Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo78Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo78Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo78Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo78Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo78Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo78Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo79Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo79Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo79Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo79Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo79Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo79Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo80Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo80Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo80Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo80Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo80Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo80Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo81Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo81Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo81Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo81Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo81Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo81Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo82Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo82Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo82Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo82Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo82Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo82Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo83Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo83Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo83Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo83Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo83Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo83Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo84Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo84Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo84Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo84Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo84Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo84Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo85Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo85Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo85Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo85Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo85Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo85Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo86Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo86Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo86Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo86Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo86Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo86Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo87Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo87Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo87Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo87Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo87Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo87Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo88Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo88Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo88Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo88Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo88Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo88Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo89Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo89Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo89Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo89Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo89Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo89Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo90Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo90Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo90Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo90Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo90Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo90Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo91Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo91Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo91Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo91Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo91Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo91Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo92Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo92Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo92Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo92Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo92Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo92Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo93Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo93Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo93Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo93Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo93Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo93Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo94Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo94Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo94Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo94Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo94Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo94Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo95Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo95Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo95Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo95Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo95Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo95Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo96Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo96Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo96Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo96Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo96Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo96Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo97Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo97Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo97Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo97Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo97Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo97Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo98Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo98Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo98Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo98Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo98Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo98Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo99Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo99Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo99Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo99Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo99Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo99Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo100Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo100Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo100Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo100Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo100Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo100Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo101Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo101Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo101Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo101Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo101Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo101Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo102Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo102Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo102Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo102Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo102Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo102Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo103Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo103Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo103Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo103Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo103Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo103Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo104Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo104Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo104Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo104Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo104Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo104Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo105Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo105Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo105Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo105Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo105Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo105Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo106Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo106Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo106Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo106Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo106Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo106Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo107Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo107Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo107Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo107Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo107Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo107Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo108Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo108Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo108Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo108Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo108Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo108Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo109Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo109Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo109Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo109Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo109Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo109Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo110Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo110Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo110Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo110Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo110Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo110Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo111Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo111Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo111Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo111Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo111Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo111Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo112Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo112Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo112Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo112Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo112Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo112Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo113Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo113Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo113Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo113Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo113Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo113Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo114Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo114Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo114Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo114Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo114Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo114Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo115Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo115Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo115Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo115Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo115Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo115Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo116Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo116Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo116Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo116Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo116Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo116Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo117Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo117Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo117Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo117Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo117Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo117Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo118Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo118Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo118Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo118Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo118Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo118Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo119Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo119Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo119Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo119Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo119Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo119Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo120Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo120Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo120Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo120Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo120Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo120Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo121Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo121Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo121Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo121Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo121Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo121Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo122Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo122Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo122Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo122Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo122Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo122Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo123Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo123Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo123Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo123Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo123Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo123Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo124Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo124Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo124Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo124Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo124Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo124Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo125Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo125Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo125Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo125Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo125Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo125Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo126Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo126Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo126Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo126Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo126Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo126Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo127Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo127Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo127Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo127Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo127Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo127Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo128Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo128Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo128Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo128Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo128Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo128Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo129Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo129Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo129Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo129Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo129Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo129Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo130Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo130Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo130Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo130Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo130Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo130Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo131Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo131Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo131Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo131Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo131Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo131Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo132Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo132Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo132Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo132Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo132Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo132Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo133Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo133Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo133Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo133Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo133Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo133Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo134Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo134Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo134Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo134Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo134Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo134Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo135Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo135Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo135Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo135Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo135Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo135Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo136Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo136Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo136Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo136Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo136Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo136Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo137Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo137Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo137Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo137Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo137Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo137Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo138Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo138Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo138Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo138Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo138Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo138Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo139Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo139Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo139Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo139Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo139Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo139Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo140Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo140Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo140Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo140Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo140Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo140Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo141Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo141Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo141Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo141Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo141Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo141Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo142Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo142Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo142Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo142Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo142Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo142Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo143Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo143Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo143Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo143Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo143Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo143Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo144Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo144Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo144Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo144Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo144Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo144Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo145Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo145Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo145Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo145Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo145Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo145Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo146Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo146Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo146Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo146Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo146Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo146Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo147Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo147Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo147Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo147Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo147Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo147Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo148Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo148Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo148Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo148Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo148Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo148Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo149Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo149Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo149Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo149Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo149Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo149Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo150Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo150Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo150Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo150Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo150Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo150Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo151Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo151Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo151Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo151Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo151Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo151Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo152Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo152Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo152Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo152Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsUmarenInfo152Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsUmarenInfo152Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TotalHyosuUmaren` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TotalHyosuUmaren` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・件数: 当該snapshot Parquetファイルのメタデータ。
- 表名・列名・列順・出力行数はraw-to-Parquet処理と再照合で一致。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
