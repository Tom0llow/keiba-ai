# ADR-046: 実購入額を台帳に記録し、当日の購入案の上限を実購入額の累計で決める

- Status: Accepted
- Date: 2026-11-18
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #56、Refs #57・#36・#81
- Supersedes: N/A（ADR-045の決定4の最後の項（年間の残りは常に`annual_budget_yen`）・決定4の待ちと保留の理由・決定5の
  format_version・`decision.outcome`・stdoutのキーを改める）
- Superseded by: N/A

---

## Context

SPEC-05・06・08は、1レース5,000円・暦年100,000円の上限を実際の購入額の累計で判定し、提案額と実購入額を区別し、実購入額が
把握できず上限を確認できなければ購入を提案しないことを求める。ADR-009も「運用では記録した実購入額を用い、…実購入額が把握できず
上限を確認できない場合は購入を提案しない」と定める。

ADR-045の`model propose-bets-live`は、提示額を常に0円とし、方策の参考額（`reference_stake_yen`）をそのレースだけの上限で縮小する。
年間の残りは常に`annual_budget_yen`で、実購入額を記録する仕組みはない。

GATE 1の前に人間が決めた（2026-11-18）:

1. 記録は新しいCLIが検証して追記するJSON Linesの台帳とする（人は通常は手で編集しない）。
2. 「実購入額がわからない」は確認時刻で判定する。台帳に「ここまで記録済み」の確認の行を持たせ、最新の確認時刻が「そのレースより
   前に発走する当日の重賞の発売締切」以後（そのような重賞がなければ当日0時（JST）以後）でなければ、そのレースは保留する。
3. 年間100,000円の累計には、重賞以外やシステムが提案していないレースを含むすべての馬券を数える。

提示額はADR-045により常に0円なので、SPEC-05・06は既に満たされている。この決定は参考額の上限を実購入額で決め、実際の購入を
始めるときの上限の仕組みを用意する。

## Decision

1. **台帳`purchase_ledger` format_version 1**: ASCIIのJSON Linesで、各行はキーを並べ替えたJSONオブジェクトと`\n`である。
   各行は、PythonのJSONの既定の書き方（`json.dumps(…, sort_keys=True, ensure_ascii=True)`）と1文字も違わない形でなければ
   ならない: 区切りは`, `と`: `（コロンとカンマの後に空白1つ）、それ以外の空白なし、数値と文字列は既定の書き方。1行目は
   見出し`{"format": "purchase_ledger", "format_version": 1, "kind": "header"}`、以後の行は購入（`kind`・`race_id`・`bet_type`・
   `selection`・`stake_yen`・`recorded_at`）か確認（`kind`・`recorded_at`）である。
   - `race_id`は16桁（実在する日付・競馬場`01`〜`10`・回次と日次`01`以上・レース番号`01`〜`12`）。`bet_type`は`win`・`place`・
     `bracket_quinella`・`quinella`・`quinella_place`・`exacta`・`trio`・`trifecta`。`selection`は2桁の番号（馬番`01`〜`18`、
     枠番`01`〜`08`）を`-`でつなぎ、数と順序は券種の規則に従う。`stake_yen`は100の正の倍数。`recorded_at`はタイムゾーン付きで、
     行の順に減らない。
   - 確認の行は「この時刻までの購入はすべて台帳にある」という人の宣言である。空行・`\r`・BOM・NaN・重複キー・余分なキー・
     `\n`で終わらない最後の行は不正とする。
   - レースの使用額は同じ`race_id`の`stake_yen`の和、年間の使用額は開催日（`race_id`の先頭8桁）の年が同じ全レースの和とする
     （券種・重賞かどうかを問わず、年間の使用額はそのレースの使用額を含む）。払戻・返還は記録せず、使用額を減らさない。
2. **記録のCLI `model record-purchases`**（`--ledger`・`--bet <race_id>:<bet_type>:<selection>:<stake_yen>`（0回以上）・`--create`）:
   時計を1回読み、その時刻で購入の行と最後に1つの確認の行を追記する。`--bet`なしは確認の行だけを足す。台帳は`--create`のときだけ
   排他的に作り、既存の台帳は読んだバイト列と置換の直前の内容が同じときだけ、一時ファイルと`os.replace`で原子的に置き換える
   （Windowsの`PermissionError`は短く再試行する）。不正な台帳・入力、途中の変更、シンボリックリンク、時計の巻戻りでは何も書かない。
   stdoutに1行のJSON（`appended`・`confirmed_at`・`ledger_sha256`・今回のレースと年の累計）、上限を超えた累計はstderrに`warning:`を
   出す（記録は拒否しない）。台帳を書くのはこのCLIだけで、同時に1つだけ実行する（読み直しと置換の間は排他しないため、
   2つの実行が重なると一方の追記が失われうる）。年の途中で台帳を作るときは、その年の既存の購入も同時に記録する。
3. **方策の上限**: `decide_races`に任意の`annual_spent_yen`（年→円）と`race_spent_yen`（`race_id`→円）を加え、各レースの上限を
   `min(race_budget_yen − レースの使用額, annual_budget_yen − 年の使用額)`とする。省略時は今と同じで、バックテストは変わらない。
4. **当日の購入案**（ADR-045決定4を改める）: `model propose-bets-live`は必須の`--ledger`を受け取り、起動時に台帳を読んで検査する
   （ない・不正・シンボリックリンク・他の入出力の中なら`--output`を作らずに終了コード1）。各重賞は、予測が公開され、かつ台帳を
   1回読んで検査に通り最新の確認時刻が要求時刻以上のときに計算する。要求時刻は、出馬表から発走時刻がわかる当日の重賞
   （頭数で保留した重賞を含む）のうちそのレースより前に発走するものの発売締切と、当日0時（JST）の遅い方である。条件を満たさない
   間は発売締切まで待ち、締切を過ぎたら`ledger_unavailable`・`ledger_invalid`・`ledger_unconfirmed`で保留する（予測が未公開なら
   今と同じ`prediction_not_published`）。計算は、条件を満たした読込の台帳をそのまま使う。
5. **出力**（ADR-045決定5を改める）: `ev_race_proposal`をformat_version 2とし、`ledger`（台帳のSHA-256・最新の確認時刻・要求時刻。
   パスは入れない）と`budget`（レースと年の使用額・残り（0未満は0）・`cap_yen`）を加える。`decision.outcome`と`decision.scaled`は
   方策の判定を写し、`reference_bets`・`no_eligible_bet`に`budget_exhausted`を加える（要求額が正の買い目は参考額0円で残す）。
   提示額`stake_yen`は常に0円のままである。stdoutの行に`race_remaining_yen`・`annual_remaining_yen`（`proposed`だけ整数）を加える。
6. **配置**: 台帳の形式・検査・集計は`models/betting/purchase_ledger.py`（標準ライブラリだけ、I/Oなし）、ファイルの排他的な作成と
   確認付きの原子的な置換は`data/storage/file_replacer.py`、記録のCLIは`cli/purchase_ledger.py`（他のCLIをimportしない）。

## Rationale

- CLIで検証して追記すると、書式の誤りが当日の全レースの保留につながらない。追記だけの台帳は、記録の順序と確認の時刻を残す。
- 確認時刻を要求すると、前の重賞を買った後の記録漏れを検知できる。人の宣言に頼るが、システムは人の購入を知る手段を持たない。
- 判定を方策に渡す使用額だけで行うと、参考額はバックテストと同じ縮小の規則になる。
- `published`で読んだ台帳を計算に使うと、待ちと計算の間の一時的な読込の失敗でレースが保留のまま確定しない。

## Consequences

### Positive

- 参考額が実購入額の残りの枠を超えない。購入を始めるときに同じ仕組みで上限を守れる。
- 購入案に台帳のhashと残りの枠が記録され、事後に照合できる。

### Negative

- 当日の手順に記録と確認が増える。重賞の間隔が短い日は、前の重賞の締切から後の重賞の締切までに記録・確認する必要がある。
- 確認が間に合わないレースは保留され、確率・期待値の記録も残らない。
- 記録しなかった購入（他の端末・窓口）は検知できない。誤記は手で直すしかない。
- 暦年をレースの開催日で数えるため、前日発売で年をまたぐ購入は購入日と違う年に数える。

### Neutral / Follow-on effects

- `plan_race_day`は発走時刻のわかる重賞の一覧も返す（`predict-pl-live`は使わない）。
- 出馬表の保留などで発走時刻がわからない重賞は、要求時刻の計算に含まれない。

## Alternatives Considered

### Option A: 人が手で編集するCSV

Summary: 人がCSVに行を書き、購入案のCLIが読むたびに検査する。

Advantages: CLIが増えない。

Disadvantages: 書式の誤りで当日の購入案が全部保留になりうる。

Reason not selected: GATE 1の前に人間がCLIの追記を選んだ。

### Option B: 台帳の存在と検査だけ

Summary: 台帳があり全行が検査に通れば完全とみなす。

Advantages: 手間が最小。

Disadvantages: 記録漏れを検知できない。

Reason not selected: 人間が確認時刻を選んだ。

### Option C: 提案したレースごとの記録

Summary: その年に購入案を出した各重賞に、購入額の記録（0円を含む）がなければ保留する。

Advantages: 提案ごとに記録の有無が厳密にわかる。

Disadvantages: 0円の提示の今は、全重賞に「買っていない」を記録する必要がある。

Reason not selected: 人間が確認時刻を選んだ。

## Implementation Notes

- `models/betting/purchase_ledger.py`（新規）、`data/storage/file_replacer.py`（新規）、`cli/purchase_ledger.py`（新規）。
- `models/betting/policy.py`: `decide_races`の任意引数2つ。`models/experiments/bet_proposal.py`: 台帳と要求時刻の引数、format_version 2。
- `cli/pl_prediction.py`: `plan_race_day`の3つ目の戻り値、`--ledger`、監視の準備と保留の理由、stdoutのキー。

## Validation

- 単体テスト: 台帳の形式の各規則、追記、`parse_bet`、要求時刻、方策の使用額（省略時の一致・2種類の上限・負の上限・引数の検査）、
  置換の補助（排他の作成・途中の変更・再試行・Ctrl+C）、購入案の`budget`・`ledger`と参考額の方策との一致・`budget_exhausted`。
- 統合テスト: `record-purchases`の作成・追記・拒否・警告・Ctrl+C・help、`propose-bets-live`の実購入額による縮小、確認を待って
  計算すること・締切での保留・当日0時の要求、起動後の台帳の破損と修復、待ちで読んだ台帳の使用、起動時の拒否、`plan_race_day`の
  発走時刻。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 確認が締切に間に合わない | そのレースの購入案がない | 手順書に記録と確認の時機を書く。提示額は0円なので損失はない |
| 記録漏れ | 上限の判定が甘くなる | 確認は人の宣言とし、重賞以外の購入も記録する手順にする |
| 台帳の誤記 | 使用額の誤り | 手で直して検査に通す。訂正のCLIは別のIssueで検討する |
| 時計の巻戻り | 記録できない | 同じPCの時計を前提とし、追いつくまで待つ |

## Security / Privacy Impact

台帳は個人の購入履歴である。口座・会員番号などの項目は持たず、git対象外の`data/`の下かリポジトリの外に置く。テストは合成の
台帳だけを使い、文書に実際の購入額を載せない。購入案の出力に台帳のパスを入れない。外部への送信と自動購入はしない。

## Operational Impact

開催日より前に`model record-purchases --create`で台帳を作る。当日は最初の重賞の前と、各重賞の発売締切の後・次の重賞の発売締切
までに購入を記録するか確認し、`model propose-bets-live`に`--ledger`を渡す（`docs/race-day-operation.md`）。

## Migration / Rollback

### Migration

`model propose-bets-live`は`--ledger`が必須になる。台帳を作ってから起動する。format_version 1の購入案は読み替えない。

### Rollback

2つのCLIの変更と新しいモジュールを戻し、`decide_races`の引数を除けば戻る。台帳のファイルは残しても害はない。

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `docs/rules/architecture.md`
- [x] `README.md`
- [x] `docs/race-day-operation.md`
- [x] `docs/experiments/ev-betting-backtest.md`
- [x] `docs/specification.md`
- [x] ADR-045のヘッダー・Follow-up・Decision History

## Follow-up Actions

- [ ] 台帳の誤記を訂正・取消する手段（人間の確認の後にIssueとする）。

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-18 | Accepted | GATE 1で人間が記録の方法・確認時刻・年間の範囲を決めた |
