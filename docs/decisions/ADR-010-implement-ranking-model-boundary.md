# ADR-010: ランキングMVPの実装境界と成果物契約

- Status: Accepted
- Date: 2026-10-06
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ADR-009でLambdaRankをランキングMVPへ採用した。実装では、raw SQLiteや取得処理をモデルへ持ち込まず、処理済み特徴量の明示的な列契約、欠損値、レース単位のgroup、モデル成果物の再読取を固定する必要がある。オッズ履歴など一部の入力は全期間で取得できないため、最終オッズ等による補完は行わず、後日データが揃った場合に同じ契約で再実行できる境界が必要である。

## Decision

1. `src/models/` は呼び出し元から渡された `RankingDataset`、`FeatureRow`、`FeatureSchema` だけを受け取り、SQLite、raw staging、JV-Link、外部通信を直接参照しない。
2. 学習は `LGBMRanker(objective="lambdarank")` を使い、ラベル3/2/1/0、label gain 0/1/3/7、連続したレース行数によるgroupを固定する。出力は有限なscoreとレース内rankに限定し、確率・EV・購入案は生成しない。
3. `FeatureSchema` はordered feature名、schema ID、数値型、単位、生成規則、欠損方針を保持する。上流の意味が未確定な場合は未確定値を明示して保存し、単位や生成規則を推測しない。結果由来の列名はallow-list境界で拒否する。
4. 欠損値は補完せず、`None`またはnative `NaN`としてLightGBMへ渡す。特に取得できないオッズ履歴を最終オッズや別期間の値で代用しない。
5. 同点scoreは一意な `horse_id` の昇順で解決する。入力行順を同点規則へ使わず、評価と推論で同じ規則を適用する。
6. 成果物はLightGBM native model、JSON metadata、ready markerで構成する。metadataにはobjective、label gain、FeatureSchema、ハッシュを含め、完成前はready markerを公開しない。既存成果物を置換せず、公開途中のmarkerは再実行時に安全に回収できるものとする。
7. `FeatureSchema` は現在の承認済み特徴量allow-listと生成規則へ完全一致する場合だけ受け付ける。現在のMVPでは事前能力値と履歴オッズを登録し、曖昧な`odds`、結果列、勝者フラグは拒否する。新しい特徴量は、時点と生成規則を確定したうえでallow-listへ明示的に追加する。

## Consequences

### Positive

- 学習と推論の列順・意味・欠損方針を成果物から検証できる。
- 過去期間の欠損を事後データで埋めず、データ取得後の再実行を同じモデル境界で行える。
- モデル処理と既存のParquet公開・取得境界が分離される。

### Negative and follow-up

- 特徴量生成、時点利用可能性監査、nested walk-forward、CLIは別の実装単位であり、このADRでは実装しない。
- 単位や生成規則が未決定の特徴量はランキング評価へ投入する前に上流でFeatureSchemaを確定する必要がある。
- 同着、取消・失格、3頭未満などの例外規則は既存の未決定事項として残る。

## Validation

モデルのgroup、ラベル、欠損保持、結果由来列拒否、FeatureSchema照合、native save/load、成果物公開途中の再実行をpytestで検証する。依存関係は`pyproject.toml`と`uv.lock`へ同時に記録する。
