"""Convert the configured SQLite race database to Parquet tables."""

from argparse import ArgumentParser
from pathlib import Path

from data.race_data import DataPaths, convert_all_tables


def main() -> int:
    """Convert all configured tables and report their row counts."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "config" / "data.toml",
        help="TOML file containing source and destination paths",
    )
    args = parser.parse_args()
    for name, count in convert_all_tables(DataPaths.from_toml(args.config)).items():
        print(f"{name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
