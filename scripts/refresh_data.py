#!/usr/bin/env python3
"""
Automated data refresh for the GP Practice Growth Dashboard.

Fetches and updates:
1. All active GP practices in England from NHS ODS API (filtered to real GP practices)
2. Geocodes postcodes via postcodes.io
3. Waitlist ODS codes from HubSpot list 1535 (the segment surfaced at
   https://app-eu1.hubspot.com/contacts/143576889/objectLists/1535)
4. Expands PCN contacts to their constituent GP practices

Requires:
    HUBSPOT_API_TOKEN env var (set in .env file or repo secrets)

Usage:
    python3 refresh_data.py              # Full refresh (practices + waitlist)
    python3 refresh_data.py --waitlist   # Waitlist only (faster, runs in CI every 5 min)
    python3 refresh_data.py --practices  # Practices only
"""

import json
import os
import time
import sys
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "public" / "data"
HUBSPOT_BASE = "https://api.hubapi.com"

# Google Sheets published CSV URL for the onboarding tracker.
# Column G (idx 6) = Status, Column H (idx 7) = ODS Code.
# Practices with Status = "Live" are merged into live_customers.json.
GSHEET_BASE = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRa6zIwdwnNSfjjU_gVYdZ7Pm6Sy6XWsyVe0gR6AZP55IzeVW9"
    "qisAUb0Hvo4Nr7qdGhWLnK1l4SDnl/pub?output=csv"
)
GSHEET_SAAS_URL = GSHEET_BASE + "&gid=0"           # SaaS tab
GSHEET_VC_URL = GSHEET_BASE + "&gid=993386637"     # VC practices tab

# Omni exports → Google Sheets (scheduled daily from Omni)
GSHEET_RECALLS_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRPwtiHacXeuoL8We31VrMDhDKb7ttfcGnz0WN1nfatH-jlVRiGWPoiaKZ9s"
    "_Nkso943XRN2WtR3x3j/pub?output=csv"
)
GSHEET_BLOODS_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vQ1W9ZAe0G1UOMPj48fHpV3-buUhxpLvn3IosfQ1y4Q2TqCOwjXSZj5BtQ"
    "_3UoI-G7um15v9FGvF_X8/pub?output=csv"
)

# Refuse to overwrite waitlist_ods.json if the new file would be more than
# this fraction smaller than the existing one. Stops a partial HubSpot
# response from silently erasing real waitlist entries.
WAITLIST_SHRINK_LIMIT = 0.10  # 10%

# HTTP retry config for HubSpot calls.
HUBSPOT_MAX_RETRIES = 3
HUBSPOT_BACKOFF_BASE = 1.5  # seconds; doubles each attempt


def load_live_customers():
    """Load live customer ODS codes (single source of truth, includes full-planner tier)."""
    with open(DATA_DIR / "live_customers.json") as f:
        return set(json.load(f))


LIVE_CUSTOMER_ODS = load_live_customers()


def load_env():
    """Load .env file if present."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


def http_get_json(url):
    """GET a URL and return parsed JSON. Used for the public NHS ODS API."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


# ============================================================
# NHS ODS API - Practice Data
# ============================================================

def fetch_ods_practices():
    """Fetch all active GP practices from the NHS ODS API."""
    print("=== Fetching GP Practices from ODS API ===")
    all_orgs = []
    offset = 0
    page = 1

    while True:
        url = (
            "https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations"
            f"?PrimaryRoleId=RO177&Status=Active&Limit=1000&Offset={offset}"
        )
        print(f"  Page {page} (offset {offset})...")
        try:
            data = http_get_json(url)
        except urllib.error.HTTPError as e:
            print(f"  ODS API HTTP {e.code}: {e.read().decode()[:200]}")
            raise
        except urllib.error.URLError as e:
            print(f"  ODS API connection error: {e}")
            raise

        orgs = data.get("Organisations", [])
        all_orgs.extend(orgs)

        if len(orgs) < 1000:
            break
        offset += 1000
        page += 1

    print(f"  Total fetched: {len(all_orgs)}")
    return all_orgs


def geocode_postcodes(postcodes):
    """Bulk geocode postcodes using postcodes.io API."""
    print(f"\n=== Geocoding {len(postcodes)} Postcodes ===")
    postcode_coords = {}
    batch_size = 100

    for i in range(0, len(postcodes), batch_size):
        batch = postcodes[i:i + batch_size]
        batch_num = i // batch_size + 1

        payload = json.dumps({"postcodes": batch}).encode()
        req = urllib.request.Request(
            "https://api.postcodes.io/postcodes",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            for result in data.get("result", []):
                if result.get("result"):
                    r = result["result"]
                    postcode_coords[result["query"]] = {
                        "lat": r["latitude"],
                        "lng": r["longitude"],
                        "country": r.get("country", ""),
                    }
        except Exception as e:
            print(f"  Error batch {batch_num}: {e}")

        if batch_num % 20 == 0:
            print(f"  {len(postcode_coords)} geocoded...")
        time.sleep(0.1)

    print(f"  Geocoded: {len(postcode_coords)}")
    return postcode_coords


def build_practices_dataset(practices, postcode_coords):
    """Build filtered England-only GP practice dataset (no Y-codes or W-codes)."""
    print("\n=== Building England GP Practice Dataset ===")

    england_coords = {
        k: v for k, v in postcode_coords.items() if v["country"] == "England"
    }

    result = []
    for p in practices:
        ods = p["OrgId"]
        pc = p.get("PostCode", "").strip()

        if ods.startswith("Y") or ods.startswith("W"):
            continue

        if pc in england_coords:
            result.append({
                "ods": ods,
                "name": p["Name"],
                "postcode": pc,
                "lat": england_coords[pc]["lat"],
                "lng": england_coords[pc]["lng"],
            })

    print(f"  England GP practices (excl Y/W codes): {len(result)}")
    return result


def refresh_practices():
    """Full practices refresh pipeline."""
    practices = fetch_ods_practices()

    unique_postcodes = list(set(
        p.get("PostCode", "").strip()
        for p in practices if p.get("PostCode", "")
    ))
    postcode_coords = geocode_postcodes(unique_postcodes)

    dataset = build_practices_dataset(practices, postcode_coords)

    output_path = DATA_DIR / "practices_geocoded.json"
    with open(output_path, "w") as f:
        json.dump(dataset, f)
    print(f"\n  Saved {len(dataset)} practices to {output_path}")
    return dataset


# ============================================================
# HubSpot API - Waitlist Data
# ============================================================

def hubspot_request(method, endpoint, data=None):
    """Make an authenticated HubSpot API request with retry on 429/5xx."""
    token = os.environ.get("HUBSPOT_API_TOKEN", "")
    if not token or token == "your-hubspot-private-app-token-here":
        print("ERROR: Set HUBSPOT_API_TOKEN in .env file or repo secrets")
        sys.exit(1)

    url = f"{HUBSPOT_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if data:
        payload = json.dumps(data).encode()
    else:
        payload = None

    last_error = None
    for attempt in range(1, HUBSPOT_MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            # Retry on 429 (rate limit) and 5xx (server). Fail fast on 4xx.
            if e.code == 429 or 500 <= e.code < 600:
                last_error = f"HTTP {e.code}: {body[:200]}"
                if attempt < HUBSPOT_MAX_RETRIES:
                    delay = HUBSPOT_BACKOFF_BASE * (2 ** (attempt - 1))
                    print(f"  HubSpot {last_error} — retry {attempt}/{HUBSPOT_MAX_RETRIES} after {delay:.1f}s")
                    time.sleep(delay)
                    continue
            print(f"  HubSpot API error {e.code}: {body[:200]}")
            raise
        except urllib.error.URLError as e:
            last_error = f"URLError: {e}"
            if attempt < HUBSPOT_MAX_RETRIES:
                delay = HUBSPOT_BACKOFF_BASE * (2 ** (attempt - 1))
                print(f"  HubSpot {last_error} — retry {attempt}/{HUBSPOT_MAX_RETRIES} after {delay:.1f}s")
                time.sleep(delay)
                continue
            raise

    raise RuntimeError(f"HubSpot request failed after {HUBSPOT_MAX_RETRIES} attempts: {last_error}")


WAITLIST_LIST_ID = "1535"  # HubSpot list ID for the waitlist


def fetch_waitlist_contacts():
    """Fetch all contacts from HubSpot waitlist list (ID 1535)."""
    print(f"\n=== Fetching Waitlist from HubSpot List {WAITLIST_LIST_ID} ===")

    # Step 1: Get all contact IDs from the list
    contact_ids = []
    after = None
    while True:
        endpoint = f"/crm/v3/lists/{WAITLIST_LIST_ID}/memberships"
        if after:
            endpoint += f"?after={after}"
        result = hubspot_request("GET", endpoint)
        contact_ids.extend(m["recordId"] for m in result.get("results", []))
        after = result.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
        time.sleep(0.1)

    print(f"  List members: {len(contact_ids)}")

    # Step 2: Fetch contact details in batches
    contacts = []
    batch_size = 100
    for i in range(0, len(contact_ids), batch_size):
        batch = contact_ids[i:i + batch_size]
        body = {
            "inputs": [{"id": cid} for cid in batch],
            "properties": ["firstname", "lastname", "email", "company"]
        }
        result = hubspot_request("POST", "/crm/v3/objects/contacts/batch/read", body)
        contacts.extend(result.get("results", []))
        time.sleep(0.2)

    # Filter out internal Suvera contacts and obvious test data.
    # Note: gmail/hotmail are NOT filtered here any more — many real GPs sign
    # up with personal emails. Move filtering into the HubSpot list filter
    # itself for the ideal long-term solution (see docs/hubspot-list-filter.md).
    real_contacts = []
    skip_email_substrings = {"@suvera.co", "@suvera.com", "@searchhog"}
    skip_names = {"test", "sdf", "wer", "qwer", "234", "wee"}

    for c in contacts:
        props = c.get("properties", {})
        email = (props.get("email") or "").lower()
        firstname = (props.get("firstname") or "").lower().strip()
        if any(s in email for s in skip_email_substrings):
            continue
        if firstname in skip_names:
            continue
        real_contacts.append(c)

    print(f"  Real contacts (excl internal Suvera/test): {len(real_contacts)}")
    return real_contacts


def get_contact_company_associations(contact_ids):
    """
    Get company associations for contacts using the v4 batch endpoint.
    Replaces the old per-contact loop (saves ~15s per refresh).
    """
    associations = {}
    if not contact_ids:
        return associations

    batch_size = 100
    for i in range(0, len(contact_ids), batch_size):
        batch = contact_ids[i:i + batch_size]
        body = {"inputs": [{"id": str(cid)} for cid in batch]}
        try:
            result = hubspot_request(
                "POST",
                "/crm/v4/associations/contact/company/batch/read",
                body,
            )
            for entry in result.get("results", []):
                from_id = int(entry.get("from", {}).get("id", 0))
                to_ids = [int(t["toObjectId"]) for t in entry.get("to", [])]
                if from_id and to_ids:
                    associations[from_id] = to_ids
        except Exception as e:
            print(f"  Error fetching association batch {i // batch_size + 1}: {e}")
        time.sleep(0.2)

    return associations


def get_companies_by_ids(company_ids):
    """Fetch company details by IDs in batches."""
    companies = {}
    batch_size = 100

    for i in range(0, len(company_ids), batch_size):
        batch = company_ids[i:i + batch_size]
        body = {
            "inputs": [{"id": str(cid)} for cid in batch],
            "properties": ["name", "practice_code", "ods_unique", "organisation_type"]
        }

        try:
            result = hubspot_request("POST", "/crm/v3/objects/companies/batch/read", body)
            for comp in result.get("results", []):
                companies[int(comp["id"])] = comp.get("properties", {})
        except Exception as e:
            print(f"  Error fetching company batch: {e}")
        time.sleep(0.2)

    return companies


def search_company_by_name(name):
    """Search for a company by name and return its ODS code."""
    body = {
        "query": name,
        "properties": ["name", "practice_code", "ods_unique"],
        "limit": 5,
    }

    try:
        result = hubspot_request("POST", "/crm/v3/objects/companies/search", body)
        for comp in result.get("results", []):
            props = comp.get("properties", {})
            ods = props.get("ods_unique") or props.get("practice_code")
            if ods:
                return ods
    except Exception:
        pass
    return None


# Whitelist: only count practices whose organisation_type explicitly says
# they are a GP practice. Stops federation/PCN/ICB child orgs from inflating
# the waitlist by accident.
GP_PRACTICE_ORG_TYPES = {
    "gp practice", "gp_practice", "gp surgery", "gp", "general practice",
}


def is_gp_practice(props):
    org_type = (props.get("organisation_type") or "").strip().lower()
    return org_type in GP_PRACTICE_ORG_TYPES


def expand_pcn_to_practices(pcn_company_id):
    """Find GP practices associated with a PCN company (whitelist by org type)."""
    ods_codes = []
    try:
        result = hubspot_request(
            "GET",
            f"/crm/v4/objects/companies/{pcn_company_id}/associations/companies"
        )
        child_ids = [r["toObjectId"] for r in result.get("results", [])]

        if child_ids:
            companies = get_companies_by_ids(child_ids)
            for props in companies.values():
                ods = props.get("ods_unique") or props.get("practice_code")
                if ods and is_gp_practice(props):
                    ods_codes.append(ods)
    except Exception as e:
        print(f"  Error expanding PCN {pcn_company_id}: {e}")

    return ods_codes


# ============================================================
# Schema validation
# ============================================================

def validate_waitlist_schema(codes):
    """Schema-check the waitlist before we write it to disk."""
    if not isinstance(codes, list):
        raise ValueError(f"waitlist must be a list, got {type(codes).__name__}")
    if len(codes) < 50:
        raise ValueError(
            f"waitlist suspiciously small ({len(codes)} codes) — refusing to write. "
            f"This usually means HubSpot returned a partial response."
        )
    for c in codes:
        if not isinstance(c, str):
            raise ValueError(f"waitlist entry must be string, got {type(c).__name__}: {c!r}")
        if not (3 <= len(c) <= 10):
            raise ValueError(f"ODS code looks malformed (length): {c!r}")
        if not c.isalnum():
            raise ValueError(f"ODS code looks malformed (non-alnum): {c!r}")


def write_waitlist_safely(new_codes, output_path):
    """
    Write waitlist_ods.json with two safety nets:
      1. Schema validation
      2. Refuse to overwrite if the new file would be >WAITLIST_SHRINK_LIMIT smaller
    """
    sorted_codes = sorted(set(new_codes))
    validate_waitlist_schema(sorted_codes)

    if output_path.exists():
        with open(output_path) as f:
            existing = json.load(f)
        if isinstance(existing, list) and len(existing) > 0:
            shrink = (len(existing) - len(sorted_codes)) / len(existing)
            if shrink > WAITLIST_SHRINK_LIMIT:
                raise RuntimeError(
                    f"Refusing to overwrite waitlist: new file would be "
                    f"{shrink:.1%} smaller ({len(existing)} → {len(sorted_codes)}). "
                    f"Likely a partial HubSpot response. Investigate before forcing."
                )

    with open(output_path, "w") as f:
        json.dump(sorted_codes, f, indent=2)


def refresh_waitlist():
    """Full waitlist refresh pipeline."""
    contacts = fetch_waitlist_contacts()
    contact_ids = [int(c["id"]) for c in contacts]

    # Get company associations for all contacts (batched)
    print(f"\n=== Fetching Company Associations ({len(contact_ids)} contacts) ===")
    associations = get_contact_company_associations(contact_ids)
    print(f"  {len(associations)} contacts have company associations")

    # Get all unique company IDs
    all_company_ids = set()
    for cids in associations.values():
        all_company_ids.update(cids)

    # Fetch company details
    print(f"\n=== Fetching {len(all_company_ids)} Company Details ===")
    companies = get_companies_by_ids(list(all_company_ids))

    # Extract ODS codes and identify PCNs
    waitlist_ods = set()
    pcn_ids = []
    no_ods_companies = []

    for comp_id, props in companies.items():
        ods = props.get("ods_unique") or props.get("practice_code")
        org_type = (props.get("organisation_type") or "").lower()
        name = props.get("name", "")

        if ods and ods.strip():
            waitlist_ods.add(ods.upper())
        elif "pcn" in org_type or "pcn" in name.upper():
            pcn_ids.append(comp_id)
        else:
            no_ods_companies.append((comp_id, name))

    print(f"  Direct ODS codes: {len(waitlist_ods)}")
    print(f"  PCNs to expand: {len(pcn_ids)}")
    print(f"  Companies without ODS: {len(no_ods_companies)}")

    # Expand PCNs to constituent practices
    if pcn_ids:
        print(f"\n=== Expanding {len(pcn_ids)} PCNs ===")
        for pcn_id in pcn_ids:
            pcn_name = companies.get(pcn_id, {}).get("name", pcn_id)
            codes = expand_pcn_to_practices(pcn_id)
            print(f"  {pcn_name}: {len(codes)} practices")
            waitlist_ods.update(c.upper() for c in codes)
            time.sleep(0.2)

    # Search by name for unassociated contacts
    unassociated = [
        c for c in contacts
        if int(c["id"]) not in associations
    ]
    if unassociated:
        print(f"\n=== Searching {len(unassociated)} Unassociated Contacts by Company Name ===")
        for c in unassociated:
            company_name = (c.get("properties", {}).get("company") or "").strip()
            if company_name and company_name.lower() not in ("", "x", "test", "sdf", "wer", "company"):
                ods = search_company_by_name(company_name)
                if ods:
                    waitlist_ods.add(ods.upper())
                    print(f"  {company_name} -> {ods}")
                time.sleep(0.2)

    # Also search by name for companies without ODS codes
    if no_ods_companies:
        print(f"\n=== Searching {len(no_ods_companies)} Companies Without ODS ===")
        for comp_id, name in no_ods_companies:
            if name and "pcn" not in name.upper() and "icb" not in name.upper():
                ods = search_company_by_name(name)
                if ods:
                    waitlist_ods.add(ods.upper())
                    print(f"  {name} -> {ods}")
                time.sleep(0.2)

    # Remove any live customer codes from waitlist (covers both planner
    # and full-planner tiers since they share live_customers.json).
    waitlist_ods -= LIVE_CUSTOMER_ODS

    # Validate + write with shrink-protection
    output_path = DATA_DIR / "waitlist_ods.json"
    write_waitlist_safely(waitlist_ods, output_path)

    # Save the raw contact count so the frontend can display it
    meta_path = DATA_DIR / "waitlist_meta.json"
    with open(meta_path, "w") as f:
        json.dump({"contacts": len(contacts)}, f)

    print(f"\n  Saved {len(waitlist_ods)} waitlist ODS codes to {output_path}")
    print(f"  Saved contact count ({len(contacts)}) to {meta_path}")
    return sorted(waitlist_ods)


def refresh_live_from_google_sheet():
    """
    Fetch live practices from the published Google Sheet and merge into
    live_customers.json. Additive only — never removes existing entries.
    Falls back gracefully if the sheet is unavailable.
    """
    global LIVE_CUSTOMER_ODS

    import csv
    import io

    def fetch_csv(url):
        req = urllib.request.Request(url, headers={"User-Agent": "SuveraRefreshBot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8-sig")

    print("\n=== Fetching Live Customers from Google Sheet ===")
    sheet_live = set()

    # 1. SaaS tab: Column G (idx 6) = Status, Column H (idx 7) = ODS Code
    try:
        raw = fetch_csv(GSHEET_SAAS_URL)
        reader = csv.reader(io.StringIO(raw))
        next(reader, None)  # skip header
        for row in reader:
            status = row[6].strip() if len(row) > 6 else ""
            ods = row[7].strip().upper() if len(row) > 7 else ""
            if status.lower() == "live" and ods:
                sheet_live.add(ods)
        print(f"  SaaS tab: {len(sheet_live)} live practices")
    except Exception as e:
        print(f"  WARN: Could not fetch SaaS tab: {e}")

    # 2. VC practices tab: Column L (idx 11) = Bloods automation ("Done" = live)
    #    No ODS column — match practice names against practices_geocoded.json
    try:
        raw = fetch_csv(GSHEET_VC_URL)
        reader = csv.reader(io.StringIO(raw))
        next(reader, None)  # skip header

        # Build name→ODS lookup from geocoded practices
        with open(DATA_DIR / "practices_geocoded.json") as f:
            practices = json.load(f)
        name_to_ods = {}
        for p in practices:
            name_to_ods[p["name"].lower().strip()] = p["ods"].upper()

        vc_done_ods = set()
        for row in reader:
            bloods = row[11].strip() if len(row) > 11 else ""
            practice_name = row[0].strip() if row else ""
            if bloods.lower() != "done" or not practice_name:
                continue
            # Try exact then substring match
            pname = practice_name.lower()
            ods = name_to_ods.get(pname)
            if not ods:
                for full_name, code in name_to_ods.items():
                    if pname in full_name:
                        ods = code
                        break
            if ods:
                sheet_live.add(ods)
                vc_done_ods.add(ods)
        print(f"  VC tab: {len(vc_done_ods)} done practices (matched by name)")
    except Exception as e:
        print(f"  WARN: Could not fetch VC tab: {e}")
        vc_done_ods = set()

    print(f"  Total from sheets: {len(sheet_live)} live practices")

    # Load existing and merge
    live_path = DATA_DIR / "live_customers.json"
    with open(live_path) as f:
        existing = set(c.upper() for c in json.load(f))

    new_additions = sheet_live - existing
    merged = sorted(existing | sheet_live)

    if new_additions:
        print(f"  Adding {len(new_additions)} new live: {sorted(new_additions)}")
        with open(live_path, "w") as f:
            json.dump(merged, f, indent=2)
        # Update the global set so waitlist refresh excludes them
        LIVE_CUSTOMER_ODS = set(merged)
    else:
        print("  No new live practices from sheet.")

    # VC "Done" practices are Full Planner (all features incl. bloods)
    if vc_done_ods:
        fp_path = DATA_DIR / "live_customers_full_planner.json"
        with open(fp_path) as f:
            existing_fp = set(c.upper() for c in json.load(f))
        new_fp = vc_done_ods - existing_fp
        if new_fp:
            merged_fp = sorted(existing_fp | vc_done_ods)
            print(f"  Adding {len(new_fp)} new full-planner: {sorted(new_fp)}")
            with open(fp_path, "w") as f:
                json.dump(merged_fp, f, indent=2)


def _fetch_monthly_totals(url, count_col, label):
    """Fetch a Google Sheet CSV and aggregate counts by month."""
    import csv
    import io
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SuveraRefreshBot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8-sig")
    except Exception as e:
        print(f"  WARN: Could not fetch {label} sheet: {e}")
        return {}, 0

    reader = csv.reader(io.StringIO(raw))
    next(reader, None)
    monthly = {}
    total = 0
    for row in reader:
        if len(row) <= count_col:
            continue
        month = row[0].strip()[:7]
        try:
            count = int(row[count_col].strip())
        except ValueError:
            continue
        monthly[month] = monthly.get(month, 0) + count
        total += count
    print(f"  {label}: {total} total across {len(monthly)} months")
    return monthly, total


def refresh_recalls():
    """Fetch recall + bloods data from Omni exports and save as JSON."""
    print("\n=== Fetching Omni Data (Recalls + Bloods) ===")

    recalls_monthly, recalls_total = _fetch_monthly_totals(
        GSHEET_RECALLS_URL, 2, "Recalls")
    bloods_monthly, bloods_total = _fetch_monthly_totals(
        GSHEET_BLOODS_URL, 4, "Bloods")

    data = {
        "recalls": {
            "total": recalls_total,
            "monthly": {m: recalls_monthly[m] for m in sorted(recalls_monthly)},
        },
        "bloods": {
            "total": bloods_total,
            "monthly": {m: bloods_monthly[m] for m in sorted(bloods_monthly)},
        },
    }

    output_path = DATA_DIR / "recalls.json"
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


# ============================================================
# Main
# ============================================================

def main():
    load_env()
    start = time.time()

    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"

    if mode in ("--all", "--practices"):
        refresh_practices()

    # Check Google Sheet for new live practices BEFORE waitlist refresh,
    # so any newly-live practices are excluded from the waitlist.
    refresh_live_from_google_sheet()

    if mode in ("--all", "--waitlist"):
        refresh_waitlist()

    refresh_recalls()

    elapsed = time.time() - start
    print(f"\n=== Completed in {elapsed:.0f}s ===")


if __name__ == "__main__":
    main()
