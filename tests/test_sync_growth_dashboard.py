import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import sync_growth_dashboard as growth


class TestGrowthDashboardModel(unittest.TestCase):
    def test_contracted_arr_is_annual_patient_price(self):
        self.assertEqual(growth.contracted_arr(9000), 6750.0)
        self.assertEqual(growth.contracted_arr(0), 0.0)
        self.assertEqual(growth.contracted_arr(None), 0.0)

    def test_arr_band(self):
        self.assertEqual(growth.arr_band(0), "unknown")
        self.assertEqual(growth.arr_band(2999.99), "<£3k")
        self.assertEqual(growth.arr_band(6000), "£6-9k")
        self.assertEqual(growth.arr_band(14000), "£13.5k+")

    def test_source_precedence_manual_wins(self):
        base = {
            "source": "Email Extension",
            "source_confidence": "high",
            "source_raw": ["Email Extension"],
            "source_inferred_evidence": ["HubSpot source field"],
        }
        override = {"source": "Webinar (registered)", "notes": "Confirmed by call notes"}
        result = growth.apply_source_precedence(base, override)
        self.assertEqual(result["source"], "Webinar (registered)")
        self.assertEqual(result["source_confidence"], "manual")
        self.assertEqual(result["source_override"], override)

    def test_source_precedence_confirmed_hubspot_field(self):
        base = {
            "source": "Email Extension",
            "source_confidence": "high",
            "source_raw": ["Email Extension"],
            "source_inferred_evidence": ["HubSpot source field"],
        }
        result = growth.apply_source_precedence(base, None)
        self.assertEqual(result["source"], "Email Extension")
        self.assertEqual(result["source_confidence"], "confirmed")

    def test_source_precedence_unknown_stays_visible(self):
        base = {
            "source": "Unknown",
            "source_confidence": "unknown",
            "source_raw": [],
            "source_inferred_evidence": [],
        }
        result = growth.apply_source_precedence(base, None)
        self.assertEqual(result["source"], "Unknown")
        self.assertEqual(result["source_confidence"], "unknown")

    def test_role_combo_normalises_order_and_duplicates(self):
        self.assertEqual(
            growth.role_combo(["Practice Manager", "GP Partner", "GP Partner"]),
            "GP Partner + Practice Manager",
        )

    def test_usage_status(self):
        self.assertEqual(growth.usage_status("live_full", True, True), "recalling_this_month")
        self.assertEqual(growth.usage_status("live_full", False, True), "recently_active")
        self.assertEqual(growth.usage_status("live_full", False, False), "live_no_recent_recall")
        self.assertEqual(growth.usage_status("signed_up", False, False), "not_live")


if __name__ == "__main__":
    unittest.main()
