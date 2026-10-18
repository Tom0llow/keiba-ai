# ADR-025: データ基盤を集約しCLIの共通契約と登録を分離する

- Status: Accepted
- Date: 2026-10-18
- Decision Owners: Repository maintainers
- Supersedes: ADR-024（データ基盤とCLI共通処理・登録の配置判断のみ）
- Superseded by: N/A

## Context

PR #21のHEAD `8053ea8fa3027109c5082612b0689e169f5030c4`では、データの物理I/O、
純粋変換、保存構造と公開は分離済みだがsrc直下の4packageに分散している。
CLIの共通オプションとJSON境界はcli_commonに混在し、取得CLIが他CLIのprivate factory、
特徴量CLIが登録のためにモデルCLIへ依存している。今回の明示要件は構成と依存の整理であり、
業務計算、公開CLI、保存形式、異常時の契約を変更しない。

## Decision

1. 共通データ基盤をdata/loader、data/preprocessor、data/saver、data/storageへ集約する。
   configurationとルートconfigは維持し、4群の既存責務と公開シンボルを新所有先へ移す。
   DataPreprocesser互換aliasも維持する。旧importのshimやFacadeは追加しない。
2. cli/options.pyはDataConfigOptionとJVLinkConfigOptionだけを所有する。
   cli/json_io.pyは汎用JSONのCLI例外変換・エラーpayload・終了処理を公開関数として所有し、
   物理I/Oはdata.loader/saverへ委譲する。機能固有スキーマやDatamartエラーは移さない。
3. 機能CLIはjra_van_retriever.py、preprocessor.py、make_features.py、make_datamart.py、
   models.pyとする。cli_common.pyと旧cli_接頭辞ファイルは廃止する。
4. 取得・前処理CLIはSnapshotBuilder.from_toml公開APIを直接利用する。
   他CLIのprivate factoryへの依存と不要なfactoryを削除する。
5. Typerの登録はmainだけが所有する。main.register_feature_commandsは同じ3コマンドを
   同じ順序で登録する公開組立APIとしてmainで維持し、特徴量CLIからモデルCLIへの登録依存を解消する。

## Rationale

dataを機能単位の共通基盤とし、その内側では既に分離したI/O・変換・状態の責務を保持する。
CLIの依存を機能ごとの業務APIと共通契約へ向けることで、独立した機能CLIのimportや登録を
他機能の実装に結びつけない。公開JSON関数による共有はprivateな機能間結合を解消する。

## Consequences

内部import、mock/monkeypatch先、現行文書の参照は新配置へ移行する。
DataLoader/SQLiteReader/SnapshotBuilder/SnapshotStoreのAPI、単一SQLite読取取引、バッチ・schema、
完成版公開、原子的CURRENT、公開失敗時の旧版保持、レース別保存、LightGBM遅延読込を継承する。
CLI名、登録順、引数・既定値・help、stdout/stderr、JSON/Parquet、例外・終了コード、
取得ロック・台帳・復旧・公開順序も維持する。ADR-024の過去の理由本文は変更しない。

## Alternatives Considered

移設だけではCLI間の不要な依存が残る。共通基底クラス、汎用Facade、動的登録、旧importの
一律shimは今回の責務整理に必要ないため追加しない。

## Validation / Follow-up

既存全テストを維持し、CLI登録の欠落・重複、共通JSON例外と公開関数、独立機能importを検証する。
変更前後のCLI照合、データ基盤回帰、Ruff、mypy、pytest、ガード回帰の実行結果を
docs/refactoring-pr21-data-cli.mdへ記録する。旧新対応と現行全対象ツリーも文書化する。
