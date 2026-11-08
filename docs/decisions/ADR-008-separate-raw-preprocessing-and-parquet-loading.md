# ADR-008: rawの前処理をParquetの読込から分離する

- Status: Superseded by ADR-024（モジュール配置判断のみ。保存・CURRENT・一貫性の契約は継続）
- Date: 2026-10-04
- Decision Owners: Repository maintainers
- Related Issues/PRs: PR #8
- Supersedes: ADR-003
- Superseded by: ADR-024（モジュール配置判断のみ）

## Context

JRA-VANからの取得は現在、historical、latest、予測時のrealtimeの各workflowを通じて、変更可能な
rawのSQLiteデータベースを更新する。以前のParquetのエクスポーターは、設定の解析、rawのSQLiteの
読込、Parquetの書き込み、processedのParquetの読込を、一つの`race_data.py`モジュールにまとめ、
既存のprocessedディレクトリの更新を拒否していた。その境界では、繰り返し行う取得や予測時の更新を、
もはやうまく扱えない。

アプリケーションには、学習と推論の両方に共通する、processedデータの読込経路が一つ必要でもある。
学習がParquetを読む一方で、realtimeの推論中にモデルがSQLiteを読めるようにすると、二つ目の提供
経路ができ、スキーマ、絞り込み、前処理のずれが生じるリスクが高まる。

## Decision

- `data/raw/race.db`を、正本となる変更可能な取得データの保存先として維持する。
- rawのSQLiteの読取りは、読込ではなく前処理に属する。これは`src/data/preprocesser/`配下に
  実装し、現在は`read_sqlite.py`である。
- `src/data/data_preprocesser.py`は、公開の前処理facadeである。次を所有する。
  - historicalとlatestのデータについての、完全なprocessed snapshotの公開。
  - realtimeの取得後の、レース単位の予測時Parquetの公開。
- `src/data/loader/`には、processedデータのreaderだけを置く。Parquetのreaderは
  `src/data/loader/read_parquet.py`であり、`race.db`を開くことはない。
- `src/data/data_loader.py`は、学習、分析、推論のための公開の読込facadeである。
- 完全なprocessedのデータセットは、`data/processed/snapshots/<snapshot-id>/`配下の不変の
  版ディレクトリとする。`data/processed/CURRENT`は小さなポインタであり、完全なsnapshotを
  書き込んで検証した後にだけ、原子的に置き換える。
- 予測時のオッズは、`RaceKey`ごとに
  `data/processed/realtime/<race-id>/versions/<version-id>/`配下へ公開する。レースごとの
  `CURRENT`ポインタは、archiveのO1/O2の両方のParquetファイルを書き込んで検証した後にだけ、
  原子的に置き換える。
- realtimeの前処理は、累積のrawのarchive表を対象のレースキーだけに絞り込み、そのレースの
  O1/O2のprocessedファイルだけを書き込む。推論の前に、過去データの完全なsnapshotを
  再構築することはしない。
- historicalの取得は、完全なprocessed snapshotを自動で再構築する。latestの取得は、完全な
  processed snapshotを更新する。realtimeの取得は、取得の後に、対象レースのprocessed Parquetを
  自動で公開する。
- rawデータが既にあり、取得が不要な場合のために、単独の`preprocess rebuild` CLIも引き続き
  利用できる。

## Rationale

これにより、依存の方向が一つになる。

```text
JV-Link -> JVLinkToSQLite -> raw SQLite -> preprocessing -> Parquet -> loader -> model
```

そのため、学習と推論は、同じ読込層を通じてParquetを使う。ポインタを原子的に公開することで、
失敗した前処理が、最後に正常と確認されたprocessedデータを置き換えることを防ぐ。レース単位の
realtimeの出力により、オッズを更新するたびに過去のParquetを完全に再構築することなく、予測時の
I/Oに上限を保てる。

## Consequences

- processedデータは、Parquetファイルを置く一つの変更可能なディレクトリではなく、版ディレクトリと
  小さな`CURRENT`ポインタファイルを使う。
- 古いsnapshot/版のディレクトリは、別の保持方針が削除するまで保持する。これは、ディスク使用量の
  最小化よりも、ロールバックと再現性を優先するものである。
- `latest`は現在、取得の後にsnapshotを完全に更新する。後の最適化で、表やパーティション単位の
  差分公開を実装してもよいが、同じ公開ローダーの契約と、原子的な公開の意味を維持しなければ
  ならない。
- realtimeの推論では、モデルが対応するレース単位のParquetの版を読む前に、前処理の呼出しが
  成功していなければならない。
- rawのSQLiteデータベースは、引き続きGitの管理対象外で、変更可能である。processedのParquetも
  Gitの管理対象外であり、Gitで版を管理するのは、データセットではなく、コードと設定である。

## Alternatives Considered

- 推論にSQLiteを直接読ませる案は、学習とは別の、二つ目のデータ提供経路ができるため、
  採用しなかった。
- realtimeのオッズの要求のたびに、すべてのParquet表を書き直す案は、不必要に高コストであるため、
  採用しなかった。
- SQLiteの`rowid`で無条件に追記する案は、上流の行が更新されることがあり、rowidだけの差分では
  変更を見落とし得るため、採用しなかった。
- SQLiteのreaderを`loader/`配下に置く案は、ローダーが利用者向けのprocessedデータの境界である
  のに対し、SQLiteはrawの前処理の入力であるため、採用しなかった。

## Validation / Follow-up

テストは、完全なsnapshotの公開、変換失敗時の以前の`CURRENT`ポインタへのロールバック、realtimeの
O1/O2のレースキーによる絞り込み、rawのSQLiteファイルを削除した後のprocessedデータの読込を対象と
する。将来の前処理モジュールは`src/data/preprocesser/`配下に、将来のprocessedの形式やreaderは
`src/data/loader/`配下に、rawの取得境界を変えずに追加できる。

## Security / Privacy Impact

新しいネットワーク境界や資格情報は導入しない。rawとprocessedのデータは、ローカルのファイル
システムに置き、Gitの外にとどめる。

## Operational Impact

historicalとlatestのコマンドは、rawの取得が成功した後に、Parquetを公開する。realtimeのコマンドは、
realtimeの取得が成功した後に、レース単位のParquetを公開する。前処理が失敗した場合は、以前に公開
したポインタを変えず、不完全なprocessedデータを見せる代わりに、コマンドを失敗させる。

## Migration / Rollback

旧来の`src/data/race_data.py`と、`src/convert_race.py`の入口を削除する。新しいローダーは
`CURRENT`ポインタを必要とするため、既存の旧形式の`data/processed/*.parquet`ファイルは、有効な
新しいsnapshotとして扱わない。`uv run python src/main.py preprocess rebuild`を1回実行して、
新形式の最初のsnapshotを公開する。公開済みのデータセットのロールバックは、その版ディレクトリが
残っている間であれば、以前の有効なポインタの値を復元することで行える。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-10-04 | Accepted | rawの前処理をParquetの読込から分離し、完全データとrealtimeの原子的な公開を追加 |
