"""Map a GP practice's current ICB to its post-2026-04-01 ICB.

Source of truth: ODS+Change+Summary+ICB+Mergers+Phase+1+Apr+2026.xlsx

Logic
-----
- 12 existing ICBs are being abolished on 2026-04-01 (Phase 1 merger).
- 9 of those map 1:1 to a single new ICB — name-only relabel.
- 3 of those split across multiple new ICBs:
    * NHS Hertfordshire and West Essex ICB   -> Central East / Essex   (by SICBL)
    * NHS Suffolk and North East Essex ICB   -> Essex / Norfolk & Suffolk (by SICBL)
    * NHS Frimley ICB                        -> Thames Valley / Surrey & Sussex / Hants & IoW
      (Frimley splits by LSOA at patient level; ODS has published a per-practice
      destination table in the xlsx "GP Practice Moves" sheet — used here.)
- The remaining ~30 ICBs are unaffected — we return the input name unchanged.

Public API
----------
resolve_icb(pre_icb, ods, *, sicbl_lookup=None, frimley_map=None) -> str
    Returns the new (post-2026-04-01) ICB name for a practice.

build_frimley_map(xlsx_path) -> dict[str, str]
    Parses the xlsx and returns {ods: new_icb_name} for Frimley GP practices.

fetch_sicbl(ods) -> str | None
    Hits NHS ODS API and returns the active Sub ICB Location (RO98) code.

Edge cases that raise
---------------------
- SPLIT ICB practice with no SICBL resolvable    -> UnresolvableSplit
- Frimley practice not in the xlsx move table    -> UnresolvableSplit
- SPLIT SICBL returns a code we don't recognise  -> UnresolvableSplit

A raise is preferred to silent fallback so the xlsx builder fails loudly rather
than quietly mislabelling a practice.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import openpyxl


# ---- Merger mapping --------------------------------------------------------

# Simple 1:1 relabels (no split).
SIMPLE_MERGER_MAP: dict[str, str] = {
    "NHS Bedfordshire, Luton and Milton Keynes ICB": "NHS Central East ICB",
    "NHS Cambridgeshire and Peterborough ICB":       "NHS Central East ICB",
    "NHS Mid and South Essex ICB":                   "NHS Essex ICB",
    "NHS Norfolk and Waveney ICB":                   "NHS Norfolk and Suffolk ICB",
    "NHS North Central London ICB":                  "NHS West and North London ICB",
    "NHS North West London ICB":                     "NHS West and North London ICB",
    "NHS Bucks, Oxfordshire & Berkshire West ICB":   "NHS Thames Valley ICB",
    "NHS Surrey Heartlands ICB":                     "NHS Surrey and Sussex ICB",
    "NHS Sussex ICB":                                "NHS Surrey and Sussex ICB",
}

# Split ICBs. Disambiguated at practice level via SICBL (Sub ICB Location code).
SPLIT_BY_SICBL: dict[str, dict[str, str]] = {
    "NHS Hertfordshire and West Essex ICB": {
        "06K": "NHS Central East ICB",
        "06N": "NHS Central East ICB",
        "07H": "NHS Essex ICB",
    },
    "NHS Suffolk and North East Essex ICB": {
        "06L": "NHS Norfolk and Suffolk ICB",
        "07K": "NHS Norfolk and Suffolk ICB",
        "06T": "NHS Essex ICB",
    },
}

# Frimley splits by LSOA, not SICBL — per-practice moves come from the xlsx.
FRIMLEY_ICB_NAME = "NHS Frimley ICB"


class UnresolvableSplit(RuntimeError):
    """Raised when a practice is in a SPLIT ICB but we can't resolve its destination."""


# ---- NHS ODS API -----------------------------------------------------------

ODS_URL = "https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations/{ods}"
SICBL_PRIMARY_ROLE_ID = "RO98"  # "SUB ICB LOCATION" in the NHS ODS role ontology


def fetch_sicbl(ods: str, *, timeout: int = 20) -> Optional[str]:
    """Return the active Sub ICB Location code for a practice, or None if unknown."""
    url = ODS_URL.format(ods=ods)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None

    org = data.get("Organisation") or {}
    for rel in (org.get("Rels") or {}).get("Rel", []) or []:
        if rel.get("Status") != "Active":
            continue
        target = rel.get("Target") or {}
        role_id = (target.get("PrimaryRoleId") or {}).get("id")
        if role_id == SICBL_PRIMARY_ROLE_ID:
            return (target.get("OrgId") or {}).get("extension")
    return None


# ---- Frimley move table ----------------------------------------------------

_FRIMLEY_HEADER = "Commissioner as at 1 Apr 2026"
_FRIMLEY_DEST_KEYWORDS: list[tuple[str, str]] = [
    ("HAMPSHIRE AND ISLE OF WIGHT", "NHS Hampshire and Isle of Wight ICB"),
    ("SURREY AND SUSSEX",           "NHS Surrey and Sussex ICB"),
    ("THAMES VALLEY",               "NHS Thames Valley ICB"),
]


def _dest_to_icb(dest: str) -> Optional[str]:
    upper = dest.upper()
    for key, new_name in _FRIMLEY_DEST_KEYWORDS:
        if key in upper:
            return new_name
    return None


def build_frimley_map(xlsx_path: str | Path) -> dict[str, str]:
    """Parse GP Practice Moves sheet and return {ods: new_icb_name} for GP practices."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["GP Practice Moves"]
    result: dict[str, str] = {}
    capturing = False

    for row in ws.iter_rows(values_only=True):
        non_null = [c for c in row if c is not None]
        if not non_null:
            continue
        header_cells = [str(x) for x in non_null]

        if _FRIMLEY_HEADER in header_cells:
            # The xlsx has TWO headers with this text: the first starts the
            # practice-level move table, the second starts a PCN-level table.
            # After the first we capture; if we were already capturing and hit
            # this header again, stop (we've moved past the practice rows).
            capturing = not capturing
            continue

        if not capturing:
            continue

        # Stop conditions: trailing prose rows
        first = row[1] if len(row) > 1 else None
        if isinstance(first, str):
            low = first.lower()
            if low.startswith((
                "prescribing cost centre",
                "pcn commissioning",
                "n/a",
                "*note",
                "commissioner as at 1 apr 2026 (tbc)",
            )):
                capturing = False
                continue

        if len(row) < 5:
            continue
        dest, code, _name, setting = row[1], row[2], row[3], row[4]
        if not (dest and code and setting == "GP PRACTICE"):
            continue
        new_icb = _dest_to_icb(str(dest))
        if new_icb:
            result[str(code).strip().upper()] = new_icb

    return result


# ---- Resolution ------------------------------------------------------------

def resolve_icb(
    pre_icb: str,
    ods: str,
    *,
    sicbl_lookup: Optional[Callable[[str], Optional[str]]] = None,
    frimley_map: Optional[dict[str, str]] = None,
) -> str:
    """Map pre-merger ICB name → post-2026-04-01 ICB name for a specific practice.

    Parameters
    ----------
    pre_icb : current ICB name (as seen in practices_geocoded.json)
    ods : practice ODS code (used only for SPLIT disambiguation)
    sicbl_lookup : fn(ods) -> SICBL code. Defaults to fetch_sicbl.
        Injected for tests and to allow caching.
    frimley_map : {ods: new_icb_name} from build_frimley_map, required if pre_icb
        is Frimley.

    Returns
    -------
    Post-merger ICB name. Non-merging ICBs pass through unchanged.

    Raises
    ------
    UnresolvableSplit if the practice is in a SPLIT ICB and cannot be resolved.
    """
    if not pre_icb:
        return pre_icb

    # Non-merging ICB — pass through
    if (
        pre_icb not in SIMPLE_MERGER_MAP
        and pre_icb not in SPLIT_BY_SICBL
        and pre_icb != FRIMLEY_ICB_NAME
    ):
        return pre_icb

    # Simple 1:1 relabel
    if pre_icb in SIMPLE_MERGER_MAP:
        return SIMPLE_MERGER_MAP[pre_icb]

    # SPLIT by SICBL (Herts & W Essex, Suffolk & NE Essex)
    if pre_icb in SPLIT_BY_SICBL:
        lookup = sicbl_lookup or fetch_sicbl
        sicbl = lookup(ods)
        if not sicbl:
            raise UnresolvableSplit(
                f"{ods}: no active SICBL from ODS API — cannot resolve {pre_icb!r}"
            )
        mapping = SPLIT_BY_SICBL[pre_icb]
        if sicbl not in mapping:
            raise UnresolvableSplit(
                f"{ods}: SICBL {sicbl} not in {pre_icb!r} split map {sorted(mapping)}"
            )
        return mapping[sicbl]

    # Frimley — uses per-practice table from the xlsx
    if pre_icb == FRIMLEY_ICB_NAME:
        if frimley_map is None:
            raise UnresolvableSplit(
                f"{ods}: Frimley practice but no frimley_map supplied"
            )
        new_icb = frimley_map.get(ods.upper())
        if not new_icb:
            raise UnresolvableSplit(
                f"{ods}: Frimley practice not found in GP Practice Moves table"
            )
        return new_icb

    return pre_icb  # unreachable; kept for type-checker comfort


# ---- SICBL cache (persists across script runs) -----------------------------

class SicblCache:
    """Disk-backed SICBL cache. Callable, so it slots into resolve_icb directly."""

    def __init__(self, path: str | Path, fetcher: Callable[[str], Optional[str]] = fetch_sicbl):
        self.path = Path(path)
        self.fetcher = fetcher
        self._cache: dict[str, Optional[str]] = {}
        if self.path.exists():
            try:
                self._cache = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                self._cache = {}

    def __call__(self, ods: str) -> Optional[str]:
        key = ods.upper()
        if key in self._cache:
            return self._cache[key]
        sicbl = self.fetcher(key)
        self._cache[key] = sicbl
        self.save()
        return sicbl

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._cache, indent=2, sort_keys=True))
