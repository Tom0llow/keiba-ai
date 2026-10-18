"""Define the shared raw O1/O2 tables and complete race-key columns."""

KEY_COLUMNS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
ODDS_TABLES = {
    "0B41": ("RT_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O1_ODDS_TANFUKUWAKU"),
    "0B42": ("RT_O2_ODDS_UMAREN", "ARCHIVE_O2_ODDS_UMAREN"),
}
ARCHIVE_TABLES = {spec: archive for spec, (_, archive) in ODDS_TABLES.items()}
