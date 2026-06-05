"""
Live-cohort enrichment — channel attribution + engaged-role combinations.

For each of the 36 Live practices:
  1. Get associated contacts from HubSpot
  2. Filter to ENGAGED contacts only (real activity: replied to email,
     attended meeting, was called, was contacted — not just bulk-imported)
  3. Cross-reference engaged contacts against curated HubSpot lists
     (webinar registrants/attendees, event attendees, content downloaders,
     partner-page visitors). List membership = strong channel signal.
  4. Infer dominant channel(s) per practice with evidence
  5. Aggregate engaged-role combinations across the cohort — answer
     "who's in the room when a practice converts?"

Output:
  apps/primary-care-tech-overview/public/data/live_enrichment.json
  apps/primary-care-tech-overview/public/data/hubspot_channel_lists.json (cache)

Run:
  HUBSPOT_API_TOKEN=pat-eu1-... python3 scripts/enrich_live_practices.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DATA = REPO_ROOT / "apps" / "tech-growth-map" / "public" / "data"
DASHBOARD_DATA = REPO_ROOT / "apps" / "primary-care-tech-overview" / "public" / "data"
CACHE = REPO_ROOT / "scripts" / ".attribution_cache"
HUBSPOT_BASE = "https://api-eu1.hubapi.com"


# ---------- HubSpot helper ------------------------------------------------


def hs(method, endpoint, data=None, tries=3):
    token = os.environ.get("HUBSPOT_API_TOKEN", "")
    if not token:
        sys.exit("HUBSPOT_API_TOKEN not set")
    url = f"{HUBSPOT_BASE}{endpoint}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = json.dumps(data).encode() if data else None
    for n in range(tries):
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            if e.code in (429,) or 500 <= e.code < 600:
                time.sleep(1.5 * (2 ** n))
                continue
            raise RuntimeError(f"HS {method} {endpoint} -> {e.code}: {body[:300]}")
    raise RuntimeError(f"HS {method} {endpoint} exhausted retries")


# ---------- Channel taxonomy from list names ------------------------------


def canonical_channel_for(name: str) -> tuple[str, str] | None:
    """Return (canonical_channel, sub_label) if list name implies a channel.

    Crucial distinction:
      - SOURCE lists = "they chose to engage with us" (registered, attended, clicked, downloaded).
        These tell us what BROUGHT THEM IN.
      - OUTREACH lists = "we targeted them" (Suvera invites, polymail batches, nurture).
        These do NOT tell us how they came in; they're outbound activity FROM Suvera.
        Returned as ("Outbound (Suvera)") so we can see it but not confuse with source.
    """
    s = name.lower().strip()

    # Skip non-attributional lists (segmentation, exclusion, technical)
    if re.search(r"^(unmatched|never been sent|nhs data upload|nhs_pcn_)", s):
        return None
    if re.search(r"\b(exclusion|to be removed|cloned|errors\.csv|\.csv$)\b", s):
        return None

    # OUTREACH (Suvera-originated, NOT a source signal)
    if re.search(
        r"\b(invite \d+|invite$|polymail|gmail send|batch \d+|nurture|"
        r"remaining contacts|to receive email|outreach|leads? -|mqls? -|"
        r"unengaged|small pop|gp \+ leadership|minus \(|hs events lists test|"
        r"campaign|outbound)\b", s
    ):
        return ("Outbound (Suvera)", name)

    # WEBINAR — only count active opt-in signals
    if "webinar" in s:
        if "attendee" in s or "attended" in s:
            return ("Webinar (attended)", name)
        if "no show" in s or "no-show" in s:
            return ("Webinar (no-show — registered)", name)
        if "registrant" in s or "registration" in s or "sign up" in s or "signups" in s:
            return ("Webinar (registered)", name)
        if "clicker" in s or "link clicks" in s:
            return ("Webinar (email clicked)", name)
        # Unclassified webinar list — treat as outbound to be conservative
        return ("Outbound (Suvera)", name)

    # EVENTS / CONFERENCES — Suvera-attended events where leads were scanned
    if re.search(r"\b(event|conference|round.?table|best practice|pcpn|"
                 r"croydon training|training hub)\b", s):
        if "attendee" in s or "scanned" in s or "attended" in s or "sign ups" in s:
            return ("Event (attended)", name)
        if "registrant" in s or "registration" in s:
            return ("Event (registered)", name)
        return ("Event (other)", name)

    # CONTENT — inbound: they downloaded / submitted form
    if "downloader" in s or "calculator" in s or "form filler" in s or \
       ("report" in s and "download" in s):
        return ("Content download", name)

    # NHS PARTNERS PAGE — inbound web traffic to Suvera's NHS-facing site
    if "partners visitor" in s or "partners page" in s or "partner survey" in s:
        return ("NHS Partners Page", name)

    # RELATIONSHIP — existing connections, not a channel
    if re.search(r"^(federation|current partners|existing partners|pcn contacts|"
                 r"operational staff of partners|existing, alumni|relevant managers)", s):
        return ("Existing relationship", name)

    # BETA programmes
    if "beta programme" in s or "beta program" in s:
        return ("Beta programme", name)

    return None


# ---------- Fetch lists + classify ---------------------------------------


def fetch_all_lists() -> list[dict]:
    """Paginate /crm/v3/lists/search to enumerate all lists in the portal."""
    cache_path = CACHE / "all_lists.json"
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < 3600:
        return json.loads(cache_path.read_text())
    CACHE.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    while True:
        body = {"limit": 100, "offset": len(out)}
        r = hs("POST", "/crm/v3/lists/search", body)
        results = r.get("lists", []) or r.get("results", [])
        if not results:
            break
        out.extend(results)
        if len(out) >= r.get("total", len(out)):
            break
        if len(out) > 1500:
            break
    cache_path.write_text(json.dumps(out))
    return out


def classify_lists(lists: list[dict]) -> dict[str, dict]:
    """Return list_id -> {name, channel, sublabel}. Only lists that classify."""
    out = {}
    for l in lists:
        nm = l.get("name", "")
        lid = str(l.get("listId") or l.get("id") or "")
        if not lid:
            continue
        c = canonical_channel_for(nm)
        if c:
            out[lid] = {"name": nm, "channel": c[0], "sublabel": c[1]}
    return out


def fetch_list_memberships(list_id: str) -> set[str]:
    """All contact IDs in a list. Cached on disk."""
    cache_path = CACHE / f"list_{list_id}_members.json"
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < 24 * 3600:
        return set(json.loads(cache_path.read_text()))
    CACHE.mkdir(parents=True, exist_ok=True)
    ids: list[str] = []
    after = None
    while True:
        ep = f"/crm/v3/lists/{list_id}/memberships"
        if after:
            ep += f"?after={after}"
        try:
            r = hs("GET", ep)
        except RuntimeError as e:
            # Some lists are unreadable (deleted, restricted). Skip.
            print(f"  list {list_id}: {e}")
            ids = []
            break
        ids.extend(str(m.get("recordId")) for m in r.get("results", []))
        after = r.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
        time.sleep(0.1)
    cache_path.write_text(json.dumps(ids))
    return set(ids)


# ---------- Engaged-contact detection -------------------------------------


def is_engaged(props: dict) -> tuple[bool, list[str]]:
    """Return (engaged?, reasons). Engagement = real, non-passive activity."""
    reasons: list[str] = []
    if props.get("hs_email_first_reply_date"):
        reasons.append("replied to email")
    if props.get("hs_first_outreach_date"):
        reasons.append("had outreach")
    if props.get("hs_sa_first_engagement_date"):
        reasons.append("first engagement")
    if props.get("hs_latest_meeting_activity"):
        reasons.append("meeting activity")
    if props.get("hublead_last_linkedin_message_sent_date") or \
       props.get("hublead_last_linkedin_invitation_accepted_date"):
        reasons.append("LinkedIn outreach")
    if props.get("hs_email_first_open_date"):
        reasons.append("opened email")
    if props.get("hs_email_first_click_date"):
        reasons.append("clicked email")
    return (bool(reasons), reasons)


# ---------- Main ---------------------------------------------------------


def main():
    print("Loading attribution.json to get Live practices...")
    attribution = json.loads((DASHBOARD_DATA / "attribution.json").read_text())
    live = [p for p in attribution["practices"]
            if p["stage"] in ("live_full", "live_partial")]
    print(f"  {len(live)} Live practices")

    print("\nFetching all HubSpot lists...")
    all_lists = fetch_all_lists()
    print(f"  {len(all_lists)} total")
    classified = classify_lists(all_lists)
    print(f"  classified as channel-source: {len(classified)}")
    # Save classification for reference
    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)
    (DASHBOARD_DATA / "hubspot_channel_lists.json").write_text(json.dumps(classified, indent=2))

    by_channel = Counter(v["channel"] for v in classified.values())
    print("  by channel:")
    for ch, n in by_channel.most_common():
        print(f"    {n:>3}  {ch}")

    print("\nFetching memberships for classified lists...")
    list_members: dict[str, set[str]] = {}
    for i, lid in enumerate(classified, 1):
        list_members[lid] = fetch_list_memberships(lid)
        if i % 10 == 0:
            print(f"  fetched {i}/{len(classified)} ({sum(len(v) for v in list_members.values())} memberships total)")

    # Build contact -> [list_id] index
    contact_to_lists: dict[str, list[str]] = {}
    for lid, members in list_members.items():
        for cid in members:
            contact_to_lists.setdefault(cid, []).append(lid)
    print(f"  contacts referenced across any list: {len(contact_to_lists)}")

    # Now per Live practice: which engaged contacts belong to which channel lists?
    enriched: list[dict] = []
    cohort_role_counts: Counter[str] = Counter()
    cohort_combos: Counter[tuple] = Counter()
    cohort_channels: Counter[str] = Counter()

    for p in live:
        engaged_contacts: list[dict] = []
        channels_evidence: list[dict] = []
        roles_at_practice: list[str] = []
        for c in p.get("contacts") or []:
            # The contact rows in attribution.json contain a `engagement_proxy` dict.
            # Reconstruct a quasi-props object for is_engaged()
            proxy = c.get("engagement_proxy") or {}
            props_like = {
                "hs_email_first_reply_date": proxy.get("first_email_reply_date"),
                "hs_email_first_open_date": proxy.get("first_email_open_date"),
                "hs_email_first_click_date": proxy.get("first_email_click_date"),
                "hs_first_outreach_date": proxy.get("first_outreach_date"),
                "hs_latest_meeting_activity": proxy.get("latest_meeting_activity"),
                "hublead_last_linkedin_message_sent_date": proxy.get("linkedin_message_sent"),
                "hublead_last_linkedin_invitation_accepted_date": proxy.get("linkedin_invitation_accepted"),
            }
            engaged, reasons = is_engaged(props_like)
            if not engaged:
                continue
            # Channel lists for this contact
            lids = contact_to_lists.get(str(c["id"]), [])
            channels = [classified[l]["channel"] for l in lids if l in classified]
            channel_details = [{"channel": classified[l]["channel"],
                                "list_name": classified[l]["name"],
                                "list_id": l}
                               for l in lids if l in classified]
            engaged_contacts.append({
                "id": c["id"],
                "name": f"{c.get('firstname') or ''} {c.get('lastname') or ''}".strip(),
                "email": c.get("email"),
                "role": c.get("jobtitle_bucket"),
                "engagement_reasons": reasons,
                "channels": channels,
                "channel_details": channel_details,
            })
            if c.get("jobtitle_bucket"):
                roles_at_practice.append(c["jobtitle_bucket"])

        # Dominant SOURCE channels for this practice (exclude Outbound/Suvera-originated)
        chan_count = Counter(ch for ec in engaged_contacts for ch in ec["channels"])
        outbound_count = chan_count.pop("Outbound (Suvera)", 0)
        dominant = chan_count.most_common(3)
        # Total number of distinct outbound lists this practice is on — secondary signal
        outbound_lists = sum(1 for ec in engaged_contacts
                             for ch in ec["channels"] if ch == "Outbound (Suvera)")
        # Build evidence lines
        for ec in engaged_contacts:
            for cd in ec["channel_details"]:
                channels_evidence.append({
                    "contact": ec["name"],
                    "role": ec["role"],
                    "channel": cd["channel"],
                    "list": cd["list_name"],
                })

        # Decide channel attribution
        # - SOURCE signal (inbound/opt-in) > outbound > unknown
        if dominant:
            channel = ", ".join(d[0] for d in dominant)
            confidence = "high"
        elif outbound_count and engaged_contacts:
            channel = "Outbound (Suvera-led)"
            confidence = "medium"
        elif engaged_contacts:
            channel = "Sales-led (no list signal)"
            confidence = "low"
        else:
            channel = "Unknown"
            confidence = "unknown"

        # Cohort accumulators
        unique_roles_here = sorted(set(roles_at_practice))
        for r in unique_roles_here:
            cohort_role_counts[r] += 1
        if len(unique_roles_here) >= 2:
            for combo in combinations(unique_roles_here, 2):
                cohort_combos[combo] += 1
            cohort_combos[tuple(unique_roles_here)] += 1  # full combo
        if dominant:
            for ch, _ in dominant:
                cohort_channels[ch] += 1
        else:
            cohort_channels["Unknown"] += 1

        enriched.append({
            "ods": p["ods"],
            "name": p["name"],
            "stage": p["stage"],
            "icb": p.get("icb"),
            "patients": p.get("patients"),
            "primary_role": p.get("primary_role"),
            "engaged_contact_count": len(engaged_contacts),
            "engaged_roles": sorted(set(roles_at_practice)),
            "channel_attribution": {
                "channels_ranked": dominant,
                "primary": dominant[0][0] if dominant else channel,
                "confidence": confidence,
                "outbound_list_touches": outbound_count,
                "evidence": [e for e in channels_evidence if "outbound" not in e.get("channel","").lower()][:10],
                "outbound_evidence_sample": [e for e in channels_evidence if "outbound" in e.get("channel","").lower()][:5],
            },
            "engaged_contacts": engaged_contacts,
        })

    # Cohort-level summary
    summary = {
        "cohort_size": len(live),
        "engaged_role_frequency": dict(cohort_role_counts.most_common()),
        "engaged_role_pair_frequency": {
            " + ".join(k): v for k, v in cohort_combos.most_common(20)
        },
        "channel_attribution_summary": dict(cohort_channels.most_common()),
    }

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cohort": "live",
        "summary": summary,
        "practices": enriched,
    }
    out_path = DASHBOARD_DATA / "live_enrichment.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")

    print("\n=== SUMMARY ===")
    print(f"Cohort: {len(live)} Live practices")
    print(f"\nEngaged-role frequency (# practices where role appears):")
    for r, n in cohort_role_counts.most_common():
        print(f"  {n:>3}  {r}")
    print(f"\nTop role combinations:")
    for combo, n in cohort_combos.most_common(10):
        print(f"  {n:>3}  {' + '.join(combo)}")
    print(f"\nChannel attribution across Live cohort:")
    for ch, n in cohort_channels.most_common():
        print(f"  {n:>3}  {ch}")


if __name__ == "__main__":
    main()
