# ADR-027: Hydraで実験設定、MLflowでモデル版と結果を管理する

- Status: Accepted
- Date: 2026-10-21
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ユーザー要件は、実際にランキングモデルを学習・予測し、最新入力でも予測を試すこと、
実験のパラメータをHydra、モデルの版と実験結果をMLflowで管理することである。
既存の明示FeatureInput JSON、時点監査、LambdaRank、数値特徴量allow-list、
native model/JSON metadata/ready marker契約は維持する。rawデータからの業務計算、
新たな特徴量、取得時刻の推定は、この実験管理要件から導入しない。

## Decision

1. `configuration/experiments.py`がHydra Compose APIで
   `configs/experiments/{train,predict}.yaml`とmodel/mlflowグループを合成する。
   `--config-dir`、`--config-name`、反復可能な`--override key=value`を提供する。
   cwdを変更せず、相対パスは呼出時のcwdから解決する。既存3 TOMLは変えない。
   HydraによるPythonオブジェクト生成は行わない。import/helpでは入力・設定を読まない。
2. `model train`は既存JSON契約の全行を監査し、同じレース内の共通freeze_atと、
   レース間の厳密な昇順を検証する。末尾`split.test_races`をholdoutへ割り当て、
   それより前の全レースだけを学習に渡す。NDCG@3、Top1精度、Top3一致割合、
   holdoutのscore/rankを保存する。モデル選択やnested検証は導入しない。
3. `models/experiments/`が実験の組立、入力要約、実行記録を所有する。
   既定のMLflow trackingとregistryは`output/mlflow/mlflow.db`のSQLite、
   artifactは`output/mlflow/artifacts`とする。出力先はcwdの`output/`内に限定し、
   毎回新しいrun IDディレクトリを使う。既存入力や出力を置き換えない。
   クライアントへURIを明示し、global tracking URIや外部サーバーを利用しない。
   ローカル実験ではMLflowの外部telemetryを無効にする。
4. 解決済み設定、実効LightGBMパラメータ（既定値・固定objective/gainを含む）、
   入力SHA-256、schema、欠損件数を含む監査、期間・レースID・件数、指標、予測、
   native成果物一式をrunへ記録する。ソースファイル集合のSHA-256、各ファイルhash、
   uv.lock hash、依存versionをコードと環境の識別情報とし、Gitコマンドを呼ばない。
   run作成後の失敗はFAILEDとする。各学習runは登録名の新model versionを作る。
5. registryのsourceはMLflowへ記録したnativeフォルダーであり、MLmodel/pyfuncや
   pickle形式へ変換しない。training.jsonに学習末時点とレースIDを記録し、nativeと
   training contextのhashをmodel versionのtagに固定する。
6. `model predict`は登録名と厳密な正整数versionを要求し、alias/latestを認めない。
   FINISHEDなtrain runとREADY版、設定したローカルartifact領域内のsource、hash、
   `RankingModel.load`の既存成果物検証、入力schema一致を確認する。
   予測対象は学習末時点より後であり、学習レースIDと重複しないことを要求する。
   出力する予測値はscore/rankだけである。
7. `data.selection=latest_date`は入力JSONのfreeze_atを`data.date_timezone`へ変換し、
   最大日付の全レースを選ぶ。OSの更新時刻や暗黙の取得処理は使わない。
   入力内の最新日、ローカル取得済みデータの最新日、提供元の最新公開日、
   未来のライブ予測を区別する。全入力の監査を通した後に対象日を選ぶ。
8. Hydra/MLflowはユーザー指定の依存であり`pyproject.toml`と`uv.lock`へ追加する。
   SQLite registryと`mlflow ui`を同じ固定環境で利用できるよう、skinny単独ではなく
   完全版MLflowを使う。既存の学習既定値、native保存形式、既存CLIは維持する。

## Rationale

Compose APIは既存Typer CLIを保ったまま実験設定のグループと上書きを扱える。
低水準MLflow clientなら、実行状態・指標・artifact・registry版を明示して管理できる。
実験層を既存の純粋なdataset/学習/推論から分離し、入力とnative成果物の監査を再利用する。

## Consequences

学習時の入力、パラメータ、環境と、予測に使った版を追跡できる。
SQLiteとartifact一式の保全が必要であり、同時実行やサーバー運用・保持期間は今回扱わない。
完全版MLflowはUIとSQLite依存を含むため依存数と初回起動時間が増える。
hashは事故による混在を検出するもので、悪意あるregistry管理者に対する署名ではない。
raw Parquetから監査済み数値入力を作る加工規則が未確定なら、実データ学習の前提は満たされない。
統合テストの合成入力を実データの学習実績として報告しない。

## Alternatives Considered

- TOMLだけの管理は、Hydraで設定する明示要件を満たさない。
- MLflow pyfunc/pickleへの変換は不要であり、既存native成果物契約を維持する。
- registryのlatest版を暗黙に選ぶと予測の再現性を失うため、versionを固定する。
- rawから能力値や利用可能時刻を仮定して作ると未承認の業務規則になるため採用しない。

## Validation / Follow-up

実LightGBM、Hydra YAML、MLflow SQLite/registryを使い、学習から新version登録、
別processでのnative再読込、最大freeze日予測までを検証する。
設定上書き、時系列違反、schema/欠損方針改変、未来available_at、学習期間への予測、
失敗runの状態を検査する。既存CLIと学習APIの検証も維持する。
