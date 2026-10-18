# ADR-024: 機能ごとの処理と共通基盤の責務を分離する

- Status: Accepted
- Date: 2026-10-18
- Decision Owners: Repository maintainers
- Supersedes: ADR-008（raw SQLite readerとpreprocessing/loadingのモジュール配置判断のみ）、ADR-021（共有設定配置とDatamart入出力配置）、ADR-022（全CLIのmain集中配置）、ADR-023（旧モジュール配置とCLI配置）
- Superseded by: N/A

## Context

PR #21への追加要件では、src全体を機能単位、その内部を責務単位に整理し、
設定の物理読込、汎用I/O、変換、スナップショットの保存構造と公開を分離する。
既存のCLI、計算、型検証、ロック・台帳・復旧順序、保存形式は維持する必要がある。

## Decision

共通TOML読込とパス解決はconfiguration、汎用物理I/Oはdata_loader/data_saver、
SQLite値の純粋変換はdata_preprocessor、スナップショット統括・構造・公開はstorageに置く。
configurationは機能設定に依存しない。機能固有の設定検証は所有機能に残す。
ADR-008のraw readerをpreprocessing配下に限定しloaderへのSQLite配置を拒否した判断は、
今回の明示要件により置き換える。data_loader/read_sqliteは生成工程の汎用物理readerであり、
モデル向けDataLoaderは引き続きParquetだけを読む。ADR-008の保存構造、単一SQLite読取の一貫性、
完成版だけの公開、原子的CURRENT、公開失敗時の旧版保持、レース別公開契約は全て継承する。

取得処理はjra_van_retrieverのworkflows/acquisition/progress/config/contracts/parsing、
特徴量はmake_features、モデルはdataset/ranking/training/backends/evaluation/artifactsに分離する。
Datamart builderは純粋結合のみを所有し、ファイル入力からの構築はtables/parquetで組み立てる。
CLI処理はcli内の機能別モジュールへ移し、mainは組立・登録・起動に限定する。

旧の公開クラス・関数名とパッケージ公開APIは新所有先で維持する。
README・既存テストで利用される公開APIを根拠とし、旧内部モジュールの一律互換ファイルは残さない。
元からあるmodels/predict_model.pyの2名再公開だけは、既存の明示的な互換入口として維持する。
旧HistoricalRetrieverの統合入口はretriever.pyに移し、baseと旧オッズの実処理は専有workflowへ分ける。
Datamartのpackage公開5名は維持し、旧builder直importのファイルAPIはtables/parquetへ移す。
これにより純粋builderとファイル境界間の循環を防ぐ。
RankingModel.save/loadは利用中の公開契約として成果物所有者への委譲を残す。
モデル設定の外部化や未使用の将来用モジュールは追加しない。

## Rationale

物理I/Oの所有者を一意にすると、機能のmetadata検証と原子的公開を保ったまま重複を減らせる。
単一SQLite読取トランザクションと既存のロック・台帳更新順序を保持して、分割に伴う整合性低下を避ける。
関数は純粋処理、クラスは資源や状態の所有に利用する。

## Consequences

内部importとテストのpatch先は新所有先へ変わる。旧settings/utilsは廃止する。
既存の設定値、特徴量定義・登録順（独自IDを含む）、LightGBM遅延読込、保存形式、
異常時のfail-closed契約は変更しない。全件の対応と最終構成はdocs/refactoring-pr21.mdに記録する。

## Alternatives Considered

ディレクトリ移動のみでは責務の混在が残る。汎用Facadeや基底クラスの追加は
既存関数で十分な処理に抽象化を増やすため採用しない。

## Validation / Follow-up

既存テストを全て維持し、設定、SQLite一貫性、原子的CURRENT、取得復旧、特徴量、
Datamart、モデル成果物、CLI互換と新Datamart CLIを検証する。
Ruff、mypy、pytest、ガード回帰は実行結果を記録する。
