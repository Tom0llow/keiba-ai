# 年次の再学習手順

## 目的と範囲

[ADR-048](decisions/ADR-048-rebuild-and-retrain-once-a-year-after-the-last-race-day.md)に従い、年に1回、学習用datamart、PLモデル、当日の購入案の推定器を作り直して同時に切り替える手順である。対象は前年の最終開催日の翌日（JST）から翌年の最初の開催日より前までとする。提示額は常に0円であり、この手順で購入の判断や購入の実行はしない。

この手順は人が実行する。作り直しと切替を自動化しない。当日の特徴量、予測、購入案の常駐CLIは[当日の運用手順](race-day-operation.md)に従う。

## 時期と所要時間の目安

最終開催日の翌日（JST）以後に開始し、最初の開催日より前に終える。historical-oddsは実行日の前日までのレースだけを対象とするため、最終開催日の当日の夜に始めると、その日のレースが取得から漏れる。2027年向けの初回では、2026年の最終開催日の翌日以後に実行する。年ごとに`Y`を翌年として読み替える。

- datamartの全期間再構築は約2.6〜3.1時間、ピークcommitは約8 GBである。
- PL評価は、2 variantのときに約20分だった。[ADR-051](decisions/ADR-051-add-calculated-card-and-history-columns-and-decide-at-the-yearly-rebuild.md)で7 variantにしたため、約1時間かかる（試行の実測で約59分・ピークcommit約4 GB、[計算済みの列の追加の試行](experiments/pl-added-columns.md)）。購入方策のバックテストは約7分、推定器の作成は約3〜3.5分（いずれも2 variantの評価結果での実測）、最終学習は約2分である。7 variantの評価結果でも、バックテストは約3分、推定器の作成は約3分、ピークcommitはどちらも約3.5 GBだった（試行の実測）。
- 最終開催日より前からhistorical-oddsを進めておく。race-day-oddsまたは開催日の常駐CLIと、datamartの構築を重ねない。

## 2027年向けの作り直しでの注意（ADR-051）

[ADR-051](decisions/ADR-051-add-calculated-card-and-history-columns-and-decide-at-the-yearly-rebuild.md)は閉じた数値列に8列を加えた。この変更のコードは、それまでの36列の学習用datamartを、特徴量の常駐CLI・`model evaluate-pl`・`model train-pl`で拒否する。そのため、この変更のPRは2027年向けの切替の夜にマージする。2027年向けの作り直しは「臨時の作り直し」の節と同じく、手順1の取得とsnapshotの固定を当日の運用のcheckoutで行い、手順2〜6をこの変更のブランチのworktree（別のcheckout・環境）で、運用のcheckoutの`data/processed`と`output/`を絶対パスで指定して行う。このブランチのコードは、切替の夜まで当日の運用のcheckoutに入れない（このPRのマージ前なら、当日の修正などのために運用のcheckoutでmainを`git pull`するのは差し支えない）。切替の夜は、運用のcheckoutの`git rev-parse HEAD`を記録してから、PRのマージの後に運用のcheckoutを`git pull`で更新し、「切替」の節の新しい3成果物で常駐CLIを起動する。切り戻しでは、運用のcheckoutで記録したコミットを`git checkout`し、前年のdatamartとPLモデルで常駐CLIを動かす。その後に当日の修正をmainから取り込むには、先にこの変更を取り消すPRが要る（rulesetがCIと最後のpushへの承認を求めるので、切替の夜には間に合わない）。記録したコミットの`git checkout`では運用のcheckoutがブランチから外れ、`git pull`できない。取り消しのPR（または直した版）がマージされたら、`git switch main`と`git pull`でブランチへ戻す。

手順2の前に、このブランチにmainを取り込み、PRを最新にしておく。作り直しの成果物は、取り込んだ後のコードで作る。作り直しの後、マージまでにmainが進んだら、マージの前に必ずもう一度取り込む（`main`のrulesetは最新のブランチでの`Quality`・`Test`と、最後のpushへのcode ownerの承認を求める。取り込みのpushはClaude Codeが行い、人間はその最後のpushを承認する）。進んだ変更が特徴量・datamart・学習・予測のコードに関わるなら、取り込んだうえで手順2から作り直す。datamart・PLモデルの読込は記録された計算契約と入力を照合するが、動いているコードとの違いは検出しないためである。取り込み・CI・承認と、必要なら作り直しの時間を、切替の夜より前に見込んでおく。

手順3の評価の後、人間が加えた8列を運用で使うかを決める。test年2026の結果（2016〜2025年は列を選ぶのに使ったので、それだけでは決めない）で、`all_columns`（44列）と`without_added_columns`（元の36列）を比べる。使うと決めたら、手順4に`--override pl_variant=all_columns`を、手順6に`--override variant.name=all_columns`と`--override 'variant.excluded_columns=[]'`を足す。推定器（手順5）はバックテストのreportのvariantを引き継ぐ。使わないなら、既定（`without_added_columns`）のまま進める。

## 手順

以下の値は初回の`Y`=2027を例にする。翌年以降は、対象終了日、test年、valid年、出力名の末尾を年`Y`に合わせて読み替える。各段階のstdoutの要約と、以下で示すSHA-256の値を残す。CLIへ渡すSHA-256は小文字の16進でなければならない。`Get-FileHash`は大文字を出すので、`(Get-FileHash <ファイル> -Algorithm SHA256).Hash.ToLower()`で得る。失敗した段階は、同じ入力と設定で新しい`--output`を指定してやり直す。

### 1. 固定snapshotを作る

最終開催日の翌日（JST）以後に`latest`を実行し、続けてhistorical-oddsの予定を確認して取得を実行する。完全Parquetのsnapshotは`latest`も公開する。historical-oddsの実行のうちでは、`--plan-only`でない実行が全年の取得を終え、公開を待つ年があるときにだけ再構築して公開する。`--plan-only`と`--confirm-provider-missing`は公開しない。CURRENTのIDは、最後のhistorical-oddsの実行の後に読む。

```powershell
uv run python src/main.py --retrieve --mode=latest
uv run python src/main.py --retrieve --mode=historical-odds --plan-only
uv run python src/main.py --retrieve --mode=historical-odds
```

- 実行する日付（JST）が最終開催日の翌日以後であることを確かめる。historical-oddsは実行日の前日までのレースだけを対象とし、`--plan-only`の出力は年と件数だけでレースを示さない。
- `failed/empty_response_unverified`で止まった項目は、[READMEの`--confirm-provider-missing`の手順](../README.md)に従ってJRA-VAN側の欠落を確認するまで完了扱いにしない。`--confirm-provider-missing`を使ったら、その後に`--plan-only`なしでhistorical-oddsを実行し直す。
- それ以外の`failed`（表の欠落、不正なスキーマ、archiveやプロセスの失敗）は、欠落の確認に回さない。原因を直してhistorical-oddsを実行し直す（実行が中断された場合は`--recover`を付ける）。
- 最後の`--plan-only`なしの実行が、終了コード0で、`Complete Parquet rebuild failed.`を出さずに終わったことを確かめる。

その後、次を実行し、`--plan-only`の出力のJSONが`"year": null`と`"requested_specs": 0`を示すことを確かめてから、CURRENTのIDを控える。`--plan-only`はrawだけを見るので、取得の完了だけを示す（`status`は常に`plan`である）。公開は、上の最後の`--plan-only`なしの実行で確かめる。

```powershell
uv run python src/main.py --retrieve --mode=historical-odds --plan-only
Get-Content data/processed/CURRENT
```

以後のdatamart、評価、バックテスト、推定器、最終学習は、このIDのsnapshotだけを読む（評価・バックテスト・推定器は、datamartとreportに記録されたsnapshotを読む）。

### 2. 学習用datamartを全期間で作り直す

対象2006-01-01〜2026-12-31、履歴2005-01-01からを、固定したsnapshotと`measure`で1回だけ構築する。年別出力を束ねたり、途中から再開したりしない。

```powershell
uv run python src/main.py datamart build-reference `
  --config-name measure `
  --override processed_root=data/processed `
  --override snapshot_id=<CURRENTのID> `
  --override target_start=2006-01-01 `
  --override target_end=2026-12-31 `
  --output output/reference-datamart-2006-2026

(Get-FileHash output/reference-datamart-2006-2026/manifest.json -Algorithm SHA256).Hash.ToLower()
```

### 3. PL確率を評価する

手順2のstdoutの要約の`manifest_sha256`（上の`Get-FileHash`の値と同じ）を`<datamartのmanifest SHA-256>`に入れ、test年2016〜2026の評価を行う。`model evaluate-pl`はSHA-256を出力しないので、次の段階に渡す2つのファイルのSHA-256を`Get-FileHash`で得る。

```powershell
uv run python src/main.py model evaluate-pl `
  --config-name measure `
  --override processed_root=data/processed `
  --override datamart_path=output/reference-datamart-2006-2026 `
  --override datamart_manifest_sha256=<datamartのmanifest SHA-256> `
  --override 'test_years=[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025,2026]' `
  --output output/pl-evaluation-2016-2026

(Get-FileHash output/pl-evaluation-2016-2026/predictions.parquet -Algorithm SHA256).Hash.ToLower()
(Get-FileHash output/pl-evaluation-2016-2026/report.json -Algorithm SHA256).Hash.ToLower()
```

### 4. 購入方策をバックテストする

手順3の`predictions.parquet`と`report.json`のSHA-256を入れ、同じtest年2016〜2026でバックテストする。`model backtest-betting`もSHA-256を出力しないので、`report.json`のSHA-256を`Get-FileHash`で得る。

```powershell
uv run python src/main.py model backtest-betting `
  --config-name measure `
  --override processed_root=data/processed `
  --override pl_evaluation_path=output/pl-evaluation-2016-2026 `
  --override pl_predictions_sha256=<predictions.parquetのSHA-256> `
  --override pl_report_sha256=<report.jsonのSHA-256> `
  --override 'test_years=[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025,2026]' `
  --output output/ev-betting-backtest-2016-2026

(Get-FileHash output/ev-betting-backtest-2016-2026/report.json -Algorithm SHA256).Hash.ToLower()
```

### 5. 2027年の推定器を作る

手順4の`report.json`のSHA-256を入れ、最後のtest年の翌年である2027年の推定器を作る。

```powershell
uv run python src/main.py model fit-betting-estimator `
  --backtest output/ev-betting-backtest-2016-2026 `
  --backtest-report-sha256 <バックテストのreport.jsonのSHA-256> `
  --pl-evaluation output/pl-evaluation-2016-2026 `
  --processed-root data/processed `
  --output output/ev-betting-estimator-2027

(Get-FileHash output/ev-betting-estimator-2027/manifest.json -Algorithm SHA256).Hash.ToLower()
```

### 6. PLモデルを最終学習する

同じdatamartから、train 2006〜2025年、valid 2026年の最終PLモデルを作る。`<datamartのmanifest SHA-256>`は手順3と同じ値である。

書込みが欠損の枝の照合で拒否された場合は、[ADR-038](decisions/ADR-038-train-and-persist-the-final-top3-pl-model.md) Amendment 1のとおり、`configs/pl_evaluation/measure.yaml`と`configs/pl_training/final.yaml`の`lightgbm`に同じ`bin_construct_sample_cnt`（最終学習のtrainの行数以上）を入れ、手順3〜6をやり直す。手順3〜5の出力先は既にあり、各CLIは既存の出力先を拒否するので、やり直す段階の出力名の末尾に`-r2`のような版の番号を付ける（例: `output/pl-evaluation-2016-2026-r2`）。手順4〜6に渡すSHA-256は、やり直した出力から得る。最初の手順5の推定器は使わない。設定の変更は作り直しの後のPRに含める。やり直しが終わるまでは「間に合わないとき・切り戻し」に従う。2027年には2026年の推定器を使えないため、Amendment 1の「今の推定器」で運用を続けることはできない。

```powershell
uv run python src/main.py model train-pl `
  --config-name final `
  --override datamart_path=output/reference-datamart-2006-2026 `
  --override datamart_manifest_sha256=<datamartのmanifest SHA-256> `
  --override valid_year=2026 `
  --output output/pl-final-model-2006-2026

(Get-FileHash output/pl-final-model-2006-2026/manifest.json -Algorithm SHA256).Hash.ToLower()
```

## 切替の前の確認

前日の夜に切り替える前に、次を確かめる。

- `datamart build-reference`・`model fit-betting-estimator`・`model train-pl`のstdoutの要約の`manifest_sha256`が、各`manifest.json`の`Get-FileHash`の値（小文字）と一致する。`model evaluate-pl`と`model backtest-betting`はSHA-256を出力しない。それらのファイルは、次の段階が渡されたSHA-256で固定して照合する。
- 評価とバックテストの`report.json`のtest年が、2016〜2026年のちょうどすべての年である。途中の年が抜けても推定器の`target_year`は2027のままで、CLIは検出しない（2026年が抜けると`target_year`が2026になり、購入案の常駐CLIが2027年の`--date`で起動を拒否する）。
- 推定器の`target_year`が2027であること、最終モデルのvalid年が2026であることを確認する。
- バックテストの`report.json`の`config.pl_variant`と、PLモデルの`manifest.json`の`features.variant`が同じで、PLモデルの`features.excluded_columns`が評価の`report.json`の同名のvariantの`excluded_columns`と同じである。購入案の常駐CLIは名前の違いだけを起動時に拒否する。
- PLモデルの`training.label_usable_through`が、切替後の最初の開催日の最も早いfreezeより前である。
- 評価のtest年2026の成績、バックテストの回収率と95%区間、推定器の`method`・`α`・`β`を前年の記録と並べる。2026年までの記録の`all_columns`は元の36列で、2027年向けの`all_columns`（44列）とは列が違う。前年と比べる相手は、同じ36列の`without_added_columns`である。ADR-042〜045の採否、方策、方法の選択を変えうる差があれば、人間が判断する。

提示額は0円のままとし、この確認で方策や提示額を変更しない。

## 切替

開催日の前日の夜に、[当日の運用手順](race-day-operation.md)の特徴量、予測、購入案の常駐CLIへ渡す値を同時に替える。

| 新しい値 | 渡すCLIとオプション |
| --- | --- |
| `output/reference-datamart-2006-2026`とその`manifest.json`のSHA-256 | 特徴量の常駐CLI（`datamart build-reference-prediction-live`）の`--reference-datamart`・`--reference-datamart-manifest-sha256` |
| `output/pl-final-model-2006-2026`とその`manifest.json`のSHA-256 | 予測の常駐CLI（`model predict-pl-live`）と購入案の常駐CLI（`model propose-bets-live`）の両方の`--pl-model`・`--pl-model-manifest-sha256` |
| `output/ev-betting-estimator-2027`とその`manifest.json`のSHA-256 | 購入案の常駐CLI（`model propose-bets-live`）の`--estimator`・`--estimator-manifest-sha256` |

予測の常駐CLIだけでモデルを替えると、購入案の常駐CLIはモデルの不一致で各重賞を保留する。

`--snapshot-id`には、従来どおり当日の前日の夜に`latest`で固定したCURRENTのIDを渡す。学習に使ったsnapshot IDで置き換えない。開催日の途中には切り替えない。

## historical-oddsの対象年を延ばす

年`Y`の作り直しと切替を終えた後、年`Y`の最初の開催日の翌日（JST）以後で、年`Y`のレースをhistorical-oddsでbackfillする前に、対象年の終わりを`Y`へ延ばす。初回は、2027年の最初の開催日の翌日以後に行う。

次の順に実行する。

1. 進捗台帳`data/runtime/jvlink/historical-odds-progress.db`（`configs/data.toml`の`jvlink_runtime_dir`の下）を複製し、切り戻し用に保管する。
2. 当日の運用のcheckoutで、`configs/jvlink.toml`の`[historical_odds.batch].last_year`を`Y`にする。
3. `--plan-only`でhistorical-oddsを実行し、`policy differs`で拒否されずに予定が出ることを確かめる。この実行は台帳へ書き込まない。予定の年は未完了の最も古い年で、それより前の年がすべて取得済みのときに`Y`になる。
4. `--plan-only`なしでhistorical-oddsを実行する。この実行で既存の台帳に年`Y`を`pending`として加え、`policy_hash`を新しい設定へ移す。
5. `configs/jvlink.toml`の`last_year`と、それを確かめる`src/tests/integration/test_setting.py`の値を変えるPRを作る（作り直しの記録PRには含めない）。マージまで、当日の運用のcheckoutでは`configs/jvlink.toml`の変更を戻さない（戻すと延長した台帳が拒否される）。マージの後に当日の運用のcheckoutを更新するときは、historical-oddsのコマンドを実行していない間に、`git checkout -- configs/jvlink.toml`で手元の変更を捨ててから`git pull`する（手元の変更が残っていると`git pull`は上書きを拒否する）。

```powershell
uv run python src/main.py --retrieve --mode=historical-odds --plan-only
uv run python src/main.py --retrieve --mode=historical-odds
```

年`Y`の最初の開催日より前に`last_year`を上げない。台帳へ書き込むhistorical-oddsのコマンドは、通常の実行だけでなく`--recover`と`--confirm-provider-missing`も延長を行う。延長で加えた年`Y`は公開待ち（`pending`）になり、年`Y`の候補がまだなくても、次の`--plan-only`なしの実行が完全Parquetの再構築を行う（rawデータベースが大きいため長い時間がかかる）。最初の開催日の後であれば、年`Y`のレースの取得によってどのみち再構築が必要になる。

延長後は、古い設定や古いコードでは台帳の方針が一致せず拒否される。切り戻すときは、設定やコードだけでなく、手順1で複製した延長前の台帳も元の場所へ戻す。

## 間に合わないとき・切り戻し

新しい3成果物が揃わない、常駐CLIが起動に失敗する、または新しいモデルのラベル利用境界が最初の開催日に届かない場合は、特徴量と予測の常駐CLIを前年のdatamartとPLモデルで動かす。購入案の常駐CLIは起動しない。前年の推定器は新しい年の`--date`に対して起動できないためである。

新しい版へ切り替えた後に問題が出た場合も同じ手順で切り戻す。前年の版で運用した開催日を、この文書の「前年の版で運用した開催日」の表に記録する。

運用した学習用datamart、PLモデル、推定器のディレクトリは消さずに残す。[ADR-047](decisions/ADR-047-connect-wide-and-exacta-race-day-odds-to-expected-value-decisions.md)の評価では、当日に残した特徴量を、その開催日に結び付いたPLモデルで後から採点する。特徴量はモデルと同じ学習用datamartに結び付くため、ほかのモデルでは採点できない。各開催日のモデルは、「版の履歴」の表の切替日と、「前年の版で運用した開催日」の表で決まる（ADR-047の決定6の「その年の固定したPLモデル」は、ADR-048の決定7でこの意味に改めた）。

## 作り直しの後のPR

作り直しと切替の記録を残すPRを作る。次を更新する。

- `configs/pl_evaluation/measure.yaml`と`configs/betting_backtest/measure.yaml`の`test_years`（`configs/betting_backtest/measure.yaml`の「計測の後に値を変えない」という注記は、ADR-043・044で固定した方策と補正・推定の値に限るよう、ADR-051で書き直した）
- 加えた8列を使うと決めた場合は、`configs/betting_backtest/measure.yaml`の`pl_variant`と`configs/pl_training/final.yaml`の`variant`を`all_columns`へ変え、それを固定して確かめるテスト（`src/tests/integration/test_pl_variant_configs.py`など）とREADMEの最終学習・バックテストの節を合わせる。列の群ごとのvariant（`without_post_position`など）を翌年以降の評価に残すかも決める（残すと評価の時間が延びる）
- `configs/pl_training/final.yaml`の`valid_year`
- 上の値の年を書いた先頭のコメント（`configs/pl_evaluation/measure.yaml`の「test 2016-2025」、`configs/pl_training/final.yaml`の「train 2006-2024 ... 2025」）
- 上の運用の年を固定して確かめるテスト（評価・バックテスト・最終学習のCLIの統合テストで、`measure.yaml`の`test_years`や`final.yaml`の`valid_year`の値を確かめているもの）。変えないと`Test`のCIが失敗する
- READMEのPLの評価と最終学習の節に書いた年（`measure.yaml`のtest年、`final.yaml`のtrainとvalidの年）
- 評価、バックテスト、最終学習の実験の記録
- この文書の「版の履歴」の表（新しい行を足し、前の行は残す）と、「前年の版で運用した開催日」の表

初回の作り直しで使う年の値は設定ファイルを先に変えず、手順の`--override`で渡す。

## 臨時の作り直し

年の途中には通常の作り直しをしない。LightGBMの更新、閉じた数値列・計算契約・特徴量の定義（`configs/features.toml`）の変更、ADR-038 Amendment 1による`bin_construct_sample_cnt`の変更のときは、同じ年の範囲（datamartの対象〜前年、test年2016〜前年、推定器はその年、validは前年）でこの手順を臨時に行う（ADR-048の決定9）。

- 年の途中に行うときは、新しい版へ切り替えるまで、今のdatamart、PLモデル、推定器で運用を続ける（購入案の常駐CLIも起動する）。切り戻しも今の3つへ戻す。
- 臨時の作り直しの手順2〜6は、当日の運用に使うcheckoutと環境とは別のcheckout・環境（変更のブランチのworktreeなど）で行う。`data/`と`output/`はgitの対象外で、取得の設定（`configs/data.toml`）はデータのパスをcheckoutからの相対パスで決める。そのため、手順1の取得とsnapshotの固定は当日の運用のcheckoutで行う。別のcheckoutでは、`processed_root`・`--processed-root`・`datamart_path`・`pl_evaluation_path`・`--backtest`・`--pl-evaluation`・`--output`に、運用のcheckoutの`data/processed`と`output/`の下を絶対パス（`C:/.../data/processed`のように`/`で区切る）で指定する。`Get-FileHash`のパスも、同じ絶対パスにする。成果物を別のcheckoutの中に置かない（worktreeを消すと中の成果物も消える）。年明けと同じ年の範囲なので、出力名は運用中の成果物と重なる。各CLIは既存の出力先を拒否するため、出力名の末尾に`-r2`・`-r3`のように版の番号を付ける（まだ使っていない次の番号を選ぶ。例: 運用中の`output/pl-final-model-2006-2026`に対して`output/pl-final-model-2006-2026-r2`）。計算契約・閉じた数値列・特徴量の定義を変えたcheckoutでは、特徴量の常駐CLIが今の学習用datamartを拒否する。LightGBMを更新した環境では、前の版のPLモデルを読めない（学習時のLightGBMのversionとの違いで拒否する）。当日の運用のcheckoutと環境は、切替の夜まで前のコードと依存のままにする。切替の夜にコード・依存と3成果物を一緒に替え、切り戻しは両方を戻す。
- LightGBMの更新の後は、前の版のPLモデルで当日に残した特徴量を採点できない。ADR-047の評価のための後からの採点は、更新の前に済ませるか、前のLightGBMの環境で行う。
- 年明けの作り直しの中での欠損の枝の照合による拒否は、手順6に従う。

## 記録として残すもの

- historical-oddsの完了を確認したCURRENTのID、`latest`と各段階の開始・終了時刻。
- 各CLIのstdoutの要約、`Get-FileHash`で照合したSHA-256、使用した`--override`。
- datamart、PL評価、バックテスト、推定器、最終モデルの出力先。
- 評価のtest年、推定器の`target_year`、最終モデルのvalid年、前年との成績・回収率・95%区間・`method`・`α`・`β`の比較。
- 切替日、切り戻しの有無と理由、前年の版で運用した開催日、当日の常駐CLIの起動結果。
- ADR-051の切替の夜は、マージ前の運用のcheckoutのコミット（`git rev-parse HEAD`）。

## 版の履歴

運用した版を、切替のたびに1行ずつ足す。前の行は消さない。最後の行が運用中の版である。1行目は2026-11-21に確認した版で、固定snapshotのIDは学習用datamartの`manifest.json`の`snapshot.snapshot_id`から転記した。切替日は記録が残っていないため未記録とする。次回の切替からは、両方を記録する。

| 固定snapshot ID | 切替日 | 学習用datamart | datamart manifest SHA-256 | PLモデル | PLモデル manifest SHA-256 | 推定器 | 推定器 manifest SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `098ce3f4b5d7480282269218d80cef05` | 未記録 | `output/reference-datamart-2006-2025` | `dc37514732fdb653ce9ed3a6e836a0f6f120a5613a905c5574d43cdc0f4b51b9` | `output/pl-final-model-2006-2025-r3` | `89656d49140504993c57695f320a83068e73e020cefb37f37ee9a55e6a2a2aee` | `output/ev-betting-estimator-2026-final` | `f87671a43af31fe373c4115f84a8aed6430443b68351adbde291f5aeabf3efa3` |

## 前年の版で運用した開催日

切替の後に、前年の版（または臨時の作り直しの前の版）で特徴量と予測を運用した開催日を記録する。まだ記録はない。

| 開催日 | 使った学習用datamart manifest SHA-256 | 使ったPLモデル manifest SHA-256 | 理由 |
| --- | --- | --- | --- |
