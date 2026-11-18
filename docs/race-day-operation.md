# 当日の運用手順

## 目的と範囲

開催日の各レースの参考特徴量とJRA平地重賞のPL確率、重賞の0円の購入案を、発走前に公開するための手順である（ADR-041、ADR-045）。実行順序は、前日の夜の`latest`、当日のrace-day-odds、特徴量の常駐CLI、予測の常駐CLI、購入案の常駐CLIとする。

この手順は人が実行する。4本のCLIを自動化せず、別々の端末から順に起動する。購入案の提示額は常に0円で、参考額（`reference_stake_yen`）を購入の根拠にしない。freezeは発走5分前、提示期限は発売締切（発走2分前）である。発売締切の後に計算した予測は`after_sales_close: true`として記録されるが、購入の判断には使わない。

## 前提

特徴量の常駐CLIには、学習用datamartのパスと、その`manifest.json`のSHA-256を渡す。予測の常駐CLIには、保存済みPLモデルのパスと、その`manifest.json`のSHA-256を渡す。SHA-256は次のように確認する。

```powershell
Get-FileHash <学習用datamart>\manifest.json -Algorithm SHA256
Get-FileHash <PLモデル>\manifest.json -Algorithm SHA256
```

学習用datamartのmanifestの値は`--reference-datamart-manifest-sha256`へ、PLモデルのmanifestの値は`--pl-model-manifest-sha256`へ渡す。購入案の常駐CLIには、その年の推定器（`model fit-betting-estimator`の出力）のパスと、その`manifest.json`のSHA-256（`--estimator-manifest-sha256`）も渡す。推定器は年に1回、開催日より前に作る（README「当日の購入案の推定器を年ごとに保存する」）。年の違う推定器では起動しない。特徴量と予測のCLIには、前日の夜に`latest`が公開して控えた同じsnapshotのIDを、それぞれ`--snapshot-id`で渡す。race-day-oddsは`--snapshot-id`を受け取らない。

## 前日の夜

当日のrace-day-oddsが最後の要約を出して終了したことを確かめてから（その日に開催がなければ、race-day-oddsの終了の確認は不要）、翌日の開催日のために`latest`を実行する。実行中はパイプやリダイレクトを使わない。開始・終了時刻と、新しく公開されたCURRENTのIDを控える。

```powershell
$t0 = Get-Date; uv run python src/main.py --retrieve --mode=latest; $t1 = Get-Date; "$t0 -> $t1 ($(($t1 - $t0).TotalSeconds) s)"
Get-Content data/processed/CURRENT
```

翌朝に`latest`や`preprocess rebuild`を実行しない。前日の夜に控えたCURRENTのIDを、当日の特徴量と予測のCLIで`--snapshot-id`に指定して固定して使う。race-day-oddsには指定しない。

## 当日の朝

最初の発走の30分前より前に、次を確認する。

```powershell
w32tm /query /status
w32tm /stripchart /computer:time.windows.com /samples:3 /dataonly
Get-Process JVLinkToSQLite -ErrorAction SilentlyContinue
Get-Content data/processed/CURRENT
```

時計のずれを控え、JVLinkToSQLiteが動いていないこと、CURRENTが前日の夜に控えたIDであることを確かめる。JV-Linkの設定画面が開くことも確認する。設定画面に表示されるサービスキーは記録しない。

## 起動

### 端末1: race-day-odds

最初の取得より前に起動する。race-day-oddsはJVLinkToSQLiteを起動するため、端末から直接実行し、パイプやリダイレクトを使わない。起動が遅れると、それより前の取得は`skipped_late`になる。

```powershell
uv run python src/main.py --retrieve --mode=race-day-odds --date <開催日>
```

`setup failed`が出た場合は取得を続けず、stderrとstdoutの出力を控える。

### 端末2: 特徴量の常駐CLI

端末1を起動した後、時刻付きのログを残して起動する。`<CURRENTのID>`には前日の夜に控えた値を入れる。

```powershell
$env:PYTHONUNBUFFERED = "1"
uv run python src/main.py datamart build-reference-prediction-live `
  --reference-datamart <学習用datamart> `
  --reference-datamart-manifest-sha256 <manifestのSHA-256> `
  --date <開催日> --processed-root data/processed --snapshot-id <CURRENTのID> `
  --output <特徴量の出力先> 2>&1 |
  ForEach-Object { "{0:o} {1}" -f (Get-Date), $_ } | Tee-Object -Append -FilePath <特徴量のログ>
```

### 端末3: 予測の常駐CLI

端末2の準備が終わった後に起動する。特徴量の出力先と同じsnapshotのIDを指定する。

```powershell
$env:PYTHONUNBUFFERED = "1"
uv run python src/main.py model predict-pl-live `
  --features-root <特徴量の出力先> `
  --pl-model <PLモデル> `
  --pl-model-manifest-sha256 <manifestのSHA-256> `
  --date <開催日> --processed-root data/processed --snapshot-id <CURRENTのID> `
  --output <予測の出力先> 2>&1 |
  ForEach-Object { "{0:o} {1}" -f (Get-Date), $_ } | Tee-Object -Append -FilePath <予測のログ>
```

常駐CLIを同じ`--output`で起動し直すと直ちに失敗する。新しい`--output`（例えば末尾に`-r2`を付けたもの）を指定する。特徴量の常駐CLIに新しい`--output`を指定した場合は、予測の常駐CLIも新しい`--features-root`を指定して再起動する。`-Append`を付けると、それまでのログを残せる。

### 端末4: 購入案の常駐CLI

端末3を起動した後に起動する。`--features-root`・`--pl-model`・`--snapshot-id`には端末3と同じ値、`--predictions-root`には端末3の`--output`を指定する。

```powershell
$env:PYTHONUNBUFFERED = "1"
uv run python src/main.py model propose-bets-live `
  --predictions-root <予測の出力先> --features-root <特徴量の出力先> `
  --estimator <推定器> --estimator-manifest-sha256 <manifestのSHA-256> `
  --pl-model <PLモデル> --pl-model-manifest-sha256 <manifestのSHA-256> `
  --date <開催日> --processed-root data/processed --snapshot-id <CURRENTのID> `
  --output <購入案の出力先> 2>&1 |
  ForEach-Object { "{0:o} {1}" -f (Get-Date), $_ } | Tee-Object -Append -FilePath <購入案のログ>
```

予測の常駐CLIを新しい`--output`で再起動した場合は、購入案の常駐CLIも新しい`--predictions-root`と新しい`--output`で再起動する。
購入案のCLIの`prediction_not_published`の本当の理由（特徴量の保留など）は、同じ`race_id`の予測のログの行で確かめる。

## 当日の流れと所要時間の目安

前日の夜に`latest`を完了してsnapshotのIDを控え、当日は次の順序で進める。

```text
前日の夜のlatest
  -> 当日のrace-day-odds
  -> 特徴量の常駐CLI
  -> 予測の常駐CLI
  -> 購入案の常駐CLI
```

2026-11-14・15の計測では、予測用の取得は約1秒、特徴量の準備は64〜85秒、freezeの5〜6秒後に特徴量を公開した。重賞の予測は、2026-11-15にfreezeの約6秒後、発売締切の約174秒前に公開した。前日夜の`latest`は全体で約76分だった。詳細は[当日の運用の実測](experiments/race-day-operation.md)に記録する。

race-day-oddsの実行中は、`latest`、`preprocess rebuild`、対象日の`--mode=realtime`を実行しない。完全Parquetの出力を重ねると、取得の書込みが`database is locked`で失敗し、取得が欠けるか停止する。

## 終わり方

- race-day-oddsは、対象日の取得を終えると、最後に件数の要約をJSONで出す。失敗があれば終了コード1、Ctrl+Cは130である。
- 特徴量の常駐CLIは、対象レースごとに`published`または`held`を決めると終了し、stderrに`targets`・`published`・`held`を含む要約を出す。
- 予測の常駐CLIは、重賞を`predicted`または`held`、重賞でないレースを`out_of_scope`として決めると終了し、stderrに`graded`・`predicted`・`held`・`out_of_scope`を含む要約を出す。
- 購入案の常駐CLIは、重賞を`proposed`または`held`、重賞でないレースを`out_of_scope`として決めると終了し、stderrに`graded`・`proposed`・`held`・`out_of_scope`を含む要約を出す。

予測の常駐CLIは、発売締切までに特徴量が公開されない重賞を`features_not_published`で保留する。発売締切後に特徴量が見つかった場合は予測を公開して`after_sales_close: true`を記録する。

## 失敗時の対応

- race-day-oddsが途中で止まった場合は、`--recover`で`running`の取得を`interrupted`にしてから、`--date <開催日>`で再起動する。常駐CLIを再起動する場合は、新しい`--output`を指定する。
- `JVOpen -211`や`-303`が続く場合: 2026-11-14・15の原因は、JV-Linkのサービス`JVLinkAgent`の異常終了だった。JV-Link側の不具合であり、JRA-VANも同じ事象を確認している。サービス停止後は`JVOpen -211`が返り、その後の取得で`-303`が続く。`Get-Service JVLinkAgent`が`Stopped`を示すことと、WindowsのApplicationログに`JVLinkAgent.exe`のApplication Errorがあることを確認する。JV-Linkを使うのはrace-day-oddsだけで、特徴量と予測の常駐CLIはJV-Linkを使わない。race-day-oddsを止め、特徴量と予測の常駐CLIは動かしたままにする。管理者として起動したPowerShellで`Start-Service JVLinkAgent`を試す（実機の運用PCではまだ試していない）。JV-Linkの設定画面が開くことを確認し、開かない場合またはサービスが起動しない場合はPCを再起動する。PCを再起動しない場合は、race-day-oddsだけを`--date <開催日>`で起動し直す。PCを再起動した場合は、3本のCLIを起動し直す。常駐CLIは新しい`--output`を指定し、予測CLIの`--features-root`には特徴量CLIの新しい出力先を指定する。race-day-oddsは`--date <開催日>`で起動すると、開始時に`running`の取得を復旧する。サービスキーは記録しない。エラーコード、最後の取得、停止・復旧の時刻を残す。停止中は、各取得が`execution_timeout_seconds`の上限（120秒）まで待つことがある。
- `features_not_published`は、特徴量の計算が遅れた場合だけでなく、予測用の取得が`jvlink_error`などで失敗した場合にも起きる。予測のログだけで判断せず、特徴量のログの保留理由（`race_day_fetch_failed: ...`など）と取得記録を照合する。

## 記録として残すもの

- 時計のずれ、前日の夜の`latest`の開始・終了時刻、公開したsnapshotのCURRENTのID。
- race-day-oddsの端末出力、各取得の記録（`ARCHIVE_CAPTURE_LOG`と`data/processed/realtime/<開催日のレースディレクトリ>/`）、失敗時の隔離先。
- 特徴量・予測・購入案の時刻付きログ（`<特徴量のログ>`、`<予測のログ>`、`<購入案のログ>`）、各CLIの最後の要約、公開・保留されたレースの出力。購入案の`publication_age_seconds`（古い発表、#78）。
- 予測用の取得の`HappyoTime`、`features_not_published`や`race_day_fetch_failed: jvlink_error`などの保留理由、`after_sales_close`の有無。

取得記録やログにサービスキーを含めない。

## 自動化しないこと

前日の夜の`latest`、当日のrace-day-odds、特徴量の常駐CLI、予測の常駐CLI、購入案の常駐CLIは、人が別々の端末から順に起動する。起動スクリプトや自動集計はこの手順の対象外である。
