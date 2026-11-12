# top-3 PLの最終モデルの学習

## 目的と範囲

[ADR-038](../decisions/ADR-038-train-and-persist-the-final-top3-pl-model.md)の`model train-pl`で、当日の予測（#53）に使う
top-3 PLの最終モデルを学習し、成果物`pl_top3_model`として保存した。この記録は、評価（ADR-035）との一致と、
運用のモデルの学習の結果を示す。

## 実行

```powershell
uv run python src/main.py model train-pl --config-name final --override datamart_path=<学習用datamart> --override datamart_manifest_sha256=<manifestのSHA-256> --output <新しい出力先>
```

- `final.yaml`は、train 2006〜2024年・valid 2025年・variant`all_columns`（36列）で、LightGBMの引数・反復数・温度の範囲は
  評価の`configs/pl_evaluation/measure.yaml`と同じである。
- 再現の確認では、同じ設定に`--override valid_year=2024`を加えた。

## 条件

- 学習用datamart: `output/reference-datamart-2006-2025`（対象2006〜2025年、manifest SHA-256 `dc375147…`）。
- 評価の結果: `output/pl-evaluation-2016-2025-graded-final3`（ADR-035、test 2016〜2025年）。
- 機械: 開発用のWindows 11の1台。LightGBM 4.7.0、`num_threads` 8、`deterministic`。
- 所要時間とピークの作業セットは、CLIを同じプロセスで呼ぶ計測用のスクリプト（コミットしない）で測った。
- 日付: 2026-11-12。

## 評価との一致（valid 2024年）

`valid_year=2024`の最終学習は、train 2006〜2023年・valid 2024年で、評価のtest 2025年のfoldと同じ分割になる
（そのfoldのvalidは除外0件だった）。

| 項目 | 評価のfold（test 2025年、`all_columns`） | 最終学習（valid 2024年） |
| --- | --- | --- |
| `best_iteration` | 351 | 351 |
| `best_valid_nll` | 6.010769144083349 | 6.010769144083349 |
| 温度 | 0.9951775559470158 | 0.9951775559470158 |
| trainのレース数・除外 | 53,103・0 | 53,103・0 |
| validのレース数 | 2,995 | 2,995 |

すべて完全に一致した。最終学習は、評価と同じ手順である。

## 運用のモデル（valid 2025年）

| 項目 | 値 |
| --- | --- |
| trainのレース数・馬数 | 56,098・793,735（除外0件） |
| validのレース数・馬数 | 3,017・41,663 |
| `best_iteration` | 231 |
| validのNLL（raw / 校正後） | 6.074701593890548 / 6.074584195959277 |
| 温度 | 0.9894104119159786（範囲の端ではない） |
| ラベルの利用境界（`label_usable_through`） | 2026-01-04T15:00:00+00:00（学習用datamart全体の境界と同じ） |
| 学習で欠損のなかった列 | 4（市場の単勝オッズ・距離・斤量・過去の出走数） |
| 成果物のmanifest SHA-256 | `89656d49140504993c57695f320a83068e73e020cefb37f37ee9a55e6a2a2aee` |
| 所要時間 | 111.7秒（読込51.1秒を含む） |
| ピークの作業セット | 2.11GB |

公開の前に、書いた成果物を読み直し、validのスコアが学習直後と一致することをCLIが確かめた。
学習で欠損のあった32列は、すべての分岐が欠損の枝を持ち、書込みと読込の照合を通った。
この成果物は、レビューの修正を終えた最終のソースで学習した。
修正前のコードで学習した成果物と、`model.txt`はバイト単位で同じだった。
valid 2024年の実行は、129.1秒・2.08GBだった。

## 制約

- 運用のモデルは2025年までのデータで学習しており、2026年のレースを学習していない（#55）。
- 予測するレースのfreezeは、2026-01-04T15:00:00+00:00より後でなければならない。2026年11月の予測では満たす。
- 市場の単勝オッズ列が欠けたレースは、モデルが予測を拒否する（#53で保留として示す）。
