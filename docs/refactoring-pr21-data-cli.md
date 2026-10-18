# PR #21 データ基盤・CLI構成の移行記録

今回の基準HEADは`8053ea8fa3027109c5082612b0689e169f5030c4`。実装日は2026-10-18。
前段階の781cbcfから8053ea8までに行った責務分離は[既存記録](refactoring-pr21.md)に残し、
本書は8053ea8を基準とする追加移設・依存整理・検証を記録する。
[ADR-025](decisions/ADR-025-group-data-and-separate-cli-contracts.md)がADR-024の配置判断だけを部分置換する。

## 旧ファイルと新ファイルの全件対応

dataの4群とCLIの全旧ファイルを以下に示す。新規data/__init__.pyと境界回帰も追加した。
既存の23テストファイル、root config3ファイル、configuration4ファイルは維持する。

|8053ea8でのファイル|現行ファイル|処置|
|---|---|---|
|`src/cli/cli_data_preprocessor.py`|`src/cli/preprocessor.py`|機能と整合するファイル名へ変更。共通処理・他CLIへの依存を整理。|
|`src/cli/cli_jra_van_retriever.py`|`src/cli/jra_van_retriever.py`|機能と整合するファイル名へ変更。共通処理・他CLIへの依存を整理。|
|`src/cli/cli_make_datamart.py`|`src/cli/make_datamart.py`|機能と整合するファイル名へ変更。共通処理・他CLIへの依存を整理。|
|`src/cli/cli_make_features.py`|`src/cli/make_features.py`|機能と整合するファイル名へ変更。共通処理・他CLIへの依存を整理。|
|`src/cli/cli_models.py`|`src/cli/models.py`|機能と整合するファイル名へ変更。共通処理・他CLIへの依存を整理。|
|`src/data_loader/__init__.py`|`src/data/loader/__init__.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/data_loader/processed_data_loader.py`|`src/data/loader/processed_data_loader.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/data_loader/read_json.py`|`src/data/loader/read_json.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/data_loader/read_parquet.py`|`src/data/loader/read_parquet.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/data_loader/read_sqlite.py`|`src/data/loader/read_sqlite.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/data_preprocessor/__init__.py`|`src/data/preprocessor/__init__.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/data_preprocessor/sqlite_to_arrow.py`|`src/data/preprocessor/sqlite_to_arrow.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/data_saver/__init__.py`|`src/data/saver/__init__.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/data_saver/write_json.py`|`src/data/saver/write_json.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/data_saver/write_parquet.py`|`src/data/saver/write_parquet.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/storage/__init__.py`|`src/data/storage/__init__.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/storage/snapshot_builder.py`|`src/data/storage/snapshot_builder.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/storage/snapshot_publisher.py`|`src/data/storage/snapshot_publisher.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/storage/snapshot_store.py`|`src/data/storage/snapshot_store.py`|実装・公開シンボル・保存契約を維持して移設。参照importとpatch先を更新。|
|`src/cli/cli_common.py`|`src/cli/options.py` / `src/cli/json_io.py`|混在した共通責務を分割し、旧ファイルを廃止。|
|なし|`src/data/__init__.py`|共通データ基盤package宣言。上位の統括を再公開しない。|
|なし|`src/tests/test_cli_boundaries.py`|登録・独立import・共通JSON/option契約の回帰。|

旧4ディレクトリは残さず、旧CLI接頭辞ファイルとcli_commonも削除した。
新依存、shim、Facade、汎用基底クラス、将来用の空moduleは追加していない。

## cli_commonの処理別対応

|旧処理|新しい公開所有者|維持する契約|
|---|---|---|
|DataConfigOption|cli.options.DataConfigOption|Path型、--data-config、help、各利用先の既定値。|
|JVLinkConfigOption|cli.options.JVLinkConfigOption|Path型、--jvlink-config、help、各利用先の既定値。|
|_read_json_object|cli.json_io.read_json_object|物理読込の後、I/O/UTF-8/JSONエラーを既存メッセージのBadParameterへ変換。|
|_parse_inputs|cli.json_io.parse_json_inputs|読込成功後にparser実行。TypeError/ValueErrorの文言とcauseを保持してBadParameterへ変換。|
|input_error_payload|cli.json_io.input_error_payload|type=input、message=str(error)の既存JSON形。|
|_exit_input_error|cli.json_io.exit_input_error|contextとエラーJSONを保存して終了1。保存失敗はExitで隠さない。|

物理JSON読込・保存はdata.loader.read_json/data.saver.write_jsonへ委譲する。
JSON共通層にmodel/featureのschema検証やDatamartのstderrエラー契約を混在させない。

## CLIの共通・固有責務と依存

|ファイル|責務・依存|
|---|---|
|cli/options.py|共通option型だけ。設定読込や固有検証を行わない。|
|cli/json_io.py|共通CLI JSON境界と終了。物理I/Oはdataへ委譲。|
|cli/jra_van_retriever.py|取得flags/レース/モード固有検証、進捗表示、業務取得APIとSnapshotBuilder公開APIの連携。|
|cli/preprocessor.py|preprocess rebuildを受付しSnapshotBuilder.from_toml().rebuild()と表示。|
|cli/make_features.py|explanatory-variables固有catalog/registry/入力解析/監査/生成とJSON結果。|
|cli/make_datamart.py|Datamartの引数・定義名・構築API・stderr/終了/表示。JSONエラー出力へ統合しない。|
|cli/models.py|audit/features/walk-forward、model schema/監査/構築/評価・JSON結果。model専用read_feature_inputs_or_exitは残す。|
|main.py|Typerの組立・全コマンド登録・起動。register_feature_commandsもここで同じ3登録を所有する。|

取得CLI→前処理CLIのprivate _preprocesser依存を削除し、SnapshotBuilder.from_tomlへ直接置換した。
薄い前処理factoryは廃止した。factory生成のタイミング、ロック内のpublisher callback、取得・復旧・公開順序は維持する。
特徴量CLI→model CLIの登録依存も削除した。機能CLI間のimportはなく、共有はoptions/json_ioだけである。
他CLIからprivate関数をimportせず、CLIより下位のdata/機能層はTyper/main/cliへ依存しない。

mainの登録順はpreprocess/model/datamart、model配下はwalk-forward/audit/features/explanatory-variablesを保持する。
公開main.register_feature_commandsは同じ3関数を同じ順に登録し、既存の独立Typer利用も維持する。

## importとAPI・保存契約

srcの通常import、subprocess内のコード、monkeypatch/mockの文字列、現行文書を新所有先へ更新した。
過去ADRの理由本文は変更せず、024の状態欄だけに025への部分置換を記録した。
DataLoader、SQLiteReader、SnapshotBuilder、SnapshotStoreとDataPreprocesser aliasのAPIは同一である。
旧importの互換moduleは残さず、内部importと公開シンボル/CLIの互換性を区別する。

単一SQLite読取取引、batch sizeとschema、NULL/先頭ゼロ/rowid順、Parquet metadata、JSON形式、
完成snapshotとrace別version、CURRENTの原子的切替、失敗時の旧版保持は前段階の契約を継承する。
モデル/特徴量/取得/Datamartの業務計算は変更せず、config値やモデル成果物形式も変更していない。

## 今回の変更対象（移設後・省略なし）

旧ファイル削除は上表に全件示した。以下は今回追加・変更・移設した現行ファイルの全件である。
リポジトリ全src/configの現行完全ツリーは[既存記録の最終構成](refactoring-pr21.md)にも更新した。

```text
├── docs/
│   ├── decisions/
│   │   ├── ADR-024-separate-functional-responsibilities.md
│   │   └── ADR-025-group-data-and-separate-cli-contracts.md
│   ├── rules/
│   │   ├── architecture.md
│   │   └── coding-style.md
│   ├── implementation-design.md
│   ├── refactoring-pr21-data-cli.md
│   └── refactoring-pr21.md
├── src/
│   ├── cli/
│   │   ├── jra_van_retriever.py
│   │   ├── json_io.py
│   │   ├── make_datamart.py
│   │   ├── make_features.py
│   │   ├── models.py
│   │   ├── options.py
│   │   └── preprocessor.py
│   ├── data/
│   │   ├── loader/
│   │   │   ├── __init__.py
│   │   │   ├── processed_data_loader.py
│   │   │   ├── read_json.py
│   │   │   ├── read_parquet.py
│   │   │   └── read_sqlite.py
│   │   ├── preprocessor/
│   │   │   ├── __init__.py
│   │   │   └── sqlite_to_arrow.py
│   │   ├── saver/
│   │   │   ├── __init__.py
│   │   │   ├── write_json.py
│   │   │   └── write_parquet.py
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   ├── snapshot_builder.py
│   │   │   ├── snapshot_publisher.py
│   │   │   └── snapshot_store.py
│   │   └── __init__.py
│   ├── make_datamart/
│   │   └── tables/
│   │       └── parquet.py
│   ├── make_features/
│   │   └── tables/
│   │       └── parquet.py
│   ├── tests/
│   │   ├── test_cli_boundaries.py
│   │   ├── test_data_pipeline.py
│   │   ├── test_datamart.py
│   │   ├── test_feature_catalog.py
│   │   ├── test_main.py
│   │   ├── test_make_features.py
│   │   ├── test_read_json.py
│   │   └── test_serialization.py
│   └── main.py
├── ARCHITECTURE.md
└── README.md
```

## 検証

基準8053ea8のuv sync --locked/Ruff/mypy160/pytest5892/ガード成功をrootが確認し、今回もuv sync --lockedが成功した。
変更後の焦点検証は既存CLI/data152件、新境界16件が成功し、mypy163ファイルも成功した。
最終実行では`uv run ruff format --check .`（163ファイル）、`uv run ruff check .`、
`uv run mypy src`（163ファイル）、`uv run pytest -q`（5908件、27.80秒）が全て成功した。
基準5892件を維持して16件の境界回帰を追加した。

rootの独立照合では8053ea8基準のCLI外部プロセス29ケースと取得dispatch1536ケースが全て一致した。
helpも除外せず、stdout/stderr/終了・呼出先/引数/例外型に差分はない。
CLI/tests/mainを除く既存129runtime modulesは移設先とAST照合し、import/docstring以外の変更は0。
config3TOMLも改行差を除いて同一である。
最終139runtime modulesに循環がなく、全import成功・LightGBM未読込、指定CLI8ファイル、
機能CLI間依存なし・private共有importなし、dataからTyper/CLIへの依存なしをrootが確認した。

今回のガード回帰はrootがCodex0.151.0/PowerShell7で昇格実行しexit0。
native process、PR lifecycle19fixtures、base update17fixturesと実conflict、baseline/task-stateを含む。
実行ポリシー検証を省略せず全成功した。

## 文書と残る制約

README、ARCHITECTURE、implementation-design、architecture/coding-style規約、既存全件記録を更新した。
ADR-025を追加し、ADR-024の状態欄だけを部分置換した。無関係な既存改行は保持する。
Windows sandbox ACLがpytest一時ファイルや全体走査を妨げるため、該当検証は同じコマンドを
理由付きrequire_escalatedで通常ユーザー権限実行した。ガードやテスト条件の省略による回避は行っていない。
実JVLink取得は実行していない。既存の決定的な取得境界テストと独立CLI照合で互換性を確認する。
旧内部importは新所有先へ移行が必要であり、保存データや設定値の移行は不要である。
