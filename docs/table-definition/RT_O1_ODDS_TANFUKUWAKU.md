# RT_O1_ODDS_TANFUKUWAKU（processed snapshot）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `RT_O1_ODDS_TANFUKUWAKU` |
| 論理名 | To confirm |
| 層・形式 | `processed snapshot`、Parquet |
| 保存先 | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/RT_O1_ODDS_TANFUKUWAKU.parquet` |
| 直接の入力 | `data/raw/race.db` の `RT_O1_ODDS_TANFUKUWAKU` 表 |
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
| 確認時の行数・列数 | 77 行・323 列 |
| 確認時のファイルサイズ | 115,311 byte |
| 品質確認 | rawとの表名・列名・列順、変換時の行数、Parquetスキーマを照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `RT_O1_ODDS_TANFUKUWAKU` 表 → `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/RT_O1_ODDS_TANFUKUWAKU.parquet`。
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
| `TansyoFlag` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TansyoFlag` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FukusyoFlag` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FukusyoFlag` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `WakurenFlag` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `WakurenFlag` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `FukuChakuBaraiKey` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `FukuChakuBaraiKey` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo0Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo0Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo0Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo0Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo1Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo1Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo1Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo1Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo2Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo2Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo2Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo2Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo3Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo3Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo3Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo3Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo3Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo3Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo4Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo4Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo4Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo4Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo4Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo4Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo5Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo5Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo5Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo5Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo5Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo5Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo6Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo6Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo6Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo6Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo6Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo6Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo7Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo7Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo7Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo7Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo7Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo7Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo8Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo8Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo8Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo8Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo8Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo8Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo9Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo9Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo9Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo9Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo9Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo9Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo10Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo10Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo10Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo10Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo10Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo10Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo11Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo11Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo11Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo11Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo11Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo11Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo12Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo12Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo12Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo12Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo12Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo12Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo13Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo13Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo13Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo13Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo13Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo13Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo14Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo14Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo14Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo14Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo14Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo14Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo15Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo15Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo15Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo15Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo15Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo15Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo16Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo16Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo16Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo16Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo16Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo16Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo17Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo17Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo17Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo17Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo17Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo17Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo18Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo18Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo18Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo18Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo18Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo18Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo19Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo19Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo19Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo19Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo19Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo19Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo20Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo20Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo20Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo20Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo20Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo20Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo21Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo21Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo21Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo21Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo21Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo21Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo22Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo22Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo22Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo22Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo22Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo22Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo23Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo23Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo23Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo23Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo23Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo23Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo24Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo24Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo24Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo24Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo24Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo24Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo25Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo25Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo25Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo25Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo25Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo25Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo26Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo26Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo26Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo26Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo26Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo26Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo27Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo27Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo27Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo27Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsTansyoInfo27Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsTansyoInfo27Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo0Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo0Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo0OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo0OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo0OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo0OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo1Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo1Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo1OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo1OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo1OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo1OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo2Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo2Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo2OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo2OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo2OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo2OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo3Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo3Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo3OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo3OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo3OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo3OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo3Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo3Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo4Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo4Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo4OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo4OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo4OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo4OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo4Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo4Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo5Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo5Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo5OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo5OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo5OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo5OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo5Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo5Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo6Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo6Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo6OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo6OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo6OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo6OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo6Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo6Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo7Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo7Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo7OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo7OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo7OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo7OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo7Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo7Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo8Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo8Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo8OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo8OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo8OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo8OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo8Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo8Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo9Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo9Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo9OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo9OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo9OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo9OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo9Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo9Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo10Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo10Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo10OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo10OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo10OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo10OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo10Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo10Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo11Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo11Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo11OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo11OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo11OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo11OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo11Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo11Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo12Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo12Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo12OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo12OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo12OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo12OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo12Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo12Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo13Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo13Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo13OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo13OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo13OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo13OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo13Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo13Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo14Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo14Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo14OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo14OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo14OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo14OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo14Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo14Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo15Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo15Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo15OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo15OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo15OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo15OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo15Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo15Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo16Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo16Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo16OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo16OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo16OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo16OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo16Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo16Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo17Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo17Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo17OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo17OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo17OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo17OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo17Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo17Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo18Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo18Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo18OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo18OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo18OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo18OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo18Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo18Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo19Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo19Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo19OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo19OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo19OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo19OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo19Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo19Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo20Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo20Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo20OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo20OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo20OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo20OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo20Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo20Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo21Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo21Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo21OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo21OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo21OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo21OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo21Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo21Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo22Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo22Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo22OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo22OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo22OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo22OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo22Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo22Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo23Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo23Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo23OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo23OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo23OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo23OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo23Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo23Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo24Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo24Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo24OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo24OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo24OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo24OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo24Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo24Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo25Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo25Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo25OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo25OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo25OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo25OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo25Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo25Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo26Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo26Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo26OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo26OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo26OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo26OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo26Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo26Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo27Umaban` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo27Umaban` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo27OddsLow` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo27OddsLow` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo27OddsHigh` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo27OddsHigh` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsFukusyoInfo27Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsFukusyoInfo27Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo0Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo0Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo0Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo0Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo0Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo0Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo1Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo1Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo1Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo1Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo1Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo1Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo2Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo2Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo2Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo2Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo2Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo2Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo3Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo3Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo3Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo3Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo3Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo3Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo4Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo4Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo4Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo4Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo4Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo4Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo5Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo5Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo5Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo5Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo5Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo5Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo6Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo6Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo6Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo6Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo6Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo6Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo7Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo7Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo7Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo7Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo7Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo7Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo8Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo8Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo8Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo8Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo8Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo8Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo9Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo9Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo9Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo9Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo9Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo9Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo10Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo10Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo10Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo10Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo10Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo10Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo11Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo11Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo11Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo11Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo11Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo11Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo12Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo12Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo12Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo12Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo12Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo12Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo13Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo13Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo13Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo13Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo13Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo13Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo14Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo14Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo14Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo14Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo14Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo14Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo15Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo15Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo15Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo15Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo15Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo15Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo16Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo16Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo16Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo16Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo16Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo16Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo17Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo17Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo17Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo17Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo17Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo17Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo18Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo18Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo18Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo18Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo18Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo18Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo19Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo19Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo19Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo19Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo19Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo19Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo20Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo20Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo20Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo20Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo20Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo20Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo21Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo21Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo21Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo21Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo21Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo21Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo22Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo22Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo22Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo22Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo22Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo22Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo23Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo23Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo23Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo23Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo23Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo23Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo24Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo24Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo24Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo24Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo24Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo24Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo25Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo25Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo25Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo25Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo25Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo25Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo26Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo26Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo26Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo26Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo26Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo26Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo27Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo27Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo27Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo27Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo27Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo27Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo28Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo28Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo28Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo28Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo28Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo28Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo29Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo29Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo29Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo29Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo29Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo29Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo30Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo30Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo30Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo30Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo30Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo30Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo31Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo31Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo31Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo31Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo31Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo31Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo32Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo32Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo32Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo32Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo32Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo32Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo33Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo33Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo33Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo33Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo33Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo33Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo34Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo34Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo34Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo34Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo34Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo34Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo35Kumi` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo35Kumi` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo35Odds` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo35Odds` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `OddsWakurenInfo35Ninki` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `OddsWakurenInfo35Ninki` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TotalHyosuTansyo` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TotalHyosuTansyo` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TotalHyosuFukusyo` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TotalHyosuFukusyo` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `TotalHyosuWakuren` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `TotalHyosuWakuren` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・件数: 当該snapshot Parquetファイルのメタデータ。
- 表名・列名・列順・出力行数はraw-to-Parquet処理と再照合で一致。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
