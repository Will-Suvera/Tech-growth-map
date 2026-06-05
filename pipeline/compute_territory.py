"""
Compute per-practice PCN/ICB neighbour signals + write hot_zones.json
(PCN beachheads + ICB density leaders) for the Planner Growth Dashboard.

Reads:
  public/data/practices_geocoded.json      — universe of England GPs
  public/data/waitlist_ods.json
  public/data/onboarding_ods.json
  public/data/live_customers.json
  public/data/recalls.json                  — active recalling set
  apps/primary-care-tech-overview/public/data/attribution.json  — pipeline rows (annotates in place)

Writes (in apps/primary-care-tech-overview/public/data/):
  attribution.json   (in-place: adds pcn_/icb_ neighbour counts to each row)
  hot_zones.json     (ranked PCN beachheads + ICB density leaders)

Run AFTER refresh_attribution.py + score_practices.py:
  python3 scripts/compute_territory.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DATA = REPO_ROOT / "apps" / "tech-growth-map" / "public" / "data"
DASHBOARD_DATA = REPO_ROOT / "apps" / "primary-care-tech-overview" / "public" / "data"
ATTRIBUTION_PATH = DASHBOARD_DATA / "attribution.json"
HOT_ZONES_PATH = DASHBOARD_DATA / "hot_zones.json"

PCN_BEACHHEAD_TOP_N = 15
ICB_DENSITY_TOP_N = 12


def load_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def main() -> None:
    practices = load_json(PUBLIC_DATA / "practices_geocoded.json", [])
    waitlist = set(load_json(PUBLIC_DATA / "waitlist_ods.json", []))
    onboarding = set(load_json(PUBLIC_DATA / "onboarding_ods.json", []))
    live = set(load_json(PUBLIC_DATA / "live_customers.json", []))
    recalls_data = load_json(PUBLIC_DATA / "recalls.json", {})

    pipeline = (waitlist | onboarding | live)
    recalling_this_month = set(recalls_data.get("active_ods_this_month") or [])

    # Index practices by PCN and ICB
    by_pcn: dict[str, list[dict]] = defaultdict(list)
    by_icb: dict[str, list[dict]] = defaultdict(list)
    by_ods: dict[str, dict] = {}
    for p in practices:
        ods = (p.get("ods") or "").upper()
        if not ods:
            continue
        by_ods[ods] = p
        pcn = (p.get("pcn_name") or "").strip()
        if pcn:
            by_pcn[pcn].append(p)
        icb = (p.get("icb") or "").strip()
        if icb:
            by_icb[icb].append(p)

    def status_for(ods: str) -> str:
        if ods in recalling_this_month and ods in live:
            return "recalling"
        if ods in live:
            return "live"
        if ods in onboarding:
            return "onboarding"
        if ods in waitlist:
            return "signed_up"
        return "untapped"

    # Aggregate per PCN
    pcn_stats: dict[str, dict] = {}
    for pcn, members in by_pcn.items():
        signed = 0
        live_n = 0
        recalling_n = 0
        untapped_ods: list[str] = []
        untapped_patients = 0
        members_summary: list[dict] = []
        for m in members:
            ods = m["ods"].upper()
            st = status_for(ods)
            if st == "untapped":
                untapped_ods.append(ods)
                untapped_patients += int(m.get("patients") or 0)
            else:
                if ods in (waitlist | onboarding | live):
                    signed += 1
                if ods in live:
                    live_n += 1
                if ods in recalling_this_month and ods in live:
                    recalling_n += 1
            members_summary.append({
                "ods": ods,
                "name": m.get("name"),
                "patients": m.get("patients"),
                "status": st,
            })
        pcn_stats[pcn] = {
            "total": len(members),
            "signed": signed,
            "live": live_n,
            "recalling": recalling_n,
            "untapped_count": len(untapped_ods),
            "untapped_ods": untapped_ods,
            "untapped_patients": untapped_patients,
            "members": members_summary,
        }

    # Aggregate per ICB (counts only — full member lists are too large)
    icb_stats: dict[str, dict] = {}
    for icb, members in by_icb.items():
        signed = 0
        live_n = 0
        recalling_n = 0
        recalls_total = 0
        patients_total = 0
        bloods_total = 0
        for m in members:
            ods = m["ods"].upper()
            patients_total += int(m.get("patients") or 0)
            if ods in (waitlist | onboarding | live):
                signed += 1
            if ods in live:
                live_n += 1
            if ods in recalling_this_month and ods in live:
                recalling_n += 1
        # Recalls/forms volume in this ICB (current month, from recalls.json)
        for r in (recalls_data.get("recalls") or {}).get("practices_this_month", []) or []:
            ods = (r.get("ods") or "").upper()
            if ods and by_ods.get(ods, {}).get("icb") == icb:
                recalls_total += int(r.get("count") or 0)
        for r in (recalls_data.get("bloods") or {}).get("practices_this_month", []) or []:
            ods = (r.get("ods") or "").upper()
            if ods and by_ods.get(ods, {}).get("icb") == icb:
                bloods_total += int(r.get("count") or 0)
        icb_stats[icb] = {
            "total_practices": len(members),
            "signed": signed,
            "live": live_n,
            "recalling": recalling_n,
            "patients_total": patients_total,
            "recalls_this_month": recalls_total,
            "bloods_this_month": bloods_total,
            "recalls_per_patient_month":
                round(recalls_total / patients_total, 5) if patients_total else 0,
        }

    # Annotate attribution.json rows with neighbour counts
    payload = load_json(ATTRIBUTION_PATH, None)
    if payload:
        for row in payload.get("practices") or []:
            pcn = (row.get("pcn_name") or "").strip()
            icb = (row.get("icb") or "").strip()
            pstats = pcn_stats.get(pcn)
            if pstats:
                row["pcn_total_practices"] = pstats["total"]
                row["pcn_signed_count"] = pstats["signed"]
                row["pcn_live_count"] = pstats["live"]
                row["pcn_recalling_count"] = pstats["recalling"]
                row["pcn_untapped_count"] = pstats["untapped_count"]
                row["pcn_untapped_ods"] = pstats["untapped_ods"]
            istats = icb_stats.get(icb)
            if istats:
                row["icb_signed_count"] = istats["signed"]
                row["icb_live_count"] = istats["live"]
                row["icb_recalling_count"] = istats["recalling"]
                row["icb_recalls_per_patient_month"] = istats["recalls_per_patient_month"]
        ATTRIBUTION_PATH.write_text(json.dumps(payload, indent=2, default=str))

    # PCN beachheads = ≥1 Live + ≥1 untapped, sorted by upside £-potential
    # (we use untapped_patients as a £-proxy; the £/patient slider is applied
    # client-side so the same ranking holds at any rate)
    beachheads: list[dict] = []
    for pcn, s in pcn_stats.items():
        if s["live"] >= 1 and s["untapped_count"] >= 1:
            beachheads.append({
                "pcn": pcn,
                "live": s["live"],
                "recalling": s["recalling"],
                "signed": s["signed"],
                "untapped_count": s["untapped_count"],
                "untapped_patients": s["untapped_patients"],
                "members": s["members"],
            })
    beachheads.sort(key=lambda x: -x["untapped_patients"])

    # ICB density leaders by recalls_per_patient (current month is the best
    # signal we have until per-practice monthly history is backfilled)
    icb_leaders = sorted(
        ({"icb": icb, **s} for icb, s in icb_stats.items() if s["live"] >= 1),
        key=lambda x: -x["recalls_per_patient_month"],
    )

    hot_zones = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "pcn_beachheads": beachheads[:PCN_BEACHHEAD_TOP_N],
        "icb_density_leaders": icb_leaders[:ICB_DENSITY_TOP_N],
        "totals": {
            "pcns_with_any_live": sum(1 for s in pcn_stats.values() if s["live"] >= 1),
            "pcns_with_untapped_neighbours": sum(
                1 for s in pcn_stats.values() if s["live"] >= 1 and s["untapped_count"] >= 1),
            "untapped_patients_in_beachhead_pcns": sum(b["untapped_patients"] for b in beachheads),
        },
    }
    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)
    HOT_ZONES_PATH.write_text(json.dumps(hot_zones, indent=2, default=str))
    print(f"Wrote {HOT_ZONES_PATH.name}: {len(beachheads)} PCN beachheads "
          f"({hot_zones['totals']['untapped_patients_in_beachhead_pcns']:,} untapped patients), "
          f"{len(icb_leaders)} ICB density leaders")


if __name__ == "__main__":
    main()
