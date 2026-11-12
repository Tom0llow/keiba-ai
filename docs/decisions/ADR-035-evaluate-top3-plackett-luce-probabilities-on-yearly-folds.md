# ADR-035: 参考datamartの年単位foldでtop-3 PLの着順確率を学習・校正し、市場と比較する

- Status: Accepted
- Date: 2026-11-09
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #34, Refs #33, Refs #48, Refs #49
- Supersedes: N/A
- Superseded by: ADR-038（Decision 3の「モデルは永続化しない」のみ）

---

## Context

[ADR-009](ADR-009-use-lambdarank-mvp-and-top3-pl-extension.md)は、LambdaRankのMVPの後に、top-3
Plackett–Luce（PL）の負の対数尤度をLightGBMのcustom objectiveで学習する拡張を決めた。ただし、
微分の実装、校正の方法、時系列の分割、市場との比較の手順は「実装前に定める」とした
（[仕様書](../specification.md)も同じ）。ADR-009のValidation 4・5は、有限差分による微分の照合、
着順段階別・券種別の校正、同時点の市場確率$q_i=(1/O_i)/\sum_j(1/O_j)$との勝者のLog Loss・
多クラスBrier・帯ごとの校正による比較、レース単位の対応ありbootstrapの95%信頼区間を求める。

Issue #34はこの拡張を求め、Issue #33の残り（年単位fold、validによるearly stoppingと校正、
fold内のラベル利用境界の監査）もこの評価に必要である。入力には
[ADR-034](ADR-034-build-full-period-reference-feature-datamart.md)の参考datamartを使う。
datamartは閉じた数値列36列（freeze時点の単勝オッズ`market_characteristics__market_win_odds`を含む）、
レースごとの`label_usable_after`、1..nの連続した着順を持ち、同着・異常区分・取消のレースは
保留されて入らない。

既存の`RankingDataset`はPythonのdict行を1行ずつ検証し、`walk_forward.py`はレース数で区切り、
計算契約付きの入力を拒否してvalidを学習に使わない。どちらも全期間（約84万行）のPL学習には向かない。

---

## Decision

1. **PLの損失と微分。** レースごとに、実際の1〜3着を順に選ぶtop-3 PLの負の対数尤度
   $L_r=\sum_{k=1}^{3}(\mathrm{logsumexp}_{S_k}(s)-s_{\pi_k})$を使う（$S_k$は1〜k−1着を除いた馬）。
   学習の損失は総和$\sum_r L_r$、報告とearly stoppingはレース平均とする。custom objectiveは、
   勾配$g_j=\sum_k\mathbf{1}[j\in S_k]p^{(k)}_j-\mathbf{1}[j=\pi_k]$と厳密なHessian対角項
   $h_j=\sum_k\mathbf{1}[j\in S_k]p^{(k)}_j(1-p^{(k)}_j)$を返す。対角項に下限は付けず、
   LightGBMの正則化に任せる。レースは最大頭数へpaddingした配列でベクトル化し、`logsumexp`で
   安定に計算する。頭数3未満のレースは拒否する。
2. **確率。** 同じスコアから、勝率・2着以内・3着以内の周辺確率と、実際の組合せ（単勝・馬単・
   馬連・3連単・3連複）の対数確率を計算する。周辺確率はレースごとに最大値を引いた強さで計算し、
   組合せは対数領域で計算する。温度$T$は$s/T$として全計算に一様に掛ける。
3. **学習。** `lightgbm.train`にPLのcallable objective、`metric: "None"`、validのレース平均NLLを
   返す`feval`、`valid_sets=[valid]`、early stoppingのcallbackを渡す。objective・metric・反復数・
   early stopping・verbosityを設定から上書きすることは拒否し、boostingは`gbdt`だけを許す
   （`dart`はearly stoppingを無効にする）。モデルは永続化しない。
4. **年単位の拡大型fold。** test年$Y$ごとに、train=`train_start_year`〜$Y-2$、valid=$Y-1$、
   test=$Y$とする。年は`scheduled_start_at`のJSTの年である。
5. **ラベル利用境界。** `label_usable_after`がvalidの最初のfreeze以後のtrainのレースと、testの
   最初のfreeze以後のvalidのレースを除き、件数を記録する。除いた後に、trainの最大
   `label_usable_after` < validの最初のfreeze、trainとvalidの最大 < testの最初のfreezeを検査して
   記録する。この除外はfreeze前に決まる日付だけで決まり、結果を見て母集団を選ばない。
   testの着順は採点だけに使い、学習・early stopping・温度推定・確率の生成には使わない。
   評価母集団は、参考datamartに入った中央競馬10場（場コード01〜10）の全競走であり、基本評価では
   格付けの有無、平地・障害を区別しない。別途、下記の`jra_flat_graded_stakes_v1`部分集合を同じfoldで
   報告する。
6. **校正。** validのtop-3 PLのレース平均NLLを最小にする単一の温度を、$\log(1/T)$上の黄金分割で
   求める（既定の範囲は$T\in[0.05,20]$）。単勝のLog Lossだけで温度を合わせる方法や、着順段階別の
   温度は採らない。testには校正前（raw）と校正後（calibrated）の両方を報告する。
7. **市場との比較。** 全馬の単勝オッズが有限かつ正のレースだけを「市場完全」とし、
   $q_i$（温度なし）と比較する。連勝式の市場基準は、$\log q_i$を同じPLの式に入れたHarville展開で
   あり、連勝式の実際のオッズではない。指標はレースを等しい重みとする勝者のLog Loss、多クラス
   Brier、馬単・馬連・3連単・3連複のLog Loss、着順段階別のNLLである。モデルと市場のレースごとの
   差を、seed固定のレース単位の復元抽出によるパーセンタイル区間で評価し、上限<0なら
   `model_better`、下限>0なら`market_better`、それ以外は`inconclusive`とする。foldごとと、全foldの
   testレースをまとめたpooledで報告する。
8. **校正表。** 予測確率の帯（勝率・2着以内・3着以内）と単勝オッズの帯ごとに、件数・予測の平均・
   実測の割合を出す。校正表だけは馬を等しい重みとする。
9. **特徴量のvariant。** 設定のvariantごとに除外する列を指定する。実データでは、市場の単勝オッズ列を
   含む全36列（市場の情報と他の特徴量を合わせて市場を上回るか）と、それを除く35列（市場を使わない
   基礎モデル）の2通りを評価する。どちらも$q_i$との比較には同じ列を使う。
10. **出力。** 新しいCLI `model evaluate-pl`が、`configs/pl_evaluation/`の設定、
    `processed_root`、datamart manifestのSHA-256で固定したdatamartを読み、`report.json`（format
    `pl_probability_evaluation`、format_version 1）と`predictions.parquet`（testの馬ごとのスコア・
    温度・校正後の確率・単勝オッズ・$q_i$・部分集合所属）を新しいディレクトリへ公開する。
11. **延期。** ADR-009 Validation 4の同じfoldでのLambdaRank MVPとのランキング性能比較（#48）と、
    Validation 5の購入候補帯の校正（#36）は、このADRでは行わない。2・3着の偏りは測るだけで、
    補正は#49で決める。
12. **評価範囲。** 基本評価は、上記の広い母集団に対する研究評価である。これに加えて、ADR-009
    Validation 2が評価対象とするJRA平地重賞を、下記の固定snapshot由来の部分集合として比較する。

13. **平地重賞部分集合。** `jra_flat_graded_stakes_v1`は、固定snapshotの`NL_RA_RACE`で
    `GradeCD`が`A`・`B`・`C`、かつ`TrackCD`が`10`〜`24`のrace_id集合である。D・L・E・空の格付け、
    TrackCD 51〜59の障害その他のコードは含めない。部分集合の判定は格付け・コースだけから行い、
    testの着順を使わない。学習母集団は従来どおりdatamartの全レースとし、foldごと・pooledの
    件数、指標、市場比較、校正を部分集合として報告する。評価するのはdatamartに入ったtestレースだけであり、
    datamartの保留（同着・異常区分・取消など）で除かれた平地重賞は含まない。その件数をtest年ごとに
    `report.json`へ記録する。したがって、Validation 2の平地重賞の全体ではなく、保留されなかった平地重賞の評価である。

### Amendment 1: 平地重賞の評価とsnapshot出典（2026-11-10）

- 2026-11-10に人間の承認を受けてこのADRへ追加した（ADRのStatusはAcceptedのまま。Decision Historyを参照）。
- `model evaluate-pl`は設定の`processed_root`とdatamart manifestの`snapshot_id`・`target_period`・`venues`を使って
  固定snapshotの`NL_RA_RACE`を読み、datamart manifestに記録された同表のSHA-256と、読込後に再計算した
  SHA-256を照合する。不一致と、datamartのtest年のレースがsnapshotに無いことは、datamartの全体の読込・学習の前に
  拒否する（後者は、datamartの読込口`read_reference_datamart_race_ids`がtest年の`races.parquet`をmanifestの
  SHA-256で照合してから`race_id`列だけを先に読んで調べる）。fold年と全列を除くvariantも読込の前に検査する。
- `report.json`のトップに部分集合の定義と、表名・SHA-256・`snapshot_id`の出典、test年ごとのdatamartに無い
  部分集合のレース数（`not_in_datamart_by_test_year`）を記録する。
  `predictions.parquet`には`in_jra_flat_graded_stakes`（bool、非null）を追加する。追加フィールドは
  format_version 1の範囲内である。
- CLIの失敗メッセージは改行を空白へ畳んだ1行とし、`???`が残る設定も終了コード1で拒否する。

---

## Rationale

- 損失・勾配・Hessian対角項は、ADR-009の式をそのまま微分したもので、スカラーの参照実装と
  有限差分で照合できる。padded配列のベクトル化で、20年分の学習でも反復ごとの計算が軽い。
- 年単位の拡大型foldは、Issue #33が求める「train〜Y−2・valid Y−1・test Y」の形であり、
  validをearly stoppingと校正の両方に使える。日付だけで決まる除外なら、評価母集団を結果で選ばない。
- 単一の温度は、一つの確率モデルから全券種の確率を出すというADR-009の構成を保つ。単勝だけで
  合わせると、2・3着の確率がさらに偏る可能性がある。段階別の温度は補正の一種であり、偏りを
  測ってから決める（#49）。
- 市場完全レースに限ることで、モデルと市場を同じレース集合で比べられる。
- 平地重賞の選択をdatamartの特徴量やtestの着順から分離し、固定snapshotの出典とhashを出力へ残すことで、
  ADR-009 Validation 2の対象を再現可能にする。

---

## Consequences

### Positive

- 単勝・馬単・馬連・3連単・3連複の確率を一つのモデルから出し、同時点の市場と同じレースで比べられる。
- foldごとのラベル境界と除外件数が記録され、漏洩がないことを後から確かめられる。

### Negative

- モデルを保存しないため、評価以外の予測には使えない。予測への接続は別途決める。
- 単一の温度では、着順段階ごとの偏りを補正できない。
- 連勝式の市場基準は単勝からのHarville展開であり、実際の連勝式オッズとの比較ではない。

### Neutral / Follow-on effects

- `numpy`を直接依存に加える（版は`uv.lock`の2.5.3のまま）。
- 既存の`model train`・`model predict`・`walk_forward.py`・`RankingModel`・保存形式は変えない。

---

## Alternatives Considered

### Option A: 既存の`RankingDataset`と`walk_forward.py`を拡張する

Summary:

PL学習を既存のdatasetとレース数のwalk-forwardへ追加する。

Advantages:

- 既存の検証・時点監査を再利用できる。

Disadvantages:

- 1行ずつのPython検証とlistの行列で、全期間では時間とメモリが成り立たない。walk-forwardは計算契約付きの入力を拒否し、validを使わない。

Reason not selected:

全期間の年単位foldというIssue #33・#34の規模と形に合わないため。

### Option B: 単勝のLog Lossで温度を合わせる

Summary:

valid上の勝者のLog Lossを最小にする温度を使う。

Advantages:

- 単勝の確率の校正だけを見れば最も良くなりやすい。

Disadvantages:

- 2・3着の確率が単勝に合わせて歪み、券種ごとの比較が一つのモデルの評価でなくなる。

Reason not selected:

一つの確率モデルから全券種を出すADR-009の構成を保つため。

### Option C: LambdaRankのスコアにsoftmaxを後付けする

Summary:

既存のLambdaRankモデルのスコアを確率へ変換する。

Advantages:

- 新しいobjectiveが要らない。

Disadvantages:

- PLの尤度で学習したモデルにならない（ADR-009が明示的に退けた）。

Reason not selected:

ADR-009の決定に反するため。

### Option D: datamartに格付け・コースの列を加える（Amendment 1）

Summary:

`races.parquet`に`GradeCD`・`TrackCD`を加え、平地重賞の判定をdatamartから行う。

Advantages:

- 評価時にsnapshotを読まずに済み、datamartだけで部分集合を作れる。

Disadvantages:

- ADR-034の保存形式（format_version）を変え、全期間の再構築（約2.6時間）が要る。

Reason not selected:

人間が、datamartの形式を変えずに評価時に同じsnapshotから読む方法を選んだため（2026-11-10）。

---

## Implementation Notes

- `models/probability/plackett_luce.py`: padded配置、NLL・勾配・Hessian対角項、周辺確率、組合せの対数確率。
- `models/probability/calibration.py`: 温度の推定。
- `models/evaluation/probability_metrics.py`: レース指標、$q_i$、校正表、bootstrap。
- `models/dataset/race_arrays.py`・`models/serialization/race_arrays.py`: numpyの`RaceArrays`と、datamartの`pa.Table`からの変換。
- `models/evaluation/yearly_folds.py`: 年単位foldとラベル利用境界の除外・監査。
- `models/backends/lightgbm.py`: `fit_native_pl_booster`。
- `models/experiments/pl_evaluation.py`: variant×foldの組立とreport・予測表。
- `models/serialization/race_subsets.py`: 固定snapshotの`NL_RA_RACE`から評価部分集合を作る純粋な分類。
- `configuration/pl_evaluation.py`・`configs/pl_evaluation/`・`cli/pl_evaluation.py`: 設定とCLI。

---

## Validation

- スカラーの参照実装との一致（頭数3〜18）、勾配とHessian対角項の中心差分による照合、極端なスコアと
  温度の上下限での有限性、全列挙との一致（頭数3〜6）をunit testで確かめる。
- 合成データで、学習がsignalを学ぶこと、validのbest scoreが独立に計算したNLLと一致すること、
  testの着順を変えてもスコア・確率・best iteration・温度が変わらないことを確かめる。
- 合成snapshotとdatamartで、`NL_RA_RACE`のhash照合、testレース欠落の拒否、部分集合の出典と
  予測列を確かめる。
- 2006〜2025年の全期間datamartで、test 2016〜2025の10 fold×2 variantを評価し、結果を
  [着順確率モデルの評価](../experiments/pl-probability-model.md)に記録する。基本評価は中央競馬10場の
  全競走、追加の部分集合評価はADR-009 Validation 2のJRA平地重賞を対象とする。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Harville型の仮定による2・3着の偏り | 連勝式の確率が偏る | 段階別NLLと校正表で測り、補正は#49で決める |
| 市場列を含むvariantが市場を写すだけになる | 市場超過の解釈を誤る | 市場列を除くvariantと並べて報告する |
| 保留レース（同着・取消など）が評価母集団の外 | 結果が通常レースに限られる | 件数をdatamartの`held_races.json`で確認できる |
| $q_i$がfreeze時点のオッズで確定オッズではない | 購入判断の評価とずれる | オッズ変動の補正は#35で扱う |
| 平地重賞の判定に使う`GradeCD`・`TrackCD`はsnapshotの最終版の値で、freeze時点の値であることは確かめていない | 部分集合の選択がずれる可能性がある | 選択にだけ使い特徴量には使わない。重賞の格付け・コースは出走前に決まり後から変わらない前提を記録する |

---

## Security / Privacy Impact

認証・秘密情報・外部通信の境界は変えない。ローカルのdatamartを読み、ローカルの新しいディレクトリへ書く。

---

## Operational Impact

全期間の評価は単一プロセスで、学習は10 fold×2 variantの20回である。処理時間とピークメモリは
[着順確率モデルの評価](../experiments/pl-probability-model.md)に記録する。

---

## Migration / Rollback

### Migration

新しいCLIと出力形式の追加だけで、既存のデータ・モデル・設定の移行はない。

### Rollback

`model evaluate-pl`と関連モジュール・設定を削除すれば元に戻る。既存の経路は影響を受けない。

---

## Documentation Changes

- `ARCHITECTURE.md`のモデルとCLIの節。
- `docs/experiments/pl-probability-model.md`（使い方・出力形式・実データの結果）。

---

## Follow-up Actions

- 同じfoldでのLambdaRank MVPとのランキング性能比較（#48）。
- 2・3着の偏りの補正（#49）。
- 期待値による購入判断と購入候補帯の校正（#36）、オッズ変動の補正（#35）。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-09 | Accepted | top-3 PLの微分・年単位fold・ラベル境界・温度校正・市場との比較の手順を決定 |
| 2026-11-10 | Accepted | Amendment 1: 固定snapshotの`NL_RA_RACE`による平地重賞（GradeCD A・B・C × TrackCD 10〜24）の部分集合評価を追加 |
| 2026-11-12 | Accepted | ADR-038が、同じ学習の手順で最終モデルを学習し、成果物として保存することを決めた。評価（`model evaluate-pl`）は引き続きモデルを永続化しない |
