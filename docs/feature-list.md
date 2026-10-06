# 説明変数一覧表

## 位置付け

この文書は、現行実装における説明変数の列契約を整理したものである。対象は、
学習・推論の `FeatureSchema` が受け付ける変数と、`src/features/` が作成する
中間テーブルの値列である。中間テーブルの列が、そのままモデルの説明変数に
なることを意味しない。

業務コードの解釈、過去成績の集計方法、発走前オッズ履歴の時点再現など、実装で
確定していない内容は推測で補わない。モデル境界は [ADR-010](decisions/ADR-010-implement-ranking-model-boundary.md)、
時点監査は [ADR-011](decisions/ADR-011-feature-generation-temporal-audit-and-walk-forward.md)、
中間テーブルは [ADR-012](decisions/ADR-012-feature-intermediate-tables-and-datamart.md)
に従う。

## 1. モデルへ投入可能な説明変数

現行の承認済み `FeatureSchema` で、モデルへ投入できる説明変数は次の2つだけで
ある。列の並び順は、利用する `FeatureSchema` が明示的に保持する。

| 変数名 | 位置付け | 生成規則 | 型 | 単位 | 利用可能時点 | 欠損時の扱い |
| --- | --- | --- | --- | --- | --- | --- |
| `ability` | レース前能力値。業務上の具体的な算出方法は未確定 | `pre_race_ability_v1` | numeric | `score` | 値がある場合は `available_at <= freeze_at` | `None` / `NaN` を保持し、補完しない |
| `historical_odds` | 履歴オッズ。対象時点の選択・集計規則は未確定 | `historical_odds_v1` | numeric | `decimal` | 値がある場合は `available_at <= freeze_at` | `None` / `NaN` を保持し、最終オッズなどで補完しない |

`FeatureSchema` は値の型を numeric に限定し、承認済みの生成規則・単位・欠損方針と
一致しない定義を受け付けない。上表の変数名を変更したり、新しい変数を追加したり
する場合は、生成規則と利用可能時点を確定してから承認済み allow-list に追加する。

## 2. 特徴量別の中間テーブル

`src/features/` では、特徴量の生成・検証・再計算単位を分離するため、次の値列を
中間 Parquet テーブルとして扱う。これらは現時点で数値 `FeatureSchema` に自動投入
されない。

| 中間テーブル | 列名 | 型 | 値の定義 | 欠損・変換 | モデル投入 |
| --- | --- | --- | --- | --- | --- |
| `previous_race_result` | `previous_race_finish_position` | `int64` | 直前レースの着順 | 入力が欠損なら `NULL`。値の業務コード解釈や過去レースの選択規則は未確定 | 自動投入しない |
| `odds_ratio` | `odds_ratio` | `float64` | `odds / reference_odds` | `odds` または `reference_odds` が `None` / `NaN` なら `NULL` に正規化。入力は正数、比率は有限値に限定 | 自動投入しない |
| `pedigree` | `sire` | `string` | 父の識別子 | 欠損なら `NULL`。カテゴリ符号化は行わない | 数値 FeatureSchema へ自動投入しない |
| `pedigree` | `broodmare_sire` | `string` | 母の父の識別子 | 欠損なら `NULL`。カテゴリ符号化は行わない | 数値 FeatureSchema へ自動投入しない |

中間テーブルには、値列に加えて次の共通列を持つ。

| 列名 | 型 | 役割 |
| --- | --- | --- |
| `race_id` | `string` | レース識別子 |
| `horse_id` | `string` | 馬識別子 |
| `freeze_at` | `timestamp[us, UTC]` | 予測入力を固定した時刻 |
| `available_at` | `timestamp[us, UTC]` または `NULL` | その中間値が利用可能になった時刻 |

値が欠損でない場合は `available_at` を必須とし、`available_at` は `freeze_at` より
後であってはならない。datamart へ結合した後は、共通の `available_at` は
`<feature_name>__available_at` として特徴量ごとに保持される。

## 3. 説明変数ではない列

- `race_id`、`horse_id` は識別子であり、説明変数ではない。
- `freeze_at`、`available_at` は時点監査用のメタデータであり、説明変数ではない。
- `finish_position` は学習時の正解である。1着・2着・3着をそれぞれラベル3・2・1、
  4着以下をラベル0へ変換するが、説明変数へは含めない。現行実装は、通常の確定済みで
  一意かつ連続した着順と、予測対象レースが3頭以上であることを前提とする。同着、取消・
  失格、未確定結果、3頭未満のレースの扱いは、現時点では未実装・未確定である。
- 確定着順、結果、払戻、人気、最終オッズなど結果由来の列名は、モデルの
  FeatureSchema で拒否する。

## 4. 共通の制約

1. モデル入力の欠損値は `None` / native `NaN` のまま保持する。中間テーブルでは
   欠損値を `NULL` として保存し、`odds_ratio` の入力 `NaN` は `NULL` に正規化する。
   いずれも行削除や別期間の値での補完を行わない。
2. 非欠損値には利用可能時刻を付与し、`available_at <= freeze_at` を満たすことを
   監査する。
3. `historical_odds` や中間テーブルのオッズ値を、後から取得した最終オッズで
   置き換えない。
4. 血統の文字列列を、辞書・カテゴリ符号化を決めないまま数値説明変数へ変換しない。
5. JRA-VAN の業務コード解釈、履歴集計、時点付きデータからモデル入力へ写像する
   規則は、別途確定するまで未実装・未確定として扱う。

## 参照

- [ランキングMVP 詳細実装設計](implementation-design.md)
- [ADR-010: ランキングMVPの実装境界と成果物契約](decisions/ADR-010-implement-ranking-model-boundary.md)
- [ADR-011: 明示入力による特徴量生成・時点監査・Walk-forward](decisions/ADR-011-feature-generation-temporal-audit-and-walk-forward.md)
- [ADR-012: 特徴量単位の中間テーブルとdatamart結合](decisions/ADR-012-feature-intermediate-tables-and-datamart.md)
