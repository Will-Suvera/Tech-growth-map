#!/usr/bin/env python3
"""Push the "Expansion Contacts" tab: non-live practices near a live one,
with Partner/Manager contact details for outreach.

Two tiers (a practice lands in the highest tier that applies):

  Tier 1 - PCN : practice shares a PCN with a live practice.
  Tier 2 - ICB : practice shares a (post-merger) ICB with a live practice.

Practices that are themselves live are excluded — this tab is the outreach
ring AROUND the live estate. One row per contact (mail-merge friendly:
separate First name / Last name / Email columns); a practice whose HubSpot
company has no matching contact still gets one row with blank contact cells.
Contacts match when their jobtitle contains "partner" OR "manager"
(GP Partner, Managing Partner, Practice Manager, Business Manager, ...).

Target sheet/tab: the sales-artefacts spreadsheet (same as Sheet1 /
Expansion Hitlist / Live Practices), tab "Expansion Contacts", full rewrite
each run with a refreshed-at stamp in A1.

Run:  python3 pipeline/push_expansion_contacts_to_sheet.py [--dry-run]
Auth: GOOGLE_SHEETS_SA_JSON(_PATH) or .secrets key (see push_to_sheets), and
      HUBSPOT_API_TOKEN for the contact sweep (skipped with a warning if
      unset — the tab still refreshes with blank contact columns).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import push_to_sheets as pts  # noqa: E402
from hubspot_partners import (  # noqa: E402
    _clean, _company_contacts, _format_name, _read_contacts,
    _search_companies_by_ods,
)
from icb_mapper import SicblCache, UnresolvableSplit, resolve_icb  # noqa: E402
from ods_pcn import OdsPcnError, fetch_pcn_membership  # noqa: E402

TAB_NAME = "Expansion Contacts"
HEADERS = [
    "Tier",
    "Practice name",
    "ODS code",
    "Status",
    "PCN",
    "Post-merger ICB",
    "Patients",
    "Live anchor",
    "First name",
    "Last name",
    "Job title",
    "Email",
]
TIER_COL_IDX = HEADERS.index("Tier")
TIER1 = "Tier 1 - PCN"
TIER2 = "Tier 2 - ICB"

CONTACT_TITLE_TOKENS = ("partner", "manager")


def _resolve_icb_soft(p: dict, sicbl_lookup, frimley_map) -> str:
    try:
        return resolve_icb(p.get("icb", ""), p["ods"].upper(),
                           sicbl_lookup=sicbl_lookup, frimley_map=frimley_map)
    except UnresolvableSplit:
        return p.get("icb", "")


def build_targets(inputs: dict, sicbl_lookup, pcn_map: dict[str, dict]) -> list[dict]:
    """Classify every non-live practice into tier 1/2 (or drop it).

    PCN + ICB come from the current ODS ePCN mapping (`pcn_map`, keyed on
    ODS code) — NOT the stale legacy fields in practices_geocoded.json.
    Practices absent from the mapping (not in any PCN, or the fetch failed)
    fall back to the legacy fields + merger relabel for ICB only."""
    live_all = {c.upper() for c in inputs["live_all"]}
    waitlist = {c.upper() for c in inputs["waitlist"]}
    onboarding = {c.upper() for c in inputs["onboarding"]}

    def locate(p: dict) -> tuple[str, str, str]:
        """(pcn_code, pcn_name, icb) for a practice — ODS-first."""
        m = pcn_map.get(p["ods"].upper())
        if m:
            return m["pcn_code"], m["pcn_name"], m["icb"]
        return (
            (p.get("pcn_code") or "").upper(),
            p.get("pcn_name", ""),
            _resolve_icb_soft(p, sicbl_lookup, inputs["frimley_map"]),
        )

    live_pcns: dict[str, list[str]] = {}   # pcn_code -> live practice names
    live_icb_counts: dict[str, int] = {}
    for p in inputs["practices"]:
        ods = p["ods"].upper()
        if ods not in live_all:
            continue
        pcn_code, _pcn_name, icb = locate(p)
        if pcn_code:
            live_pcns.setdefault(pcn_code, []).append(p["name"])
        if icb:
            live_icb_counts[icb] = live_icb_counts.get(icb, 0) + 1

    targets = []
    for p in inputs["practices"]:
        ods = p["ods"].upper()
        if ods in live_all:
            continue
        pcn_code, pcn_name, icb = locate(p)
        if pcn_code and pcn_code in live_pcns:
            tier = TIER1
            anchor = ", ".join(sorted(live_pcns[pcn_code]))
        elif icb and icb in live_icb_counts:
            tier = TIER2
            n = live_icb_counts[icb]
            anchor = f"{n} live practice{'s' if n != 1 else ''} in ICB"
        else:
            continue
        if ods in onboarding:
            status = "Onboarding"
        elif ods in waitlist:
            status = "Signed up"
        else:
            status = "Not signed up"
        targets.append({
            "tier": tier,
            "name": p["name"],
            "ods": ods,
            "status": status,
            "pcn": pcn_name,
            "icb": icb,
            "patients": p.get("patients", ""),
            "anchor": anchor,
        })
    targets.sort(key=lambda t: (t["tier"], t["pcn"] or "zzz", t["name"]))
    return targets


def fetch_contacts_by_ods(ods_codes) -> dict[str, list[dict]]:
    """{ODS: [{first, last, jobtitle, email}, ...]} for contacts whose
    jobtitle contains any of CONTACT_TITLE_TOKENS. Same HubSpot walk as
    hubspot_partners.fetch_partners_by_ods, wider title filter, and names
    kept as separate first/last fields."""
    ods_set = {str(o).strip().upper() for o in ods_codes if o and str(o).strip()}
    if not ods_set:
        return {}
    ods_to_company = _search_companies_by_ods(ods_set)
    company_contacts = _company_contacts(set(ods_to_company.values()))
    all_ids = {cid for cids in company_contacts.values() for cid in cids}
    contacts = _read_contacts(all_ids)

    result: dict[str, list[dict]] = {}
    for ods, comp_id in ods_to_company.items():
        rows: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for cid in company_contacts.get(comp_id, []):
            props = contacts.get(cid)
            if not props:
                continue
            title = (props.get("jobtitle") or "").strip()
            if not any(tok in title.lower() for tok in CONTACT_TITLE_TOKENS):
                continue
            first = _format_name(_clean(props.get("firstname")))
            last = _format_name(_clean(props.get("lastname")))
            email = (props.get("email") or "").strip()
            if not first and not last and not email:
                continue
            key = (first.lower(), last.lower(), email.lower())
            if key in seen:
                continue
            seen.add(key)
            rows.append({"first": first, "last": last, "jobtitle": title, "email": email})
        if rows:
            result[ods] = rows
    return result


def build_rows(targets: list[dict], contacts_by_ods: dict[str, list[dict]]) -> list[list[Any]]:
    rows = []
    for t in targets:
        practice_cells = [t["tier"], t["name"], t["ods"], t["status"],
                          t["pcn"], t["icb"], t["patients"], t["anchor"]]
        contacts = contacts_by_ods.get(t["ods"]) or [{}]
        for c in contacts:
            rows.append(practice_cells + [
                c.get("first", ""), c.get("last", ""),
                c.get("jobtitle", ""), c.get("email", ""),
            ])
    return rows


def build_formatting_requests(tab_gid: int) -> list[dict]:
    """Stamp row + navy header + freeze + widths + tier colour rules.
    Layout matches the Live Practices tab: row 1 stamp, row 2 headers."""
    ncols = len(HEADERS)
    tier_rule = lambda value, bg: {"addConditionalFormatRule": {"rule": {  # noqa: E731
        "ranges": [{"sheetId": tab_gid, "startRowIndex": 2,
                    "startColumnIndex": TIER_COL_IDX,
                    "endColumnIndex": TIER_COL_IDX + 1}],
        "booleanRule": {
            "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": value}]},
            "format": {"backgroundColor": pts._hex_to_rgbf(bg),
                       "textFormat": {"bold": True,
                                      "foregroundColor": pts._hex_to_rgbf("#FFFFFF")}}}},
        "index": 0}}
    return [
        {"repeatCell": {
            "range": {"sheetId": tab_gid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": ncols},
            "cell": {"userEnteredFormat": {"textFormat": {
                "italic": True, "foregroundColor": pts._hex_to_rgbf("#6B7280")}}},
            "fields": "userEnteredFormat.textFormat"}},
        {"repeatCell": {
            "range": {"sheetId": tab_gid, "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": 0, "endColumnIndex": ncols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": pts._hex_to_rgbf("#1E3A5F"),
                "textFormat": {"bold": True, "foregroundColor": pts._hex_to_rgbf("#FFFFFF")}}},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": tab_gid, "gridProperties": {"frozenRowCount": 2}},
            "fields": "gridProperties.frozenRowCount"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": tab_gid, "dimension": "COLUMNS",
                      "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 280}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": tab_gid, "dimension": "COLUMNS",
                      "startIndex": 4, "endIndex": 6},
            "properties": {"pixelSize": 230}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": tab_gid, "dimension": "COLUMNS",
                      "startIndex": 7, "endIndex": 8},
            "properties": {"pixelSize": 260}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": tab_gid, "dimension": "COLUMNS",
                      "startIndex": 11, "endIndex": 12},
            "properties": {"pixelSize": 240}, "fields": "pixelSize"}},
        tier_rule(TIER1, "#15803D"),
        tier_rule(TIER2, "#F59E0B"),
    ]


def push(service, rows: list[list[Any]], *, spreadsheet_id: str = pts.SPREADSHEET_ID) -> None:
    try:
        tab_gid = pts.get_tab_gid(service, spreadsheet_id, TAB_NAME)
    except ValueError:
        resp = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": TAB_NAME}}}]},
        ).execute()
        tab_gid = resp["replies"][0]["addSheet"]["properties"]["sheetId"]

    stamp = datetime.now(timezone.utc).strftime("Last refreshed: %Y-%m-%d %H:%M UTC")
    values = [[stamp], HEADERS] + rows

    api = service.spreadsheets().values()
    api.clear(spreadsheetId=spreadsheet_id, range=f"'{TAB_NAME}'", body={}).execute()
    api.update(
        spreadsheetId=spreadsheet_id,
        range=f"'{TAB_NAME}'!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    from googleapiclient.errors import HttpError  # noqa: PLC0415
    while True:
        try:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"deleteConditionalFormatRule": {"sheetId": tab_gid, "index": 0}}]},
            ).execute()
        except HttpError:
            break
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": build_formatting_requests(tab_gid)},
    ).execute()


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    inputs = pts.load_inputs()
    sicbl = SicblCache(pts.SICBL_CACHE)
    try:
        pcn_map = fetch_pcn_membership()
        print(f"ODS ePCN mapping: {len(pcn_map)} practices with a current PCN.")
    except OdsPcnError as e:
        print(f"[!] ePCN fetch failed — falling back to legacy PCN fields: {e}")
        pcn_map = {}
    targets = build_targets(inputs, sicbl, pcn_map)
    sicbl.save()
    n1 = sum(1 for t in targets if t["tier"] == TIER1)
    print(f"Targets: {len(targets)} ({n1} {TIER1}, {len(targets) - n1} {TIER2})")

    contacts_by_ods: dict[str, list[dict]] = {}
    try:
        print("Fetching Partner/Manager contacts from HubSpot "
              f"for {len(targets)} practices (takes a few minutes)...")
        contacts_by_ods = fetch_contacts_by_ods([t["ods"] for t in targets])
        total = sum(len(v) for v in contacts_by_ods.values())
        print(f"  {total} contacts across {len(contacts_by_ods)} practices.")
    except Exception as e:  # fail soft: tab still refreshes without contacts
        print(f"[!] HubSpot contact fetch failed — contact columns left blank: {e}")

    rows = build_rows(targets, contacts_by_ods)
    if dry_run:
        print(f"Dry-run. {len(rows)} rows; first 3:")
        for r in rows[:3]:
            print("   ", r)
        return

    service = pts._build_sheets_service()
    push(service, rows)
    print(f"Wrote {len(rows)} rows to '{TAB_NAME}'.")


if __name__ == "__main__":
    main()
