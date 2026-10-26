"""Build the demo database: Plant A's 60-day simulated pilot (30 days observing, 30 with MeltWise).

    python scripts/build_demo_data.py [--compliance 0.6]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from meltwise import pilot, store  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compliance", type=float, default=0.6, help="share of prompts operators follow")
    parser.add_argument("--db", default=str(ROOT / "data" / "meltwise.db"))
    args = parser.parse_args()

    rows, _, _ = pilot.run(compliance=args.compliance)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    db = store.connect(args.db)
    db.execute("DELETE FROM melts")
    for i, row in enumerate(rows):
        explain = json.loads(json.dumps(row["explain"], default=float))
        store.insert_melt(db, plant="Plant A (simulated)", furnace="F1", period=row["period"],
                          started=store.started_at(row["day"], i % pilot.HEATS_PER_DAY),
                          record=row["record"], explain=explain)
    db.commit()
    summary = pilot.summarise(rows)
    print(f"Stored {len(rows)} melts in {args.db}")
    print(f"kWh/t {summary['sec_before']:.1f} -> {summary['sec_after']:.1f} "
          f"(saved {summary['saved_kwh_t']:.1f} kWh/t, {summary['saved_pct']:.1f}%)")


if __name__ == "__main__":
    main()
