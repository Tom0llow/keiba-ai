# keiba-ai

ローカルでのJRA-VANレースデータ取得、rawからParquetへの前処理、processedデータの読込、
AI駆動開発の基盤を備えたPython 3.12のプロジェクトである。

## 現状

このリポジトリは、Claude Code + Codexの開発workflow、JVLinkToSQLiteを通じたローカルの
JRA-VANデータ取得境界、版管理されたParquet公開、Parquet専用のローダー境界を含む。引き続き、
配布しないPythonプロジェクトである。

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
├─ models/                      # dataset・ranking・training・backends・evaluation・artifacts・experiments・probability
├─ domain/                      # 共有RaceKey
└─ tests/
   ├─ unit/                     # 純粋処理と外部境界mockの分離テスト
   ├─ integration/              # 実ファイル・DB・process・機能接続のテスト
   └─ test_project_environment.py # 既存環境契約の確認
```

プロジェクトにはビルドシステムがない。`uv sync`は、このリポジトリをPythonの配布物として
インストールせずに、ロックされた依存関係をインストールする。

データ契約はADR-005〜008、特徴量登録はADR-020に従う。
[ADR-024](docs/decisions/ADR-024-separate-functional-responsibilities.md)が
ADR-008とADR-021〜023の配置判断を置き換えた責務分離を継承する。
[ADR-025](docs/decisions/ADR-025-group-data-and-separate-cli-contracts.md)によりデータ基盤をdataへ集約し、CLI共通契約と登録の依存を整理した。
全ファイルの最終構成、旧配置の対応表、責務と互換性は
[PR #21リファクタリング記録](docs/refactoring-pr21.md)と
[データ基盤・CLI移行記録](docs/refactoring-pr21-data-cli.md)を参照する。
[ADR-026](docs/decisions/ADR-026-rename-configs-and-classify-tests.md)に従うconfigsへの改名とsrc/tests内の分類、
全テストの分類・旧新対応は[設定・テスト移行記録](docs/refactoring-pr21-configs-tests.md)に記録する。

## データの流れ

すべてのデータ経路は、保存に関する一つの依存方向にそろう。

```text
JV-Link
  -> JVLinkToSQLite
  -> data/raw/race.db
  -> DataPreprocesser
  -> Parquet
  -> DataLoader
  -> training / analysis / prediction
```

`race.db`は、変更可能なrawの取得データの保存先である。モデル向けのコードは、これを直接
読まない。SQLiteの読取取引は`src/data/loader/read_sqlite.py`、純粋変換は
`src/data/preprocessor/sqlite_to_arrow.py`、生成と公開は`src/data/storage/`が所有する。

`src/data/loader/read_parquet.py`は、processedのParquetだけを読む。別の`read_json.py`は、
特徴量やモデルの検証を行わずに、明示されたJSON入力を読む。

保存先のパスは`configs/data.toml`で設定する。

```toml
[paths]
raw_db = "../data/raw/race.db"
processed_dir = "../data/processed"
jvlink_runtime_dir = "../data/runtime/jvlink"
```

## レースデータの取得

レースデータは、ローカルにインストールしたJVLinkToSQLiteの実行ファイルを通じて取得する。
JV-LinkとJVLinkToSQLiteは、Windowsにインストールと設定を済ませておく必要がある。
PythonのコードはJV-Link COMを直接呼び出さず、JRA-VANのサービスキーも保存しない。

ユーザーが所有する`C:\JVLinkToSQLite\setting.xml`はseedとして扱う。取得の動作は
`configs/jvlink.toml`で宣言し、Pythonがhistorical-basic、historical-odds、latest、realtime、
race-day-oddsの各モードの実行用XMLを生成する。

主なprofileは次のとおり。

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

`historical-odds`は`[historical_odds].skip_existing = true`を必須とし、`NL_RA_RACE`の完全な
レースキーごとに、不足しているO1/O2のDataSpecだけを要求する。そのレースの行が
`ARCHIVE_O1_ODDS_TANFUKUWAKU`にある場合は`0B41`を、`ARCHIVE_O2_ODDS_UMAREN`にある場合は
`0B42`を省略する。archive表が存在しない場合や空の場合は取得する。行があっても、時系列の
すべての観測を取得したことの証明にはならないため、このworkflowは、archive済みの
レースとspecの組の再取得を意図的にサポートしない。このオプションはrealtimeの取得を変えない。

リポジトリに登録済みの`[historical]` profileは`setup_update`を有効にしているため、
`historical-basic`コマンドは、完全なParquet snapshotを公開する前に、設定された基本データの
DataSpecを取得する。更新フラグを`false`にするのは、対応する基本データの取得を意図的に
無効にする場合だけとする。データベースがない場合は、それでも取得の前に失敗する。

realtime取得の対象レースは、`configs/jvlink.toml`でも設定できる。

```toml
[realtime]
date = 2026-10-04
jyo = "05"
kaiji = "04"
nichiji = "08"
race = "11"
```

`[realtime]`を設定した場合は、CLIで対象レースのオプションを省略できる。CLIで5つのオプションを
すべて指定すると、設定した対象レースより優先される。

JVLinkToSQLiteのrealtimeのO1/O2表は、一時的なstaging表である。これらは直ちに累積のraw表へ
コピーされる。

```text
ARCHIVE_O1_ODDS_TANFUKUWAKU
ARCHIVE_O2_ODDS_UMAREN
```

同一の行の繰り返しは重複除去し、`HappyoTime`が異なる観測は保持する。

開催日の発走前オッズは、`[race_day_odds]`で取得時点を設定する（[ADR-032](docs/decisions/ADR-032-capture-race-day-odds-for-all-bet-types.md)）。

```toml
[race_day_odds]
normal_update = false
setup_update = false
realtime_update = true
normal_data_specs = []
setup_data_specs = []
realtime_data_specs = ["0B31", "0B32", "0B33", "0B34", "0B35", "0B36"]
offsets_minutes = [30, 10, 5, 2]
late_tolerance_seconds = 60
```

race-day-oddsの実行中に、`latest`や`preprocess rebuild`による完全なParquet出力を重ねない。raw DBは
ロールバックジャーナル方式のため、長い読取の間は取得の書込みが`database is locked`で失敗し、
取得が欠けるか、その日の取得が停止する。当日の`latest`は、race-day-oddsを起動する前に済ませておく。

DataSpecは`0B31`〜`0B36`の6種ちょうどとする。取得した行は既存のO1/O2 archiveとは別の表へ保存し、
取得ごとの記録を`ARCHIVE_CAPTURE_LOG`へ残す。

```text
ARCHIVE_CAPTURE_O1_ODDS_TANFUKUWAKU
ARCHIVE_CAPTURE_O2_ODDS_UMAREN
ARCHIVE_CAPTURE_O3_ODDS_WIDE
ARCHIVE_CAPTURE_O4_ODDS_UMATAN
ARCHIVE_CAPTURE_O5_ODDS_SANREN
ARCHIVE_CAPTURE_O5_OddsSanrenInfo
ARCHIVE_CAPTURE_O6_ODDS_SANRENTAN
ARCHIVE_CAPTURE_O6_OddsSanrentanInfo
ARCHIVE_CAPTURE_LOG
```

## CLI

依存関係をインストールし、リポジトリのルートからコマンドを実行する。

```powershell
uv sync --locked

uv run python src/main.py --retrieve --mode=historical-basic
uv run python src/main.py --retrieve --mode=historical-odds
uv run python src/main.py --retrieve --mode=latest
uv run python src/main.py --retrieve --mode=realtime
uv run python src/main.py --retrieve --mode=race-day-odds --date 2026-11-15
```

取得と完全なParquet公開は、workflowごとに分かれている。

- `--retrieve --mode=historical-basic`: 有効な基本データの更新を実行してから、完全なParquet
  snapshotを1つ公開する。このモードは過去のO1/O2オッズを取得しない。
- `--retrieve --mode=historical-odds`: 過去のO1/O2オッズのうち未完了の最も古い年を取得し、
  レースごとの進捗を記録して、1年ずつ続ける。完全なParquet公開は、管理対象のすべての年で
  rawがそろうまで延期し、その後に1回だけ行う。
  取得または公開に失敗しても、rawデータベースと進捗台帳は次回の手動実行で利用できる。
  このコマンドは、運用者が中断するか、対象の年がなくなると停止する。
  `--plan-only`を使うと、書き込みやJVLinkToSQLiteの起動をせずに次の年を確認できる。
  このコマンドは一つの継続したプロセスを開始する。Task Schedulerへのジョブ登録や、
  曜日の規則の適用は行わない。有効な空のrealtime表で成功した実行は、取得したJVOpen/JVRTOpenの
  戻り値が`-1`の場合に限り`provider_missing/jvopen_no_data`として記録し、再試行しない。
  APIのコードが得られない場合、結果は`failed/empty_response_unverified`のままとなる。
  表の欠落、不正なスキーマ、archiveの失敗、プロセスの失敗は`failed`のままとし、実行を
  停止する。JV-Link APIの公式なエラーコード一覧は[JRA-VAN](https://developer.jra-van.jp/t/topic/822)が公開している。
  進捗台帳は、プロセスの終了コードを、取得したDataSpec別のAPI名と戻り値とは別に保持する。
  管理対象のすべての年が完了すると、CLIは完全なParquetの再構築の前に英語のメッセージを
  表示し、その後、再構築が完了したか失敗したかを表示する。rawデータベースが大きい場合、
  再構築には長い時間がかかることがある。
  旧v1の台帳に、API列のない分類済みの`provider_missing/jvopen_no_data`行がある場合は、最初の
  書き込みでそれを`provider_missing/legacy_provider_missing`へ移行する。新しく自動で記録する
  `jvopen_no_data`行には、常に、取得した`JVOpen`/`JVRTOpen = -1`の証拠が必要となる。
  JRA-VAN側の欠落を確認した後、JVLinkToSQLiteを起動せずに、失敗したその特定のレースを
  確認する。

  ```powershell
  uv run python src/main.py --retrieve --mode=historical-odds `
    --confirm-provider-missing --date 2008-02-03 --jyo 05 --kaiji 01 --nichiji 02 --race 01
  ```

  既定ではO1/O2（`0B41`/`0B42`）の両方を確認する。一方だけを確認するには、`--data-spec 0B41`
  または`--data-spec 0B42`を使う。このコマンドは、失敗した`empty_response_unverified`の項目の
  うち、現在のarchiveの件数がまだ0のものだけを受け付ける。
- `--retrieve --mode=latest`: rawデータを更新してから、更新した完全なParquet snapshotを
  公開する。
- `--retrieve --mode=realtime`: 対象レースの履歴/現在のオッズを取得してarchiveし、その同じ
  `RaceKey`についてレース単位のParquetを公開する。
- `--retrieve --mode=race-day-odds --date YYYY-MM-DD`: 指定日の中央01〜10場の全レースについて、
  `NL_RA_RACE.HassoTime`の`offsets_minutes`の各分前まで待ち、`0B31`〜`0B36`を取得して`ARCHIVE_CAPTURE_*`へ
  保存する。当日の`NL_RA_RACE`は、事前に`latest`で取得しておく。取得ごとに
  `race-day-odds capture <capture_id> <race> -<offset>m <spec>=<status> ...`を出力し、最後の行に件数の要約を
  JSONで出す。失敗があれば終了コード1、Ctrl+Cでは130となる。予定時刻を`late_tolerance_seconds`より過ぎた取得は
  `skipped_late`とし、発走時刻の変更には追従しない。取得の途中で止まった場合は、取得記録の`running`が残り、
  他の取得モードはこのコマンドを再起動して復旧するまで拒否される。このコマンドはParquetを公開しないので、
  `preprocess rebuild`などの完全な再構築で出力する。

すべての取得モードは、フラグ形式のインターフェースを使う。既存のrawデータからprocessedデータを
公開するための別の`preprocess`コマンドも、引き続き利用できる。

rawデータが既にある場合は、JRA-VANから新たに取得せずに、完全なprocessed snapshotを
再構築できる。

```powershell
uv run python src/main.py preprocess rebuild
```

該当するコマンドでは、`--data-config`と`--jvlink-config`で別の設定ファイルを指定できる。

## processed Parquetの配置

historical/latestの完全なデータセットは、不変のsnapshotである。

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

`CURRENT`は、新しいsnapshotのすべての表を書き込んで検証した後にだけ、原子的に置き換える。
そのため、再構築に失敗しても、以前のsnapshotが有効なまま残る。

予測時のrealtime Parquetは、レース単位である。

```text
data/processed/realtime/<race-id>/
├─ CURRENT
└─ versions/
   └─ <version-id>/
      ├─ ARCHIVE_O1_ODDS_TANFUKUWAKU.parquet
      └─ ARCHIVE_O2_ODDS_UMAREN.parquet
```

realtimeの前処理は、累積のraw archiveを対象のレースだけに絞り込み、O1/O2の2ファイルを1つの
版として公開してから、レースごとの`CURRENT`ポインタを切り替える。推論の前に、過去の
Parquetをすべて再構築することはしない。

古いsnapshotとrealtimeの版は、別の保持方針を導入するまで、ロールバックと再現性のために
意図的に保持する。

## データローダー

`src/data/loader/processed_data_loader.py`は、公開の読込facadeである。
`src/data/loader/read_parquet.py`は、Parquetの物理読込を所有する。
`src/data/storage/snapshot_store.py`がCURRENTの版を選択し、readerは版を管理しない。

ローダーは次のことができる。

- 有効なsnapshotから完全な表を一覧表示し、読み込む。
- 大きなParquet表を、上限のあるArrowのrecord batchで反復処理する。
- 指定した`RaceKey`について、予測時のO1/O2 Parquetを読む。

汎用SQLite物理readerは`src/data/loader/read_sqlite.py`に置き、snapshot生成工程が利用する。
公開DataLoader APIは引き続きprocessed Parquetだけを読み、raw `race.db`を開かない。
Realtimeもレース別Parquet版を公開してから`read_parquet.py`で読む。

## 計画中の競馬AI

合意済みの製品要件は`docs/requirements.md`に、決定済みの動作は`docs/specification.md`にある。
設計案と未解決の問題は`docs/discussions/`に残っている。明示的で監査済みの数値入力によって、
LambdaRankの学習と予測ができる。rawから特徴量への業務計算と購入判断は、引き続き別の作業とする。

LambdaRank MVPの詳細な実装案は[実装設計](docs/implementation-design.md)にある。

現行の説明変数の契約は[説明変数一覧](docs/feature-list.md)に記載している。

## セットアップと検証

ロックされた開発環境をインストールする。

```bash
uv sync --locked
```

リポジトリのチェックを実行する。

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

エージェントのworkflowの結合テストには、PowerShell 7（`pwsh`）が必要である。Windowsでは、
`.claude/skills/`の共用スキルのリンクがシンボリックリンクとしてチェックアウトされるよう、
開発者モードと`git config core.symlinks true`を有効にする。

## 開発workflow

Claude CodeとCodexは、ADR-031（`docs/rules/agent-collaboration.md`）に従って協働する。
軽微でない変更は、Claude Codeで`/cc-task`を使って実行する。

1. Claude Codeが`.handoff/<task-id>/plan.md`を書き、人間が承認する。
2. Codexが`.worktrees/<task-id>/`で実装し、Claude Codeが結果を検証して、二系統の独立した
   レビュー（Claudeのサブエージェント + Codex）を行う。
3. Claude Codeが`keiba-ai-agent` GitHub AppとしてpushしてPRを作成し、CIに対応する。
4. 人間がGitHub上でPRをレビュー・承認し、マージする。`main`のrulesetは、最新のpushに対する
   人間の承認を必須とし、Appによるマージを防ぐ。

エージェント識別の一度だけの設定は、`docs/rules/git-workflow.md`に記載している。

リポジトリの指示は`AGENTS.md`に、現行のアーキテクチャの事実は`ARCHITECTURE.md`にある。

## 特徴量の登録とPython APIの移行

`configs/features.toml`は、F01〜F21の群ID、名前、宣言順を所有する。これらは、モデルの数値
allow-listとは独立した、安定したJSON識別子である。各`[[features]]`項目は`id`と`name`だけを持つ。
catalogは実装済みのすべての群と一致しなければならず、ID・名前の重複、不正な形式の項目、
未知の名前、実装の欠落は拒否する。IDを変更するには、既存のJSONの利用者を考慮する必要がある。
モジュールのimportやCLIのヘルプの表示では、このファイルを読まない。

```bash
uv run python src/main.py model explanatory-variables --input inputs.json --output features.json --features-config configs/features.toml
```

`--features-config`の既定値は`configs/features.toml`である。その他のコマンドと、その既存の
引数、JSONキー、終了コードは、契約を維持する。

Pythonの呼出し側は、catalogを明示的に1回読み込み、同じregistryを再利用する。

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

上の`batch_inputs`、`jockey_inputs`、`column_types`は、呼出し側が渡す検証済みの入力と、明示的な
Arrowのscalar型である。登録によって、新しい計算規則が承認されたり、モデル学習に列が追加されたり
することはない。

`make_features`パッケージは、実装を再exportしなくなった。個別のbuild APIは各特徴量モジュールから、
`FeatureTableRow`は`make_features.contracts.rows`から、入力・結果の型は
`make_features.contracts.types`から、表の構築は`make_features.tables.build`から、表の検証は
`make_features.validation.table`から、永続化は`make_features.tables.parquet`からimportする。
元からある前走結果、オッズ比、血統のbuild APIは、引数とmetadataを維持し、F識別子を持たない。
その他の個別のbuild APIは、現在は`definition`を必須とし、一括の生成・監査は`registry`を必須とする。
表とdatamartのAPIは、それらの群について`registered_names=registry.names`を必須とし、省略時は
元の3つについて固定の検証を維持する。

`DataRetriever`は`jra_van_retriever.retriever`から、`DataPreprocesser`は
`data.storage.snapshot_builder`から、`DataLoader`は`data.loader.processed_data_loader`から、
`DataPaths`は`configuration.data_paths`から、`RaceKey`は`domain.race_key`からimportする。
rawのレースキー行は`jra_van_retriever.parsing.race_key.race_key_from_row`で変換する。
datamartの純粋な結合は`make_datamart.builder`から、ファイルからの構築と永続化は
`make_datamart.tables.parquet`から、検証は`make_datamart.validation.table`からimportする。
既存の5つの公開名は、すべて引き続き`make_datamart`から利用できる。以前`make_datamart.builder`から
importしていたファイル系の名前は、`make_datamart.tables.parquet`へ移る。以前の統合データ
モジュール、`features/common/`、`features/make_features.py`、およびモジュールの`SPEC`定数は
削除された。現在の`src/data/`は、既に分離したデータの責務をまとめている。取得済みのデータと
既存のParquet成果物は、元の場所と形式のまま残る。`docs/GUARDED_WORKFLOW_REPAIR.md`は、
ADR-031によりguarded workflowと共に削除した。

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

## 全期間の参考特徴量datamartを構築する

`datamart build-reference`は、固定snapshotから対象期間の中央全レースについて全21群を時系列順に
一度だけ計算し、閉じた数値列の全列・群ごとの利用可能時刻・ラベルを年ごとのParquetへ保存する。
参考規則と計算式は`model prepare-reference-input`と同じで、読込時に21群を再計算しない。

```powershell
uv run python src/main.py datamart build-reference --config-name measure --override processed_root=data/processed --override snapshot_id=098ce3f4b5d7480282269218d80cef05 --output output/reference-datamart-2025
```

`--output`は存在しない新しいパスで、processed rootの外に置く。`configs/reference_datamart/build.yaml`は
`snapshot_id`（nullなら最初の一度だけCURRENTを解決する）以外を必須値`???`とし、`measure.yaml`は計測用の明示値（対象2025年、履歴2005年から）である。
形式・検証・計測結果は[参考特徴量datamartの構築と計測](docs/experiments/reference-feature-datamart.md)と
[ADR-034](docs/decisions/ADR-034-build-full-period-reference-feature-datamart.md)を参照する。

## 年単位foldでtop-3 PLの着順確率を評価する

`model evaluate-pl`は、全期間の参考datamartから年単位の拡大型fold（train〜Y−2・valid Y−1・test Y）で
top-3 Plackett–Luceの着順確率をLightGBMで学習し、validでearly stoppingと温度の校正を行い、testで同時点の
市場確率と比較する。モデルは保存せず、`report.json`と`predictions.parquet`だけを新しいディレクトリへ公開する。

```powershell
uv run python src/main.py model evaluate-pl --config-name measure --override datamart_path=<datamart> --override datamart_manifest_sha256=<manifestのSHA-256> --output output/pl-evaluation-2016-2025
```

`configs/pl_evaluation/evaluate.yaml`はすべて必須値`???`で、`measure.yaml`が実データ用の明示値
（train 2006年から、test 2016〜2025年、市場の単勝オッズ列あり・なしの2 variant）を持つ。datamartのパスと
`datamart build-reference`が出したmanifestのSHA-256は`--override`で渡す。手順・出力形式・結果は
[着順確率モデルの評価](docs/experiments/pl-probability-model.md)と
[ADR-035](docs/decisions/ADR-035-evaluate-top3-plackett-luce-probabilities-on-yearly-folds.md)を参照する。
