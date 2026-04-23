"""Fetch GP practice patient list sizes from NHS Digital.

Authoritative source: NHS Digital's monthly "Patients Registered at a GP Practice"
publication (https://digital.nhs.uk/data-and-information/publications/statistical/patients-registered-at-a-gp-practice).
All other list-size datasets derive from this.

Why this source
---------------
- Published on a fixed monthly cadence (2nd Thursday of each month).
- Landing URL and CSV filename (`gp-reg-pat-prac-all.csv`) have been stable
  for years across releases. Only the CDN hash in the URL rotates monthly.
- Covers every active GP practice in England (~6,100 rows).
- Stable 10-column CSV schema (unchanged since 2015 releases).

Resolution
----------
1. GET the landing page → list of monthly publication URLs (e.g. /april-2026).
2. Pick the most-recent publication that is actually published (landing lists
   some upcoming months with no data yet).
3. GET the publication page → regex for the `gp-reg-pat-prac-all.csv` URL.
4. GET the CSV → parse → return {ODS_CODE: NUMBER_OF_PATIENTS}.

Public API
----------
fetch_list_sizes() -> dict[str, int]
    High-level one-shot. Uses on-disk cache (24h TTL). Raises on failure.

fetch_list_sizes_from_csv_url(url) -> dict[str, int]
    Lower-level; downloads the given CSV URL and parses it.

discover_latest_csv_url() -> str
    Scrapes NHS Digital to find the current `gp-reg-pat-prac-all.csv` URL.

apply_to_practices(practices, sizes) -> (updated_count, missing_codes)
    Mutates a list of practice dicts, setting `patients`. Returns counters.

Failure modes
-------------
Every HTTP + parsing failure raises a specific subclass of `PatientListError`
so the caller can decide whether to bail or keep stale data. Silent fallback
is deliberately *not* offered — we'd rather flag the problem than display
quietly-wrong numbers.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


# ---- URLs and constants ----------------------------------------------------

LANDING_URL = (
    "https://digital.nhs.uk/data-and-information/publications/statistical/"
    "patients-registered-at-a-gp-practice"
)

# CSV we want. Filename has been stable across NHS Digital releases since 2015.
PRIMARY_CSV_FILENAME = "gp-reg-pat-prac-all.csv"

# HTTP UA — NHS Digital's CDN 403s on default Python UA.
UA = (
    "Mozilla/5.0 (compatible; SuveraDashboardRefresh/1.0; "
    "+https://suvera.co.uk)"
)

# Expected CSV columns (prefix match — NHS Digital has added columns before).
REQUIRED_COLS = {"CODE", "NUMBER_OF_PATIENTS"}

# Sanity thresholds for the fetched dataset.
MIN_PRACTICES = 5500   # actual file has ~6100; alert if we drop far below
MAX_PRACTICES = 10000  # paranoia cap

# Cache TTL. Cadence is monthly so 24h is plenty fresh while avoiding
# needless scrapes during CI's 5-minute refresh loop.
CACHE_TTL_SECONDS = 24 * 60 * 60


# ---- Exceptions ------------------------------------------------------------

class PatientListError(Exception):
    """Base class for all patient-list-size fetch failures."""


class LatestUrlNotFound(PatientListError):
    """Couldn't locate the current CSV URL on the NHS Digital site."""


class CsvParseError(PatientListError):
    """CSV downloaded but schema / contents didn't validate."""


class CsvDownloadError(PatientListError):
    """HTTP-level failure fetching the CSV."""


# ---- URL discovery ---------------------------------------------------------

_PUBLICATION_PATH_RE = re.compile(
    r'href="(/data-and-information/publications/statistical/'
    r'patients-registered-at-a-gp-practice/[a-z]+-\d{4})"'
)

_MONTH_ORDER = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def _http_get(url: str, *, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        raise CsvDownloadError(f"GET {url}: {e}") from e


def _sort_key(slug: str) -> tuple[int, int]:
    """Turn 'april-2026' into a sortable (year, month) tuple."""
    month, year = slug.split("-")
    return int(year), _MONTH_ORDER.index(month)


def _parse_publication_slugs(html: str) -> list[str]:
    """Pull 'april-2026'-style slugs from the landing HTML, newest first."""
    matches = _PUBLICATION_PATH_RE.findall(html)
    slugs = []
    seen = set()
    for m in matches:
        slug = m.rsplit("/", 1)[-1]
        if "-" in slug and slug not in seen:
            try:
                _sort_key(slug)
            except (ValueError, KeyError):
                continue
            seen.add(slug)
            slugs.append(slug)
    slugs.sort(key=_sort_key, reverse=True)
    return slugs


def _find_csv_url_in_page(html: str) -> str | None:
    """Find the PRIMARY_CSV_FILENAME URL on a publication page."""
    pattern = (
        r'https://files\.digital\.nhs\.uk/[A-Z0-9]+/[A-Z0-9]+/'
        + re.escape(PRIMARY_CSV_FILENAME)
    )
    m = re.search(pattern, html)
    return m.group(0) if m else None


def discover_latest_csv_url() -> str:
    """Scrape NHS Digital to find the current CSV URL.

    Walks publication slugs newest-first; some recent ones may be listed in
    the index before their data is actually published, so we keep trying
    older months until one yields a CSV link.
    """
    landing_html = _http_get(LANDING_URL).decode("utf-8", errors="replace")
    slugs = _parse_publication_slugs(landing_html)
    if not slugs:
        raise LatestUrlNotFound(
            "No publication slugs found on landing page. NHS Digital may have "
            "restructured the site — re-inspect the landing URL manually."
        )

    for slug in slugs[:6]:  # try up to 6 months back
        page_url = f"{LANDING_URL}/{slug}"
        try:
            html = _http_get(page_url).decode("utf-8", errors="replace")
        except CsvDownloadError:
            continue
        csv_url = _find_csv_url_in_page(html)
        if csv_url:
            return csv_url

    raise LatestUrlNotFound(
        f"Walked {len(slugs[:6])} recent publications, none contained a "
        f"{PRIMARY_CSV_FILENAME} link. NHS Digital site layout may have changed."
    )


# ---- CSV parsing -----------------------------------------------------------

def parse_list_size_csv(csv_text: str) -> dict[str, int]:
    """Parse the NHS Digital CSV → {ods_code: patients}."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or not REQUIRED_COLS.issubset(reader.fieldnames):
        raise CsvParseError(
            f"CSV missing required columns {REQUIRED_COLS - set(reader.fieldnames or [])}; "
            f"got {reader.fieldnames}"
        )

    out: dict[str, int] = {}
    for i, row in enumerate(reader, start=2):
        ods = (row.get("CODE") or "").strip().upper()
        raw = (row.get("NUMBER_OF_PATIENTS") or "").strip()
        if not ods or not raw:
            continue
        try:
            patients = int(raw)
        except ValueError:
            raise CsvParseError(f"row {i}: non-integer NUMBER_OF_PATIENTS {raw!r}")
        if patients < 0:
            raise CsvParseError(f"row {i}: negative list size {patients} for {ods}")
        out[ods] = patients

    if len(out) < MIN_PRACTICES:
        raise CsvParseError(
            f"Only {len(out)} practices parsed (expected ≥{MIN_PRACTICES}). "
            f"Likely a truncated or corrupted CSV."
        )
    if len(out) > MAX_PRACTICES:
        raise CsvParseError(
            f"{len(out)} practices parsed (expected ≤{MAX_PRACTICES}). "
            f"Schema may have changed — investigate before trusting."
        )
    return out


def fetch_list_sizes_from_csv_url(url: str) -> dict[str, int]:
    raw = _http_get(url)
    return parse_list_size_csv(raw.decode("utf-8", errors="replace"))


# ---- High-level API with disk cache ----------------------------------------

@dataclass
class CacheEntry:
    url: str
    fetched_at: float
    sizes: dict[str, int]


def _cache_path() -> Path:
    return Path(__file__).parent / ".patient_list_sizes_cache.json"


def _read_cache() -> CacheEntry | None:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return CacheEntry(
            url=data["url"],
            fetched_at=float(data["fetched_at"]),
            sizes={k: int(v) for k, v in data["sizes"].items()},
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _write_cache(entry: CacheEntry) -> None:
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "url": entry.url,
        "fetched_at": entry.fetched_at,
        "sizes": entry.sizes,
    }))


def fetch_list_sizes(*, force: bool = False) -> dict[str, int]:
    """Return {ODS: patients}. Uses a 24h disk cache unless force=True."""
    if not force:
        cached = _read_cache()
        if cached and (time.time() - cached.fetched_at) < CACHE_TTL_SECONDS:
            return cached.sizes

    url = discover_latest_csv_url()
    sizes = fetch_list_sizes_from_csv_url(url)
    _write_cache(CacheEntry(url=url, fetched_at=time.time(), sizes=sizes))
    return sizes


# ---- Practice dataset application -----------------------------------------

def apply_to_practices(
    practices: list[dict],
    sizes: dict[str, int],
) -> tuple[int, list[str]]:
    """Mutate `practices` in place, setting `patients` from `sizes`.

    Returns (updated_count, missing_ods_codes). A practice is only updated
    if its ODS exists in `sizes`; missing codes are reported so callers can
    decide whether to log or alarm.
    """
    updated = 0
    missing = []
    for p in practices:
        ods = (p.get("ods") or "").upper()
        if ods and ods in sizes:
            p["patients"] = sizes[ods]
            updated += 1
        else:
            missing.append(ods)
    return updated, missing
