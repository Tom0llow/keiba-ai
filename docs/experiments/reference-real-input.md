# 固定snapshotから全21群で参考学習・予測する

2026-11-01のユーザー選択に基づく現行経路である。保存発走予定時刻が当時も有効、
市場発表時に受信済み、保存された出馬情報・血統・過去結果の訂正版時点は未検証という
仮定を明示する。厳格経路とは別の計算契約を使い、実測受信時刻を仮置きしない。
全21群を計算し、[trial設定](../../configs/reference_input/trial.yaml)で各群1列ずつを
明示選択する。全出力が非欠損になることや、収益性を意味しない。

## 入力と固定版

`model prepare-reference-input`はprocessedルートのCURRENTを最初の一度だけ解決する。
`snapshot_id`を指定すればその版へ直接固定する。raw SQLiteは読まず、raw/processedは変更しない。
Arrowで必要列と明示レース・期間だけを読み、読んだ表ファイルのSHA-256を保存・再照合する。
選択O1/O2だけは同じ固定版から該当発表時刻の原行全列も読み、内容の競合と原行hashを保持する。
表ファイルhashはファイル全体を順次読むため、対象レース数を絞っても一定のI/Oを要する。

外部manifestは`races`のみを持ち、各行に完全16桁race_id、予定発走時刻、5分前freeze、
`schedule_known_at: null`を指定する。次は**合成fixtureの形式例**で、実在日程の証拠ではない。

```json
{"races":[{
  "race_id":"2026090601010109",
  "scheduled_start_at":"2026-09-06T15:00:00+09:00",
  "freeze_at":"2026-09-06T14:55:00+09:00",
  "schedule_known_at":null,
  "schedule_source":"assumed_stored_NL_RA_RACE.HassoTime"
}]}
```

実データでは選択した固定版のRA.HassoTimeと必ず一致させる。対象馬は当該freeze以前の
中間O1のUmaban集合から決め、SEのpre-race列でKettoNumへ対応付ける。取消を示す中間符号、
集合不一致や不適格ラベルは、そのレース全体を理由付きで保留する。最終SE.IJyoCDをcard.activeへ使わない。

参照する表はRA、SE、ARCHIVE O1/O2、HC、WC、UMである。履歴は指定history_start以後の
中央01〜10の採用可能な通常結果全頭で、対象馬だけに絞らない。調教の比較相手も前日以前の
指定期間の全馬を保持する。UMは対象と採用履歴全馬の父・母父ID（配列0・4）だけを読む。
現在の累積賞金・成績・担当者を履歴へ流用しない。

## 加工規則と影響

| 判断・Why | Impact | Validation |
| --- | --- | --- |
| 予定発走時刻の300秒前で固定する | stored scheduleの当時有効性は仮定。変更前時計を自動選択しない | manifestと保存時刻・差300秒を照合 |
| O1/O2は区分1、発表時計が各anchor以下の最新のみ | freezeと600秒前anchorを同期。未来・最終・確定値で補完しない | 同時刻異内容拒否、鮮度・60秒整合幅を共通F19で検証 |
| 単勝・複勝4桁、馬連6桁は整数÷10 | 0000、取消記号、上限超過、空欄はNone。通常数値を作らない | 倍率・特殊値・原値/hashのfixture照合 |
| 票数合計は百円単位の票数を保持 | 円へ換算せず、オッズから売上を逆算しない | anchor間非減少と券種集合をF19で検証 |
| 過去結果は通常確定・異常なし・同着なし・全頭順位連続のみ | 部分馬の除外をせず、レース全体を理由付きhold。母集団はこの採用範囲内 | RA頭数、SE集合・馬番・KettoNum・順位を照合 |
| 結果利用は明示delay日を経過した日末より後 | delay=7なら9/13結果は9/21 0時以後。実測確定/受信時計ではない | headMakeDateが宣言日を超える結果をhold、holdout前境界を監査 |
| 当日結果、対象馬体重・時計・最終オッズ・最終馬場を特徴量へ渡さない | target goingと未整備classはNone。昇降級等も欠損を維持 | 対象着順・時計等変更前後で特徴量不変 |
| SE.Timeは分・秒・0.1秒、TimeDiffは符号付き0.1秒 | 1456は105.6秒。BaTaijyuの999/000等は実重量にしない | 単位と特殊値、欠損理由を手計算fixtureで確認 |
| RAラップは200m、端数距離は先頭区間 | 未計測を0秒にせず、総距離一致を検証。半分境界がなければ既存F18がNone | 距離・順序・時計のfixture照合 |
| 調教は前日以前だけを参考利用 | ChokyoTimeは実施時刻。headMakeDateを発表時計にしない。HCのcourse/turnは適用外None | HC/WCの200m区間と同日他馬比較を照合 |
| 血統と出馬情報の過去訂正版は未検証 | ReferenceEvidenceのbasisへ残し、厳格な受信証拠にしない | 旧strict入口が参考型を拒否 |

raw解釈は現在2005年以後、芝TrackCD10〜22・ダート23/24・障害51〜59を対象にする。
未対応トラックをダートへ混ぜずholdする。障害の馬場状態は一律に芝で代用せずNoneとする。
class対応表は未整備なので全てNoneとし、class_orderの単一識別子は順位付けに使用されない。

coverage.completeは固定snapshotと明示採用母集団の中での宣言であり、JRA全量の収録完全性を示さない。
出典の実測時計はnullableのまま保持し、参考利用境界`usable_after`、basis、event_time_basisを別に残す。
同じ原観測の識別・hash・境界を対象レースごとに変更しない。

## Hydraの初期実験設定

`prepare.yaml`は必須値`???`を持ち、暗黙に実データを選ばない。`trial.yaml`は明示的な開始値である。
履歴起点2026-08-01、lag4、件数窓5、日数窓30、半減期30日、条件はsurface/distance、
平滑化2、最低1件、脚質窓3、閾値0.25/0.5、調教800/200m、市場anchor600秒・最大鮮度600秒・
版整合幅60秒、対戦グラフ30日・damping0.85・許容差1e-8・最大200回を使う。
小規模な接続確認を目的とし、最適値の主張やパラメータを当時選定済みという主張をしない。
比較条件・窓・列順・参考規則の変更はschema hashを変える。

## コマンド

今回承認された選択は9/6・9/13の中央race09〜12を学習候補、9/27同範囲を評価候補、
ローカルの10/4同範囲を予測候補とする。結果で候補キーを選び直さない。
新規出力へmanifestを保存した後、次のように準備する。既存出力の上書きは拒否する。

```powershell
uv run python src/main.py model prepare-reference-input --manifest output/real-reference-20261101/train-manifest.json --output output/real-reference-20261101/train-input.json --config-name trial --override processed_root=data/processed --override snapshot_id=098ce3f4b5d7480282269218d80cef05
uv run python src/main.py model prepare-reference-input --manifest output/real-reference-20261101/predict-manifest.json --output output/real-reference-20261101/predict-input.json --config-name trial --override processed_root=data/processed --override snapshot_id=098ce3f4b5d7480282269218d80cef05 --override include_labels=false
```

preparedのheld_races、recordsの日付・レース数、assuranceを確認する。9/27の残存評価レースが
7件であることを確認した場合の学習例は次のとおりである。別データでは末尾件数を明示し直す。

```powershell
uv run python src/main.py model train --override data.input=output/real-reference-20261101/train-input.json --override split.test_races=7 --override mlflow.registered_model_name=reference_all21_trial
uv run python src/main.py model predict --override data.input=output/real-reference-20261101/predict-input.json --override mlflow.registered_model_name=reference_all21_trial --override model.version=1 --override data.selection=latest_date
```

`model.version=1`は新規登録名で最初に得た版を使う場合の例であり、必ず実際に返った厳密版へ合わせる。
`latest_date`はprepared入力内の最大freeze日で、提供元の最新日やライブ取得を意味しない。
参考計算契約は旧walk-forwardでは拒否し、このrunnerの結果利用境界監査を使う。

## 保存・再検証

preparedには元の必要列投影、snapshot/tablefile hash、規則・設定、全21出力、選択列、
原観測を一度ずつ持つsource_catalog、共有依存集合、欠損理由、保留理由を残す。
モデルの読込時には原投影から正規化と全21計算を再実行し、値・availability・全ラベルを照合する。
履歴・出馬表・ラベルで共有するRAはレース6キー、SEはさらにKettoNumで同じ原行を識別し、
重複列を原値のまま照合する。不一致はレース保留にせず入力全体を拒否し、独立したラベル読込でも
ラベル原行と元の投影を照合する。
hashは署名ではなく、管理者による原本とhashの協調的な改変を証明するものではない。

MLflowはprepared一式をartifactに保存し、input.jsonとnative/training.jsonへschema、参考保証、
出典catalog、ラベル原行と利用境界を記録する。互換フィールドlabel_known_throughは、
label_boundary_meaning=declared_usable_afterの場合に実測known時刻を意味しない。
trainラベルの宣言利用境界は最初のholdout freezeより厳密に前、予測freezeは学習末とこの境界の
双方より後を要求する。native形式番号は既存の3を維持し、新契約の版をschemaで区別する。

公式根拠は[JV-Data仕様書4.9.0.1](https://jra-van.jp/dlb/sdv/sdk/JV-Data4901.pdf)
（RA/SE、O1/O2、HC/WC、血統配列、コード表2009）、
[時系列オッズ](https://targetfaq.jra-van.jp/faq/detail?category=47&id=667&site=SVKNEGBV)、
[データ提供内容](https://jravan.jp/dlb/ddata.html)を参照する。
