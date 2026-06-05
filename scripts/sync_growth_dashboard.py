"""
Planner growth dashboard sync.

Builds a revenue-weighted, decision-ready dataset from the existing
attribution pipeline outputs without writing to the Google Sheets onboarding
tracker. The Google Sheet is treated as read-only upstream data via the JSON
files already produced by refresh_data.py.

Outputs:
  attribution-dashboard/public/data/growth_dashboard.json
  attribution-dashboard/public/data/growth_summary.json
  attribution-dashboard/public/data/meeting_intelligence.json
  attribution-dashboard/public/data/manual_overrides.template.json

Optional env:
  HUBSPOT_API_TOKEN   - if present and --skip-hubspot is not passed, refreshes
                        attribution.json and live_enrichment.json first.
  NOTION_API_TOKEN    - if present and --skip-notion is not passed, refreshes
                        public/data/notion_meetings.json from the Partner
                        Meeting Library.

Run:
  python3 scripts/sync_growth_dashboard.py --skip-hubspot --skip-notion
  HUBSPOT_API_TOKEN=... NOTION_API_TOKEN=... python3 scripts/sync_growth_dashboard.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DATA = REPO_ROOT / "public" / "data"
DASHBOARD_DATA = REPO_ROOT / "attribution-dashboard" / "public" / "data"

ARR_PER_PATIENT = 0.75
ARR_TARGET = 1_000_000

NOTION_DATABASE_ID = os.environ.get(
    "NOTION_PARTNER_MEETING_DATABASE_ID",
    "cb96551db62b4d6f9eaa05f50995e9d7",
)
NOTION_DATA_SOURCE_ID = os.environ.get(
    "NOTION_PARTNER_MEETING_DATA_SOURCE_ID",
    "8115f0ee00c8488aa05b57726af0acf4",
)

SOURCE_CONFIDENCE_ORDER = {
    "manual": 5,
    "confirmed": 4,
    "strong_inferred": 3,
    "weak_inferred": 2,
    "unknown": 1,
}


# ---------------------------------------------------------------------------
# Small pure helpers used by tests
# ---------------------------------------------------------------------------


def contracted_arr(patients: int | float | None) -> float:
    if patients is None:
        return 0.0
    try:
        return round(float(patients) * ARR_PER_PATIENT, 2)
    except (TypeError, ValueError):
        return 0.0


def arr_band(arr: float) -> str:
    if arr <= 0:
        return "unknown"
    if arr < 3_000:
        return "<£3k"
    if arr < 6_000:
        return "£3-6k"
    if arr < 9_000:
        return "£6-9k"
    if arr < 13_500:
        return "£9-13.5k"
    return "£13.5k+"


def normalise_source_confidence(value: str | None, has_raw_source: bool = False) -> str:
    if value == "manual":
        return "manual"
    if value in {"confirmed", "strong_inferred", "weak_inferred", "unknown"}:
        return value
    if value == "high":
        return "confirmed" if has_raw_source else "strong_inferred"
    if value == "medium":
        return "strong_inferred"
    if value == "low":
        return "weak_inferred"
    return "unknown"


def apply_source_precedence(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """Manual override > confirmed source > inferred source > unknown."""
    if override and override.get("source"):
        return {
            "source": override["source"],
            "source_confidence": "manual",
            "source_override": override,
            "source_evidence": override.get("source_evidence")
            or override.get("notes")
            or "Manual override",
        }

    source = base.get("source") or "Unknown"
    has_raw = bool(base.get("source_raw"))
    confidence = normalise_source_confidence(base.get("source_confidence"), has_raw)
    evidence = base.get("source_inferred_evidence") or []
    if source == "Unknown":
        confidence = "unknown"
    return {
        "source": source,
        "source_confidence": confidence,
        "source_override": None,
        "source_evidence": evidence,
    }


def role_combo(roles: list[str]) -> str | None:
    clean = sorted({r for r in roles if r})
    return " + ".join(clean) if clean else None


def usage_status(stage: str, is_recalling: bool, is_recently_active: bool) -> str:
    if is_recalling:
        return "recalling_this_month"
    if is_recently_active:
        return "recently_active"
    if stage in {"live_full", "live_partial"}:
        return "live_no_recent_recall"
    return "not_live"


def days_between(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        a = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (b - a).days)


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"Wrote {path.relative_to(REPO_ROOT)}")


def load_manual_overrides() -> dict[str, dict]:
    """Load overrides from either public app data or root public/data."""
    candidates = [
        DASHBOARD_DATA / "manual_overrides.json",
        PUBLIC_DATA / "growth_manual_overrides.json",
    ]
    merged: dict[str, dict] = {}
    for path in candidates:
        raw = load_json(path, {})
        if not isinstance(raw, dict):
            continue
        for ods, value in raw.items():
            if isinstance(value, dict):
                merged[ods.upper()] = value
    return merged


def write_override_template() -> None:
    template = {
        "A12345": {
            "source": "Webinar (registered)",
            "source_confidence": "manual",
            "role": "GP Partner",
            "opportunity_signal": "High",
            "notes": "Example only. Save real overrides as manual_overrides.json.",
        }
    }
    write_json(DASHBOARD_DATA / "manual_overrides.template.json", template)


# ---------------------------------------------------------------------------
# Optional Notion pull
# ---------------------------------------------------------------------------


def notion_request(method: str, endpoint: str, token: str, data: Any = None, version: str = "2022-06-28") -> dict:
    url = f"https://api.notion.com{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": version,
    }
    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def rich_text_plain(value: dict | list | None) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return "".join(part.get("plain_text", "") for part in value)
    if isinstance(value, dict):
        for key in ("title", "rich_text"):
            if key in value:
                return rich_text_plain(value[key])
        if "plain_text" in value:
            return value["plain_text"]
    return ""


def parse_notion_page(page: dict) -> dict:
    props = page.get("properties", {})

    def text(name: str) -> str:
        return rich_text_plain(props.get(name))

    def select(name: str) -> str | None:
        item = (props.get(name) or {}).get("select")
        return item.get("name") if item else None

    def multi_select(name: str) -> list[str]:
        return [x.get("name") for x in (props.get(name) or {}).get("multi_select", []) if x.get("name")]

    def date_value(name: str) -> str | None:
        item = (props.get(name) or {}).get("date")
        return item.get("start") if item else None

    def url_value(name: str) -> str | None:
        return (props.get(name) or {}).get("url")

    return {
        "id": page.get("id"),
        "url": page.get("url"),
        "title": text("Meeting"),
        "meeting": text("Meeting"),
        "practice": text("Practice"),
        "partner_role": select("Partner Role"),
        "main_themes": multi_select("Main Theme"),
        "opportunity_signal": select("Opportunity Signal"),
        "attendees": text("Attendees"),
        "date": date_value("Date"),
        "fathom_url": url_value("Fathom Recording"),
        "status": select("Status"),
        "meeting_id": text("Meeting ID"),
    }


def fetch_notion_meetings(token: str) -> list[dict]:
    """Fetch Partner Meeting Library using Notion API.

    Uses the older database-query endpoint first because the token most likely
    targets the database URL the user supplied; falls back to the data source
    endpoint if the workspace has migrated.
    """
    endpoints = [
        (f"/v1/databases/{NOTION_DATABASE_ID}/query", "2022-06-28"),
        (f"/v1/data_sources/{NOTION_DATA_SOURCE_ID}/query", "2025-09-03"),
    ]
    last_error = None
    for endpoint, version in endpoints:
        try:
            rows: list[dict] = []
            cursor = None
            while True:
                body: dict[str, Any] = {"page_size": 100}
                if cursor:
                    body["start_cursor"] = cursor
                resp = notion_request("POST", endpoint, token, body, version)
                rows.extend(parse_notion_page(page) for page in resp.get("results", []))
                if not resp.get("has_more"):
                    break
                cursor = resp.get("next_cursor")
                time.sleep(0.2)
            return rows
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as exc:
            last_error = exc
            continue
    raise RuntimeError(f"Unable to fetch Notion meetings: {last_error}")


def maybe_refresh_notion(skip: bool) -> None:
    if skip:
        return
    token = os.environ.get("NOTION_API_TOKEN")
    if not token:
        print("NOTION_API_TOKEN not set; using existing public/data/notion_meetings.json")
        return
    print("Refreshing Notion Partner Meeting Library...")
    meetings = fetch_notion_meetings(token)
    write_json(PUBLIC_DATA / "notion_meetings.json", meetings)


def maybe_refresh_hubspot(skip: bool) -> None:
    if skip:
        return
    if not os.environ.get("HUBSPOT_API_TOKEN"):
        print("HUBSPOT_API_TOKEN not set; using existing attribution files")
        return
    print("Refreshing HubSpot attribution data...")
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    refresh_attribution = importlib.import_module("refresh_attribution")
    refresh_attribution.main()
    print("Refreshing Live cohort list enrichment...")
    enrich_live_practices = importlib.import_module("enrich_live_practices")
    enrich_live_practices.main()


# ---------------------------------------------------------------------------
# Growth model composition
# ---------------------------------------------------------------------------


def recall_maps() -> tuple[set[str], set[str], dict[str, int]]:
    data = load_json(PUBLIC_DATA / "recalls.json", {})
    active_month = {x.upper() for x in data.get("active_ods_this_month", []) if x}
    active_recent = {x.upper() for x in data.get("active_ods_recent", []) if x}
    counts = {
        (row.get("ods") or "").upper(): int(row.get("count") or 0)
        for row in data.get("recalls", {}).get("practices_this_month", [])
        if row.get("ods")
    }
    return active_month, active_recent, counts


def contact_activity_counts(contacts: list[dict]) -> dict[str, Any]:
    email = 0
    latest: str | None = None
    for c in contacts:
        proxy = c.get("engagement_proxy") or {}
        for key in (
            "first_email_send_date",
            "first_email_open_date",
            "first_email_click_date",
            "first_email_reply_date",
        ):
            if proxy.get(key):
                email += 1
                latest = max(latest or proxy[key], proxy[key])
        for key in ("first_outreach_date", "latest_meeting_activity"):
            if proxy.get(key):
                latest = max(latest or proxy[key], proxy[key])
    return {"email_touch_count": email, "last_touch_date": latest}


def stage_dates_from_contacts(contacts: list[dict]) -> dict[str, str | None]:
    fields = {
        "first_touch_date": "createdate",
        "signed_date": "opportunity",
        "live_date": "customer",
    }
    out = {k: None for k in fields}
    for c in contacts:
        if c.get("createdate"):
            out["first_touch_date"] = min(out["first_touch_date"] or c["createdate"], c["createdate"])
        sd = c.get("stage_dates") or {}
        for out_key, stage_key in fields.items():
            if out_key == "first_touch_date":
                continue
            value = sd.get(stage_key)
            if value:
                out[out_key] = min(out[out_key] or value, value)
    return out


def live_enrichment_index() -> dict[str, dict]:
    data = load_json(DASHBOARD_DATA / "live_enrichment.json", {})
    return {p["ods"].upper(): p for p in data.get("practices", [])}


def dominant_meeting_fields(row: dict) -> dict[str, Any]:
    meetings = row.get("meetings") or []
    themes = [t for m in meetings for t in (m.get("main_themes") or [])]
    signals = [m.get("opportunity_signal") for m in meetings if m.get("opportunity_signal")]
    partner_roles = [m.get("partner_role") for m in meetings if m.get("partner_role")]
    return {
        "themes": [k for k, _ in Counter(themes).most_common(5)],
        "opportunity_signal": signals[-1] if signals else row.get("latest_opportunity_signal"),
        "meeting_partner_roles": sorted(set(partner_roles)),
        "pain_points": [],
        "objections": [],
    }


def priority_for(row: dict) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []
    arr = row["contracted_arr"]
    if arr >= 13_500:
        score += 25
        reasons.append("large ARR")
    elif arr >= 9_000:
        score += 20
        reasons.append("good ARR")
    elif arr >= 6_000:
        score += 15

    if row["stage"] in {"live_full", "live_partial"}:
        score += 15
        reasons.append("already live")
    elif row["stage"] == "signed_up":
        score += 20
        reasons.append("signed, not live")

    if row["usage_status"] == "recalling_this_month":
        score += 20
        reasons.append("active recall")
    elif row["usage_status"] == "live_no_recent_recall":
        score += 12
        reasons.append("live but no recent recall")

    if row.get("role_combo") and "GP Partner" in row["role_combo"] and "Practice Manager" in row["role_combo"]:
        score += 20
        reasons.append("GP Partner + PM involved")
    elif row.get("engaged_roles"):
        score += 10
        reasons.append("engaged contact")

    conf = row.get("source_confidence")
    if conf in {"manual", "confirmed", "strong_inferred"}:
        score += 10
    elif conf == "unknown":
        reasons.append("source unknown")

    if row.get("days_signed_to_live") is not None and row["days_signed_to_live"] <= 30:
        score += 10
        reasons.append("fast activation")
    elif row["stage"] == "signed_up":
        reasons.append("needs activation")

    return min(score, 100), "; ".join(reasons[:4]) or "Needs review"


def build_growth_rows() -> list[dict]:
    attribution = load_json(DASHBOARD_DATA / "attribution.json", {})
    rows = attribution.get("practices", [])
    overrides = load_manual_overrides()
    live_idx = live_enrichment_index()
    active_month, active_recent, recall_counts = recall_maps()
    growth_rows: list[dict] = []

    for row in rows:
        ods = row["ods"].upper()
        live_extra = live_idx.get(ods, {})
        override = overrides.get(ods)
        source = apply_source_precedence(row, override)
        arr = contracted_arr(row.get("patients"))
        stage_dates = stage_dates_from_contacts(row.get("contacts") or [])
        if row.get("stage") not in {"live_full", "live_partial"}:
            stage_dates["live_date"] = None
        elif (
            stage_dates.get("signed_date")
            and stage_dates.get("live_date")
            and days_between(stage_dates["live_date"], stage_dates["signed_date"]) is not None
            and stage_dates["live_date"] < stage_dates["signed_date"]
        ):
            stage_dates["live_date"] = None
        meeting_fields = dominant_meeting_fields(row)
        activity = contact_activity_counts(row.get("contacts") or [])

        engaged_roles = live_extra.get("engaged_roles")
        if not engaged_roles:
            engaged_roles = sorted(k for k, v in (row.get("role_counts") or {}).items() if v)
        if override and override.get("role"):
            primary_role = override["role"]
        else:
            primary_role = live_extra.get("primary_role") or row.get("primary_role")

        is_recalling = ods in active_month
        is_recent = ods in active_recent
        usage = usage_status(row.get("stage"), is_recalling, is_recent)
        meeting_count = row.get("meeting_count") or len(row.get("meetings") or [])

        if live_extra.get("channel_attribution", {}).get("primary") and source["source_confidence"] in {"unknown", "weak_inferred"}:
            source = {
                "source": live_extra["channel_attribution"]["primary"],
                "source_confidence": "strong_inferred",
                "source_override": None,
                "source_evidence": live_extra["channel_attribution"].get("evidence") or [],
            }

        out = {
            "ods": ods,
            "name": row.get("name"),
            "icb": row.get("icb"),
            "pcn_name": row.get("pcn_name"),
            "patients": row.get("patients"),
            "stage": row.get("stage"),
            "contracted_arr": arr,
            "arr_band": arr_band(arr),
            "target_contribution_pct": round((arr / ARR_TARGET) * 100, 3),
            "first_touch_date": stage_dates["first_touch_date"] or row.get("signed_up_date"),
            "demo_date": (row.get("meetings") or [{}])[0].get("date") if row.get("meetings") else None,
            "signed_date": stage_dates["signed_date"] or row.get("signed_up_date"),
            "live_date": stage_dates["live_date"],
            "days_to_signed": days_between(stage_dates["first_touch_date"], stage_dates["signed_date"]),
            "days_signed_to_live": days_between(stage_dates["signed_date"], stage_dates["live_date"]),
            **source,
            "engaged_roles": engaged_roles,
            "primary_role": primary_role,
            "role_combo": role_combo(engaged_roles),
            "engaged_contact_count": live_extra.get("engaged_contact_count") or len(row.get("contacts") or []),
            "email_touch_count": activity["email_touch_count"],
            "meeting_count": meeting_count,
            "call_count": 0,
            "note_count": 0,
            "last_touch_date": activity["last_touch_date"],
            **meeting_fields,
            "is_recalling": is_recalling,
            "patients_awaiting_recall": recall_counts.get(ods, 0),
            "recall_cadence": "this_month" if is_recalling else ("recent" if is_recent else "none"),
            "usage_status": usage,
            "contacts": row.get("contacts") or [],
            "meetings": row.get("meetings") or [],
        }
        out["priority_score"], out["priority_reason"] = priority_for(out)
        growth_rows.append(out)
    return growth_rows


def source_performance(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row.get("source") or "Unknown"].append(row)
    out = []
    for source, items in grouped.items():
        live = [r for r in items if r["stage"] in {"live_full", "live_partial"}]
        usage = [r for r in items if r["is_recalling"]]
        out.append({
            "source": source,
            "practices": len(items),
            "contracted_arr": round(sum(r["contracted_arr"] for r in items), 2),
            "live_practices": len(live),
            "recalling_practices": len(usage),
            "live_rate": round(len(live) / len(items) * 100, 1) if items else 0,
            "usage_rate": round(len(usage) / len(items) * 100, 1) if items else 0,
        })
    return sorted(out, key=lambda x: (x["contracted_arr"], x["live_rate"]), reverse=True)


def meeting_intelligence(rows: list[dict]) -> dict:
    theme_counts = Counter(t for r in rows for t in (r.get("themes") or []))
    signal_counts = Counter(r.get("opportunity_signal") or "Unknown" for r in rows if r.get("meeting_count"))
    theme_rows = []
    for theme, count in theme_counts.most_common():
        matched = [r for r in rows if theme in (r.get("themes") or [])]
        live = sum(1 for r in matched if r["stage"] in {"live_full", "live_partial"})
        theme_rows.append({
            "theme": theme,
            "practices": count,
            "live_practices": live,
            "live_rate": round(live / len(matched) * 100, 1) if matched else 0,
        })
    return {
        "theme_counts": dict(theme_counts.most_common()),
        "opportunity_signal_counts": dict(signal_counts.most_common()),
        "theme_performance": theme_rows,
    }


def median(values: list[int | float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(statistics.median(clean), 1)


def build_summary(rows: list[dict]) -> dict:
    stage_counts = Counter(r["stage"] for r in rows)
    source_counts = Counter(r["source"] for r in rows)
    confidence_counts = Counter(r["source_confidence"] for r in rows)
    role_counts = Counter(r["primary_role"] for r in rows if r.get("primary_role"))
    arr_total = round(sum(r["contracted_arr"] for r in rows), 2)
    live_rows = [r for r in rows if r["stage"] in {"live_full", "live_partial"}]
    recalling = [r for r in rows if r["is_recalling"]]
    return {
        "arr_target": ARR_TARGET,
        "contracted_arr": arr_total,
        "target_progress_pct": round(arr_total / ARR_TARGET * 100, 1),
        "total_practices": len(rows),
        "live_practices": len(live_rows),
        "recalling_practices": len(recalling),
        "weighted_pipeline_arr": round(sum(r["contracted_arr"] * stage_weight(r["stage"]) for r in rows), 2),
        "by_stage": dict(stage_counts),
        "arr_by_stage": {
            stage: round(sum(r["contracted_arr"] for r in rows if r["stage"] == stage), 2)
            for stage in stage_counts
        },
        "by_source": dict(source_counts),
        "by_source_confidence": dict(confidence_counts),
        "by_primary_role": dict(role_counts),
        "source_performance": source_performance(rows),
        "data_quality": {
            "unknown_source": sum(1 for r in rows if r["source_confidence"] == "unknown"),
            "weak_source": sum(1 for r in rows if r["source_confidence"] == "weak_inferred"),
            "manual_overrides": sum(1 for r in rows if r.get("source_override")),
        },
        "funnel_velocity": {
            "median_days_to_signed": median([r["days_to_signed"] for r in rows]),
            "median_days_signed_to_live": median([r["days_signed_to_live"] for r in rows]),
        },
    }


def stage_weight(stage: str) -> float:
    return {
        "live_full": 1.0,
        "live_partial": 0.85,
        "signed_up": 0.45,
        "onboarding": 0.65,
    }.get(stage, 0.25)


def write_growth_outputs(rows: list[dict]) -> None:
    summary = build_summary(rows)
    meeting = meeting_intelligence(rows)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stats": {
            "total": len(rows),
            "by_stage": summary["by_stage"],
            "by_source": summary["by_source"],
            "by_source_confidence": summary["by_source_confidence"],
            "by_primary_role": summary["by_primary_role"],
        },
        "summary": summary,
        "practices": rows,
    }
    write_json(DASHBOARD_DATA / "growth_dashboard.json", payload)
    write_json(DASHBOARD_DATA / "growth_summary.json", {
        "generated_at": payload["generated_at"],
        "summary": summary,
    })
    write_json(DASHBOARD_DATA / "meeting_intelligence.json", {
        "generated_at": payload["generated_at"],
        **meeting,
    })
    write_override_template()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-hubspot", action="store_true", help="Use existing attribution files")
    parser.add_argument("--skip-notion", action="store_true", help="Use existing Notion snapshot")
    args = parser.parse_args(argv)

    maybe_refresh_notion(args.skip_notion)
    maybe_refresh_hubspot(args.skip_hubspot)
    rows = build_growth_rows()
    write_growth_outputs(rows)


if __name__ == "__main__":
    main()
