# ADR-041: freezeを発走5分前に保ち、提示期限を発売締切とする

- Status: Accepted
- Date: 2026-11-14
- Decision Owners: Repository maintainers
- Related Issues/PRs: Closes #54、Refs #57・#30・#31・#59・#66・#69
- Supersedes: ADR-040の決定3（当日の順序）のみ。ADR-037・ADR-039のOperational Impactにある当日の朝の`latest`の記述も置き換える
- Superseded by: [ADR-049](ADR-049-handle-race-day-start-time-changes.md)（発走時刻変更の追従を#31へ送る記述のみ）

---

## Context

SPEC-02とREQ-07は、購入案を発走5分前までに提示するとしている。一方で、学習用datamartと当日の特徴量の入力固定時刻（freeze）は発走5分前であり、`freeze_offset_seconds: 300`と`prediction_offset_minutes = 5`で同じ時刻を使う。同じ時刻を提示期限にすると、取得、特徴量の計算、推論、提示の時間が残らない。

過去の0B41では、発走11分前より後の発表は発走11分前、6分前、1分前だけである（`docs/experiments/reference-prediction-features.md`）。freezeを6分前より前に置くと、11分前の発表を使うことになり、市場情報が5分古くなる。freezeを変えるには、参考datamartの再構築とPLモデルの再学習も必要になる。

JRAの発売締切は発走2分前である。2026-11-14の12:20から15:10までの実データでは、予測用の取得はfreezeのおよそ1秒後に終わり、特徴量はfreezeのおよそ6秒後に公開された。取得にはおよそ1秒、計算と公開にはおよそ1秒を要し、残りは5秒ごとの確認による。

---

## Decision

1. freezeは発走5分前のままとする。学習、当日の特徴量、race-day-oddsの予測用の取得で同じ時刻を使う。datamartとモデルは作り直さない。
2. 提示期限は発売締切、すなわち発走2分前とする。SPEC-02とREQ-07をこの期限に改める。発売締切の後に計算した予測は、ADR-039のとおり`after_sales_close: true`を記録し、購入の判断に使わない。段階1の購入額は0円とする。
3. 当日の手順は、前日の夜にrace-day-oddsが終了したことを確かめてから`latest`を実行し（その日に開催がなければ、race-day-oddsの終了の確認は不要）、翌日分の完全snapshotを公開する。前日夜の後にsnapshotのIDを控える。当日の朝は`latest`も`preprocess rebuild`も実行しない。当日はrace-day-odds、特徴量の常駐CLI、予測の常駐CLIの順に起動する。race-day-oddsの実行中は完全Parquet出力をしない。#30はこの順序で避け、コードによる排他はしない。手順は`docs/race-day-operation.md`に記す。この決定は、当日の手順を#54に委ねていたADR-040の決定3の当日の朝の`latest`の順序と、ADR-037・ADR-039のOperational Impactにある当日の朝の順序を置き換える。
4. 手順は自動化しない。3本のCLIは人が別々の端末で起動する。

---

## Rationale

発走5分前のfreezeは、発売締切前に得られる最新の発表である発走6分前の0B41を使える。2026-11-14・15は、予測用の取得を保存した各日16レースのうち13レースで0B41が6分前の発表を返し、残りの3レースは0B41への反映が遅れて10〜11分前の発表を返した（Risks、`docs/experiments/race-day-operation.md`）。11分前の発表に下げる損失は、発売締切までに残るおよそ180秒に対して、実測した処理時間がおよそ6秒と小さいことに見合わない。

前日夜の`latest`は、`result_delay_days: 7`のため土曜日の結果を日曜日に使わない。当日の朝の`latest`と比べて失うのは、前日夜のsnapshotの後の出馬表の変更だけである。取消はO1で保留し、#46で扱う。結果は`result_delay_days: 7`のため失わない。調教、マスタ、出馬表は前日夜までを使える。

---

## Consequences

### Positive

- 最新の発走6分前の発表を使いながら、利用者が購入できる時間を提示から発売締切まで確保する。
- race-day-oddsと完全Parquet出力を重ねない手順により、最小運用で#30を避ける。

### Negative

- 前日夜のsnapshotの後の出馬表の変更は特徴量に入らない。取消はO1で保留とし、#46で扱う。
- 発走時刻の変更への追従は#31で扱う。

### Neutral / Follow-on effects

- 段階2の購入額と購入判断は#56・#36で扱う。
- ADR-037とADR-039の決定は変更せず、両ADRのOperational Impactにある当日の朝の順序だけをこのADRで置き換える。
- ADR-004とADR-009が旧SPEC-02・REQ-07から引いた「発走5分前の提示」の期限は、このADRの発売締切に置き換わる。提示期限は仕様（SPEC-02・REQ-07）が定めるので、仕様の改訂で置き換わる。そのため両ADRには履歴の行も加えず、本文を記録として残す（ADR-004はすでにSuperseded、ADR-009のモデルの決定は変わらない）。

---

## Alternatives Considered

### Option A: freezeを早めて11分前の発表を使う

Summary:

freezeを発走6分前より前に置き、SPEC-02の従来の発走5分前までの提示を維持する。

Advantages:

- 発走5分前までの提示期限を維持できる。

Disadvantages:

- 発走11分前の古い市場情報を使う。
- 参考datamartの再構築とPLモデルの再学習が必要になる。

Reason not selected:

最新の発表を使う価値に対して、実測した処理時間は発売締切までの残り時間より小さい。

### Option B: 当日の早朝に`latest`を実行する

Summary:

当日の朝に`latest`を実行してからrace-day-oddsを起動する。

Advantages:

- 当日の朝までの完全snapshotを使える。

Disadvantages:

- 所要時間が読めず、race-day-oddsの起動と重なり得る。
- 2026-11-13の`latest`はおよそ3.1時間を要した。全体の実測は[当日のlatestでの調教と競走馬マスタの差分取得の実測](../experiments/race-day-latest-masters.md)にあり、11,202秒だった。

Reason not selected:

前日夜の`latest`で調教、マスタ、出馬表を使え、土曜日の結果は日曜日に使わない。

### Option C: #30のコードによる排他を先に行う

Summary:

race-day-oddsと完全Parquet出力の重なりをコードで排他する。

Advantages:

- 実行順序に依存せず重なりを防げる。

Disadvantages:

- 最小運用には不要なコード変更になる。

Reason not selected:

前日夜の`latest`と当日の起動順序で重なりを避けられる。

---

## Implementation Notes

- SPEC-02とREQ-07の提示期限を発売締切に改める。
- 入力固定時刻と提示期限の関係を`docs/implementation-design.md`に記す。
- 当日の具体的な手順は`docs/race-day-operation.md`に記す。

---

## Validation

2026-11-14・15の実データについて、予測用の取得、特徴量の公開、重賞の予測、夜の`latest`、時計のずれを`docs/experiments/race-day-operation.md`に記録する。

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 発走6分前の発表がfreezeまでに`0B41`へ反映されない | 古い市場情報を使う | 実験の記録に残し、発表の取得を改善する後続作業とする。このADRではコードを変更しない |
| JV-Linkのサービス（`JVLinkAgent`）が停止する | 取得がtimeoutし、後続の取得と特徴量の公開が遅れる | `Start-Service JVLinkAgent`を実行し、だめならPCを再起動する。手順は運用文書に記す |
| 前日夜の`latest`が翌朝までに終わらない | race-day-oddsの起動と重なる | 所要時間を記録し、必要なら#30のコードによる排他を検討する |

両日とも16レース中13レースでは`0B41`が発走6分前の発表を返した。残りの3レースでも、リアルタイムの`0B31`には発走6分前の発表があり、`0B41`への反映が遅れていた。学習用datamartは常に発走6分前の市場を使い、当日は約10レースに2レースで古い市場を使う。freezeより新しい情報は混ざらない。人の決定（2026-11-15）により、freezeは発走5分前のままとする。

両日とも`JVLinkAgent`が異常終了した。JV-Linkの不具合であり、JRA-VANも同じ事象を確認している。このリポジトリで修正できる原因ではない。

---

## Security / Privacy Impact

セキュリティやプライバシーへの重大な影響はない。認証情報は扱わない。

---

## Operational Impact

- 前日夜の`latest`、当日のrace-day-odds、特徴量の常駐CLI、予測の常駐CLIを人が順に起動する。
- 自動化、コード、設定の変更は行わない。

---

## Migration / Rollback

### Migration

コード、設定、永続データ形式の移行はない。提示期限の文言を発売締切へ改める。

### Rollback

実装上のロールバックはない。freezeまたは提示期限を改める必要がある場合は、計測結果を基に新しい決定を行う。

---

## Documentation Changes

- [x] `docs/specification.md`
- [x] `docs/requirements.md`
- [x] `docs/implementation-design.md`
- [x] `docs/race-day-operation.md`
- [x] `README.md`
- [x] 実験の記録（`docs/experiments/race-day-operation.md`）

---

## Follow-up Actions

- [x] 2026-11-15の計測後に、2日分の計測記録と運用文書の所要時間を更新する。
- [ ] freeze後、提示期限前に発走6分前の発表が届いた場合に予測用の取得へ反映する（後続Issue）。
- [x] `JVLinkAgent`の停止を検知し、取得がtimeoutまで待ち続けないようにする（#79、ADR-032 Amendment 3）。

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-11-14 | Accepted | freezeを発走5分前に保ち、提示期限を発売締切とした |
| 2026-11-15 | Accepted | 2日分の計測を記録し、freezeを5分前のまま維持した |
| 2026-11-25 | Accepted | ADR-049が、発走時刻変更の追従を#31へ送る記述を置き換えた。freezeを発走5分前、提示期限を発売締切とする決定は変えない |
