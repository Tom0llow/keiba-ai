# ADR-018: 特徴量CLIとJSON読込の配置を分離する

- Status: Superseded
- Date: 2026-10-12
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: [ADR-019](ADR-019-unify-feature-builders-and-common-contracts.md)

## Context

`src/main.py`に特徴量のCLI、JSONの読込、入力型への変換、実行編成、結果の
JSON出力が集中している。ユーザーは、実行専用の`src/run`を設けず、特徴量CLIと
実行処理を`src/features/make_features.py`へ配置し、汎用JSON読込を
`src/data/loader/read_json.py`へ分離することを指定した。

ADR-011/017の監査条件と既存CLIの入力・出力契約を保ちながら、ファイルの責務を
整理する必要がある。この決定は配置と呼出し境界の変更に限定する。

## Decision

1. `src/features/make_features.py`が、`model audit`、`model features`、
   `model candidate-features`のCLI登録、入力型への変換、監査・生成APIの呼出し、
   監査結果と生成値のJSON出力を担当する。`src/main.py`は従来のCLI入口を維持し、
   特徴量コマンドを委譲する。取得・加工・Walk-forwardのコマンドは従来の責務を保つ。
2. `src/data/loader/read_json.py`は、明示パスのUTF-8 JSONを読み込み、ルートが
   objectであることを検証する。ファイル・文字コード・JSON構文のエラーを意味のある
   例外として返し、Typerや特徴量の型・加工規則へ依存しない。
3. JSON読込を必要とする特徴量生成とWalk-forwardは、この汎用readerを利用する。
   特徴量固有の入力契約は`make_features.py`で検証し、CLIの例外・終了コードへ変換する。
   JSON出力とNaNのnull変換は実行境界が担当する。
4. `src/run`と`json_io.py`は導入しない。既存のコマンド名、引数、終了コード、
   JSON項目、数値FeatureSchemaと中間Parquetの列契約は維持する。
5. 個別特徴量・監査モジュールはCLI入口をimportせず、raw SQLite・JV-Link・
   外部通信を呼び出さない。`DataLoader`のParquet facadeはJSON readerから独立する。

## Rationale

入力ファイル形式の検証をdataの読込境界へ置くことで、取得処理やCLIを開始せずに
JSON読込を再利用できる。特徴量の入力変換と実行処理を同じファイルへまとめることで、
呼出し元とJSON成果物の対応を追いやすくなる。利用者のコマンドを維持するため、
配置変更で既存の実行手順や保存済み入力を変更する必要はない。

## Consequences

- 特徴量の実行処理とCLI登録は`make_features.py`で確認できる。
- JSON readerを、Typerやモデル処理を必要とせずに単体検証できる。
- `src/features/`には計算・監査モジュールに加えて明示的なCLI/I/O境界が入るため、
  下位モジュールが`make_features.py`を参照しない依存方向を維持する。
- F01〜F21の加工規則、共通型、基底クラス、中間テーブルへの統合は別の変更単位であり、
  この配置変更で計算式や欠損処理を決定しない。

## Alternatives Considered

- `src/run`へCLIとJSON処理を置く案は、ユーザーの指定に従い採用しない。
- JSON readerにTyper依存やJSON出力を含める案は、readerの再利用と検証を妨げるため
  採用しない。

## Validation

UTF-8のobject読込、非objectの拒否、不正JSON、不正UTF-8、ファイル不存在を
テストする。従来の特徴量CLIとWalk-forwardの成功・失敗・NaN出力の試験を維持し、
Ruff、mypy、pytest、guard回帰で配置変更後の互換性を確認する。
