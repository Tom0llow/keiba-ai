# 当日の未確定レースの参考特徴量の構築と計測

## 目的と範囲

[ADR-036](../decisions/ADR-036-build-label-free-reference-features-for-unfinished-races.md)の
`datamart build-reference-prediction`は、学習用の参考datamart（ADR-034）にmanifestのSHA-256で固定し、
同じ計算設定・参考規則・計算器で、対象日1日の特徴量をラベルなしで作る。
この記録は、実データでの所要時間・メモリと、学習用datamartとの値の一致を示す。

## 実行

```powershell
uv run python src/main.py datamart build-reference-prediction --reference-datamart <学習用datamart> --reference-datamart-manifest-sha256 <manifestのSHA-256> --date 2025-12-28 --processed-root <processed root> --snapshot-id <snapshot_id> --output <新しい出力先>
```

- `--processed-root`は必須で、`--snapshot-id`を省略するとCURRENTを最初の一度だけ解決する。
- 計算設定と参考規則は、学習用datamartのmanifestの`preparation_config`だけから取る。
  特徴量定義（`--features-config`）と計算契約が学習用datamartと異なれば、snapshotを読む前に失敗する。
- 進捗・対象の保留の段階ごとの件数・鮮度（`freshness`）はstderrに出る。
  要約1行（`date`・`targets`・`races`・`rows`・`held_targets`・`manifest_sha256`）はstdoutに出る。

## 出力

学習用datamartと同じディレクトリ構造で、format `reference_prediction_features`・format_version 1である。

- 行にもレースにも、`finish_position`やラベルの列はない。
- manifestの`source_datamart`は、学習用datamartとの結び付きを記録する。#52・#53はこれで、モデルを学習したdatamartと、
  学習に使ったラベルの利用境界を照合する。
  - `manifest_sha256`、`contract_sha256`、`target_period`
  - `label_usable_through`: 学習用の`label_usable_after`の最大値
  - `provenance_source_sha256`
- `freshness`は、当日のsnapshotで調教と血統が古くないかを判断するための指標である。
  - `latest_workout_date`: HC・WCの対象日より前の最新の調教日。
  - `card_horses`: 出馬表の馬の数。
  - `card_horses_without_pedigree_row`: そのうち`NL_UM_UMA`に行がない馬の数。
  - `history_held_recent`: 対象日の`result_delay_days`+7日前から前日までに開始した、履歴として採用できなかったレースの数。
- 対象日の各レースは、freezeより後のO1の発表がsnapshotにない場合、`target_pre_freeze`・
  `market_not_observed_after_freeze`で保留される。freeze以前のO1で取消が示されたレースも、学習と同じく
  `target_pre_freeze`で保留される（#46）。heldには履歴の保留も含まれるため、
  予測の対象の保留は`role == "target"`で絞って読む。

## 実データでの結果（2026-11-11）

### 条件

- 学習用datamart: `output/reference-datamart-2006-2025`（対象2006-01-01〜2025-12-31、履歴2005-01-01から、
  manifest SHA-256 `dc37514732fdb653ce9ed3a6e836a0f6f120a5613a905c5574d43cdc0f4b51b9`）。
- snapshot: 学習用datamartと同じ`098ce3f4b5d7480282269218d80cef05`。計測の時点ではCURRENTも同じsnapshotだったので、
  「同じsnapshotでの一致の確認」と「CURRENTでの実行」は同じ1回の実行である。
- 対象日: 2025-12-28。
- 機械: 開発用のWindows 11の1台。PowerShellで、0.5秒ごとにpythonプロセスの作業セットを監視した。

### 計測

| 項目 | 値 |
| --- | --- |
| 所要時間 | 207.7秒 |
| pythonのピーク作業セット | 4.62GB |
| 対象 | 24レース（保留0件） |
| 行 | 356 |
| 履歴だけの年（2005〜2024年）の取込み | 1年あたり約6.6〜7.3秒 |
| 対象年（2025年）の取込みと計算 | 46.3秒 |
| 出力のmanifest SHA-256 | `f305544cd3617842b25b7feed6eefd809a395a0bfa27fb322cf709cd127fbddb` |

`freshness`は次のとおりだった。

- `latest_workout_date`: HC・WCとも`2025-12-27`。
- `card_horses`: 356、`card_horses_without_pedigree_row`: 0。
- `history_held_recent`: 15（窓7日）。

### 学習用datamartとの一致

同じ日の学習用datamartの行と、全数値列・群ごとの`available_at`・`scheduled_start_at`・`freeze_at`を比べた。

- 共通の316行・18,644値で、不一致は0件だった。
- ラベルなしの出力にだけあった3レース（`2025122806050812`・`2025122809050805`・`2025122809050812`）は、
  学習用datamartで`target_outcome`（結果に由来する保留）だったレースとちょうど一致した。
  ラベルを読まないため、これらも計算された。

### 制約

- 過去の日付で計測したため、当日の発走前の行（未確定の結果、`headDataKubun`が確定前）を実データでは試していない。
  当日の形は、fixtureのテストで確かめている。
- 当日の実行は、#54の最初の開催日で行う。
- 当日の完全snapshotでは、`[latest]`が調教・血統を取得しないため、`freshness`の値が悪くなる見込みである（#61）。
