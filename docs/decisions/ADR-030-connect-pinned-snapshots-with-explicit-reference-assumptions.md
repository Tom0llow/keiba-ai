# ADR-030: 固定Parquetから全21群を参考実験へ接続する

- Status: Accepted
- Date: 2026-11-01
- Decision Owners: Repository maintainers
- Supersedes: ADR-028の現存データを参考実験へ接続しない制限のみ

## Context

ユーザーは全21群を現存データへ接続し、保存発走予定時刻が当時も有効であり、
発表時に受信済みと仮定する参考学習を明示的に選択した。過去訂正版の時点は未検証である。
通常結果以外のレース全体を理由付きで保留し、結果は7日以上経過後に利用する。
実測の発表・受信・確定時計を捏造せず、旧厳格経路を維持する必要がある。

## Decision

実測`SourceEvidence`は維持し、`ReferenceEvidence`でnullable実発表時計、null受信時計、
宣言利用境界`usable_after`、時計と仮定の根拠を区別する。参考専用入口が同じ21群計算を共有する。
旧厳格入口は参考型を拒否する。固定snapshot、明示レースmanifest、原列投影、原行hash、
換算規則、母集団、保留理由をprepared入力へ保存し、読込時に純粋変換と計算を再実行する。
出典と依存集合をcatalogで共有し、同じ原観測を馬・群ごとに複製しない。

`snapshot_reference_21_groups_v1`のschema identityへ計算設定、明示列順、参考規則を含める。
恒久馬IDはKettoNum、市場slotだけUmabanを使う。対象結果はラベルとして分離し、
特徴量へは当日結果、最終オッズ、対象馬体重・時計・最終馬場を渡さない。
前日までの全馬調教、採用過去レースの全頭、対応する父・母父を使用する。
coverageは固定snapshot内の明示採用母集団についての完全性であり、全JRAの収録証明ではない。

MLflow、native training context、予測へ保証区分と結果利用境界を保持する。
この参考保証は厳格な過去時点再現、改善効果、運用成績の証明ではない。

## Validation

小さなParquet fixtureから全21群、実LightGBM、MLflow登録、厳密版予測を検証する。
旧厳格経路の拒否、未来・最終市場、対象結果変更の不変性、単位・特殊値・血統配列・
調教相手集合、保留と欠損保持、改変・上書き拒否を検証する。

公式根拠: [JV-Data仕様書4.9.0.1](https://jra-van.jp/dlb/sdv/sdk/JV-Data4901.pdf)、
[時系列オッズ](https://targetfaq.jra-van.jp/faq/detail?category=47&id=667&site=SVKNEGBV)。
