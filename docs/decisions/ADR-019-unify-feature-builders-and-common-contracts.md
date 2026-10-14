# ADR-019: 説明変数生成と共通契約を統一する

- Status: Superseded by ADR-020
- Date: 2026-10-12
- Decision Owners: Repository maintainers
- Supersedes: ADR-017, ADR-018
- Superseded by: ADR-020（配置・登録・CLI境界。生成・監査・保存契約は継承）

## Context

既存の説明変数は個別モジュールで入力・正規化・中間テーブル生成を所有する一方、
F01〜F21は仕様だけを個別ファイルへ置き、型・監査・生成を一つのファイルへ集めていた。
ユーザーは追加時期による管理の分離を廃止し、各説明変数で入力・生成・正規化を
管理すること、共通の中間行を既存の`FeatureTableRow`へ統一すること、共通処理を
`features/`の適切なディレクトリへ配置することを指定した。

CLIは`src/features/make_features.py`へ、JSON読込は
`src/data/loader/read_json.py`へ置き、`src/run`を設けない指定も維持する。
ADR-011/012の時点・欠損・モデル採用条件を変えず、配置と生成契約を整理する。

## Decision

1. 各説明変数のファイルは専用の`Input`、`FeatureBuilder`の派生クラス、公開の
   `build_*`関数、内部の`_normalize_*`関数を所有する。基底クラスは行生成と
   テーブル構築の共通手順だけを管理し、レース相対値やグラフを扱える一括入力の
   行生成を派生クラスへ委譲する。既存3説明変数も同じ基底クラスを利用する。
2. 共通処理は`src/features/common/`に置く。`rows.py`が`FeatureTableRow`、
   `base.py`が基底クラス、`types.py`が明示入力と監査結果、`availability.py`が
   時刻解析と時点監査、`leakage.py`が結果・未来データの検証、`validation.py`が
   値・欠損検証、`audit.py`がレース・行整合性、`normalization.py`が監査済み入力の
   共通正規化、`registry.py`がF01〜F21の登録、`feature_table.py`がArrow/Parquetの
   スキーマと保存・再読込を担当する。物理読込に属さない説明変数の監査を
   `src/data`へ移さない。
3. 共通の中間行は`FeatureTableRow`だけとし、`FeatureRecord`は導入しない。
   `FeatureBatchInput`と`FeatureGroupInput`は上流からの値と証跡を受け取る入力型であり、
   中間行ではない。`explanatory_variables.py`は個別生成APIをまとめる薄い境界とし、
   生成結果には説明変数ID別の`FeatureTableRow`を返す。
4. `Candidate`のAPI表現は廃止し、F01〜F21は`feature_id`で管理する。CLIは
   `model explanatory-variables`とし、出力ID項目は`feature_ids`とする。
   旧`candidate-features`コマンドと旧候補API/importは置き換える。
5. 既存3説明変数は登録済みの列名・型・保存metadataを維持する。F01〜F21は
   呼出し元が列名とArrow scalar型（int64、float64、string、bool）を明示する。
   値から型を推測せず、順序付きの型metadataを保存して再読込時に検証する。
   欠損はNULLのまま保持し、結果由来列、未来時点、型不一致を拒否する。
6. `src/make_datamart/builder.py`は生成を行わず、中間テーブルの型契約を使って
   新旧の説明変数を同じleft joinで結合する。キー・順序・freeze一致・列衝突・
   各説明変数のavailable時刻を検証する。既存3だけのdatamart保存契約は維持し、
   明示型の説明変数を含む場合だけ追加の型metadataを保存する。
7. 数値`FeatureSchema`への投影と`RankingDataset`構築は
   `src/models/dataset_builder.py`へ移す。中間テーブルの共通スキーマとモデル固有の
   入力構築を分離し、ADR-011のモデルallow-listとWalk-forward挙動を維持する。
8. `make_features.py`はCLI登録・入力変換・実行編成・JSON出力を担当し、
   `read_json.py`はUTF-8 objectの読込だけを担当する。下位の個別生成・監査・loaderは
   CLI入口へ依存しない。`src/run`、`cli.py`、`json_io.py`は設けない。

## Rationale

個別モジュールが入力と規則を所有すれば、説明変数を追加した時期で生成経路を分けずに
変更・検証できる。共通監査とテーブル保存は計算式に依存しないため、個別生成から
分離して再利用する。モデル固有の数値入力構築をモデル側へ移すことで、
`feature_table.py`は共通の中間成果物に責務を限定できる。

## Consequences

- 追加時期ではなく、説明変数固有の入力と規則を所有する個別ファイルを変更単位にする。
- 中間行、時点監査、保存契約、モデル入力、実行境界を別々に検証できる。
- 呼出し元は旧候補API/import、旧CLI名、`candidate_group_ids`、`group_id`を移行する
  必要がある。リポジトリ内の呼出しとテスト・文書を同時に更新する。
- 既存3の中間Parquetとdatamartは移行不要であり、新しい型metadataも保存・再読込で
  検証する。元データの加工、補完、符号化、行削除は追加しない。
- F01〜F21は上流で計算済みの明示値を監査・生成する。業務式、履歴窓、閾値、
  JRA-VANコード解釈、発走5分前の取得・受信証明は未確定のまま残す。
  型を指定できることをモデル採用の承認とは扱わず、数値allow-listへ自動投入しない。

## Alternatives Considered

- `FeatureRecord`を別の中間表現として設ける案は、既存の中間行と重複するため採用しない。
- CLIをdatamartへ移す案は生成と結合を混在させるため採用しない。
- 全体生成を基底クラスの単一行処理へ固定する案は、レース相対・グラフ生成を妨げる。
- 列名からArrow型を推測する案は、未承認の永続形式を暗黙に確定するため採用しない。

## Validation

全21説明変数の個別行生成、共通中間テーブルのParquet round-trip、明示型、
欠損保持、未来・結果由来列の拒否、新旧混在datamartの行順とNULL保持を検証する。
既存のモデル・Walk-forward・CLI・監査の回帰を維持し、Ruff、mypy、pytestと
guard回帰を実行する。
