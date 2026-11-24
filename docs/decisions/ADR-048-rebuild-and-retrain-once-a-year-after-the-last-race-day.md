# ADR-048: 前年の最終開催日の後に学習用datamart・PLモデル・推定器を年に1回作り直して同時に切り替える

- Status: Accepted
- Date: 2026-11-21
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #55、Closes #47、Refs #57・#66・#72・#111
- Supersedes: ADR-038の決定2のうち運用の年（train 2006〜2024年・valid 2025年）の固定のみ（あわせて、ADR-038 Amendment 1の手順3を年明けの作り直しについて決定9で改め、ADR-047の決定6の「その年の固定したPLモデル」を決定7で開催日ごとのPLモデルに改める）
- Superseded by: N/A

---

## Context

当日の購入案の推定器は対象年と同じ年の成果物でなければ起動できず、翌年の購入案には、前年までをtest年とするPL評価、購入方策のバックテスト、翌年の推定器が必要である。さらに、当日の特徴量とPLモデルは、同じ学習用datamartのmanifestで結び付く。datamartだけを更新しても、モデルと当日の特徴量を安全に組み合わせられない。

学習用datamartは固定snapshotから全期間を一度に構築できる。2006〜2025年を対象とした再構築は約2時間37分、ピークcommitは約8 GBだった。年に1回の実行なら、年ごとの出力を束ねる仕組みや途中再開を加えずに全期間を作り直せる。

2026年は既存の成果物を使い続ける。初回の作り直しは2026年の最終開催日の後に、2027年向けとして行う。

当日に残した特徴量は、その日に結び付いたPLモデルでなければ採点できない（`source_datamart`の一致、ADR-038決定4）。ADR-047の決定6は、当日に残した全レースの特徴量から、その年の固定したPLモデルで後から確率を計算する。

## Decision

1. **周期と時期**: 年に1回、年`Y−1`の最終開催日の翌日（JST）以後、年`Y`の最初の開催日より前に作り直す。年の途中には作り直さない（例外は決定9）。
2. **固定snapshot**: 最終開催日の翌日（JST）以後に`latest`、続けて`historical-odds`を実行する。historical-oddsは実行日の前日までのレースだけを対象とするため、最終開催日の当日に実行すると、その日のレースは取得の対象にも`--plan-only`の残りにも入らない。完全Parquetのsnapshotは`latest`も公開する。historical-oddsの実行のうちでは、`--plan-only`でない実行が全年の取得を終え、公開を待つ年があるときにだけ再構築して公開し、`--plan-only`と`--confirm-provider-missing`は公開しない。そのため、`--confirm-provider-missing`を使ったら、その後に`--plan-only`なしで`historical-odds`を実行し直す。`failed/empty_response_unverified`以外の`failed`は、原因を直して実行し直す。最後の`--plan-only`なしの実行が、終了コード0で、`Complete Parquet rebuild failed.`を出さずに終わったことを確かめる。続く`--plan-only`（rawだけを見るので、取得の完了だけを示す）の出力が`"year": null`と`"requested_specs": 0`を示してから、CURRENTのIDを控える。以後の段階はこのsnapshotだけを読む（評価・バックテスト・推定器は、datamartとreportに記録されたsnapshotを読む）。race-day-oddsの実行中には行わない。
3. **全期間のdatamartを作り直す**: 決定2のsnapshotから、対象を2006-01-01〜年`Y−1`-12-31、履歴を2005-01-01からとして、`measure`と同じ計算設定・参考規則で1回だけ構築する。年ごとの別出力、束ね、途中再開は作らない。失敗時は同じsnapshotと設定で、新しい出力先に作り直す。
4. **段階の順序と年の値**: `datamart build-reference`、`model evaluate-pl`、`model backtest-betting`、`model fit-betting-estimator`、`model train-pl`の順に行う。test年は2016〜年`Y−1`、推定器は年`Y`、最終学習はtrain 2006〜年`Y−2`・valid 年`Y−1`とする。年ごとに変わる値は`--override`で渡し、解決済みの設定は各成果物のmanifestまたはreportに残す。順序はADR-038 Amendment 1の評価、バックテスト、推定器、学習と同じである。この決定は、ADR-038決定2の運用の年（train 2006〜2024年・valid 2025年）の固定を、年ごとのこの規則に置き換える。LightGBMの引数・反復数・温度の範囲を評価と同じにする規則は変えない。
5. **同時の切替と切替前の確認**: 学習用datamart、PLモデル、推定器の3つを、開催日の前日の夜に同時に切り替える。開催日の途中には切り替えない。切替前に次を確かめる。
   - `datamart build-reference`・`model fit-betting-estimator`・`model train-pl`のstdoutの要約の`manifest_sha256`が、各`manifest.json`のSHA-256（小文字の16進）と一致する。`model evaluate-pl`と`model backtest-betting`はSHA-256を出力しないため、`report.json`・`predictions.parquet`のSHA-256を記録し、次の段階がその値で固定して照合する。
   - 評価とバックテストの`report.json`のtest年が2016〜年`Y−1`のちょうどすべての年であり、推定器の`target_year`が年`Y`、最終モデルのvalid年が年`Y−1`である。途中の年の抜けは推定器の`target_year`を変えず、CLIは検出しない（年`Y−1`が抜けると`target_year`が年`Y−1`になり、購入案の常駐CLIが年`Y`の`--date`で起動を拒否する）。
   - PLモデルの`training.label_usable_through`が、切替後の最初の開催日の最も早いfreezeより前である。
   - 前年の記録と、test年`Y−1`の成績、回収率と95%区間、推定器の`method`・`α`・`β`を並べる。ADR-042〜045の採否・方策・方法を変えうる結果は人間が判断する。提示額は0円のままとする。
6. **間に合わない場合と切り戻し**: 新しい3成果物が間に合わない、起動に失敗する、または決定5のラベル境界を満たさない場合は、特徴量と予測の常駐CLIを前年のdatamartとPLモデルで動かし、購入案の常駐CLIは起動しない（前年の推定器は年`Y`に起動しない）。新しい版の問題による切り戻しも同じとする。前年の版で運用した開催日を記録する。
7. **版の記録・保持と作り直し後のPR**: 出力名には対象期間または対象年を入れる。例は`output/reference-datamart-2006-<Y−1>`、`output/pl-final-model-2006-<Y−1>`、`output/ev-betting-estimator-<Y>`である。成果物は`manifest.json`のSHA-256で識別する。運用中の3成果物のパスとSHA-256、固定snapshotのID、切替日を`docs/retraining-operation.md`に記録する。運用した学習用datamart・PLモデル・推定器は消さずに残す。当日に残した特徴量は、その開催日に結び付いたPLモデルでしか採点できないためである。ADR-047の決定6の「その年の固定したPLモデル」は、この決定で「その開催日に結び付いたPLモデル」に改める（決定6・決定9により、同じ年に複数のモデルがありうる）。版の表は切替のたびに行を足し、前の行を残す。決定6で前年の版を使った開催日は、`docs/retraining-operation.md`の表に記録する。各開催日のモデルは、この2つの表で決まる。作り直し後に、`configs/pl_evaluation/measure.yaml`と`configs/betting_backtest/measure.yaml`の`test_years`、`configs/pl_training/final.yaml`の`valid_year`、それらの値の年を書いた2つのファイルの先頭のコメント（`configs/pl_evaluation/measure.yaml`の「test 2016-2025」、`configs/pl_training/final.yaml`の「train 2006-2024 ... 2025」）、それらの運用の年を固定して確かめるテスト、READMEのPLの評価と最終学習の節に書いた年、実験の記録、版の表を更新するPRを作る。`configs/betting_backtest/measure.yaml`の「計測の後に値を変えない」という注記は、ADR-043・044で固定した方策と補正の値についてのものであり、`test_years`はその対象ではない。初回のこのPRで、注記の対象をそれらの値に限るよう書き直す。
8. **historical-oddsの対象年**: 年`Y`の時系列オッズを取得するには、`[historical_odds.batch].last_year`を`Y`へ上げ、進捗台帳を移行するコードの変更が必要である。この変更は、年`Y`の作り直しを記録するPRまでに、#111として別に行う。
9. **臨時の作り直し**: LightGBMの更新（ADR-038決定3）、閉じた数値列・計算契約・特徴量の定義（`configs/features.toml`）の変更、ADR-038 Amendment 1による`bin_construct_sample_cnt`の変更のときは、同じ年の範囲（datamartの対象〜年`Y−1`、test年2016〜年`Y−1`、推定器は年`Y`、valid 年`Y−1`）で決定2〜7の手順を行う。
   - 年の途中に行うときは、新しい版へ切り替えるまで、今の3成果物（推定器を含む）で運用を続ける（ADR-038 Amendment 1の手順3と同じ）。切り戻しも今の3成果物へ戻す。
   - 計算契約・閉じた数値列・特徴量の定義の変更では、当日の特徴量の常駐CLIが、実行中のcheckoutから計算した契約・列・定義と異なる学習用datamartを拒否する。LightGBMを更新すると、前の版のPLモデルは読めない（ADR-038決定3）。そのため、臨時の作り直しの決定3〜4の段階は、当日の運用に使うcheckoutと環境とは別のcheckout・環境（変更のブランチのworktreeなど）で行い、当日の運用のcheckoutと環境は切替の夜まで前のコードと依存のままにする。`data/`と`output/`はgitの対象外で、取得の設定はデータのパスをcheckoutからの相対パスで決めるため、決定2の取得とsnapshotの固定は当日の運用のcheckoutで行う。別のcheckoutでは、運用のcheckoutの`data/processed`と`output/`を絶対パスで指定し、成果物を別のcheckoutの中に置かない（worktreeを消すと中の成果物も消え、決定7の保持が守れないため）。臨時の作り直しは年明けと同じ年の範囲なので、決定7の出力名は運用中の成果物と重なる。各CLIは既存の出力先を拒否するため、出力名の末尾に`-r2`・`-r3`のように版の番号を付ける（まだ使っていない次の番号を選ぶ。例: 運用中の`output/pl-final-model-2006-2026`に対して`output/pl-final-model-2006-2026-r2`）。切替の夜に、コード・依存と3成果物を一緒に替え、切り戻しは両方を戻す。
   - LightGBMの更新の後は、前の版のPLモデルで当日に残した特徴量を採点できない。決定7の後からの採点は、更新の前に済ませるか、前のLightGBMの環境で行う。
   - 年明けの作り直しの中で`model train-pl`が欠損の枝の照合で拒否されたときは、ADR-038 Amendment 1のとおり評価と最終学習の両方の設定の`lightgbm`に同じ`bin_construct_sample_cnt`を入れ、評価から最終学習までをやり直す。やり直す段階の出力名には、臨時の作り直しと同じく`-r2`のような版の番号を付ける（成功した段階の出力先は既にあり、各CLIは既存の出力先を拒否する）。その設定の変更は作り直し後のPRに含める。やり直しが終わるまでは決定6に従う（年`Y`では年`Y−1`の推定器を使えないため、ADR-038 Amendment 1の「今の推定器」で運用を続けることはできない）。

## Rationale

- 固定snapshotと全期間の再構築により、過去データの訂正を反映しつつ、評価、バックテスト、推定器、最終学習が同じ入力を参照する。
- 1つのdatamart manifestをモデルと当日の特徴量で照合する既存の契約を保てる。
- 年に1回なら約3時間の構築は許容でき、年別の出力、束ね、途中再開の永続形式や復旧規則を増やさずに済む。
- 推定器だけを前年のまま使うことは年の検査で拒否されるため、切替失敗時は購入案を止める必要がある。

## Consequences

### Positive

- 翌年の購入案に必要な推定器を、前年までの評価とバックテストから再現可能に作れる。
- datamart、PLモデル、推定器を同時に切り替えるため、manifestの不整合を避けられる。
- 版、snapshot、切替日を運用文書に残し、当日の入力を追跡できる。

### Negative

- 最終開催日から最初の開催日までの短い期間に、取得、再構築、評価、確認を終える必要がある。
- 新しいモデルのラベル利用境界が最初の開催日に間に合わないことがあり、その場合は購入案を出せない。
- 年の値を`--override`で渡すため、運用者はtest年、valid年、出力名を相互に照合する必要がある。

### Neutral / Follow-on effects

- `configs/`の年の値は初回の作り直しでは変更しない。作り直し後の記録PRで更新する。
- historical-oddsの対象年を延長する台帳移行は、この決定の実装範囲外である。

## Alternatives Considered

### Option A: 年別のdatamartを別出力で構築して束ねる

Summary: 新しい年だけを構築し、既存年の出力と結合して学習用datamartにする。

Advantages: 年次の構築時間を短くできる可能性がある。

Disadvantages: 複数manifestの整合、過去データの訂正、束ねた出力の検証と切替を新たに設計する必要がある。

Reason not selected: 年に1回の約3時間の構築を許容すれば、既存の1つのmanifestによる照合を保てるため。

### Option B: 途中再開を実装して既存の出力へ追記する

Summary: 年ごとの構築途中の状態を保存し、失敗後に同じ出力へ再開する。

Advantages: 長時間の構築が失敗したときの再計算を減らせる。

Disadvantages: stagingと公開済み出力の整合、再開可能な中間状態、失敗時の復旧規則を永続契約として追加する必要がある。

Reason not selected: 現在の構築は失敗時にstagingを削除して何も残さない。年1回の実行では、同じ固定snapshotから新しい出力先に再実行する方が単純である。

## Implementation Notes

コード、CLI、設定形式、成果物形式は変更しない。具体的な手順、出力名、SHA-256の照合、切替と切り戻しは[年次の再学習手順](../retraining-operation.md)に記す。

当日の特徴量、予測、購入案の常駐CLIは、切替後も[当日の運用手順](../race-day-operation.md)の入力規則に従う。`--snapshot-id`は前日の夜に固定するCURRENTのIDであり、学習用datamartの構築に使ったsnapshotとは別に当日の入力として固定する。

## Validation

- 初回の年`Y`=2027の実行で、固定snapshotから2006〜2026年のdatamart、2016〜2026年の評価とバックテスト、2027年の推定器、valid 2026年の最終モデルを作る。
- datamart・推定器・最終モデルのstdoutの要約の`manifest_sha256`を`manifest.json`のSHA-256（小文字）と照合し、当日の常駐CLIへ渡す値として記録する。評価とバックテストの出力のSHA-256は、次の段階の固定の照合で確かめる。
- 切替前に、PLモデルのラベル利用境界、前年との評価・バックテスト・推定器の比較、当日の常駐CLIの起動を確認する。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 年末年始にhistorical-oddsまたは再構築が失敗する | 最初の開催日に購入案を出せない | 最終開催日より前からhistorical-oddsを進め、失敗時は前年の特徴量・予測だけを使う |
| 新しいモデルのラベル利用境界が最初の開催日に届かない | 新しいモデルで予測できない | 切替前に最も早いfreezeと照合し、届かなければ前年の版を使う |
| `--override`の年を誤る | 年の抜けた評価または不適切な推定器になる | reportのtest年、推定器の`target_year`、最終モデルのvalid年を切替前に照合する |
| #111が未完了で時系列オッズの対象年を延長できない | 翌年の作り直しに必要なオッズが欠ける | 台帳移行を年`Y`の作り直しを記録するPRまでに別途行う |

## Security / Privacy Impact

セキュリティやプライバシーへの重大な影響はない。既存のローカルデータと成果物を読むだけで、認証情報、個人データ、外部への送信を新たに扱わない。

## Operational Impact

年に1回、人が`latest`、historical-odds、datamartの再構築、評価、バックテスト、推定器、最終学習、切替を順に実行する。datamartのピークcommitは約8 GBであるため、開催日のrace-day-oddsと重ねない。所要時間と操作は[年次の再学習手順](../retraining-operation.md)に従う。

## Migration / Rollback

### Migration

既存の成果物形式は変えない。初回の切替で、運用中の3成果物のパスとmanifestのSHA-256を2027年向けの値へ同時に更新する。

### Rollback

新しい版が起動できない、または切替後に問題が出た場合は、前年のdatamartとPLモデルへ戻し、購入案の常駐CLIを起動しない。前年の推定器を年`Y`で使わない。運用した成果物は消さずに残す（決定7）。臨時の作り直しの切り戻しは決定9に従う。

## Documentation Changes

- [x] `README.md`
- [x] `docs/race-day-operation.md`
- [x] `docs/retraining-operation.md`
- [x] ADR-034・ADR-038のFollow-up
- [x] ADR-038・ADR-047のヘッダとDecision History（このADRが改める部分）
- [x] `docs/experiments/pl-final-model.md`

## Follow-up Actions

- [ ] 初回の2027年向け作り直しを実行し、実験の記録と版の履歴を更新する（#57）。
- [ ] `[historical_odds.batch].last_year`の年次延長と進捗台帳の移行を行う（#111）。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-21 | Accepted | GATE 1の前に人間が、年1回の全期間再構築、3成果物の同時切替、切替失敗時の購入案停止を決定した |
