# ADR-050: PLの評価とバックテストのreportを事後にMLflowへ記録する

- Status: Accepted
- Date: 2026-11-26
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #117、Refs #83・#57
- Supersedes: N/A
- Superseded by: N/A

---

## Context

精度改善（#83〜#88）では、variant・LightGBMの設定・datamartを変えて`model evaluate-pl`と`model backtest-betting`を
繰り返し、市場との差や回収率を比べる。今は結果を`output/`の出力ディレクトリ名（`-r2`・`-final3`など）と
`docs/experiments/*.md`の手書きの表で管理している。2026-11-26時点で`output/`には173のディレクトリがあり、PLの評価だけで
6版ある。列群ごとのablationや学習期間の窓の比較で実行の数が増えると、どの出力がどの設定・datamartの結果かを
手でたどることになる。

[ADR-027](ADR-027-manage-ranking-experiments-with-hydra-and-mlflow.md)はMLflowで実験の結果とモデルの版を管理すると決めたが、
対象は旧LambdaRankの`model train`/`model predict`だけである。[ADR-038](ADR-038-train-and-persist-the-final-top3-pl-model.md)の
決定6は、PLのモデルをMLflowで管理せず、manifestのSHA-256で固定するファイルの成果物とすることを、人が承認した意図的な例外として記録している。

PLの評価は約1時間、バックテストは数分かかる。どちらの出力も`publish_directory`で原子的に公開され、`report.json`に
設定・入力のhash・provenanceが入っている。

---

## Decision

1. **事後の記録のCLI。** `model track-report --report-dir <出力ディレクトリ>`を加える。公開済みの`report.json`を読み、
   ローカルのMLflow（既定は`output/mlflow/mlflow.db`、artifactは`output/mlflow/artifacts`）にrunとして記録する。
   `--database`と`--artifact-root`は作業ディレクトリの`output/`の下の異なるパスに限る（ADR-027と同じ規則）。
   `model evaluate-pl`・`model backtest-betting`などの既存のCLIはMLflowを呼ばず、振る舞いも変えない。
2. **対象の形式。** `pl_probability_evaluation` v1と`ev_betting_backtest` v2だけを記録する。それ以外の形式・版、必要な項目が
   欠けたreport（重賞の集合`race_subsets`を持たない初期のv1のPLの評価を含む）、MLflowが受け付けないキー（出力ディレクトリの
   ファイル名や`config`のキーから作るもの）や長すぎるtagの値は、MLflowに触れる前に拒否する。実験名は形式で決める（`pl-evaluation`・`betting-backtest`）。
   旧LambdaRankの`ranking`とは同じデータベースの別の実験とする。
3. **runの構成。**
   - 親run（1回の記録につき1つ、tag `run_role: report`）: tagsに`report_format`・`report_format_version`・`report_dir`・
     `report_sha256`・出力ディレクトリ直下の各ファイルの`file_sha256.<name>`・`source_sha256`・`snapshot_id`を記録する。
     PLの評価では`datamart_manifest_sha256`・`datamart_contract_sha256`、バックテストでは`pl_report_sha256`・
     `pl_predictions_sha256`・`pl_variant`も記録し、バックテストのrunを元のPLの評価のrunとtagで照合できるようにする。
     paramsは`config`をドット区切りで平らにした値（文字列以外はJSON）とし、6,000文字を超える値は記録せずtag
     `params_omitted`にキーを残す。artifactは`report.json`の複製と`config.json`とする。
   - PLの評価では、variantごとに子run（tag `run_role: variant`、`mlflow.parentRunId`で親に結ぶ）を作り、pooled・重賞の
     市場との比較（raw・calibratedの6指標それぞれの`model_mean`・`market_mean`・`mean_difference`・区間）、段階別NLL、
     test年をstepとしたfoldごとの差・`best_iteration`・`best_valid_nll`・温度を記録する。同じ指標名でvariantどうしを並べて比べられる。
   - バックテストでは子runを作らず、親runに全test年・共通の年・年ごと（stepは年）の回収率などと、方法ごとの年ごとの
     定額・方策の回収率を記録する。
   - reportの`null`の数値は記録しない。
4. **重複と失敗。** 同じ実験に`report_sha256`が同じで`FINISHED`の親runがあれば、記録せずに`already recorded`を出して
   終了コード0で終える。子runを先に、親runを最後に`FINISHED`にするので、`FINISHED`の親runは記録が揃っていることを意味する。
   途中で失敗したら、作ったrunをすべて`FAILED`にして終了コード1（Ctrl+Cでは130）で終える。`FAILED`のrunは重複とみなさない。
5. **正本と範囲。** 出力ディレクトリが正本であり、MLflowは出力ディレクトリから作り直せる派生の索引とする。
   `--report-dir`のファイルは読むだけで変えない。Parquetは複製しない。PLのモデル・推定器・当日の成果物はMLflowに
   登録しない（ADR-038の決定6を保つ）。モデルregistryは使わない。年1回の作り直しの手順（ADR-048）は変えない。

---

## Rationale

- 長い計測とMLflowへの記録を切り離すと、MLflowの失敗で約1時間の評価を失わず、既存の公開・終了コードの契約にも触れない。
- 事後の記録なら、既存の結果（重賞の集合を持つPLの評価`pl-evaluation-2016-2025-graded*`の4版と、v2のバックテスト）も
  同じ形で取り込み、基準線にできる。
- variantを子runにすると、#83のablationで列群ごとのvariantを同じ指標名で並べられる。親runのtagで同じ実行のvariantを束ねられる。
- 出力ディレクトリを正本とし、MLflowを派生の索引に限ると、ADR-038の「モデルはファイルの成果物」とも矛盾しない。

---

## Consequences

### Positive

- 設定・datamart・variantの違いによる指標を、MLflowのUIで並べて比べられる。
- バックテストのrunとPLの評価のrunを、`pl_report_sha256`と`report_sha256`で照合できる。
- 既存のCLI・report・成果物・運用の手順は変わらない。

### Negative

- 記録は手動の後処理なので、実行し忘れた結果はMLflowに現れない（出力ディレクトリからいつでも記録できる）。
- reportの形式の版を上げるたびに、このCLIの対応を更新する必要がある。
- `report_dir`のtagはローカルの絶対パスを含む。MLflowのデータベースは外へ出さない。

### Neutral / Follow-on effects

- 新しいSQLiteの作成時に、MLflowが自身のINFOの行をstderrへ出すことがある。
- `final_odds_evaluation`など、ほかのreportの形式は必要になったときに別のIssueで加える。

---

## Alternatives Considered

### Option A: 事後の取り込みCLI（採用）

Summary:

公開済みの出力ディレクトリを読み、MLflowへ記録する独立したCLI。

Advantages:

既存のCLIを変えない。MLflowの失敗が計測に影響しない。過去の結果も取り込める。

Disadvantages:

記録を忘れることがある。

### Option B: 各CLIに記録を組み込む

Summary:

`model evaluate-pl`・`model backtest-betting`に任意のoptionを加え、公開の後にMLflowへ記録する。

Advantages:

記録を忘れない。

Disadvantages:

既存のCLIの契約と終了コードの意味が変わる。記録の失敗を計測の失敗とどう区別するかを決める必要がある。
過去の結果の取り込みには別の手段が要る。

### Option C: MLflowを使わず、reportを表に集める

Summary:

複数の`report.json`から比較の表（CSVなど）を作るスクリプトにする。

Advantages:

依存も保存先も増えない。

Disadvantages:

ADR-027で導入済みのMLflowのUI・検索・グラフを使えず、年ごとの推移の比較を自前で作ることになる。

---

## Implementation Notes

- `models/experiments/report_tracking.py`（I/Oなし）が、reportのバイト列とファイルのhashから記録の内容を組み立てて検証する。
  指標の値はキーが欠けていれば拒否し、`null`のときだけ記録から外す。各runのキー（MLflowのWindowsの規則。`:`はどのOSでも拒否する）とtagの値も検査し、`config`を平らにしたキーの重複も拒否する。
- `models/experiments/tracking.py`に、registryの名前を持たないパス指定のclientと実験の取得・作成（`local_client`・
  `active_experiment_id`）を加え、既存の`local_tracking_client`・`experiment_id`はそれに委ねる（振る舞いは同じ）。
- `cli/experiment_tracking.py`が`model track-report`を持つ。MLflowはコマンドの中でimportし、`--help`では読み込まない。
  `log_batch`は1回の要求の上限（metrics 1,000、params・tags 100）で分けて送る。

---

## Validation

- `src/tests/unit/test_report_tracking.py`: 2形式の記録の内容と値、`null`の除外、拒否、長いparamの除外。
- `src/tests/integration/test_track_report_cli.py`: 一時ディレクトリのSQLiteへの記録、子runの親子関係、stepの履歴、
  重複、失敗時の`FAILED`と再記録、パスの拒否、出力ディレクトリが変わらないこと、`--help`でMLflowをimportしないこと。
- 実データの`pl-evaluation-2016-2025-graded-final3`（子run 2つ、各276指標）と`ev-betting-estimates-2016-2025-r6`
  （251指標）を、ワークツリーのローカルのデータベースへそれぞれ6秒・4秒で記録し、2回目は`already recorded`になった。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| MLflowの更新でparamやtagの長さ・名前の制約が変わる | 記録が失敗する | キー（英数字・`_`・`-`・`.`・空白・`/`、250文字以下、正規化で変わらない相対パス）とparam・tagの値の長さを記録の前に検査する。それでも失敗したらrunは`FAILED`になり、出力ディレクトリは変わらない |
| reportの形式の版が上がる | 新しいreportを記録できない | 対応しない版は明示的に拒否する。版を上げるPRでこのCLIも更新する |
| MLflowの内容を外へ貼る | ローカルのパスが漏れる | MLflowのデータベースはgit対象外の`output/`に置き、IssueやPRには貼らない |

---

## Security / Privacy Impact

外部サービスには接続しない（ローカルのSQLiteとファイルだけ）。MLflowのtelemetryは既存と同じく無効にする。
`report_dir`のtagにはローカルの絶対パスが入るため、MLflowのデータベースとartifactを外へ共有しない。

---

## Operational Impact

当日の運用と年1回の作り直しの手順は変わらない。記録は人が必要なときに実行する。MLflowのUIは
`uv run mlflow ui --backend-store-uri sqlite:///output/mlflow/mlflow.db`でローカルに起動する。

---

## Migration / Rollback

### Migration

既存の出力ディレクトリは、必要なものを`model track-report`で記録する。データの移行はない。

### Rollback

CLIを外しても、ほかのCLIと成果物に影響はない。記録したrunはMLflowのUIで削除するか、データベースを消せばよい
（出力ディレクトリから作り直せる）。

---

## Documentation Changes

- `README.md`に「評価とバックテストの結果をMLflowに記録する」の節を加える。
- `ARCHITECTURE.md`のADR-027の段落、experimentsの表、CLIの説明を更新する。

---

## Follow-up Actions

- [ ] マージの後、人の確認を得て、基準線として`pl-evaluation-2016-2025-graded-final3`と`ev-betting-estimates-2016-2025-r6`を記録する。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-26 | Accepted | 人がGATE 1で、事後の取り込みCLIとvariantごとの子runを承認した（#117） |
