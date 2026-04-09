"""
Static checks on the data files that the dashboard reads.
Run: python3 -m unittest tests.test_data_validity
"""

import json
import re
import unittest
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "public" / "data"
SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "public" / "snapshots"

ODS_RE = re.compile(r"^[A-Z0-9]{3,10}$")


def load_json(path):
    with open(path) as f:
        return json.load(f)


class TestLiveCustomers(unittest.TestCase):
    def setUp(self):
        self.live = load_json(DATA_DIR / "live_customers.json")
        self.full_planner = load_json(DATA_DIR / "live_customers_full_planner.json")

    def test_live_is_list_of_strings(self):
        self.assertIsInstance(self.live, list)
        for c in self.live:
            self.assertIsInstance(c, str)

    def test_live_codes_well_formed(self):
        for c in self.live:
            self.assertRegex(c, ODS_RE, f"Malformed ODS: {c!r}")

    def test_live_no_duplicates(self):
        self.assertEqual(len(self.live), len(set(self.live)))

    def test_full_planner_is_list_of_strings(self):
        self.assertIsInstance(self.full_planner, list)
        for c in self.full_planner:
            self.assertIsInstance(c, str)

    def test_full_planner_codes_well_formed(self):
        for c in self.full_planner:
            self.assertRegex(c, ODS_RE, f"Malformed ODS: {c!r}")

    def test_full_planner_is_subset_of_live(self):
        live_set = set(self.live)
        for c in self.full_planner:
            self.assertIn(c, live_set,
                          f"{c} is in live_customers_full_planner but not in live_customers")

    def test_full_planner_count_matches_user_spec(self):
        # User specified 13 codes for 'Live with all planner functionality'
        self.assertEqual(len(self.full_planner), 13)

    def test_required_full_planner_codes_present(self):
        # The 4 codes the user named explicitly + the 9 in their notes.
        required = {
            "J82067", "F85071", "J82058", "P92014",
            "P84038", "M88006", "E82031", "J82218",
            "E82107", "G84023", "P84068", "J82064", "L81051",
        }
        self.assertEqual(set(self.full_planner), required)


class TestWaitlist(unittest.TestCase):
    def setUp(self):
        self.waitlist = load_json(DATA_DIR / "waitlist_ods.json")
        self.live = set(load_json(DATA_DIR / "live_customers.json"))

    def test_waitlist_is_list_of_strings(self):
        self.assertIsInstance(self.waitlist, list)
        for c in self.waitlist:
            self.assertIsInstance(c, str)

    def test_waitlist_codes_well_formed(self):
        for c in self.waitlist:
            self.assertRegex(c, ODS_RE, f"Malformed ODS: {c!r}")

    def test_no_overlap_with_live(self):
        # Refresh script removes live codes from waitlist; test enforces it.
        # Note: this can be transiently false right after we add a code to
        # live_customers.json but before the next refresh runs. CI will catch
        # the steady state.
        overlap = set(self.waitlist) & self.live
        self.assertFalse(overlap,
                         f"Codes appear in both live and waitlist: {sorted(overlap)}")

    def test_waitlist_not_suspiciously_small(self):
        self.assertGreaterEqual(len(self.waitlist), 50,
                                "Waitlist <50 codes — likely a partial HubSpot pull")


class TestPracticesGeocoded(unittest.TestCase):
    def setUp(self):
        self.practices = load_json(DATA_DIR / "practices_geocoded.json")

    def test_practices_is_list(self):
        self.assertIsInstance(self.practices, list)
        self.assertGreater(len(self.practices), 5000, "Expected ~6000+ England GP practices")

    def test_each_practice_has_required_fields(self):
        required = {"ods", "name", "lat", "lng", "postcode"}
        for p in self.practices[:50]:
            missing = required - set(p.keys())
            self.assertFalse(missing, f"{p.get('ods')} missing fields: {missing}")

    def test_coords_inside_uk_bbox(self):
        # Rough UK bounding box. Catches geocoding regressions.
        for p in self.practices[:200]:
            self.assertTrue(49 < p["lat"] < 61, f"{p['ods']} lat {p['lat']} outside UK")
            self.assertTrue(-9 < p["lng"] < 3, f"{p['ods']} lng {p['lng']} outside UK")


class TestTimeline(unittest.TestCase):
    def setUp(self):
        self.timeline = load_json(SNAPSHOT_DIR / "timeline.json")

    def test_timeline_is_chronological(self):
        dates = [t["date"] for t in self.timeline]
        self.assertEqual(dates, sorted(dates))

    def test_each_entry_has_practices_and_patients(self):
        for t in self.timeline:
            self.assertIn("practices", t)
            self.assertIn("patients", t)
            self.assertIn("waitlist", t["practices"])
            self.assertIn("pipeline", t["practices"])


if __name__ == "__main__":
    unittest.main()
