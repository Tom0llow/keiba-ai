# 参考特徴量datamartの構築と計測

[ADR-034](../decisions/ADR-034-build-full-period-reference-feature-datamart.md)の
`datamart build-reference`の使い方、出力形式、実データでの計測結果を記録する。
特徴量の計算式・参考規則・仮定は[全21群の参考接続手順](reference-real-input.md)と同じである。
計測値は1台のローカル環境での実測であり、性能の保証ではない。

## 目的と範囲

Issue #33の年単位の検証に向けて、全期間の特徴量を時系列順に一度だけ計算し、年ごとのParquetへ保存する。
対象は`target_start`〜`target_end`の`NL_RA_RACE`の中央全レース（場01〜10）で、履歴は
`history_start`以降の採用可能な通常結果全頭である。年単位fold、early stopping、datamartからの学習は
次のタスクで扱う。

## 構築

```powershell
uv run python src/main.py datamart build-reference --config-name measure --override processed_root=data/processed --override snapshot_id=098ce3f4b5d7480282269218d80cef05 --output output/reference-datamart-2025
```

- `configs/reference_datamart/build.yaml`は`snapshot_id`（nullなら最初の一度だけCURRENTを解決する）以外を
  必須値`???`とする。`measure.yaml`は計測用の明示値で、
  計算設定と参考規則は`configs/reference_input/trial.yaml`と同じ、`history_start`だけ`2005-01-01`、
  対象は2025-01-01〜2025-12-31である。期間は`--override target_start=...`などで変えられる。
- `--output`は存在しない新しいパスで、親が存在し、processed rootの外にあることを要求する。
- 進捗はstderrに`phase=year year=<YYYY> targets=<n> races=<n> rows=<n> held=<n> seconds=<s>`の形で出る。
  `seconds`はその年の処理時間である。公開に成功した後だけ、stdoutへ要約1行が出る。
- 失敗した場合（Ctrl+Cを含む）は出力もstagingも残らない。

## 出力

```text
<output>/
├─ manifest.json            # 計算契約、列一覧、snapshotの表のSHA-256、各ファイルのSHA-256と件数
├─ held_races.json          # 保留したレース（役割・段階・理由）
└─ year=<YYYY>/
   ├─ part-0.parquet        # 馬ごとの行: 閉じた数値列の全列（36列）、群ごとのavailable_at、着順
   └─ races.parquet         # レースごとの行: 頭数、ラベル利用境界、ラベルのダイジェスト、履歴の利用境界
```

- 数値列はfloat64で、欠損はnullのまま保持する。補完・除外・丸めは行わない。
- 群ごとの`<group>__available_at`は依存の利用可能時刻の最大値で、参考規則では常に`freeze_at`と等しい。
- 読込APIは`make_datamart.tables.reference.read_reference_datamart`で、hash・schema・計算契約・
  列一覧・行の時点・ラベル境界・着順の連続性を検証する。21群は再計算しない。

## 保留

レース全体を理由付きで保留し、馬単位では除外しない。`held_races.json`の`stage`は次のとおりである。

| stage | 意味 |
| --- | --- |
| `history_result` | 履歴として採用できない結果（通常結果でない、作成日が利用境界以後など） |
| `target_pre_freeze` | freeze以前の情報で対象にできない（O1・出馬表の不整合、市場anchorの衝突など） |
| `target_outcome` | 対象の結果がラベルとして採用できない |
| `calculation` | 計算器が`ValueError`を出した（市場anchorの鮮度超過など） |

`target_outcome`はfreeze後の情報で評価母集団を選ぶことになるため、次のタスクで件数を報告する。

## 計測

2026-11-09に、snapshot `098ce3f4b5d7480282269218d80cef05`と`measure`設定で4回構築した。
環境はWindows 11、Intel Core i5-14400F（16論理コア）、物理メモリ32GB、NVMe SSD、Python 3.12.12、
pyarrow 25.0.1である。直前に同じsnapshotを読んでいたため、ファイルキャッシュは温かい状態である。
時間・CPU時間・ピークメモリは、インタープリタ自身を`ctypes`の`K32GetProcessMemoryInfo`と
`GetProcessTimes`で測った（`uv run`の親プロセスは含まない）。構築は単一プロセスで行う。

| 実行 | 対象 | 履歴の開始 | 全体の時間 | 対象年の処理 | CPU時間 | ピーク作業セット | ピークcommit | 対象→出力レース | 行 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2025-12-01〜12-31 | 2005-01-01 | 130秒 | 64秒 | 147秒 | 5.0GB | 5.9GB | 264→237 | 3,403 |
| 2 | 2025-12-01〜12-31 | 2015-01-01 | 92秒 | 52秒 | 99秒 | 4.7GB | 5.7GB | 264→237 | 3,403 |
| 3 | 2025-12-01〜12-31 | 2024-01-01 | 57秒 | 42秒 | 60秒 | 4.3GB | 5.2GB | 264→237 | 3,403 |
| 4 | 2025-01-01〜12-31 | 2005-01-01 | 601秒 | 532秒 | 641秒 | 6.5GB | 7.3GB | 3,468→3,017 | 41,663 |

- 履歴だけの年の取込み（RA/SEの読込と正規化）は1年あたり約2.7秒で、2005〜2024年の20年分で約55秒だった。
- 表のhashは最初に約6秒、構築の最後のmanifestでの再照合に約5〜10秒かかる。
- 対象年の処理には、その年の履歴の取込み、調教の読込、O1/O2のfooterの解析（年に1回）と開催日ごとの
  読込を含む。実行4の対象1レースあたりは約0.15秒（532秒÷3,468）だった。
- 実行1〜3では、履歴が長いほど対象1レースあたりの費用が増える（読込などの固定費約15秒を除いて、
  履歴1年で約0.10秒、10年で約0.14秒、20年で約0.18秒）。計算器は窓の外の履歴を走査しないが、
  対象ごとに履歴馬全体の母集団を複製し、それを含むcoverageの宣言を4回hashしている（10万頭で
  対象あたり約30ミリ秒という見積もりがある）。増え方の主な原因はこれと基準集合の統計と推定しているが、
  プロファイルでは確かめていない。
- 実行4の出力は、`part-0.parquet`が3.1MB、`races.parquet`が0.5MB、`held_races.json`が2.1MB、
  `manifest.json`が0.05MBだった。
- 2026-11-08のベンチマーク（既存の参考経路、対象36レース、履歴1年）は264秒・1.38GBのJSONだった。
  実行4は履歴21年分を使い、対象3,468レースを601秒・3.6MBのParquetで保存した。

### 保留の内訳（実行4）

| 役割 | 段階 | 理由 | 件数 |
| --- | --- | --- | --- |
| history | `history_result` | `non_normal_or_tied_result`（異常区分または同着を含む） | 9,697 |
| history | `history_result` | `result_created_after_declared_use_date` | 784 |
| history | `history_result` | `not_final_normal_result` | 355 |
| target | `target_outcome` | `non_normal_or_tied_result` | 373 |
| target | `target_pre_freeze` | `intermediate O1 indicates a cancelled entrant` | 66 |
| target | `target_pre_freeze` | `no intermediate O1 publication at or before freeze`（2025-02-08の開催日） | 12 |
| target | `calculation` | なし | 0 |

2005〜2025年の中央の履歴レース72,880件の約15%が、参考規則（ADR-030）によりレース全体で保留される。
最も多い理由は、異常区分（`IJyoCD`が`0`以外）または同着を含むことである。

### 2006〜2025年の外挿

対象1レースあたりの費用を、履歴の年数`h`の一次式`c(h) ≈ 0.073 + 0.003h`秒と置く。傾きは実行1〜3の
増え方から求め、全体を実行4（`h`=20で、読込を除いて約0.13秒）に合わせて縮めた。年3,450レース、
対象年ごとの読込などの固定費を約75秒（年の取込み約3秒、footer約7秒、開催日約108日分の市場の読込
約65秒）とすると、

- 計算: Σ<sub>h=1..20</sub> 3,450 × c(h) ≈ 3,450 × (20 × 0.073 + 0.003 × 210) ≈ 7,200秒
- 対象年ごとの固定費: 20年 × 約75秒 ≈ 1,500秒
- 2005年の取込み、最初のhashと最後の再照合: 約20秒

となり、全体で約2.4時間と見積もる。ピークメモリは、履歴（2005〜2025年）と基準集合の統計を最後まで
保持するため、実行4の7.3GB（commit）より大きくなる見込みで、8〜10GBと見積もる（未計測）。
調教の証拠は全期間の登録表に保持しないため、対象年が増えても調教の分は増えない。
Parquetは1年あたり約3.6MBで、20年分で約70MBである。

この外挿は、2025年と各年の対象レース数・頭数・調教の量がおおむね同じという前提に立つ。
`NL_WC_WOOD`は2021年以降にしかないため、それ以前の年の調教の処理は軽くなる。
途中再開がないため、全期間を1回で構築する場合は、失敗すると最初からやり直しになる。

2026-11-10に2006〜2025年（履歴2005年から）を、ほぼ単独で（他の処理と重なったのは開始直後の数分だけ）
構築したところ、全体で9,393秒（2時間37分）、CPU時間9,898秒、ピーク作業セット6.95GB、ピークcommit 8.05GBで、
59,115レース・835,398行・保留21,150件、ディスク上71MBだった。対象年の処理は1年あたり289秒（2006年）から658秒（2025年）へ
おおむね増えた。外挿の約2.4時間・8〜10GBとほぼ同じである。同じ設定での2回の構築で、年ごとのParquetと
保留の内容は同じSHA-256だった。詳細は[着順確率モデルの評価](pl-probability-model.md)に記録した。
