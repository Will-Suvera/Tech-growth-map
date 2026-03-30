#!/usr/bin/env python3
"""
Takes a daily snapshot of dashboard metrics for historical tracking.
Saves to snapshots/ directory as JSON with date-stamped filename.
"""

import json
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
SNAPSHOT_DIR = PROJECT_ROOT / "snapshots"

with open(DATA_DIR / "live_customers.json") as f:
    LIVE_CUSTOMER_ODS = set(json.load(f))


def take_snapshot():
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    with open(DATA_DIR / "practices_geocoded.json") as f:
        practices = json.load(f)
    with open(DATA_DIR / "waitlist_ods.json") as f:
        waitlist_ods = set(json.load(f))

    live_count = waitlist_count = live_patients = waitlist_patients = 0
    for p in practices:
        ods = p["ods"].upper()
        patients = p.get("patients", 0) or 0
        if ods in LIVE_CUSTOMER_ODS:
            live_count += 1; live_patients += patients
        elif ods in waitlist_ods:
            waitlist_count += 1; waitlist_patients += patients

    pipeline = live_count + waitlist_count

    snapshot = {
        "date": date_str,
        "timestamp": now.isoformat(),
        "practices": {
            "live": live_count, "waitlist": waitlist_count,
            "pipeline": pipeline, "total": len(practices),
            "coverage_pct": round((pipeline / len(practices)) * 100, 2) if practices else 0,
        },
        "patients": {
            "live": live_patients, "waitlist": waitlist_patients,
            "pipeline": live_patients + waitlist_patients,
        },
        "live_ods": sorted(LIVE_CUSTOMER_ODS),
        "waitlist_ods": sorted(waitlist_ods),
    }

    SNAPSHOT_DIR.mkdir(exist_ok=True)
    with open(SNAPSHOT_DIR / f"{date_str}.json", "w") as f:
        json.dump(snapshot, f, indent=2)

    # Update lightweight timeline (no ODS lists)
    timeline_file = SNAPSHOT_DIR / "timeline.json"
    timeline = json.loads(timeline_file.read_text()) if timeline_file.exists() else []
    entry = {k: v for k, v in snapshot.items() if k not in ("live_ods", "waitlist_ods")}
    timeline = [t for t in timeline if t["date"] != date_str] + [entry]
    timeline.sort(key=lambda t: t["date"])
    with open(timeline_file, "w") as f:
        json.dump(timeline, f, indent=2)

    print(f"Snapshot saved: {date_str}")
    print(f"  Pipeline: {pipeline} ({live_patients + waitlist_patients:,} patients)")
    print(f"  Live: {live_count} | Waitlist: {waitlist_count}")


if __name__ == "__main__":
    take_snapshot()
