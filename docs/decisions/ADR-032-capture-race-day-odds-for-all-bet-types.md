# ADR-032: 開催日の発走前複数時点で全券種の速報オッズをarchiveする

- Status: Accepted
- Date: 2026-11-08
- Decision Owners: Repository maintainers
- Related Issues/PRs: #27, #29（Amendment 1）
- Supersedes: N/A
- Superseded by: N/A

---

## Context

過去分の時系列オッズを取得できるDataSpecは`0B41`（単勝・複勝・枠連）と`0B42`（馬連）だけである
（[ADR-007](ADR-007-archive-realtime-odds-for-training-and-inference.md)）。ワイド・馬単・3連複・3連単は
確定オッズしか保存されておらず、発走前のオッズは発走前に取得しない限り得られない。
単勝オッズからこれらを推定する方法は、期待値の判断に使える精度に達しなかった
（[推定誤差の調査](../experiments/exotic-odds-estimation-error.md)）。

2026-11-08にJVLinkToSQLiteで`0B33`〜`0B36`を1回実行し、次を確認した。

- `0B33`→`RT_O3_ODDS_WIDE`、`0B34`→`RT_O4_ODDS_UMATAN`は1表で、`HappyoTime`を持つ。
- `0B35`→`RT_O5_ODDS_SANREN`と子表`RT_O5_OddsSanrenInfo`、`0B36`→`RT_O6_ODDS_SANRENTAN`と子表
  `RT_O6_OddsSanrentanInfo`に分かれる。子表は`HappyoTime`と`headDataKubun`を持たない。
- 全列の宣言型は`TEXT`である。

historical-oddsは`ARCHIVE_O1_ODDS_TANFUKUWAKU`/`ARCHIVE_O2_ODDS_UMAREN`の行の有無を`0B41`/`0B42`の
取得済み判定に使う。また[ADR-013](ADR-013-manual-yearly-odds-acquisition.md)は、未確定の要求が
`running`の間は新しいJV-Linkの起動を拒否し、空の応答は`JVOpen/JVRTOpen=-1`の証跡がある場合だけ
無データとすることを定める。

---

## Decision

1. `--retrieve --mode=race-day-odds --date YYYY-MM-DD`を追加する。指定日の`NL_RA_RACE`のうち中央01〜10場、
   `headDataKubun`が`0`/`9`以外、有効な`HassoTime`のレースについて、`HassoTime`（JST）から
   `[race_day_odds].offsets_minutes`の各分前に、`0B31`〜`0B36`を1回のJVLinkToSQLite実行で取得する。
   予定時刻を`late_tolerance_seconds`より過ぎた取得は実行せず`skipped_late`とする。
   発走時刻の変更には追従しない。
2. 取得した行は、既存のarchiveと分けた次の表へ保存する。
   - `0B31`〜`0B34`と`0B35`/`0B36`の親表: `ARCHIVE_CAPTURE_O1_ODDS_TANFUKUWAKU`、
     `ARCHIVE_CAPTURE_O2_ODDS_UMAREN`、`ARCHIVE_CAPTURE_O3_ODDS_WIDE`、`ARCHIVE_CAPTURE_O4_ODDS_UMATAN`、
     `ARCHIVE_CAPTURE_O5_ODDS_SANREN`、`ARCHIVE_CAPTURE_O6_ODDS_SANRENTAN`。staging表と同じ列名・列順とし、
     全行で重複除去する（ADR-007と同じ）。
   - 子表: `ARCHIVE_CAPTURE_O5_OddsSanrenInfo`、`ARCHIVE_CAPTURE_O6_OddsSanrentanInfo`。子表の全列の後ろに、
     親表の唯一の行の`headDataKubun`と`HappyoTime`を加え、全列を`TEXT`とする。これはADR-007の
     「同じ列名と列順」の例外である。
   - 既存の`ARCHIVE_O1_ODDS_TANFUKUWAKU`/`ARCHIVE_O2_ODDS_UMAREN`へは書き込まない。
3. 取得×DataSpecごとに1行を`ARCHIVE_CAPTURE_LOG`（全列`TEXT`）へ記録する。予定・開始・完了のUTC時計、
   状態（`running`/`archived`/`no_data`/`failed`/`skipped_late`/`interrupted`）、理由、process終了コード、
   API名と戻り値、親の`headDataKubun`/`HappyoTime`、観測行数と挿入行数を持つ。
4. 取得結果の分類はADR-013と同じとする。fatal specは`failed/jvlink_error`、空のstagingは
   `no_data_specs`の証跡がある場合だけ`no_data/jvopen_no_data`、証跡がなければ
   `failed/empty_response_unverified`とする。レース不一致、同一レースの複数行、子表のレース不一致、
   archiveのschema不一致、親表が空で子表だけに行がある場合（`orphan_child_rows`）は、
   そのDataSpecだけ`failed`とする。
5. 同じレース・`headDataKubun`・`HappyoTime`の行がarchiveにあり、その行集合が今回と異なる場合は
   `failed/happyo_conflict`とし、archiveへ入れない。親表の版が既にarchiveにある場合、子表の行集合は
   空の場合も含めて一致しなければならない。重複除去の比較は、archiveのうち対象レースの行に限る。
6. 中断と復旧はADR-013の順序に合わせる。取得のたびに、ロック内で`running`の記録を確定してから、
   既存のstaging行を検証付きで退避して空にし、実行する。失敗でstagingに行が残れば退避してから空にする。
   `running`の確定後にraw DBへの書込みが失敗した場合は、`running`とstagingを残して処理を止める。
   `ARCHIVE_CAPTURE_LOG`に`running`の行がある間、`AcquisitionLock`は全取得モードで取得を拒否する。
   既存の`allow_unresolved=True`でも拒否し、race-day-oddsの起動時復旧と、Amendment 1の`--recover`だけが解除できる。
   起動時復旧は、runner停止を確認し、stagingを退避・初期化して、その行を`interrupted`にする。
7. 設定は`configs/jvlink.toml`の任意section `[race_day_odds]`に置く。DataSpecは`0B31`〜`0B36`の6種ちょうどとする。

### Amendment 1: 実行タイムアウト・実行XMLの起動時検証・復旧専用の手段（2026-11-11）

- 2026-11-11に人間の承認を受けてこのADRへ追加した（ADRのStatusはAcceptedのまま。Decision Historyを参照）。Issue #29。
- `[race_day_odds]`に必須キー`execution_timeout_seconds`（正の整数、秒）を加える。リポジトリの設定値は120秒とする。
  race-day-oddsは、この値をタイムアウトとする専用のJVLinkToSQLite runnerで実行する。他の取得モードのrunnerとタイムアウトは変えない。
  タイムアウトはJV-Linkの失敗と同じ`failed/jvlink_error`として記録し、stagingに行があれば退避してから初期化し、次の取得へ進む。
  120秒は実測の前の値であり、運用で計測して見直す。タイムアウトが戻るのは、killしたJVLinkToSQLiteの出力を他のプロセスが
  握っていない場合である（Risks参照）。
- 起動時復旧と取得予定の計画の後、最初の待機の前に、最初の予定のレースキーで実行XMLを一度生成し、実時間更新と`0B31`〜`0B36`が
  有効で、各`JVRaceKey`がそのレースの値であることを検証する。失敗すれば取得記録に何も書かずに終了する
  （CLIはstderrに`race-day-odds setup failed: ...`を1行、stdoutに要約のJSONを出し、終了コード1）。
  seedのファイル自体がない場合は、従来どおりretrieverの構築時に例外で終わる（`--recover`も同じ）。どちらも何も書かない。
- 各取得では、実行XMLの生成を`running`の確定の前に行う。生成に失敗した取得は記録せずに`failed/capture_not_recorded`と報告し、
  次の取得へ進む。Decision 6の`running`確定後の書込み失敗で止まる挙動は変えない。
- `--retrieve --mode=race-day-odds --recover`は、起動時復旧と同じ手順だけを行って`{"interrupted":N}`を出力し、取得はしない。
  `--date`やレースのoptionとは併用できない。ロックを取れない場合とrunnerが動いている場合は、stderrに
  `race-day-odds recovery failed: ...`を1行出して終了コード1とする。常駐中のrace-day-oddsを止めてから実行する。
- 取得記録の`running`が残っているときの他モードの拒否メッセージは、`--retrieve --mode=race-day-odds --recover`を示す。

---

## Rationale

- 発走前の実オッズは後から取り戻せないため、取得を早く始めることを優先した。
- `0B31`/`0B32`の速報snapshotを既存のO1/O2 archiveへ混ぜると、historical-oddsが時系列を取得済みと誤認し、
  発売開始以降の時系列のbackfillを省略する。別表にすれば既存の判定を変えずに済む。
- 子表には時点の列がなく、全行の重複除去だけでは別時点の同じ組合せを区別できない。
  親表の`headDataKubun`と`HappyoTime`を加えることで、元の列の値を保ったまま時点を識別できる。
- 取得記録に実測時計とAPI結果を残せば、後から「いつの時点で利用できたオッズか」を確認できる。
- 全列`TEXT`は、既存の完全snapshotが全string契約で、`TEXT`/`DATETIME`以外の宣言型を拒否するためである。

---

## Consequences

### Positive

- ワイド・馬単・3連複・3連単を含む全券種の発走前オッズを、時点と取得証跡付きで蓄積できる。
- 既存のhistorical-odds、realtime、archiveの挙動と取得済み判定は変わらない。
- 中断後も、stagingの行を消す前に検証付きで退避するため、取得した行を失わない。

### Negative

- 3連単の子表は1取得で最大4,896行となり、1開催日で最大約70万行増える。
- `running`の記録が残ると、`--recover`またはrace-day-oddsの起動時復旧で復旧するまで全取得モードが止まる。
- 同じ`HappyoTime`の訂正版はarchiveに入らず、退避だけされる。

### Neutral / Follow-on effects

- 新しい表は、次回の完全snapshot再生成で同名の全string Parquetとして出力される。取得のたびには公開しない。
- 特徴量・datamart・期待値計算への接続は、この決定の範囲外である。

---

## Alternatives Considered

### Option A: 単勝の時系列から連勝式のオッズを推定する

Summary:

Harville型・Benter補正型で単勝オッズから組合せ確率を作り、推定オッズとする。

Advantages:

- 新しい取得が不要で、過去分にも適用できる。

Disadvantages:

- 2024〜2025年の評価で、締切時点の単勝から確定オッズを推定した誤差の中央値は3連単56.5%、ワイド32.8%であった。

Reason not selected:

期待値の判断に使える精度に達しないため。

### Option B: 既存の`ARCHIVE_O1`/`ARCHIVE_O2`へ`0B31`/`0B32`も保存する

Summary:

realtimeと同じく既存のO1/O2 archiveを共有する。

Advantages:

- 表の数が増えない。

Disadvantages:

- historical-oddsの取得済み判定が速報snapshotの有無で変わり、時系列のbackfillが省略される。

Reason not selected:

既存の取得計画を壊すため。

### Option C: 全archive行に取得IDを持たせる

Summary:

取得ごとに行を区別して、同じ`HappyoTime`の訂正版も保存する。

Advantages:

- 各取得時点の行集合を完全に復元できる。

Disadvantages:

- 同じ発表の再取得でも行が増え、子表の容量が取得回数に比例して増える。

Reason not selected:

訂正版の保存は要件ではなく、`happyo_conflict`として検出・退避すれば足りるため。

---

## Implementation Notes

- 取得計画・遅延判定・分類は`jra_van_retriever/workflows/race_day_odds_plan.py`の純粋関数とする。
- 指定日の`NL_RA_RACE`の読取は`progress/raw_observation.py`、archiveと取得記録は`acquisition/odds_archive.py`、
  未解決の検査は`acquisition/acquisition_lock.py`、取得ループは`workflows/race_day_odds.py`が所有する。
- 当日の`NL_RA_RACE`は、事前に`latest`で取得しておく必要がある。

---

## Validation

- tmp SQLiteで、事前確認と同じ列構成のstagingからのarchive、重複除去、時点の区別、`happyo_conflict`、
  分類、取得記録、完全snapshotの再生成を検証する。
- 偽のrunnerと時計で、待機・順序・遅延・JV-Link失敗後の続行・書込み失敗時の停止・起動時復旧と
  ロックの拒否・解除を検証する。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| JVLinkToSQLiteがstagingを作り直すか追記するかが繰り返し実行で未確認 | 前回の行を今回の取得と誤認する | 取得前の退避・初期化と同一レース1行の検査 |
| 発走前の中間オッズで子表が全組合せを返すか未確認 | 一部の組合せが欠ける | `child_observed_rows`で事後に確認する |
| 発走時刻の変更に追従しない | 変更レースの取得時点がずれる | 基準時刻と実測時計を記録し、事後に補正する |
| 常駐中のスリープ・認証切れ・ネットワーク断 | 取得が欠ける | 失敗を記録し、復旧は行わない |
| JVLinkToSQLiteが応答しない | その時点の取得が欠ける | `execution_timeout_seconds`で打ち切り、`failed/jvlink_error`として次の取得へ進む（Amendment 1） |
| タイムアウトでkillした後にJV-Linkの別のプロセスが残るかが未確認 | 次の取得のstagingに前の行が混ざる | 取得前の退避・初期化と同一レース1行の検査で、archiveには入れない |
| TTYでない実行で、killした後もJVLinkToSQLiteの出力を握る別のプロセスが残る | 出力の読取が終わらず、タイムアウトが戻らずに常駐が止まる | 未確認。kill後の待機に上限を設けるか、プロセスツリーごと終了するかは後続課題とする |
| 完全なParquet出力との重なり | 書込みが`database is locked`で失敗し、取得が欠けるか当日の取得が止まる | 運用で重ねない。出力側との排他は後続課題とする |
| 中断で残ったロールバックジャーナル | 読取専用の接続では巻き戻せない | 取得記録の検査は読み書き接続で開き、SQLiteに巻き戻させる |

---

## Security / Privacy Impact

セキュリティやプライバシーへの重大な影響はない。認証情報は読まず、取得記録にも残さない。

---

## Operational Impact

- 開催日に`latest`を実行してから、`race-day-odds`を起動しておく必要がある。
- race-day-oddsの実行中に、`latest`や`preprocess rebuild`による完全なParquet出力を重ねてはならない。
  raw DBはロールバックジャーナル方式のため、出力の長い読取取引の間は取得の書込みが失敗する。
- 再起動すると、取得記録に終了状態がある（レース、分前）の組は実行も記録もし直さない。
- raw DBの容量が開催日ごとに増える。
- 中断後は、`--retrieve --mode=race-day-odds --recover`、またはrace-day-oddsの起動時復旧で解消するまで他の取得モードが止まる。
  `--recover`は、常駐中のrace-day-oddsを止めてから実行する。

---

## Migration / Rollback

### Migration

既存の表は変更しない。新しい表は最初の取得で作成される。

### Rollback

`[race_day_odds]`を削除すればコマンドは使えなくなる。作成済みの`ARCHIVE_CAPTURE_*`表は残る。
`running`の行が残っている場合は、先に`--retrieve --mode=race-day-odds --recover`で解消する。

---

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [ ] `docs/rules/architecture.md`
- [ ] `AGENTS.md`
- [x] `README.md`
- [x] APIとユーザー向けの文書（`docs/jra-van-acquisition-design.md`、`docs/table-definition/`）
- [ ] 運用文書・運用手順書

---

## Follow-up Actions

- [ ] 発走時刻の変更情報を取得して、取得予定を更新する。
- [ ] 蓄積したオッズを特徴量と期待値の判断へ接続する。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-08 | Accepted | 開催日の発走前複数時点で全券種の速報オッズをarchiveすることを決定 |
| 2026-11-11 | Accepted | Amendment 1: 実行タイムアウト、実行XMLの起動時検証と`running`確定前の生成、`--recover`を追加 |
