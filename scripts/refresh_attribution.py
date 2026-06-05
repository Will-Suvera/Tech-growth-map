"""
Build attribution.json — per-practice funnel + source + role + meeting context
for the Planner pipeline. Combines:

  - HubSpot EU1 contact/company data (with all the source/lifecycle props
    discovered in Phase 0 — see docs/hubspot_discovery.md)
  - Notion Partner Meeting Library snapshot at public/data/notion_meetings.json
    (refreshed separately via the Notion MCP in a Claude session)
  - Existing pipeline JSON (waitlist_ods, live_customers, etc.)
  - Optional per-practice manual overrides at
    public/data/source_overrides.json (committed; safe to edit by hand)

Output:
  attribution-dashboard/public/data/attribution.json

Run:
  HUBSPOT_API_TOKEN=pat-eu1-... python3 scripts/refresh_attribution.py

Notes:
  - EU1 base URL (api-eu1.hubapi.com). Does NOT share env with the existing
    US-portal waitlist refresh; pass token explicitly.
  - Email-engagement counts require `sales-email-read` scope on the token.
    If absent, the pipeline still runs and uses pre-aggregated date fields
    (hs_email_first_send_date etc.) as proxies — see infer_engagement_proxy().
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DATA = REPO_ROOT / "public" / "data"
DASHBOARD_DATA = REPO_ROOT / "attribution-dashboard" / "public" / "data"
CACHE_DIR = REPO_ROOT / "scripts" / ".attribution_cache"

HUBSPOT_BASE = "https://api-eu1.hubapi.com"
MAX_RETRIES = 3
BACKOFF_BASE = 1.5

# Lifecycle stage IDs that aren't named slugs (see docs/hubspot_discovery.md).
LIFECYCLESTAGE_ALIAS = {
    "645749455": "none",
    "1709731041": "inquiry",
    "701959416": "disqualified",
    "1962372335": "ex-customer",
}

# Job-title normaliser buckets — keep small and obviously-interpretable.
JOB_TITLE_BUCKETS = {
    "GP Partner": ["gp partner", "gp partner/principal", "managing partner",
                   "senior partner", "partner gp"],
    "Salaried GP": ["salaried gp", "salaried"],
    "GP": ["gp", "dr", "doctor"],  # last to avoid eating "salaried gp"
    "Practice Manager": ["practice manager", "practice business manager",
                         "business manager", "pm"],
    "Operations": ["operations manager", "operations", "ops"],
    "Digital/Transformation": ["digital transformation lead", "digital",
                                "transformation"],
}


# ---------- HubSpot helper ------------------------------------------------


def hs_request(method: str, endpoint: str, data: Any = None) -> dict:
    token = os.environ.get("HUBSPOT_API_TOKEN", "")
    if not token:
        print("ERROR: HUBSPOT_API_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    url = f"{HUBSPOT_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = json.dumps(data).encode() if data else None

    last_error = ""
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
            raise RuntimeError(f"HubSpot {method} {endpoint} -> {e.code}: {body[:300]}")
        except urllib.error.URLError as e:
            last_error = f"URLError: {e}"
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
                continue
            raise
    raise RuntimeError(f"HubSpot request exhausted retries: {last_error}")


# ---------- Local data loaders --------------------------------------------


def load_pipeline_practices() -> tuple[list[dict], dict[str, str]]:
    """Return (practice_rows, stage_by_ods) for every ODS in the pipeline union.

    Stages (per docs/planner_growth_dashboard.md funnel):
      signed_up   — waitlist_ods (on list, no contract)
      onboarding  — onboarding_ods (Status="In Progress" in Sheet, "Signed DPA")
      live_partial — live_customers (Live, no bloods)
      live_full    — live_customers_full_planner (Live + bloods enabled)
    """
    practices = json.loads((PUBLIC_DATA / "practices_geocoded.json").read_text())
    waitlist = set(json.loads((PUBLIC_DATA / "waitlist_ods.json").read_text()))
    live = set(json.loads((PUBLIC_DATA / "live_customers.json").read_text()))
    live_full = set(json.loads((PUBLIC_DATA / "live_customers_full_planner.json").read_text()))
    onb_path = PUBLIC_DATA / "onboarding_ods.json"
    onboarding = set(json.loads(onb_path.read_text())) if onb_path.exists() else set()

    pipeline = (waitlist | live | onboarding) - {""}
    stage_by_ods: dict[str, str] = {}
    rows: list[dict] = []
    by_ods = {p["ods"].upper(): p for p in practices if p.get("ods")}
    for ods in pipeline:
        ods = ods.upper()
        if ods in live_full:
            stage = "live_full"
        elif ods in live:
            stage = "live_partial"
        elif ods in onboarding:
            stage = "onboarding"
        elif ods in waitlist:
            stage = "signed_up"
        else:
            continue
        stage_by_ods[ods] = stage
        p = by_ods.get(ods)
        if not p:
            rows.append({"ods": ods, "name": None, "stage": stage, "_missing_in_geocoded": True})
            continue
        rows.append({
            "ods": ods,
            "name": p.get("name"),
            "stage": stage,
            "icb": (p.get("icb") or "").strip() or None,
            "pcn_name": (p.get("pcn_name") or "").strip() or None,
            "pcn_code": (p.get("pcn_code") or "").strip() or None,
            "patients": p.get("patients"),
            "lat": p.get("lat"),
            "lng": p.get("lng"),
        })
    return rows, stage_by_ods


def load_notion_meetings() -> list[dict]:
    """Load Notion snapshot if present. Format documented in scripts/fetch_notion_meetings.md."""
    p = PUBLIC_DATA / "notion_meetings.json"
    if not p.exists():
        return []
    return json.loads(p.read_text())


def load_source_overrides() -> dict[str, dict]:
    """Load manual overrides — prefers attribution-dashboard/public/data/manual_overrides.json
    (new, written by the in-dashboard editor), falls back to legacy source_overrides.json."""
    new = DASHBOARD_DATA / "manual_overrides.json"
    if new.exists():
        raw = json.loads(new.read_text())
        return {k.upper(): v for k, v in raw.items()}
    legacy = PUBLIC_DATA / "source_overrides.json"
    if legacy.exists():
        raw = json.loads(legacy.read_text())
        return {k.upper(): v for k, v in raw.items()}
    return {}


def load_practice_tiers() -> dict[str, str]:
    """{ods: 'Freemium' | 'Money-back' | 'VC'} — written by scripts/refresh_data.py --tiers."""
    p = PUBLIC_DATA / "practice_tiers.json"
    if not p.exists():
        return {}
    return {k.upper(): v for k, v in json.loads(p.read_text()).items()}


def load_recalls_data() -> dict:
    """recalls.json — contains both recalls and bloods (pathology forms) by month."""
    p = PUBLIC_DATA / "recalls.json"
    return json.loads(p.read_text()) if p.exists() else {}


def load_launch_visits() -> dict[str, dict]:
    """{ods: {status, date, attendees, ...}} — written by scripts/ingest_practice_visits.py
    (or legacy ingest_launch_visits.py). Tries the new path first."""
    new = DASHBOARD_DATA / "practice_visits.json"
    legacy = DASHBOARD_DATA / "launch_visits.json"
    path = new if new.exists() else legacy
    if not path.exists():
        return {}
    return {k.upper(): v for k, v in json.loads(path.read_text()).items()}


def load_first_live_dates() -> dict[str, str]:
    """Earliest snapshot date each ODS appears in live_ods. Used as a fallback
    go-live date when no manual override exists. Date-precision only."""
    snapshots_dir = REPO_ROOT / "public" / "snapshots"
    if not snapshots_dir.exists():
        return {}
    first_live: dict[str, str] = {}
    for f in sorted(snapshots_dir.glob("*.json")):
        if f.name == "timeline.json":
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        date = data.get("date") or f.stem  # snapshot stem is YYYY-MM-DD
        for ods in data.get("live_ods") or []:
            first_live.setdefault(ods.upper(), date)
    return first_live


def fy_start_for(today: dt.date | None = None) -> dt.date:
    """UK Financial Year starts April 1. Returns the start date of the current FY."""
    today = today or dt.date.today()
    return dt.date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def _months_since(start: dt.date, today: dt.date | None = None) -> list[str]:
    """Return list of 'YYYY-MM' strings from `start` through current month inclusive."""
    today = today or dt.date.today()
    out: list[str] = []
    y, m = start.year, start.month
    while (y, m) <= (today.year, today.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def compute_fy_metrics(ods: str, recalls_data: dict, patients: int | None,
                       today: dt.date | None = None) -> dict:
    """FY-to-date + this-month recalls/bloods + per-patient ratios.

    Reads recalls.json keys:
      - recalls.fy_by_practice[ODS] -> {fy_to_date, this_month}
      - bloods.fy_by_practice[ODS]  -> {fy_to_date, this_month}
    (both populated by scripts/refresh_data.py:refresh_recalls; see
    docs/planner_growth_dashboard.md "Data fix" section)

    Falls back to practices_this_month for legacy recalls.json files that
    pre-date the fy_by_practice schema addition.
    """
    today = today or dt.date.today()
    ods_u = ods.upper()
    out = {
        "recalls_this_month": 0,
        "bloods_this_month": 0,
        "is_recalling_this_month": False,
        "is_bloods_this_month": False,
        "recalls_fy_to_date": 0,
        "bloods_fy_to_date": 0,
        "recalls_per_patient_fy": None,
        "bloods_per_patient_fy": None,
        "forms_to_recalls_ratio": None,
    }
    if not recalls_data:
        return out

    r_section = recalls_data.get("recalls") or {}
    b_section = recalls_data.get("bloods") or {}

    # Preferred path: per-practice FY map (new schema)
    r_fy = (r_section.get("fy_by_practice") or {}).get(ods_u)
    b_fy = (b_section.get("fy_by_practice") or {}).get(ods_u)
    if r_fy:
        out["recalls_fy_to_date"] = int(r_fy.get("fy_to_date") or 0)
        out["recalls_this_month"] = int(r_fy.get("this_month") or 0)
    if b_fy:
        out["bloods_fy_to_date"] = int(b_fy.get("fy_to_date") or 0)
        out["bloods_this_month"] = int(b_fy.get("this_month") or 0)

    # Per-month + per-clinician detail (drilldown shows "who recalled / when")
    r_by_month = (r_section.get("by_ods_month") or {}).get(ods_u)
    if r_by_month:
        out["recalls_by_month"] = dict(sorted(r_by_month.items()))
    b_by_month_clin = (b_section.get("by_ods_month_clinician") or {}).get(ods_u)
    if b_by_month_clin:
        # Sort each month's clinicians by count desc; drop the "_total" key
        # (frontend recomputes if needed)
        cleaned: dict = {}
        for m in sorted(b_by_month_clin):
            clin = {k: v for k, v in b_by_month_clin[m].items() if k != "_total"}
            cleaned[m] = dict(sorted(clin.items(), key=lambda x: -x[1]))
        out["bloods_by_month_clinician"] = cleaned

    # Legacy fallback: scan practices_this_month if fy_by_practice missing
    if not r_fy:
        for p in r_section.get("practices_this_month", []):
            if (p.get("ods") or "").upper() == ods_u:
                out["recalls_this_month"] = int(p.get("count") or 0)
                out["recalls_fy_to_date"] = out["recalls_this_month"]
                break
    if not b_fy:
        for p in b_section.get("practices_this_month", []):
            if (p.get("ods") or "").upper() == ods_u:
                out["bloods_this_month"] = int(p.get("count") or 0)
                out["bloods_fy_to_date"] = out["bloods_this_month"]
                break

    out["is_recalling_this_month"] = out["recalls_this_month"] > 0
    out["is_bloods_this_month"] = out["bloods_this_month"] > 0

    if patients and patients > 0:
        if out["recalls_fy_to_date"]:
            out["recalls_per_patient_fy"] = round(out["recalls_fy_to_date"] / patients, 4)
        if out["bloods_fy_to_date"]:
            out["bloods_per_patient_fy"] = round(out["bloods_fy_to_date"] / patients, 4)
    if out["recalls_fy_to_date"]:
        out["forms_to_recalls_ratio"] = round(
            out["bloods_fy_to_date"] / max(1, out["recalls_fy_to_date"]), 3)

    return out


# ---------- HubSpot fetches -----------------------------------------------


CONTACT_PROPS = [
    # identity
    "firstname", "lastname", "email", "jobtitle", "createdate",
    # lifecycle + stage timing
    "lifecyclestage", "hs_lead_status",
    "hs_v2_date_entered_subscriber", "hs_v2_date_entered_lead",
    "hs_v2_date_entered_marketingqualifiedlead",
    "hs_v2_date_entered_salesqualifiedlead",
    "hs_v2_date_entered_opportunity", "hs_v2_date_entered_customer",
    "hs_v2_date_entered_evangelist",
    # source (Suvera custom)
    "um_source_category", "um_source_category_1", "um_source_category_2",
    "um_lead_score",
    # standard HubSpot source (mostly empty/OFFLINE but worth capturing)
    "hs_analytics_source", "hs_analytics_source_data_1", "hs_analytics_source_data_2",
    "hs_latest_source", "hs_object_source_label",
    # engagement proxies (pre-aggregated date fields — no scope cost)
    "hs_email_first_send_date", "hs_email_first_open_date",
    "hs_email_first_click_date", "hs_email_first_reply_date",
    "hs_latest_meeting_activity", "hs_first_outreach_date",
    "hs_sa_first_engagement_date",
    # owner
    "hubspot_owner_id",
    # LinkedIn outreach signals (Hublead)
    "hublead_last_linkedin_invitation_sent_date",
    "hublead_last_linkedin_message_sent_date",
    "hublead_last_linkedin_invitation_accepted_date",
    # NHS Partners visits (mostly empty but cheap)
    "nhs_partners_visit", "nhs_partners_visit_date",
]


def search_companies_by_ods(ods_codes: list[str]) -> dict[str, list[dict]]:
    """Batched search for companies by practice_code. Returns ods -> [company...]."""
    result: dict[str, list[dict]] = {}
    BATCH = 100  # HubSpot search supports up to 100 OR-filter values
    company_props = [
        "name", "practice_code", "ods_unique", "organisation_type",
        "lifecyclestage", "hs_lead_status", "hubspot_owner_id", "createdate",
        "hs_date_entered_opportunity", "hs_date_entered_customer",
        "hs_analytics_source", "hs_latest_source",
        "hs_object_source_label", "hs_object_source_detail_1",
        "partnership_status",
    ]
    for i in range(0, len(ods_codes), BATCH):
        chunk = ods_codes[i : i + BATCH]
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "practice_code", "operator": "IN", "values": chunk}
            ]}],
            "properties": company_props,
            "limit": 100,
        }
        r = hs_request("POST", "/crm/v3/objects/companies/search", body)
        for co in r.get("results", []):
            ods = (co.get("properties", {}) or {}).get("practice_code", "").upper()
            if ods:
                result.setdefault(ods, []).append(co)
        time.sleep(0.2)
    return result


def fetch_company_contact_associations(company_ids: list[str]) -> dict[str, list[str]]:
    """Return company_id -> [contact_id, ...] via v4 batch associations read."""
    if not company_ids:
        return {}
    body = {"inputs": [{"id": cid} for cid in company_ids]}
    r = hs_request(
        "POST",
        "/crm/v4/associations/companies/contacts/batch/read",
        body,
    )
    out: dict[str, list[str]] = {}
    for item in r.get("results", []):
        cid = item.get("from", {}).get("id")
        contacts = [t.get("toObjectId") for t in item.get("to", [])]
        if cid and contacts:
            out[str(cid)] = [str(c) for c in contacts if c]
    return out


def fetch_contacts(contact_ids: list[str]) -> dict[str, dict]:
    """Batch-read contact records keyed by id."""
    out: dict[str, dict] = {}
    BATCH = 100
    for i in range(0, len(contact_ids), BATCH):
        chunk = contact_ids[i : i + BATCH]
        body = {"inputs": [{"id": cid} for cid in chunk], "properties": CONTACT_PROPS}
        r = hs_request("POST", "/crm/v3/objects/contacts/batch/read", body)
        for c in r.get("results", []):
            out[str(c["id"])] = c
        time.sleep(0.2)
    return out


# Deal-level source is the most authoritative signal — it's hand-set by the
# sales team using a structured convention (e.g. "Channel Partner: Cogora",
# "Webinar: 2026-05-14", "Practice Referral: [name]"). See the lead_source /
# lead_source_detail property descriptions in HubSpot.
DEAL_PROPS = [
    "dealname", "dealstage", "pipeline", "createdate", "hs_lastmodifieddate",
    "lead_source", "lead_source_detail",
    "hs_analytics_source", "hs_object_source_label",
    "ehr_type",  # clinical system: "EMIS" / "SystmOne"
]


def fetch_company_deal_associations(company_ids: list[str]) -> dict[str, list[str]]:
    """Return company_id -> [deal_id, ...] via v4 batch associations read."""
    if not company_ids:
        return {}
    out: dict[str, list[str]] = {}
    BATCH = 100
    for i in range(0, len(company_ids), BATCH):
        chunk = company_ids[i : i + BATCH]
        body = {"inputs": [{"id": cid} for cid in chunk]}
        r = hs_request("POST", "/crm/v4/associations/companies/deals/batch/read", body)
        for item in r.get("results", []):
            cid = item.get("from", {}).get("id")
            deals = [t.get("toObjectId") for t in item.get("to", [])]
            if cid and deals:
                out[str(cid)] = [str(d) for d in deals if d]
        time.sleep(0.2)
    return out


def fetch_contact_deal_associations(contact_ids: list[str]) -> dict[str, list[str]]:
    """Return contact_id -> [deal_id, ...] via v4 batch associations read.

    Needed because some deals (e.g. the Voyager 'Webinar' deal) are associated
    only with a contact, not the company — company-deal fetch alone misses them.
    """
    if not contact_ids:
        return {}
    out: dict[str, list[str]] = {}
    BATCH = 100
    for i in range(0, len(contact_ids), BATCH):
        chunk = contact_ids[i : i + BATCH]
        body = {"inputs": [{"id": cid} for cid in chunk]}
        r = hs_request("POST", "/crm/v4/associations/contacts/deals/batch/read", body)
        for item in r.get("results", []):
            cid = item.get("from", {}).get("id")
            deals = [t.get("toObjectId") for t in item.get("to", [])]
            if cid and deals:
                out[str(cid)] = [str(d) for d in deals if d]
        time.sleep(0.2)
    return out


def fetch_deals(deal_ids: list[str]) -> dict[str, dict]:
    """Batch-read deal records keyed by id."""
    out: dict[str, dict] = {}
    BATCH = 100
    for i in range(0, len(deal_ids), BATCH):
        chunk = deal_ids[i : i + BATCH]
        body = {"inputs": [{"id": did} for did in chunk], "properties": DEAL_PROPS}
        r = hs_request("POST", "/crm/v3/objects/deals/batch/read", body)
        for d in r.get("results", []):
            out[str(d["id"])] = d
        time.sleep(0.2)
    return out


def parse_deal_lead_source(raw: str) -> tuple[str, str]:
    """Split a structured lead_source string into (channel, detail).

    Convention: "Channel Partner: Cogora" -> ("Channel Partner", "Cogora").
    A bare value with no colon is treated as the channel with empty detail.
    """
    if not raw:
        return "", ""
    if ":" in raw:
        channel, _, detail = raw.partition(":")
        return channel.strip(), detail.strip()
    return raw.strip(), ""


# ---------- Normalisation -------------------------------------------------


def normalise_jobtitle(raw: str | None) -> tuple[str | None, str]:
    """Return (bucket, raw_lower). Bucket is one of JOB_TITLE_BUCKETS keys or None."""
    if not raw:
        return None, ""
    s = raw.strip().lower()
    for bucket, keywords in JOB_TITLE_BUCKETS.items():
        if any(s == k or k in s.split() or s.startswith(k + " ") or s.endswith(" " + k)
               or s == k for k in keywords):
            return bucket, s
    # Last-pass: substring contains
    for bucket, keywords in JOB_TITLE_BUCKETS.items():
        if any(k in s for k in keywords):
            return bucket, s
    return None, s


def normalise_lifecyclestage(value: str | None) -> str | None:
    if not value:
        return None
    return LIFECYCLESTAGE_ALIAS.get(value, value)


# ---------- Source inference ----------------------------------------------

# Map raw `um_source_category_1` values onto a tidy canonical taxonomy. Keep
# Suvera's vocabulary intact (no synonyms invented); just collapse the
# clearly-non-attributable buckets ("Import", "HubSpot User") into Unknown.
CANONICAL_SOURCE = {
    "Webinars": "Webinar",
    "Webinar": "Webinar",
    "Webinar (attended)": "Webinar",
    "On Demand Webinar": "Webinar",
    "Conference": "Conference",
    "Round Table": "Round Table",
    "LinkedIn": "LinkedIn",
    "Facebook": "Social",
    "Twitter": "Social",
    "Google Search": "Organic Search",
    "Gated Content": "Content",
    "Gated Content Download": "Content",
    "Guides & Resources": "Content",
    "Case Studies": "Content",
    "Content Download": "Content",
    "Form Submission": "Inbound Form",
    "Contact Us": "Inbound Form",
    "Calculator": "Inbound Form",
    "Email Extension": "Email Extension",
    "Direct Traffic": "Direct",
}


def infer_source(contacts: list[dict], meetings: list[dict], deals: list[dict] | None = None) -> dict:
    """Return {value, confidence, evidence: [str], raw_source_set: [str]}."""
    evidence: list[str] = []
    raw_sources: set[str] = set()
    deals = deals or []

    # 0. Highest confidence: deal-level lead_source (hand-set by sales using a
    #    structured convention, e.g. "Channel Partner: Cogora"). This is the
    #    most authoritative signal — prefer it over everything else.
    deal_channels: set[str] = set()
    deal_evidence: list[str] = []
    for d in deals:
        p = d.get("properties", {}) or {}
        raw = (p.get("lead_source") or "").strip()
        if not raw:
            continue
        channel, detail = parse_deal_lead_source(raw)
        channel = CANONICAL_SOURCE.get(channel, channel)  # unify "Webinars"->"Webinar" etc.
        if channel:
            deal_channels.add(channel)
            label = f"{channel}: {detail}" if detail else channel
            deal_evidence.append(f"deal {d.get('id')} lead_source={label}")
    if deal_channels:
        canon = sorted(deal_channels)
        return {
            "value": canon[0] if len(canon) == 1 else "Multiple",
            "confidence": "high",
            "evidence": deal_evidence[:3],
            "raw_sources": sorted(deal_channels),
            "canonical_set": canon,
        }

    # 1. High confidence: any contact has a non-Import um_source_category_1
    for c in contacts:
        p = c.get("properties", {}) or {}
        s1 = p.get("um_source_category_1")
        if s1 and s1 not in ("Import", "HubSpot User", "Other"):
            raw_sources.add(s1)
            evidence.append(f"contact {c['id']} um_source_category_1={s1}")
    if raw_sources:
        canon = sorted({CANONICAL_SOURCE.get(s, s) for s in raw_sources})
        return {
            "value": canon[0] if len(canon) == 1 else "Multiple",
            "confidence": "high",
            "evidence": evidence[:3],
            "raw_sources": sorted(raw_sources),
            "canonical_set": canon,
        }

    # 2. Medium confidence: Notion meeting present — infer from theme or LinkedIn activity
    if meetings:
        themes = [t for m in meetings for t in (m.get("main_themes") or [])]
        # Most meetings are demo/discovery — if first meeting theme is "Onboarding"
        # the practice was already converted; the source was something else.
        if any("Onboarding" not in (m.get("main_themes") or []) for m in meetings):
            evidence.append(f"has {len(meetings)} meeting(s) in Notion library")
            return {
                "value": "Outbound/Demo",
                "confidence": "medium",
                "evidence": evidence,
                "raw_sources": [],
                "canonical_set": ["Outbound/Demo"],
            }

    # 3. Low confidence: LinkedIn-Hublead activity on any contact
    for c in contacts:
        p = c.get("properties", {}) or {}
        if p.get("hublead_last_linkedin_invitation_sent_date") or \
           p.get("hublead_last_linkedin_message_sent_date"):
            evidence.append(f"contact {c['id']} has LinkedIn outreach activity")
            return {
                "value": "LinkedIn",
                "confidence": "low",
                "evidence": evidence,
                "raw_sources": [],
                "canonical_set": ["LinkedIn"],
            }

    # 4. Low: um_source_category_1=Import is the only signal
    for c in contacts:
        s1 = (c.get("properties", {}) or {}).get("um_source_category_1")
        if s1 == "Import":
            return {
                "value": "Unknown",
                "confidence": "unknown",
                "evidence": ["all contacts marked Import — bulk added, no source"],
                "raw_sources": ["Import"],
                "canonical_set": ["Unknown"],
            }

    return {
        "value": "Unknown",
        "confidence": "unknown",
        "evidence": [],
        "raw_sources": [],
        "canonical_set": ["Unknown"],
    }


# ---------- Notion match --------------------------------------------------


def _norm_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\b(surgery|practice|medical centre|medical center|health centre|"
               r"health center|partnership|family practice|gp|the)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def match_meetings_to_ods(meetings: list[dict], practices: list[dict]) -> dict[str, list[dict]]:
    """Return ods -> [meeting, ...]. Logs unmatched to scripts/.notion_unmatched.log."""
    by_norm_name = {}
    for p in practices:
        if p.get("name"):
            by_norm_name[_norm_name(p["name"])] = p["ods"]
    result: dict[str, list[dict]] = {}
    unmatched: list[str] = []
    for m in meetings:
        candidates: list[str] = []
        # 1. explicit Practice column
        if m.get("practice"):
            candidates.append(m["practice"])
        # 2. parse title before " — " or " - "
        title = m.get("title") or m.get("meeting") or ""
        if title:
            head = re.split(r"\s+[—\-]\s+", title, maxsplit=1)[0].strip()
            # strip prefixes like "🏥 ", "Planner demo: "
            head = re.sub(r"^[^\w]+", "", head)
            head = re.sub(r"^(planner demo:|demo:|will <> )\s*", "", head, flags=re.I)
            if head:
                candidates.append(head)
        matched_ods = None
        for cand in candidates:
            key = _norm_name(cand)
            if key in by_norm_name:
                matched_ods = by_norm_name[key]
                break
            # try substring (cand contains practice name)
            for nk, ods in by_norm_name.items():
                if nk and len(nk) > 6 and nk in key:
                    matched_ods = ods
                    break
            if matched_ods:
                break
        if matched_ods:
            result.setdefault(matched_ods, []).append(m)
        else:
            unmatched.append(title or json.dumps(m)[:100])

    log = REPO_ROOT / "scripts" / ".notion_unmatched.log"
    log.write_text("\n".join(unmatched) + "\n" if unmatched else "")
    return result


# ---------- Engagement proxy ---------------------------------------------


def engagement_proxy(contact_props: dict) -> dict:
    """Compute lightweight engagement signals from pre-aggregated date props."""
    def has(field):
        return bool(contact_props.get(field))
    return {
        "first_outreach_date": contact_props.get("hs_first_outreach_date") or
                                contact_props.get("hs_sa_first_engagement_date"),
        "first_email_send_date": contact_props.get("hs_email_first_send_date"),
        "first_email_open_date": contact_props.get("hs_email_first_open_date"),
        "first_email_click_date": contact_props.get("hs_email_first_click_date"),
        "first_email_reply_date": contact_props.get("hs_email_first_reply_date"),
        "latest_meeting_activity": contact_props.get("hs_latest_meeting_activity"),
        "linkedin_invitation_sent": has("hublead_last_linkedin_invitation_sent_date"),
        "linkedin_message_sent": has("hublead_last_linkedin_message_sent_date"),
        "linkedin_invitation_accepted": has("hublead_last_linkedin_invitation_accepted_date"),
    }


# ---------- Compose per-practice row --------------------------------------


def compose_practice(p: dict, company: dict | None, contacts: list[dict],
                     meetings: list[dict], override: dict | None,
                     tier: str | None = None,
                     fy_metrics: dict | None = None,
                     launch_visit: dict | None = None,
                     first_live_date: str | None = None,
                     deals: list[dict] | None = None) -> dict:
    deals = deals or []
    contact_rows: list[dict] = []
    primary_role = None
    primary_role_priority = -1
    earliest_create: str | None = None
    role_counts: Counter[str] = Counter()
    for c in contacts:
        cp = c.get("properties", {}) or {}
        bucket, raw_lc = normalise_jobtitle(cp.get("jobtitle"))
        ls = normalise_lifecyclestage(cp.get("lifecyclestage"))
        cd = cp.get("createdate")
        if cd and (earliest_create is None or cd < earliest_create):
            earliest_create = cd
        if bucket:
            role_counts[bucket] += 1
        # primary role priority: GP Partner > Practice Manager > GP > others
        priority = {"GP Partner": 5, "Practice Manager": 4, "GP": 3, "Operations": 2,
                    "Digital/Transformation": 2, "Salaried GP": 2}.get(bucket, 1)
        if bucket and priority > primary_role_priority:
            primary_role = bucket
            primary_role_priority = priority

        contact_rows.append({
            "id": c["id"],
            "firstname": cp.get("firstname"),
            "lastname": cp.get("lastname"),
            "email": cp.get("email"),
            "jobtitle_raw": cp.get("jobtitle"),
            "jobtitle_bucket": bucket,
            "lifecyclestage": ls,
            "createdate": cd,
            "stage_dates": {
                "subscriber": cp.get("hs_v2_date_entered_subscriber"),
                "lead": cp.get("hs_v2_date_entered_lead"),
                "marketingqualifiedlead": cp.get("hs_v2_date_entered_marketingqualifiedlead"),
                "salesqualifiedlead": cp.get("hs_v2_date_entered_salesqualifiedlead"),
                "opportunity": cp.get("hs_v2_date_entered_opportunity"),
                "customer": cp.get("hs_v2_date_entered_customer"),
                "evangelist": cp.get("hs_v2_date_entered_evangelist"),
            },
            "um_source_category": cp.get("um_source_category"),
            "um_source_category_1": cp.get("um_source_category_1"),
            "um_source_category_2": cp.get("um_source_category_2"),
            "um_lead_score": cp.get("um_lead_score"),
            "engagement_proxy": engagement_proxy(cp),
            "owner_id": cp.get("hubspot_owner_id"),
        })

    meetings_pruned = [{
        "id": m.get("id"),
        "date": m.get("date"),
        "title": m.get("title") or m.get("meeting"),
        "partner_role": m.get("partner_role"),
        "main_themes": m.get("main_themes") or [],
        "opportunity_signal": m.get("opportunity_signal"),
        "attendees": m.get("attendees"),
        "fathom_url": m.get("fathom_url"),
        "status": m.get("status"),
    } for m in sorted(meetings, key=lambda x: x.get("date") or "")]

    # Latest opportunity signal = signal from most-recent meeting
    latest_signal = None
    if meetings_pruned:
        for m in reversed(meetings_pruned):
            if m.get("opportunity_signal"):
                latest_signal = m["opportunity_signal"]
                break

    dominant_themes = [t for t, _ in Counter(
        t for m in meetings_pruned for t in m.get("main_themes") or []
    ).most_common(5)]

    inferred = infer_source(contacts, meetings_pruned, deals)
    final_source = inferred["value"]
    final_confidence = inferred["confidence"]
    if override and override.get("source"):
        final_source = override["source"]
        final_confidence = "manual"

    # Capture deal-level lead source rows for the drilldown
    deal_rows = []
    ehr_type = None
    for d in deals:
        dp = d.get("properties", {}) or {}
        raw_ls = (dp.get("lead_source") or "").strip()
        ehr = (dp.get("ehr_type") or "").strip()
        if ehr and not ehr_type:
            ehr_type = ehr  # first non-empty EHR type across the practice's deals
        if raw_ls or dp.get("dealname"):
            channel, detail = parse_deal_lead_source(raw_ls)
            deal_rows.append({
                "id": d.get("id"),
                "dealname": dp.get("dealname"),
                "lead_source": raw_ls or None,
                "lead_source_channel": channel or None,
                "lead_source_detail": detail or (dp.get("lead_source_detail") or None),
                "dealstage": dp.get("dealstage"),
                "ehr_type": ehr or None,
            })

    row = {
        "ods": p["ods"],
        "name": p.get("name"),
        "stage": p.get("stage"),
        "tier": tier or "Freemium",
        "icb": p.get("icb"),
        "pcn_name": p.get("pcn_name"),
        "pcn_code": p.get("pcn_code"),
        "patients": p.get("patients"),
        "lat": p.get("lat"),
        "lng": p.get("lng"),
        "company_id": company.get("id") if company else None,
        "company_props": (company or {}).get("properties"),
        "signed_up_date": earliest_create,
        "contacts": contact_rows,
        "primary_role": override.get("role") if override and override.get("role") else primary_role,
        "role_counts": dict(role_counts),
        "engaged_roles": sorted(role_counts.keys()),
        "meetings": meetings_pruned,
        "meeting_count": len(meetings_pruned),
        "latest_opportunity_signal": latest_signal,
        "dominant_themes": dominant_themes,
        "source": final_source,
        "source_confidence": final_confidence,
        "source_inferred_evidence": inferred.get("evidence"),
        "source_raw": inferred.get("raw_sources"),
        "deals": deal_rows,
        "deal_count": len(deal_rows),
        "ehr_type": ehr_type,
        "override_notes": (override or {}).get("notes"),
    }
    if fy_metrics:
        row.update(fy_metrics)
    if launch_visit:
        row["practice_visit_status"] = launch_visit.get("status")
        row["practice_visit_date"] = launch_visit.get("date")
        row["practice_visit_attendees"] = launch_visit.get("attendees")
        row["practice_visit_times"] = launch_visit.get("times")
        row["practice_visit_site_address"] = launch_visit.get("site_address")
        row["practice_visit_problems"] = launch_visit.get("problems")
        row["practice_visit_outcome"] = launch_visit.get("outcome")
    else:
        row["practice_visit_status"] = "none"
        row["practice_visit_date"] = None

    # Go-live date: manual override wins, fallback to first snapshot appearance.
    manual_go_live = (override or {}).get("go_live_date")
    row["go_live_date"] = manual_go_live or first_live_date
    row["go_live_date_source"] = "manual" if manual_go_live else ("snapshot" if first_live_date else None)
    return row


# ---------- Output --------------------------------------------------------


def write_attribution(rows: list[dict]) -> None:
    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)
    out_path = DASHBOARD_DATA / "attribution.json"

    # Stats roll-up
    stage_counts = Counter(r["stage"] for r in rows)
    source_counts = Counter(r["source"] for r in rows)
    confidence_counts = Counter(r["source_confidence"] for r in rows)
    role_counts = Counter(r["primary_role"] for r in rows if r["primary_role"])
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stats": {
            "total": len(rows),
            "by_stage": dict(stage_counts),
            "by_source": dict(source_counts),
            "by_source_confidence": dict(confidence_counts),
            "by_primary_role": dict(role_counts),
        },
        "practices": rows,
    }

    # Shrink-guard
    if out_path.exists():
        prev = json.loads(out_path.read_text())
        prev_n = len(prev.get("practices", []))
        if prev_n and len(rows) < prev_n * 0.9:
            raise RuntimeError(
                f"Shrink guard: refusing to write {len(rows)} rows, previous was {prev_n}"
            )

    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {out_path} ({len(rows)} practices)")


# ---------- Main ----------------------------------------------------------


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading pipeline practices...")
    practices, stage_by_ods = load_pipeline_practices()
    print(f"  pipeline ODS count: {len(practices)}")

    print("Searching HubSpot companies...")
    ods_codes = [p["ods"] for p in practices]
    company_by_ods = search_companies_by_ods(ods_codes)
    print(f"  matched companies: {sum(len(v) for v in company_by_ods.values())} "
          f"across {len(company_by_ods)} ODS codes")

    company_ids = [co["id"] for cos in company_by_ods.values() for co in cos]
    print(f"Fetching contact associations for {len(company_ids)} companies...")
    BATCH = 100
    assoc: dict[str, list[str]] = {}
    for i in range(0, len(company_ids), BATCH):
        chunk = company_ids[i : i + BATCH]
        assoc.update(fetch_company_contact_associations(chunk))
        time.sleep(0.2)
    all_contact_ids = sorted({cid for ids in assoc.values() for cid in ids})
    print(f"  associated contacts: {len(all_contact_ids)}")

    print("Batch-reading contacts...")
    contacts_by_id = fetch_contacts(all_contact_ids)
    print(f"  retrieved: {len(contacts_by_id)}")

    print("Fetching deal associations + deals (lead_source)...")
    deal_assoc = fetch_company_deal_associations(company_ids)
    # Some deals are associated only with a contact (no company) — fetch those too.
    contact_deal_assoc = fetch_contact_deal_associations(all_contact_ids)
    all_deal_ids = sorted(
        {did for ids in deal_assoc.values() for did in ids}
        | {did for ids in contact_deal_assoc.values() for did in ids}
    )
    deals_by_id = fetch_deals(all_deal_ids)
    n_with_source = sum(1 for d in deals_by_id.values()
                        if (d.get("properties", {}) or {}).get("lead_source"))
    print(f"  deals: {len(deals_by_id)} ({n_with_source} with lead_source) "
          f"— {len(deal_assoc)} via company, {len(contact_deal_assoc)} contacts w/ deals")

    print("Loading Notion meetings snapshot...")
    meetings = load_notion_meetings()
    print(f"  meetings in snapshot: {len(meetings)}")

    print("Joining Notion meetings to ODS...")
    meetings_by_ods = match_meetings_to_ods(meetings, practices)
    print(f"  matched practices: {len(meetings_by_ods)}; "
          f"unmatched logged to scripts/.notion_unmatched.log")

    print("Loading manual overrides...")
    overrides = load_source_overrides()
    print(f"  overrides: {len(overrides)}")

    print("Loading practice tiers, recalls, practice visits, snapshots...")
    tiers = load_practice_tiers()
    recalls_data = load_recalls_data()
    launch_visits = load_launch_visits()
    first_live_dates = load_first_live_dates()
    print(f"  tiers: {len(tiers)} · recalls/bloods feed: {'yes' if recalls_data else 'no'} · "
          f"visits: {len(launch_visits)} · snapshot live dates: {len(first_live_dates)}")

    print("Composing per-practice rows...")
    rows: list[dict] = []
    for p in practices:
        cos = company_by_ods.get(p["ods"], [])
        company = cos[0] if cos else None
        contact_ids = assoc.get(company["id"], []) if company else []
        contacts = [contacts_by_id[cid] for cid in contact_ids if cid in contacts_by_id]
        ms = meetings_by_ods.get(p["ods"], [])
        fy = compute_fy_metrics(p["ods"], recalls_data, p.get("patients"))
        # Deals for this practice = company-associated ∪ contact-associated
        deal_id_set: set[str] = set(deal_assoc.get(company["id"], []) if company else [])
        for cid in contact_ids:
            deal_id_set.update(contact_deal_assoc.get(cid, []))
        prac_deals = [deals_by_id[did] for did in sorted(deal_id_set) if did in deals_by_id]
        rows.append(compose_practice(
            p, company, contacts, ms, overrides.get(p["ods"]),
            tier=tiers.get(p["ods"]),
            fy_metrics=fy,
            launch_visit=launch_visits.get(p["ods"]),
            first_live_date=first_live_dates.get(p["ods"]),
            deals=prac_deals,
        ))

    write_attribution(rows)


if __name__ == "__main__":
    main()
