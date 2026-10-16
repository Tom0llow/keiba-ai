# ADR-022: CLIをmainへ集約し機能固有の変換と汎用JSON出力を分離する

- Status: Accepted
- Date: 2026-10-15
- Decision Owners: Repository maintainers
- Supersedes: ADR-020（CLI配置判断のみ）
- Superseded by: N/A

## Context

ユーザーは`src/run/`の削除と、全体のCLI定義・実行を`main.py`で管理する構成を
明示的に要求した。既存のrunにはCLI制御、特徴量・モデル固有の入力・出力変換、
汎用JSON保存が混在していた。CLIを集約しても、純粋な型変換をCLIに依存させず、
コマンドの入出力・取得と公開の順序・特徴量登録の契約を維持する必要がある。

## Decision

1. `src/run/`を削除し、互換用モジュールを残さない。`src/main.py`が全Typerアプリ、
   コマンド登録、オプション定義、ハンドラーを所有する。CLI引数の検証、実行時の
   設定・入力読込と依存生成、取得・公開・特徴量・評価の編成、表示、エラーJSONと
   終了コードもここで管理する。`__main__`ガードではappの起動だけを行う。
2. `features/serialization/inputs.py`は読込済みJSON objectを`FeatureBatchInput`と
   `FeatureGroupInput`へ変換する。`outputs.py`は`FeatureAudit`と`FeatureBuildResult`を
   JSON用の値へ変換する。既存のフィールド検証、明示的な境界フラグ、tuple変換を維持する。
3. `models/serialization/inputs.py`はモデルの`FeatureSchema`と`FeatureInput`を変換し、
   `outputs.py`は可用性監査、生成結果、walk-forward評価・指標をJSON用の値へ変換する。
   F01〜F21の入力とモデル入力を混同せず、モデル採用・数値投影を変更しない。
4. 変換処理はI/Oを行わず、通常の`ValueError`・`TypeError`を送出する。下位モジュールは
   `main`やTyperに依存しない。別モジュールから利用する変換関数は公開名を用いる。
5. 汎用`write_json`と再帰的なNaNのnull変換のみを`utils/json_output.py`へ置く。
   UTF-8、親ディレクトリ作成、`allow_nan=False`、2字のインデント、末尾改行を維持する。
   汎用読込は既存の`utils/loader/read_json.py`に残し、CLIエラーへの変換はmainが担当する。
6. importとhelpでは設定・入力を読まず、クライアント生成や取得を開始しない。
   特徴量設定はコマンド実行時に一回だけ読み、同じ不変登録を監査・生成へ渡す。
7. 既存CLI名、フラグ、既定値、help、終了コード、表示、JSONキー・日時・欠損表現を維持する。
   全raw取得後の単一公開、plan-onlyの無書込、ロック・台帳・callback・realtime二段取得、
   processed-dataとdatamartの契約を変更しない。ADR-021は継続する。

## Rationale

CLIの定義と実行順序をmainで確認できるようにし、機能固有の変換を各機能から
再利用できるようにする。汎用JSON保存から業務型を除くことで共通処理の責務を限定する。
既存の計算APIを利用し、ファイルの大きさだけを理由に新たな実行基盤を導入しない。

## Consequences

runを参照するPython利用者とテストは新しい所有モジュールへ移行する必要がある。
mainは複数コマンドの編成を含むが、業務計算や型変換は下位機能が所有する。
既存CLI入力と保存済み成果物の移行、依存追加、実データ加工は必要ない。

## Alternatives Considered

- runに互換用の再公開を残す案は、run削除という要求を満たさない。
- JSON変換を全てmainへ置く案は、CLIと独立した利用を妨げる。
- 特徴量・モデルの型変換をutilsにまとめる案は、共通処理を業務契約へ依存させる。
- service・workflow層の新設は、今回必要なCLI管理に対して責務と依存を増やす。

## Validation

既存CLIテストをmainへ移行し、登録、取得と公開順序、plan-only、エラーJSON、終了コード、
特徴量設定の一回読込を確認する。純粋な変換の値保持・検証例外・Typer非依存と、
mainのimport/help時の無実行を検証する。Ruff、mypy、全pytestとguard回帰で既存契約を確認する。
