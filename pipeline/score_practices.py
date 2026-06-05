"""
Compute Health buckets, priority score, and next-action strings for every
practice in attribution.json. Writes back in-place (no shrink risk — same row
count, just extra fields).

Run AFTER refresh_attribution.py:
  python3 scripts/score_practices.py

See docs/planner_growth_dashboard.md (Health buckets + Priority score sections).
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DATA = REPO_ROOT / "apps" / "primary-care-tech-overview" / "public" / "data"
ATTRIBUTION_PATH = DASHBOARD_DATA / "attribution.json"

# Health bucket constants (single source of truth — mirrored in
# attribution-dashboard/src/utils/funnel.js for the frontend pills).
NEAR_CAP_THRESHOLD = 1000        # ≥1,000 of 2,000 freemium recalls used (halfway = "nearing end")
TESTIMONIAL_THRESHOLD = 500      # > 500 FY recalls
EXPANSION_FORMS_PER_PATIENT = 0.05
DEMO_STALE_DAYS = 30
RECENCY_FRESH_DAYS = 90

HEALTH_BUCKETS_ORDER = [
    "near_cap",
    "testimonial_ready",
    "expansion_super_user",
    "vc_paying_not_using",
    "cadence_dropping",
    "dormant",
    "healthy",
    "pre_live",
]

HEALTH_BUCKET_LABELS = {
    "near_cap": "🔥 Near freemium cap",
    "testimonial_ready": "🏆 Testimonial-ready",
    "expansion_super_user": "💎 Expansion super-user",
    "vc_paying_not_using": "⚡ VC paying-not-using",
    "cadence_dropping": "🟠 Cadence dropping",
    "dormant": "🔴 Dormant",
    "healthy": "🟢 Healthy",
    "pre_live": "⚪ Pre-live",
}

HEALTH_BUCKET_WEIGHTS = {
    "near_cap": 25,
    "testimonial_ready": 22,
    "expansion_super_user": 20,
    "vc_paying_not_using": 18,
    "cadence_dropping": 15,
    "dormant": 12,
    "healthy": 5,
    "pre_live": 2,
}

TIER_ARR_MULTIPLIER = {
    "Money-back": 1.0,
    "Freemium": 0.5,
    "VC": 0.3,
}

STAGE_PROXIMITY = {
    "live_full": 20,
    "live_partial": 18,
    "onboarding": 15,
    "signed_up": 8,
}

LIVE_STAGES = {"live_full", "live_partial"}


def is_live(row: dict) -> bool:
    return row.get("stage") in LIVE_STAGES


def health_bucket(row: dict) -> str:
    """Single-bucket classifier, highest-priority match wins.

    Priority order encodes "money on the table beats things on fire".
    See docs/planner_growth_dashboard.md.
    """
    tier = row.get("tier") or "Freemium"
    fy_recalls = row.get("recalls_fy_to_date") or 0
    forms_per_patient = row.get("bloods_per_patient_fy") or 0
    recalls_this_month = row.get("recalls_this_month") or 0
    live = is_live(row)

    # 1. Near freemium cap — Freemium with >=1,500 FY recalls
    if tier == "Freemium" and fy_recalls >= NEAR_CAP_THRESHOLD:
        return "near_cap"

    # 2. Testimonial-ready — any tier, >500 FY recalls (overlaps with super-user
    #    deliberately; expansion takes precedence if forms/patient is strong)
    if fy_recalls > TESTIMONIAL_THRESHOLD and forms_per_patient > EXPANSION_FORMS_PER_PATIENT:
        return "expansion_super_user"
    if fy_recalls > TESTIMONIAL_THRESHOLD:
        return "testimonial_ready"

    # 4. VC paying-not-using — has the bundle, Live, not recalling
    if tier == "VC" and live and recalls_this_month == 0:
        return "vc_paying_not_using"

    # 5. Cadence dropping — needs rolling 3mo per-practice history. The
    #    public Omni feed doesn't carry that yet (acknowledged v2 gap in
    #    docs/planner_growth_dashboard.md). Skip until backfill exists.

    # 6. Dormant — Live, not recalling, not the VC case above
    if live and recalls_this_month == 0:
        return "dormant"

    # 7. Healthy — Live AND recalling this month
    if live and recalls_this_month > 0:
        return "healthy"

    # 8. Pre-live — everything else (signed_up, onboarding)
    return "pre_live"


def days_since(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        d = dt.datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except Exception:
        try:
            d = dt.date.fromisoformat(date_str[:10])
        except Exception:
            return None
    return (dt.date.today() - d).days


def role_completeness(row: dict) -> int:
    """0–10: 10 if GP Partner + Practice Manager both engaged, 5 if one, 0 if neither."""
    roles = set(row.get("engaged_roles") or [])
    has_partner = "GP Partner" in roles
    has_pm = "Practice Manager" in roles
    if has_partner and has_pm:
        return 10
    if has_partner or has_pm:
        return 5
    return 0


def arr_potential_score(row: dict) -> int:
    """0–25: log-scaled patients × tier multiplier.

    log10(10_000) ≈ 4. We scale so a 10k-patient practice on Money-back hits the top.
    """
    patients = row.get("patients") or 0
    tier = row.get("tier") or "Freemium"
    if patients <= 0:
        return 0
    log_patients = math.log10(max(1, patients))  # ~3.0 (1k) … ~4.3 (20k)
    normalised = min(1.0, log_patients / 4.3)
    base = normalised * 25
    return int(round(base * TIER_ARR_MULTIPLIER.get(tier, 0.5)))


def stage_proximity_score(row: dict) -> int:
    return STAGE_PROXIMITY.get(row.get("stage"), 0)


def recency_score(row: dict) -> int:
    """0–10: practices touched recently rank higher. signed_up_date or latest engagement."""
    candidates = [
        row.get("signed_up_date"),
    ]
    # Pull latest engagement date across contacts if present
    for c in row.get("contacts") or []:
        ep = c.get("engagement_proxy") or {}
        for k in ("first_email_reply_date", "first_email_click_date",
                  "first_email_open_date", "latest_meeting_activity"):
            if ep.get(k):
                candidates.append(ep[k])
    days = [d for d in (days_since(c) for c in candidates) if d is not None]
    if not days:
        return 0
    most_recent = min(days)
    if most_recent <= RECENCY_FRESH_DAYS:
        return 10
    # Linear decay over the next 270 days, then 0
    if most_recent <= RECENCY_FRESH_DAYS + 270:
        return max(0, int(round(10 * (1 - (most_recent - RECENCY_FRESH_DAYS) / 270))))
    return 0


def expansion_kicker(row: dict) -> int:
    """0–10: PCN beachhead bonus. Populated by compute_territory.py — read pcn_untapped_count."""
    untapped = row.get("pcn_untapped_count")
    if not untapped:
        return 0
    if untapped >= 5:
        return 10
    if untapped >= 3:
        return 6
    if untapped >= 1:
        return 3
    return 0


def next_action_for(row: dict, bucket: str) -> str:
    """Short imperative for the practice row + drilldown."""
    fy = row.get("recalls_fy_to_date") or 0
    if bucket == "near_cap":
        remaining = max(0, 2000 - fy)
        return f"Pitch paid — {remaining} recalls from cap"
    if bucket == "testimonial_ready":
        return f"Ask for case study — {fy} FY recalls"
    if bucket == "expansion_super_user":
        return f"Expansion conversation — super-user signal"
    if bucket == "vc_paying_not_using":
        return "Re-launch — VC bundle paid, no recall activity"
    if bucket == "cadence_dropping":
        return "Check in — recall cadence dropping"
    if bucket == "dormant":
        return "Activation needed — Live but no recalls this month"
    if bucket == "healthy":
        return "Leave alone — healthy"
    # pre_live
    stage = row.get("stage")
    if stage == "signed_up":
        if not (row.get("meeting_count") or 0):
            return "Chase or disqualify — no meeting booked"
        return "Push toward DPA"
    if stage == "onboarding":
        if row.get("practice_visit_status") in (None, "none"):
            return "Book launch visit"
        return "Drive to Live"
    return "Funnel motion"


def score_row(row: dict) -> dict:
    bucket = health_bucket(row)
    arr_pts = arr_potential_score(row)
    stage_pts = stage_proximity_score(row)
    bucket_pts = HEALTH_BUCKET_WEIGHTS.get(bucket, 0)
    role_pts = role_completeness(row)
    expansion_pts = expansion_kicker(row)
    recency_pts = recency_score(row)
    total = arr_pts + stage_pts + bucket_pts + role_pts + expansion_pts + recency_pts
    return {
        "health_bucket": bucket,
        "health_bucket_label": HEALTH_BUCKET_LABELS[bucket],
        "priority_score": total,
        "priority_breakdown": {
            "arr_potential": arr_pts,
            "stage_proximity": stage_pts,
            "health_bucket": bucket_pts,
            "role_completeness": role_pts,
            "expansion_kicker": expansion_pts,
            "recency": recency_pts,
        },
        "next_action": next_action_for(row, bucket),
    }


def main() -> None:
    if not ATTRIBUTION_PATH.exists():
        raise SystemExit(f"{ATTRIBUTION_PATH} not found — run refresh_attribution.py first")

    payload = json.loads(ATTRIBUTION_PATH.read_text())
    rows = payload.get("practices") or []

    bucket_counts: dict[str, int] = {}
    for row in rows:
        scored = score_row(row)
        row.update(scored)
        bucket_counts[scored["health_bucket"]] = bucket_counts.get(scored["health_bucket"], 0) + 1

    # Surface bucket counts in stats roll-up so the dashboard header can read them.
    stats = payload.setdefault("stats", {})
    stats["by_health_bucket"] = dict(sorted(bucket_counts.items()))
    payload["scored_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    ATTRIBUTION_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"Scored {len(rows)} practices · " +
          " · ".join(f"{n} {b}" for b, n in sorted(bucket_counts.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
