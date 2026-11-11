# ADR-036: 当日の未確定レースの参考特徴量をラベルなしで構築する

- Status: Accepted
- Date: 2026-11-11
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #51、Refs #37・#52・#53・#54・#46・#61
- Supersedes: N/A
- Superseded by: N/A

---

## Context

ADR-034の参考datamartは、対象レースの通常の確定結果をラベルとして読み、結果がない対象を
`target_outcome`で保留する。ADR-035のtop-3 PLは、このdatamartで学習・評価する。当日の予測（#53）には、
結果がまだないレースについて、学習と同じ計算器・同じ列・同じ`available_at`の規則の特徴量が必要である。

`normalize_reference_target`は、もともと結果を読まずに対象の観測を作る。ビルダーは、その後で結果を読む。
一方で、ビルダーは年のRA/SEの全行を履歴として正規化する。そのため、当日の未確定の行が履歴の保留になり、
`KettoNum`の空の行では構築全体が失敗する。

また、2026-11-11の時点では、当日の完全snapshotの市場（O1）・調教・血統が当日の時点まで揃っているとは限らない。
`[latest]`は`RACE`と速報系しか取得しない。

---

## Decision

1. **ラベルなしモード。** `ReferenceDatamartBuilder(labeled=False)`は、ADR-034と同じ計算を、結果のない対象日1日
   （`target_start == target_end`）について行う。複数日を拒否するのは、前の対象日の結果が後の対象日の
   履歴になるため、ラベルなしでは複数日で値が一致しないからである。
   - 対象日より前の行だけを履歴として検証・正規化する。対象日の見る履歴は、利用境界が対象日の0時（JST）以前の
     接頭辞なので、値は変わらない。
   - 対象のRA/SEは、出馬表の列（`CARD_RA_COLUMNS`・`CARD_SE_COLUMNS`）に射影してから、重複除去・正規化・
     計算器に渡す。ラベルの入力は空にする。結果の列は構造上どこからも読めない。
   - `reference_label`を呼ばず、`finish_position`とラベルの列を出力しない。
   - 対象のO1に、freeze_atより後の発表が一つもなければ、`target_pre_freeze`・
     `market_not_observed_after_freeze`で保留する。snapshotには作成時刻がないため、freezeより前に取った
     snapshotの最新の発表を、黙ってfreezeの値として使うことをデータで防ぐ。
   - 保留と致命的な失敗の規則は、`target_outcome`がないことを除いてADR-034と同じである。
2. **学習用datamartへの固定。** 新しいCLI `datamart build-reference-prediction`は、学習用datamartの
   パスとmanifestのSHA-256（必須）を受け取る。
   - 計算設定と参考規則は、そのmanifestの`preparation_config`だけから取る（Hydraの設定は読まない）。
   - snapshotを読む前に、計算契約（設定・規則・列名）、閉じた数値列の内容（群・列・意味・単位）、特徴量定義がmanifestと一致することを検証する。snapshotを固定した直後に対象日のレースの有無を確かめ、ない場合は履歴を読む前に失敗する。
   - 計算器のコードの同一性は計算契約に含まれない。学習時の`provenance.source_sha256`を記録するだけで、
     一致は要求しない。
3. **保存形式`reference_prediction_features`（format_version 1）。** ディレクトリの構造と検証は
   ADR-034のdatamartと共有し、次の点だけが異なる。
   - 行・レースにラベルの列がない。heldの形式名は`reference_prediction_features_held_races`である。
   - Parquetのmetadataに`format`を含め、table_kindを`reference_prediction_rows`・`reference_prediction_races`とする。
     学習用datamartのmetadataのバイト列は変えない。
   - manifestは`label`を持たず、`source_datamart`と`freshness`を持つ。
   - `source_datamart`の内容: 学習用manifestのSHA-256、計算契約のSHA-256、対象期間、
     `label_usable_through`（学習用datamart全体の`label_usable_after`の最大値。どの学習foldの境界よりも遅いか等しい、保守的な上限）、`provenance_source_sha256`。
   - `freshness`の内容: HC・WCごとの、読み込んだ調教の窓（対象日の`days_window`+1日前から前日まで）の中の最新の調教日（窓の中になければnull）、出馬表の馬の数とそのうち`NL_UM_UMA`に行がない数、
     直近の履歴の保留件数（`history_held_recent`）とその窓の日数（`history_held_recent_window_days`）。
   - 読込API`read_reference_prediction_features`は、ラベルに依存しない検証をすべて行い、次も検査する。
     - 全レースが対象日の日付であること。
     - `history_usable_through`が対象日の0時以前であること。
     - 保留のうち`history_result`は対象日より前のレースの`role=history`だけで、それ以外の段階は対象日のレースの`role=target`だけであること。
     - `source_datamart`の形式と、計算契約との一致。
4. **#52・#53への引き継ぎ。**
   - 予測には、モデルを学習した学習用datamartと`source_datamart.manifest_sha256`が完全に一致する特徴量だけを使う。
   - 学習に使ったラベルの利用境界が、予測の最初のfreeze以前でなければならない。予測の特徴量は、学習用datamart全体の`label_usable_through`を持つ。#52は、学習foldだけの境界を別に保存してもよい。
   - heldは`role == "target"`で絞って読む。
   - ADR-030の要求どおり、`assurance`の結果の利用境界の情報を予測へ残す。
5. **鮮度は記録だけ。** 当日のsnapshotで調教・血統が古いと、学習時より特徴量が欠ける。ラベルなしの構築は
   これを`freshness`として記録し、stderrにも出すが、失敗にはしない。取得の修正は#61で扱う。

---

## Rationale

- ラベルの処理は計算の後に続く別の段階であり、計算器はラベルを読まない。既存のビルダーを共有すれば、
  学習と予測で同じ計算を保証でき、同値テストで確かめられる。
- 対象日の行を履歴から外しても、日付の接頭辞の規則により値は変わらない。それでいて、当日の未確定の行による
  失敗をなくせる。
- 外部から与えたSHA-256で学習用datamartを固定する方式は、`model evaluate-pl`と同じである。manifestだけを
  読めば、全体の読込（約50秒・約2GB）を避けられる。
- 市場の観測の要求は、snapshotの作成時刻がない現状で、freezeの値が完全であることを確かめる唯一の
  データ上の根拠である。

---

## Consequences

### Positive

- 学習用datamartと同じ値の特徴量を、結果のないレースについて作れる。実データの2025-12-28では、共通の316行・
  18,644値が学習用datamartと完全に一致した（`docs/experiments/reference-prediction-features.md`）。
- 予測の特徴量と、学習に使ったdatamart・ラベルの利用境界が、manifestで機械的に結び付く。

### Negative

- 1日分でも全履歴をたどり直すため、実データで約3.5分・約4.6GBかかる。
- 当日の市場は、freezeの後の発表がsnapshotに入るまで使えない。#37までは、当日の発走前の予測には使えない。
- O1で取消が示されたレースは、学習と同じく保留される（#46）。

### Neutral / Follow-on effects

- `make_datamart/tables/reference.py`は、形式ごとの違いを一つの`_Layout`にまとめ、二つの形式を検証する。
- 学習用datamartの部分読込API（`read_reference_datamart_manifest`・`read_reference_datamart_label_usable_through`）を
  追加した。

---

## Alternatives Considered

### Option A: 学習用datamartの形式で`finish_position`をnullにする

Summary:

既存の形式をそのまま使い、ラベルの列をnullにできるようにする。

Advantages:

- 新しい形式名や読込APIが要らない。

Disadvantages:

- 学習用とラベルなしのファイルを取り違えても、読込で区別できない。学習用の読込の検証（着順の連続性など）を弱める。

Reason not selected:

学習用datamartの検証と、公開済みファイルのバイト列を変えずに、取り違えを検出するため。

### Option B: 履歴の索引を一度作り、市場だけを後で差し替える2段階の構築

Summary:

当日の朝に履歴をたどって状態を保存し、freezeの後に市場だけを加えて計算する。

Advantages:

- 発走前の短い時間に何度も実行できる。

Disadvantages:

- ビルダーの状態の永続化という新しい契約が要る。計算の一致の保証が難しくなる。

Reason not selected:

最小運用では1回あたり数分で足りるかを、#54で計測してから判断する。

### Option C: 計算設定をHydraの設定から読む

Summary:

`build-reference`と同じく、Hydraの設定で計算設定を与える。

Advantages:

- 既存の設定の方式と揃う。

Disadvantages:

- 学習時と異なる設定を誤って与えうる。一致を検査しても、設定の二重管理になる。

Reason not selected:

学習用datamartのmanifestを唯一の出典とし、契約の一致を構造上保証するため。

---

## Implementation Notes

- ビルダー: `models/serialization/reference_datamart.py`（`labeled`、`prediction_manifest`、`freshness`）。
- 保存と読込: `make_datamart/tables/reference.py`。
- 設定の検証: `configuration/reference_datamart.py`（`validate_reference_datamart_config`）。
- CLI: `cli/reference_datamart.py`。

---

## Validation

- fixtureで、各対象日のラベルなしの出力が、学習用datamartの同じ日の行と全数値列・`available_at`・レースの列で
  一致することを確かめる。
- 対象日の結果の列を発走前の形や任意の値に変えても、ラベルなしの出力が変わらないことを確かめる。
- 当日の行の異常（`KettoNum`の空、`Umaban="00"`、`HassoTime`の欠落）が、該当する対象だけの保留になることを確かめる。
- freezeの後の市場がない対象の保留、読込APIの拒否、CLIの成功・失敗・中断を確かめる。
- 実データの2025-12-28で、学習用datamartと値が一致することを確かめた。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 当日のsnapshotで調教・血統が古い | 特徴量が欠け、学習時と分布がずれる | `freshness`に記録する。取得の修正は#61 |
| 出馬表・発走時刻のfreeze後の変更 | まれに学習時と値の意味がずれる | snapshotを取る時刻を#54で定める |
| 計算器のコードの変更 | 契約が一致しても値が変わりうる | `provenance_source_sha256`を記録し、#53で扱いを決める |
| race-day-oddsと同じ機械での実行 | 約4.6GB・数分の負荷で取得が遅れうる | READMEで注意する。#54で順序を決める |

---

## Security / Privacy Impact

セキュリティやプライバシーへの影響はない。認証情報を読まず、出力にも残さない。

---

## Operational Impact

- 当日の予測の前に、`latest`と完全snapshotの公開が必要である。freezeの後のO1がsnapshotにない対象は保留される。
- 出力の`preparation_config`は、解決済みの絶対パスを記録する。

---

## Migration / Rollback

### Migration

既存の学習用datamartとその読込は変わらない。新しい形式は新しいCLIの出力だけである。

### Rollback

新しいCLIと形式を使わなければよい。学習用datamartには影響しない。

---

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `docs/rules/architecture.md`
- [ ] `AGENTS.md`
- [x] `README.md`
- [x] APIとユーザー向けの文書（`docs/table-definition/README.md`、`docs/experiments/reference-prediction-features.md`）
- [ ] 運用文書・運用手順書（#54）

---

## Follow-up Actions

- [ ] 当日の発走前オッズを市場の入力につなぐ（#37）。
- [ ] 当日の取得で調教・血統の表も更新する（#61）。
- [ ] 当日の運用手順で、構築の時点と所要時間を定める（#54）。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-11 | Accepted | 結果のない対象日1日について、学習用datamartに固定したラベルなしの参考特徴量を構築することを決定 |
