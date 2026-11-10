# アーキテクチャ — keiba-ai

## 状態

このリポジトリは、開発自動化、ローカルでのJRA-VANレースデータ取得、rawからprocessedへの前処理、
学習と予測のためのParquet読込を含む。引き続き、Pythonの配布物としてはインストールされていない。

以前のローカルの試作版は、現行の要件の出典でも、設計の判断根拠でもない。製品の動作と永続的な
アーキテクチャ上の決定は、明示的な要件、またはAcceptedのアーキテクチャ決定記録（ADR）に
基づかなければならない。

## 現行の実行環境とツール

- Python: 3.12
- 環境・依存関係の管理ツール: uv
- データCLI: Typer
- フォーマッターとリンター: Ruff
- 型チェッカー: mypy
- テストフレームワーク: pytest
- 自動化: GitHub Actions、GitHubのruleset、GitHub Appによるエージェント識別

ロック済みの開発環境は`pyproject.toml`と`uv.lock`で定義する。プロジェクトにはビルドシステムが
ないため、`uv sync`は、このリポジトリをPythonの配布物としてインストールせずに依存関係を
インストールする。

リポジトリ全体の検証には次を使う。

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

## 開発自動化

ADR-031は、Claude CodeとCodexが協働する方法と、信頼を強制する場所を定める。役割と引き継ぎは
`docs/rules/agent-collaboration.md`に、Git、PR、CI、マージの規則は
`docs/rules/git-workflow.md`にある。

```text
.agents/skills/              # Codex専用スキル + 共用スキルの正本
.claude/
├─ skills/                   # Claude専用のcc-*スキル + 共用スキルへのリンク
├─ agents/reviewer.md        # 独立した読み取り専用のレビュー用サブエージェント
└─ settings.json             # Claude Codeの権限
.codex/                      # Codexの設定と実行規則（Git・gh・ネットワークなし）
.github/
├─ workflows/ci.yml          # 必須のQualityとTestのチェック
├─ CODEOWNERS                # 人間のオーナーがすべての変更を承認する
└─ rulesets/                 # main-protectionとmain-merge-restriction
scripts/github-app/github-app.ps1   # App JWTをインストールトークンへ交換するヘルパー
```

- Claude Codeは、タスクの設計と調整、Codexの出力の検証、二系統の独立したレビューを行い、
  エージェントによるGit・GitHubへの書き込みをすべて`keiba-ai-agent` GitHub Appとして行う。
  Codexは、Gitの変更、`gh`、ネットワークアクセスを使わずに`.worktrees/<task-id>/`で実装する。
- `github-app.ps1`は、リポジトリの外に保管した秘密鍵でRS256のApp JWTに署名し、このリポジトリに
  限定した1時間有効のインストールトークンと交換する。Gitの資格情報プロトコルには
  `x-access-token`のpush URLに対してだけ応答し、allow-listにある`gh`のサブコマンドだけを
  実行する。Appには`workflows`権限がない。ADR-033により、AppはIssuesの読み書き権限を持ち、
  helperは`gh issue`の`create`、`view`、`list`、`comment`、`edit`だけを許可する。`check`は、トークンの
  権限で`contents`・`pull_requests`・`issues`が`write`であり、`workflows`がないことを検証する。
- `main`はサーバー側で保護される。最新のpushに対するcode ownerの承認と解決済みの会話を備えた
  PR、GitHub Actionsのappに紐づく厳格な`Quality`と`Test`のチェック、線形履歴、force pushと
  削除の禁止を必須とし、バイパスはない。二つ目のrulesetにより、管理者だけがPRを通じて
  `main`を更新できるため、Appはマージできない。
- 共用スキルは、`.claude/skills/`から`.agents/skills/`への、スキルごとの相対シンボリック
  リンクとする。`src/tests/integration/test_agent_skills_layout.py`がこの配置を検証する。

## 現行の機能境界

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

共通TOML読込とパス解決の依存は`機能の設定 → configuration → 標準ライブラリ`の一方向である。
configurationは業務機能へ依存しない。暗黙の設定読込とsingletonは設けない。
ADR-027により`configuration/experiments.py`が明示呼出し時にHydra Compose APIで
`configs/experiments/`のYAMLとグループ・上書きを合成する。既存3 TOMLは変更しない。
実験の相対パスは呼出時cwdから解決し、生成物とMLflowのSQLite/artifactはcwdの`output/`内に限定する。

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

`jra_van_retriever/retriever.py`のJraVanRetrieverはhistorical-basic/historical-odds/latest/realtime/
race-day-oddsを構成する。既存のDataRetriever名も同じクラスを指す。workflowsはモードごとの処理順序を所有する。
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

ADR-032のrace-day-oddsは、指定日の`NL_RA_RACE`の`HassoTime`から`[race_day_odds]`の各分前に
0B31〜0B36を1回のJVLinkToSQLite実行で取得し、既存O1/O2 archiveとは別の`ARCHIVE_CAPTURE_*`表へ保存する。

| モジュール | 責務 |
| --- | --- |
| workflows/race_day_odds_plan.py | 取得予定の純粋な計画、遅延判定、ADR-013と同じ規則の結果分類。 |
| workflows/race_day_odds.py | 起動時復旧、予定時刻までの待機、ロック内の1件ずつの取得の組立。時計とsleepは注入可能。 |
| acquisition/odds_archive.py | 取得用stagingの検証付き退避・初期化、取得記録`ARCHIVE_CAPTURE_LOG`、DataSpec別SAVEPOINTでのarchive。 |
| acquisition/acquisition_lock.py | 取得記録の`running`行がある間、全取得モードを拒否する。race-day-oddsの起動時復旧だけが解除する。 |
| progress/raw_observation.py | 指定日の`NL_RA_RACE`のキー・区分・発走時刻の読取。 |

3連複・3連単の子表のarchiveは、親表の`headDataKubun`/`HappyoTime`を列として加え、全列`TEXT`とする。
同じ`HappyoTime`で行集合が異なる取得は`happyo_conflict`として退避する。`running`の確定後の書込み失敗では
`running`とstagingを残して停止し、次回起動時にstagingを退避・初期化して`interrupted`とする。
発走時刻の変更には追従しない。

台帳は完全RaceKeyとDataSpecをキーとし、初期archive欠損をpendingとする。
captured JVOpen/JVRTOpen=-1だけを自動provider_missingとし、証拠なし空応答はfailedで停止する。
旧状態移行、API名/コード列追加、明示確認も従来通り。raw完了年を順に取得し、全管理年の完了後に
一度の完全Parquet公開を行う。callback失敗ではfailedを確定し、raw/台帳を次回へ残す。

## 特徴量とDatamart

make_featuresの個別モジュールは入力型、計算、固有検証・正規化を所有する。
既存のFeatureBuilder/RegisteredFeatureBuilder、共通FeatureTableRow、F01〜F21の計算と監査順序を維持する。
catalogは定義と登録、contractsは型、generationは共通手順、serializationは純粋JSON変換、
validationは漏洩・時点・値・表の監査、tablesはArrow構築と保存metadataの契約を所有する。
ADR-028で各21ファイルにcalculate APIを追加し、正規化観測からの数値計算を所有する。
contracts/observations.pyが出典・版・hash・実際の発表/受信/事象時計、完全出馬表/通常結果、
距離付き調教/ラップ、正規化父/母父、発売集合とオッズ、coverageと必須パラメータを定義する。
validation/observations.pyが時点・改訂競合・完全集合・測定距離を検証し、generation/observations.pyと
statistics.pyがas-of版、馬/担当者index、窓・共通統計を提供する。個別計算とgraph fitはcontext内で共有する。
generation/calculate.pyは既存registryのcalculateを呼び、既存FeatureBatchInput/監査/中間行へ投影する。
混合依存・欠損理由・診断・パラメータをserialization/observations.pyが純粋JSON変換する。
原本とのhash/受信証拠照合やrawコードの解釈は追加していない。現存Parquetを厳格時点入力へ変換しない。

元のprevious_race_result/odds_ratio/pedigreeの固定列・metadataを維持する。
その他の表は明示registered_namesとscalar column_types、保存metadataの整合性を要求する。
データの物理Parquet読書きは共通reader/writerに委譲し、各機能が保存前・読込後の検証を続ける。

make_datamart/builder.pyは入力tableの純粋な順序付き左結合だけを実装する。
先頭表のキーと順序、欠損、feature別available_at、freeze_at、重複と列衝突の規則は変えない。
tables/schema.pyが列・metadata、validation/table.pyが表固有検証、tables/parquet.pyが
ファイルからの構築APIと保存・読込契約を所有する。packageの5公開名は維持する。
旧builderのファイルAPIはtables/parquetへ移し、循環importや互換Facadeを残さない。

ADR-034の参考datamartは、特徴量中間表の結合とは別の種類のdatamartである。固定snapshotから対象期間の
中央全レースについて、ADR-030と同じ参考規則・同じ21群の計算器で特徴量を時系列順に一度だけ計算し、
年ごとのParquetへ保存する。

| 所有者 | 責務 |
| --- | --- |
| make_features/generation/chronological.py | 開始順の1本の履歴配列、JST日付ごとの接頭辞の見方、基準集合の統計、調教の日付索引、対象ごとの共有context、時点の不変条件。I/Oなし。 |
| make_features/generation/observations.py | `CalculationContext`の取得口（窓・騎手・調教師・親・調教・基準集合・事前率・日付で共有する値）。既定の実装は対象ごとの参考経路と同じ値を返す。 |
| make_features/reference_snapshot.py | 対象1レースの正規化`normalize_reference_target`、履歴・血統・ラベルの正規化。既存の`normalize_reference_input`と共有する。 |
| models/serialization/reference_datamart.py | 年ごとに履歴を進め、開催日ごとに対象を計算し、閉じた数値列の全列・群ごとの`available_at`・ラベルへ投影し、manifestの内容を作る。I/Oなし。 |
| make_datamart/tables/reference.py | 年ごとの`part-0.parquet`・`races.parquet`、`held_races.json`、`manifest.json`の書込みと、hash・schema・時点・ラベルの読込検証。指定年の`race_id`だけをhash照合して読む軽い読込口（`read_reference_datamart_race_ids`）。21群の再計算はしない。`models`をimportしない。 |
| data/storage/directory_publisher.py | 出力と同じ親のstagingへ書き、完成後にrenameで公開し、失敗時にstagingを削除する。 |
| data/loader/fixed_snapshot.py / reference_input.py | 表の事前のhash、年・日付の期間読込、O1/O2のfooterを1年の間使い回す読込口。 |

同じJST日付の対象は同じ履歴の接頭辞を見るため、馬・騎手・調教師の索引、窓付き母集団、基準集合の統計、
半減期がnullのときのPageRankを共有する。freezeの時刻に依存する調教の窓・EWMA・市場は対象ごとに計算する。
依存は`available_at`と`event_at`の最大値を与えるevidenceに要約し、漏洩は見方ごとの不変条件で防ぐ。
計算器の`ValueError`はそのレースを`stage=calculation`、対象ごとのcontextの検証の`ValueError`は
`stage=target_pre_freeze`で保留し、履歴・調教・evidence登録表の不変条件の違反では構築全体を失敗させる。
読込APIはhash・契約・列一覧・行の時点・ラベル境界・着順の連続性を検証する。

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
| experiments/inputs.py / provenance.py | 明示JSONとhashの読込・監査、最大freeze日選択、ソース・lock・依存の識別記録。 |
| experiments/tracking.py / runner.py | 明示したローカルMLflow SQLiteのrun/registry/native artifact管理と学習・予測の組立。 |

ラベルは1着3/2着2/3着1/他0、gainは0/1/3/7、groupはrace内行数とする。
旧allow-listはability/historical_oddsを維持する。ADR-029のdataset/calculated.pyが追加の閉じた数値列と計算契約を所有し、
型・単位・生成規則・順序付き列と意味上設定のhashを再検証する。欠損値やNaNを保持し、最終オッズで補完しない。
RankingModel.save/loadは利用中のAPIとしてNativeModelArtifactへ委譲し、成果物処理を複製しない。
既存models/predict_model.pyは元からある互換入口として新rankerの2名を再公開する。
feature/model serializationはI/O・Typerへ依存しない。

ADR-027の`model train`は末尾の設定レース数をholdoutへ分離し、厳密な時系列順とレース境界を
検証してtrainだけを学習する。NDCG@3、Top1精度、Top3一致割合とholdout予測、設定、実効学習値、
入力hash、schema、時点監査、期間・件数、ソース集合hashと依存versionをMLflowへ保存する。
学習ごとに登録名の新versionを作り、既存native一式と学習時点を示すtraining.jsonを記録する。
run作成後の失敗はFAILEDとし、各実行は新run IDディレクトリを所有する。

`model predict`は登録名と厳密なversionを指定し、FINISHED学習run、READY版、ローカルsource、
hashと既存RankingModel.loadでnative一式を検証する。schema一致と学習末時点より後のレースを要求し、
score/rankだけを返す。latest_dateは入力JSONのfreeze_atを設定timezoneへ変換した最大日付であり、
OS更新時刻や提供元の最新公開状態を意味しない。rawからの業務加工、入力時刻推定、取得は行わない。

ADR-029のserialization/projection.pyは計算結果から明示した承認数値列だけを投影し、別の完全通常結果を
計算後に結合する。全計算payloadと出典manifestをprepared JSONへ保持する。実験層はlabel_sourcesを
検証し、学習結果available_atの最大label_known_throughが最初のholdout freezeより前であることを要求する。
training.jsonとMLflowへその値と学習結果出典・保証区分を保存し、予測は学習末freezeと結果known時刻の
両方より後を要求する。旧入力/成果物はラベル時点未保証を明示する。新列もnative形式番号3を維持するが旧コードでは読めない。

ADR-035のtop-3 Plackett–Luce（PL）の評価経路は、参考datamartから年単位の拡大型foldで着順確率を学習・校正し、
同時点の市場確率と比較する。固定snapshotの`NL_RA_RACE`から、GradeCD A/B/CかつTrackCD 10〜24の
`jra_flat_graded_stakes_v1`部分集合も判定し、foldごと・pooledで別集計する。既存のLambdaRankの学習・予測・
保存形式とは独立で、PLモデルは永続化しない。

| 所有者 | 責務 |
| --- | --- |
| probability/plackett_luce.py | padded配置、top-3 PLのNLL・勾配・厳密なHessian対角項、勝率・2着以内・3着以内の周辺確率、単勝・馬単・馬連・3連単・3連複の実際の組合せの対数確率。numpyだけ、I/Oなし。 |
| probability/calibration.py | validのtop-3 PLのレース平均NLLを最小にする単一の温度（黄金分割）。 |
| evaluation/probability_metrics.py | レース単位の確率指標、市場完全レースの$q_i$、確率帯・オッズ帯の校正表（馬の等重み）、レース単位の対応ありbootstrap。 |
| dataset/race_arrays.py / serialization/race_arrays.py | numpyの`RaceArrays`の不変条件と部分集合、datamartの`pa.Table`からの列単位の変換。 |
| serialization/race_subsets.py | 固定snapshotの`NL_RA_RACE`のGradeCD・TrackCDから評価部分集合のrace_id集合を作る純粋な分類。 |
| evaluation/yearly_folds.py | train〜Y−2・valid Y−1・test Yのfold、次のsplitの最初のfreeze以後に結果が使えるレースの除外と監査。 |
| backends/lightgbm.py | `fit_native_pl_booster`: callable objectiveとvalidのfeval・early stoppingによる`lightgbm.train`。予約parametersと`gbdt`以外を拒否する。 |
| experiments/pl_evaluation.py | variant×foldの学習・温度推定・testの確率と指標、市場（連勝式はHarville展開）との比較、report・予測表の組立。I/Oなし。 |

testの着順は採点だけに使い、学習・early stopping・温度推定・確率の生成には使わない。

## CLI

main.pyはTyperの組立・登録・起動だけを行う。cli/options.pyとcli/json_io.pyは共通option、JSON境界、構造化エラー、
各機能CLIは対応機能の引数検証、実行、表示と終了を所有する。下位機能はCLIやTyperをimportしない。
importとhelpは設定や入力を読まず、取得資源を作らない。
model prepare-inputはcli/model_projection.pyがHydra必須parameters/selected_columnsと正規化観測を読み、
全21群の計算と明示列投影、任意の別結果入力結合、新規JSON保存を組み立てる。configuration/model_projection.pyは
Hydra合成だけを行う。
model calculate-featuresはcli/make_features.pyが正規化JSONとHydra必須パラメータを読み、
全21群の値・依存manifestを新規JSONへ保存する。configuration/feature_calculation.pyは
Hydraの合成だけを行い、特徴量型への変換・監査を下位のserialization/validationへ委譲する。
入力・既存成果物の上書きは拒否し、保存は共通write_jsonの排他的作成を使う。

既存の取得flags、preprocess/modelコマンド、引数・文言・stdout/stderr・終了コードを維持する。
main.register_feature_commandsは既存の公開登録APIとしてmainで実装する。
cli/options.pyがDataConfigOption/JVLinkConfigOption、cli/json_io.pyが公開のread_json_object/
parse_json_inputs/input_error_payload/exit_input_errorを所有する。CLI固有スキーマは各機能に残す。
取得・前処理CLIはSnapshotBuilder.from_tomlを直接呼び、他CLIのprivate factoryを参照しない。
機能CLIはjra_van_retriever.py/preprocessor.py/make_features.py/make_datamart.py/models.py/model_projection.pyとし、
機能同士を登録のためにimportしない。Typer登録は全てmainが所有する。
新規datamart buildはrepeatable --input、--output、既定configs/features.tomlの--features-configを受け、
定義名のみを読み、既存のファイル構築・保存APIへ渡す。失敗はstderr/終了1、成功は行数をstdoutへ出す。
CLIは出力先がいずれかの入力と同じファイルを指す場合、相対パス表記やリンクが異なっても保存前に拒否する。
`datamart build-reference`はcli/reference_datamart.pyが、configuration/reference_datamart.pyで合成した
`configs/reference_datamart/`の設定と固定snapshotを読み、年ごとに読込・計算・書込みを繰り返す。
`--output`は存在しない新しいパスで、親が存在し、processed rootの外にあることを要求する。進捗はstderr、
公開後の要約1行はstdoutへ出す。失敗は終了コード1、Ctrl+Cは130とし、どちらでもstagingを残さない。
`model evaluate-pl`はcli/pl_evaluation.pyが、configuration/pl_evaluation.pyで合成した`configs/pl_evaluation/`の
設定と`processed_root`を読み、datamart manifestの`snapshot_id`で固定snapshotの`NL_RA_RACE`を期間・venue限定で
読み、表hashを照合する。設定・fold年・variantを検査した後、make_datamart/tables/reference.pyの
`read_reference_datamart_race_ids`でtest年の`races.parquet`をmanifestのSHA-256で照合して`race_id`列だけを先に読み、
snapshotに無いtestレースを拒否し、datamartに無い平地重賞の件数をtest年ごとに記録する。その後、manifestのSHA-256で固定した参考datamartを`read_reference_datamart`で検証して読み、
ADR-035の評価を実行する。`report.json`と`predictions.parquet`を`publish_directory`で新しいディレクトリへ公開する。
helpとimportは設定・datamart・snapshot・LightGBMを読まない。進捗・要約・終了コードは`datamart build-reference`と同じ規則である。

## 進化時の制約

ADR-030の参考経路では`data/loader/fixed_snapshot.py`がCURRENTを一度だけ固定し、
`reference_input.py`が必要列・レース・期間・馬IDでArrow読込を限定する。
`make_features/reference_raw.py`と`reference_snapshot.py`は純粋な原列換算・集合検証・
通常結果の全レース保留・KettoNum対応・前日調教・父/母父・同期O1/O2を所有する。
`ReferenceEvidence`はnullable実発表時計、null受信時計、宣言利用境界と根拠を区別する。
旧SourceEvidenceと厳格入口は維持し、参考専用入口が同じ21群計算を共有する。
`models/serialization/reference.py`は固定原投影から再計算し、出典・依存集合catalogで重複を抑える。
`snapshot_reference_21_groups_v1`の設定と参考規則をschemaへ固定し、結果利用境界をrunnerへ接続する。
Hydra設定は`configs/reference_input/`、組立CLIは`prepare-reference-input`である。
MLflowへprepared一式と参考保証を保存し、最新予測も厳密版・schema・ラベル利用境界を検証する。
これは固定snapshot内の採用母集団についての参考実験で、過去の受信・訂正時計の証明ではない。

import時のI/O、循環依存、不要なFacade、将来用の空設定・依存は追加しない。
公開API・保存形式・セキュリティ境界の変更は影響を整理し、長期判断をADRに残す。
実装されていないrawからの履歴集計・nested選定・購入判断を現行機能としない。
