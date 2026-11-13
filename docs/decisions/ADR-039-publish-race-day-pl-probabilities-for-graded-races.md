# ADR-039: 保存したPLモデルで、当日の重賞のレースごとに確率を公開する

- Status: Accepted
- Date: 2026-11-13
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #53、Refs #57・#54・#36・#35・#31・#46・#49・#61
- Supersedes: N/A
- Superseded by: N/A

---

## Context

最小運用の段階1（#57）では、JRA平地重賞の各レースについて、発走前に、保存したPLモデル（ADR-038）の確率を人へ示す。

- 当日の特徴量は、常駐CLI`datamart build-reference-prediction-live`（ADR-037）が、取得が揃ったレースから
  `<output>/<race_id>/`へ原子的に公開する。出馬表の前の段階で保留したレースは、ディレクトリを作らない。
- 特徴量の行は馬番を持たない。レースの行は、馬番から`horse_id`への対応の`canonical_hash`（`horse_mapping_sha256`）だけを持つ。
- PLモデルのAPI（ADR-038 Decision 4）は、スコア・勝率・2着以内・3着以内、特徴量との結び付き、ラベルの境界の検査を持つ。
  全組合せの確率を列挙する関数はない。
- ADR-036 Decision 4とADR-038 Decision 4は、予測の特徴量を行列にして確率を出す処理を#53へ引き継いだ。

人が決めたこと（2026-11-13、GATE 1の前）: 常駐で監視する、重賞（`jra_flat_graded_stakes_v1`）だけを予測する、出力はレースごとのJSON。

---

## Decision

1. **常駐CLI `model predict-pl-live`。** 朝に1回起動し、当日の特徴量の常駐CLIの出力（`--features-root`）を監視する。
   - オプション: `--features-root`・`--pl-model`・`--pl-model-manifest-sha256`・`--date`（JST）・`--processed-root`・
     `--snapshot-id`（省略時はCURRENT）・`--output`（存在しない新しいパス）・`--poll-interval-seconds`（既定2、1以上）。
   - 起動: 安い検査（`--poll-interval-seconds`、SHA-256の書式、`--output`が新しく、`--features-root`と互いに含まず、processed rootの外にあること）→
     モデルの読込 → 固定snapshotの`NL_RA_RACE`・`NL_SE_RACE_UMA`の固定と、対象日の出馬表の読込 → 物理ファイルの再hash →
     最も早いfreezeについて`require_prediction_after` → 出典の取得 → `--output`の作成、の順に行う。対象日の出馬表に
     宣言した場（JRAの10場）のレースが1つもなければ（日付の誤りや古いsnapshot）、起動の失敗とする。`--output`を作る前の失敗は、
     `--output`を作らない。
   - 監視: freezeの早い順に、未完了の重賞について`--poll-interval-seconds`ごとに`<features-root>/<race_id>/`の有無を見る。
     レースはfreezeの後にだけ見る。各レースを見る直前に時計を読み直す。その時点で`--features-root`が存在しなければ、
     stderrへ警告を1回だけ出す（特徴量の常駐CLIは準備の後に出力を作るので、起動時には警告しない）。
   - 全重賞が予測か保留になったら、要約をstderrへ出して終了コード0で終わる。致命的な失敗は1、中断は130とし、公開済みのレースは残す。
   - 時計と待機は注入できる（テストで実時間を待たない）。
2. **対象の決定と出馬表の共有。** 対象日のRA（`CARD_RA_COLUMNS`と`GradeCD`）とSE（`CARD_SE_COLUMNS`）を固定snapshotから読み、
   特徴量の構築と同じ正規化の関数で、レースごとに予定（`race_id`・`scheduled_start_at`・`freeze_at`）と馬番の対応を作る。
   - 特徴量の構築の処理から、`target_rows`（対象期間の行のまとめと射影）・`target_manifest`（予定と、freezeの日付の検査）・
     `card_entrants`（馬番の順の射影と馬番の対応、識別子の欠けと重複の拒否）を抽出し、構築もそれを呼ぶ（振る舞いは変えない）。
     `label_free_target_cards`がこれらを組み合わせる。そのため、対応の`canonical_hash`は、公開される`horse_mapping_sha256`と一致する。
   - 再現する保留は、出馬表だけで決まるもの（RAの行の食い違い・`HassoTime`の不正・freezeが別の日・識別子の欠け・馬番または
     `horse_id`の重複）である。stageは構築と同じ`target_pre_freeze`である。RAの行の保留のreasonは構築と同じである。SEの行の保留
     （識別子の欠け・重複）は、構築では市場とO1の検査の後に判定されるので、レースが市場の理由でも保留されるときは、構築のreasonが
     市場の理由になりうる（どちらでもレースは保留になる）。市場・履歴・計算で決まる保留は再現しない。そのレースは、特徴量の常駐CLIの公開した保留（下の4）か、発売締切の後の`features_not_published`になる。
   - 重賞の判定は、`classify_nl_ra_race_rows`（GradeCD A/B/CかつTrackCD 10〜24）をレースごとの`GradeCD`・`TrackCD`に適用する。
     同じレースの行で値が食い違い、そのどれかが重賞に当たるときは、`card`の段階の`schedule_ambiguous`で保留する。
   - 重賞でないレースは`out_of_scope`の行だけを出す。3頭未満の重賞は、起動時に`prediction`の段階の`unsupported_field_size`で保留する。
3. **確率の列挙。** `top3_order_probabilities(scores, *, temperature)`は、1レースのPLの段階の積から、馬単・3連単（順序あり）と、
   馬連・ワイド・3連複（順序なし）の全組合せの確率を返す。対数の領域で計算し（logsumexp）、順序のない券種は最後に1回だけ`exp`する。
   3頭以上を要求する。既存の周辺確率と評価用の対数確率は変えない。
4. **1レースの検査と保留。** 特徴量の読込から予測の組立までの検査に失敗したレースは、理由を付けて保留し、他のレースの監視を続ける。
   - `features`の段階:
     - `features_invalid`: `read_reference_prediction_features`が拒否した（hash・形式・`history_usable_through`・各群の
       `available_at`・市場の取得の開始時刻など）。読込のOSErrorも含む。`detail`に読込のメッセージを入れる。
     - `snapshot_mismatch`: 特徴量のmanifestの`snapshot`の`snapshot_id`、または`NL_RA_RACE`・`NL_SE_RACE_UMA`の`sha256`が、
       監視の固定と異なる・欠ける・型が違う。
     - `features_not_published`: 発売締切（発走2分前）より厳密に後になっても、特徴量が公開されない。
   - 特徴量の`held_races.json`（`ReferenceDatamartRead.held`）にそのレースが`role=target`で載っていれば、その`stage`と`reason`で保留する。
   - `prediction`の段階（`models/experiments/pl_prediction.py`）:
     `model_features_mismatch`（`require_compatible_features`）・`features_missing_race`（そのレースの行が1行でない）・
     `schedule_mismatch`（特徴量の発走・freezeの時刻がsnapshotの予定と異なる。特徴量と監視は同じsnapshotの`HassoTime`から
     予定を作るので、snapshotが一致すれば通常は起きない防御の検査である）・
     `freeze_before_model_boundary`・`horse_number_invalid`（2桁の数字でない）・`unsupported_field_size`・
     `horse_mapping_mismatch`（対応のhashが`horse_mapping_sha256`と異なる）・`horse_set_mismatch`（行の`horse_id`の集合や重複）・
     `features_rejected`（`predict_scores`の拒否。学習で欠損のなかった列の欠損・±inf・列の欠け・数値でない値）。
5. **発売締切の時刻の規則。** 特徴量が見つかれば、発売締切の後でも計算して公開し、`after_sales_close: true`を記録する
   （段階1は購入額0円のため、記録として残す）。`computed_at`と`after_sales_close`は、そのレースの計算を始める直前の同じ1回の
   時計の値から決める。締切と同じ時刻は締切前とする。
6. **出力の形式`pl_race_prediction` format_version 1。** `<output>/<race_id>/prediction.json`を`publish_directory`で公開する。
   キーを並べ替えたASCIIのJSON（字下げ2、NaNなし、末尾に改行）である。
   - `format`・`format_version`・`computed_at`（UTCのISO 8601）・`after_sales_close`
   - `race`: `race_id`・`scheduled_start_at`・`freeze_at`・`field_size`・`race_subset`・`grade_code`
   - `model`: `manifest_sha256`・`label_usable_through`・`temperature`
   - `features`: `manifest_sha256`・`market_source`・`freshness`
   - `snapshot`: `snapshot_id`と、`tables`の`NL_RA_RACE`・`NL_SE_RACE_UMA`のSHA-256
   - `horses`: 馬番の昇順。各要素は`horse_number`（2桁の文字列）・`horse_id`・`score`・`win`・`top2`・`top3`
   - `combinations`: `exacta`・`quinella`・`wide`・`trio`・`trifecta`。各要素は`horses`（馬番のリスト。順序のない券種は昇順）と
     `probability`で、馬番の辞書順に並べる。18頭なら306・153・153・816・4896件である。
   - `provenance`: 起動時の`experiment_provenance()`
   - 確率は丸めない。この形式の読込APIは作らない（利用者は人と#36）。
7. **stdoutとstderr。** stdoutは1レース1行のJSONで、キーは`race_id`・`status`（`predicted`・`held`・`out_of_scope`）・`stage`・
   `reason`・`detail`・`output`・`after_sales_close`・`win`（予測のときの馬番から勝率への辞書）である。値のないキーは`null`である。
   起動時に決まる行（`out_of_scope`と出馬表の保留）は、`--output`を作った後にレースIDの順に出す。stderrには要約
   （`graded`・`predicted`・`held`・`out_of_scope`）と、重賞がない日の旨を出す。
8. **読込の保留の一覧。** `ReferenceDatamartRead`に、検証済みの`held_races.json`の内容（`held`）を加える。学習用datamartと
   予測の特徴量の両方で返す。永続形式は変えない。

---

## Rationale

- 特徴量の常駐CLIと独立のプロセスにすると、特徴量の公開の遅れや失敗が、予測の監視を止めない。ディレクトリの出現は、
  `publish_directory`の原子的な改名なので、読み始めに不完全な特徴量を見ない。
- 出馬表の正規化を抽出して共有するので、馬番の対応と出馬表の保留が特徴量の構築と食い違わない（plan critiqueのP1）。
- 発売締切の後に見つけた特徴量も記録として公開すると、遅れの頻度を運用（#54）で測れる。購入額は0円なので、誤用の害は小さい。

---

## Consequences

### Positive

- 当日の重賞について、発走前にPLの勝率・2着以内・3着以内と全券種の組合せの確率を、モデル・特徴量・snapshotの識別と一緒に残せる。
- 予測できなかった重賞は、理由付きの1行で分かる。

### Negative

- 組合せの確率はPLそのままで、2・3着の偏りを補正していない（#49）。オッズ変動の補正もしない（#35）。
- 朝のsnapshotの後に発走時刻が変わっても、特徴量の常駐CLIも監視も検出しない。予測は変更前の予定で行い、
  `after_sales_close`も変更前の発走時刻から判定する（#31）。
- 監視はディレクトリの出現だけを見る。特徴量の常駐CLIが出馬表の前の段階で保留したレースは、発売締切まで待ってから保留になる。
- 再起動では新しい`--output`を指定する（途中からの再開はない）。既に公開された特徴量は起動の直後に予測する（発売締切の後なら
  `after_sales_close: true`）。

### Neutral / Follow-on effects

- `--help`は、LightGBM・成果物と予測の組立のモジュールを読み込まない。pyarrowと確率の関数のモジュールは、既存のCLIの登録が
  既に読み込むので、このコマンドの対象外である。

---

## Alternatives Considered

### Option A: 1回だけ実行するコマンド

Summary:

その時点で公開されている特徴量だけを予測して終わる。

Advantages:

- 実装が小さい。

Disadvantages:

- 発走ごとに人が実行する必要がある。

Reason not selected:

人間の決定（2026-11-13）。

### Option B: 特徴量の常駐CLIの中で予測する

Summary:

`build-reference-prediction-live`が特徴量の公開の直後にPLの確率も公開する。

Advantages:

- プロセスが1つで済む。

Disadvantages:

- 特徴量の契約（ADR-037）とモデル（ADR-038）が1つのコマンドに結び付き、片方の失敗が他方を止める。

Reason not selected:

責務を分け、既存の常駐CLIを変えないため。

### Option C: 監視CLIが自分でRA/SEを解釈して馬番の対応を作る

Summary:

構築と別に、監視CLIが出馬表を正規化する。

Advantages:

- 構築のコードに手を入れない。

Disadvantages:

- 重複の除き方や保留の理由が構築と食い違いうる（plan critiqueのP1）。

Reason not selected:

構築の処理を抽出して共有するため。

---

## Implementation Notes

- 確率の列挙: `models/probability/plackett_luce.py`（`top3_order_probabilities`・`OrderProbabilities`）。
- 出馬表の共有: `make_features/reference_snapshot.py`（`card_entrants`）、`models/serialization/reference_datamart.py`
  （`target_rows`・`target_manifest`・`TargetCard`・`label_free_target_cards`）。
- 読込の保留の一覧: `make_datamart/tables/reference.py`（`ReferenceDatamartRead.held`）。
- 予測の組立: `models/experiments/pl_prediction.py`（I/Oなし。`RaceTarget`・`RaceFeatures`・`build_race_prediction`・`prediction_json`）。
- CLI: `cli/pl_prediction.py`（`plan_race_day`・`watch_races`）、登録は`main.py`。

---

## Validation

- 確率の列挙の総和・周辺確率との一致・評価用の対数確率との一致・温度・極端なスコアを確かめる。
- 共有した出馬表の正規化が、構築の予定・保留・`horse_mapping_sha256`を再現し、既存の構築のテストが変更なしで通ることを確かめる。
- 予測の組立の各保留の理由、payloadのキー・順序・組合せの数・バイト列の決定性を確かめる。
- CLIで、公開・`out_of_scope`・出馬表の保留・特徴量の保留・未公開・snapshotの不一致・読込の拒否・発売締切の境界・
  前のレースの計算中の締切・起動の検査・重賞のない日・中断・helpを、時計と待機を注入して確かめる。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| PLの2・3着の偏り | 組合せの確率が系統的にずれる | 段階1は提示だけ（購入額0円）。#49で補正を検討する |
| 発走時刻の変更 | 検出されず、`after_sales_close`が変更前の予定で判定される | 人が当日の発表で確かめる。#31で追従を検討する |
| 特徴量の公開の遅れ | `after_sales_close`か未公開になる | 記録を#54の運用で集計する |

---

## Security / Privacy Impact

セキュリティやプライバシーへの影響はない。出力は認証情報を含まない。stdoutの`output`は、ローカルの出力パスを含む。

---

## Operational Impact

- 当日の朝に、完全snapshotの公開・race-day-odds・特徴量の常駐CLIを起動した後に、このコマンドを起動する。手順は#54で定める。
- `--pl-model-manifest-sha256`は、`model train-pl`の要約のSHA-256である。

---

## Migration / Rollback

### Migration

既存の形式・CLIは変わらない。`ReferenceDatamartRead`はフィールドが増えるだけである。

### Rollback

新しいCLIを使わなければよい。

---

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [ ] `docs/rules/architecture.md`
- [ ] `AGENTS.md`
- [x] `README.md`
- [ ] 運用文書・運用手順書（#54）

---

## Follow-up Actions

- [ ] 当日の運用手順を定める（#54）。
- [ ] 確率から購入案を作る（#36）。
- [ ] 実データの開催日で、勝率がモデルを直接呼んだ値と一致することと、公開の遅れを確かめる（#54）。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-13 | Accepted | 当日の重賞のPL確率の常駐CLI・出力形式・出馬表の正規化の共有を決定 |
