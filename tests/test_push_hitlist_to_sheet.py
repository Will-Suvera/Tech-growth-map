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


# London-area coords used so haversine math is meaningful but predictable.
# 0.5 deg lat ~ 34.5 mi; 0.1 deg lat ~ 6.9 mi.
TARGET = {
    "ods": "T0001", "name": "TARGET PRACTICE",
    "postcode": "WD7 7JQ", "patients": 18000,
    "pcn_name": "Herts Five PCN", "pcn_code": "U97051",
    "icb": "NHS Hertfordshire and West Essex ICB",
    "lat": 51.6776, "lng": -0.3206,
}
# Same PCN as target
ANCHOR_SAME_PCN = {
    "ods": "A0001", "name": "PCN PARTNER PRACTICE",
    "postcode": "AL1 1AA", "patients": 9000,
    "pcn_name": "Herts Five PCN", "pcn_code": "U97051",
    "icb": "NHS Hertfordshire and West Essex ICB",
    "lat": 51.75, "lng": -0.34,  # ~5 mi away
}
# Different PCN but same ICB
ANCHOR_SAME_ICB = {
    "ods": "A0002", "name": "ICB PARTNER PRACTICE",
    "postcode": "EN3 0AA", "patients": 7000,
    "pcn_name": "Different PCN", "pcn_code": "U99999",
    "icb": "NHS Hertfordshire and West Essex ICB",
    "lat": 51.66, "lng": 0.05,   # ~17 mi away (different PCN, same ICB)
}
# Different ICB, within 20 mi
ANCHOR_NEARBY = {
    "ods": "A0003", "name": "NEARBY PRACTICE",
    "postcode": "NW1 1AA", "patients": 5000,
    "pcn_name": "North London PCN", "pcn_code": "U88888",
    "icb": "NHS North Central London ICB",
    "lat": 51.55, "lng": -0.30,  # ~9 mi (in NCL ICB → relabelled by resolve_icb)
}
# Different ICB, far away (excluded)
ANCHOR_FAR = {
    "ods": "A0004", "name": "FAR PRACTICE",
    "postcode": "M1 1AA", "patients": 6000,
    "pcn_name": "Manchester PCN", "pcn_code": "U77777",
    "icb": "NHS Greater Manchester ICB",
    "lat": 53.48, "lng": -2.24,  # ~150 mi away
}
# Live but NOT active recalling (not an anchor)
NOT_ACTIVE = {
    "ods": "A0005", "name": "NOT ACTIVE",
    "postcode": "AL2 2BB", "patients": 4000,
    "pcn_name": "Herts Five PCN", "pcn_code": "U97051",
    "icb": "NHS Hertfordshire and West Essex ICB",
    "lat": 51.74, "lng": -0.33,
}
# Target with NO nearby anchors (excluded from output)
LONELY_TARGET = {
    "ods": "T0002", "name": "LONELY TARGET",
    "postcode": "TR1 1AA", "patients": 3000,
    "pcn_name": "Cornwall PCN", "pcn_code": "U11111",
    "icb": "NHS Cornwall and IoS ICB",
    "lat": 50.27, "lng": -5.05,  # Truro — nowhere near anything
}

ALL_PRACTICES = [
    TARGET, ANCHOR_SAME_PCN, ANCHOR_SAME_ICB, ANCHOR_NEARBY,
    ANCHOR_FAR, NOT_ACTIVE, LONELY_TARGET,
]


def fake_sicbl(_ods):
    # Not used for these fixtures (no SPLIT_BY_SICBL ICBs)
    return None


BASE_KWARGS = dict(
    practices=ALL_PRACTICES,
    waitlist={"T0001", "T0002"},
    full_planner={"A0001", "A0002", "A0003", "A0004", "A0005"},
    onboarding=set(),
    active={"A0001", "A0002", "A0003", "A0004"},  # NOT_ACTIVE excluded
    sicbl_lookup=fake_sicbl,
    frimley_map={},
)


class TestHaversine(unittest.TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(phs.haversine_mi(51.5, -0.1, 51.5, -0.1), 0.0, places=4)

    def test_known_distance(self):
        # London (51.5, -0.1) to Manchester (53.48, -2.24) ~ 163 mi
        d = phs.haversine_mi(51.5, -0.1, 53.48, -2.24)
        self.assertGreater(d, 150)
        self.assertLess(d, 175)


class TestNormPcn(unittest.TestCase):
    def test_code_takes_priority(self):
        p = {"pcn_code": "U001", "pcn_name": "Anything"}
        self.assertEqual(phs._norm_pcn(p), ("code", "U001"))

    def test_falls_back_to_name(self):
        p = {"pcn_code": "", "pcn_name": "Herts Five PCN"}
        self.assertEqual(phs._norm_pcn(p), ("name", "herts five pcn"))

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

    def test_includes_cold_target_with_anchors(self):
        # A cold (not-signed-up) practice in same PCN as an anchor should
        # appear with signed_up=False.
        cold = {**TARGET, "ods": "C0001", "name": "COLD TARGET"}
        practices = ALL_PRACTICES + [cold]
        # waitlist does NOT include C0001
        kwargs = {**BASE_KWARGS, "practices": practices}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "C0001"]
        self.assertFalse(r["signed_up"])
        self.assertEqual(r["tier"], 1)

    def test_signed_up_flag(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertTrue(r["signed_up"])

    def test_excludes_full_planner_practices(self):
        # A Full Planner practice must not be its own target even if it's
        # technically in the waitlist set (defensive).
        kwargs = {**BASE_KWARGS, "waitlist": {"T0001", "A0001"}}
        rows = phs.build_hitlist(**kwargs)
        ods = {r["target"]["ods"] for r in rows}
        self.assertNotIn("A0001", ods)

    def test_excludes_onboarding_practices(self):
        kwargs = {**BASE_KWARGS, "onboarding": {"T0001"}}
        rows = phs.build_hitlist(**kwargs)
        ods = {r["target"]["ods"] for r in rows}
        self.assertNotIn("T0001", ods)

    def test_signed_up_sorted_before_cold_within_tier(self):
        # Two tier-1 targets, one signed-up, one cold — signed-up first.
        cold = {**TARGET, "ods": "C0001", "name": "COLD TARGET"}
        practices = ALL_PRACTICES + [cold]
        kwargs = {**BASE_KWARGS, "practices": practices}
        rows = phs.build_hitlist(**kwargs)
        tier1 = [r for r in rows if r["tier"] == 1]
        # Pull just the two-row block of tier-1 targets and assert order
        self.assertEqual(tier1[0]["signed_up"], True)
        self.assertEqual(tier1[1]["signed_up"], False)

    def test_target_tier_is_1_when_same_pcn_present(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 1)

    def test_anchor_partition(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        same_pcn_ods = {a["ods"] for a, _ in r["same_pcn"]}
        same_icb_ods = {a["ods"] for a, _ in r["same_icb"]}
        nearby_ods = {a["ods"] for a, _ in r["nearby"]}
        self.assertEqual(same_pcn_ods, {"A0001"})
        self.assertEqual(same_icb_ods, {"A0002"})
        self.assertEqual(nearby_ods, {"A0003"})
        # A0004 (far) excluded entirely
        all_ods = same_pcn_ods | same_icb_ods | nearby_ods
        self.assertNotIn("A0004", all_ods)

    def test_excludes_non_active_live(self):
        # NOT_ACTIVE is Full Planner but NOT in active set — must not appear.
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        all_anchor_ods = (
            {a["ods"] for a, _ in r["same_pcn"]} |
            {a["ods"] for a, _ in r["same_icb"]} |
            {a["ods"] for a, _ in r["nearby"]}
        )
        self.assertNotIn("A0005", all_anchor_ods)

    def test_tier_2_when_no_same_pcn(self):
        # Drop the same-PCN anchor from the active set
        kwargs = {**BASE_KWARGS, "active": {"A0002", "A0003", "A0004"}}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 2)
        self.assertEqual(len(r["same_pcn"]), 0)
        self.assertEqual(len(r["same_icb"]), 1)

    def test_tier_3_when_only_nearby(self):
        kwargs = {**BASE_KWARGS, "active": {"A0003", "A0004"}}
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        self.assertEqual(r["tier"], 3)
        self.assertEqual(len(r["same_pcn"]), 0)
        self.assertEqual(len(r["same_icb"]), 0)
        self.assertEqual(len(r["nearby"]), 1)

    def test_nearby_sorted_by_distance(self):
        # Add a second nearby anchor closer than A0003
        closer = {**ANCHOR_NEARBY, "ods": "A0006", "lat": 51.65, "lng": -0.31}
        practices = ALL_PRACTICES + [closer]
        kwargs = {**BASE_KWARGS,
                  "practices": practices,
                  "active": {"A0003", "A0006"}}  # only nearby anchors
        rows = phs.build_hitlist(**kwargs)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        distances = [d for _, d in r["nearby"]]
        self.assertEqual(distances, sorted(distances))


class TestRowToListAndDetail(unittest.TestCase):
    def test_row_has_all_columns(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        row = phs.row_to_list(r)
        self.assertEqual(len(row), len(phs.HEADERS))
        self.assertEqual(row[phs.TIER_COL_IDX], 1)
        self.assertEqual(row[phs.SIGNED_UP_COL_IDX], phs.SIGNED_UP_YES)
        self.assertEqual(row[2], "T0001")              # Target ODS
        self.assertEqual(row[3], "TARGET PRACTICE")    # Name
        self.assertEqual(row[5], 18000)                # Patients
        # Counts: same-PCN / same-ICB / nearby / total
        self.assertEqual(row[8:12], [1, 1, 1, 3])

    def test_anchor_detail_format(self):
        rows = phs.build_hitlist(**BASE_KWARGS)
        (r,) = [r for r in rows if r["target"]["ods"] == "T0001"]
        detail = phs.format_anchor_detail(r)
        self.assertIn("PCN PARTNER PRACTICE (A0001) — same PCN", detail)
        self.assertIn("ICB PARTNER PRACTICE (A0002) — same ICB", detail)
        self.assertIn("NEARBY PRACTICE (A0003) —", detail)
        self.assertIn(" mi", detail)
        # Order: PCN first, then ICB, then nearby
        i_pcn = detail.index("same PCN")
        i_icb = detail.index("same ICB")
        i_mi = detail.index(" mi")
        self.assertLess(i_pcn, i_icb)
        self.assertLess(i_icb, i_mi)

    def test_anchor_detail_truncation(self):
        # Make a synthetic row with 12 nearby anchors
        many = [({"ods": f"X{i:04d}", "name": f"P{i}"}, float(i)) for i in range(12)]
        row = {"tier": 3, "target": TARGET, "target_icb_post": "",
               "same_pcn": [], "same_icb": [], "nearby": many}
        detail = phs.format_anchor_detail(row)
        self.assertIn("+4 more", detail)


class TestSortOrder(unittest.TestCase):
    def test_tier1_before_tier2_before_tier3(self):
        # Build a fixture with three targets, one per tier
        t1 = {**TARGET, "ods": "T1"}  # tier 1 via same-PCN anchor
        t2 = {**TARGET, "ods": "T2", "pcn_code": "DIFFERENT", "pcn_name": "X"}  # tier 2
        t3 = {**TARGET, "ods": "T3", "pcn_code": "DIFFERENT", "pcn_name": "X",
              "icb": "NHS Some Other ICB"}  # tier 3 (still nearby)
        kwargs = {**BASE_KWARGS,
                  "practices": ALL_PRACTICES + [t1, t2, t3],
                  "waitlist": {"T1", "T2", "T3"}}
        rows = phs.build_hitlist(**kwargs)
        tiers = [r["tier"] for r in rows]
        self.assertEqual(tiers, sorted(tiers))


class TestEnsureTab(unittest.TestCase):
    def test_returns_gid_when_tab_exists(self):
        service = mock.MagicMock()
        service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "Expansion Hitlist", "sheetId": 99}}],
        }
        gid = phs.ensure_tab(service, "SID", "Expansion Hitlist")
        self.assertEqual(gid, 99)
        # batchUpdate must NOT have been called
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
        service.spreadsheets.return_value.batchUpdate.assert_called_once()


class TestFormattingRequests(unittest.TestCase):
    def test_contains_expected_request_types(self):
        reqs = phs.build_formatting_requests(tab_gid=7)
        kinds = [list(r.keys())[0] for r in reqs]
        self.assertIn("repeatCell", kinds)
        self.assertIn("updateSheetProperties", kinds)
        self.assertIn("updateDimensionProperties", kinds)
        self.assertIn("addConditionalFormatRule", kinds)

    def test_tier_and_signed_up_colour_rules(self):
        reqs = phs.build_formatting_requests(tab_gid=7)
        adds = [r for r in reqs if "addConditionalFormatRule" in r]
        # 3 tier rules + 2 Signed-Up rules
        self.assertEqual(len(adds), 5)
        tier_rules = [
            a for a in adds
            if a["addConditionalFormatRule"]["rule"]["ranges"][0]["startColumnIndex"]
            == phs.TIER_COL_IDX
        ]
        signed_rules = [
            a for a in adds
            if a["addConditionalFormatRule"]["rule"]["ranges"][0]["startColumnIndex"]
            == phs.SIGNED_UP_COL_IDX
        ]
        self.assertEqual(len(tier_rules), 3)
        self.assertEqual(len(signed_rules), 2)
        for add in tier_rules:
            cond = add["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"]
            self.assertEqual(cond["type"], "NUMBER_EQ")
        for add in signed_rules:
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
        # Tab exists
        service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "Expansion Hitlist", "sheetId": 7}}],
        }
        values_api = service.spreadsheets.return_value.values.return_value
        values_api.clear.return_value.execute.return_value = {}
        values_api.update.return_value.execute.return_value = {
            "updatedRange": "Expansion Hitlist!A1:L2", "updatedRows": 2,
        }
        # batchUpdate (formatting) — including the delete-loop and final apply
        service.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}

        # Build a minimal row
        rows = phs.build_hitlist(**BASE_KWARGS)
        result = phs.push_hitlist(service, rows)

        values_api.clear.assert_called_once()
        values_api.update.assert_called_once()
        # update body must start with HEADERS
        update_body = values_api.update.call_args.kwargs["body"]["values"]
        self.assertEqual(update_body[0], phs.HEADERS)
        self.assertEqual(len(update_body), 1 + len(rows))
        self.assertEqual(result["updatedRows"], 2)


if __name__ == "__main__":
    unittest.main()
