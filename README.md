# keiba-ai

Python 3.12 project with local JRA-VAN race-data retrieval, raw-to-Parquet
preprocessing, processed-data loading, and an AI-driven development foundation.

## Current status

The repository contains the Claude Code + Codex development workflow, a local JRA-VAN data
retrieval boundary through JVLinkToSQLite, versioned Parquet publication, and a
Parquet-only loader boundary. It remains a non-distributed Python project.

```text
configs/                        # 既存3 TOMLとHydra実験YAML
src/
├─ main.py                      # CLI組立・登録・起動
├─ cli/                         # options/json_ioと機能別CLI
├─ configuration/               # TOML・共通パス・DataPaths・Hydra実験設定
├─ data/                        # 共通データ基盤
│  ├─ loader/                   # JSON・Parquet・SQLite物理読込
│  ├─ preprocessor/             # SQLite値からArrowへの純粋変換
│  ├─ saver/                    # JSON・Parquet物理保存
│  └─ storage/                  # snapshot生成・構造・CURRENT・原子的公開
├─ jra_van_retriever/            # 取得とロック・台帳・復旧
├─ make_features/               # 特徴量契約・生成・監査・テーブル
├─ make_datamart/                # 純粋結合・検証・保存契約
├─ models/                      # dataset・ranking・training・backends・evaluation・artifacts・experiments
├─ domain/                      # 共有RaceKey
└─ tests/
   ├─ unit/                     # 純粋処理と外部境界mockの分離テスト
   ├─ integration/              # 実ファイル・DB・process・機能接続のテスト
   └─ test_project_environment.py # 既存環境契約の確認
```

The project has no build system. `uv sync` installs its locked dependencies
without installing this repository as a Python distribution.

データ契約はADR-005〜008、特徴量登録はADR-020に従う。
[ADR-024](docs/decisions/ADR-024-separate-functional-responsibilities.md)が
ADR-008とADR-021〜023の配置判断を置き換えた責務分離を継承する。
[ADR-025](docs/decisions/ADR-025-group-data-and-separate-cli-contracts.md)によりデータ基盤をdataへ集約し、CLI共通契約と登録の依存を整理した。
全ファイルの最終構成、旧配置の対応表、責務と互換性は
[PR #21リファクタリング記録](docs/refactoring-pr21.md)と
[データ基盤・CLI移行記録](docs/refactoring-pr21-data-cli.md)を参照する。
[ADR-026](docs/decisions/ADR-026-rename-configs-and-classify-tests.md)に従うconfigsへの改名とsrc/tests内の分類、
全テストの分類・旧新対応は[設定・テスト移行記録](docs/refactoring-pr21-configs-tests.md)に記録する。

## Data flow

All data paths converge on one storage dependency direction:

```text
JV-Link
  -> JVLinkToSQLite
  -> data/raw/race.db
  -> DataPreprocesser
  -> Parquet
  -> DataLoader
  -> training / analysis / prediction
```

`race.db` is the mutable raw acquisition store. Model-facing code does not read
it directly. SQLiteの読取取引は`src/data/loader/read_sqlite.py`、純粋変換は
`src/data/preprocessor/sqlite_to_arrow.py`、生成と公開は`src/data/storage/`が所有する。

`src/data/loader/read_parquet.py` reads processed Parquet only. The separate
`read_json.py` reads explicit JSON inputs without feature or model validation.

Storage paths are configured in `configs/data.toml`:

```toml
[paths]
raw_db = "../data/raw/race.db"
processed_dir = "../data/processed"
jvlink_runtime_dir = "../data/runtime/jvlink"
```

## Race data retrieval

Race data is acquired through a locally installed JVLinkToSQLite executable.
JV-Link and JVLinkToSQLite must already be installed and configured on Windows.
The Python code does not call JV-Link COM directly and does not store the
JRA-VAN service key.

The user-owned `C:\JVLinkToSQLite\setting.xml` is treated as a seed. Retrieval
behavior is declared in `configs/jvlink.toml`, and Python generates execution XML
for historical-basic, historical-odds, latest, and realtime modes.

Important profiles include:

```toml
[historical_odds]
realtime_data_specs = ["0B41", "0B42"]
race_start_date = 2003-10-04
skip_existing = true

[realtime_history]
realtime_data_specs = ["0B41", "0B42"]

[realtime_current]
realtime_data_specs = ["0B31", "0B32"]
```

`historical-odds` requires `[historical_odds].skip_existing = true` and requests
only the missing O1/O2 DataSpecs for each complete race key in `NL_RA_RACE`.
`0B41` is skipped when that race has rows in `ARCHIVE_O1_ODDS_TANFUKUWAKU`;
`0B42` is skipped when it has rows in `ARCHIVE_O2_ODDS_UMAREN`. Missing or empty
archive tables are retrieved. Row presence does not prove that every time-series
observation was acquired, so this workflow intentionally does not support
refetching already archived race/spec pairs. This option does not change realtime
retrieval.

The checked-in `[historical]` profile enables `setup_update`, so the
`historical-basic` command retrieves the configured base-data DataSpecs before
publishing the complete Parquet snapshot. Set the update flags to `false` only
when the corresponding base-data retrieval is intentionally disabled. A missing
database still fails before retrieval.

The target race for realtime retrieval can also be configured in
`configs/jvlink.toml`:

```toml
[realtime]
date = 2026-10-04
jyo = "05"
kaiji = "04"
nichiji = "08"
race = "11"
```

When `[realtime]` is configured, the target race options can be omitted from
the CLI. Supplying all five CLI options overrides the configured target race.

JVLinkToSQLite realtime O1/O2 tables are transient staging tables. They are
copied immediately into cumulative raw tables:

```text
ARCHIVE_O1_ODDS_TANFUKUWAKU
ARCHIVE_O2_ODDS_UMAREN
```

Repeated identical rows are deduplicated while distinct `HappyoTime`
observations are retained.

## CLI

Install dependencies and run commands from the repository root:

```powershell
uv sync --locked

uv run python src/main.py --retrieve --mode=historical-basic
uv run python src/main.py --retrieve --mode=historical-odds
uv run python src/main.py --retrieve --mode=latest
uv run python src/main.py --retrieve --mode=realtime
```

Retrieval and complete Parquet publication are separated by workflow:

- `--retrieve --mode=historical-basic`: run the enabled base-data updates, then publish one
  complete Parquet snapshot. This mode does not retrieve historical O1/O2 odds.
- `--retrieve --mode=historical-odds`: retrieve the oldest unfinished year of historical
  O1/O2 odds, record per-race progress, and continue year by year. Complete Parquet
  publication is deferred until every managed year is raw-complete, then performed once.
  If retrieval or publication fails, the raw database and progress ledger remain available
  for the next manual run. The command stops when the operator interrupts it or no target
  years remain.
  Use `--plan-only` to inspect the next year without writing or starting JVLinkToSQLite.
  The command starts one continuous process; it does not register Task Scheduler
  jobs or apply a weekday rule. A successful run with a valid empty realtime table is recorded
  as `provider_missing/jvopen_no_data` only when the captured JVOpen/JVRTOpen return code is
  `-1`; it is not retried. If the API code is unavailable, the result remains
  `failed/empty_response_unverified`. Missing tables, invalid schemas, archive failures, and
  process failures remain `failed` and stop the run. The official JV-Link API error-code list
  is published by [JRA-VAN](https://developer.jra-van.jp/t/topic/822).
  The progress ledger preserves the process exit code separately from the captured
  DataSpec-specific API name and return code.
  After all managed years are complete, the CLI prints an English message before the full
  Parquet rebuild, then prints whether the rebuild completed or failed. The rebuild can take
  a long time for a large raw database.
  When an older v1 ledger has a previously classified `provider_missing/jvopen_no_data`
  row without API columns, the first write migrates it to
  `provider_missing/legacy_provider_missing`; new automatic `jvopen_no_data` rows always
  require captured `JVOpen`/`JVRTOpen = -1` evidence.
  After confirming a JRA-VAN-side gap, confirm that exact failed race without starting
  JVLinkToSQLite:

  ```powershell
  uv run python src/main.py --retrieve --mode=historical-odds `
    --confirm-provider-missing --date 2008-02-03 --jyo 05 --kaiji 01 --nichiji 02 --race 01
  ```

  Both O1/O2 (`0B41`/`0B42`) are confirmed by default. Use `--data-spec 0B41` or
  `--data-spec 0B42` to confirm only one. The command accepts only failed
  `empty_response_unverified` entries whose current archive count is still zero.
- `--retrieve --mode=latest`: update raw data, then publish a refreshed complete Parquet
  snapshot.
- `--retrieve --mode=realtime`: retrieve and archive the target race's history/current
  odds, then publish race-scoped Parquet for that same `RaceKey`.

All retrieval modes use the flag-based interface. The separate `preprocess`
command remains available for publishing processed data from existing raw data.

If raw data already exists, a complete processed snapshot can be rebuilt without
new JRA-VAN retrieval:

```powershell
uv run python src/main.py preprocess rebuild
```

Alternative config files can be supplied with `--data-config` and
`--jvlink-config` where applicable.

## Processed Parquet layout

Complete historical/latest datasets are immutable snapshots:

```text
data/processed/
├─ CURRENT
└─ snapshots/
   └─ <snapshot-id>/
      ├─ NL_RA_RACE.parquet
      ├─ ARCHIVE_O1_ODDS_TANFUKUWAKU.parquet
      ├─ ARCHIVE_O2_ODDS_UMAREN.parquet
      └─ ...
```

`CURRENT` is replaced atomically only after every table in a new snapshot has
been written and validated. A failed rebuild therefore leaves the previous
snapshot active.

Prediction-time realtime Parquet is race-scoped:

```text
data/processed/realtime/<race-id>/
├─ CURRENT
└─ versions/
   └─ <version-id>/
      ├─ ARCHIVE_O1_ODDS_TANFUKUWAKU.parquet
      └─ ARCHIVE_O2_ODDS_UMAREN.parquet
```

Realtime preprocessing filters the cumulative raw archive to the exact race and
publishes the two O1/O2 files as one version before switching the race-local
`CURRENT` pointer. It does not rebuild all historical Parquet before inference.

Old snapshots and realtime versions are intentionally retained for rollback and
reproducibility until a separate retention policy is introduced.

## Data loader

`src/data/loader/processed_data_loader.py` is the public loading facade.
`src/data/loader/read_parquet.py` owns physical Parquet reads.
`src/data/storage/snapshot_store.py` selects CURRENT versions; readers do not manage versions.

The loader can:

- list and read complete tables from the active snapshot;
- iterate large Parquet tables in bounded Arrow record batches;
- read prediction-time O1/O2 Parquet for a specified `RaceKey`.

汎用SQLite物理readerは`src/data/loader/read_sqlite.py`に置き、snapshot生成工程が利用する。
公開DataLoader APIは引き続きprocessed Parquetだけを読み、raw `race.db`を開かない。
Realtimeもレース別Parquet版を公開してから`read_parquet.py`で読む。

## Planned racing AI

The agreed product requirements are in `docs/requirements.md`, and decided
behavior is in `docs/specification.md`. Design proposals and open questions
remain in `docs/discussions/`. Explicit, audited numeric inputs support LambdaRank
training and prediction; raw-to-feature business calculations and betting decisions
remain separate work.

The detailed LambdaRank MVP implementation proposal is in
[implementation design](docs/implementation-design.md).

The current explanatory-variable contracts are listed in the
[explanatory variable list](docs/feature-list.md).

## Setup and validation

Install the locked development environment:

```bash
uv sync --locked
```

Run repository checks:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

単体テストだけを実行する場合は`uv run pytest src/tests/unit`、結合テストは
`uv run pytest src/tests/integration`を使う。引数なしのpytestは両方を実行する。
型検査は`src`全体を対象とし、分類した全テストも含む。環境確認テストは従来の
`src/tests/test_project_environment.py`に置き、既定実行と`pytest src/tests`の両方で収集する。

The agent-workflow integration tests require PowerShell 7 (`pwsh`). On Windows,
enable Developer Mode and `git config core.symlinks true` so the shared skill
links in `.claude/skills/` check out as symbolic links.

## Development workflow

Claude Code and Codex collaborate under ADR-031
(`docs/rules/agent-collaboration.md`). Run a non-trivial change with `/cc-task`
in Claude Code:

1. Claude Code writes `.handoff/<task-id>/plan.md`; you approve it.
2. Codex implements it in `.worktrees/<task-id>/`; Claude Code verifies the
   result and runs a dual independent review (Claude subagent + Codex).
3. Claude Code pushes and opens a PR as the `keiba-ai-agent` GitHub App and
   drives CI.
4. You review, approve, and merge the PR on GitHub. Rulesets on `main` require
   your approval of the latest push and prevent the App from merging.

One-time agent identity setup is described in `docs/rules/git-workflow.md`.

Repository instructions are in `AGENTS.md`. Current architectural facts are in
`ARCHITECTURE.md`.

## Feature registration and Python API migration

`configs/features.toml` owns the F01-F21 group IDs, names and declaration order.
These are stable JSON identifiers, independent of the numeric model allow-list.
Each `[[features]]` entry contains only `id` and `name`. The catalog must match
all implemented groups; duplicate IDs/names, malformed entries, unknown names
and missing implementations are rejected. Changing an ID requires considering
existing JSON consumers. Importing modules or requesting CLI help never reads it.

```bash
uv run python src/main.py model explanatory-variables --input inputs.json --output features.json --features-config configs/features.toml
```

`--features-config` defaults to `configs/features.toml`. Other commands and their
existing arguments, JSON keys and exit codes retain their contracts.

Python callers load the catalog explicitly once and reuse the same registry:

```python
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.explanatory_variables import build_explanatory_variables
from make_features.jockey_combination import build_jockey_combination
from make_features.tables.parquet import read_feature_table, write_feature_table

registry = create_feature_registry(load_feature_definitions("configs/features.toml"))
result = build_explanatory_variables(batch_inputs, registry=registry)
definition = registry.by_name("jockey_combination").definition
table = build_jockey_combination(
    jockey_inputs, definition=definition, column_types=column_types
)
write_feature_table(table, "jockey.parquet", registered_names=registry.names)
restored = read_feature_table("jockey.parquet", registered_names=registry.names)
```

`batch_inputs`, `jockey_inputs`, and `column_types` above are caller-provided
validated inputs and explicit Arrow scalar types. Registration does not approve
new calculation rules or add columns to model training.

The `make_features` package no longer re-exports implementations. Import individual
build APIs from their feature modules, `FeatureTableRow` from
`make_features.contracts.rows`, input/result types from `make_features.contracts.types`,
table construction from `make_features.tables.build`, table validation from
`make_features.validation.table`, and persistence from `make_features.tables.parquet`.
The original previous-race result, odds ratio and pedigree build APIs keep their
arguments and metadata and receive no F identifiers. Other individual build APIs
now require `definition`; batch generation/audit require `registry`. Table and
datamart APIs require `registered_names=registry.names` for those groups and
retain fixed validation for the original three when omitted.

Import `DataRetriever` from `jra_van_retriever.retriever`, `DataPreprocesser` from
`data.storage.snapshot_builder`, `DataLoader` from `data.loader.processed_data_loader`,
`DataPaths` from `configuration.data_paths`, and `RaceKey` from `domain.race_key`.
Raw race-key rows are converted by `jra_van_retriever.parsing.race_key.race_key_from_row`.
Import pure datamart joins from `make_datamart.builder`, file-based construction and persistence from
`make_datamart.tables.parquet`, and validation from
`make_datamart.validation.table`. All five existing public names remain available from `make_datamart`;
file-based names previously imported from `make_datamart.builder` move to `make_datamart.tables.parquet`. The former
the earlier combined data modules, `features/common/`, `features/make_features.py` and module `SPEC`
constants are removed. The current `src/data/` groups the already separated data responsibilities. Acquired data and existing Parquet artifacts remain in
their original locations and formats. `docs/GUARDED_WORKFLOW_REPAIR.md`
was removed with the guarded workflow under ADR-031.

## Datamart CLI

既存の中間Parquetを指定順に左結合し、検証済みDatamartを保存する。

```powershell
uv run python src/main.py datamart build --input previous.parquet --input odds.parquet --output datamart.parquet --features-config configs/features.toml
```

`--input`は結合順に繰り返す。`--features-config`は既定で`configs/features.toml`を使用し、
宣言された特徴量名を読込・結合・保存の検証へ渡す。元の3特徴量は従来の固定スキーマも使用できる。
F01〜F21と独自IDの登録では、既存APIと同じ列・metadata・時点検証を維持する。
`--output`がいずれかの`--input`と同じファイルを指す場合は、相対パス表記やリンクが異なっても拒否する。
入力や結合の失敗は標準エラーへ表示して終了コード1とし、保存処理へ進まない。
成功時は`datamart saved: N rows`を標準出力へ表示する。

共通設定の物理読込は`configuration.loader.load_toml`、パス解決は
`configuration.path_resolver.resolve_path`が所有する。機能設定がこの基盤へ依存し、
基盤から取得・特徴量・モデルへの依存はない。

## HydraとMLflowによる学習・予測

リポジトリのルートから実行する。入力は既存`model audit/features`と同じ明示JSONであり、
`schema_id`、順序付き`feature_names`、各馬の`race_id`/`horse_id`/timezone付き`freeze_at`、
`features`、特徴量別`available_at`を含む。学習入力には全行の`finish_position`も必要となる。
旧入力の数値allow-listは`ability`と`historical_odds`を維持する。計算した21群の数値列を使う場合は、
[model prepare-input](docs/model-input-preparation.md)で明示選択と計算契約・ラベル出典を持つ入力を作る。
欠損は保持し、最終オッズによる補完や、raw Parquetからの能力値・利用可能時刻の推測は行わない。
既存の入力検証・保存と、新しい正規化観測からの計算・モデル投影は別の入口である。

```powershell
uv run python src/main.py model train --override "data.input=output/inputs/training.json" --override "split.test_races=10" --override "model.parameters.n_estimators=50"
uv run python src/main.py model predict --override "data.input=output/inputs/prediction.json" --override "model.version=1" --override "data.selection=latest_date"
uv run mlflow ui --backend-store-uri sqlite:///output/mlflow/mlflow.db --host 127.0.0.1
```

`configs/experiments/train.yaml`と`predict.yaml`をHydra Compose APIで合成する。
`model/lambdarank.yaml`、`mlflow/local.yaml`の既定グループと反復`--override`で、
学習パラメータ、入力、holdoutレース数、出力、MLflowの実験名・登録名・保存先を管理する。
独自YAMLは`--config-dir`と`--config-name`で選ぶ。相対パスは実行時の作業ディレクトリから解決し、
出力・MLflowデータベース・artifactはその`output/`内に限定する。既存3 TOMLは変更しない。

学習は共通freeze_atを持つレースを厳密な時間順で受け取り、末尾の設定レース数をholdoutにする。
それより前の全レースだけで学習し、holdoutのNDCG@3・Top1精度・Top3一致割合とscore/rankを記録する。
各学習はMLflow登録名の新versionを作成する。予測は`mlflow.registered_model_name`と正整数の
`model.version`を固定し、schema、native成果物、学習末時点より後であることを検証する。
予測値はscore/rankであり、確率や購入案は生成しない。

`latest_date`は、入力JSON内のfreeze_atを`data.date_timezone`（既定Asia/Tokyo）へ変換した
最大日付の全レースを選ぶ。ローカル取得済みの最新日、提供元の最新公開日、未来のライブ予測とは
区別する。OSのファイル更新時刻は使わず、データの自動取得もしない。古い入力ならその入力の最新日となる。

各runは`output/experiments/<run_id>/`へ解決済み設定、監査と分割の件数・期間、予測、実効学習値、
入力hash、ソースhash一覧、uv.lock hash、依存versionを保存し、MLflow artifactへ記録する。
既定のSQLiteは`output/mlflow/mlflow.db`、artifactは`output/mlflow/artifacts`。
学習のnative一式は既存のmodel/metadata/ready形式を維持し、版に学習時点とhashを紐付ける。
失敗runはFAILEDとなり、入力と既存出力は置き換えない。SQLiteとartifactは一緒に保全する。
合成入力を使う統合テストの成功は、実データの学習結果として扱わない。
設計の理由と境界は[ADR-027](docs/decisions/ADR-027-manage-ranking-experiments-with-hydra-and-mlflow.md)を参照する。

## 正規化観測から全21群を計算する

既存21ファイルの`calculate_*`は、証跡付き正規化観測から履歴・条件補正・調教・市場・
対戦グラフ等を数値計算する。既存の計算済み値を受ける`build_*`と旧モデルallow-listは維持する。

```powershell
uv run python src/main.py model calculate-features --input output/inputs/normalized.json --output output/features/calculated.json --config-dir output/feature-config
```

`output/feature-config/calculate.yaml`には`configs/feature_calculation/calculate.yaml`の
全必須パラメータ（`???`）を、選定証跡と共に明示する。運用値の既定採用はない。
入力は`schema_version=1 / observations`を持つJSONであり、原観測の出典・版・hashと
実際の発表/受信/事象時計、完全な固定出馬表・過去通常結果、coverageを要求する。
対象と同日の履歴や当該結果は利用せず、各過去出走の基準もその出走より過去だけで求める。
出力は値・既存監査・全依存manifest・欠損理由を持つ新規JSONで、既存出力を上書きしない。

[入力・設定・時点・列契約](docs/feature-calculation.md)を参照する。
JSONの証跡宣言を検証できても、外部の原本・過去受信履歴を照合したことにはならない。
現存raw/Parquetの証跡不足を時刻の仮置きで補わず、厳格な実データ学習・最新予測は
必要な証拠がそろうまで開始しない。モデル列への自動写像・自動採用も行わない。

学習へ接続する場合は[計算結果のモデル入力準備](docs/model-input-preparation.md)に従う。
計算列の選定と意味上設定をHydraで明示し、計算契約のhashと学習ラベルの受信時刻を検証する。

## 現存Parquetから全21群で参考学習する

`model prepare-reference-input`は固定snapshotと明示manifestから全21群を計算する。
ユーザーが選択した保存発走時刻・発表時受信の仮定、過去訂正時点未検証を実測時計と区別し、
通常結果以外はレース全体を理由付きで保留する。対象の最終結果・馬場・馬体重・オッズを
特徴量へ流用せず、欠損も保持する。既存の厳格経路は引き続き実測証跡を要求する。

[設定、manifest例、加工影響、準備・MLflow学習・厳密版予測の手順](docs/experiments/reference-real-input.md)
と[ADR-030](docs/decisions/ADR-030-connect-pinned-snapshots-with-explicit-reference-assumptions.md)を参照する。
`configs/reference_input/trial.yaml`は全21群から各1列を選ぶ明示的な初期実験設定で、最適値ではない。
