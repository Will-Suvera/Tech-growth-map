#!/usr/bin/env python3
"""Keep the Notion "Recall Priority List" in step with HubSpot + the recall data.

The recall team ranks practices in Notion; the facts behind that ranking (who is
paying, who is live, who is actually recalling, how big the list is) live in
HubSpot and in the pipeline's JSON. This script pushes those facts into Notion
every night so the list can't quietly go stale — most importantly, **a deal that
gets renamed "PAID - ..." in HubSpot appears here as a paying row within a day**.

Division of labour, and it matters:
  * MACHINE-OWNED (overwritten every run): Testimonial, List size, Expansion
    reach, Where, ODS, Planner practice — and Paying, but UPGRADE-ONLY: a tier
    is written when HubSpot flags the deal PAID and the cell is otherwise left
    alone, so a hand-set tier is never reverted to Freemium overnight.
  * HUMAN-OWNED (only ever set when a row is FIRST created, never touched
    again): Influence, Expansion, Why they matter, and the practice title.
    These are the team's judgement calls — clobbering them would make the tool
    useless to the people who maintain it.

Rows are matched on the ODS column, so renaming a practice in Notion is safe.
Rows already in Notion that this script knows nothing about are left completely
alone (someone added them by hand — that's allowed).

Setup (one-time): share BOTH the "Recall Priority List" and "Planner Practices"
databases with the internal integration behind NOTION_API_TOKEN, otherwise the
API returns 404 for them and this script exits non-zero with an explanation.

Usage:
  python3 pipeline/sync_recall_priority_notion.py [--dry-run]
"""
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTION_VERSION = "2022-06-28"

PRIORITY_DB = "468d8f8c67874719b79c00a0224edb9c"   # Commercial ▸ Recall Priority List
PLANNER_DB = "506413ec202c433db739971a9f3830d6"    # Planner Practices (read-only here)

FUNNEL = ROOT / "apps/primary-care-tech-overview/public/data/funnel_board.json"
PRACTICES = ROOT / "apps/tech-growth-map/public/data/practices_geocoded.json"
RECALLS = ROOT / "apps/tech-growth-map/public/data/recalls.json"

# Stages that mean "this practice is a live customer".
LIVE_STAGES = {"live", "recalling"}

# Paying tiers. HubSpot only tells us PAID vs not; which flavour of paid is a
# commercial decision, so it is seeded once and then left to the team. Anything
# not flagged PAID is Freemium.
DESIGN_PARTNER_ODS = {"Y04925"}   # Chapelford — discounted design-partner deal

# Practices whose HubSpot name and Notion "Planner Practices" name differ by more
# than the fuzzy join can bridge. ODS -> the Planner Practices title(s) to link.
# Brooklands is one HubSpot deal covering two Notion rows, hence the list.
PLANNER_NAME_ALIASES = {
    "H85095": ["Robin Hood Lane Health Centre"],
    "Y06810": ["Brooklands Health Centre", "Whitehouse Health Centre"],
}


def get_token() -> str:
    t = os.environ.get("NOTION_API_TOKEN", "").strip()
    if t:
        return t
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("NOTION_API_TOKEN"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


TOKEN = get_token()


def api(path: str, body: dict | None = None, method: str = "POST") -> dict:
    req = urllib.request.Request(
        "https://api.notion.com/v1" + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code == 404:
            raise SystemExit(
                f"ERROR: Notion returned 404 for {path}.\n"
                "The integration behind NOTION_API_TOKEN almost certainly has not been "
                "given access to the database. Open it in Notion → ••• → Connections → "
                "add the integration, for BOTH 'Recall Priority List' and "
                "'Planner Practices'.\n" + detail
            )
        raise SystemExit(f"ERROR: Notion {e.code} on {path}: {detail}")


def query_all(db_id: str) -> list[dict]:
    out, cursor = [], None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = api(f"/databases/{db_id}/query", body)
        out += resp.get("results", [])
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return out


def plain(prop: dict | None) -> str:
    if not prop:
        return ""
    arr = prop.get("rich_text") or prop.get("title") or []
    return "".join(x.get("plain_text", "") for x in arr).strip()


def norm(name: str) -> str:
    """Loose practice-name key for joining to Planner Practices."""
    s = (name or "").lower()
    for junk in ("(onemedical)", "- freemium", "freemium", "surgery", "surgeries",
                 "medical centre", "health centre", "medical practice", "practice",
                 "the ", "&", "and", ",", ".", "'", "-"):
        s = s.replace(junk, " ")
    return " ".join(s.split())


def build_desired() -> dict[str, dict]:
    """ODS -> the machine-owned facts we want Notion to show."""
    funnel = json.loads(FUNNEL.read_text())
    practices = json.loads(PRACTICES.read_text())
    recalls = json.loads(RECALLS.read_text())
    active = {c.upper() for c in (recalls.get("active_ods_this_month") or [])}

    geo = {p["ods"].upper(): p for p in practices}
    pcn_total: Counter = Counter()
    for p in practices:
        key = (p.get("pcn_name") or "").strip().lower()
        if key:
            pcn_total[key] += p.get("patients") or 0

    desired: dict[str, dict] = {}
    for d in funnel.get("deals", []):
        ods = (d.get("ods") or "").upper()
        if not ods:
            continue
        is_paid = bool(d.get("paid"))
        is_live = d.get("stage") in LIVE_STAGES
        # Only track practices that are already customers or are paying. Everything
        # earlier in the funnel is sales' problem, not the recall team's.
        if not (is_paid or is_live):
            continue

        g = geo.get(ods, {})
        pcn = (g.get("pcn_name") or "").strip().lower()

        if is_paid:
            paying = "Design partner" if ods in DESIGN_PARTNER_ODS else "Full price"
        else:
            paying = "Freemium"

        # Testimonial opportunity, 0-3. A live Freemium practice that is actually
        # recalling is a strong testimonial prospect — that is the whole point of
        # scoring this separately from whether they pay us.
        if is_live and ods in active:
            testimonial = 3
        elif is_live:
            testimonial = 2
        else:
            testimonial = 0

        desired[ods] = {
            "name": (d.get("name") or ods).strip(),
            "paying": paying,
            "testimonial": testimonial,
            "list_size": d.get("patients") or g.get("patients") or 0,
            "reach": pcn_total.get(pcn, 0),
            "where": (g.get("icb") or "").replace("NHS ", "").replace(" ICB", ""),
            "recalling": ods in active,
            "live": is_live,
            "paid": is_paid,
        }
    return desired


def props_payload(want: dict, planner_pages: list[str]) -> dict:
    p: dict = {"Testimonial": {"number": want["testimonial"]}}
    # Paying is only ever written UPWARDS, when HubSpot says PAID. If HubSpot has
    # no PAID flag we leave the cell alone rather than writing "Freemium" — the
    # team sets tiers by hand (e.g. marking a practice a design partner before
    # the deal is renamed), and a nightly job must not undo that.
    if want["paid"]:
        p["Paying"] = {"select": {"name": want["paying"]}}
    # Same principle for the numbers: only write a figure we actually have.
    # Writing 0 over a hand-entered list size would be a silent data loss.
    if want["list_size"]:
        p["List size"] = {"number": want["list_size"]}
    if want["reach"]:
        p["Expansion reach"] = {"number": want["reach"]}
    if want["where"]:
        p["Where"] = {"rich_text": [{"text": {"content": want["where"]}}]}
    if planner_pages:
        p["Planner practice"] = {"relation": [{"id": pid} for pid in planner_pages]}
    return p


def planner_links(ods: str, name: str, by_name: dict[str, str]) -> list[str]:
    aliases = PLANNER_NAME_ALIASES.get(ods)
    if aliases:
        return [by_name[norm(a)] for a in aliases if norm(a) in by_name]
    hit = by_name.get(norm(name))
    return [hit] if hit else []


def seed_reason(want: dict) -> str:
    if want["paid"]:
        return "Paying customer."
    if want["recalling"]:
        return "Active recaller — testimonial-ready."
    if want["live"]:
        return "Live, not recalling yet — needs activating."
    return ""


def main() -> None:
    dry = "--dry-run" in sys.argv
    if not TOKEN:
        raise SystemExit(
            "ERROR: NOTION_API_TOKEN not set. Create an internal integration at "
            "https://www.notion.so/my-integrations, share both databases with it, "
            "and set NOTION_API_TOKEN in .env or as a GitHub Actions secret."
        )

    desired = build_desired()
    print(f"  source: {len(desired)} paying/live practices from funnel_board.json")

    planner_by_name = {}
    for pg in query_all(PLANNER_DB):
        nm = plain(pg["properties"].get("Practice Name"))
        if nm:
            planner_by_name.setdefault(norm(nm), pg["id"])
    print(f"  planner practices: {len(planner_by_name)} linkable rows")

    existing: dict[str, dict] = {}
    untracked = 0
    for pg in query_all(PRIORITY_DB):
        ods = plain(pg["properties"].get("ODS")).upper()
        if not ods:
            # First run: rows created by hand have no ODS yet — match on name once,
            # then the ODS we write makes every later run a stable key lookup.
            title = plain(pg["properties"].get("Practice"))
            hit = next((o for o, w in desired.items() if norm(w["name"]) == norm(title)), None)
            if hit:
                ods = hit
            else:
                untracked += 1
                continue
        existing[ods] = pg

    created = updated = 0
    for ods, want in sorted(desired.items()):
        props = props_payload(want, planner_links(ods, want["name"], planner_by_name))
        props["ODS"] = {"rich_text": [{"text": {"content": ods}}]}
        pg = existing.get(ods)
        if pg:
            if not dry:
                api(f"/pages/{pg['id']}", {"properties": props}, method="PATCH")
            updated += 1
        else:
            # New row: seed the human-owned columns with neutral defaults, then
            # never touch them again.
            props["Practice"] = {"title": [{"text": {"content": want["name"]}}]}
            props.setdefault("Paying", {"select": {"name": want["paying"]}})
            props["Influence"] = {"number": 1}
            props["Expansion"] = {"number": 1}
            props["Why they matter"] = {"rich_text": [{"text": {"content": seed_reason(want)}}]}
            if not dry:
                api("/pages", {"parent": {"database_id": PRIORITY_DB}, "properties": props})
            created += 1
            print(f"    + new row: {want['name']} ({ods}, {want['paying']})")

    linked = sum(1 for o, w in desired.items() if planner_links(o, w["name"], planner_by_name))
    print(f"{'[dry-run] ' if dry else ''}synced Recall Priority List: "
          f"{updated} updated, {created} created, {linked}/{len(desired)} linked to "
          f"Planner Practices, {untracked} hand-added rows left alone")


if __name__ == "__main__":
    main()
