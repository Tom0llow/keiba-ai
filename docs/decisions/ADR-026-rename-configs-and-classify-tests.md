# ADR-026: 設定フォルダーを改名し既存テスト配置の中で分類する

- Status: Accepted
- Date: 2026-10-19
- Decision Owners: Repository maintainers
- Supersedes: ADR-006・ADR-020・ADR-024・ADR-025（ルート設定フォルダー名のみ）
- Superseded by: N/A

## Context

PR #21の追加要件は、ルート設定フォルダーをconfigsへ改名し、既存テストを単体と結合に分類することである。
既存のガード付き開発手順とCIをそのまま使えることが制約となる。CIはpytest src/testsとmypy srcを
使用し、AGENTS.mdとスキルもsrc配下の全体検証を前提にしている。テストをsrcの外へ出すと、
保護対象の変更が必要になるため、既存のテスト配置の中で分類する。
業務計算、設定値・相対パス値、保存形式、非配布Pythonプロジェクトの環境契約を維持する。

## Decision

1. 既存3 TOMLを内容を変えずconfigs/へ移す。CLIの既定設定パスと利用例を更新する。
   設定ファイルの親からの相対パス解決を維持し、同じ深さの改名でデータ保存先を変えない。
   機能内のjra_van_retriever/config/と共通configuration/は移動しない。
2. テストはADR-002のsrc/tests配置を維持する。純粋な計算・検証と外部境界をmockした
   分離テストをsrc/tests/unit/、実ファイル、SQLite、subprocess、環境、機能間の接続を
   確認するテストをsrc/tests/integration/へ分類する。混合ファイルは既存関数・decorator・
   parametrize・fixtureを保持して分割する。
3. 環境契約のsmoke testだけはsrc/tests/test_project_environment.pyの既存パスを維持する。
   実環境の確認として性質は結合テストであるが、既存文書・指示・直接実行との互換性を優先する。
4. 実カタログから多数のbuilderを組み立てるexplanatory_variablesとindividual_feature_builders、
   実ファイルの存在確認を通すJVLink adapterはintegrationにまとめる。
   tmp_path引数の有無だけでは分類しない。CLIのhelp・dispatchは外部処理をmockしてunitで検査する。
5. pytestのtestpathsはsrc/tests、mypyのfilesはsrcを維持する。同名の分割モジュールを
   収集できるimportlibモードを使う。既存のpytest src/testsとmypy srcが全テストを検査し、
   CI、pre-commit、スキル、ガード付き開発手順の保護ファイルを変更しない。

## Rationale

テスト分類の意図を表しながら、現在の検証対象とガードの前提を維持する。
実境界を含むテストをunitへ置かず、既存fixtureとテスト本体を保持する。
設定定義の複製や新しい共通層を増やさず、過去ADRの理由は保持して設定フォルダー名だけを部分置換する。

## Consequences

設定パスを明示する利用者はconfigs/へ参照を更新する。CLIの引数名・終了コード、設定の
キー・値・登録順、計算・永続形式は維持する。分類したテストを直接実行する場合は新しい
src/tests内のパスを指定する。pytestの既定実行、CIの明示実行、mypy srcの検査範囲は同じである。
ガード付き開発手順を使うための保護設定変更や再インストールは、この配置変更には必要ない。

## Alternatives Considered

- ルートtestsへの移設は既存CIと型検査の前提を変えるため採用しない。
- 全テストのunitへの一括配置は、実ファイル・DB・機能接続の検証を正しく表さない。
- カタログの21定義をテスト側へ複製すると唯一の登録元と乖離するため採用しない。
- 旧配置へのshimやシンボリックリンクは設けず、実体をsrc/tests内に置く。

## Validation / Follow-up

基準HEADの収集nodeidと比べ、ファイル部分を除く関数名・parameter ID・重複数が一致することを確認する。
既存テストの本体・decorator差分を参照パス変更に限定し、3 TOMLの内容をSHA-256で照合する。
既存コマンドのpytest src/tests、mypy srcとRuff、ガード回帰を検証する。
全ファイルの対応・分類理由と実行結果を[移行記録](../refactoring-pr21-configs-tests.md)へ記録する。
