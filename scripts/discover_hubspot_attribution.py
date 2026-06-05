"""
Phase 0 discovery: inventory HubSpot properties + sample one Live practice's
contact/engagement data, so we can shape the attribution data model.

Output: docs/hubspot_discovery.md

Usage:
    HUBSPOT_API_TOKEN=pat-eu1-... python3 scripts/discover_hubspot_attribution.py

Token must be EU1 (pat-eu1-*) — this script targets api-eu1.hubapi.com.
The existing scripts/refresh_data.py targets US (api.hubapi.com); they are
independent and will not interfere.

Required token scopes:
    crm.objects.contacts.read
    crm.objects.companies.read
    crm.schemas.contacts.read
    crm.schemas.companies.read
    crm.objects.deals.read              (optional — for deal-stage discovery)
    sales-email-read                    (for email engagements)
    crm.objects.engagements.read        (calls, meetings, notes, tasks)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HUBSPOT_BASE = "https://api-eu1.hubapi.com"
MAX_RETRIES = 3
BACKOFF_BASE = 1.5

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "docs" / "hubspot_discovery.md"


def hs_request(method, endpoint, data=None):
    token = os.environ.get("HUBSPOT_API_TOKEN", "")
    if not token:
        print("ERROR: Set HUBSPOT_API_TOKEN")
        sys.exit(1)

    url = f"{HUBSPOT_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = json.dumps(data).encode() if data else None

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            if e.code == 429 or 500 <= e.code < 600:
                last_error = f"HTTP {e.code}: {body[:200]}"
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
                    continue
            print(f"  HubSpot {method} {endpoint} -> {e.code}: {body[:300]}")
            raise
        except urllib.error.URLError as e:
            last_error = f"URLError: {e}"
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            raise
    raise RuntimeError(f"HubSpot request failed: {last_error}")


# ----- Property inventory --------------------------------------------------


def list_properties(object_type):
    result = hs_request("GET", f"/crm/v3/properties/{object_type}")
    return result.get("results", [])


def flag_attribution_relevant(prop):
    """Heuristic — name/label suggests source/attribution/lifecycle/lead value."""
    keywords = (
        "source", "channel", "origin", "lead", "referr", "webinar", "campaign",
        "partner", "lifecycle", "stage", "owner", "first", "latest",
        "originating", "analytics", "utm", "attribution",
    )
    blob = (prop.get("name", "") + " " + prop.get("label", "")).lower()
    return any(k in blob for k in keywords)


# ----- Sample practice deep dive ------------------------------------------


def search_company_by_ods(ods_code):
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "practice_code", "operator": "EQ", "value": ods_code}
        ]}],
        "properties": [
            "name", "practice_code", "ods_unique", "organisation_type",
            "lifecyclestage", "hs_lead_status", "hubspot_owner_id", "createdate",
            "industry", "type", "domain",
        ],
        "limit": 5,
    }
    return hs_request("POST", "/crm/v3/objects/companies/search", body).get("results", [])


def get_company_contacts(company_id):
    endpoint = f"/crm/v4/objects/companies/{company_id}/associations/contacts"
    return hs_request("GET", endpoint).get("results", [])


def batch_read_contacts(contact_ids, properties):
    if not contact_ids:
        return []
    body = {
        "inputs": [{"id": cid} for cid in contact_ids],
        "properties": properties,
    }
    return hs_request("POST", "/crm/v3/objects/contacts/batch/read", body).get("results", [])


def get_engagements_for_contact(contact_id, engagement_type):
    """Search engagements (emails/calls/meetings/notes) associated to a contact."""
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": f"associations.contact", "operator": "EQ", "value": str(contact_id)},
        ]}],
        "limit": 50,
        "sorts": [{"propertyName": "hs_timestamp", "direction": "DESCENDING"}],
        "properties": ["hs_timestamp", "hs_engagement_type", "hubspot_owner_id"],
    }
    try:
        return hs_request("POST", f"/crm/v3/objects/{engagement_type}/search", body).get("results", [])
    except urllib.error.HTTPError as e:
        return [{"_error": f"{e.code}"}]


# ----- Report --------------------------------------------------------------


def render_markdown(contact_props, company_props, sample):
    lines = []
    lines.append("# HubSpot Attribution Discovery — Phase 0")
    lines.append("")
    lines.append(f"_Generated by `scripts/discover_hubspot_attribution.py`. EU1 portal._")
    lines.append("")

    # Property sections
    for title, props in [("Contact", contact_props), ("Company", company_props)]:
        lines.append(f"## {title} properties — attribution-relevant")
        lines.append("")
        flagged = [p for p in props if flag_attribution_relevant(p)]
        custom_flagged = [p for p in flagged if not p.get("hubspotDefined", True)]
        std_flagged = [p for p in flagged if p.get("hubspotDefined", True)]

        lines.append(f"**Custom ({len(custom_flagged)}):**")
        if custom_flagged:
            lines.append("")
            lines.append("| name | label | type | options |")
            lines.append("|---|---|---|---|")
            for p in custom_flagged:
                opts = ",".join(o.get("value", "") for o in (p.get("options") or [])[:8])
                if len(p.get("options") or []) > 8:
                    opts += ",..."
                lines.append(f"| `{p['name']}` | {p.get('label','')} | {p['type']} | {opts} |")
        else:
            lines.append("_None._")
        lines.append("")

        lines.append(f"**Standard (HubSpot-defined) ({len(std_flagged)}):**")
        lines.append("")
        for p in std_flagged:
            lines.append(f"- `{p['name']}` — {p.get('label','')} ({p['type']})")
        lines.append("")
        lines.append(f"_Total {title.lower()} properties scanned: {len(props)}._")
        lines.append("")

    # Sample practice
    lines.append("## Sample Live practice deep-dive")
    lines.append("")
    lines.append(f"**ODS:** `{sample['ods']}` — {sample['name']}")
    lines.append("")
    if sample.get("error"):
        lines.append(f"_Error:_ {sample['error']}")
        return "\n".join(lines)

    if not sample.get("companies"):
        lines.append("_No HubSpot company found matching this `practice_code`._")
        return "\n".join(lines)

    for company in sample["companies"]:
        lines.append(f"### Company {company['id']}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(company.get("properties", {}), indent=2, default=str))
        lines.append("```")
        lines.append("")
        lines.append(f"**Associated contacts:** {len(company.get('contacts', []))}")
        for c in company.get("contacts", []):
            lines.append(f"- Contact `{c['id']}`")
            lines.append("")
            lines.append("  ```json")
            lines.append("  " + json.dumps(c.get("properties", {}), indent=2, default=str).replace("\n", "\n  "))
            lines.append("  ```")
            lines.append("")
            lines.append(f"  **Engagement counts:**")
            for et, items in (c.get("engagements") or {}).items():
                err = items[0].get("_error") if items and isinstance(items[0], dict) and "_error" in items[0] else None
                if err:
                    lines.append(f"  - {et}: error {err}")
                else:
                    lines.append(f"  - {et}: {len(items)} (showing most-recent timestamps below)")
                    for it in items[:3]:
                        ts = (it.get("properties") or {}).get("hs_timestamp", "?")
                        lines.append(f"    - {ts}")
        lines.append("")
    return "\n".join(lines)


# ----- Main ----------------------------------------------------------------


def main():
    print("=== Phase 0: HubSpot Attribution Discovery ===")
    print()

    print("Listing contact properties...")
    contact_props = list_properties("contacts")
    print(f"  {len(contact_props)} total")

    print("Listing company properties...")
    company_props = list_properties("companies")
    print(f"  {len(company_props)} total")

    # Pick a Live practice to deep-dive on.
    # Use J82122 (Alma Road) — most recent Live promotion per repo history.
    sample_ods = os.environ.get("SAMPLE_ODS", "J82122")
    practices_geocoded = json.loads((REPO_ROOT / "public/data/practices_geocoded.json").read_text())
    practice = next((p for p in practices_geocoded if p.get("ods", "").upper() == sample_ods), None)
    sample = {
        "ods": sample_ods,
        "name": practice["name"] if practice else "(unknown)",
        "companies": [],
        "error": None,
    }

    print(f"Searching HubSpot company by practice_code={sample_ods}...")
    try:
        companies = search_company_by_ods(sample_ods)
        print(f"  {len(companies)} company match(es)")
        sample["companies"] = companies
    except Exception as e:
        sample["error"] = str(e)
        print(f"  ERROR: {e}")

    # For each matched company, fetch contacts + engagements
    contact_props_to_pull = [
        "firstname", "lastname", "email", "jobtitle",
        "lifecyclestage", "hs_lead_status",
        "hubspot_owner_id", "createdate",
        "hs_analytics_source", "hs_analytics_source_data_1", "hs_analytics_source_data_2",
        "hs_latest_source", "hs_latest_source_data_1", "hs_latest_source_data_2",
    ]

    for company in sample["companies"]:
        cid = company["id"]
        print(f"  -> contacts for company {cid}...")
        try:
            assocs = get_company_contacts(cid)
            contact_ids = [a["toObjectId"] for a in assocs][:5]  # cap at 5 per company
            contacts = batch_read_contacts(contact_ids, contact_props_to_pull)
        except Exception as e:
            print(f"    contacts error: {e}")
            contacts = []
        for c in contacts:
            engagements = {}
            for et in ("emails", "calls", "meetings", "notes"):
                try:
                    engagements[et] = get_engagements_for_contact(c["id"], et)
                    time.sleep(0.15)
                except Exception as e:
                    engagements[et] = [{"_error": str(e)}]
            c["engagements"] = engagements
        company["contacts"] = contacts

    md = render_markdown(contact_props, company_props, sample)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(md)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
