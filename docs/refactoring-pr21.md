# PR #21 責務分離リファクタリング記録

前段階の基準HEAD: `781cbcfdda0d1ec7377e70440e887562e89629dd`。その実装は`8053ea8fa3027109c5082612b0689e169f5030c4`までに完了した。
今回の構成変更の基準は8053ea8。以下の旧123ファイルの履歴は保持し、移設先・責務一覧・最終ツリーはADR-025の現行配置へ更新した。今回の差分と検証は[データ基盤・CLI移行記録](refactoring-pr21-data-cli.md)を参照する。
[ADR-024](decisions/ADR-024-separate-functional-responsibilities.md)に従い、既存の計算、設定値、保存形式、ロック・台帳・復旧とCLIの契約を維持して所有者を分離した。

## 旧ファイルと新ファイルの全件対応

変更前の`src/`全123 Pythonファイル（本体101、テスト22）を以下に列挙する。テストファイルは全て維持した。

|旧ファイル|新しい所有先（src/配下）|処置・理由|
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
|`src/tests/test_data_pipeline.py`|`tests/test_data_pipeline.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_data_retriever.py`|`tests/test_data_retriever.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_datamart.py`|`tests/test_datamart.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_explanatory_variables.py`|`tests/test_explanatory_variables.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_feature_catalog.py`|`tests/test_feature_catalog.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_feature_tables.py`|`tests/test_feature_tables.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_features.py`|`tests/test_features.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_historical.py`|`tests/test_historical.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_individual_feature_builders.py`|`tests/test_individual_feature_builders.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_jvlinktosqlite.py`|`tests/test_jvlinktosqlite.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_latest.py`|`tests/test_latest.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_main.py`|`tests/test_main.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_make_features.py`|`tests/test_make_features.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_models.py`|`tests/test_models.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_odds_archive.py`|`tests/test_odds_archive.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_project_environment.py`|`tests/test_project_environment.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_read_json.py`|`tests/test_read_json.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_realtime.py`|`tests/test_realtime.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_serialization.py`|`tests/test_serialization.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_setting.py`|`tests/test_setting.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_walk_forward.py`|`tests/test_walk_forward.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
|`src/tests/test_weekly_progress.py`|`tests/test_weekly_progress.py`|既存ファイルと全検証を維持。import/patch先を新所有先へ更新し、必要な回帰を追加。|
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

以下は現行src全Pythonファイルとconfig全TOMLファイルを省略せず列挙する。
package宣言も記録し、存在しない将来用model設定は含めない。

|ファイル|責務|
|---|---|
|`src/cli/__init__.py`|Command-line boundaries grouped by functional responsibility.|
|`src/cli/jra_van_retriever.py`|Validate retrieval options and execute acquisition commands.|
|`src/cli/json_io.py`|Translate generic JSON input and output failures at the CLI boundary.|
|`src/cli/make_datamart.py`|Build a datamart from explicitly ordered intermediate Parquet inputs.|
|`src/cli/make_features.py`|Execute explanatory-variable generation at the command-line boundary.|
|`src/cli/models.py`|Execute model input audits, projection and walk-forward evaluation.|
|`src/cli/options.py`|Define option types shared by data retrieval and preprocessing CLIs.|
|`src/cli/preprocessor.py`|Execute processed-data publication and report command results.|
|`src/configuration/__init__.py`|Configuration responsibilities.|
|`src/configuration/data_paths.py`|Load filesystem paths shared by race-data workflows.|
|`src/configuration/loader.py`|Read TOML without applying feature-specific configuration contracts.|
|`src/configuration/path_resolver.py`|Resolve explicitly configured paths beside their configuration file.|
|`src/data/__init__.py`|Common data I/O, transformation and snapshot lifecycle boundaries.|
|`src/data/loader/__init__.py`|Data loader responsibilities.|
|`src/data/loader/processed_data_loader.py`|Public processed-data loading facade.|
|`src/data/loader/read_json.py`|Read UTF-8 JSON objects without CLI or feature-specific validation.|
|`src/data/loader/read_parquet.py`|Read Parquet files and bounded batches without storage-version policy.|
|`src/data/loader/read_sqlite.py`|Read raw SQLite tables through one read-only transaction.|
|`src/data/preprocessor/__init__.py`|Pure transformations of raw source values.|
|`src/data/preprocessor/sqlite_to_arrow.py`|Convert SQLite-derived values to the existing all-string Arrow contract.|
|`src/data/saver/__init__.py`|Data saver responsibilities.|
|`src/data/saver/write_json.py`|Write JSON-compatible values as standard UTF-8 JSON.|
|`src/data/saver/write_parquet.py`|Write explicit Arrow tables or batches to Parquet files.|
|`src/data/storage/__init__.py`|Storage responsibilities.|
|`src/data/storage/snapshot_builder.py`|Build processed snapshots from one consistent raw SQLite observation.|
|`src/data/storage/snapshot_publisher.py`|Publish completed processed versions with an atomic CURRENT replacement.|
|`src/data/storage/snapshot_store.py`|Own processed snapshot layout and CURRENT version resolution.|
|`src/domain/__init__.py`|Shared domain values independent of data boundaries.|
|`src/domain/race_key.py`|Shared race identity used across retrieval, preprocessing, and loading.|
|`src/jra_van_retriever/__init__.py`|Jra van retriever responsibilities.|
|`src/jra_van_retriever/acquisition/__init__.py`|Acquisition responsibilities.|
|`src/jra_van_retriever/acquisition/acquisition_lock.py`|Serialize application acquisition and bind one raw database to its ledger.|
|`src/jra_van_retriever/acquisition/jvlink_runner.py`|Run the local JVLinkToSQLite executable for race-data acquisition.|
|`src/jra_van_retriever/acquisition/odds_archive.py`|Persist JVLinkToSQLite realtime odds tables without changing their schema.|
|`src/jra_van_retriever/acquisition/setting_xml.py`|Generate execution XML from typed JVLink profiles.|
|`src/jra_van_retriever/config/__init__.py`|Config responsibilities.|
|`src/jra_van_retriever/config/profiles.py`|Convert declarative acquisition profiles into validated settings.|
|`src/jra_van_retriever/config/validation.py`|Validate JVLink-specific TOML values without reading files.|
|`src/jra_van_retriever/contracts/__init__.py`|Contracts responsibilities.|
|`src/jra_van_retriever/contracts/odds.py`|Define the shared raw O1/O2 tables and complete race-key columns.|
|`src/jra_van_retriever/parsing/__init__.py`|Parsing responsibilities.|
|`src/jra_van_retriever/parsing/race_key.py`|Convert raw race-key rows at the retrieval boundary.|
|`src/jra_van_retriever/progress/__init__.py`|Progress responsibilities.|
|`src/jra_van_retriever/progress/ledger.py`|Persist and validate the authoritative historical odds progress ledger.|
|`src/jra_van_retriever/progress/output.py`|Regenerate historical-odds JSON and TOML reports from committed progress.|
|`src/jra_van_retriever/progress/raw_observation.py`|Observe raw acquisition data and close readers before external writes.|
|`src/jra_van_retriever/progress/state.py`|Define acquisition values and calculate progress without persistence.|
|`src/jra_van_retriever/retriever.py`|Provide the public orchestration API for JRA-VAN race-data retrieval.|
|`src/jra_van_retriever/workflows/__init__.py`|Workflows responsibilities.|
|`src/jra_van_retriever/workflows/historical_basic.py`|Retrieve historical base race data through JVLinkToSQLite.|
|`src/jra_van_retriever/workflows/historical_odds.py`|Coordinate bounded historical odds batches and their lifecycle owners.|
|`src/jra_van_retriever/workflows/historical_odds_legacy.py`|Acquire historical odds for the existing combined Python retrieval API.|
|`src/jra_van_retriever/workflows/historical_odds_plan.py`|Plan year-scoped odds work from raw and committed ledger observations.|
|`src/jra_van_retriever/workflows/historical_odds_publication.py`|Publish raw-complete historical odds under the common acquisition lock.|
|`src/jra_van_retriever/workflows/historical_odds_recovery.py`|Preserve interrupted acquisition evidence before resetting staging.|
|`src/jra_van_retriever/workflows/historical_odds_request.py`|Execute and classify one durable historical odds acquisition request.|
|`src/jra_van_retriever/workflows/latest.py`|Retrieve the latest race-data changes through JVLinkToSQLite.|
|`src/jra_van_retriever/workflows/realtime.py`|Retrieve prediction-time odds for one target race through JVLinkToSQLite.|
|`src/main.py`|Assemble, register and start the keiba-ai command-line interface.|
|`src/make_datamart/__init__.py`|Datamart construction from feature intermediate tables.|
|`src/make_datamart/builder.py`|Join validated feature tables into an ordered datamart without I/O.|
|`src/make_datamart/tables/__init__.py`|Datamart schema contracts and explicit persistence.|
|`src/make_datamart/tables/parquet.py`|Persist and reload validated datamart Parquet tables.|
|`src/make_datamart/tables/schema.py`|Declare and decode datamart columns and persisted metadata.|
|`src/make_datamart/validation/__init__.py`|Datamart schema and row validation.|
|`src/make_datamart/validation/table.py`|Validate datamart schemas, keys, timestamps and missing values.|
|`src/make_features/__init__.py`|Feature-specific generation, validation and table contracts.|
|`src/make_features/basic_conditions_and_weight.py`|Build the basic conditions and weight intermediate feature rows and tables.|
|`src/make_features/catalog/__init__.py`|Load and bind declarative feature registrations.|
|`src/make_features/catalog/loader.py`|Read the declarative feature catalog without importing implementations.|
|`src/make_features/catalog/registry.py`|Bind validated feature definitions to explicitly registered implementations.|
|`src/make_features/condition_adjusted_ability.py`|Build the condition adjusted ability intermediate feature rows and tables.|
|`src/make_features/condition_suitability.py`|Build the condition suitability intermediate feature rows and tables.|
|`src/make_features/contracts/__init__.py`|Declare feature inputs and middle rows.|
|`src/make_features/contracts/rows.py`|Represent normalized feature middle rows without storage dependencies.|
|`src/make_features/contracts/types.py`|Explicit feature inputs and structured validation results.|
|`src/make_features/expected_race_development.py`|Build the expected race development intermediate feature rows and tables.|
|`src/make_features/explanatory_variables.py`|Build explanatory-variable middle rows through their individual modules.|
|`src/make_features/generation/__init__.py`|Share audited row generation.|
|`src/make_features/generation/base.py`|Share feature-row generation and validated Arrow table construction.|
|`src/make_features/generation/normalization.py`|Normalize audited explicit feature inputs into the common middle-row type.|
|`src/make_features/hill_and_wood_workouts.py`|Build the hill and wood workouts intermediate feature rows and tables.|
|`src/make_features/history_volume_and_missingness.py`|Build the history volume and missingness intermediate feature rows and tables.|
|`src/make_features/jockey_combination.py`|Build the jockey combination intermediate feature rows and tables.|
|`src/make_features/jockey_performance.py`|Build the jockey performance intermediate feature rows and tables.|
|`src/make_features/market_characteristics.py`|Build the market characteristics intermediate feature rows and tables.|
|`src/make_features/odds_ratio.py`|Build the explicit-odds-ratio intermediate feature table.|
|`src/make_features/opponent_pagerank.py`|Build the opponent pagerank intermediate feature rows and tables.|
|`src/make_features/past_body_weight.py`|Build the past body weight intermediate feature rows and tables.|
|`src/make_features/past_lap_and_running_style.py`|Build the past lap and running style intermediate feature rows and tables.|
|`src/make_features/past_racing_ability.py`|Build the past racing ability intermediate feature rows and tables.|
|`src/make_features/pedigree.py`|Build the string-valued pedigree intermediate feature table.|
|`src/make_features/pedigree_suitability.py`|Build the pedigree suitability intermediate feature rows and tables.|
|`src/make_features/previous_race_result.py`|Build the previous-race-result intermediate feature table.|
|`src/make_features/recent_performance.py`|Build the recent performance intermediate feature rows and tables.|
|`src/make_features/recent_stability.py`|Build the recent stability intermediate feature rows and tables.|
|`src/make_features/rest_and_condition_change.py`|Build the rest and condition change intermediate feature rows and tables.|
|`src/make_features/running_style_and_position.py`|Build the running style and position intermediate feature rows and tables.|
|`src/make_features/same_gate_and_trainer_relative.py`|Build the same gate and trainer relative intermediate feature rows and tables.|
|`src/make_features/serialization/__init__.py`|Convert feature contracts to and from JSON-compatible values.|
|`src/make_features/serialization/inputs.py`|Convert decoded JSON objects into feature group input contracts.|
|`src/make_features/serialization/outputs.py`|Convert feature generation results and audits to JSON-ready values.|
|`src/make_features/tables/__init__.py`|Build and persist registered feature tables.|
|`src/make_features/tables/build.py`|Construct intermediate tables from normalized feature rows.|
|`src/make_features/tables/parquet.py`|Persist and reload validated intermediate feature tables.|
|`src/make_features/tables/schema.py`|Declare and resolve registered intermediate feature schemas.|
|`src/make_features/trainer_performance.py`|Build the trainer performance intermediate feature rows and tables.|
|`src/make_features/validation/__init__.py`|Validate feature evidence and tables.|
|`src/make_features/validation/audit.py`|Audit race shape and coordinate shared feature validation.|
|`src/make_features/validation/availability.py`|Normalize and validate explicitly supplied feature timestamps.|
|`src/make_features/validation/groups.py`|Validate feature scalars, missingness, status and source evidence.|
|`src/make_features/validation/leakage.py`|Reject target-result columns and references to future outcomes.|
|`src/make_features/validation/table.py`|Validate feature table schemas, keys and availability.|
|`src/make_features/validation/values.py`|Check scalar values and missingness without changing data.|
|`src/make_features/within_race_relative.py`|Build the within race relative intermediate feature rows and tables.|
|`src/models/__init__.py`|Race-ranking model primitives for the LambdaRank MVP.|
|`src/models/artifacts/__init__.py`|Artifacts responsibilities.|
|`src/models/artifacts/native_model.py`|Publish, validate, and recover native model artifacts as one complete set.|
|`src/models/backends/__init__.py`|Backends responsibilities.|
|`src/models/backends/lightgbm.py`|Connect validated model inputs to the lazily imported LightGBM backend.|
|`src/models/dataset/__init__.py`|Dataset responsibilities.|
|`src/models/dataset/availability.py`|Audit feature values at their explicit freeze timestamps.|
|`src/models/dataset/builder.py`|Construct validated prediction rows and labeled ranking datasets.|
|`src/models/dataset/dataset.py`|Hold a validated race-contiguous ranking dataset.|
|`src/models/dataset/rows.py`|Immutable model input rows and numeric value types.|
|`src/models/dataset/schema.py`|Own the approved model feature schema and semantic metadata.|
|`src/models/dataset/validation.py`|Validate and normalize model rows, labels and race groups.|
|`src/models/evaluation/__init__.py`|Evaluation responsibilities.|
|`src/models/evaluation/metrics.py`|Race-level ranking metrics for the LambdaRank MVP.|
|`src/models/evaluation/walk_forward.py`|Race-level chronological walk-forward splitting and evaluation.|
|`src/models/predict_model.py`|Preserve the existing prediction import entry point.|
|`src/models/ranking/__init__.py`|Ranking responsibilities.|
|`src/models/ranking/ranker.py`|Score feature rows and assign deterministic race-local ranks.|
|`src/models/ranking/rules.py`|Define fixed ranking contracts and pure race grouping and ordering rules.|
|`src/models/serialization/__init__.py`|Convert model contracts to and from JSON-compatible values.|
|`src/models/serialization/inputs.py`|Convert decoded JSON objects into model feature input contracts.|
|`src/models/serialization/outputs.py`|Convert model features, audits, and evaluations to JSON-ready values.|
|`src/models/training/__init__.py`|Training responsibilities.|
|`src/models/training/train.py`|Training entry point for the LambdaRank MVP.|
|`src/tests/test_cli_boundaries.py`|Tests for CLI composition, independent imports and shared input contracts.|
|`src/tests/test_configuration.py`|Tests for shared physical TOML loading and path resolution.|
|`src/tests/test_data_pipeline.py`|Tests for raw SQLite preprocessing and processed Parquet loading.|
|`src/tests/test_data_retriever.py`|Tests for the public race-data retrieval facade.|
|`src/tests/test_datamart.py`|Tests for ordered datamart joins of intermediate feature tables.|
|`src/tests/test_explanatory_variables.py`|Tests for the explicit F01-F21 explanatory-variable boundary.|
|`src/tests/test_feature_catalog.py`|Verify declarative registrations reach audit, generation and saved contracts.|
|`src/tests/test_feature_tables.py`|Tests for feature-specific intermediate tables.|
|`src/tests/test_features.py`|Tests for temporal feature construction and availability auditing.|
|`src/tests/test_historical.py`|Tests for historical race and odds retrieval orchestration.|
|`src/tests/test_individual_feature_builders.py`|Verify individual builders share middle rows, source audits and table storage.|
|`src/tests/test_jvlinktosqlite.py`|Tests for the local JVLinkToSQLite subprocess boundary.|
|`src/tests/test_latest.py`|Tests for latest-data retrieval orchestration.|
|`src/tests/test_main.py`|Tests for the Typer data CLI.|
|`src/tests/test_make_features.py`|Tests for feature execution JSON serialization.|
|`src/tests/test_models.py`|Focused tests for the LambdaRank ranking MVP.|
|`src/tests/test_odds_archive.py`|Tests for cumulative archiving of transient JVLinkToSQLite odds tables.|
|`src/tests/test_project_environment.py`|Smoke tests for the non-package bootstrap environment.|
|`src/tests/test_read_json.py`|Tests for the reusable UTF-8 JSON object loader.|
|`src/tests/test_realtime.py`|Tests for prediction-time realtime odds retrieval.|
|`src/tests/test_serialization.py`|Tests for reusable feature and model JSON contract conversion.|
|`src/tests/test_setting.py`|Tests for declarative JVLinkToSQLite setting generation.|
|`src/tests/test_walk_forward.py`|Tests for race-level chronological walk-forward evaluation.|
|`src/tests/test_weekly_progress.py`|Tests for isolated weekly progress bootstrap and reconciliation.|
|`config/data.toml`|共有raw/processed/runtimeパス宣言。|
|`config/features.toml`|特徴量ID・名前・登録順の宣言。|
|`config/jvlink.toml`|取得profile・DataSpec・期間の宣言。|

## 最終の対象ディレクトリ構成（全ファイル）

対象はsrcとconfig。生成キャッシュ・取得データ・仮想環境を除き全ファイルを示す。

```text
config/
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
│   ├── test_cli_boundaries.py
│   ├── test_configuration.py
│   ├── test_data_pipeline.py
│   ├── test_data_retriever.py
│   ├── test_datamart.py
│   ├── test_explanatory_variables.py
│   ├── test_feature_catalog.py
│   ├── test_feature_tables.py
│   ├── test_features.py
│   ├── test_historical.py
│   ├── test_individual_feature_builders.py
│   ├── test_jvlinktosqlite.py
│   ├── test_latest.py
│   ├── test_main.py
│   ├── test_make_features.py
│   ├── test_models.py
│   ├── test_odds_archive.py
│   ├── test_project_environment.py
│   ├── test_read_json.py
│   ├── test_realtime.py
│   ├── test_serialization.py
│   ├── test_setting.py
│   ├── test_walk_forward.py
│   └── test_weekly_progress.py
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
