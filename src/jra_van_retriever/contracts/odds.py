"""Define raw odds staging, archive, and capture-log contracts."""

type RaceDayRaceRow = tuple[
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]

KEY_COLUMNS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
ODDS_TABLES = {
    "0B41": ("RT_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O1_ODDS_TANFUKUWAKU"),
    "0B42": ("RT_O2_ODDS_UMAREN", "ARCHIVE_O2_ODDS_UMAREN"),
}
ARCHIVE_TABLES = {spec: archive for spec, (_, archive) in ODDS_TABLES.items()}
# The race-day prediction fetch (ADR-032 Amendment 2) runs exactly the time-series specs.
PREDICTION_SPECS = frozenset(ODDS_TABLES)

CAPTURE_TABLES = {
    "0B31": (("RT_O1_ODDS_TANFUKUWAKU", "ARCHIVE_CAPTURE_O1_ODDS_TANFUKUWAKU"),),
    "0B32": (("RT_O2_ODDS_UMAREN", "ARCHIVE_CAPTURE_O2_ODDS_UMAREN"),),
    "0B33": (("RT_O3_ODDS_WIDE", "ARCHIVE_CAPTURE_O3_ODDS_WIDE"),),
    "0B34": (("RT_O4_ODDS_UMATAN", "ARCHIVE_CAPTURE_O4_ODDS_UMATAN"),),
    "0B35": (
        ("RT_O5_ODDS_SANREN", "ARCHIVE_CAPTURE_O5_ODDS_SANREN"),
        ("RT_O5_OddsSanrenInfo", "ARCHIVE_CAPTURE_O5_OddsSanrenInfo"),
    ),
    "0B36": (
        ("RT_O6_ODDS_SANRENTAN", "ARCHIVE_CAPTURE_O6_ODDS_SANRENTAN"),
        ("RT_O6_OddsSanrentanInfo", "ARCHIVE_CAPTURE_O6_OddsSanrentanInfo"),
    ),
}
ARCHIVE_CAPTURE_LOG = "ARCHIVE_CAPTURE_LOG"
