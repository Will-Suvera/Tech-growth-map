"""
Build apps/primary-care-tech-overview/public/data/practice_visits.json — practice visit
records pulled from the Notion "Practice Visits" DB.

Notion DB:
  https://www.notion.so/suvera/a80fc303d664476f8a45b66f4d27953b

Views (both must be pulled into the sidecar):
  - Upcoming  (Status = Confirmed)
  - Completed (Status = Completed)

Per docs/planner_growth_dashboard.md, the dashboard uses the visit status as a
binary signal — scheduled / happened / not logged — and surfaces date,
attendees, times, site address, and the Problems field (free-text notes from
past visits, often the key adoption-blocker signal).

Two modes:

  1. NORMALISE MODE (default) — read a curated sidecar file
     `notion_practice_visits.json` at the repo root, shape:
        [{
          "practice": "Bramblys Grange",          // resolved to ODS via fuzzy match
          "ods": "...",                            // optional, wins if present
          "status": "Confirmed" | "Completed",
          "date": "2026-05-26",
          "times": "13:00-14:00",                  // free text
          "site_address": "Dickson House, Crown Heights, Basingstoke RG21 7AP",
          "attendees": ["Amy Wei-Krkoska", "Caitlin Griffiths"],
          "problems": "Wanted multiple appointments..."
        }, ...]
     Resolve practice -> ODS, normalise status into "scheduled" / "happened",
     write {ods: {...}} to practice_visits.json.

  2. MCP MODE — the sidecar is refreshed in a Claude session via Notion MCP
     (notion-fetch on the DB URL). The script itself does NOT call MCP; that
     step lives in a separate Claude conversation, same pattern as
     notion_meetings.json.

Falls back to writing an empty {} if no sidecar exists, so downstream scripts
keep working with "not logged" everywhere.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DATA = REPO_ROOT / "apps" / "tech-growth-map" / "public" / "data"
DASHBOARD_DATA = REPO_ROOT / "apps" / "primary-care-tech-overview" / "public" / "data"
SIDECAR_PATH = REPO_ROOT / "notion_practice_visits.json"
OUT_PATH = DASHBOARD_DATA / "practice_visits.json"

STATUS_MAP = {
    "confirmed": "scheduled",
    "scheduled": "scheduled",
    "completed": "happened",
    "happened": "happened",
    "done": "happened",
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def resolve_ods(name: str, name_to_ods_list: dict[str, list[str]],
                pipeline_ods: set[str] | None = None) -> str | None:
    """Resolve a free-text practice name to an ODS code.

    When the name is ambiguous (e.g. 8 practices called "Mayfield Surgery" in
    England), prefer an ODS that's in our pipeline (waitlist / onboarding /
    live) — anything else is almost certainly the wrong one for our context.

    `name_to_ods_list` maps normalised name -> [list of ODS codes] so we
    preserve all candidates for the tie-break.
    """
    n = _norm(name)
    if not n:
        return None
    pipeline = pipeline_ods or set()

    # Exact match first
    if n in name_to_ods_list:
        candidates = name_to_ods_list[n]
        in_pipe = [o for o in candidates if o in pipeline]
        return in_pipe[0] if in_pipe else candidates[0]

    # Substring fallback — collect candidates from all matching keys
    sub_candidates: list[str] = []
    for k, odses in name_to_ods_list.items():
        if n in k or k in n:
            sub_candidates.extend(odses)
    if sub_candidates:
        in_pipe = [o for o in sub_candidates if o in pipeline]
        return in_pipe[0] if in_pipe else sub_candidates[0]

    return None


def main() -> None:
    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)

    if not SIDECAR_PATH.exists():
        OUT_PATH.write_text(json.dumps({}, indent=2))
        print(f"No sidecar at {SIDECAR_PATH.name} — wrote empty {OUT_PATH.name}. "
              f"Populate the sidecar via Notion MCP (both Upcoming and Completed views) and re-run.")
        return

    sidecar = json.loads(SIDECAR_PATH.read_text())
    practices = json.loads((PUBLIC_DATA / "practices_geocoded.json").read_text())
    name_to_ods_list: dict[str, list[str]] = {}
    for p in practices:
        if not p.get("name"):
            continue
        key = _norm(p["name"])
        # Multiple practices share normalised names (8 Mayfields in England!).
        # Keep all candidates; resolve_ods picks the pipeline-resident one.
        name_to_ods_list.setdefault(key, []).append(p["ods"].upper())

    # Build the pipeline-resident set so resolve_ods can prefer ODS we care about.
    pipeline_ods: set[str] = set()
    for fname in ("waitlist_ods.json", "onboarding_ods.json", "live_customers.json"):
        path = PUBLIC_DATA / fname
        if path.exists():
            pipeline_ods |= set(c.upper() for c in json.loads(path.read_text()))

    today = dt.date.today()
    # If multiple visit rows exist for the same ODS, prefer the most recent
    # Completed visit as the headline; Confirmed (future) is the headline only
    # if no completed visit exists. Keep all rows in `history`.
    by_ods: dict[str, dict] = {}
    unmatched: list[str] = []
    for row in sidecar:
        name = (row.get("practice") or "").strip()
        raw_status = (row.get("status") or "").strip().lower()
        status = STATUS_MAP.get(raw_status, "scheduled" if raw_status else "none")
        date_str = (row.get("date") or "").strip()[:10] or None
        if not raw_status and date_str:
            try:
                d = dt.date.fromisoformat(date_str)
                status = "happened" if d <= today else "scheduled"
            except Exception:
                pass

        ods = (row.get("ods") or "").upper() or resolve_ods(name, name_to_ods_list, pipeline_ods)
        if not ods:
            unmatched.append(name)
            continue

        entry = {
            "status": status,
            "date": date_str,
            "attendees": row.get("attendees") or [],
            "times": row.get("times"),
            "site_address": row.get("site_address"),
            "problems": row.get("problems"),
            "outcome": row.get("outcome"),
            "practice_name": name,
        }
        existing = by_ods.get(ods)
        if existing is None:
            entry["history"] = [{k: v for k, v in entry.items() if k != "history"}]
            by_ods[ods] = entry
        else:
            existing.setdefault("history", []).append({
                k: v for k, v in entry.items() if k != "history"
            })
            # Promote a more-recent or more-conclusive entry to headline:
            #   completed > scheduled, and within same status newer date wins.
            promote = False
            if status == "happened" and existing["status"] != "happened":
                promote = True
            elif status == existing["status"]:
                if date_str and (not existing.get("date") or date_str > existing["date"]):
                    promote = True
            if promote:
                for k in ("status", "date", "attendees", "times", "site_address",
                          "problems", "outcome", "practice_name"):
                    existing[k] = entry[k]

    OUT_PATH.write_text(json.dumps(by_ods, indent=2, sort_keys=True))
    n_happened = sum(1 for v in by_ods.values() if v["status"] == "happened")
    n_scheduled = sum(1 for v in by_ods.values() if v["status"] == "scheduled")
    print(f"Wrote {OUT_PATH.name}: {len(by_ods)} ODS ({n_happened} happened · {n_scheduled} scheduled)")
    if unmatched:
        sample = unmatched[:5]
        print(f"  Unmatched practice names ({len(unmatched)}): {sample}{' ...' if len(unmatched) > 5 else ''}")


if __name__ == "__main__":
    main()
