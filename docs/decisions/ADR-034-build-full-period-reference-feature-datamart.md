# ADR-034: 固定snapshotから全期間の参考特徴量datamartを時系列順に一度だけ構築する

- Status: Accepted
- Date: 2026-11-09
- Decision Owners: Repository maintainers
- Related Issues/PRs: Refs #33
- Supersedes: ADR-029のlabel_sources必須と読込時の再監査、ADR-030の読込時の再計算のうち、参考datamartの経路の部分のみ
- Superseded by: N/A

---

## Context

Issue #33は、年単位のtrain/valid/test（例: train〜2022・valid 2023・test 2024）で検証するために、
全期間の特徴量を時系列順に一度だけ計算してParquet datamartへ保存する方式を求めている。

[ADR-030](ADR-030-connect-pinned-snapshots-with-explicit-reference-assumptions.md)の参考経路
（`model prepare-reference-input`）は、明示したレースごとに、固定snapshotの原投影から全21群を計算し、
原投影・出典catalog・依存集合をprepared JSONへ保存する。モデルの読込時には原投影から正規化と
全21群計算を再実行して照合する（[ADR-029](ADR-029-project-calculated-features-into-strict-model-inputs.md)・ADR-030）。

この経路は大規模に耐えない。2026-11-08のベンチマークでは、1開催日36レース・履歴1年の準備に264秒かかり、
1.38GBのJSONになった。2026-11-09のプロファイルでは、対象レースごとに次の処理が履歴全体に比例していた。

- `prepare_context`が履歴全体を検証・並べ替え・索引し直す。
- `adjusted_history`が馬の過去出走ごとに、その時点の基準レース集合を履歴全体から作り直す
  （31対象で`historical_as_of`が1,222回、`validate_race`が約211万回）。
- `result()`が群ごとに全履歴レースのevidenceとrace IDを依存に加える。
- 血統適性・対戦グラフが全履歴を走査し、正規化がレースごとに全馬の血統とcoverageを作る。

履歴を2005年からにすると、対象1レースあたりの処理は約20倍になり、20年分の構築と読込時の再計算は
成り立たない。

関連するADRは次のとおりである。[ADR-012](ADR-012-feature-intermediate-tables-and-datamart.md)の
datamartは特徴量中間表の順序付き左結合であり、このADRのdatamartはそれとは別の種類である。ADR-012 §4の
結合規則は変えない。[ADR-027](ADR-027-manage-ranking-experiments-with-hydra-and-mlflow.md)の学習・予測と
MLflow管理、[ADR-028](ADR-028-calculate-all-feature-groups-from-timestamped-observations.md)の21群の計算式と
時点の規則は変えない。datamartからの学習は次のタスクで決める。

---

## Decision

1. 新しいCLI `datamart build-reference`が、固定したprocessed snapshot（CURRENTを最初の一度だけ解決するか、
   `snapshot_id`を明示）から、`target_start`〜`target_end`の`NL_RA_RACE`の中央全レースを対象に、
   ADR-030と同じ参考規則・同じ21群の計算器で特徴量を計算し、datamartへ保存する。
   予定発走時刻は保存された`HassoTime`、freezeはその300秒前とする（ADR-030のmanifest規則と同じ）。
2. 履歴の範囲は既存の意味を維持する。`history_start`以降の採用可能な通常結果全頭を使い、遡及期間の窓は
   導入しない。
3. 計算は時系列順に一度だけ行う。各履歴レースは一度だけ正規化・検証し、開始順の1本の配列に置く。
   参考結果の利用境界は日単位（JSTの0時）なので、同じJST日付の対象が見る履歴はこの配列の接頭辞であり、
   過去出走の時点の基準集合はより短い接頭辞である。馬・騎手・調教師の索引、窓付き母集団、基準集合の
   統計、PageRankのグラフ（半減期がnullのとき）を日付ごとに共有する。freezeの時刻に依存する値
   （調教の窓、EWMA、市場、半減期付きのPageRank、coverageのevidence）は対象ごとに計算する。
4. 共有の見方は既存の対象ごとの経路と同じ集合・同じ順序を返し、浮動小数の総和順序も変えない。
   値の一致はfixtureでの同値テスト（全数値列・群ごとの`available_at`・着順・保留理由）で保証する。
5. datamartの経路だけ、各群の依存は「`available_at`と`event_at`の最大値を与えるevidence」に要約する。
   参考経路では出馬表のevidenceが常にfreezeで利用可能になるため、各群の`available_at`は常に
   `freeze_at`と等しい。この最大値の比較は漏洩の検出にならないため、漏洩への防御は次の不変条件で行う。
   - 履歴の接頭辞の全レースは、開始日が`history_start`以後かつ対象のJST日付より前で、利用境界が
     対象のfreeze以下である（配列の末尾の値でO(1)に検査する）。
   - 過去出走の時刻`t`の基準集合は、利用境界が`t`以下で、開始日が`t`の日付より前である。
   - 調教は、対象のfreezeから`days_window`日前以後で、日付が対象日より前、利用境界がfreeze以下である。
   - 出馬表・パラメータ・市場・coverage・血統のevidenceはfreeze以下である（対象ごとに検査する）。
   - evidenceの版は、全期間で`(source, observation_id, version)`を鍵とする登録表で一度だけ照合する。
6. 計算器が`ValueError`を出した対象（市場anchorの鮮度超過、PageRankの非収束など）は、datamartの経路だけ、
   `stage=calculation`と理由を付けてレース全体を保留し、構築を続ける（2026-11-09の人間の決定）。
   対象ごとのcontextの検証で`ValueError`が出た対象（二つの市場anchorの観測が同じO1発表と異なるO2発表を
   組み合わせて衝突する場合など）も、`stage=target_pre_freeze`として保留する（同日の人間の決定）。
   上の5の不変条件の違反と、全期間のevidence登録表での版の衝突（いずれも`ChronologicalInvariantError`）、
   coverageの要求の不足、年単位の入力の検証（RA/SEのprojection、調教の正規化と版の衝突）の失敗、
   出力の投影の失敗（±infなど）、`ValueError`以外の例外、読込時の検証の失敗では構築全体を失敗させる。
   既存の`prepare-reference-input`の動作は変えない。
7. 永続形式（format_version 1）は次のとおりとする。
   - `year=<YYYY>/part-0.parquet`: 馬ごとの行。`race_id`、`horse_id`、`scheduled_start_at`、`freeze_at`、
     閉じた数値列一覧の全列（float64、NaNはnull）、群ごとの`<group>__available_at`、`finish_position`。
   - `year=<YYYY>/races.parquet`: レースごとの行。`field_size`、`label_usable_after`、`result_delay_days`、
     `label_raw_sha256`、`horse_mapping_sha256`、`history_usable_through`。
   - `held_races.json`: 保留したレース、役割（history/target）、段階
     （history_result/target_pre_freeze/target_outcome/calculation）、理由。
   - `manifest.json`: 計算契約（全列を選んだ`snapshot_reference_21_groups_v1`）、列一覧、snapshotの表の
     SHA-256、参考保証、ラベルの保証区分（`REFERENCE_LABEL_ASSURANCE`と`label_boundary_meaning`
     `declared_usable_after`）、検証区分`build_time_audit_no_read_recomputation_v1`、各ファイルのSHA-256と件数、
     コードと環境の識別情報、解決済み設定。
   - 出力はstagingに書き、全ファイルを読込APIで検証した後に、ディレクトリのrenameで公開する。失敗時は
     stagingを削除する。
8. ADR-029/030の照合のうち、datamartの経路では次のとおりとする。
   - 構築時に残す: 既存の正規化・保留・projection検証、上の不変条件、各計算器の検証、
     `build_explanatory_variables`の値と`available_at`の監査、公開前の全ファイルの読込検証。
     ただし`build_explanatory_variables`の`contains_target_result`・`contains_future_data`は常にFalseで
     渡され、datamartでは`source_race_ids`が空のため、それらの検査は効果がない。漏洩への実際の防御は
     上の不変条件と、出力の各`available_at` ≤ `freeze_at`の検査である。
   - 読込時に残す: manifest・held_races・各Parquetのhash、schemaとmetadata、計算契約のhash、列一覧、
     行ごとの時点（各`available_at` ≤ `freeze_at`、freezeのずれ、`history_usable_through` ≤ `freeze_at`、
     `label_usable_after`の再計算との一致）、キーの一意性、レースごとの行数と着順の連続性。
   - datamartでやめる: 原投影・出典catalog・依存集合・ラベル原行の保存と、読込時の21群の再計算。
     ラベルの「元の証拠」は、snapshotの表のSHA-256とレースごとのダイジェストに置き換わる。必要なら
     固定snapshotから再導出できる。prepared JSONの経路では、ADR-029/030の照合をそのまま続ける。

   既存の各検査の扱いは次のとおりである。

   | 既存の検査 | datamartでの扱い |
   | --- | --- |
   | `historical_race`・`validate_race`・履歴の保留 | 全期間で各レース一度 |
   | `select_versions`（履歴） | 構造上成り立つ（race_idの重複を追加時に拒否し、各レースは版1） |
   | `select_versions`（調教） | 対象年の調教の読込ごとに一度 |
   | `select_versions`（血統） | 構造上成り立つ（馬ごとに一度だけ作る） |
   | `select_versions`（市場・coverage）、`validate_card`、coverageの区間 | 対象ごと |
   | `latest_o1`の同じ発表時刻の行の衝突 | 対象ごと。ただし射影した列だけで判定する（prepared JSONの経路は選んだ発表の原行全列で判定する） |
   | coverageの母集団の完全性 | 構造上成り立つ（日付の履歴馬と出馬表から作った母集団を同一性で照合） |
   | 調教の項目と区間の検証 | 対象年の調教の読込ごとに一度 |
   | 血統の対応の完全性 | 履歴馬は日付ごとに一度、出馬表の馬は対象ごと |
   | `validate_evidence_version` | 全期間の登録表（履歴・血統・出馬表・coverage・市場）。調教は読込ごと |
   | `build_explanatory_variables` | 対象ごと（`contains_*`と`source_race_ids`の検査は効果なし） |
   | `validate_reference_payload`・`parse_reference_labels` | datamartではやめる（読込APIの検証に置き換える） |

---

## Rationale

- 履歴の接頭辞と日単位の共有で、対象ごとの処理を履歴の長さからほぼ切り離せる。計算式・閉じた数値列・
  参考規則は変えないため、既存の参考経路とテストで突き合わせられる。
- 読込時の再計算は全期間では成り立たない。構築時に既存の監査を実行し、hashと契約で同一性を固定すれば、
  学習時の検証は軽い検査だけで済む。
- 計算器の例外で20年分の構築全体を止めると、実データの1年分すら通らない可能性が高い。保留を理由付きで
  記録すれば、評価母集団から外したレースを後で数えられる。

---

## Consequences

### Positive

- 全期間の特徴量を一度だけ計算し、年単位のfoldで再利用できる。
- 構築時の監査とhashで、学習入力の同一性と時点の境界を確かめられる。

### Negative

- 読込時に原本から再計算しないため、構築コードの不具合を読込時には検出できない。同値テストと構築時の
  不変条件に依存する。
- 2005年からの全履歴を正規化済みオブジェクトとして保持するため、ピークメモリが数GBになる。
- 途中再開がないため、長い構築が途中で失敗すると最初からやり直しになる。
- 計算中の例外による保留は、既存の参考経路（全体を失敗させる）と動作が異なる。

---

## Alternatives Considered

### Option A: 遡及期間の窓（例: 3年）で履歴を切る

Summary:

対象ごとの履歴を一定期間に限り、計算量を一定にする。

Advantages:

- 実装が単純で、メモリも一定になる。

Disadvantages:

- 通算出走数や血統の産駒成績などの値が変わり、計算契約が変わる。

Reason not selected:

人間が、既存の特徴量の定義を変えない固定開始日を選んだため。

### Option B: prepared JSONを期間ごとに分割する

Summary:

既存の`prepare-reference-input`を小さな期間ごとに実行する。

Advantages:

- 既存の契約と読込時の再計算をそのまま使える。

Disadvantages:

- 対象ごとに全履歴を処理する費用が変わらず、20年分では時間とサイズが成り立たない。

Reason not selected:

Issue #33の規模の要件を満たさないため。

### Option C: 読込ごとに抽出したレースを再計算して照合する

Summary:

学習でdatamartを読むたびに、決定的に選んだ少数のレースを既存の参考経路で再計算する。

Advantages:

- 実データでの一致を読込ごとに確かめられる。

Disadvantages:

- 1レースの再計算にも全履歴の正規化が要り、読込が遅くなる。

Reason not selected:

人間が、構築時の監査とhashに限る方針を選んだため。

### Option D: 21群をベクトル化して再実装する

Summary:

pandasやArrowで特徴量を一括計算する新しい実装を作る。

Advantages:

- 計算は速くなりうる。

Disadvantages:

- 21群の式を二重に持ち、既存の計算器と一致する保証がなくなる。

Reason not selected:

同じ計算器を共有する方が、値の一致を保ちやすいため。

### Option E: 並列実行

Summary:

対象の日付ごとに複数プロセスで計算する。

Advantages:

- 実時間を短くできる。

Disadvantages:

- 履歴索引とメモリをプロセスごとに持つ必要があり、依存も増える。

Reason not selected:

まず単一プロセスで計測し、必要なら後続で判断するため。

---

## Implementation Notes

- 共有の時系列索引と日付ごとの見方は`src/make_features/generation/chronological.py`、取得口の既定の実装は
  `src/make_features/generation/observations.py`にある。計算器は取得口を通して窓・索引・基準集合を読む。
- 対象1レースの正規化は`src/make_features/reference_snapshot.py`の`normalize_reference_target`に分け、
  既存の`normalize_reference_input`と共有する。
- 構築の組立は`src/models/serialization/reference_datamart.py`、ファイル契約と読込APIは
  `src/make_datamart/tables/reference.py`、stagingと公開は`src/data/storage/directory_publisher.py`、
  CLIは`src/cli/reference_datamart.py`、Hydra設定は`configs/reference_datamart/`にある。
- RA/SEは年ごと、調教は対象年の窓ごと、O1/O2は開催日ごとに読む。O1/O2のfooterは大きいため、
  対象年の間はdataset handleを使い回す。計画と異なり、O1とO2のhandleは同時に開き、キー列だけの先読みは
  しない。`latest_o1`は同じ発表時刻の行の内容の衝突を全行で調べるため、キー列だけでは値を再現できない。
  調教は対象年の窓の分をまとめて`Workout`にする。計測したピークメモリは
  [計測結果](../experiments/reference-feature-datamart.md)に記す。

---

## Validation

- 複数日・同日の複数レース・年またぎ・異常結果・境界の調教を含むfixtureで、datamartの全数値列・
  `available_at`・着順・保留理由が、全列を選んだ既存の`prepare_reference_payload`と一致することを、
  5通りの計算設定で確かめる。
- 利用境界の前の結果、対象の当日結果・確定後の値、freeze後の市場、当日の調教が特徴量を変えないこと、
  後の対象の有無や行順で既存の行が変わらないことを確かめる。
- 不変条件の違反、読込時の改変（hashを更新した意味上の改変を含む）、計算中の例外の保留を確かめる。
- 実データでの処理時間・ピークメモリ・サイズの計測と20年分の外挿は
  [参考特徴量datamartの構築と計測](../experiments/reference-feature-datamart.md)に記す。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 共有の見方の順序や依存要約のずれ | 値が静かに変わる | 全列の同値テストを5通りの設定で行う |
| 漏洩の検出を最大時刻に頼る | 未来の情報が入っても検出できない | 見方ごとの不変条件と漏洩テストで防ぐ |
| 長い構築の途中失敗 | 最初からやり直しになる | 年ごとの進捗を出し、対象年ごとに別の出力で構築できる |
| 結果由来の対象保留 | 評価母集団の選び方にfreeze後の情報が入る | 保留の段階を記録し、次のタスクで報告する |
| 対象ごとの母集団の複製とcoverageのhash | 履歴の馬数に比例する費用が対象ごとに残る | 計測の外挿に含める。日付ごとの共有は後続で検討する |

---

## Security / Privacy Impact

外部への通信や新しい資格情報はない。datamartは`data/`や`output/`などgit管理外のローカルに保存し、
JRA-VANの生データ値を含むためリポジトリへ入れない。

---

## Operational Impact

全期間の構築は長時間になる。年ごとの進捗がstderrに出る。

---

## Migration / Rollback

### Migration

既存のprepared JSONと学習済みモデルはそのまま使える。datamartは新しい出力として別に構築する。

### Rollback

`datamart build-reference`と関連モジュールを削除しても、既存の参考経路と学習・予測は影響を受けない。

---

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `docs/rules/architecture.md`
- [x] `README.md`
- [x] `docs/table-definition/README.md`
- [x] `docs/experiments/reference-feature-datamart.md`
- [x] ADR-029・ADR-030の`Superseded by:`行

---

## Follow-up Actions

- [ ] 年単位fold、validによるearly stopping、fold内のラベル利用境界の監査、datamartからの学習（#33）。
  同時刻のfreeze_atを持つ別レースの順序の扱いもここで決める。
- [ ] 計測で20年分の構築が長すぎると分かった場合、対象年ごとの別出力での運用、途中再開、並列化を検討する。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-09 | Accepted | 全期間の参考特徴量datamartの構築方式と、ADR-029/030の照合の残し方を決定 |
