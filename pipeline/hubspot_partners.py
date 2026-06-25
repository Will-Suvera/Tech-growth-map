#!/usr/bin/env python3
"""Fetch GP Partner contacts (name + email) per practice ODS from HubSpot.

Used by ``push_hitlist_to_sheet.py`` to populate the ``GP Partners`` /
``GP Partner Emails`` columns on the Expansion Hitlist tab.

Matching path
-------------
::

    ODS code
      -> HubSpot company   (match on practice_code OR ods_unique)
      -> associated contacts
      -> keep contacts whose jobtitle contains "partner"   (any partner role:
         GP Partner, GP Partner/Principal, Salaried GP Partner, Senior /
         Managing Partner, ...)
      -> (name, email)

The "any partner role" rule is deliberate — some practices only tag their
lead as "Senior Partner" with no exact "GP Partner" contact, and the hitlist
is for outreach, so a wider net is more useful.

Auth
----
Reuses ``HUBSPOT_API_TOKEN`` and the retrying ``hubspot_request`` helper from
``refresh_data.py`` — same token, same 429/5xx backoff.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from refresh_data import hubspot_request  # noqa: E402

PARTNER_TOKEN = "partner"          # case-insensitive substring match on jobtitle
_BATCH = 100                       # HubSpot batch / search page cap
_SLEEP = 0.2                       # be polite between batched calls
_PLACEHOLDER_NAMES = {"", "-", "--", "- -"}


# --- Pure assembly (no I/O — unit-tested) ------------------------------------

def _clean(value: str | None) -> str:
    """Strip and treat HubSpot placeholder dashes as empty."""
    v = (value or "").strip()
    return "" if v in {"-", "--"} else v


def assemble_partners(
    ods_to_company: dict[str, int],
    company_contacts: dict[int, list[int]],
    contacts: dict[int, dict],
    *,
    token: str = PARTNER_TOKEN,
) -> dict[str, list[dict]]:
    """Build ``{ODS: [{"name", "email"}, ...]}`` from already-fetched data.

    Pure function so the matching / cleaning / dedupe logic is testable
    without hitting HubSpot. A contact counts as a partner when its jobtitle
    contains ``token`` (case-insensitive). Contacts with no usable name fall
    back to the email local-part so the two output columns stay row-aligned.
    """
    result: dict[str, list[dict]] = {}
    for ods, comp_id in ods_to_company.items():
        partners: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for cid in company_contacts.get(comp_id, []):
            props = contacts.get(cid)
            if not props:
                continue
            title = (props.get("jobtitle") or "").lower()
            if token not in title:
                continue
            email = (props.get("email") or "").strip()
            name = " ".join(
                p for p in (_clean(props.get("firstname")), _clean(props.get("lastname"))) if p
            ).strip()
            if not name and not email:
                continue
            key = (name.lower(), email.lower())
            if key in seen:
                continue
            seen.add(key)
            # Keep columns aligned: if no name on record, show the email
            # local-part so the names column still identifies the person.
            display_name = name or (email.split("@")[0] if email else "")
            partners.append({"name": display_name, "email": email})
        if partners:
            result[ods] = partners
    return result


# --- HubSpot I/O -------------------------------------------------------------

def _search_companies_by_ods(ods_codes: set[str]) -> dict[str, int]:
    """Return ``{ODS: company_id}`` by searching ``practice_code`` then
    ``ods_unique`` in batches of 100. First match wins per ODS."""
    result: dict[str, int] = {}
    ods_list = sorted(ods_codes)
    for i in range(0, len(ods_list), _BATCH):
        batch = ods_list[i:i + _BATCH]
        for prop in ("practice_code", "ods_unique"):
            todo = [o for o in batch if o not in result]
            if not todo:
                break
            after: str | None = None
            while True:
                body = {
                    "filterGroups": [{
                        "filters": [{"propertyName": prop, "operator": "IN", "values": todo}],
                    }],
                    "properties": ["practice_code", "ods_unique"],
                    "limit": _BATCH,
                }
                if after:
                    body["after"] = after
                resp = hubspot_request("POST", "/crm/v3/objects/companies/search", body)
                for comp in resp.get("results", []):
                    cid = int(comp["id"])
                    cprops = comp.get("properties", {})
                    for key in ("practice_code", "ods_unique"):
                        val = (cprops.get(key) or "").strip().upper()
                        if val in ods_codes and val not in result:
                            result[val] = cid
                after = resp.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
                time.sleep(_SLEEP)
            time.sleep(_SLEEP)
    return result


def _company_contacts(company_ids: set[int]) -> dict[int, list[int]]:
    """Return ``{company_id: [contact_id, ...]}`` via the v4 batch association
    read (companies -> contacts)."""
    out: dict[int, list[int]] = {}
    ids = list(company_ids)
    for i in range(0, len(ids), _BATCH):
        batch = ids[i:i + _BATCH]
        body = {"inputs": [{"id": str(c)} for c in batch]}
        resp = hubspot_request(
            "POST", "/crm/v4/associations/company/contact/batch/read", body,
        )
        for entry in resp.get("results", []):
            frm = int(entry.get("from", {}).get("id", 0))
            tos = [int(t["toObjectId"]) for t in entry.get("to", [])]
            if frm:
                out[frm] = tos
        time.sleep(_SLEEP)
    return out


def _read_contacts(contact_ids: set[int]) -> dict[int, dict]:
    """Batch-read contact name/email/jobtitle. Returns ``{contact_id: props}``."""
    out: dict[int, dict] = {}
    ids = list(contact_ids)
    for i in range(0, len(ids), _BATCH):
        batch = ids[i:i + _BATCH]
        body = {
            "inputs": [{"id": str(c)} for c in batch],
            "properties": ["firstname", "lastname", "email", "jobtitle"],
        }
        resp = hubspot_request("POST", "/crm/v3/objects/contacts/batch/read", body)
        for c in resp.get("results", []):
            out[int(c["id"])] = c.get("properties", {})
        time.sleep(_SLEEP)
    return out


def fetch_partners_by_ods(ods_codes) -> dict[str, list[dict]]:
    """Return ``{ODS: [{"name", "email"}, ...]}`` of partner contacts.

    ODS codes with no HubSpot company, or a company with no partner-titled
    contact, are simply absent from the result (caller renders blank cells).
    """
    ods_set = {str(o).strip().upper() for o in ods_codes if o and str(o).strip()}
    if not ods_set:
        return {}

    # Fail soft, not hard: hubspot_request() would sys.exit(1) on a missing
    # token, which the caller's try/except can't catch. Raise a normal error
    # so the hitlist push degrades to blank partner columns instead of dying.
    token = os.environ.get("HUBSPOT_API_TOKEN", "")
    if not token or token == "your-hubspot-private-app-token-here":
        raise RuntimeError("HUBSPOT_API_TOKEN not set")

    ods_to_company = _search_companies_by_ods(ods_set)
    company_ids = set(ods_to_company.values())
    company_contacts = _company_contacts(company_ids)
    all_contact_ids = {cid for cids in company_contacts.values() for cid in cids}
    contacts = _read_contacts(all_contact_ids)
    return assemble_partners(ods_to_company, company_contacts, contacts)
