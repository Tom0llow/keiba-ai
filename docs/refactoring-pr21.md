# PR #21 責務分離リファクタリング記録

前段階の基準HEAD: `781cbcfdda0d1ec7377e70440e887562e89629dd`。その実装は`8053ea8fa3027109c5082612b0689e169f5030c4`までに完了した。
今回の構成変更の基準は8053ea8。以下の旧123ファイルの履歴は保持し、移設先・責務一覧・最終ツリーはADR-026までの現行配置へ更新した。今回の差分と検証は[データ基盤・CLI移行記録](refactoring-pr21-data-cli.md)を参照する。
[ADR-024](decisions/ADR-024-separate-functional-responsibilities.md)に従い、既存の計算、設定値、保存形式、ロック・台帳・復旧とCLIの契約を維持して所有者を分離した。

設定とテストの追加移設・分類は[設定・テスト移行記録](refactoring-pr21-configs-tests.md)に記録する。

## 旧ファイルと新ファイルの全件対応

変更前の`src/`全123 Pythonファイル（本体101、テスト22）を以下に列挙する。テストファイルは全て維持した。

|旧ファイル|新しい所有先（製品コードはsrc/配下、テストはルートからのパス）|処置・理由|
|---|---|---|
|`src/domain/__init__.py`|`domain/__init__.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/domain/race_key.py`|`domain/race_key.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/features/__init__.py`|`make_features/__init__.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/basic_conditions_and_weight.py`|`make_features/basic_conditions_and_weight.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/catalog/__init__.py`|`make_features/catalog/__init__.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/catalog/loader.py`|`make_features/catalog/loader.py`<br>`configuration/loader.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/features/catalog/registry.py`|`make_features/catalog/registry.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/condition_adjusted_ability.py`|`make_features/condition_adjusted_ability.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/condition_suitability.py`|`make_features/condition_suitability.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/contracts/__init__.py`|`make_features/contracts/__init__.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/contracts/rows.py`|`make_features/contracts/rows.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/contracts/types.py`|`make_features/contracts/types.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/expected_race_development.py`|`make_features/expected_race_development.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/explanatory_variables.py`|`make_features/explanatory_variables.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/generation/__init__.py`|`make_features/generation/__init__.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/generation/base.py`|`make_features/generation/base.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/generation/normalization.py`|`make_features/generation/normalization.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/hill_and_wood_workouts.py`|`make_features/hill_and_wood_workouts.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/history_volume_and_missingness.py`|`make_features/history_volume_and_missingness.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/jockey_combination.py`|`make_features/jockey_combination.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/jockey_performance.py`|`make_features/jockey_performance.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/market_characteristics.py`|`make_features/market_characteristics.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/odds_ratio.py`|`make_features/odds_ratio.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/opponent_pagerank.py`|`make_features/opponent_pagerank.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/past_body_weight.py`|`make_features/past_body_weight.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/past_lap_and_running_style.py`|`make_features/past_lap_and_running_style.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/past_racing_ability.py`|`make_features/past_racing_ability.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/pedigree.py`|`make_features/pedigree.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/pedigree_suitability.py`|`make_features/pedigree_suitability.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/previous_race_result.py`|`make_features/previous_race_result.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/recent_performance.py`|`make_features/recent_performance.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/recent_stability.py`|`make_features/recent_stability.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/rest_and_condition_change.py`|`make_features/rest_and_condition_change.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/running_style_and_position.py`|`make_features/running_style_and_position.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/same_gate_and_trainer_relative.py`|`make_features/same_gate_and_trainer_relative.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/serialization/__init__.py`|`make_features/serialization/__init__.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/serialization/inputs.py`|`make_features/serialization/inputs.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/serialization/outputs.py`|`make_features/serialization/outputs.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/tables/__init__.py`|`make_features/tables/__init__.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/tables/build.py`|`make_features/tables/build.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/tables/parquet.py`|`make_features/tables/parquet.py`<br>`data/loader/read_parquet.py`<br>`data/saver/write_parquet.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/features/tables/schema.py`|`make_features/tables/schema.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/trainer_performance.py`|`make_features/trainer_performance.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/validation/__init__.py`|`make_features/validation/__init__.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/validation/audit.py`|`make_features/validation/audit.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/validation/availability.py`|`make_features/validation/availability.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/validation/groups.py`|`make_features/validation/groups.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/validation/leakage.py`|`make_features/validation/leakage.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/validation/table.py`|`make_features/validation/table.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/validation/values.py`|`make_features/validation/values.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/features/within_race_relative.py`|`make_features/within_race_relative.py`|make_featuresへ移設。個別の計算・監査・生成ロジックは変更しない。|
|`src/main.py`|`main.py`<br>`cli/options.py`<br>`cli/json_io.py`<br>`cli/jra_van_retriever.py`<br>`cli/preprocessor.py`<br>`cli/make_features.py`<br>`cli/models.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/make_datamart/__init__.py`|`make_datamart/__init__.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/make_datamart/builder.py`|`make_datamart/builder.py`<br>`make_datamart/tables/parquet.py`<br>`make_datamart/__init__.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/make_datamart/tables/__init__.py`|`make_datamart/tables/__init__.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/make_datamart/tables/parquet.py`|`make_datamart/tables/parquet.py`<br>`data/loader/read_parquet.py`<br>`data/saver/write_parquet.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/make_datamart/tables/schema.py`|`make_datamart/tables/schema.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/make_datamart/validation/__init__.py`|`make_datamart/validation/__init__.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/make_datamart/validation/table.py`|`make_datamart/validation/table.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/models/__init__.py`|`models/__init__.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/models/artifacts.py`|`models/artifacts/native_model.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/models/dataset_builder.py`|`models/dataset/rows.py`<br>`models/dataset/availability.py`<br>`models/dataset/builder.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/models/evaluate_model.py`|`models/evaluation/metrics.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/models/lightgbm_backend.py`|`models/backends/lightgbm.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/models/predict_model.py`|`models/predict_model.py`|既存の2名再公開だけを維持。既存互換入口である根拠は後述。|
|`src/models/ranker.py`|`models/ranking/ranker.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/models/ranking_dataset.py`|`models/dataset/rows.py`<br>`models/dataset/schema.py`<br>`models/dataset/validation.py`<br>`models/dataset/dataset.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/models/ranking_rules.py`|`models/ranking/rules.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/models/serialization/__init__.py`|`models/serialization/__init__.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/models/serialization/inputs.py`|`models/serialization/inputs.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/models/serialization/outputs.py`|`models/serialization/outputs.py`|現配置を維持。移設に伴うimportまたは所有先の再公開を更新。|
|`src/models/train_model.py`|`models/training/train.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/models/walk_forward.py`|`models/evaluation/walk_forward.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/preprocesser/__init__.py`|該当する新packageの`__init__.py`へ統合|旧package宣言を削除。旧settings/utilsを含む旧配置は廃止し、実装を残さない。|
|`src/preprocesser/data_preprocesser.py`|`data/storage/snapshot_builder.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/preprocesser/read_sqlite.py`|`data/loader/read_sqlite.py`<br>`data/preprocessor/sqlite_to_arrow.py`<br>`data/saver/write_parquet.py`<br>`data/storage/snapshot_builder.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/preprocesser/snapshot.py`|`data/storage/snapshot_builder.py`<br>`data/storage/snapshot_store.py`<br>`data/storage/snapshot_publisher.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/retriever/__init__.py`|該当する新packageの`__init__.py`へ統合|旧package宣言を削除。旧settings/utilsを含む旧配置は廃止し、実装を残さない。|
|`src/retriever/acquisition_lock.py`|`jra_van_retriever/acquisition/acquisition_lock.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/data_retriever.py`|`jra_van_retriever/retriever.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/historical.py`|`jra_van_retriever/workflows/historical_basic.py`<br>`jra_van_retriever/workflows/historical_odds_legacy.py`<br>`jra_van_retriever/retriever.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/retriever/jvlinktosqlite.py`|`jra_van_retriever/acquisition/jvlink_runner.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/latest.py`|`jra_van_retriever/workflows/latest.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/odds_archive.py`|`jra_van_retriever/acquisition/odds_archive.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/odds_contract.py`|`jra_van_retriever/contracts/odds.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/progress.py`|`jra_van_retriever/progress/ledger.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/progress_output.py`|`jra_van_retriever/progress/output.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/progress_state.py`|`jra_van_retriever/progress/state.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/race_key_parser.py`|`jra_van_retriever/parsing/race_key.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/raw_snapshot.py`|`jra_van_retriever/progress/raw_observation.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/realtime.py`|`jra_van_retriever/workflows/realtime.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/retriever/setting.py`|`jra_van_retriever/config/profiles.py`<br>`jra_van_retriever/config/validation.py`<br>`jra_van_retriever/acquisition/setting_xml.py`<br>`configuration/loader.py`<br>`configuration/path_resolver.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/retriever/weekly.py`|`jra_van_retriever/workflows/historical_odds.py`<br>`jra_van_retriever/workflows/historical_odds_plan.py`<br>`jra_van_retriever/workflows/historical_odds_request.py`<br>`jra_van_retriever/workflows/historical_odds_recovery.py`<br>`jra_van_retriever/workflows/historical_odds_publication.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/settings/__init__.py`|該当する新packageの`__init__.py`へ統合|旧package宣言を削除。旧settings/utilsを含む旧配置は廃止し、実装を残さない。|
|`src/settings/data_paths.py`|`configuration/data_paths.py`<br>`configuration/loader.py`<br>`configuration/path_resolver.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
|`src/tests/test_data_pipeline.py`|`src/tests/integration/test_data_pipeline.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_data_retriever.py`|`src/tests/integration/test_data_retriever.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_datamart.py`|`src/tests/unit/test_datamart.py`<br>`src/tests/integration/test_datamart.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_explanatory_variables.py`|`src/tests/integration/test_explanatory_variables.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_feature_catalog.py`|`src/tests/unit/test_feature_catalog.py`<br>`src/tests/integration/test_feature_catalog.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_feature_tables.py`|`src/tests/unit/test_feature_tables.py`<br>`src/tests/integration/test_feature_tables.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_features.py`|`src/tests/unit/test_features.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_historical.py`|`src/tests/unit/test_historical.py`<br>`src/tests/integration/test_historical.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_individual_feature_builders.py`|`src/tests/integration/test_individual_feature_builders.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_jvlinktosqlite.py`|`src/tests/integration/test_jvlinktosqlite.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_latest.py`|`src/tests/integration/test_latest.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_main.py`|`src/tests/unit/test_main.py`<br>`src/tests/integration/test_main.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_make_features.py`|`src/tests/integration/test_make_features.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_models.py`|`src/tests/unit/test_models.py`<br>`src/tests/integration/test_models.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_odds_archive.py`|`src/tests/integration/test_odds_archive.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_project_environment.py`|`src/tests/test_project_environment.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_read_json.py`|`src/tests/integration/test_read_json.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_realtime.py`|`src/tests/integration/test_realtime.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_serialization.py`|`src/tests/unit/test_serialization.py`<br>`src/tests/integration/test_serialization.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_setting.py`|`src/tests/integration/test_setting.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_walk_forward.py`|`src/tests/unit/test_walk_forward.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_weekly_progress.py`|`src/tests/integration/test_weekly_progress.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/utils/__init__.py`|該当する新packageの`__init__.py`へ統合|旧package宣言を削除。旧settings/utilsを含む旧配置は廃止し、実装を残さない。|
|`src/utils/data_loader.py`|`data/loader/processed_data_loader.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/utils/json_output.py`|`data/saver/write_json.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/utils/loader/__init__.py`|該当する新packageの`__init__.py`へ統合|旧package宣言を削除。旧settings/utilsを含む旧配置は廃止し、実装を残さない。|
|`src/utils/loader/read_json.py`|`data/loader/read_json.py`|責務に対応する機能内の配置へ移設。既存の型・引数・動作を維持。|
|`src/utils/loader/read_parquet.py`|`data/loader/read_parquet.py`<br>`data/loader/processed_data_loader.py`<br>`data/storage/snapshot_store.py`|混在していた責務を分割し、共通処理の所有者を一意にした。|
## 実際に分離・共通化した処理

- TOML物理読込と相対/絶対/ホームパスの解決をconfigurationに集約した。DataPathsは共有パス固有の必須値、JVLink configは取得固有の型・検証、feature catalogはID/名前/順序を所有する。共通基盤から機能への依存はない。
- SQLiteReaderは接続・読取取引・表/列/rowid順バッチ、sqlite_to_arrowは純粋な宣言型/値変換、Parquet writerは物理保存、SnapshotBuilderは生成と保存結果照合を所有する。
- SnapshotStoreに保存構造とCURRENT解決、snapshot_publisherに完成版renameと原子的CURRENT更新を移した。Reader/Writer/Converterには版管理を残していない。
- 週次は計画、要求実行、復旧、公開へ実処理を分け、workflowに年単位統括とロック順序を残した。台帳確定前に派生報告を判断元に使わず、要求・隔離・reset・結果確定の順序を維持する。
- historical_basicはbase取得だけを所有する。旧の非週次オッズ全取得/skip-existing経路はhistorical_odds_legacyへ移し、既存の統合APIはretriever.pyに限定した。
- 特徴量とDatamartの保存前/読込後検証・metadata生成を機能に残し、物理Parquet処理だけを共通化した。Datamart builderは純粋結合、ファイルからの構築はtables/parquetへ移した。
- modelsでは行型、承認schema、値/ラベル/race検証、時点監査、dataset集約、構築を分割した。学習、native backend、推論、評価、成果物、JSON変換の所有者を分離した。
- CLIは機能ごとの引数・表示・終了処理へ分割し、mainに組立/登録/起動だけを残した。新Datamart CLIは既存APIを利用し、定義名のみをcatalogから検証へ渡す。
- settings/utilsの旧package、モデルの旧内部配置、不要な宣言を廃止した。新依存、将来用model設定、空の将来用moduleは導入していない。

## 設定・I/O・状態の依存方向

`機能config/catalog → configuration.loader/path_resolver → 標準ライブラリ`を維持する。
機能固有の必須値・DataSpec/日付・feature ID/name検証は各所有者に残す。
`config/`の既存3ファイルは変更しない。特徴量の独自IDも既存の検証に従い、F01〜F21だけへの新しい制限は加えない。

`SnapshotBuilder → SQLiteReader / 純粋Arrow変換 / Parquet writer / SnapshotStore / publisher`と構成する。
完全版の全表は同一SQLite読取取引に固定し、最大65,536行/目安1,000,000セルのバッチ、空schema、
TEXT/DATETIME、NULL、先頭ゼロ、rowid fallback、保存後schema/行数照合を維持する。
完成版だけをrename後にCURRENTで選択する。CURRENT更新失敗は従前のpointerと読み込みを維持し、
未選択の完成版を残す既存の失敗時契約も変えない。

`DataLoader → SnapshotStore（選択パス） + Parquet reader（物理読込）`であり、下位の物理readerは
Storageをimportしない。バッチ読込は反復開始までCURRENTを解決せず、無効batch_sizeを先に拒否する。
共通packageの__init__には上位統括を再公開しないため、下位から上位への循環を作らない。

## 維持した互換入口と移行

|公開入口|利用根拠・維持理由|
|---|---|
|`jra_van_retriever.retriever.DataRetriever`|READMEとtest_data_retrieverで利用する既存の公開取得API名。実クラスJraVanRetrieverの同一参照として維持する。|
|`jra_van_retriever.retriever.HistoricalRetriever` / `retrieve_historical`|test_historicalと既存統合APIでbase→旧オッズ経路を利用する。retriever.pyの互換組立から専有workflowへ委譲し、元と同じ一時ディレクトリと順序を維持する。|
|`data.storage.snapshot_builder.DataPreprocesser`|READMEとCLI/既存pipelineテストで使用するAPIの綴り。実クラスSnapshotBuilderの同一参照としてfrom_toml/rebuild/update/update_raceを維持する。|
|`data.loader.processed_data_loader.DataLoader`|READMEと既存pipelineテストで利用。list/read/iter/realtimeの引数、結果と例外を維持する。|
|`models`の既存公開名|既存models/__init__.pyの公開リスト全体を新所有先から再公開する。保存形式や学習・推論仕様を変えない。|
|`models.predict_model`のRankingModel/RankingPrediction|元から存在する5行のprediction互換入口であり、既存モデルテストが利用していた。新Facadeは作らず、既存入口から新rankerの同じ2名を再公開する。|
|`RankingModel.save/load`|既存モデルテストの保存・再読込API。実処理はNativeModelArtifactに集約し、metadata検証・復旧を複製しない。|
|`make_datamart`の5公開名|既存package APIとround-tripテストで利用。joinはbuilder、他4名はtables/parquetから再公開する。|
|`main.register_feature_commands`|既存CLI登録テストとADR-022で公開する登録関数。mainの組立責務として同じ3コマンドを登録する関数を維持する。|
|週次の公開メソッドとWeeklyBatchResult|既存取得統括・週次テストで利用。publicメソッドの署名を維持し、公開処理の所有者へ委譲する。|

旧settings/utils/features/retriever/preprocesserのimportは上表の新所有先へ移行する。
旧make_datamart.builderのファイルAPI4名はtables/parquetへ移す。純粋joinとの循環を避けるため、
旧内部ファイルの一律shim、遅延import、動的再公開は追加しない。クラス名/公開名の維持と内部import移行を区別する。
ADR-008とADR-021〜023の該当配置判断はADR-024で置換し、過去の理由本文は書き換えない。
ADR-008のraw readerをpreprocessingに限定した配置判断だけを置換し、保存構造・単一SQLite読取の一貫性・完成版公開・原子的CURRENT・公開失敗時の旧版保持・レース別公開は継承する。

## 新Datamart CLI

`datamart build --input first.parquet --input second.parquet --output out.parquet --features-config config/features.toml`
を追加した。--inputの順に既存APIで左結合する。features-configは既定config/features.tomlで、
元の3固定featureと宣言されたF01〜F21/独自IDの名前を同じmetadata検証へ渡す。未登録名は拒否する。
成功はstdoutに`datamart saved: N rows`、入力・結合失敗はstderrに説明、終了コード1。
import/helpでは設定・入力を読まず、取得環境も作らない。

## 各最終ファイルの責務

以下は現行srcの全Pythonファイル、configsの全TOMLファイルを省略せず列挙する。
package宣言も記録し、存在しない将来用model設定は含めない。

|ファイル|責務|
|---|---|
|`src/cli/__init__.py`|機能別の責務でまとめたコマンドラインの境界。|
|`src/cli/jra_van_retriever.py`|取得のオプションを検証し、取得のコマンドを実行する。|
|`src/cli/json_io.py`|汎用のJSON入出力の失敗を、CLIの境界で変換する。|
|`src/cli/make_datamart.py`|明示的に順序付けた中間Parquetの入力から、datamartを構築する。|
|`src/cli/make_features.py`|コマンドラインの境界で、説明変数の生成を実行する。|
|`src/cli/models.py`|モデル入力の監査、投影、walk-forward評価を実行する。|
|`src/cli/options.py`|データ取得と前処理のCLIで共有するオプションの型を定義する。|
|`src/cli/preprocessor.py`|processedデータの公開を実行し、コマンドの結果を報告する。|
|`src/configuration/__init__.py`|設定の責務。|
|`src/configuration/data_paths.py`|レースデータのworkflowで共有するファイルシステムのパスを読み込む。|
|`src/configuration/loader.py`|特徴量固有の設定の契約を適用せずに、TOMLを読む。|
|`src/configuration/path_resolver.py`|明示的に設定したパスを、その設定ファイルの位置を基準に解決する。|
|`src/data/__init__.py`|共通のデータI/O、変換、snapshotのライフサイクルの境界。|
|`src/data/loader/__init__.py`|データローダーの責務。|
|`src/data/loader/processed_data_loader.py`|公開のprocessedデータの読込facade。|
|`src/data/loader/read_json.py`|CLIや特徴量固有の検証を行わずに、UTF-8のJSONオブジェクトを読む。|
|`src/data/loader/read_parquet.py`|保存の版の方針を持たずに、Parquetファイルと上限のあるバッチを読む。|
|`src/data/loader/read_sqlite.py`|一つの読み取り専用トランザクションを通じて、rawのSQLiteの表を読む。|
|`src/data/preprocessor/__init__.py`|rawの入力元の値の純粋な変換。|
|`src/data/preprocessor/sqlite_to_arrow.py`|SQLite由来の値を、既存の全列文字列のArrowの契約へ変換する。|
|`src/data/saver/__init__.py`|データ保存の責務。|
|`src/data/saver/write_json.py`|JSON互換の値を、標準のUTF-8のJSONとして書き込む。|
|`src/data/saver/write_parquet.py`|明示的なArrowの表やバッチを、Parquetファイルへ書き込む。|
|`src/data/storage/__init__.py`|保存の責務。|
|`src/data/storage/snapshot_builder.py`|一貫した一つのrawのSQLiteの観測から、processedのsnapshotを構築する。|
|`src/data/storage/snapshot_publisher.py`|完成したprocessedの版を、CURRENTの原子的な置き換えによって公開する。|
|`src/data/storage/snapshot_store.py`|processedのsnapshotの配置と、CURRENTの版の解決を所有する。|
|`src/domain/__init__.py`|データの境界から独立した、共有のドメイン値。|
|`src/domain/race_key.py`|取得、前処理、読込をまたいで使う、共有のレースの識別。|
|`src/jra_van_retriever/__init__.py`|JRA-VAN取得の責務。|
|`src/jra_van_retriever/acquisition/__init__.py`|取得の責務。|
|`src/jra_van_retriever/acquisition/acquisition_lock.py`|アプリケーションの取得を直列化し、一つのrawデータベースをその台帳に結び付ける。|
|`src/jra_van_retriever/acquisition/jvlink_runner.py`|レースデータの取得のために、ローカルのJVLinkToSQLiteの実行ファイルを実行する。|
|`src/jra_van_retriever/acquisition/odds_archive.py`|JVLinkToSQLiteのrealtimeのオッズの表を、スキーマを変えずに永続化する。|
|`src/jra_van_retriever/acquisition/setting_xml.py`|型付きのJVLink profileから、実行用のXMLを生成する。|
|`src/jra_van_retriever/config/__init__.py`|設定の責務。|
|`src/jra_van_retriever/config/profiles.py`|宣言的な取得profileを、検証済みの設定へ変換する。|
|`src/jra_van_retriever/config/validation.py`|ファイルを読まずに、JVLink固有のTOMLの値を検証する。|
|`src/jra_van_retriever/contracts/__init__.py`|契約の責務。|
|`src/jra_van_retriever/contracts/odds.py`|共有のrawのO1/O2の表と、完全なレースキーの列を定義する。|
|`src/jra_van_retriever/parsing/__init__.py`|解析の責務。|
|`src/jra_van_retriever/parsing/race_key.py`|取得の境界で、rawのレースキーの行を変換する。|
|`src/jra_van_retriever/progress/__init__.py`|進捗の責務。|
|`src/jra_van_retriever/progress/ledger.py`|正本となる過去オッズの進捗台帳を永続化し、検証する。|
|`src/jra_van_retriever/progress/output.py`|確定済みの進捗から、historical-oddsのJSONとTOMLの報告を再生成する。|
|`src/jra_van_retriever/progress/raw_observation.py`|rawの取得データを観測し、外部の書き込みの前にreaderを閉じる。|
|`src/jra_van_retriever/progress/state.py`|永続化を伴わずに、取得の値を定義し、進捗を計算する。|
|`src/jra_van_retriever/retriever.py`|JRA-VANのレースデータ取得のための、公開のオーケストレーションAPIを提供する。|
|`src/jra_van_retriever/workflows/__init__.py`|workflowの責務。|
|`src/jra_van_retriever/workflows/historical_basic.py`|JVLinkToSQLiteを通じて、過去の基本レースデータを取得する。|
|`src/jra_van_retriever/workflows/historical_odds.py`|上限のある過去オッズのバッチと、そのライフサイクルの所有者を調整する。|
|`src/jra_van_retriever/workflows/historical_odds_legacy.py`|既存の統合されたPythonの取得APIのために、過去オッズを取得する。|
|`src/jra_van_retriever/workflows/historical_odds_plan.py`|rawと確定済みの台帳の観測から、年単位のオッズの作業を計画する。|
|`src/jra_van_retriever/workflows/historical_odds_publication.py`|共通の取得ロックの下で、rawがそろった過去オッズを公開する。|
|`src/jra_van_retriever/workflows/historical_odds_recovery.py`|stagingをリセットする前に、中断した取得の証拠を保存する。|
|`src/jra_van_retriever/workflows/historical_odds_request.py`|永続的な過去オッズの取得要求を一つ実行し、分類する。|
|`src/jra_van_retriever/workflows/latest.py`|JVLinkToSQLiteを通じて、最新のレースデータの変更を取得する。|
|`src/jra_van_retriever/workflows/realtime.py`|JVLinkToSQLiteを通じて、対象の1レースの予測時のオッズを取得する。|
|`src/main.py`|keiba-aiのコマンドラインインターフェースを組み立て、登録し、起動する。|
|`src/make_datamart/__init__.py`|特徴量の中間表からのdatamartの構築。|
|`src/make_datamart/builder.py`|I/Oを行わずに、検証済みの特徴量の表を、順序付きのdatamartへ結合する。|
|`src/make_datamart/tables/__init__.py`|datamartのスキーマの契約と、明示的な永続化。|
|`src/make_datamart/tables/parquet.py`|検証済みのdatamartのParquetの表を永続化し、再読込する。|
|`src/make_datamart/tables/schema.py`|datamartの列と、永続化したmetadataを宣言し、復号する。|
|`src/make_datamart/validation/__init__.py`|datamartのスキーマと行の検証。|
|`src/make_datamart/validation/table.py`|datamartのスキーマ、キー、時刻、欠損値を検証する。|
|`src/make_features/__init__.py`|特徴量固有の生成、検証、表の契約。|
|`src/make_features/basic_conditions_and_weight.py`|基本条件・斤量の中間特徴量の行と表を構築する。|
|`src/make_features/catalog/__init__.py`|宣言的な特徴量の登録を読み込み、結び付ける。|
|`src/make_features/catalog/loader.py`|実装をimportせずに、宣言的な特徴量のcatalogを読む。|
|`src/make_features/catalog/registry.py`|検証済みの特徴量の定義を、明示的に登録した実装に結び付ける。|
|`src/make_features/condition_adjusted_ability.py`|条件補正能力の中間特徴量の行と表を構築する。|
|`src/make_features/condition_suitability.py`|条件別適性の中間特徴量の行と表を構築する。|
|`src/make_features/contracts/__init__.py`|特徴量の入力と中間行を宣言する。|
|`src/make_features/contracts/rows.py`|保存への依存を持たずに、正規化した特徴量の中間行を表す。|
|`src/make_features/contracts/types.py`|明示的な特徴量の入力と、構造化された検証結果。|
|`src/make_features/expected_race_development.py`|想定展開の中間特徴量の行と表を構築する。|
|`src/make_features/explanatory_variables.py`|個別のモジュールを通じて、説明変数の中間行を構築する。|
|`src/make_features/generation/__init__.py`|監査済みの行の生成を共有する。|
|`src/make_features/generation/base.py`|特徴量の行の生成と、検証済みのArrowの表の構築を共有する。|
|`src/make_features/generation/normalization.py`|監査済みの明示的な特徴量の入力を、共通の中間行の型へ正規化する。|
|`src/make_features/hill_and_wood_workouts.py`|坂路・ウッド調教の中間特徴量の行と表を構築する。|
|`src/make_features/history_volume_and_missingness.py`|履歴量・欠損状態の中間特徴量の行と表を構築する。|
|`src/make_features/jockey_combination.py`|騎手組合せの中間特徴量の行と表を構築する。|
|`src/make_features/jockey_performance.py`|騎手成績の中間特徴量の行と表を構築する。|
|`src/make_features/market_characteristics.py`|市場特徴の中間特徴量の行と表を構築する。|
|`src/make_features/odds_ratio.py`|明示的なオッズ比の中間特徴量の表を構築する。|
|`src/make_features/opponent_pagerank.py`|対戦相手補正PageRankの中間特徴量の行と表を構築する。|
|`src/make_features/past_body_weight.py`|過去馬体重推移の中間特徴量の行と表を構築する。|
|`src/make_features/past_lap_and_running_style.py`|過去ラップ・走り方の中間特徴量の行と表を構築する。|
|`src/make_features/past_racing_ability.py`|過去走力の中間特徴量の行と表を構築する。|
|`src/make_features/pedigree.py`|文字列値の血統の中間特徴量の表を構築する。|
|`src/make_features/pedigree_suitability.py`|血統適性の中間特徴量の行と表を構築する。|
|`src/make_features/previous_race_result.py`|前走結果の中間特徴量の表を構築する。|
|`src/make_features/recent_performance.py`|近走成績の中間特徴量の行と表を構築する。|
|`src/make_features/recent_stability.py`|近況安定性の中間特徴量の行と表を構築する。|
|`src/make_features/rest_and_condition_change.py`|休養・条件変更の中間特徴量の行と表を構築する。|
|`src/make_features/running_style_and_position.py`|脚質・位置取りの中間特徴量の行と表を構築する。|
|`src/make_features/same_gate_and_trainer_relative.py`|同枠・同厩舎相対の中間特徴量の行と表を構築する。|
|`src/make_features/serialization/__init__.py`|特徴量の契約を、JSON互換の値との間で相互に変換する。|
|`src/make_features/serialization/inputs.py`|復号したJSONオブジェクトを、特徴量群の入力の契約へ変換する。|
|`src/make_features/serialization/outputs.py`|特徴量の生成結果と監査を、JSONにできる値へ変換する。|
|`src/make_features/tables/__init__.py`|登録した特徴量の表を構築し、永続化する。|
|`src/make_features/tables/build.py`|正規化した特徴量の行から、中間表を構築する。|
|`src/make_features/tables/parquet.py`|検証済みの特徴量の中間表を永続化し、再読込する。|
|`src/make_features/tables/schema.py`|登録した特徴量の中間スキーマを宣言し、解決する。|
|`src/make_features/trainer_performance.py`|調教師成績の中間特徴量の行と表を構築する。|
|`src/make_features/validation/__init__.py`|特徴量の証拠と表を検証する。|
|`src/make_features/validation/audit.py`|レースの形を監査し、共有の特徴量の検証を調整する。|
|`src/make_features/validation/availability.py`|明示的に渡した特徴量の時刻を、正規化して検証する。|
|`src/make_features/validation/groups.py`|特徴量のscalar、欠損、状態、出典の証拠を検証する。|
|`src/make_features/validation/leakage.py`|予測対象の結果の列と、将来の結果への参照を拒否する。|
|`src/make_features/validation/table.py`|特徴量の表のスキーマ、キー、利用可能性を検証する。|
|`src/make_features/validation/values.py`|データを変更せずに、scalarの値と欠損を確認する。|
|`src/make_features/within_race_relative.py`|レース内相対の中間特徴量の行と表を構築する。|
|`src/models/__init__.py`|LambdaRank MVPのための、レース順位付けモデルの基本要素。|
|`src/models/artifacts/__init__.py`|成果物の責務。|
|`src/models/artifacts/native_model.py`|ネイティブのモデルの成果物を、完全な一式として公開、検証、復旧する。|
|`src/models/backends/__init__.py`|バックエンドの責務。|
|`src/models/backends/lightgbm.py`|検証済みのモデル入力を、遅延importしたLightGBMのバックエンドへ接続する。|
|`src/models/dataset/__init__.py`|データセットの責務。|
|`src/models/dataset/availability.py`|明示的なfreeze時刻における特徴量の値を監査する。|
|`src/models/dataset/builder.py`|検証済みの予測行と、ラベル付きの順位付けデータセットを構築する。|
|`src/models/dataset/dataset.py`|検証済みの、レースが連続する順位付けデータセットを保持する。|
|`src/models/dataset/rows.py`|不変のモデル入力の行と、数値の値の型。|
|`src/models/dataset/schema.py`|承認済みのモデルの特徴量スキーマと、意味上のmetadataを所有する。|
|`src/models/dataset/validation.py`|モデルの行、ラベル、レースのグループを検証し、正規化する。|
|`src/models/evaluation/__init__.py`|評価の責務。|
|`src/models/evaluation/metrics.py`|LambdaRank MVPのための、レース単位の順位付けの指標。|
|`src/models/evaluation/walk_forward.py`|レース単位の時系列のwalk-forwardによる分割と評価。|
|`src/models/predict_model.py`|既存の予測のimportの入口を維持する。|
|`src/models/ranking/__init__.py`|順位付けの責務。|
|`src/models/ranking/ranker.py`|特徴量の行にscoreを付け、決定論的なレース内の順位を割り当てる。|
|`src/models/ranking/rules.py`|固定の順位付けの契約と、純粋なレースのグループ化・順序付けの規則を定義する。|
|`src/models/serialization/__init__.py`|モデルの契約を、JSON互換の値との間で相互に変換する。|
|`src/models/serialization/inputs.py`|復号したJSONオブジェクトを、モデルの特徴量入力の契約へ変換する。|
|`src/models/serialization/outputs.py`|モデルの特徴量、監査、評価を、JSONにできる値へ変換する。|
|`src/models/training/__init__.py`|学習の責務。|
|`src/models/training/train.py`|LambdaRank MVPの学習の入口。|
|`src/tests/integration/test_cli_boundaries.py`|integration: CLIの構成、独立したimport、共有の入力の契約のテスト。|
|`src/tests/integration/test_configuration.py`|integration: 共有のTOMLの物理読込とパスの解決のテスト。|
|`src/tests/integration/test_data_pipeline.py`|integration: rawのSQLiteの前処理とprocessedのParquetの読込のテスト。|
|`src/tests/integration/test_data_retriever.py`|integration: 公開のレースデータ取得facadeのテスト。|
|`src/tests/integration/test_datamart.py`|integration: 特徴量の中間表の、順序付きのdatamart結合のテスト。|
|`src/tests/integration/test_explanatory_variables.py`|integration: 明示的なF01〜F21の説明変数の境界のテスト。|
|`src/tests/integration/test_feature_catalog.py`|integration: 宣言的な登録が、監査、生成、保存の契約まで届くことを検証する。|
|`src/tests/integration/test_feature_tables.py`|integration: 特徴量固有の中間表のテスト。|
|`src/tests/integration/test_historical.py`|integration: 過去のレースとオッズの取得のオーケストレーションのテスト。|
|`src/tests/integration/test_individual_feature_builders.py`|integration: 個別のbuilderが、中間行、出典の監査、表の保存を共有することを検証する。|
|`src/tests/integration/test_jvlinktosqlite.py`|integration: ローカルのJVLinkToSQLiteのsubprocess境界のテスト。|
|`src/tests/integration/test_latest.py`|integration: 最新データの取得のオーケストレーションのテスト。|
|`src/tests/integration/test_main.py`|integration: TyperのデータCLIのテスト。|
|`src/tests/integration/test_make_features.py`|integration: 特徴量の実行のJSONシリアライズのテスト。|
|`src/tests/integration/test_models.py`|integration: LambdaRankの順位付けMVPに絞ったテスト。|
|`src/tests/integration/test_odds_archive.py`|integration: 一時的なJVLinkToSQLiteのオッズの表の、累積のarchiveのテスト。|
|`src/tests/test_project_environment.py`|既存環境smoke: パッケージにしないbootstrap環境のスモークテスト。|
|`src/tests/integration/test_read_json.py`|integration: 再利用できるUTF-8のJSONオブジェクトのローダーのテスト。|
|`src/tests/integration/test_realtime.py`|integration: 予測時のrealtimeのオッズの取得のテスト。|
|`src/tests/integration/test_serialization.py`|integration: 再利用できる、特徴量とモデルのJSONの契約の変換のテスト。|
|`src/tests/integration/test_setting.py`|integration: 宣言的なJVLinkToSQLiteの設定の生成のテスト。|
|`src/tests/integration/test_weekly_progress.py`|integration: 分離した週次の進捗のbootstrapと突合のテスト。|
|`src/tests/unit/test_cli_boundaries.py`|unit: CLIの構成、独立したimport、共有の入力の契約のテスト。|
|`src/tests/unit/test_configuration.py`|unit: 共有のTOMLの物理読込とパスの解決のテスト。|
|`src/tests/unit/test_datamart.py`|unit: 特徴量の中間表の、順序付きのdatamart結合のテスト。|
|`src/tests/unit/test_feature_catalog.py`|unit: 宣言的な登録が、監査、生成、保存の契約まで届くことを検証する。|
|`src/tests/unit/test_feature_tables.py`|unit: 特徴量固有の中間表のテスト。|
|`src/tests/unit/test_features.py`|unit: 時点に基づく特徴量の構築と、利用可能性の監査のテスト。|
|`src/tests/unit/test_historical.py`|unit: 過去のレースとオッズの取得のオーケストレーションのテスト。|
|`src/tests/unit/test_main.py`|unit: TyperのデータCLIのテスト。|
|`src/tests/unit/test_models.py`|unit: LambdaRankの順位付けMVPに絞ったテスト。|
|`src/tests/unit/test_serialization.py`|unit: 再利用できる、特徴量とモデルのJSONの契約の変換のテスト。|
|`src/tests/unit/test_walk_forward.py`|unit: レース単位の時系列のwalk-forward評価のテスト。|
|`configs/data.toml`|共有raw/processed/runtimeパス宣言。|
|`configs/features.toml`|特徴量ID・名前・登録順の宣言。|
|`configs/jvlink.toml`|取得profile・DataSpec・期間の宣言。|

## 最終の対象ディレクトリ構成（全ファイル）

対象はsrcとconfigs。生成キャッシュ・取得データ・仮想環境を除き全ファイルを示す。

```text
configs/
├── data.toml
├── features.toml
└── jvlink.toml
src/
├── cli/
│   ├── __init__.py
│   ├── jra_van_retriever.py
│   ├── json_io.py
│   ├── make_datamart.py
│   ├── make_features.py
│   ├── models.py
│   ├── options.py
│   └── preprocessor.py
├── configuration/
│   ├── __init__.py
│   ├── data_paths.py
│   ├── loader.py
│   └── path_resolver.py
├── data/
│   ├── loader/
│   │   ├── __init__.py
│   │   ├── processed_data_loader.py
│   │   ├── read_json.py
│   │   ├── read_parquet.py
│   │   └── read_sqlite.py
│   ├── preprocessor/
│   │   ├── __init__.py
│   │   └── sqlite_to_arrow.py
│   ├── saver/
│   │   ├── __init__.py
│   │   ├── write_json.py
│   │   └── write_parquet.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── snapshot_builder.py
│   │   ├── snapshot_publisher.py
│   │   └── snapshot_store.py
│   └── __init__.py
├── domain/
│   ├── __init__.py
│   └── race_key.py
├── jra_van_retriever/
│   ├── acquisition/
│   │   ├── __init__.py
│   │   ├── acquisition_lock.py
│   │   ├── jvlink_runner.py
│   │   ├── odds_archive.py
│   │   └── setting_xml.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── profiles.py
│   │   └── validation.py
│   ├── contracts/
│   │   ├── __init__.py
│   │   └── odds.py
│   ├── parsing/
│   │   ├── __init__.py
│   │   └── race_key.py
│   ├── progress/
│   │   ├── __init__.py
│   │   ├── ledger.py
│   │   ├── output.py
│   │   ├── raw_observation.py
│   │   └── state.py
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── historical_basic.py
│   │   ├── historical_odds.py
│   │   ├── historical_odds_legacy.py
│   │   ├── historical_odds_plan.py
│   │   ├── historical_odds_publication.py
│   │   ├── historical_odds_recovery.py
│   │   ├── historical_odds_request.py
│   │   ├── latest.py
│   │   └── realtime.py
│   ├── __init__.py
│   └── retriever.py
├── make_datamart/
│   ├── tables/
│   │   ├── __init__.py
│   │   ├── parquet.py
│   │   └── schema.py
│   ├── validation/
│   │   ├── __init__.py
│   │   └── table.py
│   ├── __init__.py
│   └── builder.py
├── make_features/
│   ├── catalog/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   └── registry.py
│   ├── contracts/
│   │   ├── __init__.py
│   │   ├── rows.py
│   │   └── types.py
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── normalization.py
│   ├── serialization/
│   │   ├── __init__.py
│   │   ├── inputs.py
│   │   └── outputs.py
│   ├── tables/
│   │   ├── __init__.py
│   │   ├── build.py
│   │   ├── parquet.py
│   │   └── schema.py
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── audit.py
│   │   ├── availability.py
│   │   ├── groups.py
│   │   ├── leakage.py
│   │   ├── table.py
│   │   └── values.py
│   ├── __init__.py
│   ├── basic_conditions_and_weight.py
│   ├── condition_adjusted_ability.py
│   ├── condition_suitability.py
│   ├── expected_race_development.py
│   ├── explanatory_variables.py
│   ├── hill_and_wood_workouts.py
│   ├── history_volume_and_missingness.py
│   ├── jockey_combination.py
│   ├── jockey_performance.py
│   ├── market_characteristics.py
│   ├── odds_ratio.py
│   ├── opponent_pagerank.py
│   ├── past_body_weight.py
│   ├── past_lap_and_running_style.py
│   ├── past_racing_ability.py
│   ├── pedigree.py
│   ├── pedigree_suitability.py
│   ├── previous_race_result.py
│   ├── recent_performance.py
│   ├── recent_stability.py
│   ├── rest_and_condition_change.py
│   ├── running_style_and_position.py
│   ├── same_gate_and_trainer_relative.py
│   ├── trainer_performance.py
│   └── within_race_relative.py
├── models/
│   ├── artifacts/
│   │   ├── __init__.py
│   │   └── native_model.py
│   ├── backends/
│   │   ├── __init__.py
│   │   └── lightgbm.py
│   ├── dataset/
│   │   ├── __init__.py
│   │   ├── availability.py
│   │   ├── builder.py
│   │   ├── dataset.py
│   │   ├── rows.py
│   │   ├── schema.py
│   │   └── validation.py
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── metrics.py
│   │   └── walk_forward.py
│   ├── ranking/
│   │   ├── __init__.py
│   │   ├── ranker.py
│   │   └── rules.py
│   ├── serialization/
│   │   ├── __init__.py
│   │   ├── inputs.py
│   │   └── outputs.py
│   ├── training/
│   │   ├── __init__.py
│   │   └── train.py
│   ├── __init__.py
│   └── predict_model.py
├── tests/
│   ├── integration/
│   │   ├── test_cli_boundaries.py
│   │   ├── test_configuration.py
│   │   ├── test_data_pipeline.py
│   │   ├── test_data_retriever.py
│   │   ├── test_datamart.py
│   │   ├── test_explanatory_variables.py
│   │   ├── test_feature_catalog.py
│   │   ├── test_feature_tables.py
│   │   ├── test_historical.py
│   │   ├── test_individual_feature_builders.py
│   │   ├── test_jvlinktosqlite.py
│   │   ├── test_latest.py
│   │   ├── test_main.py
│   │   ├── test_make_features.py
│   │   ├── test_models.py
│   │   ├── test_odds_archive.py
│   │   ├── test_read_json.py
│   │   ├── test_realtime.py
│   │   ├── test_serialization.py
│   │   ├── test_setting.py
│   │   └── test_weekly_progress.py
│   ├── unit/
│   │   ├── test_cli_boundaries.py
│   │   ├── test_configuration.py
│   │   ├── test_datamart.py
│   │   ├── test_feature_catalog.py
│   │   ├── test_feature_tables.py
│   │   ├── test_features.py
│   │   ├── test_historical.py
│   │   ├── test_main.py
│   │   ├── test_models.py
│   │   ├── test_serialization.py
│   │   └── test_walk_forward.py
│   └── test_project_environment.py
└── main.py
```

## 更新文書・ADR

- README.md: 新import先、共通I/O/Storageの境界、Datamart CLI。
- ARCHITECTURE.md: 実装済み責務、依存、既存契約、分割後の順序。
- docs/implementation-design.md: 現行配置とDatamart CLIを更新し、未実装候補との区別を維持。
- docs/rules/architecture.md / coding-style.md: 現行の所有者とCLI境界。
- ADR-024: 新しい配置・責務分離の判断。ADR-008/021/022/023は配置判断の置換先を状態欄へ記録。
- docs/refactoring-pr21.md: 本記録。

## 前段階の検証（8053ea8までの完了証跡）

変更前はrootによりuv sync --locked、Ruff、mypy、pytest 5869件、native Codex 0.151.0のガード回帰が成功。
変更後の最終実行は`uv run ruff format --check .`（160ファイル）、`uv run ruff check .`、`uv run mypy src`（160ファイル）、`uv run pytest -q`（5892件、32.93秒）が全て成功した。既存5869件に23件の回帰を追加し、途中の焦点検証も成功した。
rootによるガード回帰もCodex 0.151.0・PowerShell 7でexit 0。native process、PR lifecycle 19 fixtures、base update 17 fixturesと実conflict、baseline/task-state encodingを含み、`Guard trust-boundary regression validation passed`を確認した。ソース検証や実行ポリシー検証は省略していない。
rootの独立照合ではCLIフラグ1536ケース（終了・stdout/stderr・呼出先/引数/例外）、実プロセスCLI23ケース、モデル200組、SQLite/Parquet（空表・70003行・NULL・先頭ゼロ・rowid shadow）の基準結果が一致した。必須のDatamart追加によるroot helpの1行だけを比較から分離し、setの表示順を正規化した。
rootの静的検査では分割後runtime modulesに循環がなく、全module import時もLightGBMを読み込まないこと、TOML/Parquet物理I/Oの所有者が一意であることを確認した。

## 制約・残リスク

実際のJRA-VAN/JVLinkToSQLite取得は実行していない。外部プロセス境界は既存の決定的テストで検証する。
Windows sandboxのtmp ACLにより通常権限ではpytest tempと全体探索の一部が失敗するため、該当検証はrequire_escalatedで通常ユーザー権限実行した。失敗をテスト成功には数えていない。
旧内部importの移行が必要である。保存データ・モデル成果物・設定値の移行は不要。
モデル設定外部化、未承認の特徴量計算、履歴集計、nested選定、train/predict CLI、購入判断は本変更に含まない。
