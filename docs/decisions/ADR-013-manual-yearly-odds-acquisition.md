# ADR-013: 手動年単位のオッズ履歴取得と進捗台帳

- Status: Accepted
- Date: 2026-10-09
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

JRA-VANのオッズ履歴の取得は年単位で長時間になる。毎週の差分を人が
手動で起動し、取得済み範囲と提供元側の欠損を区別して次回へ引き継ぐ必要が
ある。タスクスケジューラや曜日判定をアプリへ持ち込むと、火曜メンテナンス
の実際の結果を誤って欠損扱いにするため、取得実行の判断を外部運用へ残す。

## Decision

1. `historical-weekly` は一回の起動で最古の未完了年だけを処理し、過去日
   cutoffまでの候補を時系列に処理する。`scripts/retrieve-historical-odds-weekly.ps1`
   は単発起動して終了し、タスク登録・常駐ループ・曜日による待機を行わない。
2. 取得ポリシーは `config/jvlink.toml` の
   `[historical_odds.batch]` に置き、実行状態はGit管理外のruntime SQLite
   (`historical-odds-progress.db`)を正とする。race_idとDataSpecの組を台帳の
   主キーにして、`pending`、`running`、`acquired`、`provider_missing`、
   `failed`を保持する。
3. 初回台帳作成時は、既存アーカイブを完全なレースキーで観測する。指定した
   frontierまでの未取得組は、利用者がJRA-VAN側欠損として受理した
   `provider_missing`にする。frontier後に新しく候補となった組は取得対象の
   `pending`とし、後からアーカイブへ現れた行は外部観測として台帳へ取り込む。
4. raw SQLiteへ書き込む全取得モードは同じOSロックを保持する。別runtimeの
   台帳で同じraw DBを扱う設定を拒否し、未確定の`running`がある間は新しい
   JV-Link起動を拒否する。
5. JRA-VANが公開する [JV-Link APIエラーコード一覧](https://developer.jra-van.jp/t/topic/822)
   に従い、JVOpen/JVRTOpenの`-1`（該当データ無し）は正常終了として扱う。
   プロセス成功後に要求対象のRT表が存在し、スキーマ検証を通過したうえで空であり、
   DataSpec別にAPI戻り値`-1`を取得できた場合だけ、`provider_missing/jvopen_no_data`
   として完了にする。API戻り値を取得できない空表は`failed/empty_response_unverified`とし、
   表不在・不正な対象キー・保存やスキーマの異常も`failed`として再試行対象にする。
   火曜日もこの規則を変えない。
6. アーカイブ保存を先に確定し、その後に台帳と派生JSON/TOMLを原子的に更新
   する。生成された実行TOMLは状態から導出する成果物であり、固定方針TOMLや
   既存のJVLink設定ローダーの入力契約を置き換えない。
7. 旧台帳に残る`failed/empty_response_unverified`は、完全なRaceKeyとDataSpecを指定する
   明示コマンドで`provider_missing/provider_confirmed_missing`へ移行できる。確認時にも
   アーカイブ件数が0であることを検証する。新規取得では、公式の正常な空応答を
   `jvopen_no_data`として自動確定するため、この移行は旧台帳互換に限る。
8. 正常な`jvopen_no_data`は同じrunの次のRaceKeyへ進む。JVLinkToSQLiteの起動失敗・
   非0終了・タイムアウト、保存失敗、スキーマ検証失敗ではそのrunを停止し、未完了の年を
   次回へ引き継ぐ。プロセス境界で取得できないJV-Link API戻り値をログから推測せず、
   API名とコードはDataSpecごとに台帳の`api_name`・`api_returncode`へ永続化し、既存の
   `returncode`（JVLinkToSQLiteプロセス終了コード）の意味は変更しない。旧v1台帳は最初の
   更新時にAPI列だけを追加し、API証跡なしの既存`provider_missing/jvopen_no_data`は
   `provider_missing/legacy_provider_missing`へ移行する。

## Consequences

### Positive

- 週次の取得差分、初期受理した欠損、別モードで追加された行を分けて追跡できる。
- 年途中で停止しても、次回は同じ年の未確定組から再開できる。
- 曜日やタスクスケジューラを製品コードへ埋め込まず、メンテナンス結果を実際の
  JV-Link応答として扱える。

### Negative and follow-up

- JV-LinkToSQLiteがAPI戻り値をプロセス境界へ公開しない実行環境では、空表を
  `empty_response_unverified`として明示確認へ回す。実行結果から取得できたAPIコードは
  DataSpec別にAPI列へ保存する。
- 台帳とraw SQLiteは別DBなので、外部取得・アーカイブ保存・台帳更新の中断復旧を
  継続的にテストする必要がある。
- 取得済み判定はアーカイブ行の存在を基準とし、時系列全体の完全性を保証しない。

## Validation

一時SQLiteと偽のJV-Link実行境界で、frontier境界、全10競馬場、DataSpec別差分、
年選択、ロック、別runtime拒否、外部追加の取り込み、再実行、火曜日を特別扱い
しない失敗分類を検証する。実機の成功・正常空応答・メンテナンス失敗の判定は、
一次仕様として [JRA-VANのエラーコード一覧](https://developer.jra-van.jp/t/topic/822) を参照し、
実機のプロセス成功と空RT表を模したテストで`jvopen_no_data`の分類を検証する。
