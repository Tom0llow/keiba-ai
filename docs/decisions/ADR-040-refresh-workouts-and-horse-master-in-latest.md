# ADR-040: 当日のlatestで調教と競走馬マスタも差分取得する

- Status: Accepted
- Date: 2026-11-13
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #61、Refs #57・#54・#30・#51
- Supersedes: N/A
- Superseded by: N/A

---

## Context

当日の予測用の特徴量（ADR-036・037）は、当日の完全snapshotから、出走馬の直近の調教（`NL_HC_HANRO`・`NL_WC_WOOD`）と、
競走馬マスタの親のID（`NL_UM_UMA`の`Ketto3Info0HansyokuNum`・`Ketto3Info4HansyokuNum`）を読む。

- 当日の朝に実行する`--retrieve --mode=latest`は、`[latest]`で`normal_data_specs = ["RACE"]`と速報系だけを取得していた。
  調教（SLOP・WOOD）とマスタ（DIFN）は、`historical-basic`のsetup取得でしか更新されなかった。
- そのため当日のsnapshotでは、直近の調教と新馬の親のIDが欠け、学習時と比べて特徴量が欠ける。ADR-036は、この鮮度を
  manifestの`freshness`に記録するだけにした。2026-11-13の手元のsnapshotでは、調教は2026-10-07、マスタは2026-10-05で止まっていた。
- latestは、永続的なruntime設定（`latest.xml`）を持ち、JVLinkToSQLiteが種別ごとの読込位置をそこへ書き戻す（ADR-006）。
  まだ有効にしたことのない種別の位置は、seedの値（手元では2015-01-01）のままである。そのまま有効にすると、初回に約11年分の
  差分を要求する。

---

## Decision

1. **当日のlatestの取得範囲。** `[latest]`の`normal_data_specs`を`["RACE", "SLOP", "WOOD", "DIFN"]`とする。
   - BLDN（繁殖馬・産駒）とDIFF（旧形式のマスタ）は加えない。今の特徴量は`NL_UM_UMA`の親のIDだけを読み、DIFNがそれを更新する。
     朝の取得を短く保つ（人の決定、2026-11-13）。
2. **読込位置の下限`[latest.normal_start_floors]`。** 種別IDからTOMLのlocal datetimeへの表で、normalの節の読込位置の下限を表す。
   - XMLを作るとき、有効なnormalの種別のうち下限を持つものについて、位置が下限より前なら下限に置き換え、同じか後なら変えない。
     位置を進めるのはJVLinkToSQLiteだけなので、下限は初回の実行だけに効き、何度実行しても同じ結果になる。
   - `[latest]`だけが持てる。他のprofileでの指定、`normal_update = false`との組合せ、`normal_data_specs`にない種別、
     local datetimeでない値は、設定の読込で拒否する。
   - 下限を持つ種別の位置が欠ける・読めない・タイムゾーン付きなら、XMLを書く前に拒否する。既存の`latest.xml`は変わらない。
   - リポジトリの値は、SLOP・WOOD・DIFNとも`2026-10-01T00:00:00`とする。下限は、その種別を最後に取得した
     `historical-basic`のsetupの収録の終わり以前に置く。重なった行はJVLinkToSQLiteが上書きする。
3. **当日の順序。** 当日の朝に`latest`（この取得範囲）を済ませてから、race-day-oddsと当日の特徴量の常駐CLIを起動する。
   race-day-oddsとの排他（#30）と、当日の手順（#54）は、この決定では変えない。

---

## Rationale

- latestの差分取得は、ADR-006の永続的な読込位置の仕組みに乗るので、新しい取得モードを作らずに済む。
- 下限を`max`として扱うと、初回の長い取得を防ぎつつ、以後のJVLinkToSQLiteの位置を壊さない。
- 下限を設定に明示するので、どこから取得したかを設定とADRで追える。

---

## Consequences

### Positive

- 当日のsnapshotで、前日までの調教と新馬の親のIDが欠けにくくなる。

### Negative

- 朝の`latest`の所要時間が延びる。初回は下限から当日までの差分を取るので、さらに長い。
- JV-LinkがSLOP・WOOD・DIFNを通常データとしていつ提供するかは、提供元に依存する。前日の調教が当日の朝に届かなければ、
  鮮度は改善しない（記録は`freshness`に残る）。

### Neutral / Follow-on effects

- `historical-basic`・`historical-odds`・`race-day-odds`・`realtime`のprofileは変わらない。

---

## Alternatives Considered

### Option A: 朝に別のsetup取得を行う

Summary:

latestを変えず、直近の日付からのsetup取得（SLOP・WOOD・DIFN）を一時的なXMLで行うモードを作る。

Advantages:

- 読込位置を持たない。

Disadvantages:

- setupのデータが当日分まで新しいかが分からない。取得モードが増える。

Reason not selected:

人間の決定（2026-11-13）。

### Option B: コードを変えず、人が`latest.xml`の位置を直す

Summary:

`normal_data_specs`に足すだけにし、初回の前に人がruntime設定を手で直す手順をREADMEに書く。

Advantages:

- コードの変更がない。

Disadvantages:

- 手順を忘れると、初回に約11年分を要求する。runtime設定を作り直したときにも同じ危険がある。

Reason not selected:

人間の決定（2026-11-13）。

---

## Implementation Notes

- 設定: `jra_van_retriever/config/profiles.py`（`JVLinkProfile.normal_start_floors`、`_load_profile`）、
  `jra_van_retriever/config/validation.py`（`_optional_datetimes`の`require_local`）。
- XML: `jra_van_retriever/acquisition/setting_xml.py`（`_raise_normal_start_floors`）。
- 値: `configs/jvlink.toml`の`[latest]`と`[latest.normal_start_floors]`。

---

## Validation

- 設定の読込と拒否、XMLの下限の適用（前・同じ・後）、2回の適用で同じ結果、位置を進めたruntime設定、不正な位置での拒否と
  既存のファイルの不変を、テストで確かめる。
- リポジトリの設定の値を、テストで完全に固定する。
- 実機で`latest`を実行し、所要時間・読込位置・表の最新日付・当日の特徴量の`freshness`の前後を
  `docs/experiments/race-day-latest-masters.md`に記録する。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 下限を最後のsetupより後に置く | その間の調教・マスタが欠ける | READMEとこのADRに決め方を書く |
| 朝の取得が長い | race-day-oddsの起動が遅れる | 実機で時間を測り、#54の手順で扱う |
| 提供元が当日の朝に前日の調教を返さない | 鮮度が改善しない | `freshness`で記録し、#54で扱う |

---

## Security / Privacy Impact

セキュリティやプライバシーへの影響はない。認証情報は扱わない。

---

## Operational Impact

- 当日の朝の`--retrieve --mode=latest`が、調教とマスタも更新する。初回だけ、下限からの差分を取る。

---

## Migration / Rollback

### Migration

既存の`latest.xml`はそのまま使える。初回の実行で、SLOP・WOOD・DIFNの位置が下限へ進む。

### Rollback

`[latest]`の`normal_data_specs`を`["RACE"]`へ戻し、`[latest.normal_start_floors]`を消す。runtime設定の進んだ位置は残るが、
無効の種別は取得されない。

---

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [ ] `docs/rules/architecture.md`
- [ ] `AGENTS.md`
- [x] `README.md`
- [x] 実験の記録（`docs/experiments/race-day-latest-masters.md`）
- [ ] 運用文書・運用手順書（#54）

---

## Follow-up Actions

- [ ] 当日の手順に、latestの所要時間と順序を入れる（#54）。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-13 | Accepted | 当日のlatestにSLOP・WOOD・DIFNを加え、normalの読込位置の下限を設定に持たせる |
