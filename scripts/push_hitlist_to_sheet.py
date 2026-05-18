#!/usr/bin/env python3
"""Push the account-expansion hitlist to a Google Sheet tab.

Hitlist logic
-------------
Targets = every England GP practice in practices_geocoded.json that
          is NOT already Live (Full Planner) or In Progress
          (onboarding). Includes signed-up (waitlist) practices and
          cold prospects. A `Signed-Up?` column flags which is which.

Anchors = Live (Full Planner) practices that recalled this month
          (intersection of live_customers_full_planner.json and
          recalls.json's active_ods_this_month).

Five tiers, best wins:
  1. Live anchor in same PCN AND >=1 In Progress practice in same PCN
     ("your Live partner is converting your PCN right now")
  2. Live anchor in same PCN AND >=1 Signed-up practice in same PCN
     (no In Progress)  ("Live partner + another PCN member signed up")
  3. Live anchor in same PCN, no Signed-up or In Progress partner yet
     ("your PCN partner is Live")
  4. Live anchor within 10 miles (not in same PCN)
     ("your local cluster is live")
  5. Live anchor in same ICB (not in same PCN, not within 10 mi)
     ("your ICB has live customers")

Targets with no Live anchor in any of these conditions are excluded.

Two use cases share one sheet:
  - Mobilise signed-up practices to convert (warm leads)
  - Cold-outreach to not-signed-up practices in high-density clusters

Output
------
Wipe + rewrite a single tab on the existing internal sheet
(https://docs.google.com/spreadsheets/d/1-CMR8eyKkFtM13A0wkRtCrJ73LAtPdU8fT9gMm9AYsw/),
matching the auth setup in push_to_sheets.py.

Auth
----
Same as scripts/push_to_sheets.py. Reads one of:
  1. GOOGLE_SHEETS_SA_JSON              — inline JSON (GH Actions)
  2. GOOGLE_SHEETS_SA_JSON_PATH         — path to JSON file
  3. .secrets/nhsjobscraper-sa.json     — default local path
"""

from __future__ import annotations

import json
import sys
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from icb_mapper import (  # noqa: E402
    SicblCache,
    UnresolvableSplit,
    build_frimley_map,
    resolve_icb,
)
from push_to_sheets import (  # noqa: E402
    HEADER_BG,
    WHITE,
    _build_sheets_service,
    _col_letter,
    _hex_to_rgbf,
    get_tab_gid,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "public" / "data"
ODS_XLSX = ROOT / "ODS+Change+Summary+ICB+Mergers+Phase+1+Apr+2026 (2).xlsx"
SICBL_CACHE = Path(__file__).resolve().parent / ".sicbl_cache.json"

SPREADSHEET_ID = "1-CMR8eyKkFtM13A0wkRtCrJ73LAtPdU8fT9gMm9AYsw"
TAB_NAME = "Expansion Hitlist"

NEARBY_RADIUS_MI = 10.0
EARTH_MI = 3958.8
MAX_ANCHORS_IN_DETAIL = 8

HEADERS = [
    "Tier",                                                       # A
    "Signed-Up?",                                                 # B
    "Target ODS",                                                 # C
    "Target Practice Name",                                       # D
    "Postcode",                                                   # E
    "Patients",                                                   # F
    "PCN",                                                        # G
    "ICB (post-merger)",                                          # H
    "Live Recalling practices in the same PCN",                   # I
    "In Progress practices in the same PCN",                      # J  (drives Tier 1)
    "Signed-up practices in the same PCN",                        # K  (drives Tier 2)
    "Live Recalling practices within 10 miles",                   # L
    "Live Recalling practices in the same ICB",                   # M
    "Total Live anchor practices",                                # N
    "Anchor practices (summary)",                                 # O
]
TIER_COL_IDX = HEADERS.index("Tier")           # 0
SIGNED_UP_COL_IDX = HEADERS.index("Signed-Up?")  # 1

SIGNED_UP_YES = "Signed-up"
SIGNED_UP_NO = "Not signed up"
SIGNED_UP_BG = {
    SIGNED_UP_YES: _hex_to_rgbf("DCFCE7"),  # pale green
    SIGNED_UP_NO:  _hex_to_rgbf("FEF3C7"),  # pale amber
}

# Tier colours — 5 tiers, dark green = hottest, fading to grey
BLACK = _hex_to_rgbf("0F172A")
TIER_COLOURS = {
    1: _hex_to_rgbf("15803D"),  # dark green   — Live + In Progress in PCN
    2: _hex_to_rgbf("65A30D"),  # lime green   — Live + Signed-up in PCN
    3: _hex_to_rgbf("CA8A04"),  # gold/amber   — Live in PCN alone
    4: _hex_to_rgbf("DC2626"),  # red          — Live within 10 mi (local)
    5: _hex_to_rgbf("94A3B8"),  # grey         — Live in same ICB (regional)
}


# --- Geometry ----------------------------------------------------------------

def haversine_mi(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles."""
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = rlat2 - rlat1
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_MI * asin(sqrt(a))


# --- PCN / ICB matching ------------------------------------------------------

def _norm_pcn(p: dict) -> tuple[str, str] | None:
    """Canonical key for PCN equality. Prefer pcn_code; fall back to pcn_name."""
    code = (p.get("pcn_code") or "").strip().upper()
    if code:
        return ("code", code)
    name = (p.get("pcn_name") or "").strip().lower()
    if name:
        return ("name", name)
    return None


def _resolve_post_icb(p: dict, *, sicbl_lookup, frimley_map: dict[str, str]) -> str:
    """Resolve a practice's ICB to its post-2026-04-01 name.

    On UnresolvableSplit (missing SICBL data, Frimley not in map), falls back
    to the pre-merger ICB string. This is intentional: a missing SICBL fetch
    shouldn't silently drop a target from same-ICB matching. Worst case is
    that two practices in a SPLIT ICB that split into *different* post-merger
    ICBs get treated as same-ICB — still a defensible signal for outreach.
    """
    pre = (p.get("icb") or "").strip()
    if not pre:
        return ""
    try:
        return resolve_icb(
            pre, p["ods"],
            sicbl_lookup=sicbl_lookup,
            frimley_map=frimley_map,
        )
    except UnresolvableSplit:
        return pre


# --- Core hitlist build (pure, no I/O) ---------------------------------------

def build_hitlist(
    *,
    practices: list[dict],
    waitlist: set[str],
    full_planner: set[str],
    onboarding: set[str],
    active: set[str],
    sicbl_lookup,
    frimley_map: dict[str, str],
) -> list[dict]:
    """Compute the expansion hitlist. Returns rows sorted for display.

    Target = any practice in practices_geocoded.json that is NOT already
    Live (Full Planner) or In Progress. Each row carries a `signed_up`
    flag (true if ODS ∈ waitlist) and tier 1..5 (see module docstring).
    """
    by_ods = {p["ods"].upper(): p for p in practices}
    waitlist_upper = {c.upper() for c in waitlist}
    onboarding_upper = {c.upper() for c in onboarding}
    excluded = {c.upper() for c in (full_planner | onboarding)}

    # Anchor candidates: Full Planner AND active recalling this month.
    anchor_ods = {c.upper() for c in (full_planner & active)}
    anchor_practices = [by_ods[c] for c in anchor_ods if c in by_ods]
    anchor_meta = []
    for a in anchor_practices:
        anchor_meta.append({
            "p": a,
            "pcn": _norm_pcn(a),
            "icb_post": _resolve_post_icb(a, sicbl_lookup=sicbl_lookup, frimley_map=frimley_map),
        })

    # Index pipeline practices (In Progress + Signed-up) by PCN so we can
    # answer "how many of each kind are in this target's PCN" in O(1).
    inprogress_by_pcn: dict = {}
    signedup_by_pcn: dict = {}
    for ods in onboarding_upper:
        p = by_ods.get(ods)
        if not p: continue
        key = _norm_pcn(p)
        if key: inprogress_by_pcn.setdefault(key, []).append(p)
    for ods in waitlist_upper:
        if ods in onboarding_upper: continue  # don't double-count if a code is in both
        p = by_ods.get(ods)
        if not p: continue
        key = _norm_pcn(p)
        if key: signedup_by_pcn.setdefault(key, []).append(p)

    rows: list[dict] = []
    for t in practices:
        ods = t["ods"].upper()
        if ods in excluded:
            continue
        t_pcn = _norm_pcn(t)
        t_icb_post = _resolve_post_icb(t, sicbl_lookup=sicbl_lookup, frimley_map=frimley_map)
        t_lat, t_lng = t.get("lat"), t.get("lng")

        live_same_pcn: list[tuple[dict, float | None]] = []
        live_within_10: list[tuple[dict, float]] = []
        live_same_icb: list[tuple[dict, float | None]] = []

        for am in anchor_meta:
            a = am["p"]
            if t_pcn and am["pcn"] and t_pcn == am["pcn"]:
                live_same_pcn.append((a, None))
                continue
            # Geographic match has priority over ICB match (tier 4 > tier 5)
            if t_lat is not None and t_lng is not None and a.get("lat") is not None and a.get("lng") is not None:
                d = haversine_mi(t_lat, t_lng, a["lat"], a["lng"])
                if d <= NEARBY_RADIUS_MI:
                    live_within_10.append((a, d))
                    continue
            if t_icb_post and am["icb_post"] and t_icb_post == am["icb_post"]:
                live_same_icb.append((a, None))

        # Pipeline practices in same PCN (exclude target's own ODS).
        inprogress_pcn = [p for p in inprogress_by_pcn.get(t_pcn, []) if p["ods"].upper() != ods] if t_pcn else []
        signedup_pcn  = [p for p in signedup_by_pcn.get(t_pcn, [])  if p["ods"].upper() != ods] if t_pcn else []

        # Determine tier
        if live_same_pcn:
            if inprogress_pcn:
                tier = 1
            elif signedup_pcn:
                tier = 2
            else:
                tier = 3
        elif live_within_10:
            tier = 4
        elif live_same_icb:
            tier = 5
        else:
            continue

        rows.append({
            "tier": tier,
            "signed_up": ods in waitlist_upper,
            "target": t,
            "target_icb_post": t_icb_post,
            "live_same_pcn": live_same_pcn,
            "inprogress_same_pcn": inprogress_pcn,
            "signedup_same_pcn": signedup_pcn,
            "live_within_10mi": sorted(live_within_10, key=lambda x: x[1]),
            "live_same_icb": live_same_icb,
        })

    rows.sort(key=lambda r: (
        r["tier"],
        0 if r["signed_up"] else 1,           # signed-up first within tier
        -(r["target"].get("patients") or 0),
        -(len(r["live_same_pcn"]) + len(r["live_within_10mi"]) + len(r["live_same_icb"])),
    ))
    return rows


# --- Row formatting ----------------------------------------------------------

def format_anchor_detail(row: dict) -> str:
    """Live anchors first (same PCN > within 10 mi > same ICB), then a short
    pipeline note. Capped at MAX_ANCHORS_IN_DETAIL entries."""
    parts: list[str] = []
    for a, _ in row["live_same_pcn"]:
        parts.append(f"{a['name']} ({a['ods']}) — Live, same PCN")
    for a, d in row["live_within_10mi"]:
        parts.append(f"{a['name']} ({a['ods']}) — Live, {d:.1f} mi")
    for a, _ in row["live_same_icb"]:
        parts.append(f"{a['name']} ({a['ods']}) — Live, same ICB")

    if len(parts) > MAX_ANCHORS_IN_DETAIL:
        extra = len(parts) - MAX_ANCHORS_IN_DETAIL
        parts = parts[:MAX_ANCHORS_IN_DETAIL] + [f"+{extra} more"]

    # Optional pipeline context appended (kept short)
    extras = []
    if row["inprogress_same_pcn"]:
        n = len(row["inprogress_same_pcn"])
        extras.append(f"{n} In Progress in PCN")
    if row["signedup_same_pcn"]:
        n = len(row["signedup_same_pcn"])
        extras.append(f"{n} Signed-up in PCN")
    if extras:
        parts.append("[" + ", ".join(extras) + "]")

    return "; ".join(parts)


def row_to_list(row: dict) -> list[Any]:
    t = row["target"]
    n_live = len(row["live_same_pcn"]) + len(row["live_within_10mi"]) + len(row["live_same_icb"])
    return [
        row["tier"],
        SIGNED_UP_YES if row["signed_up"] else SIGNED_UP_NO,
        t["ods"],
        t.get("name", ""),
        t.get("postcode", ""),
        t.get("patients") or 0,
        t.get("pcn_name") or "",
        row["target_icb_post"] or t.get("icb") or "",
        len(row["live_same_pcn"]),
        len(row["inprogress_same_pcn"]),
        len(row["signedup_same_pcn"]),
        len(row["live_within_10mi"]),
        len(row["live_same_icb"]),
        n_live,
        format_anchor_detail(row),
    ]


# --- Sheet writes ------------------------------------------------------------

def ensure_tab(service, spreadsheet_id: str, tab_name: str) -> int:
    """Return the tab's sheetId (gid). Create the tab if it doesn't exist."""
    try:
        return get_tab_gid(service, spreadsheet_id, tab_name)
    except ValueError:
        resp = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
        return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def build_formatting_requests(tab_gid: int) -> list[dict]:
    """Header style + frozen row + column widths + tier-column conditional rules."""
    n_cols = len(HEADERS)
    requests: list[dict] = []

    # Header row: navy fill, white bold, wrap long labels
    requests.append({
        "repeatCell": {
            "range": {"sheetId": tab_gid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": n_cols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": HEADER_BG,
                "textFormat": {"foregroundColor": WHITE, "bold": True},
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment,wrapStrategy)",
        },
    })

    # Freeze header row
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": tab_gid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        },
    })

    # Centre-align the tier column body (cond. formatting can't set alignment)
    requests.append({
        "repeatCell": {
            "range": {"sheetId": tab_gid, "startRowIndex": 1, "endRowIndex": 100000,
                      "startColumnIndex": TIER_COL_IDX,
                      "endColumnIndex": TIER_COL_IDX + 1},
            "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.horizontalAlignment",
        },
    })

    # Column widths (px): A=Tier 60, B=Signed-Up? 110, C=ODS 90,
    # D=Name 280, E=Postcode 90, F=Patients 80, G=PCN 220, H=ICB 250,
    # I/J/K (same-PCN counts) 150, L/M (Live within-10/ICB) 150, N=total 130,
    # O=anchor summary 700.
    widths_px = {0: 60, 1: 110, 2: 90, 3: 280, 4: 90, 5: 80, 6: 220, 7: 250,
                 8: 150, 9: 150, 10: 150, 11: 150, 12: 150, 13: 130, 14: 700}
    for col, w in widths_px.items():
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": tab_gid, "dimension": "COLUMNS",
                          "startIndex": col, "endIndex": col + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            },
        })

    # Tier-column conditional rules (col A). Wipe-and-write means tier-column
    # values are integers 1/2/3, so we use NUMBER_EQ booleanRule.
    tier_range = {
        "sheetId": tab_gid,
        "startRowIndex": 1, "endRowIndex": 100000,
        "startColumnIndex": TIER_COL_IDX,
        "endColumnIndex": TIER_COL_IDX + 1,
    }
    for tier, bg in TIER_COLOURS.items():
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [tier_range],
                    "booleanRule": {
                        "condition": {
                            "type": "NUMBER_EQ",
                            "values": [{"userEnteredValue": str(tier)}],
                        },
                        "format": {
                            "backgroundColor": bg,
                            "textFormat": {"foregroundColor": WHITE, "bold": True},
                        },
                    },
                },
                "index": 0,
            },
        })

    # Signed-Up? column conditional rules (col B): pale green for Signed-up,
    # pale amber for Not signed up.
    signed_range = {
        "sheetId": tab_gid,
        "startRowIndex": 1, "endRowIndex": 100000,
        "startColumnIndex": SIGNED_UP_COL_IDX,
        "endColumnIndex": SIGNED_UP_COL_IDX + 1,
    }
    for label, bg in SIGNED_UP_BG.items():
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [signed_range],
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_EQ",
                            "values": [{"userEnteredValue": label}],
                        },
                        "format": {
                            "backgroundColor": bg,
                            "textFormat": {"foregroundColor": BLACK, "bold": True},
                        },
                    },
                },
                "index": 0,
            },
        })

    return requests


def apply_formatting(service, spreadsheet_id: str, tab_gid: int) -> None:
    """Apply formatting. Existing rules on the tier column are deleted first
    so re-runs don't stack duplicate rules."""
    from googleapiclient.errors import HttpError  # noqa: PLC0415

    # Delete existing rules one at a time, tolerating out-of-range errors.
    for _ in range(20):
        try:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"deleteConditionalFormatRule":
                                    {"sheetId": tab_gid, "index": 0}}]},
            ).execute()
        except HttpError:
            break

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": build_formatting_requests(tab_gid)},
    ).execute()


def push_hitlist(
    service,
    rows: list[dict],
    *,
    spreadsheet_id: str = SPREADSHEET_ID,
    tab_name: str = TAB_NAME,
) -> dict:
    """Wipe the tab, write header + rows, apply formatting."""
    tab_gid = ensure_tab(service, spreadsheet_id, tab_name)
    values = [HEADERS] + [row_to_list(r) for r in rows]

    api = service.spreadsheets().values()
    api.clear(spreadsheetId=spreadsheet_id, range=f"'{tab_name}'", body={}).execute()
    result = api.update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    apply_formatting(service, spreadsheet_id, tab_gid)
    return result


# --- I/O ---------------------------------------------------------------------

def load_inputs() -> dict:
    recalls = json.loads((DATA_DIR / "recalls.json").read_text())
    active = set(c.upper() for c in recalls.get("active_ods_this_month", []))
    onboarding_path = DATA_DIR / "onboarding_ods.json"
    onboarding = set()
    if onboarding_path.exists():
        onboarding = set(c.upper() for c in json.loads(onboarding_path.read_text()))
    return {
        "practices":    json.loads((DATA_DIR / "practices_geocoded.json").read_text()),
        "waitlist":     set(c.upper() for c in json.loads((DATA_DIR / "waitlist_ods.json").read_text())),
        "full_planner": set(c.upper() for c in json.loads((DATA_DIR / "live_customers_full_planner.json").read_text())),
        "onboarding":   onboarding,
        "active":       active,
        "frimley_map":  build_frimley_map(ODS_XLSX),
    }


# --- Entrypoint --------------------------------------------------------------

def main() -> None:
    dry_run = "--dry-run" in sys.argv

    inputs = load_inputs()
    sicbl = SicblCache(SICBL_CACHE)
    rows = build_hitlist(
        practices=inputs["practices"],
        waitlist=inputs["waitlist"],
        full_planner=inputs["full_planner"],
        onboarding=inputs["onboarding"],
        active=inputs["active"],
        sicbl_lookup=sicbl,
        frimley_map=inputs["frimley_map"],
    )

    by_tier: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    signed_up = sum(1 for r in rows if r["signed_up"])
    cold = len(rows) - signed_up
    for r in rows:
        by_tier[r["tier"]] += 1
    print(
        f"Hitlist: {len(rows)} targets "
        f"({signed_up} signed-up + {cold} cold)\n"
        f"  T1 (Live+InProgress in PCN):  {by_tier[1]}\n"
        f"  T2 (Live+Signed-up in PCN):   {by_tier[2]}\n"
        f"  T3 (Live in PCN alone):       {by_tier[3]}\n"
        f"  T4 (Live within 10 mi):       {by_tier[4]}\n"
        f"  T5 (Live in same ICB):        {by_tier[5]}"
    )

    if dry_run:
        print("Dry-run. First 5 rows:")
        for r in rows[:5]:
            print("   ", row_to_list(r))
        return

    service = _build_sheets_service()
    push_hitlist(service, rows)
    print(f"Pushed {len(rows)} rows to tab {TAB_NAME!r}.")


if __name__ == "__main__":
    main()
