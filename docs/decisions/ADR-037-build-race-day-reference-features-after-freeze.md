# ADR-037: 当日のレースごとに、freeze後の時系列オッズで参考特徴量を構築する

- Status: Accepted
- Date: 2026-11-12
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #37、Refs #57・#52・#53・#54・#30・#31・#46・#55・#59・#61・#64・#66・#67
- Supersedes: ADR-036のDecision 3の形式番号（format_version 1）と、Option B（2段階の構築）を採用しない判断のみ
- Superseded by: N/A

---

## Context

ADR-036のラベルなしの構築は、固定した完全snapshotの`ARCHIVE_O1`/`ARCHIVE_O2`から対象日の市場を読む。
完全snapshotには作成時刻がないため、freezeより後の発表がO1にないレースを`market_not_observed_after_freeze`で保留する。

実データで0B41の発表の間隔を調べた。2025-11-30・12-27・12-28の中央72レースすべてで、発走11分前より後の
`headDataKubun="1"`の発表は、発走11分前・6分前・1分前だけだった。

- freezeの時点（発走5分前）の値は、常に発走6分前の発表である。
- freezeより後で最初の発表は発走1分前で、JRAの発売締切（発走2分前）より後になる。
  そのため、「freezeより後の発表がある」という完全性の根拠は、締切までに得られない。

また、1日分の構築は全履歴をたどり直すため、実データで207.7秒かかった。freezeから締切までの約180秒には収まらない。

---

## Decision

1. **完全性の根拠を取得の開始時刻にする。** 0B41/0B42の時系列は、取得の時点までの全発表を含む。
   そのため、freeze以降に開始した取得の行は、freeze以前の全発表を含む。
   - `PreparedTargets.calculate(..., observed_through=...)`に取得の開始時刻を渡す。
     それがfreeze_at以上なら、freezeより後の発表がなくても計算する。
   - `observed_through=None`は、従来どおり完全snapshotの経路（freezeより後の発表を要求する）である。
   - 漏洩の防止は従来どおり、`latest_o1`（その時点以前の発表だけを選ぶ）と`shared_context`（freezeより後に使える証跡を拒否する）が担う。
     開始時刻の検査は、市場が古くないこと（完全性）の確認である。
2. **履歴は朝に一度だけたどり、レースごとに市場を加えて計算する。**
   `ReferenceDatamartBuilder.prepare_targets`は、対象年について市場の前までを行う。
   - 前までの処理: 履歴の索引、調教、出馬表の血統の登録、日の見方。
   - `PreparedTargets.calculate`は1レースを計算する。順序と、一部だけを計算することは自由である。
   - 状態は永続化せず、1本の常駐プロセスのメモリに保つ。
   - ラベルなしの一括の`add_year`も同じ経路を通るので、出力は変わらない。
3. **当日の取得はrace-day-oddsの1工程とする（ADR-032 Amendment 2）。**
   - `[race_day_odds].prediction_offset_minutes`（3〜5、リポジトリの値は5＝freeze）の時刻に、各レースの0B41/0B42を取得する。
     取得の前に、JVLinkToSQLiteが動いていないことを確かめる。動いていれば、その取得は記録せずに飛ばす。
   - 取得した時系列を`ARCHIVE_O1`/`ARCHIVE_O2`へ保存する。
   - 取得が終了状態になるたびに、ロックを持ったまま、そのレースのO1/O2と取得記録をレース別のParquetへ公開する。
4. **常駐CLI `datamart build-reference-prediction-live`。**
   - 朝に準備した後、freezeの早い順に、レース別のversionを`--poll-interval-seconds`（既定5秒）ごとに読む。
   - 次の条件をすべて満たす取得があれば、そのレースを計算して`<output>/<race_id>/`へ公開する。
     - 同じ`capture_id`の0B41・0B42がともに`archived`。
     - 予定の発走時刻が一致する。
     - 開始がfreeze以降。
   - 取得の失敗は、すぐに保留する（`race_day_fetch_<status>: <reason>`）。freezeから`--deadline-seconds`（既定150秒、180秒以下）を
     過ぎても取得が公開されないレースも保留する（`race_day_fetch_not_published`）。条件を満たす取得が2つ以上あれば保留する
     （`ambiguous_race_day_fetch`）。締切の判断は読込の後に行うので、`--deadline-seconds`を過ぎてから発売締切（freezeの
     180秒後）までに見つけた取得は計算する。発売締切より後に初めて見つけた取得は、計算せずに保留する
     （`race_day_sales_closed`。起動が遅れた場合・再起動した場合も同じ）。
   - JV-Linkの実行とraw DBへのアクセスはしない。レースのCURRENTは1回の読込で1度だけ開く。
     race-day-oddsのCURRENTの置換が、読込中のためWindowsで拒否された場合は、短く再試行する（`publish_pointer`）。
5. **保存形式`reference_prediction_features` format_version 2。** manifest・Parquetのmetadata・heldの形式番号を2にし、
   manifestに必須の`market_source`を加える。
   - 値は、`{"kind": "complete_snapshot"}`（一括の構築）か、`race_day_prediction_fetch`（常駐CLI）のどちらかである。
   - `race_day_prediction_fetch`は、次を記録する: レース、発走・freeze、`capture_id`、DataSpec、取得の開始時刻、
     レース別snapshotのversion名、読んだ3表のSHA-256。
   - 読込APIは、開始時刻がfreeze以上であることと、出力のレースが`market_source`の1レースだけであることを検証する。
   - format_version 1の出力は読込を拒否する。1の出力は実験の記録だけで、利用者はまだいなかった。
   - 学習用datamart（format_version 1）は変えない。

---

## Rationale

- 学習と同じDataSpec・同じarchive表・同じ選択規則を使うので、当日の値は学習の値と構造上一致する。
- 発表の間隔が5分であることは実データで確かめた。開始時刻を根拠にすれば、締切前に計算できる。
- 取得をrace-day-oddsの1工程にすると、ロックを取る主体は1つになる。
  また、既存の時計・待機・タイムアウト・起動時の設定の検証・`running`の記録と復旧を使える。
  別のプロセスが取得すると、race-day-oddsの取得とロックを取り合い、取れなかった側の取得が失われる。
- 取得記録をレース別のParquetに含めるので、常駐CLIはraw DBを読まずに、市場と取得の証跡を1つの固定versionから読める（ADR-008）。

---

## Consequences

### Positive

- 当日の発走前に、学習と同じ値の特徴量をレースごとに作れる。
- 予測の出力が、使った市場の出典・取得時刻・ファイルのSHA-256を持つ。

### Negative

- 当日に取得したレースは、archiveに行があるため、historical-oddsが取得済みとみなし、発走後の発表をbackfillしない（#66）。
  freezeより後に取得できたレースは学習の値に影響しない。一方、取得に失敗したレースの途中までの時系列は残る。
- 常駐プロセスは、朝から最終レースまで1日分の構築のメモリを持ち続ける。
- 予測の取得が長引くと、同じ時刻の0B31〜0B36の取得が`skipped_late`になりうる。他のレースの取得が長引くと、予測の取得自体が`skipped_late`になりうる。

### Neutral / Follow-on effects

- `--mode=realtime`の出力（レース別のParquet）にも、取得記録の表が加わる。
- 常駐CLIでは、manifestの`snapshot`は完全snapshotのRA/SE/HC/WC/UMだけを固定し、`ARCHIVE_O1`/`O2`を含まない。
  市場の出典は`market_source`である。`freshness`は対象日の値で、全レースで同じである。

---

## Alternatives Considered

### Option A: race-day-oddsの0B31/0B32（`ARCHIVE_CAPTURE_*`）を使う

Summary:

既に取得している速報のsnapshotを、取得の時刻から各時点の値として使う。

Advantages:

- 新しい取得が要らない。

Disadvantages:

- 学習（0B41）と出典が異なり、値の一致は構造上保証されない。
- 発走15分前の時点の取得がない。
- 配信の遅れで、学習と値が食い違う余地が残る。
- 特徴量の入力にするには、完全なParquet出力をやり直す必要がある（#30）。

Reason not selected:

人間の決定（2026-11-11）により、学習と同じ0B41/0B42を使う。

### Option B: 常駐CLI自身がfreeze後に`--mode=realtime`で取得する

Summary:

特徴量のプロセスが、各レースのfreeze後にJV-Linkを実行する。

Advantages:

- race-day-oddsを変えない。

Disadvantages:

- race-day-oddsとロックを取り合い、取れなかった側の取得は再試行されずに失われる。
- 4.6GBのプロセスがJV-Linkを実行し、TTYでない実行のタイムアウトの問題（#59）にも触れる。

Reason not selected:

ロックを取る主体を1つにするため。

### Option C: 状態を永続化する2段階の構築（ADR-036 Option B）

Summary:

朝の履歴の状態をファイルに保存し、freezeの後に別のプロセスで市場だけを加える。

Advantages:

- 常駐プロセスが要らない。

Disadvantages:

- ビルダーの状態の永続化という新しい契約が要る。

Reason not selected:

1本の常駐プロセスでメモリに保てば、新しい永続形式なしに同じ計算を共有できるため。

---

## Implementation Notes

- ビルダー: `models/serialization/reference_datamart.py`（`prepare_targets`・`PreparedTargets`・`TargetSchedule`・`TargetResult`）。
- 保存と読込: `make_datamart/tables/reference.py`（`_Layout.format_version`、`market_source`の検証）。
- 取得: `jra_van_retriever/workflows/race_day_odds_plan.py`（kind）・`race_day_odds.py`（予測の取得とpublisher）・
  `acquisition/odds_archive.py`（`_archive_prediction_spec`、stagingの解決、終了済みのキーのkind）・
  `config/profiles.py`・`config/validation.py`。
- 公開: `data/storage/snapshot_builder.py`（`update_race`に取得記録）、`data/storage/snapshot_publisher.py`（CURRENTの置換の再試行）。固定読込: `data/loader/race_version.py`。
- CLI: `cli/reference_datamart.py`（`datamart build-reference-prediction-live`）、`cli/jra_van_retriever.py`（publisherの受け渡し）。

---

## Validation

- fixtureで、`prepare_targets`の後に任意の順序・任意の一部のレースを計算した結果が、一括の構築と一致することを確かめる。
  初出走の馬のいるレースも含める。
- freeze以前の発表だけと開始時刻がfreezeの取得から、freezeより後の発表を含む一括の構築と同じ値になることを確かめる。
- 本物のrace-day-odds（JV-Linkだけ偽物）・`update_race`・常駐CLIを通し、公開した各レースの値が一括の構築と一致すること、
  および`market_source.tables`が公開ファイルのSHA-256と一致することを確かめる。
- 読込APIの`market_source`の拒否、予測の取得の分類・退避・復旧・再開・publisherの失敗、常駐CLIの待機・保留・失敗を確かめる。
- 実データの2025-12-28で、準備の所要時間とメモリ、1レースあたりの計算・公開の所要時間、学習用datamartとの一致を計測した
  （`docs/experiments/reference-prediction-features.md`）。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 当日の0B41/0B42が、発走6分前の発表をfreezeまでに返さない | freezeの値が古い発表になる | 最初の開催日（2026-11-14・15）に、取得記録の`HappyoTime`を人が確かめる（#54） |
| 1回の取得が長い | 計算と予測が締切に間に合わない | `--deadline-seconds`で保留し、#54で所要時間を記録して既定値を見直す |
| `prediction_offset_minutes`と`freeze_offset_seconds`（300）の食い違い | freezeより前に始めた取得は使われず、全レースが保留になる | 設定の範囲を3〜5に限り、READMEに書く |
| 対象日のレースに手動で`--mode=realtime`を実行する | 0B31の行が`ARCHIVE_O1`に混ざり、選ばれる発表が変わりうる | READMEで禁止する |
| PCの時計のずれ | freezeとの比較がずれる | 取得記録と予定は同じPCの時計で、運用で時刻同期を確かめる（#54） |
| 出走取消・発走時刻の変更 | 取消のあるレースは学習と同じく保留。発走時刻の変更には追従しない | #46・#31 |

---

## Security / Privacy Impact

セキュリティやプライバシーへの影響はない。認証情報を読まず、出力にも残さない。

---

## Operational Impact

- 当日の朝に`latest`と完全snapshotの公開を行い、その後にrace-day-oddsと常駐CLIを起動する（順序の詳細は#54）。
- 常駐CLIを途中で再起動すると、`--output`は新しいパスが必要なので、出力先が分かれる。
- race-day-oddsの実行中は、対象日のレースに`--mode=realtime`を実行しない。

---

## Migration / Rollback

### Migration

- 既存のformat_version 1の予測の出力は、`build-reference-prediction`で作り直す。
- 学習用datamartは変わらない。

### Rollback

- `[race_day_odds].prediction_offset_minutes`を削除すれば、race-day-oddsは予測の取得をしなくなる。
- 常駐CLIを使わなければ、ADR-036の一括の構築だけが残る。

---

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `docs/rules/architecture.md`
- [ ] `AGENTS.md`
- [x] `README.md`
- [x] APIとユーザー向けの文書（`docs/table-definition/README.md`、`docs/jra-van-acquisition-design.md`、
  `docs/experiments/reference-prediction-features.md`）
- [ ] 運用文書・運用手順書（#54）

---

## Follow-up Actions

- [ ] 当日の運用手順で、取得・構築・予測の順序と所要時間を定め、最初の開催日に確かめる（#54）。
- [ ] 当日に取得したレースの時系列をhistorical-oddsでbackfillする（#66）。
- [ ] 全券種の当日オッズを期待値判断へ接続する（#67）。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-12 | Accepted | 当日のレースごとに、freeze後に開始した0B41/0B42の取得で参考特徴量を構築することを決定。ADR-036のformat_versionとOption Bの判断を置き換える |
