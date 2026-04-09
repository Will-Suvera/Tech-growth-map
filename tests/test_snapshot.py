"""
Tests for snapshot.py — verifies the new full-planner / planner tier counts.
Run: python3 -m unittest tests.test_snapshot
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


class TestSnapshotTiers(unittest.TestCase):
    def setUp(self):
        # Build a self-contained fake project layout in a temp dir.
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "data").mkdir()
        (self.tmp / "snapshots").mkdir()

        # 5 practices: 2 full planner, 1 planner-only, 1 waitlist, 1 unsigned
        practices = [
            {"ods": "AAA001", "name": "Full Planner A", "patients": 10000, "lat": 52, "lng": -1},
            {"ods": "AAA002", "name": "Full Planner B", "patients": 20000, "lat": 52, "lng": -1},
            {"ods": "BBB001", "name": "Planner Only",   "patients": 30000, "lat": 52, "lng": -1},
            {"ods": "CCC001", "name": "Waitlist",       "patients": 40000, "lat": 52, "lng": -1},
            {"ods": "DDD001", "name": "Unsigned",       "patients": 50000, "lat": 52, "lng": -1},
        ]
        live_all = ["AAA001", "AAA002", "BBB001"]
        live_full = ["AAA001", "AAA002"]
        waitlist = ["CCC001"]

        with open(self.tmp / "data" / "practices_geocoded.json", "w") as f:
            json.dump(practices, f)
        with open(self.tmp / "data" / "live_customers.json", "w") as f:
            json.dump(live_all, f)
        with open(self.tmp / "data" / "live_customers_full_planner.json", "w") as f:
            json.dump(live_full, f)
        with open(self.tmp / "data" / "waitlist_ods.json", "w") as f:
            json.dump(waitlist, f)

        # Re-import snapshot.py with patched paths
        if "snapshot" in sys.modules:
            del sys.modules["snapshot"]
        import snapshot
        self.snapshot = snapshot
        self.snapshot.DATA_DIR = self.tmp / "data"
        self.snapshot.SNAPSHOT_DIR = self.tmp / "snapshots"

    def test_tiers_count_correctly(self):
        self.snapshot.take_snapshot()
        # Read the freshly written snapshot
        files = list((self.tmp / "snapshots").glob("*.json"))
        self.assertGreater(len(files), 0)
        snap_file = next(f for f in files if "timeline" not in f.name)
        with open(snap_file) as f:
            snap = json.load(f)

        self.assertEqual(snap["practices"]["live_full_planner"], 2)
        self.assertEqual(snap["practices"]["live_planner"], 1)
        self.assertEqual(snap["practices"]["live"], 3)
        self.assertEqual(snap["practices"]["waitlist"], 1)
        self.assertEqual(snap["practices"]["pipeline"], 4)
        self.assertEqual(snap["practices"]["total"], 5)

        self.assertEqual(snap["patients"]["live_full_planner"], 30000)
        self.assertEqual(snap["patients"]["live_planner"], 30000)
        self.assertEqual(snap["patients"]["live"], 60000)
        self.assertEqual(snap["patients"]["waitlist"], 40000)
        self.assertEqual(snap["patients"]["pipeline"], 100000)

    def test_timeline_appended(self):
        self.snapshot.take_snapshot()
        with open(self.tmp / "snapshots" / "timeline.json") as f:
            timeline = json.load(f)
        self.assertEqual(len(timeline), 1)
        self.assertIn("live_full_planner", timeline[0]["practices"])
        # Timeline must NOT contain the heavy ods lists.
        self.assertNotIn("live_ods", timeline[0])
        self.assertNotIn("waitlist_ods", timeline[0])


if __name__ == "__main__":
    unittest.main()
