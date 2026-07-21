"""
Import a Jackrabbit extension pairings CSV into the local SQLite database.

Usage:
    python scripts/import_pairings.py
    python scripts/import_pairings.py --csv data/source/pairings.csv
    python scripts/import_pairings.py --csv data/source/pairings.csv --db data/aqua_essence.db

Defaults:
    --csv  data/source/pairings.csv
    --db   data/aqua_essence.db
"""
import argparse
import sys
from pathlib import Path

# Allow running from the workspace root without installing the package
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.db import init_db, import_jackrabbit_pairings_csv  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Jackrabbit pairings CSV into the DB.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "data" / "source" / "pairings.csv",
        help="Path to the pairings CSV exported from the browser extension.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=ROOT / "data" / "aqua_essence.db",
        help="Path to the SQLite database file.",
    )
    args = parser.parse_args()

    csv_path: Path = args.csv
    db_path:  Path = args.db

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    print(f"DB  : {db_path}")
    print(f"CSV : {csv_path} ({csv_path.stat().st_size:,} bytes)")

    init_db(db_path)

    csv_text = csv_path.read_text(encoding="utf-8", errors="replace")
    try:
        result = import_jackrabbit_pairings_csv(csv_text)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"\nDone.")
    print(f"  Imported : {result['imported']:,} pairings")
    print(f"  Skipped  : {result['skipped']:,} rows (duplicates / missing fields)")
    print(f"  Sessions : {len(result['sessions'])}")
    for s in sorted(result["sessions"]):
        print(f"    - {s}")


if __name__ == "__main__":
    main()
