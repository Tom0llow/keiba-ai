# NL_YS_SCHEDULE（processed snapshot）

[一覧に戻る](README.md)

## 表の定義

| 項目 | 定義 |
| --- | --- |
| 物理名 | `NL_YS_SCHEDULE` |
| 論理名 | To confirm |
| 層・形式 | `processed snapshot`、Parquet |
| 保存先 | `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_YS_SCHEDULE.parquet` |
| 直接の入力 | `data/raw/race.db` の `NL_YS_SCHEDULE` 表 |
| 取得元 | To confirm |
| 技術的な目的 | raw のユーザー表。入力表の各行・各列を同名のParquetへ保存する。 |
| 業務上の目的・行粒度 | To confirm。物理的には入力1行に出力1行が対応する。 |
| 利用先 | To confirm。学習・分析・予測での個別利用は未確認。 |
| 作成・更新方法 | `uv run python src/main.py preprocess rebuild`。一時領域で完成・検証後に `CURRENT` を切り替える。 |
| 更新頻度 | To confirm。 |
| データ管理責任者 | To confirm |
| processed側の主キー・外部キー | ファイルで強制される主キー・外部キーはない。 |
| raw側の宣言主キー | `idYear`, `idMonthDay`, `idJyoCD`, `idKaiji`, `idNichiji` |
| その他のprocessed制約 | 列はすべてNULL許容の`string`。最大長、既定値、CHECK制約の宣言はない。 |
| 機微区分・アクセス権 | To confirm |
| 確認時の行数・列数 | 7,526 行・45 列 |
| 確認時のファイルサイズ | 93,864 byte |
| 品質確認 | rawとの表名・列名・列順、変換時の行数、Parquetスキーマを照合済み。業務品質基準はTo confirm。 |

## 加工と対応関係

`data/raw/race.db` の `NL_YS_SCHEDULE` 表 → `data/processed/snapshots/81806ba398bb4fbe9a92eb1dbb75806f/NL_YS_SCHEDULE.parquet`。
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
| `YoubiCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `YoubiCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0TokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0TokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0Hondai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0Hondai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0Ryakusyo10` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0Ryakusyo10` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0Ryakusyo6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0Ryakusyo6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0Ryakusyo3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0Ryakusyo3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0Nkai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0Nkai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0GradeCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0GradeCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0SyubetuCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0SyubetuCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0KigoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0KigoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0JyuryoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0JyuryoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0Kyori` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0Kyori` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo0TrackCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo0TrackCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1TokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1TokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1Hondai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1Hondai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1Ryakusyo10` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1Ryakusyo10` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1Ryakusyo6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1Ryakusyo6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1Ryakusyo3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1Ryakusyo3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1Nkai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1Nkai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1GradeCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1GradeCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1SyubetuCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1SyubetuCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1KigoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1KigoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1JyuryoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1JyuryoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1Kyori` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1Kyori` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo1TrackCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo1TrackCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2TokuNum` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2TokuNum` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2Hondai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2Hondai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2Ryakusyo10` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2Ryakusyo10` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2Ryakusyo6` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2Ryakusyo6` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2Ryakusyo3` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2Ryakusyo3` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2Nkai` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2Nkai` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2GradeCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2GradeCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2SyubetuCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2SyubetuCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2KigoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2KigoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2JyuryoCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2JyuryoCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2Kyori` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2Kyori` (`TEXT`) | 文字列/NULLを保持 | To confirm |
| `JyusyoInfo2TrackCD` | To confirm | To confirm | `string`・長さ宣言なし | 可（スキーマ） | 宣言なし | なし | `JyusyoInfo2TrackCD` (`TEXT`) | 文字列/NULLを保持 | To confirm |

## 根拠と照合結果

- 物理列・入力制約: `data/raw/race.db` の `PRAGMA table_info`。
- 出力型・件数: 当該snapshot Parquetファイルのメタデータ。
- 表名・列名・列順・出力行数はraw-to-Parquet処理と再照合で一致。
- 入力の主キー/NOT NULL宣言は出力ファイルの強制制約にはならない。
- 値の全セル独立照合、業務上の意味・品質判定、更新条件は未実施・未確定。
