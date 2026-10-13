# ADR-017: 説明変数候補の監査境界を分離する

- Status: Superseded
- Date: 2026-10-11
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: [ADR-019](ADR-019-unify-feature-builders-and-common-contracts.md)

## Context

F01〜F21は、履歴窓、閾値、集計式、JRA-VAN業務コードの解釈、利用可能時点の
証跡が未確定の設計候補である。未承認の規則を特徴量コードへ埋め込むと、結果由来
データや未来データの混入を検出できず、現行の数値`FeatureSchema`へ誤って投入する
可能性がある。一方、上流で正規化した候補値を同じ監査規則で検証し、後続の規則
確定・比較へ渡す境界は必要である。

## Decision

1. `src/features/recent_performance.py`〜`src/features/opponent_pagerank.py`がそれぞれ
   1候補群の仕様を所有し、
   `src/features/explanatory_variable_candidates.py`は共有の入力・時点監査・出力境界を
   担当する。raw SQLite、JV-Link、外部通信、JRA-VAN業務コード解釈は行わず、上流で
   作成済みの明示的な`CandidateRecord`だけを受け取る。各候補モジュールと共有境界は
   F01〜F21の候補行を作成・正規化するが、業務式そのものは計算しない。
2. `model candidate-features`をJSON入力のCLI境界とする。各群は値、
   `available_at`、`source_event_at`、`source_scope`、`status`、対象結果・未来データ
   の明示フラグを持ち、未指定の漏洩確認フラグは拒否する。
3. `freeze_at`は呼び出し元が明示する入力固定時刻とし、発走5分前を暗黙の既定値に
   しない。非欠損値の`available_at`、指定された`source_event_at`は
   `freeze_at`以下でなければならない。欠損値は補完せず保持する。
4. 対象レース結果、未来データ、結果由来の列名、未確定値、対象レースを含む履歴
   参照を拒否する。F19は設計文書で定義された市場列と4券種の総票数列だけを受け付け、
   券種別総票数は同一レース内で共通であることを検証する。
5. 候補群の出力は現行`FeatureSchema`のallow-listへ自動投入しない。各候補の業務式、
   列・型・単位、履歴窓、採用規則は、提供仕様とDEC-04/05/12/13を確定した後に、
   別のAccepted ADRと特徴量ごとの実装単位で追加する。

## Consequences

### Positive

- 未承認の候補式を推測せずに、候補値の時点・欠損・漏洩境界を再利用できる。
- F01〜F21を現行モデルへ混入させず、候補の比較・採用前に監査結果を保存できる。
- CLIとPython APIの入力契約を同じ監査結果へ集約できる。

### Negative and follow-up

- このADR単体では、正規化前のraw列からF01〜F21を算出しない。業務式とデータ
  契約が確定した後続ADRが必要である。
- `freeze_at`を発走5分前として運用する場合は、発走予定時刻の版、取得・受信余裕、
  遅延・取消規則を別途確定する必要がある。

## Validation

F01〜F21の全群、欠損保持、時点境界、結果由来列、F19市場列、レース整合性、CLIの
JSON入出力をpytestで検証する。全体のRuff、mypy、pytest、guarded workflow回帰を
実行する。
