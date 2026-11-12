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

学習用datamartと同じディレクトリ構造で、format `reference_prediction_features`・format_version 2である
（[ADR-037](../decisions/ADR-037-build-race-day-reference-features-after-freeze.md)で1から上げ、manifestに市場の出典
`market_source`を加えた。この一括の構築では`{"kind": "complete_snapshot"}`）。

- 行にもレースにも、`finish_position`やラベルの列はない。
- manifestの`source_datamart`は、学習用datamartとの結び付きを記録する。#52・#53はこれで、モデルを学習したdatamartと、
  学習に使ったラベルの利用境界を照合する。
  - `manifest_sha256`、`contract_sha256`、`target_period`
  - `label_usable_through`: 学習用の`label_usable_after`の最大値
  - `provenance_source_sha256`
- `freshness`は、当日のsnapshotで調教と血統が古くないかを判断するための指標である。
  - `latest_workout_date`: HC・WCごとに、対象日のために読み込んだ調教の窓（対象日の`days_window`+1日前から
    前日まで）の中で最も新しい調教日。窓の中に調教がなければnullになる。調教の表が窓より前で止まっている
    （古い）場合もnullになるので、nullは「調教がない」ではなく「窓の中に見つからない」を意味する。
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

## 当日のレースごとの構築（ADR-037）

`datamart build-reference-prediction-live`は、対象日を一度だけ準備し、race-day-oddsがfreezeの時刻に取得した0B41/0B42の
時系列から、レースごとに特徴量を作る。当日の実データはまだないため、過去の日付で次の代替の計測をした。

### 0B41の発表の間隔

2025-11-30・12-27・12-28の中央72レースすべてで、発走11分前より後の`headDataKubun="1"`の発表は、発走11分前・6分前・1分前
だけだった。freeze（発走5分前）の値は常に発走6分前の発表で、freezeより後の最初の発表は発走1分前（発売締切の後）である。
そのため、当日の取得では「freezeより後の発表がある」ではなく「取得の開始がfreeze以降である」ことを完全性の根拠にした。

### 計測（2025-12-28、2026-11-12）

コミットしない計測用のスクリプトで、常駐CLIと同じ関数を使って次を行った。

1. 対象日を準備した（`prepare_targets`まで）。
2. 各レースについて、固定snapshotの`ARCHIVE_O1`/`O2`から、そのレースのfreeze以前の発表だけを渡した。
   これは、freezeの時刻に開始した取得を模している。
3. 計算・1レース分の出力の公開・読込検証を行った。

学習用datamart・snapshot・機械は上と同じである。

| 項目 | 値 |
| --- | --- |
| 準備（完全snapshotのRA/SE/HC/WC/UMの固定から`prepare_targets`まで） | 63.5秒（1回目は60.7秒） |
| 準備の後の作業セット（そこまでのピークも同じ） | 1.35GB |
| 対象 | 24レース（市場の前の保留0件、計算の保留0件） |
| 1レースあたりの計算・公開・読込検証 | 中央値0.55秒、最大0.80秒（1回目は中央値0.52秒、最大0.72秒） |
| 1レースあたりのレース別Parquetの公開（`update_race`、race-day-odds側） | 中央値0.10秒、最大0.19秒 |
| 1レースあたりのレース別Parquetの読込とhash（`read_race_version`、常駐CLI側） | 中央値0.03秒、最大0.04秒 |
| 行 | 356 |

- レース別Parquetの公開と読込は、実際のraw DBから2025-12-28の24レースを`update_race`で作業用のprocessed rootへ公開し、`read_race_version`で読んで測った（raw DBは読取専用の接続でだけ開いた）。1レースのO1/O2は中央値381行、最大982行で、発走後の発表も含むため、当日のfreeze直後の取得より行数は多い。
  したがって、freezeの後の1レースの処理（公開・読込・計算・公開・読込検証）は合計で約1秒であり、残りの時間の大半はJV-Linkの取得と#53の予測に使える。
- 作業セットはWindowsの`GetProcessMemoryInfo`で測った。プロセス全体のピークは3.66GBだったが、これは計測用のスクリプトが
  比較のために1日分の`ARCHIVE_O1`/`O2`と学習用datamart全体を読んだ分を含み、常駐CLIの値ではない。
- ADR-037の変更の後のコードで、一括の`build-reference-prediction`も同じ条件で再実行した（2026-11-12）。
  - 出力のmanifest SHA-256は`8a44e3d63e8b4f349f06ef3cb6efe4e167bc773cda885d5aeaa3098de05ddd08`、format_version 2、
    `market_source`は`{"kind": "complete_snapshot"}`で、24レース・356行・保留0件だった。
  - 学習用datamartと共通の316行・18,644値で、不一致は0件だった。上の表（2026-11-11）のmanifest SHA-256は
    format_version 1の出力で、現在の読込APIは読まない。
  - 所要時間は91.8秒だった。2026-11-11の207.7秒と差があるのは、OSのファイルキャッシュの状態が異なるためと考えられ、
    直接は比べられない。
- 一括の構築（207.7秒）より準備が短いのは、`ARCHIVE_O1`/`O2`（約3GB）をhashせず、市場を読まないためである。
- 学習用datamartと共通の316行・18,644値で、不一致は0件だった（上の一括の構築と同じ結果）。
  常駐CLIの出力にだけあった3レースも、上と同じく学習用datamartで`target_outcome`だったレースである。

### 制約

- 当日の0B41/0B42の取得の所要時間と、発走6分前の発表がfreezeまでに届くかは、最初の開催日に確かめる（#54）。
- 計算の時間には、#53の予測の時間を含まない。
