# ADR-006: JVLinkの取得profileを設定し、Typer CLIを提供する

- Status: Superseded by ADR-026（ルート設定ファイルの配置のみ。設定所有・取得契約はAccepted）
- Date: 2026-10-04
- Superseded by: ADR-026（設定配置のみ）

## Context

JVLinkToSQLiteは、実行設定と、変更可能な最新読取状態の両方をXMLに保存する。そのローカルの
`setting.xml`はユーザーの所有物でもあり、JVLinkToSQLiteのアプリケーションから変更されることが
ある。historical、historical-odds、latestのXMLファイルを別々に保守するようユーザーに求めると、
その構造が重複し、keiba-aiがXMLの手動編集に依存することになる。

取得モードごとに、必要な動作が異なる。

- historicalの基本データの取得はセットアップデータを使い、ユーザーのseed設定を進めては
  ならない。
- historicalの時系列オッズは、選択したrealtimeのDataSpecと、レース固有の`JVRaceKey`だけを
  使う。
- latestの取得は、成功した実行の後にJVLinkToSQLiteが書き戻した読取位置を保持しなければ
  ならない。

リポジトリには、呼出し側に場当たり的なPythonで`DataRetriever`を構築させずに取得モードを選べる、
ユーザー向けの安定したコマンドも必要である。

## Decision

インストール済みのJVLinkToSQLiteの`setting.xml`は、keiba-aiから見て読み取り専用のseedとして
扱う。

取得の方針は`config/jvlink.toml`で宣言する。設定には次を含める。

- ローカルのJVLinkToSQLiteの実行ファイルのパス。
- seed設定のパス。
- historical、historicalのオッズ、latestの取得のための、意味上のprofile。
- 明示的なDataSpecのallow-listと、該当する場合はモード固有の日付。JRA-VANのデータ種別ごとに
  収録期間が異なるため、historicalのセットアップprofileでは、DataSpecごとに別の開始日時を
  定義できる。

`JVLinkSettingBuilder`は、それらの意味上のprofileからJVLinkToSQLiteのXML構造への変換を所有する。
normal、setup、realtimeの各セクションについて、セクションの有効状態を設定し、設定された
DataSpecの一覧を排他的なallow-listとして扱う。これにより、seedで有効になっているDataSpecが、
別の取得モードへ漏れることを防ぐ。

historicalの基本データとhistorical-oddsのXMLファイルは、一時ディレクトリに生成し、
`--skipslastmodifiedupdate`を付けて実行する。これらはhistoricalのworkflowの終了時に破棄し、
seedは一切変更しない。

latestの取得は、Gitの管理対象外であるデータのruntimeディレクトリ配下に、永続的なruntime設定を所有する。
初回の実行では、それをseedから生成する。以降の実行では、runtimeのXMLを元にしてlatest profileを
再適用し、更新した読取位置を、JVLinkToSQLiteにそのruntimeファイルへ書き戻させる。

`config/data.toml`は、rawデータベースとruntimeディレクトリのパスを所有する。

取得は、`src/main.py`のTyper CLIを通じて提供する。

```text
uv run python src/main.py --retrieve --mode=historical-basic
uv run python src/main.py --retrieve --mode=latest
```

`DataRetriever`は、引き続きCLIの下にある、アプリケーション層のオーケストレーションAPIとする。
Typerは明示的な実行時の依存関係であり、`uv.lock`でロックする。

## Consequences

- ユーザーは、生成されたXMLを編集する代わりに、TOMLで取得の方針を設定する。
- インストール済みのJVLinkToSQLiteのseedは、それ自体のGUIとの互換性を保ち、keiba-aiの
  変更可能な状態としては使わない。
- historicalの実行は、seedとコミット済みのprofileから再現できる。
- latestの取得は、マシン固有のruntimeファイルをコミットせずに、差分取得の状態を保持する。
- DataSpecの追加や削除は明示的な設定の変更であり、存在しないDataSpecは、設定生成の境界で
  失敗する。
- JVLinkToSQLiteのXMLスキーマが変わると、`JVLinkSettingBuilder`の変更が必要になることがある。
- CLIにより、ロックされた実行環境に、Typerとその推移的な依存関係が加わる。

## Alternatives considered

### ユーザーが所有する3つのXMLファイルを保守する

JVLinkToSQLiteの設定が重複し、手動の同期が必要となり、方針と、生成済み/変更可能な状態とが
混ざるため、採用しない。

### インストール済みの`setting.xml`をその場で書き換える

historicalの実行が、ユーザーの設定と最新読取状態を上書きし得るため、採用しない。また、失敗や
中断した実行によって、ローカルのJVLinkToSQLiteのインストールが、予期しない状態で残りやすく
なる。

### Python APIだけを残す

日常的な取得には、その場でPythonの構築を求めるのではなく、文書化された、繰り返し使えるCLIの
入口を一つ用意するべきであるため、採用しない。
