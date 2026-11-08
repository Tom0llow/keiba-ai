# ADR-005: JVLinkToSQLiteをローカルのJRA-VAN取得境界として使う

- Status: Accepted
- Date: 2026-10-03
- Decision Owners: Repository maintainers
- Related Issues/PRs: N/A
- Supersedes: N/A
- Superseded by: N/A

## Context

プロジェクトは、過去のオッズを含むJRA-VANのレースデータを、既存のrawのSQLiteデータ段階へ取得する必要がある。対象のWindows 11マシンには、JVLinkToSQLiteが既に`C:\JVLinkToSQLite`配下にインストールされている。保守されているローカルのインポーターが既にその境界を所有している場合、プロジェクトはJV-Link COMの通信を再実装したり、JRA-VANの資格情報をリポジトリの設定に保存したりするべきではない。

現行のリポジトリは、rawのSQLiteデータを、派生したParquetの出力と分けている。レースデータの取得を導入すると、ローカルの外部プロセスとの境界が加わる。この境界は明示的に保ち、通常のテストスイートでJRA-VANへのアクセスを必要とせずにテストできる状態を維持しなければならない。

## Decision

- ローカルにインストールした`JVLinkToSQLite.exe`を、このリポジトリとJRA-VAN/JV-Linkの間の取得境界として使う。
- `src/data/retriever/`配下に小さなPythonのrunnerを追加し、`subprocess.run`を通じて、argvのトークンでJVLinkToSQLiteを起動する。シェルは使わず、コマンド文字列も組み立てない。
- 実行ファイルのパス、SQLiteの出力先パス、XML設定のパス、タイムアウト、`skipslastmodifiedupdate`の選択を明示的に渡す。資格情報を環境変数やリポジトリのファイルから読まない。
- このアダプターでは、JVLinkToSQLiteを`Exec`モードで実行する。上位のhistorical/latestのオーケストレーションと設定の所有は、別の実装タスクとして残す。
- 0以外の終了ステータス、起動の失敗、タイムアウトは、明示的なPythonの例外として扱う。プロセスの起動前に、必要なファイルシステムのパスを検証する。
- subprocessの境界だけをmockし、単体テストをWindows、JV-Link、JRA-VAN、ユーザー所有のファイルから独立させる。

## Rationale

JVLinkToSQLiteは、JRA-VANの認証、JV-Linkへのアクセス、レコードの解析、SQLiteへの書き込みを既に内包している。これを再利用すると、プラットフォーム固有の連携をモデリング用のリポジトリ内に重複して持たずに済み、Pythonの境界を、決定論的にテストできるほど小さく保てる。argvを直接渡すと、シェルインジェクションのリスクを避け、パスの扱いを明示できる。

## Consequences

- データの取得には、動作するJV-Link/JRA-VANの環境と、互換性のあるJVLinkToSQLiteの実行ファイルを備えたWindowsホストが必要となる。
- リポジトリは、JRA-VANのサービスキーを所有も永続化もしない。
- 取得は、ローカルの実行ファイル、JV-Link、JRA-VANの可用性、XMLの設定、ファイルシステムの権限が原因で失敗し得る。呼出し側は、気付かれない部分的な成功ではなく、境界の例外を受け取る。
- rawのSQLiteの出力先は、JVLinkToSQLiteが作成または更新することがある。runner自体は、SQLiteの内容を解析も変更もしない。
- historicalとlatestのデータの方針は、意図的にこのrunnerに組み込まない。

## Alternatives Considered

- PythonからJV-Link COMを直接呼び出すと、JVLinkToSQLiteが既に提供する、プラットフォーム固有のプロトコル、解析、エラー処理の責務が重複する。
- 環境変数のAPIキーを使う仮定のHTTP APIを呼び出す方式は、選択したJRA-VAN Data Lab/JV-Linkの連携モデルに合わない。
- 取得のロジックを`race_data.py`に組み込むと、外部データの取り込みと、既存のSQLiteからParquetへの変換の責務が混ざる。

## Validation / Follow-up

単体テストで、argvの構築、シェルを使わない実行、任意指定の読取位置の保持、パスがない場合の扱い、タイムアウトの変換、0以外の終了の変換を検証する。後で作るhistorical/latestの取得処理は、自らsubprocessを起動せず、このrunnerに依存するべきである。

## Security / Privacy Impact

このアダプターは、資格情報をコミットせず、ログに出さず、渡しもしない。subprocessの起動には、`shell=False`でargvのトークンのリストを使う。実行ファイルと設定のパスは、ローカルのファイルシステムからの入力として扱い、使う前に検証する。

## Operational Impact

運用者は、リポジトリの外でJV-Link/JVLinkToSQLiteをインストールして設定しなければならない。長時間のインポートでは、タイムアウトを使わないことを選べる。スケジュール実行や対話的な呼出し側は、そのworkflowに合った正のタイムアウトを指定できる。

## Migration / Rollback

移行する既存の取得実装はない。ロールバックは、runnerとその呼出し側を削除することで行う。既存のrawのSQLiteとprocessedのParquetの成果物は変わらない。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-10-03 | Accepted | JRA-VANの取得境界として、ローカルのJVLinkToSQLiteプロセスを選択 |
