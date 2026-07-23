#!/usr/bin/env python3
"""Current practice → PCN / ICB mapping from the NHS ODS ePCN report.

Why: ``practices_geocoded.json``'s ``pcn_name``/``pcn_code``/``icb`` are
legacy static fields (never refreshed), so anything grouping practices by
PCN or ICB from them is quietly wrong wherever membership has changed.
This module pulls the authoritative, current mapping keyed purely on ODS
codes, from the ODS "ePCN core partner details" export:

    https://www.odsdatasearchandexport.nhs.uk/api/getReport?report=epcncorepartnerdetails

One CSV row per (practice, PCN, membership spell): practice ODS + name,
practice SICBL code + name, PCN code + name, PCN SICBL, join date,
left date (EMPTY = current membership), core-partner flag. The SICBL name
embeds the practice's *current* ICB ("NHS GREATER MANCHESTER ICB - 00Y"),
already post-merger in ODS, so it doubles as an ICB source that never goes
stale — no merger-relabel pass needed on top.

Fail-soft contract: ``fetch_pcn_membership()`` raises ``OdsPcnError`` on
any HTTP/parse problem; callers fall back to the legacy fields rather than
publishing an empty mapping. A small disk cache (24h TTL) keeps repeat
runs off the ODS endpoint.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
from pathlib import Path

EPCN_MEMBERS_URL = (
    "https://www.odsdatasearchandexport.nhs.uk/api/getReport?report=epcncorepartnerdetails"
)
CACHE_PATH = Path(__file__).resolve().parent / ".ods_pcn_cache.json"
CACHE_TTL_SECONDS = 24 * 3600
MIN_ROWS = 5000            # full file is ~7,800 rows; refuse a truncated one
_TIMEOUT = 60

# CSV columns (no header row)
_COL_PRACTICE_ODS = 0
_COL_PRACTICE_SICBL_NAME = 3
_COL_PCN_CODE = 4
_COL_PCN_NAME = 5
_COL_LEFT_DATE = 9

_KEEP_UPPER = {"NHS", "ICB"}


class OdsPcnError(Exception):
    """Any failure fetching/parsing the ePCN report."""


def _title_word(w: str) -> str:
    if w.upper() in _KEEP_UPPER:
        return w.upper()
    if w.upper() == "AND":
        return "and"
    return w[:1].upper() + w[1:].lower() if w else w


def icb_from_sicbl_name(sicbl_name: str) -> str:
    """'NHS GREATER MANCHESTER ICB - 00Y' -> 'NHS Greater Manchester ICB'.

    Output casing matches the resolve_icb house style so ODS-derived and
    legacy-derived ICB names compare equal for the common cases.
    """
    base = sicbl_name.rsplit(" - ", 1)[0].strip()
    return " ".join(_title_word(w) for w in base.split(" ") if w)


def _parse(text: str) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    rows = 0
    for row in csv.reader(io.StringIO(text)):
        if len(row) <= _COL_LEFT_DATE:
            continue
        rows += 1
        if (row[_COL_LEFT_DATE] or "").strip():
            continue  # historical membership spell
        ods = row[_COL_PRACTICE_ODS].strip().upper()
        if not ods:
            continue
        mapping[ods] = {
            "pcn_code": row[_COL_PCN_CODE].strip().upper(),
            "pcn_name": row[_COL_PCN_NAME].strip(),
            "icb": icb_from_sicbl_name(row[_COL_PRACTICE_SICBL_NAME]),
        }
    if rows < MIN_ROWS:
        raise OdsPcnError(f"ePCN report suspiciously small ({rows} rows < {MIN_ROWS})")
    return mapping


def fetch_pcn_membership(*, cache_path: Path = CACHE_PATH, ttl: int = CACHE_TTL_SECONDS) -> dict[str, dict]:
    """Return ``{practice ODS: {"pcn_code", "pcn_name", "icb"}}`` for every
    practice with a CURRENT PCN membership. Practices outside any PCN are
    absent — callers keep their fallback for those."""
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            if time.time() - cached.get("fetched_at", 0) < ttl:
                return cached["mapping"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # corrupt cache — refetch

    try:
        with urllib.request.urlopen(EPCN_MEMBERS_URL, timeout=_TIMEOUT) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 — collapse urllib's error zoo
        raise OdsPcnError(f"ePCN download failed: {e}") from e

    mapping = _parse(text)
    try:
        cache_path.write_text(json.dumps({"fetched_at": time.time(), "mapping": mapping}))
    except OSError:
        pass  # cache is best-effort
    return mapping
