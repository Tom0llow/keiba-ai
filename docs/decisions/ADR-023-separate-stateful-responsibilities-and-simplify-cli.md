# ADR-023: 状態を持つ処理の責務を分離しCLIの重複を整理する

- Status: Accepted
- Date: 2026-10-17
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ユーザーはsrc全体の責務とオブジェクト指向の観点から提示した分割案、および
main.pyの簡略化案に基づく実装を承認した。取得ではraw観測・台帳・純粋な状態計算・
派生出力が同居し、モデルでは推論と複数ファイルの保存・公開復旧が同居していた。
特徴量の全体生成と単独生成は共通監査を反復し、全体編成が市場固有の監査を知っていた。
CLIには引数判定、レース組立、成功JSON組立、エラー保存の重複が残っていた。

ADR-020〜022の登録・配置・CLI所有と、取得ロック・台帳・公開順序、保存形式を保ったまま
変更理由と依存方向を明確にする。未確定の業務式や新しい実行基盤は導入しない。

## Decision

1. `models/ranker.py`の`RankingModel`はbooster・schemaを保持し推論を担当する。
   保存・読込は`models/artifacts.py`の`NativeModelArtifact(path)`へ委譲する。
   このクラスがnative model、metadata、ready、publishingを一組として公開・検証・復旧する。
   artifact側は`RankingModel`をimportせず、読込済みboosterとschema等を返す。
2. `models/lightgbm_backend.py`に公開Protocol、LightGBMの遅延読込、fitとnative読込を置く。
   学習が推論moduleのprivate実装をimportする結合を除く。`ranking_rules.py`に固定objective、
   label gain、group範囲、同点順位規則を集約する。評価・推論の重複検証と並べ替えを整理し、
   単独公開APIの検証は残す。
3. `retriever/progress.py`は台帳schema・移行・所有・API証拠とtransactionを所有する。
   `progress_state.py`へ値型と純粋な突合・hash、`raw_snapshot.py`へraw観測、
   `progress_output.py`へ確定台帳からのJSON/TOML生成を分ける。
   共有のraw表対応・キー列は`odds_contract.py`で管理する。
4. Historicalと年次バッチの対象期間・schema検証・再開条件を統合しない。
   DB接続は観測が終わるまでに閉じ、外部取得と重ねない。台帳が状態の正本であり、派生出力を
   再開判断に用いない。stateはreader/ledger/outputをimportせず、outputからledgerへの
   型参照はTYPE_CHECKING内に限る。従来の補助関数・結果型のimportは再公開で維持する。
5. `WeeklyHistoricalOddsRetriever`はロックとバッチ手順を維持し、要求実行、結果分類、集計を
   分ける。`JVLinkToSQLiteRunner`は通常/逐次実行の結果・例外変換を共有する。
   `SnapshotPublisher`は既存クラス内で公開手順を共有し、表と抽出条件は明示する。
6. 既存`FeatureBuilder`を維持し、Definition必須の`RegisteredFeatureBuilder`を追加する。
   F01〜F21は専用Input型と個別normalizeの所有を維持する。公開単独入口は型確認・共通監査・
   固有監査を行い、全体生成は共通監査と登録済みBuilderの固有監査後に内部の監査済み経路を使う。
   市場固有監査は市場Builderが所有する。単独市場生成の早期終了と全体監査の違反追記順を保つ。
   旧3特徴量、共通中間行、明示型、登録名とモデル数値採用の境界は変えない。
7. mainは全CLI定義・引数検証・依存生成・実行編成・表示・エラー保存・終了を維持する。
   `_RaceOptions`と共通の判定・入力変換・エラー保存関数で重複を整理する。
   完全な成功JSONの組立は各機能の`serialization/outputs.py`へ純粋変換として置く。
   serializerはI/O、監査実行、Typer/main依存を持たない。

## Rationale

モデル成果物は資源と公開状態の整合条件を持つため、推論とは別のオブジェクトとして管理する。
一方、状態計算・値変換・数値規則は関数のまま分ける。既存クラスの合成と必要な生成器の
特殊化を利用し、無状態のutilityクラス、汎用service/repository層、動的pluginを増やさない。
mainの宣言と実行順序を確認できる構成を保ち、CLIのためだけの新しい実行層を作らない。

## Consequences

公開CLI、Pythonの既存公開API、nativeモデル、台帳、Parquet、JSON/TOMLの保存形式は維持する。
既存データの移行や依存追加は不要。モジュール数は増えるが、それぞれの変更理由を限定できる。
監査済みの内部経路を使う全体生成は、必ず全体監査を先に実行する必要がある。

特徴量のUTC正規化とモデルのoffset保持、scalar許容範囲の違いを維持するため、両方の検証を
utilsへ統合しない。特徴量の業務式、差分前処理、model schema/availabilityの追加分割は含めない。

## Alternatives Considered

- 全ハンドラーをCliApplicationへ包むだけでは、mainの処理量や責務の重複を改善しない。
- 年次取得loopをmain外へ移す案は、今回維持するCLI編成の所有境界を変えるため採用しない。
- 全取得器の基底クラス化は永続XML・二段取得・台帳復旧の違いを隠すため採用しない。
- 公開の監査省略フラグや、全体生成が個別normalizeを迂回する案は採用しない。
- 無状態のDatamartBuilder/Validatorクラスを追加する案は、既存の分割で足りるため採用しない。

## Validation

既存と追加の回帰で、native往復・改変拒否・非置換公開・中断復旧、取得結果/API証拠、
レポート失敗後の台帳再開、snapshot失敗時の旧版保持を検証する。
全21生成器の単独/全体結果、型取り違え、UTC/NULL、違反順序、独自ID/登録順を検証する。
CLIのhelp・異常引数出力・終了コード、入力エラーcontext、純粋serializerを確認し、
Ruff format/check、mypy、全pytest、ガード回帰と独立レビューを行う。
