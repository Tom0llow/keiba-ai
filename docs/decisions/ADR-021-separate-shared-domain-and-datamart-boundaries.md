# ADR-021: 共有設定・レースキーとdatamartの責務を分離する

- Status: Accepted
- Date: 2026-10-14
- Decision Owners: Repository maintainers
- Supersedes: ADR-020（共有パス・レースキーの配置判断のみ）
- Superseded by: N/A

## Context

ユーザーは共有パスとレースキーの配置、および`make_datamart/builder.py`に集中した
結合・検証・保存の責務を再検討し、次の配置を明示承認した。共有パスは定数ではなく
明示されたTOMLから読み込む設定であり、レース識別型と取得時のraw行変換は責務が異なる。
datamartの検証とParquet入出力を独立させても、既存公開関数と保存形式は維持する必要がある。

## Decision

1. `src/data_paths.py`を挙動を変えず`src/settings/data_paths.py`へ移す。
   `DataPaths.from_toml`を維持し、暗黙の既定設定読込やグローバルインスタンスを設けない。
2. `RaceKey`は`src/domain/race_key.py`へ移す。既存の純粋な`race_key_from_row`は
   `src/retriever/race_key_parser.py`に置き、共有型をimportする。変換処理と検証を変更しない。
   呼出し元・テスト・現行文書を新しいimportへ移し、旧ルートモジュールを削除する。
3. `src/make_datamart/`の名前を維持する。`builder.py`は入力Parquet読込の編成と
   純粋な`join_feature_tables`、結合用キー索引・値取得を所有する。
4. `validation/table.py`に既存のdatamart検証を置く。スキーマ・キー・時点・欠損・有限値の
   検証を維持し、必要性のない細分化は行わない。
5. `tables/schema.py`はmetadata生成・復号、登録名と列型、列順構築と衝突検証を所有する。
   構築と検証が同じ列契約を利用し、schema・validationはbuilderをimportしない。
   `tables/parquet.py`は保存前・読込後に検証し、`registered_names`を明示的に伝播する。
6. `make_datamart`と`make_datamart.builder`の既存5公開関数は薄い再公開で維持する。
   通常の保存・読込importは所有モジュール`make_datamart.tables.parquet`を用いる。
7. 先頭テーブル基準のleft join、行・列順、NULL、余分キー・時点不一致・名前重複・列衝突の
   拒否、登録名検証、metadata・列型・時刻正規化を変更しない。既存CLI・取得ロック・台帳・
   原子的公開・特徴量登録・モデル契約も維持し、依存関係・環境・実データ・秘密情報を扱わない。

## Rationale

設定と共有の識別型を責務のあるパッケージへ置き、取得固有のraw変換を取得境界に戻す。
datamartは結合計算、保存契約、検証、I/Oの依存方向を明確にし、保存時と読込時の
検証が同じ契約を使う。既存公開関数の再公開により、datamart利用者のimport移行を強制しない。

## Consequences

共有型と設定のPython利用者は新しいimportへ移行する。datamartの従来import、CLI入力、
保存済みParquetは引き続き利用できる。ADR-020のその他の判断と歴史的理由は維持し、
ADR-012の結合・保存契約を継承する。新しいモデル動作や取得方式は導入しない。

## Alternatives Considered

- `src/constant/`へ設定読込とレース識別型をまとめる案は、定数と設定・型の責務が混在し、
  ディレクトリ名から役割を把握しにくくなるため採用しない。
- `RaceKey`とraw変換を同じ共有モジュールへ置く案は、取得固有の変換まで共有責務に含める。
- datamartの名前変更や検証の多段分割は、今回の責務分離に必要がないため採用しない。
- schemaやvalidationからbuilderをimportする案は、下位契約が編成へ依存するため採用しない。

## Validation

既存の共有設定・レースキー利用、取得・加工・読込、特徴量登録・datamartテストを新しい
所有モジュールへ移行する。Parquetの保存前・読込後検証、登録名伝播、metadata付きround-trip、
従来5公開関数の互換性を確認する。Ruff、mypy、全pytestとguard回帰で既存契約を検証する。
