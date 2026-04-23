"""Tests for scripts/patient_list_sizes.py — NHS Digital list-size fetcher.

Run: python3 -m unittest tests.test_patient_list_sizes

No live HTTP. URL discovery and CSV parsing are tested with fixture strings.
"""
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import patient_list_sizes as pls  # noqa: E402
from patient_list_sizes import (  # noqa: E402
    CsvParseError,
    LatestUrlNotFound,
    apply_to_practices,
    discover_latest_csv_url,
    parse_list_size_csv,
    _find_csv_url_in_page,
    _parse_publication_slugs,
    _sort_key,
)


# ---- Fixtures -------------------------------------------------------------

LANDING_FIXTURE = '''
<html><body>
<a href="/data-and-information/publications/statistical/patients-registered-at-a-gp-practice/april-2026">April 2026</a>
<a href="/data-and-information/publications/statistical/patients-registered-at-a-gp-practice/march-2026">March 2026</a>
<a href="/data-and-information/publications/statistical/patients-registered-at-a-gp-practice/february-2026">February 2026</a>
<a href="/data-and-information/publications/statistical/patients-registered-at-a-gp-practice/december-2025">December 2025</a>
<a href="/data-and-information/publications/statistical/patients-registered-at-a-gp-practice/may-2026">May 2026 (upcoming)</a>
</body></html>
'''

PUB_PAGE_FIXTURE_WITH_CSV = (
    '<html><body>'
    '<a href="https://files.digital.nhs.uk/AB/CD1234/gp-reg-pat-prac-all.csv">Download CSV</a>'
    '<a href="https://files.digital.nhs.uk/EF/56GH78/gp-reg-pat-prac-quin-age.csv">Quinary</a>'
    '</body></html>'
)

PUB_PAGE_FIXTURE_NO_CSV = (
    "<html><body><p>Data not yet released</p></body></html>"
)

# Minimal valid CSV with 2 real practices — but MIN_PRACTICES threshold is
# 5500, so for real parsing we'll build a big synthetic CSV in tests.
CSV_HEADER = (
    "PUBLICATION,EXTRACT_DATE,TYPE,SUB_ICB_LOCATION_CODE,ONS_SUB_ICB_LOCATION_CODE,"
    "CODE,POSTCODE,SEX,AGE,NUMBER_OF_PATIENTS"
)


def make_big_csv(n_rows: int) -> str:
    """Build a synthetic CSV with n_rows valid practice entries."""
    lines = [CSV_HEADER]
    for i in range(n_rows):
        lines.append(
            f"GP_PRAC_PAT_LIST,2026-04-01,GP,16C,E38000001,"
            f"A{i:05d},AB1 1AB,ALL,ALL,{1000 + i}"
        )
    return "\n".join(lines) + "\n"


# ---- Tests: URL discovery -------------------------------------------------

class TestSlugParsing(unittest.TestCase):
    def test_parses_all_slugs(self):
        slugs = _parse_publication_slugs(LANDING_FIXTURE)
        self.assertIn("april-2026", slugs)
        self.assertIn("march-2026", slugs)
        self.assertIn("december-2025", slugs)
        self.assertIn("may-2026", slugs)

    def test_sorts_newest_first(self):
        slugs = _parse_publication_slugs(LANDING_FIXTURE)
        self.assertEqual(slugs[0], "may-2026")
        self.assertEqual(slugs[1], "april-2026")
        # December 2025 should be after any 2026 month
        idx_dec25 = slugs.index("december-2025")
        for later in ("may-2026", "april-2026", "march-2026", "february-2026"):
            self.assertLess(slugs.index(later), idx_dec25)

    def test_empty_landing_returns_empty(self):
        self.assertEqual(_parse_publication_slugs("<html></html>"), [])

    def test_sort_key_handles_all_months(self):
        # Should never raise for any valid month name
        for m in [
            "january-2026", "february-2026", "march-2026", "april-2026",
            "may-2026", "june-2026", "july-2026", "august-2026",
            "september-2026", "october-2026", "november-2026", "december-2026",
        ]:
            _sort_key(m)

    def test_sort_key_raises_on_bad_month(self):
        with self.assertRaises((ValueError, KeyError)):
            _sort_key("smarch-2026")


class TestCsvUrlExtraction(unittest.TestCase):
    def test_finds_csv_url(self):
        url = _find_csv_url_in_page(PUB_PAGE_FIXTURE_WITH_CSV)
        self.assertEqual(
            url,
            "https://files.digital.nhs.uk/AB/CD1234/gp-reg-pat-prac-all.csv",
        )

    def test_returns_none_when_missing(self):
        self.assertIsNone(_find_csv_url_in_page(PUB_PAGE_FIXTURE_NO_CSV))

    def test_ignores_other_csvs(self):
        # Page has quin-age too; we only match gp-reg-pat-prac-all.csv
        url = _find_csv_url_in_page(PUB_PAGE_FIXTURE_WITH_CSV)
        self.assertIn("gp-reg-pat-prac-all.csv", url)
        self.assertNotIn("quin-age", url)


class TestDiscoverLatestUrl(unittest.TestCase):
    def test_walks_back_until_csv_found(self):
        """Most recent publication may be upcoming/unpublished — we fall back."""
        def fake_get(url, *, timeout=30):
            if url == pls.LANDING_URL:
                return LANDING_FIXTURE.encode()
            if url.endswith("may-2026"):
                return PUB_PAGE_FIXTURE_NO_CSV.encode()
            if url.endswith("april-2026"):
                return PUB_PAGE_FIXTURE_WITH_CSV.encode()
            return PUB_PAGE_FIXTURE_NO_CSV.encode()

        with mock.patch.object(pls, "_http_get", side_effect=fake_get):
            url = discover_latest_csv_url()
        self.assertTrue(url.endswith("gp-reg-pat-prac-all.csv"))

    def test_raises_when_no_slugs(self):
        with mock.patch.object(pls, "_http_get", return_value=b"<html></html>"):
            with self.assertRaises(LatestUrlNotFound):
                discover_latest_csv_url()

    def test_raises_when_no_csv_in_any_month(self):
        def fake_get(url, *, timeout=30):
            if url == pls.LANDING_URL:
                return LANDING_FIXTURE.encode()
            return PUB_PAGE_FIXTURE_NO_CSV.encode()
        with mock.patch.object(pls, "_http_get", side_effect=fake_get):
            with self.assertRaises(LatestUrlNotFound):
                discover_latest_csv_url()


# ---- Tests: CSV parsing ----------------------------------------------------

class TestCsvParsing(unittest.TestCase):
    def test_parses_clean_csv(self):
        sizes = parse_list_size_csv(make_big_csv(6000))
        self.assertEqual(len(sizes), 6000)
        self.assertEqual(sizes["A00000"], 1000)
        self.assertEqual(sizes["A00042"], 1042)

    def test_uppercases_ods(self):
        # CODE column is already upper in real data, but guard the contract.
        csv_text = (
            CSV_HEADER + "\n"
            + "\n".join(
                f"X,Y,GP,16C,E38000001,a{i:05d},AB1,ALL,ALL,{1000+i}"
                for i in range(6000)
            )
        )
        sizes = parse_list_size_csv(csv_text)
        # Lowercase input should be normalised to upper
        self.assertIn("A00000", sizes)

    def test_skips_blank_ods(self):
        rows = [CSV_HEADER]
        rows.append("X,Y,GP,16C,E38000001,,AB1,ALL,ALL,1000")
        for i in range(6000):
            rows.append(f"X,Y,GP,16C,E38000001,A{i:05d},AB1,ALL,ALL,{1000+i}")
        sizes = parse_list_size_csv("\n".join(rows))
        self.assertEqual(len(sizes), 6000)

    def test_raises_on_missing_columns(self):
        with self.assertRaises(CsvParseError):
            parse_list_size_csv("FOO,BAR\n1,2\n")

    def test_raises_on_non_integer(self):
        rows = [CSV_HEADER]
        rows.append("X,Y,GP,16C,E38000001,A00001,AB1,ALL,ALL,notanumber")
        # Pad to above MIN_PRACTICES so the missing-count check doesn't fire first
        for i in range(6000):
            rows.append(f"X,Y,GP,16C,E38000001,B{i:05d},AB1,ALL,ALL,{1000+i}")
        with self.assertRaises(CsvParseError):
            parse_list_size_csv("\n".join(rows))

    def test_raises_on_too_few_practices(self):
        with self.assertRaises(CsvParseError) as cm:
            parse_list_size_csv(make_big_csv(100))
        self.assertIn("expected", str(cm.exception).lower())

    def test_raises_on_negative_list_size(self):
        rows = [CSV_HEADER]
        for i in range(6000):
            rows.append(f"X,Y,GP,16C,E38000001,A{i:05d},AB1,ALL,ALL,{1000+i}")
        rows.append("X,Y,GP,16C,E38000001,BADCODE,AB1,ALL,ALL,-5")
        with self.assertRaises(CsvParseError):
            parse_list_size_csv("\n".join(rows))


# ---- Tests: apply_to_practices --------------------------------------------

class TestApplyToPractices(unittest.TestCase):
    def test_updates_matching_ods(self):
        practices = [
            {"ods": "A00001", "name": "X", "patients": 0},
            {"ods": "A00002", "name": "Y", "patients": 100},  # will be overwritten
        ]
        sizes = {"A00001": 5000, "A00002": 7500}
        updated, missing = apply_to_practices(practices, sizes)
        self.assertEqual(updated, 2)
        self.assertEqual(missing, [])
        self.assertEqual(practices[0]["patients"], 5000)
        self.assertEqual(practices[1]["patients"], 7500)

    def test_reports_missing_ods(self):
        practices = [
            {"ods": "A00001", "patients": 0},
            {"ods": "A99999", "patients": 0},
        ]
        sizes = {"A00001": 5000}
        updated, missing = apply_to_practices(practices, sizes)
        self.assertEqual(updated, 1)
        self.assertEqual(missing, ["A99999"])

    def test_ods_is_case_insensitive(self):
        practices = [{"ods": "a00001", "patients": 0}]
        sizes = {"A00001": 3000}
        updated, _ = apply_to_practices(practices, sizes)
        self.assertEqual(updated, 1)
        self.assertEqual(practices[0]["patients"], 3000)


# ---- Tests: high-level fetch (cache behaviour) -----------------------------

class TestFetchListSizesCache(unittest.TestCase):
    def setUp(self):
        self._orig_cache_path = pls._cache_path
        self._td = tempfile.TemporaryDirectory()
        td_path = Path(self._td.name) / "cache.json"
        pls._cache_path = lambda: td_path

    def tearDown(self):
        pls._cache_path = self._orig_cache_path
        self._td.cleanup()

    def test_uses_cache_on_second_call(self):
        calls = {"n": 0}

        def fake_discover():
            calls["n"] += 1
            return "https://files.digital.nhs.uk/AA/BB1234/gp-reg-pat-prac-all.csv"

        def fake_fetch(url):
            calls["n"] += 1
            return {"A00001": 5000}

        with mock.patch.object(pls, "discover_latest_csv_url", side_effect=fake_discover), \
             mock.patch.object(pls, "fetch_list_sizes_from_csv_url", side_effect=fake_fetch):
            # Cache starts empty so MIN_PRACTICES check would fire in real life,
            # but apply_to_practices is all we care about here — and we call the
            # cached path directly below. Fake the cache write ourselves.
            pls._write_cache(pls.CacheEntry(
                url="cached", fetched_at=time.time(), sizes={"A00001": 5000},
            ))
            sizes = pls.fetch_list_sizes()
            self.assertEqual(sizes, {"A00001": 5000})
            self.assertEqual(calls["n"], 0, "should have returned from cache without fetching")

    def test_force_bypasses_cache(self):
        pls._write_cache(pls.CacheEntry(
            url="cached", fetched_at=time.time(), sizes={"A00001": 1},
        ))

        def fake_fetch(url):
            return {"A00001": 2}

        with mock.patch.object(pls, "discover_latest_csv_url",
                               return_value="https://files.digital.nhs.uk/X/Y/gp-reg-pat-prac-all.csv"), \
             mock.patch.object(pls, "fetch_list_sizes_from_csv_url", side_effect=fake_fetch):
            sizes = pls.fetch_list_sizes(force=True)
            self.assertEqual(sizes["A00001"], 2)

    def test_expired_cache_triggers_refetch(self):
        pls._write_cache(pls.CacheEntry(
            url="cached",
            fetched_at=time.time() - pls.CACHE_TTL_SECONDS - 60,
            sizes={"A00001": 1},
        ))

        with mock.patch.object(pls, "discover_latest_csv_url",
                               return_value="https://files.digital.nhs.uk/X/Y/gp-reg-pat-prac-all.csv"), \
             mock.patch.object(pls, "fetch_list_sizes_from_csv_url",
                               return_value={"A00001": 99}):
            sizes = pls.fetch_list_sizes()
            self.assertEqual(sizes["A00001"], 99)


if __name__ == "__main__":
    unittest.main()
