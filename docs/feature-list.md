# 説明変数一覧表

## 位置付け

この文書は、現行実装における説明変数の列契約を整理したものである。対象は、
学習・推論の `FeatureSchema` が受け付ける変数と、`src/make_features/` が作成する
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

`src/make_features/` では、特徴量の生成・検証・再計算単位を分離するため、次の値列を
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
5. JRA-VANの業務コード解釈と、原本から時点証跡付き正規化観測への変換は未実装である。
   正規化済み観測からの21群の純粋計算をADR-028、承認済み数値列を明示選択して
   モデル入力へ投影する経路をADR-029で実装した。全列の自動採用は行わない。

## 5. 正規化観測から計算する21群

[ADR-028](decisions/ADR-028-calculate-all-feature-groups-from-timestamped-observations.md)で
各既存ファイルへ`calculate_*`を追加した。完全な入力・パラメータと時点・欠損契約は
[計算手順](feature-calculation.md)を参照する。以下は実際に出力する列名で、`{k}`は
明示lag数、`{metric}`は設定で選んだ指標である。窓長や規則は出力パラメータへ保存し、
候補文書の`_n / _W / _h`という名前をそのまま列へ使わない。

| 群 | 計算する主な列・型 | 単位・母集団 |
| --- | --- | --- |
| F01 | `past_finish_lag{k}` int、`past_finish_relative_lag{k}` float、`past_start_count / past_win_rate / past_top3_rate` | 着順、割合、馬別n走。 |
| F02 | `past_elapsed_sec / past_signed_gap_sec / past_velocity_mps / past_last3f_sec / past_last3f_rank / past_last3f_relative / past_last3f_known_count`の`_lag{k}` | 秒、m/s、過去全馬の終い600m測定での順位・既知数。 |
| F03 | `past_condition_{time,velocity}_advantage`、`past_ability_{time,velocity}_{mean,ewma}` float、`past_condition_reference_count`と`_lag{k}` int | 過去出走ごとの自己を含まない勝者基準、score。現行`ability`への自動写像ではない。 |
| F04 | `past_{metric}_{mean,max,std,ewma,trend,count,valid_count}` | 元指標、傾きは元指標/日、件数はint。 |
| F05 | `horse_condition_{start_count,win_rate,top3_rate,relative_finish_mean,small_sample,smoothed_win_rate,smoothed_top3_rate,prior_win_rate,prior_top3_rate}` | 条件件数窓。率float、件数int、少標本bool。 |
| F06 | `days_since_previous_start / starts_in_window_days / distance_delta_m` int、`surface_changed` bool、`class_transition` string | JST暦日、W日、m。 |
| F07 | `jockey_* / jockey_condition_*` | F05と同じ率・件数・priorの組、騎手のW日全騎乗。 |
| F08 | `trainer_* / trainer_condition_*` | 同じ組、出走当時の調教師に属したW日全出走。 |
| F09 | `relative_{metric}_{rank,mean_diff,leader_gap,zscore,known_count,field_size}` | 固定馬集合、既知数/頭数int、他float。 |
| F10 | `race_distance_m / horse_age_years / gate_number / frozen_field_size` int、`carried_weight_kg / carried_weight_delta_kg` float、`horse_number / sex / surface / venue / course / going / class_code` string | 正規化カード、前走斤量差。番号文字列のゼロを保持。 |
| F11 | `horse_jockey_* / jockey_trainer_*`、`horse_jockey_frequency` float、`jockey_changed_since_previous` bool | W日組合せ出走、頻度の分母は馬の出走数。 |
| F12 | `past_corner4_relative_lag{k} / past_corner4_to_finish_gain_lag{k} / past_corner4_to_finish_relative_gain_lag{k}`、`past_corner4_relative_mean / past_corner4_relative_std / past_corner4_valid_count` | 相対位置、順位改善、馬別n走。 |
| F13 | `pre_race_style` string、`field_leader_count / field_front_count / style_unknown_count / opponent_leader_count / opponent_front_count / opponent_unknown_count / opponent_known_count` int、`opponent_front_share` float | 排他的脚質と固定集合、自身を相手へ数えない。 |
| F14 | `{sire,broodmare_sire}_condition_*` | F05の率・件数・priorの組と`offspring_count`、W日産駒出走。 |
| F15 | `past_observed_start_count / condition_observed_start_count / past_metric_valid_count` int、`history_complete / is_first_observed_start / is_first_condition / has_metric_history` bool、`past_missing_reason` string | 宣言scope内の全観測。件数窓内の初条件ではない。 |
| F16 | `past_weight_lag1_kg / past_weight_delta_last2_kg / past_weight_mean_kg / past_weight_std_kg / past_weight_vs_mean_kg / past_weight_ratio_mean` float、`past_weight_valid_count` int | 過去計量だけ、kg・比。 |
| F17 | `{hc,wc}_{last_clock_sec,last_section_sec,finish_accel_sec,clock_mean_sec,clock_best_sec,self_clock_diff_sec,same_day_course_diff_sec}` float、`{hc,wc}_{workout_count,self_reference_count,same_day_reference_count}` int | 指定距離の末尾時計、W期間と同施設/コース、自己基準はW内で当該記録より前。 |
| F18 | `past_{race_early_velocity_mps,race_late_velocity_mps,pace_velocity_gap_mps,last3f_vs_race_sec}_lag{k}` float | 過去レースの正確な半距離、m/s・秒。 |
| F19 | 既存`market_*`、`market_pair_support_i`、`ticket_total_{type} / ticket_total_growth_{type} / ticket_total_growth_rate_{type}`、追加`market_pair_known_opponent_count` int、`market_complete_win_set / market_complete_pair_set` bool | 同時点の単複・馬連、typeはtansyo/fukusyo/wakuren/umaren。票数は券種全体。 |
| F20 | `{same_gate,same_trainer}_{peer_count,known_peer_count}` int、`{same_gate,same_trainer}_{ability_diff,ability_rank}` float | 固定相手とF03の標準化時間能力平均。差は無次元で、metric設定によらない。 |
| F21 | `opponent_graph_score` float、`opponent_graph_start_count / unique_opponent_count` int、`opponent_graph_known` bool | 期間内全通常結果のloser→betterグラフ。未知scoreはNULL。 |

全列はNULL許容とする。保存のArrow型は利用者が明示し、実行結果の型から自動推測しない。
原測定理由、群別の欠損理由、件数・基準・グラフ診断、採用した版の全依存をJSON manifestへ保持する。
計算APIは既存明示値APIと並存する。業務rawコードの意味・受信証拠の復元や、モデル列採用は行わない。

## 参照

- [ランキングMVP 詳細実装設計](implementation-design.md)
- [ADR-010: ランキングMVPの実装境界と成果物契約](decisions/ADR-010-implement-ranking-model-boundary.md)
- [ADR-011: 明示入力による特徴量生成・時点監査・Walk-forward](decisions/ADR-011-feature-generation-temporal-audit-and-walk-forward.md)
- [ADR-012: 特徴量単位の中間テーブルとdatamart結合](decisions/ADR-012-feature-intermediate-tables-and-datamart.md)
