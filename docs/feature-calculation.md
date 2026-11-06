# 証跡付き正規化観測からの特徴量計算

[ADR-028](decisions/ADR-028-calculate-all-feature-groups-from-timestamped-observations.md)に基づき、
既存21ファイルの`calculate_*`が実際の数値計算を行う。
`build_*`と計算済み値のJSON契約、元の3中間表の列・metadata、モデルの旧数値allow-listは維持する。
追加の明示数値投影は[モデル入力準備](model-input-preparation.md)で扱う。
計算結果の列は[説明変数一覧](feature-list.md#5-正規化観測から計算する21群)を参照する。

## 入力と証拠の境界

追加CLIは次の形のJSONを読む。`observations`の各要素は、1レースの`ObservationInput`である。

```json
{"schema_version": 1, "observations": []}
```

空配列は計算できない。実際の各要素には`freeze_at`、`card`、`history`、`coverage`、
`workouts`、`pedigrees`、`markets`を全て指定する。
完全なフィールド・型は[source契約](../src/make_features/contracts/observations.py)に定義する。
未指定キーや余分なキーを受け付けず、当該出馬表には結果フィールドを設けない。

距離はm、時間は秒、体重・斤量はkg、オッズはdecimalの正規化済み値とする。
測定済みの`last3f_sec / race_last3f_sec`は終い600mに固定し、測定距離が600m以外または
不明なら入力を拒否する。400m等を比例換算したり履歴平均へ混ぜたりしない。
秒が欠損した原観測は、元の欠損理由を保持する。
識別子とカテゴリは文字列で保持する。父・母父は既に意味を照合した識別子を渡し、血統配列の
添字やrawコードの意味・倍率を計算側で推測しない。
`CardRunner`や`PedigreeObservation`のNULLは、凍結時の正規化原観測で不明であることを示す。
履歴のNULL測定値は`HistoricalRunner.missing_reasons`で原観測の理由を必須とする。
調教・レースラップの区間は実施順の`distance_m / seconds`を持ち、NULL秒を0へ置き換えない。

各原観測は`SourceEvidence`を必須とし、論理観測ID、出典、正整数の版、原観測のSHA-256、
timezone付きの実際の発表・受信・事象時刻を指定する。同一観測・同一版で正規化内容が競合する場合、
改訂順が一意にならない場合、通常結果の全馬・確定順位・対象馬集合が一致しない場合は拒否する。
`card.evidence.event_at`は出馬表の観測事象であり、別の`scheduled_start_at`を代入しない。

この検査は入力された証跡宣言の整合性を調べるもので、外部の原本や受信記録を独立に照合した証明ではない。
利用者は、原観測とhash・版・受信履歴の対応を先に確認する必要がある。
現存raw/Parquetの更新時刻や日付から証跡を作る機能はない。

`Coverage`は収録範囲・馬集合・完全性とその証跡を宣言する。全群計算にはhistory、workouts、
pedigree、marketの完全な証跡が必要で、不足を全欠損の成功へ変換しない。
history/pedigreeは`history_start`から、workoutsは`days_window`日前から、marketは
基準anchorの最大許容遅延まで含めてfreezeまでを覆う必要がある。
history/pedigreeは対象馬と選択された履歴全馬、market/workoutsは固定対象馬を覆う。
個別F15は、不完全な履歴も観測件数と`history_complete=false`として表現できる。

## 明示する計算設定

`configs/feature_calculation/calculate.yaml`は全項目が`???`の必須設定である。
運用既定値や自動選定はない。独自のHydra設定に、必要な選定証跡と次の選択を全て指定する。
設定は`parameters`だけを持つmappingとし、CLIの反復`--override`で上書きできる。

| 設定 | 意味 |
| --- | --- |
| `rule_id / evidence / history_start` | 規則版とその選定証跡、承認した履歴開始日。 |
| `lag_count / count_window / days_window / half_life_days` | lag列数、馬別件数窓、JST日数窓、EWMAの経過日半減期。 |
| `condition_keys / condition_window_order` | 正規化条件の完全一致キーと、F05で条件抽出を件数窓の前・後のどちらに行うか。 |
| `smoothing_alpha / minimum_count` | 率の平滑化強度と少標本表示。alpha=0は明示的な無平滑、正なら同じ過去母集団からpriorを計算する。0件をpriorで補完しない。 |
| `partial_rank / tie_policy / metric / metric_direction` | 部分観測比較の可否、competition同値順位、F04/09/15の対象指標と大小方向。 |
| `class_order` | 低い順の正規化クラスID。含まれないクラスの昇降は不明。 |
| `style_window / style_minimum_count / leader_threshold / front_threshold` | 排他的脚質推定の履歴数と閾値。未知脚質をその他へ置き換えない。 |
| `pedigree_include_self` | 産駒集計へ対象馬自身の過去出走を含めるか。 |
| `workout_distance_m / workout_section_distance_m` | 終い時計の距離と、最後の区間・加速を比較する等距離区間。 |
| `market_anchor_seconds / market_max_age_seconds / market_version_tolerance_seconds` | Fからの基準anchor間隔、観測の最大古さ、単複と馬連の発表版の許容差。 |
| `graph_days / graph_half_life_days / graph_edge_rule / graph_base_weight` | 対戦範囲、半減期（nullは無減衰）、all_pairs/winner_only、inverse_field_minus_one/unit。 |
| `graph_damping / graph_tolerance / graph_max_iterations` | PageRankの減衰・L1収束条件と反復上限。未収束は失敗。 |

率の母集団は、F05が設定した条件件数窓、F07/08/11/14がW日窓である。
騎手・調教師・産駒の条件集計を馬別n走窓で切らず、同時刻の全出走を保持する。
F15の初条件は件数窓によらず、宣言された履歴開始日・範囲内の観測全体で判断する。
真の生涯初出走を自動的に意味しない。
F11で過去の騎手・調教師が不明で組合せの所属を判断できない行は、該当する件数・率・頻度を
NULLとする。既知の異なる相手は非一致として扱う。F20も固定相手の枠・調教師が不明なら
該当する相手集合の統計をNULLとし、能力値だけの部分測定とは区別する。

## 時点、欠損と計算結果

対象レースのJST暦日より前の履歴だけを、各入力のfreezeまでに発表・受信した版から選ぶ。
当該結果と同日結果は採用しない。F03の各過去出走の基準勝者も、その出走日より前かつ
その開始時刻までに利用可能だった版だけを使う。train末の基準を古い行へ配らない。

共通集計は母標準偏差、経過日EWMA、日単位の傾きを使い、先に選んだ窓の欠測を古い有効値で埋めない。
1件の標準偏差、同一時刻だけの傾き、分散0の標準化、0分母はNULLとなる。
脚質はleader/front/other/unknown、クラス変化はsame/up/down/NULLであり、数値へ符号化しない。
末尾の要求距離までの調教区間やレース半距離に正確な境界がなければ、比例配分せずNULLを返す。

市場入力の馬IDと組合せは固定出馬表へ対応させる。票数のキーは`tansyo / fukusyo / wakuren / umaren`で、
全て券種全体の総票数である。馬別票数を逆数オッズから復元しない。
不完全な発売・quote集合には完全分母の支持率を与えず、完全性フラグとNULL理由を出す。
票数減少・訂正は勝手に投票流入と解釈せず拒否する。
各市場anchorで単複・馬連両方の発表と受信時計を満たす最新版を選び、後の訂正版によって
過去anchorで使えた旧版を失わない。PageRankの時間減衰はレース実施時刻を基準とし、
同じ結果の後日訂正で経過時間を若返らせない。

出力JSONは既存の`records/groups/values`と監査を含み、`parameters`、全群の`dependencies`、
群別の欠損理由・診断、原測定の`source_missing_reasons`を追加する。
非欠損群のavailable_atは全依存の最大である。履歴系の依存は選択した履歴母集団全体を保守的に含む。
当該カード・パラメータ・完全性・他馬・基準・市場等の混合依存をmanifestへ保持し、
歴史レースIDに当該カードのIDを混ぜない。市場群のscopeはpre_race、その他はhistoricalとする。
PageRankは既知ノード・辺・反復数・残差・総和を記録し、未知馬のscoreはNULLとする。
馬別履歴・担当者・基準・補正値とグラフの同一入力での再計算はcontext内で共有する。

## 実行と既存APIへの接続

```powershell
uv run python src/main.py model calculate-features --input output/inputs/normalized.json --output output/features/calculated.json --config-dir output/feature-config
```

`output/feature-config/calculate.yaml`には全必須値を指定しておく。
出力は新規ファイルに限り、入力・既存成果物・リンク先を上書きしない。
エラーは標準エラーへJSONで出し終了1、成功は行数・群数を表示する。
import/help時には設定や入力を読まない。

Pythonでは`generation.calculate.calculate_features`を呼び、`result.built.rows`を既存の
`build_feature_table`へ渡せる。Parquetの各値列型は呼出し元が明示し、既存の登録名・metadata・
時点・列整合検査を維持する。計算CLIは値と依存JSONを保存し、モデル列の選定や学習を行わない。

専用テストは21群の手計算、未来・同日・当該結果追加後の不変性、基準自己混入、
完全集合不足、未知・欠損・0分母・測定距離、グラフ向き・未知馬・未収束、
実ファイルCLIと全21表の明示型Parquet往復を検証する。
これは合成した正規化観測の検証であり、現存データでの厳格な学習・最新予測の実績ではない。
