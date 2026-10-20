# Architecture — keiba-ai

## Status

This repository contains development automation, local JRA-VAN race-data
retrieval, raw-to-processed preprocessing, and Parquet loading for training and
prediction. It remains uninstalled as a Python distribution.

An earlier local prototype is not a source of current requirements or design
authority. Product behavior and durable architectural decisions must come from
an explicit requirement or an Accepted architecture decision record (ADR).

## Current runtime and tooling

- Python: 3.12
- Environment and dependency manager: uv
- Data CLI: Typer
- Formatter and linter: Ruff
- Type checker: mypy
- Test framework: pytest
- Automation: GitHub Actions and guarded PowerShell wrappers

The locked development environment is defined by `pyproject.toml` and `uv.lock`.
The project has no build system, so `uv sync` installs its dependencies without
installing this repository as a Python distribution.

Host-side autonomous Git/GitHub operations run only from hash-verified wrapper
copies installed in the protected Codex user guard store. Every installation
publishes a new immutable directory identified by repository policy ID, source
SHA, and installation ID; earlier immutable directories remain untouched.
`.git/codex-guard/` contains only invocation metadata, and tracked files under
`scripts/` are reviewable sources, not executable trust anchors. A
repository-and-checkout-bound user-layer execution rule permits only the
installed wrappers' absolute paths. The manifest and runtime verification bind
the canonical physical PowerShell, Git, GitHub CLI, and Codex CLI paths and the
approved Codex CLI version. The trusted Codex path is a self-contained native
`codex.exe`; Node launcher shims such as `codex.cmd` and `codex.ps1` are outside
the supported boundary. This boundary also uses a protected system PowerShell
host and an exclusive repository workflow lock as defined by ADR-001.

PR and CI observations are bound to one explicit expected HEAD SHA through
merge readiness and human approval. PR inspection observes the current PR base
object ID as `baseSha`, then creates the complete local binary diff from the
recorded task `startSha` (`diffBaseSha`) through the expected head with external
diff and text conversion disabled. Checks use the check-runs and commit-status
APIs for that expected head. Every observation reports `baseSha` and `headSha`;
PR inspection also reports `diffBaseSha`. Merge readiness is bound to the PR
number and HEAD SHA; rebinding the task to a replacement PR clears prior
readiness and merge-attempt evidence. Merge readiness and the final unmerged-PR
merge path revalidate the protected `main` branch's required contexts, strict
status setting, and GitHub Actions application ID. If the remote merge succeeds
before a communication or cleanup failure, the remaining task state permits
recovery only after the same PR, task HEAD, merge-ready SHA, approved SHA, and
recorded pre-merge attempt and merge timestamp agree. Incomplete cleanup keeps
the guarded task state for an exact-PR/exact-SHA retry. User-layer trust paths
are rejected under both the writable repository and system temporary directory.

Repository-wide verification uses:

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Guard trust-boundary validation runs separately:

```powershell
$invocation = Get-Content -LiteralPath .git/codex-guard/guard-invocation.json -Raw | ConvertFrom-Json
pwsh -NoProfile -File scripts/guard-tests/guard-regression.ps1 `
  -CodexExecutablePath $invocation.codexPath
```

The `Quality` CI job performs that real regression for every allow-listed Codex
CLI version with both PowerShell 7 and Windows PowerShell 5.1.

Task start and commit use write-ahead state under `.git`: an interrupted
operation can be resumed only by invoking the same wrapper with the same
arguments, while unrelated task-state-dependent guarded operations fail closed.

ADR-016 extends this boundary with byte-preserving UTF-8 native execution,
baseline required-check verification, SHA-bound PR metadata updates, and
prompt-gated archival of human-merged tasks. Base updates prepare a conflict-free
merge without touching the index or worktree, reject external merge drivers,
and record pending state before advancing the branch. State version 7 retains
the original `initialStartSha` and advances `startSha` to the verified current
main used as the task diff base. Version 6 remains readable. New HEADs and PR
metadata edits invalidate readiness and require renewed review. Reinstallation
rejects active task state and Store/MSIX PowerShell hosts. Runtime shell startup
and literal argv integration remain separate manual installation checks.

## 現行の機能境界

```text
configs/                        # 既存3 TOMLの値・キーを維持
src/
├─ main.py                      # CLI組立・登録・起動
├─ cli/                         # options/json_ioと機能CLI5ファイル
├─ configuration/               # TOML物理読込・共通パス・DataPaths
├─ data/                        # 共通データ基盤
│  ├─ loader/                   # JSON・Parquet・SQLite物理読込
│  ├─ preprocessor/             # SQLite値からArrowへの純粋変換
│  ├─ saver/                    # JSON・Parquet物理保存
│  └─ storage/                  # snapshot生成・構造・CURRENT・原子的公開
├─ jra_van_retriever/            # 取得とロック・台帳・復旧
├─ make_features/               # 特徴量契約・生成・監査・テーブル
├─ make_datamart/                # 純粋結合・検証・保存契約
├─ models/                      # dataset・ranking・training・backends・evaluation・artifacts
├─ domain/                      # 共有RaceKey
└─ tests/
   ├─ unit/                     # 純粋処理と外部境界mockの分離テスト
   ├─ integration/              # 実ファイル・DB・process・機能接続のテスト
   └─ test_project_environment.py # 既存環境契約の確認
```

全ソースファイルの責務と移行対応、最終全ファイルツリーは
[PR #21リファクタリング記録](docs/refactoring-pr21.md)に記録する。
ADR-024はADR-008とADR-021〜023の配置判断を置換し、既存の計算・保存形式・CLIを維持する。
旧settings/utils/retriever/preprocesser/featuresパッケージは廃止した。
ADR-025がADR-024のデータ基盤とCLI共通処理・登録の配置判断を部分置換する。
data内の4責務と既存保存契約は継承し、configurationは独立したまま維持する。
ADR-026がルート設定のフォルダー名をconfigsへ変更し、src/tests内を分類する。
3 TOMLは内容と相対値を維持し、src/tests/unitとsrc/tests/integrationを既存のpytest・mypyで検査する。
環境確認テストは既存のsrc/tests/test_project_environment.pyに置く。
全件の分類と対応は[設定・テスト移行記録](docs/refactoring-pr21-configs-tests.md)に記録する。

## 設定管理

`configs/data.toml`、`jvlink.toml`、`features.toml`のキー・値・相対パス値は変更しない。
`configuration/loader.py`だけがTOMLを物理読込し、ファイルと解析エラーをそのまま返す。
`path_resolver.py`は非空の文字列、ホーム展開、設定ファイルの親からの相対パス、絶対パスを扱う。
`data_paths.py`は共有のraw SQLite、processed、JVLink runtimeの必須パスを検証してDataPathsを作る。

`jra_van_retriever/config/profiles.py`はJVLinkConfig/JVLinkProfile/HistoricalOddsBatchと
TOMLからの変換、`validation.py`は取得固有の値と期間・DataSpec・モードの検証を所有する。
XML生成は`acquisition/setting_xml.py`が型付きprofileから行い、TOMLを読まない。
`make_features/catalog/loader.py`は共通TOML読込を使い、ID・名前・重複・順序を検証する。
独自の非空IDを受け付ける既存契約も維持し、F01〜F21限定の新制約は導入しない。
実装と定義の対応はcatalog/registry.pyが所有する。

依存は`機能の設定 → configuration → 標準ライブラリ`の一方向である。
configurationは業務機能へ依存しない。暗黙の設定読込、singleton、model設定の新設はない。

## データI/O・変換・スナップショット

データ経路は`JVLinkToSQLite → raw SQLite → SnapshotBuilder → versioned Parquet → DataLoader`。
モデルはraw SQLiteを直接読まない。これはADR-008の保存契約を維持する。

| 所有者 | 責務 |
| --- | --- |
| data/loader/read_sqlite.py | read-only接続と単一取引、表・列の列挙、rowid順のバッチ読込。Arrowと保存を扱わない。 |
| data/preprocessor/sqlite_to_arrow.py | TEXT/DATETIME宣言をnullable stringへ変換し、NULL・先頭ゼロ・列順を保持。I/Oを持たない。 |
| data/saver/write_parquet.py | 明示Arrow schema/table/batchの物理保存。空表もschemaを保存する。 |
| data/loader/read_parquet.py | 明示Parquetパスのtable/metadata/RecordBatchの物理読込。CURRENTを扱わない。 |
| data/storage/snapshot_builder.py | 読込・変換・保存・保存結果照合・完成版公開を統括。DataPreprocesserのAPI名も維持する。 |
| data/storage/snapshot_store.py | complete/race別保存構造、versionパス、CURRENT解決、表パスの所有。 |
| data/storage/snapshot_publisher.py | stagingの完成版rename後、os.replaceでCURRENTを原子的に更新する。 |
| data/loader/processed_data_loader.py | DataLoader公開API。Storageから選択パスを取得し、物理readerへ渡す。 |
| data/loader/read_json.py / data/saver/write_json.py | UTF-8 JSON object読込と、NaNをnullへ変換する汎用JSON保存。 |

完全snapshotの全表を一つのSQLite読取取引内で処理する。バッチは最大65,536行、
目安1,000,000セルを列数で割った従来の上限を維持する。保存後のrow countとschemaを照合する。
列がrowidを隠す場合は_rowid_/oidへ順にフォールバックし、利用不能なら失敗する。

完全版は`data/processed/snapshots/<id>/`、ポインタは`data/processed/CURRENT`。
レース別は`data/processed/realtime/<race-id>/versions/<id>/`と同階層のCURRENTを使用する。
対象RaceKeyのO1/O2 archiveをフィルタし、両方の生成・検証成功後にだけ切り替える。
変換や公開の失敗では旧CURRENTを維持する。公開されなかった完成版の保持も従来通りである。
DataLoader.iter_batchesは最初の反復までパスを解決せず、batch_sizeを先に検証する。

Reader/Converter/WriterはStorage生成処理へ依存しない。DataLoaderだけが読込APIの組立として
SnapshotStoreへ依存する。各packageの__init__は下位から上位への暗黙依存を作らない。

## 取得・進捗・復旧

`jra_van_retriever/retriever.py`のJraVanRetrieverはhistorical-basic/historical-odds/latest/realtimeを
構成する。既存のDataRetriever名も同じクラスを指す。workflowsはモードごとの処理順序を所有する。
acquisitionはshellを使わないJVLinkToSQLite subprocess、raw DBのOSロック、O1/O2 archiveとXML生成を所有する。
credentialsをリポジトリへ読み込まず、ローカルのJV-Link環境を利用する。

historical-basicはbase profileだけを取得して完全版を公開する。
workflows/historical_basic.pyはbase専用とし、旧の非週次オッズ取得・skip-existingは
historical_odds_legacy.pyへ分離した。既存HistoricalRetrieverとretrieve_historicalの統合入口だけを
retriever.pyへ残し、元と同じ一時ディレクトリ内のbase→DB存在確認→odds順序を維持する。
latestは初回にseedからruntime XMLを作り、以降はruntime XMLを再利用し、seedを変更しない。
realtimeはhistoryの0B41/0B42を取得・archive後にcurrentの0B31/0B32を取得・archiveし、
一時XMLとskip-last-modified-updateを使用する。archiveは原列・順序を維持し、全行による重複排除を行う。

週次historical-oddsは次の所有者をCompositionで利用する。

| モジュール | 責務 |
| --- | --- |
| workflows/historical_odds.py | 共通ロックと年単位batchの順序・metrics・外部API互換委譲。 |
| historical_odds_plan.py | committed台帳の参照、純粋な年・レース選択、書込を行わない計画。 |
| historical_odds_request.py | request intent確定、XML/実行/archive、結果分類、要求結果確定。 |
| historical_odds_recovery.py | runner停止確認、staging隔離証拠の記録後のreset。 |
| historical_odds_publication.py | 同じロック内で完全性を再照合し、callback後に公開状態と派生報告を更新。 |
| progress/ledger.py | 台帳取引、旧版移行、所有権、取得証拠とAPI return codeの永続化。 |
| progress/state.py | 値型と純粋な突合。 |
| progress/raw_observation.py | raw観測と接続を閉じた結果。 |
| progress/output.py | 台帳確定後の派生JSON/TOML。取得・復旧の判断元にはしない。 |
| contracts/odds.py / parsing/race_key.py | オッズ表・キー列の契約と、raw行から共有RaceKeyへの純粋変換。 |

ロックbind → 必要時runner停止確認 → raw観測 → 旧台帳移行 → staging隔離証拠記録 → reset →
復旧確定 → 再観測 → bootstrap/reconcile → 要求開始確定 → 実行/archive →
失敗隔離/成功reset → 要求結果確定 → run確定 → 派生報告の順序を維持する。
未解決要求は全取得モードでfail-closedとし、復旧なしの書込を拒否する。

台帳は完全RaceKeyとDataSpecをキーとし、初期archive欠損をpendingとする。
captured JVOpen/JVRTOpen=-1だけを自動provider_missingとし、証拠なし空応答はfailedで停止する。
旧状態移行、API名/コード列追加、明示確認も従来通り。raw完了年を順に取得し、全管理年の完了後に
一度の完全Parquet公開を行う。callback失敗ではfailedを確定し、raw/台帳を次回へ残す。

## 特徴量とDatamart

make_featuresの個別モジュールは入力型、計算、固有検証・正規化を所有する。
既存のFeatureBuilder/RegisteredFeatureBuilder、共通FeatureTableRow、F01〜F21の計算と監査順序を維持する。
catalogは定義と登録、contractsは型、generationは共通手順、serializationは純粋JSON変換、
validationは漏洩・時点・値・表の監査、tablesはArrow構築と保存metadataの契約を所有する。
未承認の業務式、JRA-VANコード解釈、履歴集計を追加しない。

元のprevious_race_result/odds_ratio/pedigreeの固定列・metadataを維持する。
その他の表は明示registered_namesとscalar column_types、保存metadataの整合性を要求する。
データの物理Parquet読書きは共通reader/writerに委譲し、各機能が保存前・読込後の検証を続ける。

make_datamart/builder.pyは入力tableの純粋な順序付き左結合だけを実装する。
先頭表のキーと順序、欠損、feature別available_at、freeze_at、重複と列衝突の規則は変えない。
tables/schema.pyが列・metadata、validation/table.pyが表固有検証、tables/parquet.pyが
ファイルからの構築APIと保存・読込契約を所有する。packageの5公開名は維持する。
旧builderのファイルAPIはtables/parquetへ移し、循環importや互換Facadeを残さない。

## モデル

modelsのpackage公開名、学習値・既定値、score/rankだけを返す推論、保存形式を維持する。

| 所有者 | 責務 |
| --- | --- |
| dataset/rows.py | 数値値型、FeatureInput、FeatureRow、RankingRow。 |
| dataset/schema.py | FeatureSpec/FeatureSchemaと承認済みallow-list、結果由来名の拒否、metadata。 |
| dataset/validation.py | 値・ラベル・行キー・連続race・groupの検証と行の正規化。 |
| dataset/dataset.py | 検証済みRankingDatasetの不変条件、from_rowsと行列API。 |
| dataset/availability.py | freeze/available時刻、timezone、欠損保持の監査と違反型。 |
| dataset/builder.py | 明示入力の投影、行生成、学習dataset構築。 |
| ranking/ranker.py / rules.py | 有限scoreとrace内順位、同点規則と固定学習契約。 |
| training/train.py | 検証済みdatasetからのLambdaRank学習。 |
| backends/lightgbm.py | LightGBMの遅延import、native接続、学習adapter。 |
| evaluation/metrics.py / walk_forward.py | NDCG@3・Top1・Top3、race単位の時系列分割と評価。 |
| artifacts/native_model.py | native model/JSON metadataの保存・検証・原子的公開・復旧。 |
| serialization/inputs.py / outputs.py | model専用の純粋JSON契約変換。 |

ラベルは1着3/2着2/3着1/他0、gainは0/1/3/7、groupはrace内行数とする。
allow-listはability/historical_oddsで、欠損値やNaNを保持し、最終オッズで補完しない。
RankingModel.save/loadは利用中のAPIとしてNativeModelArtifactへ委譲し、成果物処理を複製しない。
既存models/predict_model.pyは元からある互換入口として新rankerの2名を再公開する。
feature/model serializationはI/O・Typerへ依存せず、モデル設定の外部化は導入しない。

## CLI

main.pyはTyperの組立・登録・起動だけを行う。cli/options.pyとcli/json_io.pyは共通option、JSON境界、構造化エラー、
各機能CLIは対応機能の引数検証、実行、表示と終了を所有する。下位機能はCLIやTyperをimportしない。
importとhelpは設定や入力を読まず、取得資源を作らない。

既存の取得flags、preprocess/modelコマンド、引数・文言・stdout/stderr・終了コードを維持する。
main.register_feature_commandsは既存の公開登録APIとしてmainで実装する。
cli/options.pyがDataConfigOption/JVLinkConfigOption、cli/json_io.pyが公開のread_json_object/
parse_json_inputs/input_error_payload/exit_input_errorを所有する。CLI固有スキーマは各機能に残す。
取得・前処理CLIはSnapshotBuilder.from_tomlを直接呼び、他CLIのprivate factoryを参照しない。
機能CLIはjra_van_retriever.py/preprocessor.py/make_features.py/make_datamart.py/models.pyとし、
機能同士を登録のためにimportしない。Typer登録は全てmainが所有する。
新規datamart buildはrepeatable --input、--output、既定configs/features.tomlの--features-configを受け、
定義名のみを読み、既存のファイル構築・保存APIへ渡す。失敗はstderr/終了1、成功は行数をstdoutへ出す。
CLIは出力先がいずれかの入力と同じファイルを指す場合、相対パス表記やリンクが異なっても保存前に拒否する。

## 進化時の制約

import時のI/O、循環依存、不要なFacade、将来用の空設定・依存は追加しない。
公開API・保存形式・セキュリティ境界の変更は影響を整理し、長期判断をADRに残す。
実装されていない履歴集計・nested選定・train/predict CLI・購入判断を現行機能としない。
