"""Tests for scripts/push_to_sheets.py — append + status-update + formatting.

Run: python3 -m unittest tests.test_push_to_sheets
No live Google Sheets I/O.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import push_to_sheets as pts  # noqa: E402


FAKE_PRACTICES = [
    # Not signed — excluded
    {"ods": "A00001", "name": "Not signed", "icb": "NHS Kent and Medway ICB",
     "pcn_name": "PCN X", "pcn_code": "U1", "patients": 5000},
    # Signed up, non-merging
    {"ods": "A00002", "name": "Kent practice", "icb": "NHS Kent and Medway ICB",
     "pcn_name": "Kent PCN", "pcn_code": "U2", "patients": 8000},
    # Onboarding, simple relabel (Sussex → Surrey and Sussex)
    {"ods": "A00003", "name": "Sussex practice", "icb": "NHS Sussex ICB",
     "pcn_name": "Sussex PCN", "pcn_code": "U3", "patients": 7500},
    # Live (full planner)
    {"ods": "A00004", "name": "Kent live practice", "icb": "NHS Kent and Medway ICB",
     "pcn_name": "Kent PCN", "pcn_code": "U2", "patients": 9000},
    # Signed up, SPLIT via SICBL
    {"ods": "A00005", "name": "Herts practice",
     "icb": "NHS Hertfordshire and West Essex ICB",
     "pcn_name": "Herts PCN", "pcn_code": "U4", "patients": 6000},
    # Signed up, Frimley via map
    {"ods": "A00006", "name": "Frimley practice", "icb": "NHS Frimley ICB",
     "pcn_name": "Frimley PCN", "pcn_code": "U5", "patients": 4000},
]


def fake_sicbl(ods):
    return {"A00005": "06K"}.get(ods.upper())


FAKE_FRIMLEY_MAP = {"A00006": "NHS Thames Valley ICB"}

BASE_KWARGS = dict(
    practices=FAKE_PRACTICES,
    waitlist={"A00002", "A00003", "A00005", "A00006"},
    live_all={"A00004"},
    live_full={"A00004"},
    onboarding=set(),
    sicbl_lookup=fake_sicbl,
    frimley_map=FAKE_FRIMLEY_MAP,
)


class TestBuildCurrentPipeline(unittest.TestCase):
    def test_excludes_non_signed(self):
        pipeline, errors = pts.build_current_pipeline(**BASE_KWARGS)
        ods_set = {r["ods"] for r in pipeline}
        self.assertEqual(ods_set, {"A00002", "A00003", "A00004", "A00005", "A00006"})
        self.assertEqual(errors, [])

    def test_live_full_planner_is_fully_live(self):
        pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        (r,) = [r for r in pipeline if r["ods"] == "A00004"]
        self.assertEqual(r["status"], pts.STATUS_FULLY_LIVE)

    def test_live_all_but_not_full_is_live(self):
        kwargs = {**BASE_KWARGS,
                  "live_all": {"A00004", "A00002"},
                  "live_full": {"A00004"}}
        pipeline, _ = pts.build_current_pipeline(**kwargs)
        (r,) = [r for r in pipeline if r["ods"] == "A00002"]
        self.assertEqual(r["status"], pts.STATUS_LIVE)

    def test_onboarding_tier(self):
        kwargs = {**BASE_KWARGS,
                  "onboarding": {"A00003"}}
        pipeline, _ = pts.build_current_pipeline(**kwargs)
        (r,) = [r for r in pipeline if r["ods"] == "A00003"]
        # A00003 is in both waitlist AND onboarding → onboarding wins
        self.assertEqual(r["status"], pts.STATUS_ONBOARDING)

    def test_signed_up_tier(self):
        pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        (r,) = [r for r in pipeline if r["ods"] == "A00002"]
        self.assertEqual(r["status"], pts.STATUS_SIGNED_UP)

    def test_status_priority_order(self):
        # Practice in every tier — should land as Fully Live.
        kwargs = {**BASE_KWARGS,
                  "live_full": {"A00002"},
                  "live_all":  {"A00002"},
                  "onboarding": {"A00002"},
                  "waitlist":  {"A00002"}}
        pipeline, _ = pts.build_current_pipeline(**kwargs)
        (r,) = [r for r in pipeline if r["ods"] == "A00002"]
        self.assertEqual(r["status"], pts.STATUS_FULLY_LIVE)

    def test_sussex_relabelled(self):
        pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        (r,) = [r for r in pipeline if r["ods"] == "A00003"]
        self.assertEqual(r["icb"], "NHS Surrey and Sussex ICB")
        self.assertEqual(r["changing"], "Yes")

    def test_herts_split_resolves(self):
        pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        (r,) = [r for r in pipeline if r["ods"] == "A00005"]
        self.assertEqual(r["icb"], "NHS Central East ICB")

    def test_frimley_resolves_via_map(self):
        pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        (r,) = [r for r in pipeline if r["ods"] == "A00006"]
        self.assertEqual(r["icb"], "NHS Thames Valley ICB")

    def test_unresolved_split_collected_not_raised(self):
        broken = [*FAKE_PRACTICES, {
            "ods": "A99999", "name": "Broken Herts",
            "icb": "NHS Hertfordshire and West Essex ICB",
            "pcn_name": "", "pcn_code": "", "patients": 0,
        }]
        kwargs = {**BASE_KWARGS, "practices": broken,
                  "waitlist": BASE_KWARGS["waitlist"] | {"A99999"}}
        pipeline, errors = pts.build_current_pipeline(**kwargs)
        self.assertEqual(len(errors), 1)
        self.assertIn("A99999", errors[0])
        (r,) = [r for r in pipeline if r["ods"] == "A99999"]
        self.assertTrue(r["icb"].startswith("UNRESOLVED"))


class TestDiffAgainstSheet(unittest.TestCase):
    def setUp(self):
        self.pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        # Ensure deterministic fixture content
        self.pipeline_by_ods = {r["ods"]: r for r in self.pipeline}

    def test_all_new_when_sheet_empty(self):
        # Only header row
        sheet = [pts.HEADERS]
        new_rows, updates = pts.diff_against_sheet(self.pipeline, sheet)
        self.assertEqual(len(new_rows), len(self.pipeline))
        self.assertEqual(updates, [])

    def test_no_new_when_all_present_unchanged(self):
        sheet = [pts.HEADERS]
        for r in self.pipeline:
            sheet.append(pts.row_to_list(r, "2026-04-22"))
        new_rows, updates = pts.diff_against_sheet(self.pipeline, sheet)
        self.assertEqual(new_rows, [])
        self.assertEqual(updates, [])

    def test_detects_status_change(self):
        # Sheet has A00002 as "Onboarding", pipeline says "Signed up"
        sheet = [pts.HEADERS]
        for r in self.pipeline:
            r_copy = {**r, "status": pts.STATUS_ONBOARDING if r["ods"] == "A00002" else r["status"]}
            sheet.append(pts.row_to_list(r_copy, "2026-04-22"))
        new_rows, updates = pts.diff_against_sheet(self.pipeline, sheet)
        self.assertEqual(new_rows, [])
        self.assertEqual(len(updates), 1)
        row_idx, ods, new_status = updates[0]
        self.assertEqual(ods, "A00002")
        self.assertEqual(new_status, pts.STATUS_SIGNED_UP)
        # Row 2 in sheet terms (1-based, row 1 = header)
        self.assertGreaterEqual(row_idx, 2)

    def test_detects_new_practice(self):
        # Sheet missing A00006
        sheet = [pts.HEADERS]
        for r in self.pipeline:
            if r["ods"] != "A00006":
                sheet.append(pts.row_to_list(r, "2026-04-22"))
        new_rows, updates = pts.diff_against_sheet(self.pipeline, sheet)
        self.assertEqual(len(new_rows), 1)
        self.assertEqual(new_rows[0]["ods"], "A00006")
        self.assertEqual(updates, [])

    def test_ignores_empty_ods_rows(self):
        # Sheet has a blank row in the middle
        sheet = [pts.HEADERS,
                 pts.row_to_list(self.pipeline[0], "2026-04-22"),
                 [""] * len(pts.HEADERS),
                 pts.row_to_list(self.pipeline[1], "2026-04-22")]
        new_rows, _ = pts.diff_against_sheet(self.pipeline, sheet)
        # 5 pipeline - 2 present = 3 new
        self.assertEqual(len(new_rows), len(self.pipeline) - 2)

    def test_case_insensitive_ods_match(self):
        # Sheet has lowercase ODS; current pipeline has upper.
        sheet = [pts.HEADERS]
        for r in self.pipeline:
            row = pts.row_to_list(r, "2026-04-22")
            row[pts.ODS_COL_IDX] = row[pts.ODS_COL_IDX].lower()
            sheet.append(row)
        new_rows, updates = pts.diff_against_sheet(self.pipeline, sheet)
        self.assertEqual(new_rows, [])
        self.assertEqual(updates, [])


class TestRowToList(unittest.TestCase):
    def test_row_has_all_header_columns(self):
        r = {
            "icb": "NHS Kent and Medway ICB", "pre_icb": "NHS Kent and Medway ICB",
            "changing": "No", "pcn": "Kent PCN", "pcn_code": "U2",
            "ods": "A00002", "name": "Kent practice",
            "status": "Signed up", "patients": 8000,
        }
        row = pts.row_to_list(r, "2026-04-22")
        self.assertEqual(len(row), len(pts.HEADERS))
        # ODS column and First seen column must line up
        self.assertEqual(row[pts.ODS_COL_IDX], "A00002")
        self.assertEqual(row[-1], "2026-04-22")


class TestAppendAndUpdate(unittest.TestCase):
    """Mock the Sheets client entirely and verify the right calls are made."""

    def _mock_service(self, existing_values):
        service = mock.MagicMock()
        values_api = mock.MagicMock()
        service.spreadsheets.return_value.values.return_value = values_api

        # .get(...).execute() -> existing values
        get_call = mock.MagicMock()
        get_call.execute.return_value = {"values": existing_values}
        values_api.get.return_value = get_call

        values_api.append.return_value.execute.return_value = {}
        values_api.batchUpdate.return_value.execute.return_value = {}
        return service, values_api

    def test_appends_new_rows_when_sheet_has_only_header(self):
        pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        service, values_api = self._mock_service([pts.HEADERS])

        summary = pts.append_and_update(service, pipeline=pipeline, tab_name="Sheet1")

        self.assertEqual(summary["appended"], len(pipeline))
        self.assertEqual(summary["status_updated"], 0)
        # append was called once
        values_api.append.assert_called_once()
        # batchUpdate should NOT have been called (no status changes)
        values_api.batchUpdate.assert_not_called()

    def test_updates_status_no_append_when_nothing_new(self):
        pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        existing = [pts.HEADERS] + [
            pts.row_to_list({**r, "status": pts.STATUS_ONBOARDING if r["ods"] == "A00002" else r["status"]},
                            "2026-04-22")
            for r in pipeline
        ]
        service, values_api = self._mock_service(existing)

        summary = pts.append_and_update(service, pipeline=pipeline, tab_name="Sheet1")

        self.assertEqual(summary["appended"], 0)
        self.assertEqual(summary["status_updated"], 1)
        values_api.append.assert_not_called()
        values_api.batchUpdate.assert_called_once()
        # batchUpdate body should hit column H (Status), row 2..N
        call = values_api.batchUpdate.call_args.kwargs
        data = call["body"]["data"]
        self.assertEqual(len(data), 1)
        self.assertIn("!H", data[0]["range"])

    def test_does_nothing_when_no_diff(self):
        pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        existing = [pts.HEADERS] + [pts.row_to_list(r, "2026-04-22") for r in pipeline]
        service, values_api = self._mock_service(existing)

        summary = pts.append_and_update(service, pipeline=pipeline, tab_name="Sheet1")
        self.assertEqual(summary["appended"], 0)
        self.assertEqual(summary["status_updated"], 0)
        values_api.append.assert_not_called()
        values_api.batchUpdate.assert_not_called()


class TestSetupSheet(unittest.TestCase):
    def test_clears_then_updates_then_formats(self):
        pipeline, _ = pts.build_current_pipeline(**BASE_KWARGS)
        service = mock.MagicMock()
        values_api = mock.MagicMock()
        service.spreadsheets.return_value.values.return_value = values_api
        values_api.clear.return_value.execute.return_value = {}
        values_api.update.return_value.execute.return_value = {
            "updatedRange": "Sheet1!A1:J6", "updatedRows": 6,
        }
        # spreadsheets().get() for tab_gid lookup
        service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        # batchUpdate for formatting
        service.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}

        result = pts.setup_sheet(service, pipeline=pipeline, tab_name="Sheet1")

        values_api.clear.assert_called_once()
        values_api.update.assert_called_once()
        # formatting batchUpdate ran at least once
        self.assertGreaterEqual(
            service.spreadsheets.return_value.batchUpdate.call_count, 1,
        )
        self.assertEqual(result["updatedRows"], 6)

    def test_raises_if_pipeline_missing(self):
        service = mock.MagicMock()
        with self.assertRaises(ValueError):
            pts.setup_sheet(service)


class TestFormattingRequests(unittest.TestCase):
    def test_contains_header_style_freeze_widths_conditional_rules(self):
        reqs = pts.build_formatting_requests(tab_gid=42)
        kinds = [list(r.keys())[0] for r in reqs]
        self.assertIn("repeatCell", kinds)
        self.assertIn("updateSheetProperties", kinds)
        self.assertIn("updateDimensionProperties", kinds)
        self.assertIn("addConditionalFormatRule", kinds)
        self.assertIn("deleteConditionalFormatRule", kinds)

    def test_four_status_colour_rules(self):
        reqs = pts.build_formatting_requests(tab_gid=42)
        adds = [r for r in reqs if "addConditionalFormatRule" in r]
        self.assertEqual(len(adds), 4)
        statuses_covered = set()
        for add in adds:
            cond = add["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"]
            self.assertEqual(cond["type"], "TEXT_EQ")
            statuses_covered.add(cond["values"][0]["userEnteredValue"])
        self.assertEqual(
            statuses_covered,
            {pts.STATUS_FULLY_LIVE, pts.STATUS_LIVE, pts.STATUS_ONBOARDING, pts.STATUS_SIGNED_UP},
        )

    def test_header_row_only_styled(self):
        reqs = pts.build_formatting_requests(tab_gid=42)
        (header_req,) = [r for r in reqs if "repeatCell" in r]
        rng = header_req["repeatCell"]["range"]
        self.assertEqual(rng["startRowIndex"], 0)
        self.assertEqual(rng["endRowIndex"], 1)

    def test_freeze_one_row(self):
        reqs = pts.build_formatting_requests(tab_gid=42)
        (freeze,) = [r for r in reqs if "updateSheetProperties" in r]
        self.assertEqual(
            freeze["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"], 1,
        )

    def test_rules_target_correct_column(self):
        reqs = pts.build_formatting_requests(tab_gid=42)
        adds = [r for r in reqs if "addConditionalFormatRule" in r]
        for add in adds:
            rng = add["addConditionalFormatRule"]["rule"]["ranges"][0]
            self.assertEqual(rng["startColumnIndex"], pts.STATUS_COL_IDX)
            self.assertEqual(rng["endColumnIndex"], pts.STATUS_COL_IDX + 1)


class TestColLetter(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(pts._col_letter(0), "A")
        self.assertEqual(pts._col_letter(7), "H")   # Status
        self.assertEqual(pts._col_letter(9), "J")   # First seen
        self.assertEqual(pts._col_letter(25), "Z")
        self.assertEqual(pts._col_letter(26), "AA")


class TestServiceAccountLoading(unittest.TestCase):
    def test_env_inline_json_takes_priority(self):
        payload = '{"client_email": "x@y.iam.gserviceaccount.com", "private_key": "k"}'
        with mock.patch.dict("os.environ", {"GOOGLE_SHEETS_SA_JSON": payload}, clear=False):
            info = pts._load_service_account_info()
        self.assertEqual(info["client_email"], "x@y.iam.gserviceaccount.com")

    def test_missing_credentials_raises(self):
        env = {"GOOGLE_SHEETS_SA_JSON_PATH": "/tmp/definitely-not-here.json"}
        with mock.patch.dict("os.environ", env, clear=True):
            with self.assertRaises(FileNotFoundError):
                pts._load_service_account_info()


if __name__ == "__main__":
    unittest.main()
