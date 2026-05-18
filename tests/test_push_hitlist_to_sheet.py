"""Tests for scripts/push_hitlist_to_sheet.py.

Run: python3 -m unittest tests.test_push_hitlist_to_sheet
No live Google Sheets I/O.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import push_hitlist_to_sheet as phs  # noqa: E402


# Coords spaced for predictable haversine results.
# 0.1 deg latitude ~ 6.9 mi at this latitude.
TARGET = {
    "ods": "T0001", "name": "TARGET PRACTICE",
    "postcode": "WD7 7JQ", "patients": 18000,
    "pcn_name": "Herts Five PCN", "pcn_code": "U97051",
    "icb": "NHS Hertfordshire and West Essex ICB",
    "lat": 51.6776, "lng": -0.3206,
}
# Same PCN as target (Live + recalling)
LIVE_SAME_PCN = {
    "ods": "A0001", "name": "PCN PARTNER PRACTICE",
    "postcode": "AL1 1AA", "patients": 9000,
    "pcn_name": "Herts Five PCN", "pcn_code": "U97051",
    "icb": "NHS Hertfordshire and West Essex ICB",
    "lat": 51.75, "lng": -0.34,
}
# Different PCN but same ICB (Live + recalling, will be tier-5 if no other tiers fire)
LIVE_SAME_ICB = {
    "ods": "A0002", "name": "ICB PARTNER PRACTICE",
    "postcode": "EN3 0AA", "patients": 7000,
    "pcn_name": "Different PCN", "pcn_code": "U99999",
    "icb": "NHS Hertfordshire and West Essex ICB",
    "lat": 51.7, "lng": 0.20,   # ~28 mi away (different PCN, same ICB)
}
# Different ICB, within 10 mi (Live + recalling)
LIVE_WITHIN_10 = {
    "ods": "A0003", "name": "NEARBY PRACTICE",
    "postcode": "NW1 1AA", "patients": 5000,
    "pcn_name": "North London PCN", "pcn_code": "U88888",
    "icb": "NHS North Central London ICB",
    "lat": 51.61, "lng": -0.30,  # ~5 mi
}
# Different ICB, far away (excluded)
LIVE_FAR = {
    "ods": "A0004", "name": "FAR PRACTICE",
    "postcode": "M1 1AA", "patients": 6000,
    "pcn_name": "Manchester PCN", "pcn_code": "U77777",
    "icb": "NHS Greater Manchester ICB",
    "lat": 53.48, "lng": -2.24,  # ~150 mi
}
# In Progress practice in same PCN as target (drives tier 1)
INPROGRESS_SAME_PCN = {
    "ods": "I0001", "name": "ONBOARDING PARTNER",
    "postcode": "AL2 2AA", "patients": 8000,
    "pcn_name": "Herts Five PCN", "pcn_code": "U97051",
    "icb": "NHS Hertfordshire and West Essex ICB",
    "lat": 51.74, "lng": -0.36,
}
# Signed-up practice in same PCN as target (drives tier 2)
SIGNEDUP_SAME_PCN = {
    "ods": "S0001", "name": "SIGNED-UP PARTNER",
    "postcode": "AL3 3AA", "patients": 7500,
    "pcn_name": "Herts Five PCN", "pcn_code": "U97051",
    "icb": "NHS Hertfordshire and West Essex ICB",
    "lat": 51.76, "lng": -0.31,
}
# Lonely target with no Live nearby (excluded)
LONELY_TARGET = {
    "ods": "T0002", "name": "LONELY TARGET",
    "postcode": "TR1 1AA", "patients": 3000,
    "pcn_name": "Cornwall PCN", "pcn_code": "U11111",
    "icb": "NHS Cornwall and IoS ICB",
    "lat": 50.27, "lng": -5.05,
}

ALL_PRACTICES = [
    TARGET, LIVE_SAME_PCN, LIVE_SAME_ICB, LIVE_WITHIN_10,
    LIVE_FAR, INPROGRESS_SAME_PCN, SIGNEDUP_SAME_PCN, LONELY_TARGET,
]


def fake_sicbl(_ods):
    return None


BASE_KWARGS = dict(
    practices=ALL_PRACTICES,
    waitlist={"T0001", "T0002", "S0001"},
    full_planner={"A0001", "A0002", "A0003", "A0004"},
    onboarding={"I0001"},
    active={"A0001", "A0002", "A0003", "A0004"},
    sicbl_lookup=fake_sicbl,
    frimley_map={},
)


class TestHaversine(unittest.TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(phs.haversine_mi(51.5, -0.1, 51.5, -0.1), 0.0, places=4)

    def test_known_distance(self):
        d = phs.haversine_mi(51.5, -0.1, 53.48, -2.24)
        self.assertGreater(d, 150)
        self.assertLess(d, 175)


class TestNormPcn(unittest.TestCase):
    def test_code_takes_priority(self):
        self.assertEqual(phs._norm_pcn({"pcn_code": "U001", "pcn_name": "X"}), ("code", "U001"))

    def test_falls_back_to_name(self):
        self.assertEqual(phs._norm_pcn({"pcn_code": "", "pcn_name": "Herts Five PCN"}),
                         ("name", "herts five pcn"))

    def test_both_blank(self):
        self.assertIsNone(phs._norm_pcn({"pcn_code": "", "pcn_name": ""}))


class TestBuildHitlist(unittest.TestCase):
    def test_includes_target_with_anchors(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        ods = {r["target"]["ods"] for r in rows}
        self.assertIn("T0001", ods)

    def test_excludes_target_without_anchors(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        ods = {r["target"]["ods"] for r in rows}
        self.assertNotIn("T0002", ods)

    def test_tier_1_when_live_pcn_and_inprogress_pcn(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 1)
        self.assertEqual(len(r["live_same_pcn"]), 1)
        self.assertEqual(len(r["inprogress_same_pcn"]), 1)
        self.assertEqual(r["inprogress_same_pcn"][0]["ods"], "I0001")

    def test_tier_2_when_live_pcn_and_signedup_pcn_no_inprogress(self):
        # Remove the In Progress practice from the PCN
        kwargs = {**BASE_KWARGS, "onboarding": set()}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 2)
        self.assertEqual(len(r["live_same_pcn"]), 1)
        self.assertEqual(len(r["inprogress_same_pcn"]), 0)
        self.assertEqual(len(r["signedup_same_pcn"]), 1)
        self.assertEqual(r["signedup_same_pcn"][0]["ods"], "S0001")

    def test_tier_3_when_live_pcn_only(self):
        # Remove BOTH the in-progress and signed-up PCN partners
        practices = [p for p in ALL_PRACTICES if p["ods"] not in ("I0001", "S0001")]
        kwargs = {**BASE_KWARGS, "practices": practices,
                  "onboarding": set(), "waitlist": {"T0001"}}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 3)

    def test_tier_4_when_only_within_10mi(self):
        # No same-PCN Live: drop A0001 from full_planner/active
        kwargs = {**BASE_KWARGS,
                  "full_planner": {"A0002", "A0003", "A0004"},
                  "active":       {"A0002", "A0003", "A0004"}}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 4)
        self.assertEqual(len(r["live_within_10mi"]), 1)
        self.assertEqual(r["live_within_10mi"][0][0]["ods"], "A0003")

    def test_tier_5_when_only_same_icb(self):
        kwargs = {**BASE_KWARGS,
                  "full_planner": {"A0002", "A0004"},
                  "active":       {"A0002", "A0004"}}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 5)
        self.assertEqual(len(r["live_same_icb"]), 1)
        self.assertEqual(r["live_same_icb"][0][0]["ods"], "A0002")

    def test_ten_mile_boundary(self):
        # A practice 8mi away qualifies; 12mi does not.
        close = {**LIVE_WITHIN_10, "ods": "A0099", "lat": 51.6776, "lng": -0.15, "patients": 100}
        far = {**LIVE_WITHIN_10, "ods": "A0098", "lat": 51.6776, "lng": 0.05, "patients": 100}
        practices = [p for p in ALL_PRACTICES if p["ods"] not in ("A0001", "A0003")] + [close, far]
        kwargs = {**BASE_KWARGS, "practices": practices,
                  "full_planner": {"A0099", "A0098", "A0004"},
                  "active":       {"A0099", "A0098", "A0004"}}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 4)
        nearby_ods = {a["ods"] for a, _ in r["live_within_10mi"]}
        self.assertIn("A0099", nearby_ods)
        self.assertNotIn("A0098", nearby_ods)

    def test_target_excluded_from_its_own_pcn_signedup_count(self):
        # Target is itself in waitlist → it should NOT count in signedup_same_pcn
        kwargs = {**BASE_KWARGS, "onboarding": set(), "waitlist": {"T0001"}}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        # No other signed-up in PCN besides target itself
        self.assertEqual(len(r["signedup_same_pcn"]), 0)
        # And tier should be 3, not 2
        self.assertEqual(r["tier"], 3)

    def test_excludes_full_planner_practices(self):
        kwargs = {**BASE_KWARGS, "waitlist": {"T0001", "A0001"}}
        rows = phs.build_hitlist(**kwargs)
        ods = {r["target"]["ods"] for r in rows}
        self.assertNotIn("A0001", ods)

    def test_onboarding_practices_now_appear_as_targets(self):
        # In Progress practices ARE targets now (so we can grease their motion)
        rows = phs.build_hitlist(**BASE_KWARGS)
        ods = {r["target"]["ods"] for r in rows}
        # I0001 is In Progress, in Herts Five PCN with Live A0001 → should be tier 3
        # (Live alone in PCN since I0001 itself doesn't count and S0001 makes it tier 2)
        self.assertIn("I0001", ods)
        (r,) = [r for r in rows if r["target"]["ods"] == "I0001"]
        self.assertEqual(r["status"], phs.STATUS_INPROGRESS)

    def test_status_field(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        ods_to_status = {r["target"]["ods"]: r["status"] for r in rows}
        self.assertEqual(ods_to_status["T0001"], phs.STATUS_SIGNEDUP)
        self.assertEqual(ods_to_status["S0001"], phs.STATUS_SIGNEDUP)
        self.assertEqual(ods_to_status["I0001"], phs.STATUS_INPROGRESS)
        # Cold target test
        cold = {**TARGET, "ods": "C0001", "name": "COLD"}
        kwargs = {**BASE_KWARGS, "practices": ALL_PRACTICES + [cold]}
        rows2 = phs.build_hitlist(**kwargs)
        c = next(r for r in rows2 if r["target"]["ods"] == "C0001")
        self.assertEqual(c["status"], phs.STATUS_COLD)

    def test_inprogress_target_excluded_from_its_own_pcn_inprogress_count(self):
        # I0001 is In Progress in Herts PCN. When I0001 is the target, its own
        # ODS must not count in the inprogress_same_pcn list.
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "I0001"]
        self.assertEqual(len(r["inprogress_same_pcn"]), 0)

    def test_cold_target_in_same_pcn_appears(self):
        # Cold practice (not in waitlist) in same PCN should appear
        cold = {**TARGET, "ods": "C0001", "name": "COLD TARGET"}
        kwargs = {**BASE_KWARGS, "practices": ALL_PRACTICES + [cold]}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "C0001"]
        self.assertFalse(r["signed_up"])
        self.assertEqual(r["tier"], 1)

    def test_signed_up_sorted_before_cold_within_tier(self):
        cold = {**TARGET, "ods": "C0001", "name": "COLD TARGET", "patients": 99999}
        kwargs = {**BASE_KWARGS, "practices": ALL_PRACTICES + [cold]}
        rows = phs.build_hitlist(**kwargs)
        tier1 = [r for r in rows if r["tier"] == 1]
        # All signed-up tier-1 rows come before the cold one, even though
        # the cold row has more patients.
        signed_block = [r for r in tier1 if r["signed_up"]]
        cold_block = [r for r in tier1 if not r["signed_up"]]
        self.assertTrue(signed_block, "expected at least one signed-up tier-1 row")
        self.assertTrue(cold_block, "expected at least one cold tier-1 row")
        first_cold_idx = next(i for i, r in enumerate(tier1) if not r["signed_up"])
        last_signed_idx = max(i for i, r in enumerate(tier1) if r["signed_up"])
        self.assertLess(last_signed_idx, first_cold_idx)
        # Within signed-up block, sorted by patients desc
        patients = [r["target"].get("patients") or 0 for r in signed_block]
        self.assertEqual(patients, sorted(patients, reverse=True))


class TestRowToListAndDetail(unittest.TestCase):
    def test_row_has_all_columns(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        row = phs.row_to_list(r)
        self.assertEqual(len(row), len(phs.HEADERS))
        self.assertEqual(row[phs.TIER_COL_IDX], 1)
        self.assertEqual(row[phs.STATUS_COL_IDX], phs.STATUS_SIGNEDUP)
        # Cols: Tier, Status, ODS, Name, Postcode, Patients, PCN, ICB,
        #       LiveSamePCN, InProgressSamePCN, SignedupSamePCN,
        #       LiveWithin10, LiveSameICB, TotalLive, Strongest, Summary
        self.assertEqual(row[2], "T0001")              # ODS
        self.assertEqual(row[5], 18000)                # Patients
        self.assertEqual(row[8], 1)   # Live in same PCN
        self.assertEqual(row[9], 1)   # In Progress in same PCN
        self.assertEqual(row[10], 1)  # Signed-up in same PCN (S0001)
        # Strongest anchor column
        self.assertIn("PCN PARTNER PRACTICE", row[14])
        self.assertIn("A0001", row[14])

    def test_strongest_anchor_priority_order(self):
        # Tier 4 target: strongest = within-10mi (no same-PCN anchor)
        kwargs = {**BASE_KWARGS,
                  "full_planner": {"A0002", "A0003", "A0004"},
                  "active":       {"A0002", "A0003", "A0004"}}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 4)
        s = phs.strongest_anchor(r)
        self.assertIn("NEARBY PRACTICE", s)
        self.assertIn("mi", s)  # distance shown for within-10 anchors

    def test_anchor_detail_format(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        detail = phs.format_anchor_detail(r)
        self.assertIn("PCN PARTNER PRACTICE (A0001) — Live, same PCN", detail)
        self.assertIn("In Progress in PCN", detail)


class TestEnsureTab(unittest.TestCase):
    def test_returns_gid_when_tab_exists(self):
        service = mock.MagicMock()
        service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "Expansion Hitlist", "sheetId": 99}}],
        }
        gid = phs.ensure_tab(service, "SID", "Expansion Hitlist")
        self.assertEqual(gid, 99)
        service.spreadsheets.return_value.batchUpdate.assert_not_called()

    def test_creates_tab_when_missing(self):
        service = mock.MagicMock()
        service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        service.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {
            "replies": [{"addSheet": {"properties": {"sheetId": 123}}}],
        }
        gid = phs.ensure_tab(service, "SID", "Expansion Hitlist")
        self.assertEqual(gid, 123)


class TestFormattingRequests(unittest.TestCase):
    def test_contains_expected_request_types(self):
        reqs = phs.build_formatting_requests(tab_gid=7)
        kinds = [list(r.keys())[0] for r in reqs]
        self.assertIn("repeatCell", kinds)
        self.assertIn("updateSheetProperties", kinds)
        self.assertIn("updateDimensionProperties", kinds)
        self.assertIn("addConditionalFormatRule", kinds)

    def test_tier_and_status_colour_rules(self):
        reqs = phs.build_formatting_requests(tab_gid=7)
        adds = [r for r in reqs if "addConditionalFormatRule" in r]
        # 5 tier rules + 3 Status rules
        self.assertEqual(len(adds), 8)
        tier_rules = [a for a in adds
                      if a["addConditionalFormatRule"]["rule"]["ranges"][0]["startColumnIndex"]
                      == phs.TIER_COL_IDX]
        status_rules = [a for a in adds
                        if a["addConditionalFormatRule"]["rule"]["ranges"][0]["startColumnIndex"]
                        == phs.STATUS_COL_IDX]
        self.assertEqual(len(tier_rules), 5)
        self.assertEqual(len(status_rules), 3)
        for add in tier_rules:
            cond = add["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"]
            self.assertEqual(cond["type"], "NUMBER_EQ")
        for add in status_rules:
            cond = add["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"]
            self.assertEqual(cond["type"], "TEXT_EQ")

    def test_freeze_one_row(self):
        reqs = phs.build_formatting_requests(tab_gid=7)
        (freeze,) = [r for r in reqs if "updateSheetProperties" in r]
        self.assertEqual(
            freeze["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"], 1,
        )


class TestPushHitlist(unittest.TestCase):
    def test_clears_then_writes_then_formats(self):
        service = mock.MagicMock()
        service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "Expansion Hitlist", "sheetId": 7}}],
        }
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.clear.return_value.execute.return_value = {}
        values_api.update.return_value.execute.return_value = {
            "updatedRange": f"Expansion Hitlist!A1:{phs._col_letter(len(phs.HEADERS)-1)}2",
            "updatedRows": 2,
        }
        service.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}

        rows = phs.build_hitlist(**BASE_KWARGS)
        result = phs.push_hitlist(service, rows)

        values_api.clear.assert_called_once()
        values_api.update.assert_called_once()
        update_body = values_api.update.call_args.kwargs["body"]["values"]
        self.assertEqual(update_body[0], phs.HEADERS)
        self.assertEqual(len(update_body), 1 + len(rows))
        self.assertEqual(result["updatedRows"], 2)


if __name__ == "__main__":
    unittest.main()
