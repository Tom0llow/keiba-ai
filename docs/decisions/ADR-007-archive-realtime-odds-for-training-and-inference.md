# ADR-007: 学習と推論のためにrealtimeのオッズをarchiveする

- Status: Accepted
- Date: 2026-10-04

## Context

予測時の推論には、モデルの実行の直前に、対象の1レースのオッズが必要である。同じO1/O2の
レコード群は、JVLinkのDataSpec `0B41`と`0B42`を通じて、過去の学習用の特徴量を作るためにも使う。

JVLinkToSQLiteは、realtimeのO1/O2表を一時的なstaging表として扱う。そのrealtimeのデータブリッジは
`RT_O1_ODDS_TANFUKUWAKU`と`RT_O2_ODDS_UMAREN`を作成し、以降のrealtimeの実行のたびに、それらの
表を作り直す。そのため、これらの`RT_*`表自体は、過去分のbackfillにとっても本番の推論にとっても、
オッズの累積履歴にはなり得ない。

予測には、市場に関する、関連した2つの見方も必要である。

- `0B41` / `0B42`: 発売開始から現在の取得時点までの、時系列のO1/O2オッズ。
- `0B31` / `0B32`: 対象レースの、現在のO1/O2のrealtime snapshot。

どちらも、レース固有の`JVRaceKey`が必要である。

## Decision

JVLinkToSQLiteの`RT_*`のO1/O2表は、stagingとしてだけ扱う。

historicalまたは予測時のO1/O2の実行のたびに、その後で、stagingの行を、同じrawのSQLite
データベース内の累積の表へコピーする。

- `ARCHIVE_O1_ODDS_TANFUKUWAKU`
- `ARCHIVE_O2_ODDS_UMAREN`

archive表は、staging表から、同じ列名と列順で作成する。行は、行全体を集合として重複除去して
コピーする。そのため、同一の取得を繰り返しても冪等であり、`HappyoTime`が異なる観測は保持する。

historicalの取得は、次のレースの実行がstaging表を作り直す前に、各レースの直後に
`0B41` / `0B42`をarchiveする。

予測時の取得は`RealtimeRetriever`が実装する。検証済みの1つのレースキーについて、次を行う。

1. `[realtime_history]` profile（`0B41`、`0B42`）を実行する。
2. その結果のO1/O2のstagingの行をarchiveする。
3. `[realtime_current]` profile（`0B31`、`0B32`）を実行する。
4. その結果の、現在のO1/O2の行をarchiveする。

どちらの実行も、一時的なXMLと`--skipslastmodifiedupdate`を使う。レースキーを指定した予測の
要求には、変更可能な読取位置は必要ない。

対象レースは、`config/jvlink.toml`の`[realtime]`セクションで宣言できる。CLIでレースキーの
オプションをすべて指定すると、1回の呼出しに限り、設定した対象より優先される。

この経路は、Typer CLIを通じて提供する。

```text
uv run python src/main.py --retrieve --mode=realtime
```

日付以外のレースキーの構成要素は、すべて2桁の文字列でなければならない。archiveは、`data/`配下の
ローカルのrawデータセットの一部であり、Gitにはコミットしない。

## Consequences

- 過去分と本番のO1/O2の行は、永続化された一つの列の契約を共有する。
- realtimeのstaging表が置き換わっても、以前に収集したオッズは消えない。
- 同じrealtimeの取得を繰り返しても、同一の行は重複しない。
- 異なる時系列の観測は、`HappyoTime`を含む元の列によって、区別できるまま残る。
- 特徴量の生成は、一時的なJVLinkToSQLiteの`RT_*`表に依存せず、累積のarchiveを読める。
- 将来のJVLinkToSQLite/JV-Dataの版でスキーマが変わった場合は、互換性のない行を既存のarchive表へ
  追加する前に、それを検出して対処しなければならない。

## Alternatives considered

### 推論時にだけ`RT_*`表を直接読む

予測時の観測を保存せず、次のレースの実行のたびに前のstagingの行が置き換わり得る、過去分の
backfillも解決しないため、採用しない。

### `0B31` / `0B32` / `0B41` / `0B42`を`latest`に入れる

`latest`はマシンの差分取得の状態を所有する一方、これらのDataSpecは、明示的にレースキーを指定した
予測の要求であるため、採用しない。両者を混ぜると、ライフサイクルと失敗の意味が曖昧になり、
一時的なstaging表の置き換えも解決しない。

### 履歴と現在のsnapshotを別々のスキーマに保存する

JVLinkToSQLiteは、realtimeのO1/O2を同じ条件付きのレコードスキーマへ対応付けるため、現在の範囲
では採用しない。archiveの契約を一つに保つと、元のレコードの項目を保持したまま、Training-Serving Skewを
最小にできる。
