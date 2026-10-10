# ADR-014: 基礎取得と履歴オッズ取得のCLI責務分離

- Status: Accepted
- Date: 2026-10-10
- Decision Owners: Repository maintainers
- Supersedes: 公開CLI名とParquet公開タイミングに関するADR-013の記述
- Superseded by: N/A

## Context

基礎データの一括取得と、年単位で長時間かかるリアルタイム系オッズ履歴の
取得は、失敗時の再開単位とParquet公開タイミングが異なる。両者を同じCLI
責務に置くと、オッズ履歴の年途中停止時に不完全な全体スナップショットを
公開する可能性がある。また、実行時の状態はruntime台帳に保持し、固定方針
である`config/jvlink.toml`とは分離する必要がある。

## Decision

1. `--retrieve --mode=historical-basic`は`[historical]`プロファイルによる
   基礎データだけを取得し、取得処理が完了した後に完全Parquetスナップショットを
   1回再構築する。オッズ履歴のレース単位ループは実行しない。
2. `--retrieve --mode=historical-odds`は`[historical_odds.batch]`の範囲を
   最古の未完了年から1年ずつ取得する。各年のraw取得完了時にはParquetを公開せず、
   全管理年のraw状態が`acquired`または`provider_missing`になった時点で、完全Parquet
   スナップショットを1回だけ再構築する。
3. 取得途中の停止、JV-Link異常、または最終Parquet再構築の失敗では、raw SQLiteと
   進捗台帳を保持する。次回の`historical-odds`は未完了年または未公開状態を台帳から
   再開する。火曜日やTask Schedulerをアプリケーションの制御条件にしない。
4. 旧公開名`historical`と`historical-weekly`は受け付けない。既存の
   `historical-odds` CLIをリポジトリルートから直接実行する。台帳の内部名やruntime成果物名に含まれる
   `weekly`相当の実装用語も、年単位進捗の内部表現として残す。
5. ADR-013で定めたDataSpec別状態、`provider_missing`の証跡要件、OSロック、派生
   runtime設定の扱いは維持する。変更するのは公開CLIの責務と、raw取得完了後の公開
   タイミングである。

## Consequences

基礎データだけを更新したい場合にオッズ履歴を誤って起動せず、オッズ履歴の年途中で
不完全なParquetを公開しない。完全スナップショットの再構築は全raw取得完了時に
まとめて行うため、最終実行は大きなデータベースでは長時間になる。取得途中の状態を
確認したい場合は、runtime台帳と派生進捗ファイルを参照する。

## Validation

CLIテストで新しいモード名、基礎取得後の単一再構築、複数年raw取得後の単一再構築、
失敗時の終了を検証する。weekly進捗テストでは、公開状態がpendingでも`raw_only`取得が
次年を再選択せず、全raw完了後の一括公開で状態がpublishedになることを検証する。
