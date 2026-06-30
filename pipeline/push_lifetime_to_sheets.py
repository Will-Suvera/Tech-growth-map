#!/usr/bin/env python3
"""Push lifetime_customers.csv to the 'Lifetime customers' Google Sheet.

Writes, in order:
  Row 1  — headline title (e.g. "Suvera lifetime customers — 317 GP practices")
  Row 2  — blank spacer
  Row 3  — column header
  Row 4+ — one row per practice (+ aggregate count-only deals at the bottom)

Then applies formatting: merged navy title, styled header, frozen header rows,
sensible column widths.

This is a full regenerate-and-overwrite of the target tab — the sheet is a
generated artefact of `build_lifetime_customers.py`, so the CSV is the source of
truth. Run `build_lifetime_customers.py` first.

Auth: service account, same resolution order as push_to_sheets.py
  1. GOOGLE_SHEETS_SA_JSON           (inline JSON)
  2. GOOGLE_SHEETS_SA_JSON_PATH      (path)
  3. .secrets/nhsjobscraper-sa.json  (default local)

The service account (willgao@nhsjobscraper.iam.gserviceaccount.com) must be
shared as Editor on the target sheet.

Usage:
  python3 pipeline/push_lifetime_to_sheets.py            # writes with default headline
  python3 pipeline/push_lifetime_to_sheets.py --dry-run  # print plan, no write
  HEADLINE="..." python3 pipeline/push_lifetime_to_sheets.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "lifetime_customers.csv"

SPREADSHEET_ID = "1yk8Ft6r2lqgal8YV99K6XZ-iY2EcPzeIEUlDomE5pa8"
TARGET_GID = 1646405252  # tab from the shared URL; falls back to first sheet

DEFAULT_HEADLINE = (
    "Suvera lifetime customers — 317 GP practices "
    "(304 individually identified + 13 from 2 aggregate ICB/PCN deals)"
)

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _hex(h):
    h = h.lstrip("#")
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


HEADER_BG = _hex("1E2A4A")
TITLE_BG = _hex("0F766E")
WHITE = _hex("FFFFFF")


def load_rows():
    with open(CSV_PATH, newline="") as f:
        return list(csv.reader(f))


def _service_account_info():
    inline = os.environ.get("GOOGLE_SHEETS_SA_JSON")
    if inline:
        return json.loads(inline)
    path_env = os.environ.get("GOOGLE_SHEETS_SA_JSON_PATH")
    path = Path(path_env) if path_env else (ROOT / ".secrets" / "nhsjobscraper-sa.json")
    if not path.exists():
        raise FileNotFoundError(f"No service-account credentials at {path}")
    return json.loads(path.read_text())


def _service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_info(_service_account_info(), scopes=SHEETS_SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _resolve_tab(service):
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = meta.get("sheets", [])
    for s in sheets:
        if s["properties"].get("sheetId") == TARGET_GID:
            return s["properties"]["title"], TARGET_GID
    # fall back to first tab
    p = sheets[0]["properties"]
    return p["title"], p["sheetId"]


def main():
    dry = "--dry-run" in sys.argv
    headline = os.environ.get("HEADLINE", DEFAULT_HEADLINE)
    csv_rows = load_rows()
    header, data = csv_rows[0], csv_rows[1:]
    n_cols = len(header)

    values = [[headline]] + [[""]] + [header] + data

    print(f"Headline : {headline}")
    print(f"Columns  : {n_cols}")
    print(f"Data rows: {len(data)}")
    if dry:
        print("Dry-run — first 3 data rows:")
        for r in data[:3]:
            print("   ", r)
        return

    service = _service()
    tab, gid = _resolve_tab(service)
    print(f"Target   : {SPREADSHEET_ID} tab {tab!r} (gid {gid})")

    api = service.spreadsheets().values()
    api.clear(spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'", body={}).execute()
    res = api.update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{tab}'!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    print(f"  Wrote {res.get('updatedRows')} rows.")

    requests = [
        # Merge + style the title row across all columns
        {"mergeCells": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                                  "startColumnIndex": 0, "endColumnIndex": n_cols},
                        "mergeType": "MERGE_ALL"}},
        {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                                  "startColumnIndex": 0, "endColumnIndex": n_cols},
                        "cell": {"userEnteredFormat": {
                            "backgroundColor": TITLE_BG,
                            "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 13},
                            "verticalAlignment": "MIDDLE"}},
                        "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)"}},
        # Style the column-header row (row 3, index 2)
        {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 2, "endRowIndex": 3,
                                  "startColumnIndex": 0, "endColumnIndex": n_cols},
                        "cell": {"userEnteredFormat": {
                            "backgroundColor": HEADER_BG,
                            "textFormat": {"foregroundColor": WHITE, "bold": True}}},
                        "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
        # Freeze title + spacer + header (3 rows)
        {"updateSheetProperties": {"properties": {"sheetId": gid,
                                                  "gridProperties": {"frozenRowCount": 3}},
                                   "fields": "gridProperties.frozenRowCount"}},
    ]
    widths = {0: 290, 1: 280, 2: 320, 3: 80, 4: 90, 5: 110, 6: 360}
    for col, w in widths.items():
        if col < n_cols:
            requests.append({"updateDimensionProperties": {
                "range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
                "properties": {"pixelSize": w}, "fields": "pixelSize"}})

    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": requests}).execute()
    print("  Formatting applied (title merged/styled, header styled, 3 rows frozen, widths).")


if __name__ == "__main__":
    main()
