#!/usr/bin/env python3
"""Push the current signed-up practices to a Google Sheet.

Modes
-----
**setup** (one-shot, on `--setup` flag or if sheet is empty)
   Wipes the target tab, writes header + all current sign-ups, applies
   formatting (navy header, frozen row, conditional colour-coding by
   status, sensible column widths). Each practice gets a `First seen`
   date = today. Run once after adding the `First seen` column to an
   existing sheet.

**append** (default)
   Reads the existing ODS codes from the sheet. For the current pipeline:
     - New ODS (not in sheet yet)  → append a row with First seen = today.
     - Existing ODS whose Status   → update the Status cell in-place
       has changed in HubSpot         (so the sheet reflects progression
                                      Signed up → Onboarding → Live).
   Rows are never deleted. Re-sorts are the user's call — we always
   append to the bottom of the data region.

Formatting
----------
Colours match `signups_by_icb.xlsx`:
   Live       = dark green #15803D  (white bold text)
   Onboarding = bright green #22C55E (white bold text)
   Signed up  = amber #F59E0B       (white bold text)

Colouring is done via **conditional formatting rules** on the Status
column, not per-cell writes. Set up once, auto-applies to new rows,
can't drift.

Auth
----
Service account. Reads one of (in order):
  1. GOOGLE_SHEETS_SA_JSON          — inline JSON (GH Actions)
  2. GOOGLE_SHEETS_SA_JSON_PATH     — path to JSON file
  3. .secrets/nhsjobscraper-sa.json — default local path

Target: https://docs.google.com/spreadsheets/d/1-CMR8eyKkFtM13A0wkRtCrJ73LAtPdU8fT9gMm9AYsw/
Service account must be shared on the sheet as Editor.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from icb_mapper import SicblCache, UnresolvableSplit, build_frimley_map, resolve_icb  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "public" / "data"
ODS_XLSX = ROOT / "ODS+Change+Summary+ICB+Mergers+Phase+1+Apr+2026 (2).xlsx"
SICBL_CACHE = Path(__file__).resolve().parent / ".sicbl_cache.json"

SPREADSHEET_ID = "1-CMR8eyKkFtM13A0wkRtCrJ73LAtPdU8fT9gMm9AYsw"
DEFAULT_TAB_NAME = "Sheet1"

HEADERS = [
    "Post-merger ICB",          # A
    "Current ICB",              # B
    "ICB changing?",            # C
    "Primary Care Network (PCN)",  # D
    "PCN code",                 # E
    "ODS code",                 # F  <-- key column for dedup
    "Practice name",            # G
    "Status",                   # H  <-- conditional formatting here
    "Patients",                 # I
    "First seen",               # J  <-- ISO date, set on first append
]

ODS_COL_IDX = HEADERS.index("ODS code")       # 5 (0-based)
STATUS_COL_IDX = HEADERS.index("Status")      # 7

# Status tiers (highest priority first). An ODS in multiple source sets
# gets the highest tier — a practice never appears in two tiers.
# Labels match the user's language in the operations context: a practice
# "goes live" once planner features are turned on; "fully live" = full
# planner tier; "onboarding" = actively being set up but not yet live.
STATUS_FULLY_LIVE = "Fully Live"
STATUS_LIVE       = "Live"
STATUS_ONBOARDING = "Onboarding"
STATUS_SIGNED_UP  = "Signed up"

# --- Status colours (RGB floats 0..1) --------------------------------------
def _hex_to_rgbf(hex_: str) -> dict[str, float]:
    hex_ = hex_.lstrip("#")
    r, g, b = int(hex_[0:2], 16), int(hex_[2:4], 16), int(hex_[4:6], 16)
    return {"red": r / 255, "green": g / 255, "blue": b / 255}

STATUS_COLOURS = {
    STATUS_FULLY_LIVE: _hex_to_rgbf("15803D"),  # dark green
    STATUS_LIVE:       _hex_to_rgbf("22C55E"),  # bright green
    STATUS_ONBOARDING: _hex_to_rgbf("86EFAC"),  # pale green (dark text)
    STATUS_SIGNED_UP:  _hex_to_rgbf("F59E0B"),  # amber
}
# Onboarding gets dark text for contrast on pale green; others get white.
STATUS_TEXT_DARK = {STATUS_ONBOARDING}

HEADER_BG = _hex_to_rgbf("1E2A4A")
WHITE = _hex_to_rgbf("FFFFFF")
BLACK = _hex_to_rgbf("0F172A")


# --- Core build / diff logic (pure, no I/O) ---------------------------------

def _status_for(
    ods: str,
    live_full: set, live_all: set, onboarding: set, waitlist: set,
) -> str | None:
    """Priority: Fully Live > Live > Onboarding > Signed up.
    Returns None if the practice is in none of the sets."""
    if ods in live_full:  return STATUS_FULLY_LIVE
    if ods in live_all:   return STATUS_LIVE
    if ods in onboarding: return STATUS_ONBOARDING
    if ods in waitlist:   return STATUS_SIGNED_UP
    return None


def build_current_pipeline(
    *,
    practices: list[dict],
    waitlist: set[str],
    live_all: set[str],
    live_full: set[str],
    onboarding: set[str] | None = None,
    sicbl_lookup,
    frimley_map: dict[str, str],
) -> tuple[list[dict], list[str]]:
    """Classify every signed practice. Returns (rows_dict_list, errors)."""
    rows: list[dict] = []
    errors: list[str] = []
    onboarding = onboarding or set()

    for p in practices:
        ods = p["ods"].upper()
        st = _status_for(ods, live_full, live_all, onboarding, waitlist)
        if not st:
            continue
        pre_icb = (p.get("icb") or "").strip()
        try:
            post_icb = resolve_icb(
                pre_icb, ods,
                sicbl_lookup=sicbl_lookup,
                frimley_map=frimley_map,
            )
        except UnresolvableSplit as e:
            errors.append(str(e))
            post_icb = f"UNRESOLVED: {pre_icb}"
        changing = (post_icb != pre_icb) and not post_icb.startswith("UNRESOLVED")
        rows.append({
            "icb":      post_icb,
            "pre_icb":  pre_icb or "(unknown)",
            "changing": "Yes" if changing else "No",
            "pcn":      p.get("pcn_name") or "",
            "pcn_code": p.get("pcn_code") or "",
            "ods":      ods,
            "name":     p.get("name") or "",
            "status":   st,
            "patients": p.get("patients") or 0,
        })

    return rows, errors


def row_to_list(r: dict, first_seen: str) -> list[Any]:
    return [
        r["icb"], r["pre_icb"], r["changing"],
        r["pcn"], r["pcn_code"],
        r["ods"], r["name"], r["status"], r["patients"],
        first_seen,
    ]


def diff_against_sheet(
    current: list[dict],
    sheet_rows: list[list[Any]],
) -> tuple[list[dict], list[tuple[int, str, str]]]:
    """Return (new_rows, status_updates).

    `sheet_rows` includes the header at index 0; data starts at row 2 (1-based
    in the Sheets UI).

    - `new_rows`       : rows whose ODS isn't in the sheet yet.
    - `status_updates` : list of (sheet_row_index_1based, ods, new_status) for
                         practices whose Status in the sheet differs from now.
    """
    existing: dict[str, tuple[int, str]] = {}
    for i, row in enumerate(sheet_rows[1:], start=2):  # row 2 = first data row
        if len(row) <= ODS_COL_IDX:
            continue
        ods = (row[ODS_COL_IDX] or "").strip().upper()
        if not ods:
            continue
        status = (row[STATUS_COL_IDX] or "").strip() if len(row) > STATUS_COL_IDX else ""
        existing[ods] = (i, status)

    new_rows: list[dict] = []
    status_updates: list[tuple[int, str, str]] = []
    for r in current:
        ods = r["ods"]
        if ods not in existing:
            new_rows.append(r)
        else:
            sheet_row_idx, sheet_status = existing[ods]
            if sheet_status != r["status"]:
                status_updates.append((sheet_row_idx, ods, r["status"]))
    return new_rows, status_updates


# --- I/O: local inputs -------------------------------------------------------

def load_inputs() -> dict:
    onboarding_path = DATA_DIR / "onboarding_ods.json"
    onboarding = set()
    if onboarding_path.exists():
        onboarding = set(json.loads(onboarding_path.read_text()))
    return {
        "practices":   json.loads((DATA_DIR / "practices_geocoded.json").read_text()),
        "waitlist":    set(json.loads((DATA_DIR / "waitlist_ods.json").read_text())),
        "live_all":    set(json.loads((DATA_DIR / "live_customers.json").read_text())),
        "live_full":   set(json.loads((DATA_DIR / "live_customers_full_planner.json").read_text())),
        "onboarding":  onboarding,
        "frimley_map": build_frimley_map(ODS_XLSX),
    }


# --- I/O: Sheets client ------------------------------------------------------

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _load_service_account_info() -> dict:
    inline = os.environ.get("GOOGLE_SHEETS_SA_JSON")
    if inline:
        return json.loads(inline)
    path_env = os.environ.get("GOOGLE_SHEETS_SA_JSON_PATH")
    path = Path(path_env) if path_env else (ROOT / ".secrets" / "nhsjobscraper-sa.json")
    if not path.exists():
        raise FileNotFoundError(
            f"No service-account credentials found. Set GOOGLE_SHEETS_SA_JSON "
            f"(inline JSON) or place the key at {path}."
        )
    return json.loads(path.read_text())


def _build_sheets_service():
    from google.oauth2.service_account import Credentials  # noqa: PLC0415
    from googleapiclient.discovery import build  # noqa: PLC0415

    info = _load_service_account_info()
    creds = Credentials.from_service_account_info(info, scopes=SHEETS_SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


# --- Sheets I/O helpers ------------------------------------------------------

def get_tab_gid(service, spreadsheet_id: str, tab_name: str) -> int:
    """Look up the numeric sheetId (gid) of a tab by name."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == tab_name:
            return props["sheetId"]
    raise ValueError(f"Tab {tab_name!r} not found in spreadsheet {spreadsheet_id}")


def read_all_values(service, spreadsheet_id: str, tab_name: str) -> list[list[Any]]:
    resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'",
    ).execute()
    return resp.get("values", [])


# --- Formatting (conditional rules + header style + freeze + widths) --------

def _col_letter(zero_based_idx: int) -> str:
    """0 -> A, 9 -> J, 25 -> Z, 26 -> AA."""
    s = ""
    n = zero_based_idx
    while True:
        s = chr(ord("A") + (n % 26)) + s
        n = n // 26 - 1
        if n < 0:
            break
    return s


def build_formatting_requests(tab_gid: int) -> list[dict]:
    """Idempotent-ish formatting: header + frozen row + widths + colour rules.

    Run inside a batchUpdate. We clear existing conditional-format rules on the
    Status column first so re-runs don't stack duplicate rules.
    """
    status_col = STATUS_COL_IDX  # 0-based
    n_cols = len(HEADERS)

    requests: list[dict] = []

    # Header row style: navy fill, white bold
    requests.append({
        "repeatCell": {
            "range": {"sheetId": tab_gid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": n_cols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": HEADER_BG,
                "textFormat": {"foregroundColor": WHITE, "bold": True},
                "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)",
        },
    })

    # Freeze header row
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": tab_gid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        },
    })

    # Column widths (matches xlsx widths roughly, in px ≈ xlsx units × 7)
    widths_px = {0: 320, 1: 280, 2: 90, 3: 290, 4: 70,
                 5: 75, 6: 340, 7: 90, 8: 80, 9: 95}
    for col, w in widths_px.items():
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": tab_gid, "dimension": "COLUMNS",
                          "startIndex": col, "endIndex": col + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            },
        })

    # Clear any existing conditional-format rules on the Status column.
    # We do this by deleting index 0 repeatedly; each delete shifts the rest
    # down. Applying >= rule count is harmless — batchUpdate is atomic per call
    # but we chain safely by deleting a generous number, then adding fresh.
    for _ in range(10):
        requests.append({
            "deleteConditionalFormatRule": {"sheetId": tab_gid, "index": 0},
        })

    # Conditional format rules on Status column H (status_col).
    status_range = {
        "sheetId": tab_gid,
        "startRowIndex": 1,        # skip header
        "endRowIndex": 100000,     # well past any realistic row count
        "startColumnIndex": status_col,
        "endColumnIndex": status_col + 1,
    }
    for status_text, bg in STATUS_COLOURS.items():
        fg = BLACK if status_text in STATUS_TEXT_DARK else WHITE
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [status_range],
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_EQ",
                            "values": [{"userEnteredValue": status_text}],
                        },
                        "format": {
                            "backgroundColor": bg,
                            "textFormat": {"foregroundColor": fg, "bold": True},
                        },
                    },
                },
                "index": 0,
            },
        })

    return requests


def apply_formatting(service, spreadsheet_id: str, tab_gid: int) -> None:
    """Best-effort formatting. Silently tolerates `deleteConditionalFormatRule`
    out-of-range errors by issuing them individually instead of batched."""
    # Do the non-delete requests in one batchUpdate, then delete rules one at a
    # time so we can swallow "index out of range" from the extras.
    requests = build_formatting_requests(tab_gid)
    delete_requests = [r for r in requests if "deleteConditionalFormatRule" in r]
    other_requests = [r for r in requests if "deleteConditionalFormatRule" not in r]
    add_rule_requests = [r for r in other_requests if "addConditionalFormatRule" in r]
    setup_requests = [r for r in other_requests if "addConditionalFormatRule" not in r]

    # 1. Delete existing rules one by one (tolerate errors).
    from googleapiclient.errors import HttpError  # noqa: PLC0415
    for req in delete_requests:
        try:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [req]},
            ).execute()
        except HttpError:
            break  # no more rules to delete

    # 2. Apply header / freeze / widths / add-rules in one batch.
    if setup_requests or add_rule_requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": setup_requests + add_rule_requests},
        ).execute()


# --- Setup (one-time wipe + write + format) ---------------------------------

def setup_sheet(
    service,
    *,
    spreadsheet_id: str = SPREADSHEET_ID,
    tab_name: str = DEFAULT_TAB_NAME,
    pipeline: list[dict] | None = None,
) -> dict:
    """Wipe the sheet, write header + all current practices, apply formatting."""
    if pipeline is None:
        raise ValueError("setup_sheet requires `pipeline` (use build_current_pipeline())")

    today = date.today().isoformat()
    pipeline_sorted = sorted(pipeline, key=lambda r: (r["icb"], r["pcn"] or "zzz", r["name"]))
    values = [HEADERS] + [row_to_list(r, today) for r in pipeline_sorted]

    api = service.spreadsheets().values()
    api.clear(spreadsheetId=spreadsheet_id, range=f"'{tab_name}'", body={}).execute()
    result = api.update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    tab_gid = get_tab_gid(service, spreadsheet_id, tab_name)
    apply_formatting(service, spreadsheet_id, tab_gid)
    return result


# --- Append (new ODS only) + status updates ---------------------------------

def append_and_update(
    service,
    *,
    spreadsheet_id: str = SPREADSHEET_ID,
    tab_name: str = DEFAULT_TAB_NAME,
    pipeline: list[dict],
) -> dict:
    """Append new ODS rows; update Status cells for existing rows whose status
    has changed. Never deletes rows.
    """
    existing_values = read_all_values(service, spreadsheet_id, tab_name)
    new_rows, status_updates = diff_against_sheet(pipeline, existing_values)

    today = date.today().isoformat()
    values_api = service.spreadsheets().values()
    summary = {"appended": 0, "status_updated": 0, "tab": tab_name}

    # 1. Append new ODS rows
    if new_rows:
        # Preserve input pipeline ordering — insert order in sheet is arbitrary
        # anyway, user can sort manually. Sort new rows by ICB for neatness.
        new_rows_sorted = sorted(new_rows, key=lambda r: (r["icb"], r["pcn"] or "zzz", r["name"]))
        rows_to_append = [row_to_list(r, today) for r in new_rows_sorted]
        values_api.append(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows_to_append},
        ).execute()
        summary["appended"] = len(rows_to_append)

    # 2. Update changed-status cells via batchUpdate (one request per range).
    if status_updates:
        status_col_letter = _col_letter(STATUS_COL_IDX)
        data = [
            {
                "range": f"'{tab_name}'!{status_col_letter}{row_idx}",
                "values": [[new_status]],
            }
            for row_idx, _ods, new_status in status_updates
        ]
        values_api.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": data},
        ).execute()
        summary["status_updated"] = len(status_updates)

    return summary


# --- Entrypoint -------------------------------------------------------------

def main() -> None:
    setup_mode = "--setup" in sys.argv
    dry_run = "--dry-run" in sys.argv

    inputs = load_inputs()
    sicbl = SicblCache(SICBL_CACHE)
    pipeline, errors = build_current_pipeline(
        practices=inputs["practices"],
        waitlist=inputs["waitlist"],
        live_all=inputs["live_all"],
        live_full=inputs["live_full"],
        onboarding=inputs["onboarding"],
        sicbl_lookup=sicbl,
        frimley_map=inputs["frimley_map"],
    )
    by_status: dict[str, int] = defaultdict(int)
    for r in pipeline:
        by_status[r["status"]] += 1
    print(f"Current pipeline: {len(pipeline)} practices — "
          + ", ".join(f"{n} {s}" for s, n in sorted(by_status.items())))
    if errors:
        print(f"[!] {len(errors)} unresolved splits:")
        for e in errors:
            print("   ", e)

    if dry_run:
        mode = "SETUP (wipe+rewrite)" if setup_mode else "APPEND"
        print(f"Dry-run ({mode}). First 3 rows of pipeline:")
        for r in pipeline[:3]:
            print("   ", row_to_list(r, date.today().isoformat()))
        return

    service = _build_sheets_service()

    if setup_mode:
        print("Running SETUP: wiping sheet and rewriting with formatting...")
        result = setup_sheet(service, pipeline=pipeline)
        print(f"  Wrote range: {result.get('updatedRange')}  "
              f"({result.get('updatedRows')} rows)")
        print("  Formatting applied: header styled, row frozen, column widths, "
              "conditional colour rules on Status column.")
    else:
        print("Running APPEND: reading existing sheet, diffing...")
        summary = append_and_update(service, pipeline=pipeline)
        print(f"  Appended {summary['appended']} new practices.")
        print(f"  Updated status on {summary['status_updated']} existing practices.")

    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
