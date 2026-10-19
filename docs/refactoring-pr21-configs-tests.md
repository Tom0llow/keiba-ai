# PR #21 設定・テスト配置の移行記録

基準HEADは`17b92e690e65fcdc62b05dd6640d3987ce2844c2`。実装日は2026-10-19。
前段階の[責務分離](refactoring-pr21.md)と[データ基盤・CLI移行](refactoring-pr21-data-cli.md)の
計算・保存契約を継承し、[ADR-026](decisions/ADR-026-rename-configs-and-classify-tests.md)で配置だけを更新する。
過去の実行記録やADRの理由本文は書き換えない。

## 設定と参照の対応

|旧ファイル|新ファイル|維持するもの|
|---|---|---|
|`config/data.toml`|`configs/data.toml`|全byte、raw/processed/runtimeの相対パス値。|
|`config/features.toml`|`configs/features.toml`|全byte、21特徴量のID・名前・順序。|
|`config/jvlink.toml`|`configs/jvlink.toml`|全byte、取得profile・DataSpec・期間・RaceKey。|

同じ深さのdirectory renameなので設定ファイルの親からの相対パス解決先は同じである。
機能内の`src/jra_van_retriever/config/`と`src/configuration/`は維持する。
`src/cli/jra_van_retriever.py`と`preprocessor.py`のdata/jvlink既定値、
`make_features.py`と`make_datamart.py`のfeatures既定値をconfigsへ更新する。
明示設定パスの扱い・CLI名・計算・永続形式は維持する。

## 全テストファイルの対応と分類根拠

純粋な計算・検証と外部境界をmockした分離テストはunit、実ファイル・SQLite・subprocess・
環境・機能間の接続を確認するテストはintegrationへ置く。tmp_pathの有無だけでは分類しない。
実カタログをmodule globalで読む説明変数と個別builderは結合として保持する。
JVLink adapterも実ファイルのguardを通すため、subprocessのmockだけを理由にunitへ置かない。

src/tests直下の旧24ファイルを、既存smoke 1件と分類した32モジュールへ整理し、混合9ファイルを分割した。同名ファイルは各分類内で
元のテスト関数名を保持する。以下の関数数はparametrize展開前である。

|旧ファイル|現行ファイルと関数数|分類理由|
|---|---|---|
|`src/tests/test_cli_boundaries.py`|`src/tests/unit/test_cli_boundaries.py`（3関数）<br>`src/tests/integration/test_cli_boundaries.py`（6関数）|unitは登録・明示optionのmock委譲、integrationは独立process importとJSONの実読書き。|
|`src/tests/test_configuration.py`|`src/tests/unit/test_configuration.py`（2関数）<br>`src/tests/integration/test_configuration.py`（3関数）|unitはパス値・型検証、integrationはTOMLの物理読込と必須設定検証。|
|`src/tests/test_data_pipeline.py`|`src/tests/integration/test_data_pipeline.py`（10関数）|実SQLiteとParquet、CURRENT公開、単一取引・失敗復旧。|
|`src/tests/test_data_retriever.py`|`src/tests/integration/test_data_retriever.py`（1関数）|実設定ファイルから取得Facadeを組み立てる。|
|`src/tests/test_datamart.py`|`src/tests/unit/test_datamart.py`（5関数）<br>`src/tests/integration/test_datamart.py`（10関数）|unitは純粋結合の拒否条件・mockしたhelp、integrationはCLIとParquet保存・再読込。|
|`src/tests/test_explanatory_variables.py`|`src/tests/integration/test_explanatory_variables.py`（23関数）|実カタログから21builderを登録し、生成・監査・型を接続する。|
|`src/tests/test_feature_catalog.py`|`src/tests/unit/test_feature_catalog.py`（1関数）<br>`src/tests/integration/test_feature_catalog.py`（12関数）|unitはカタログ読込をmockしたhelp、integrationはTOML検証・登録・生成・保存・CLI・独立process。|
|`src/tests/test_feature_tables.py`|`src/tests/unit/test_feature_tables.py`（9関数）<br>`src/tests/integration/test_feature_tables.py`（1関数）|unitはメモリ上のArrow構築・値・schema検証、integrationはParquet round-trip。|
|`src/tests/test_features.py`|`src/tests/unit/test_features.py`（5関数）|明示入力に対する純粋な行構築・欠損・時刻監査。|
|`src/tests/test_historical.py`|`src/tests/unit/test_historical.py`（1関数）<br>`src/tests/integration/test_historical.py`（14関数）|unitはRaceKeyの値検証、integrationはSQLite観測と取得・archive接続。|
|`src/tests/test_individual_feature_builders.py`|`src/tests/integration/test_individual_feature_builders.py`（19関数）|実カタログのbuilderと共通table・Datamart・Parquetを接続する。|
|`src/tests/test_jvlinktosqlite.py`|`src/tests/integration/test_jvlinktosqlite.py`（15関数）|subprocessはmockするが、実ファイル・親directoryの存在guardと実行adapterを通す。|
|`src/tests/test_latest.py`|`src/tests/integration/test_latest.py`（1関数）|実runtime XMLの生成・再利用・seed保持。|
|`src/tests/test_main.py`|`src/tests/unit/test_main.py`（17関数）<br>`src/tests/integration/test_main.py`（16関数）|unitはmockした取得・前処理dispatch、validation、help、integrationはJSONファイルからCLI・生成・監査・評価・保存。|
|`src/tests/test_make_features.py`|`src/tests/integration/test_make_features.py`（1関数）|汎用JSON writerの実保存と非破壊性。|
|`src/tests/test_models.py`|`src/tests/unit/test_models.py`（14関数）<br>`src/tests/integration/test_models.py`（8関数）|unitはdataset・順位・指標・mock backend学習、integrationはnative成果物の公開・復旧と実LightGBM。|
|`src/tests/test_odds_archive.py`|`src/tests/integration/test_odds_archive.py`（3関数）|実SQLite archiveのschema・累積・冪等性。|
|`src/tests/test_project_environment.py`|`src/tests/test_project_environment.py`（1関数）|実環境の確認。既存文書・指示との互換性を保つため直下のsmoke位置を維持。|
|`src/tests/test_read_json.py`|`src/tests/integration/test_read_json.py`（8関数）|実ファイルのUTF-8/JSON読込とI/O失敗。|
|`src/tests/test_realtime.py`|`src/tests/integration/test_realtime.py`（1関数）|実SQLiteの履歴archiveと現在snapshot取得の接続。|
|`src/tests/test_serialization.py`|`src/tests/unit/test_serialization.py`（7関数）<br>`src/tests/integration/test_serialization.py`（1関数）|unitは純粋なfeature/model契約変換、integrationは独立processでTyper非依存を確認する。|
|`src/tests/test_setting.py`|`src/tests/integration/test_setting.py`（9関数）|実TOML・seed XMLからprofileと実行XMLを組み立てる。|
|`src/tests/test_walk_forward.py`|`src/tests/unit/test_walk_forward.py`（4関数）|メモリ上の時系列分割・race完全性とfake modelによる評価。|
|`src/tests/test_weekly_progress.py`|`src/tests/integration/test_weekly_progress.py`（25関数）|実SQLite台帳・OS lock・週次取得・復旧・公開の接続。|

分割先には必要な既存helper・定数・importを保持する。mainの既存`cli_color_mode` fixtureは
unit側に置き、default-color/forced-colorのparametrizeとusefixturesを保持する。
新しいfixture抽象化やカタログ定義の複製は設けない。
分類したテストからルートまではparents[3]となるため、設定参照と独立processのsrc解決を更新する。
独立processテストのcwd/src_dirだけは、新しいテスト位置から明示的にルート/srcへ解決する。

## 収集と型検査

`pyproject.toml`のtestpathsは従来のsrc/tests、mypyのfilesは従来のsrcを維持する。
pythonpathもsrcのままで、importlibモードを追加して同名のunit/integrationモジュールを独立して収集する。
`uv run pytest`とCIの既存`uv run pytest src/tests`はいずれも全件を収集する。
分類単位では`uv run pytest src/tests/unit`または`uv run pytest src/tests/integration`を実行できる。
既存smokeは`uv run pytest src/tests/test_project_environment.py`で直接実行できる。

`uv run mypy src`が全製品コードと全33テストモジュールを検査する。
CI、pre-commit、AGENTS.md、スキルの検証コマンドを変更する必要はない。
ルートtestsや旧配置へのリンク、型検査除外、弱いassertion、skip追加は設けない。
AGENTS.mdの汎用ツリーに残る旧設定名configは、ユーザーの明示的なconfigs改名とADR-026により置換する。

## 保存した検証条件

基準と最終配置は全256テスト関数・5908ケースが一致する。収集nodeidのファイル部分を除いた
関数名・parameter ID・重複数は同じであり、欠落・追加はない。
unit129件、integration5778件、既存環境smoke 1件の全てを既存のpytest src/testsで収集できる。
環境smokeは実環境を確認する性質を持つが、元の直接パスとの互換性を維持する例外として直下に置く。
テスト本体とdecoratorは参照パスの変更だけに限定し、3 TOMLは基準checkoutとSHA-256が一致する。

|コマンド・検査|結果|
|---|---|
|`uv run pytest src/tests --collect-only -q`|5908件収集。基準のcase ID・重複数と一致。|
|設定・CLI・環境契約の焦点検証|80 passed、2.12秒。sandboxのtmp ACL失敗後、同一条件で再実行。|
|`uv run ruff format --check src/tests`|33ファイル成功。|
|`uv run ruff check src/tests`|成功。|
|`uv run mypy src`|172ファイル成功。全テストを含む。|

コード・テストを最終配置で確定後、coordinatorが次の全体検証を実行し、全て成功した。

|コマンド・検査|結果|
|---|---|
|`uv sync --locked`|成功。既存lockと依存関係を維持。|
|`uv run ruff format --check .`|172ファイル成功。|
|`uv run ruff check .`|成功。|
|`uv run mypy src`|172ファイル成功。全製品コードと全テストを含む。|
|`uv run pytest -q`|5908 passed、17.61秒。|
|ガード回帰（native Codex 0.151.0 / PowerShell 7）|全成功。実行ポリシー評価を省略していない。|
|収集一覧・TOML照合|全256関数・5908ケースのIDと重複数を維持。設定内容も一致。|

通常sandboxでACLが検証を妨げた場合は、同じ条件をrequire_escalatedで再実行した。
CIと既存スキルの検証コマンドを変えず全対象を検査できる。保護対象の変更はない。
独立レビュー・commit以降の実施結果はcoordinatorが報告する。
設定値・計算・永続形式とガードの信頼境界は変更しない。
