# ADR-013: 手動年単位のオッズ履歴取得と進捗台帳

- Status: Accepted
- Date: 2026-10-09
- Decision Owners: Repository maintainers
- Supersedes: N/A
- Superseded by: ADR-014（公開CLI名とParquet公開タイミングのみ）、ADR-015（初回台帳作成時の欠損判定のみ）

## Context

JRA-VANのオッズ履歴の取得は年単位で長時間になる。毎週の差分を人が
手動で起動し、取得済み範囲と提供元側の欠損を区別して次回へ引き継ぐ必要が
ある。タスクスケジューラや曜日判定をアプリへ持ち込むと、火曜メンテナンス
の実際の結果を誤って欠損扱いにするため、取得実行の判断を外部運用へ残す。

## Decision

1. `historical-weekly` は最古の未完了年を1年単位で処理し、過去日
   cutoffまでの候補を時系列に処理する。取得と完全Parquet公開が成功したら、台帳から
   導出した実行設定を次年へ更新して同じ起動で継続する。利用者の停止、取得または公開の
   異常、対象年の枯渇で終了する。`historical-odds` CLIは
   この連続実行プロセスを単発起動し、タスク登録・常駐スケジューラ・曜日による待機を行わない。
2. 取得ポリシーは `config/jvlink.toml` の
   `[historical_odds.batch]` に置き、実行状態はGit管理外のruntime SQLite
   (`historical-odds-progress.db`)を正とする。race_idとDataSpecの組を台帳の
   主キーにして、`pending`、`running`、`acquired`、`provider_missing`、
   `failed`を保持する。
3. 初回台帳作成時は、既存アーカイブを完全なレースキーで観測する。行がある組は
   `acquired`、行がない組は `pending` とし、初期状態の欠損を
   `provider_missing` へ分類しない。後からアーカイブへ現れた行は外部観測として
   台帳へ取り込む。
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

### Amendment 1: 確定の発表がない別モードの行を取得済みとしない（2026-11-21）

- 2026-11-21に人間の承認を受けてこのADRへ追加した（ADRのStatusはAcceptedのまま）。Issue #66。
- Decision 3の「後からアーカイブへ現れた行は外部観測として台帳へ取り込む」を次のとおり改める。
  台帳の照合で、要求していない組を`acquired/external_archive_observed`として取り込むのは、その組のarchiveに
  `headDataKubun`が`4`（確定オッズ）または`5`（確定オッズ（月曜））の行がある場合に限る。
  確定の行がない組は取り込まず、`pending`・`failed`・`provider_missing`の状態を保つ。新しい候補は`pending/new_candidate`とする。
- 既に`acquired`の組と、初回の台帳作成（Decision 3の初期スナップショット、ADR-015）の規則は変えない。
- archiveに確定の行が1件もない`acquired`の組と、確定の行がない`provider_missing`の組では、追加行が現れても、その組と年のpublication状態を変えない。その行は次回の完全Parquet公開に含める。確定の行がある`acquired`の組は、行数が増えれば従来どおり取り込み直し、その年を公開待ちにする。
- Decision 7の「確認時にもアーカイブ件数が0であることを検証する」を次のとおり改める。`failed/empty_response_unverified`の組を`provider_missing/provider_confirmed_missing`へ確定するとき、archiveに確定の行（`headDataKubun`の`4`・`5`）があれば拒否し、確定の行のない行（予測用の取得など）だけがある場合は受け付ける。予測用の取得の行があるレースを要求して、API戻り値のない空の応答になった組が、`failed`のまま年の取得を止め続けないためである。
- 根拠: race-day-oddsの予測用の取得（ADR-032 Amendment 2）はfreezeの時刻に0B41/0B42を保存するため、
  その行は確定の発表を含まず、freezeより後の発表と、freezeの時点で取得し損ねた発表を欠く。行の有無で取り込むと、
  historical-oddsがこのレースをbackfillしない。2026-11-21の実データでは、historical-oddsで要求した2025年の
  全3,456レースのO1・O2が`headDataKubun`の`4`を含み、2026-11-14・15に予測用の取得だけで保存した32レースは
  `1`・`2`だけだった。

### Amendment 2: 対象年の終わりを延ばす（2026-11-24）

- 2026-11-24に人間の承認を受けてこのADRへ追加した（ADRのStatusはAcceptedのまま）。Issue #111。
- 保存した`policy_hash`が、現在の設定の`last_year`だけを台帳の年の表の最後の年に置き換えた方針と一致するときに限り、`last_year`の延長を受け付ける。延長した範囲の年を`pending`で年の表へ加え、`metadata.policy_hash`を現在の設定へ移す。既存の年の公開状態と`race_specs`の行は変えない。
- 延長前の方針で台帳全体を検証してから書き込む。台帳のスキーマ、`raw_db`、既存の年の範囲、状態と件数、archiveのスキーマに不一致があれば延長を拒否し、台帳を変更しない。台帳のスキーマversionは変えない。
- `--plan-only`は台帳へ書き込まず、延長後の年を`pending`として予定に加えて示す。`last_year`の短縮、`first_year`・`race_start_date`・DataSpecなど他の取得方針の変更を伴う延長は、従来どおり拒否する。
- 延長は自動で行い、明示の引数は設けない。`last_year`を上げた後、台帳へ書き込む最初のhistorical-oddsのコマンド（通常の実行、`--recover`、`--confirm-provider-missing`）が、旧frontier形式の移行の前に延長する。運用者は年`Y`の最初の開催日の翌日以後に`last_year`を`Y`へ上げる。加えた年は公開待ち（`pending`）になり、その年の候補がなくても次の実行が完全Parquetを再構築するためである。手順は`docs/retraining-operation.md`に従う。
- 根拠: ADR-048決定8では、年`Y`の時系列オッズの取得に`last_year`を`Y`へ上げる台帳の移行が必要とし、Issue #111で別途行うとしていた。

## Consequences

### Positive

- 週次の取得差分、実取得で確認した提供元欠損、別モードで追加された行を分けて追跡できる。
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

一時SQLiteと偽のJV-Link実行境界で、初回欠損をpendingにする規則、全10競馬場、DataSpec別差分、
年選択、ロック、別runtime拒否、外部追加の取り込み、再実行、火曜日を特別扱い
しない失敗分類を検証する。実機の成功・正常空応答・メンテナンス失敗の判定は、
一次仕様として [JRA-VANのエラーコード一覧](https://developer.jra-van.jp/t/topic/822) を参照し、
実機のプロセス成功と空RT表を模したテストで`jvopen_no_data`の分類を検証する。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-10-09 | Accepted | 作成 |
| 2026-11-21 | Accepted | Amendment 1: 確定の発表がない別モードの行を取得済みとせず、確定の行のない行だけがある組の欠損の確認を受け付ける（#66） |
| 2026-11-24 | Accepted | Amendment 2: `last_year`の延長時に新しい年を`pending`で台帳へ加え、`policy_hash`を移す（#111） |
