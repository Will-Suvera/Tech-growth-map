#!/usr/bin/env python3
"""
Automated data refresh for the GP Practice Growth Dashboard.

Fetches and updates:
1. All active GP practices in England from NHS ODS API (filtered to real GP practices)
2. Geocodes postcodes via postcodes.io
3. Waitlist ODS codes from HubSpot (contacts with fillout_trigger = "Planner_Waitlist")
4. Expands PCN contacts to their constituent GP practices

Requires:
    HUBSPOT_API_TOKEN env var (set in .env file)

Usage:
    python3 refresh_data.py              # Full refresh (practices + waitlist)
    python3 refresh_data.py --waitlist   # Waitlist only (faster)
    python3 refresh_data.py --practices  # Practices only
"""

import json
import os
import subprocess
import time
import sys
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
HUBSPOT_BASE = "https://api.hubapi.com"


def load_live_customers():
    """Load live customer ODS codes from single source of truth."""
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
        if offset == 0:
            url = "https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations?PrimaryRoleId=RO177&Status=Active&Limit=1000"
        else:
            url = f"https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations?PrimaryRoleId=RO177&Status=Active&Limit=1000&Offset={offset}"

        print(f"  Page {page} (offset {offset})...")
        result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
        data = json.loads(result.stdout)
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
            with urllib.request.urlopen(req) as resp:
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

        # Skip Y-codes (merged entities, extended access hubs, etc.)
        # Skip W-codes (Welsh practices)
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
    """Make an authenticated HubSpot API request."""
    token = os.environ.get("HUBSPOT_API_TOKEN", "")
    if not token or token == "your-hubspot-private-app-token-here":
        print("ERROR: Set HUBSPOT_API_TOKEN in .env file")
        sys.exit(1)

    url = f"{HUBSPOT_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if data:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"  HubSpot API error {e.code}: {body[:200]}")
        raise


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

    # Filter out test/internal contacts
    real_contacts = []
    skip_emails = {"@suvera.co", "@suvera.com", "@searchhog", "@hotmail.co", "@gmail.com"}
    skip_names = {"test", "sdf", "wer", "qwer", "234", "wee"}

    for c in contacts:
        props = c.get("properties", {})
        email = (props.get("email") or "").lower()
        firstname = (props.get("firstname") or "").lower().strip()
        if any(s in email for s in skip_emails):
            continue
        if firstname in skip_names:
            continue
        real_contacts.append(c)

    print(f"  Real contacts (excl test/internal): {len(real_contacts)}")
    return real_contacts


def get_contact_company_associations(contact_ids):
    """Get company associations for a batch of contacts."""
    associations = {}

    for cid in contact_ids:
        try:
            result = hubspot_request(
                "GET",
                f"/crm/v4/objects/contacts/{cid}/associations/companies"
            )
            company_ids = [
                r["toObjectId"]
                for r in result.get("results", [])
            ]
            if company_ids:
                associations[cid] = company_ids
        except Exception:
            pass
        time.sleep(0.1)

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


def expand_pcn_to_practices(pcn_company_id):
    """Find GP practices associated with a PCN company."""
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
                org_type = (props.get("organisation_type") or "").lower()
                ods = props.get("ods_unique") or props.get("practice_code")
                if ods and "gp" in org_type.lower():
                    ods_codes.append(ods)
                elif ods and org_type not in ("icb", "federation", "pcn"):
                    ods_codes.append(ods)
    except Exception as e:
        print(f"  Error expanding PCN {pcn_company_id}: {e}")

    return ods_codes


def refresh_waitlist():
    """Full waitlist refresh pipeline."""
    contacts = fetch_waitlist_contacts()
    contact_ids = [int(c["id"]) for c in contacts]

    # Get company associations for all contacts
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

    # Remove any live customer codes from waitlist
    waitlist_ods -= LIVE_CUSTOMER_ODS

    # Sort and save
    sorted_codes = sorted(waitlist_ods)
    output_path = DATA_DIR / "waitlist_ods.json"
    with open(output_path, "w") as f:
        json.dump(sorted_codes, f, indent=2)

    print(f"\n  Saved {len(sorted_codes)} waitlist ODS codes to {output_path}")
    return sorted_codes


# ============================================================
# Main
# ============================================================

def main():
    load_env()
    start = time.time()

    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"

    if mode in ("--all", "--practices"):
        refresh_practices()

    if mode in ("--all", "--waitlist"):
        refresh_waitlist()

    elapsed = time.time() - start
    print(f"\n=== Completed in {elapsed:.0f}s ===")


if __name__ == "__main__":
    main()
