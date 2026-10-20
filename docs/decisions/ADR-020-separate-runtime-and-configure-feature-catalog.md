# ADR-020: 実行境界を分離し特徴量登録をTOMLへ統合する

- Status: Superseded（共有パス・レースキー、CLI、ルート設定ファイルの配置判断のみ。その他はAccepted）
- Date: 2026-10-13
- Decision Owners: Repository maintainers
- Supersedes: ADR-019（配置・登録・CLI境界の判断）
- Superseded by: ADR-021（共有パス・レースキーの配置判断のみ）、ADR-022（CLI配置判断のみ）、ADR-026（ルート設定ファイルの配置のみ）

## Context

ユーザーは取得・前処理・読込・CLIの責務分離、特徴量共通処理の分類、
`config/features.toml`への登録一覧統合を検討したうえで実装を明示承認した。
IDの重複定義と`features/common/`への責務集中を解消する必要がある。
ADR-019の個別生成・唯一の中間行・監査・保存・モデル採用の契約は継承する。

## Decision

1. `src/data/`を廃止し、取得は`retriever/`、前処理は`preprocesser/`、
   読込公開APIは`utils/data_loader.py`、読込処理は`utils/loader/`へ移す。
   共有パスとレースキーは`data_paths.py`、`race_key.py`に置く。
2. `main.py`は`run.app.app`の起動だけを担う。`run/`がコマンド登録、
   引数検証、実行編成、入力変換、JSON出力を所有する。下位処理から依存しない。
3. `features/common/`を廃止し、型は`contracts/`、監査は`validation/`、
   共通生成は`generation/`、スキーマ・構築・保存は`tables/`、登録は`catalog/`へ置く。
4. `config/features.toml`の`[[features]]`がID・グループ名・登録順の唯一の定義元となる。
   現行F01〜F21の対応と順序を維持し、各`SPEC`、Enum、採番式、ID別の重複一覧を設けない。
   TOMLは必須項目、型、空文字、ID・名前重複、実装の対応漏れ・未知名を拒否する。
   Pythonにはグループ名と入力型・生成器の明示的対応のみを置き、動的importを行わない。
5. 実行境界が設定を明示的に一回読み、不変の登録情報を監査・全体生成へ渡す。
   個別生成器と公開build APIには`definition`を明示する。下位監査には必要ID、
   テーブルとdatamart APIには`registered_names`を渡す。省略時は既存3の固定スキーマ
   だけを扱い、任意の未登録名を受け付けない。import時・help時には設定を読まない。
6. importパス、個別build API、全体生成API、テーブルAPIの呼出し元とテスト・文書を
   同時に移行する。既存CLI名・引数・終了コード・JSONキー・NaNのnull変換は維持し、
   特徴量コマンドに設定パスを明示できる`--features-config`を追加する。
   `features/__init__.py`の再公開を廃止し、利用者は各責務の所有モジュールから
   importする。これによりcatalog loaderのimportが個別生成器の読込を伴わない。
7. 既存3特徴量には新IDを与えず、列・型・metadataを維持する。登録はモデル採用を
   意味せず、モデルallow-listと数値投影は引き続き`models/`が所有する。
8. raw SQLite、ParquetのCURRENT原子的公開、race別versions、台帳・ロック、全raw完了後の
   単一公開、realtime二段取得を維持する。実データを加工・移動しない。
9. `GUARDED_WORKFLOW_REPAIR.md`の削除は保護文書・スキルの参照更新を伴うため、
   今回は維持し、別途明示承認が必要なmanual作業へ分離する。信頼境界を変更しない。

## Rationale

責務別の配置と単一の宣言的登録により、特徴量追加時の変更箇所と依存方向が明確になる。
明示的引数は設定読込の隠れた副作用を避け、一回の実行で同じ定義を使用できる。
登録名の検証をテーブル境界でも保持し、設定移行による永続形式の契約緩和を防ぐ。

## Consequences

Python利用者はimportと引数の移行が必要となるが、保存済み成果物とCLI入力は移行不要。
TOMLのID変更は外部JSONとの互換性に影響するため、通常の実行オプションとは区別して
Git上でレビューする。未確定の業務式・履歴窓・列型・発走前の取得証明は確定させない。

## Alternatives Considered

- EnumによるID一覧はTOMLとの重複となるため採用しない。
- TOMLから任意のモジュールやクラスを読み込む方式は、現在不要な拡張・安全境界となる。
- import時の設定読込やsingletonはhelp・ライブラリ利用にI/Oを持ち込むため採用しない。
- テーブル名をsnake_caseだけで許可する方式は既存の登録検証を弱めるため採用しない。

## Validation

設定エラー・登録順・実装対応、独自IDの個別生成と全体監査への伝播、import/help時の
無読込、CLI JSON、未知名拒否、Parquet round-tripを検証する。取得・台帳・公開・モデルの
回帰を維持し、Ruff、mypy、全pytest、guard回帰で確認する。
