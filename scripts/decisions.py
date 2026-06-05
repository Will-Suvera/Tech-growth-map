"""
Generate decisions.json — the "Do this next week" cards that anchor the
Planner Growth Dashboard home page. Three buckets:

  💰 Revenue moves        — money on the table
  ⚡ Activation moves     — signed but not getting value
  🔴 Pipeline moves       — deals at risk

Each card resolves to a list of practice IDs the dashboard can deep-link to.

Run AFTER score_practices.py + compute_territory.py:
  python3 scripts/decisions.py
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DATA = REPO_ROOT / "attribution-dashboard" / "public" / "data"
ATTRIBUTION_PATH = DASHBOARD_DATA / "attribution.json"
DECISIONS_PATH = DASHBOARD_DATA / "decisions.json"

DEMO_STALE_DAYS = 30
RECENT_ACTIVITY_DAYS = 30


def days_since(date_str):
    if not date_str:
        return None
    try:
        return (dt.date.today() - dt.date.fromisoformat(date_str[:10])).days
    except Exception:
        return None


def last_activity_days(row: dict) -> int | None:
    candidates = []
    for c in row.get("contacts") or []:
        ep = c.get("engagement_proxy") or {}
        for k in ("first_email_reply_date", "first_email_click_date",
                  "first_email_open_date", "latest_meeting_activity"):
            v = ep.get(k)
            if v:
                candidates.append(v)
    candidates += [m.get("date") for m in (row.get("meetings") or []) if m.get("date")]
    days = [d for d in (days_since(c) for c in candidates) if d is not None]
    return min(days) if days else None


# ---------- Rules: each returns {title, hook, evidence, practice_ids, cta} or None


def rule_near_cap(rows):
    matches = [r for r in rows if r.get("health_bucket") == "near_cap"]
    if not matches:
        return None
    return {
        "id": "near_cap",
        "bucket": "revenue",
        "title": "Pitch paid before they hit the freemium cap",
        "hook": f"{len(matches)} freemium practice(s) within 500 recalls of the 2,000 cap",
        "practice_ids": sorted(r["ods"] for r in matches),
        "cta": "Open pitch list",
        "filter": {"health_bucket": "near_cap"},
    }


def rule_testimonial_ready(rows):
    matches = [r for r in rows if r.get("health_bucket") == "testimonial_ready"]
    if not matches:
        return None
    return {
        "id": "testimonial_ready",
        "bucket": "revenue",
        "title": "Ask for a case study",
        "hook": f"{len(matches)} practice(s) past 500 FY recalls — product believers",
        "practice_ids": sorted(r["ods"] for r in matches),
        "cta": "Open testimonial list",
        "filter": {"health_bucket": "testimonial_ready"},
    }


def rule_expansion_super_user(rows):
    matches = [r for r in rows if r.get("health_bucket") == "expansion_super_user"]
    if not matches:
        return None
    return {
        "id": "expansion_super_user",
        "bucket": "revenue",
        "title": "Expansion conversation",
        "hook": f"{len(matches)} super-user(s) — high recall + pathology volume per patient",
        "practice_ids": sorted(r["ods"] for r in matches),
        "cta": "Open expansion list",
        "filter": {"health_bucket": "expansion_super_user"},
    }


def rule_vc_paying_not_using(rows):
    matches = [r for r in rows if r.get("health_bucket") == "vc_paying_not_using"]
    if not matches:
        return None
    return {
        "id": "vc_paying_not_using",
        "bucket": "activation",
        "title": "Re-launch — paying-not-using",
        "hook": f"{len(matches)} VC practice(s) live with zero recalls this month",
        "practice_ids": sorted(r["ods"] for r in matches),
        "cta": "Open re-launch list",
        "filter": {"health_bucket": "vc_paying_not_using"},
    }


def rule_dormant(rows):
    matches = [r for r in rows if r.get("health_bucket") == "dormant"]
    if not matches:
        return None
    return {
        "id": "dormant",
        "bucket": "activation",
        "title": "Activation needed — Live but no recalls",
        "hook": f"{len(matches)} live practice(s) with zero recalls this month",
        "practice_ids": sorted(r["ods"] for r in matches),
        "cta": "Open dormant list",
        "filter": {"health_bucket": "dormant"},
    }


def rule_live_no_launch_visit(rows):
    matches = [
        r for r in rows
        if r.get("stage") in {"live_full", "live_partial"}
        and r.get("practice_visit_status") in (None, "none")
    ]
    if not matches:
        return None
    return {
        "id": "live_no_launch_visit",
        "bucket": "activation",
        "title": "Book a launch visit",
        "hook": f"{len(matches)} live practice(s) without a logged launch visit",
        "practice_ids": sorted(r["ods"] for r in matches),
        "cta": "Open launch-visit gap list",
        "filter": {"practice_visit_status": "none", "is_live": True},
    }


def rule_signed_up_no_meeting(rows):
    matches = []
    for r in rows:
        if r.get("stage") != "signed_up":
            continue
        if (r.get("meeting_count") or 0) > 0:
            continue
        last = last_activity_days(r)
        if last is None or last >= RECENT_ACTIVITY_DAYS:
            matches.append(r)
    if not matches:
        return None
    return {
        "id": "signed_up_no_meeting",
        "bucket": "pipeline",
        "title": "Chase or disqualify — cold at top of funnel",
        "hook": f"{len(matches)} signed-up practice(s) with no meeting and no recent activity",
        "practice_ids": sorted(r["ods"] for r in matches),
        "cta": "Open cold-signups list",
        "filter": {"stage": "signed_up", "meeting_count_max": 0},
    }


def rule_demo_no_progress(rows):
    matches = []
    for r in rows:
        if r.get("stage") not in {"signed_up", "onboarding"}:
            continue
        if (r.get("meeting_count") or 0) == 0:
            continue
        last = last_activity_days(r)
        if last is not None and last > DEMO_STALE_DAYS:
            matches.append(r)
    if not matches:
        return None
    return {
        "id": "demo_no_progress",
        "bucket": "pipeline",
        "title": "Reach out post-demo — cold for >30 days",
        "hook": f"{len(matches)} practice(s) with a demo logged but no activity in {DEMO_STALE_DAYS}+ days",
        "practice_ids": sorted(r["ods"] for r in matches),
        "cta": "Open cold-post-demo list",
        "filter": {"demo_stale": True},
    }


RULES = [
    rule_near_cap,
    rule_testimonial_ready,
    rule_expansion_super_user,
    rule_vc_paying_not_using,
    rule_dormant,
    rule_live_no_launch_visit,
    rule_signed_up_no_meeting,
    rule_demo_no_progress,
]


def main() -> None:
    if not ATTRIBUTION_PATH.exists():
        raise SystemExit(f"{ATTRIBUTION_PATH} not found — run refresh_attribution.py + score_practices.py first")
    payload = json.loads(ATTRIBUTION_PATH.read_text())
    rows = payload.get("practices") or []

    cards = []
    for rule in RULES:
        card = rule(rows)
        if card:
            cards.append(card)

    by_bucket: dict[str, list[dict]] = {"revenue": [], "activation": [], "pipeline": []}
    for c in cards:
        by_bucket[c["bucket"]].append(c)

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cards": cards,
        "by_bucket": by_bucket,
        "totals": {b: sum(len(c["practice_ids"]) for c in cs) for b, cs in by_bucket.items()},
    }
    DECISIONS_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"Wrote {DECISIONS_PATH.name}: {len(cards)} cards")
    for c in cards:
        print(f"  [{c['bucket']:11s}] {c['title']} — {len(c['practice_ids'])} practices")


if __name__ == "__main__":
    main()
