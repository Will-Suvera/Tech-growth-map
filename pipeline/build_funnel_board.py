#!/usr/bin/env python3
"""Build funnel_board.json — data layer for the single vertical Funnel Movement board.

Joins:
  outputs/planner_deals.json   (fresh HubSpot deals: stage + hs_v2_date_entered_* + ehr + owner)
  attribution.json             (ODS, company_id, Notion practice_visit, source, icb, tier, pcn)
  public/data/recalls.json     (FY activation + per-practice monthly recalls)
  + live deal->company->ODS and future HubSpot meetings (graceful if scope missing)

Also reconstructs a WEEK-BY-WEEK funnel from the stage-entry timestamps (no stored history needed).
Output: apps/primary-care-tech-overview/public/data/funnel_board.json
"""
import json, os, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api-eu1.hubapi.com"
NOW = datetime.now(timezone.utc)

def get_token():
    t = os.environ.get("HUBSPOT_API_TOKEN", "").strip()
    if t: return t
    for line in (ROOT / ".env").read_text().splitlines():
        if line.strip().startswith("HUBSPOT_API_TOKEN"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""
TOKEN = get_token()

def hs(method, endpoint, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + endpoint, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def parse(s):
    if not s: return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None

def days_between(a, b):
    return (b - a).total_seconds() / 86400.0 if a and b else None

# ---------- load sources ----------
planner = json.loads((ROOT / "outputs/planner_deals.json").read_text())
attr = json.loads((ROOT / "apps/primary-care-tech-overview/public/data/attribution.json").read_text())
recalls = json.loads((ROOT / "apps/tech-growth-map/public/data/recalls.json").read_text())

# ---------- onboarding checklist from the Google Sheet (read-only published CSV) ----------
# "DPA Signed Onboard Ready" is not one step — it's this implementation checklist.
# (column name in SaaS tab, set of values that count as DONE). Anything else non-empty = in-progress.
ONBOARD_STEPS = [
    ("EMIS Notified",              {"yes"}),
    ("IM1 User created",           {"yes"}),
    ("Sharing agreement accepted", {"yes"}),
    ("Patient Data Sync",          {"yes"}),
    ("Practice on dashboard",      {"yes"}),
    ("HeroHealth",                 {"set up"}),
    ("Onboarding Call",            {"held"}),
    ("Appt Config",                {"uploaded"}),
    ("Recall Session",             {"held"}),
    ("Bloods automation",          {"done"}),
]
GSHEET_SAAS = ("https://docs.google.com/spreadsheets/d/e/2PACX-1vRa6zIwdwnNSfjjU_gVYdZ7Pm6Sy6"
               "XWsyVe0gR6AZP55IzeVW9qisAUb0Hvo4Nr7qdGhWLnK1l4SDnl/pub?output=csv&gid=0")

def load_onboarding_steps():
    """ods -> [{step, state}] where state ∈ done|pending|todo, from the onboarding tracker sheet."""
    import csv, io
    out = {}
    try:
        req = urllib.request.Request(GSHEET_SAAS, headers={"User-Agent": "SuveraReadOnly/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            rows = list(csv.reader(io.StringIO(r.read().decode("utf-8-sig"))))
        hdr = rows[0]
        idx = {h.strip(): i for i, h in enumerate(hdr)}
        ods_i = idx.get("ODS Code", 6)
        for row in rows[1:]:
            ods = (row[ods_i].strip().upper() if len(row) > ods_i else "")
            if not ods:
                continue
            steps = []
            for col, done_vals in ONBOARD_STEPS:
                v = (row[idx[col]].strip() if col in idx and idx[col] < len(row) else "")
                state = "done" if v.lower() in done_vals else ("pending" if v else "todo")
                steps.append({"step": col, "state": state, "value": v})
            out[ods] = steps
        print(f"  onboarding checklist: {len(out)} practices from sheet")
    except Exception as e:
        print(f"  WARN: could not load onboarding sheet ({e})")
    return out

onboarding_by_ods = load_onboarding_steps()

# Stage IDs + keys are STABLE; labels are live from HubSpot (carried for display only).
# All logic keys off `key`, never the label — so a HubSpot rename flows through cleanly.
STAGES = [(s["id"], s.get("key") or s["label"], s["label"]) for s in planner["stage_order"]]
DROP_ID = planner["dropped_stage"]["id"]
ID2KEY = {sid: key for sid, key, _ in STAGES}
KEY2LABEL = {key: lab for _, key, lab in STAGES}
KEYS = [key for _, key, _ in STAGES]
STAGE_IDS = [sid for sid, _, _ in STAGES]

# "Activated" = recalled at all this FY (not just this month — else FY recallers look like ghosts early-FY)
_rec = recalls.get("recalls", {}) if isinstance(recalls.get("recalls"), dict) else {}
_fy = _rec.get("fy_by_practice", {}) or {}
recalling_ods = set(k.upper() for k, v in _fy.items()
                    if (v.get("fy_to_date", 0) if isinstance(v, dict) else v) > 0)
recalling_ods |= set(x.upper() for x in recalls.get("active_ods_recent", []))
recalls_by_ods_month = _rec.get("by_ods_month", {}) or {}
_bl = recalls.get("bloods", {}) if isinstance(recalls.get("bloods"), dict) else {}
bloods_by_ods_month = _bl.get("by_ods_month", {}) or {}
fy_recalls_by_ods = {k.upper(): (v.get("fy_to_date", 0) if isinstance(v, dict) else v) for k, v in _fy.items()}
fy_bloods_by_ods = {k.upper(): (v.get("fy_to_date", 0) if isinstance(v, dict) else v)
                    for k, v in (_bl.get("fy_by_practice", {}) or {}).items()}
recalls_tm_by_ods = {k.upper(): (v.get("this_month", 0) if isinstance(v, dict) else 0) for k, v in _fy.items()}
bloods_tm_by_ods = {k.upper(): (v.get("this_month", 0) if isinstance(v, dict) else 0)
                    for k, v in (_bl.get("fy_by_practice", {}) or {}).items()}
CUR_MONTH = NOW.strftime("%Y-%m")
_fy_start_year = NOW.year if NOW.month >= 4 else NOW.year - 1   # UK FY starts 1 April
_FY_START = f"{_fy_start_year}-04"

def metric_stats(by_month, fy_map, ods):
    """FY-to-date total + average per active month since April for a metric."""
    if not ods:
        return 0, 0
    bom = {m: c for m, c in (by_month.get(ods, {}) or {}).items() if m >= _FY_START}
    total = sum(bom.values()) or fy_map.get(ods, 0)
    n = len([1 for c in bom.values() if c > 0])
    return total, (round(total / n) if n else 0)

def pct_of_list(x, patients):
    return round(x / patients * 100, 1) if patients and x else None

# maps from attribution.json
dealname2ods, companyid2ods, ods2p = {}, {}, {}
for p in attr.get("practices", []):
    ods = (p.get("ods") or "").upper()
    if not ods: continue
    ods2p[ods] = p
    if p.get("company_id"): companyid2ods[str(p["company_id"])] = ods
    for d in p.get("deals", []):
        if d.get("dealname"):
            dealname2ods[d["dealname"].strip().lower()] = ods

# ---------- authoritative deal -> company -> ODS join ----------
deal_id2ods = {}
try:
    deal_ids = [str(d["_id"]) for d in planner["deals"] if d.get("_id")]
    deal2company = {}
    for i in range(0, len(deal_ids), 100):
        assoc = hs("POST", "/crm/v4/associations/deals/companies/batch/read",
                   {"inputs": [{"id": x} for x in deal_ids[i:i+100]]})
        for r in assoc.get("results", []):
            tos = r.get("to", [])
            if tos: deal2company[str(r["from"]["id"])] = str(tos[0]["toObjectId"])
    comp_ids = list(set(deal2company.values()))
    comp2ods = {}
    for i in range(0, len(comp_ids), 100):
        cr = hs("POST", "/crm/v3/objects/companies/batch/read",
                {"properties": ["ods_unique", "practice_code"],
                 "inputs": [{"id": x} for x in comp_ids[i:i+100]]})
        for r in cr.get("results", []):
            pr = r.get("properties", {})
            ods = (pr.get("ods_unique") or pr.get("practice_code") or "").strip().upper()
            if ods: comp2ods[str(r["id"])] = ods
    for did, cid in deal2company.items():
        if cid in comp2ods: deal_id2ods[did] = comp2ods[cid]
    print(f"  deal->company->ODS resolved for {len(deal_id2ods)}/{len(deal_ids)} deals")
except Exception as e:
    print(f"  WARN: deal->company->ODS join failed ({e}); using dealname match only")

# ---------- future HubSpot meetings (next-step signal) ----------
future_meetings, owners, hs_ok = {}, {}, True
try:
    now_ms = str(int(NOW.timestamp() * 1000))
    after, mids = None, {}
    while True:
        body = {"filterGroups": [{"filters": [
                    {"propertyName": "hs_meeting_start_time", "operator": "GTE", "value": now_ms}]}],
                "properties": ["hs_meeting_start_time"], "limit": 100}
        if after: body["after"] = after
        resp = hs("POST", "/crm/v3/objects/meetings/search", body)
        for m in resp.get("results", []):
            mids[m["id"]] = m["properties"].get("hs_meeting_start_time")
        after = resp.get("paging", {}).get("next", {}).get("after")
        if not after: break
    ids = list(mids.keys())
    for i in range(0, len(ids), 100):
        assoc = hs("POST", "/crm/v4/associations/meetings/companies/batch/read",
                   {"inputs": [{"id": x} for x in ids[i:i+100]]})
        for r in assoc.get("results", []):
            mid = str(r.get("from", {}).get("id"))
            for to in r.get("to", []):
                ods = companyid2ods.get(str(to.get("toObjectId")))
                pdt = parse(mids.get(mid))
                if ods and pdt:
                    iso = pdt.isoformat()
                    if ods not in future_meetings or iso < future_meetings[ods]:
                        future_meetings[ods] = iso
    print(f"  future meetings mapped to {len(future_meetings)} practices")
except Exception as e:
    hs_ok = False
    print(f"  WARN: could not pull future meetings ({e})")
try:
    for o in hs("GET", "/crm/v3/owners?limit=200").get("results", []):
        owners[str(o["id"])] = f"{o.get('firstName','')} {o.get('lastName','')}".strip()
except Exception as e:
    print(f"  WARN: could not pull owners ({e})")

# ---------- last email per deal (needs `sales-email-read` scope on the Private App) ----------
# Graceful: if the token lacks the scope (403), we fall back to the sidecar
# outputs/deal_last_email.json (populated via the connected HubSpot app) so the
# feature still shows. Add `sales-email-read` to the Private App for daily auto-pull.
last_email = {}   # deal_id(str) -> {subject, date, direction}
DIR_LABEL = {"EMAIL": "sent", "INCOMING_EMAIL": "received", "FORWARDED_EMAIL": "fwd"}
def pull_last_emails():
    deal_ids = [str(d["_id"]) for d in planner["deals"] if d.get("_id")]
    d2e = {}
    for i in range(0, len(deal_ids), 100):
        a = hs("POST", "/crm/v4/associations/deals/emails/batch/read",
               {"inputs": [{"id": x} for x in deal_ids[i:i+100]]})
        for r in a.get("results", []):
            d2e[str(r["from"]["id"])] = [str(t["toObjectId"]) for t in r.get("to", [])]
    all_emails = sorted({e for v in d2e.values() for e in v})
    eprops = {}
    for i in range(0, len(all_emails), 100):
        er = hs("POST", "/crm/v3/objects/emails/batch/read",
                {"properties": ["hs_timestamp", "hs_email_subject", "hs_email_direction"],
                 "inputs": [{"id": x} for x in all_emails[i:i+100]]})
        for e in er.get("results", []):
            eprops[str(e["id"])] = e.get("properties", {})
    for did, eids in d2e.items():
        best = None
        for eid in eids:
            p = eprops.get(eid)
            if not p or not p.get("hs_timestamp"):
                continue
            if best is None or p["hs_timestamp"] > best["hs_timestamp"]:
                best = p
        if best:
            last_email[did] = {"subject": best.get("hs_email_subject") or "(no subject)",
                               "date": best["hs_timestamp"],
                               "direction": DIR_LABEL.get(best.get("hs_email_direction"), "email")}
try:
    pull_last_emails()
    print(f"  last email pulled for {len(last_email)} deals (via token)")
except Exception as e:
    print(f"  WARN: last-email via token failed ({getattr(e,'code',e)}) — add `sales-email-read` scope; trying sidecar")
sidecar = ROOT / "outputs/deal_last_email.json"
if sidecar.exists():
    try:
        sc = json.loads(sidecar.read_text())
        for did, v in sc.items():
            if did.startswith("_"):
                continue
            last_email.setdefault(str(did), v)   # token wins; sidecar fills gaps
        print(f"  last email sidecar merged ({len(sc)} deals) -> total {len(last_email)}")
    except Exception as e:
        print(f"  WARN: bad sidecar ({e})")

# ---------- stale thresholds ----------
# keyed by stable stage key (not label)
STALE = {"waitlist": 30, "demo_booked": 10, "demo_held": 14, "dpa_sent": 10, "dpa_signed": 21, "live": 21}

def why(key, days_in, recalling, fy_total=0, avg=0, pct=None, bl_total=0, bl_pct=None):
    d = f"{days_in:.0f}d" if days_in is not None else "?"
    if key == "live":
        if fy_total > 0 or bl_total > 0:
            r = f"{fy_total:,} recalls" + (f" ({pct}%)" if pct is not None else "")
            b = f"{bl_total:,} bloods" + (f" ({bl_pct}%)" if bl_pct is not None else "")
            return f"{r} · {b}"
        return f"0 recalls this FY · live {d}"
    return {
        "waitlist":    f"On signed-up list {d}, no demo booked",
        "demo_booked": "Demo booked, awaiting the call",
        "demo_held":   f"Demo held {d} ago, no DPA sent",
        "dpa_sent":    f"DPA sent {d} ago, not signed",
        "dpa_signed":  f"DPA signed {d} ago, no go-live booked",
    }.get(key, f"In {KEY2LABEL.get(key, key)} {d}")

# ---------- per-deal rows ----------
rows = []
for d in planner["deals"]:
    cur = d.get("dealstage")
    key = ID2KEY.get(cur)
    if cur == DROP_ID or key is None:
        continue
    label = KEY2LABEL.get(key, key)   # live display label
    entry = parse(d.get(f"hs_v2_date_entered_{cur}"))
    days_in = days_between(entry, NOW)
    name = d.get("dealname", "")
    ods = deal_id2ods.get(str(d.get("_id"))) or dealname2ods.get(name.strip().lower())
    p = ods2p.get(ods, {})
    recalling = ods in recalling_ods if ods else False

    # next step booked? — only FUTURE visits/meetings count (past "scheduled" visits = completed)
    vdate = parse(p.get("practice_visit_date"))
    next_step = None
    if p.get("practice_visit_status") == "scheduled" and (vdate is None or vdate >= NOW - timedelta(days=1)):
        next_step = {"type": "Visit", "date": p.get("practice_visit_date")}
    elif ods and ods in future_meetings:
        next_step = {"type": "Meeting", "date": future_meetings[ods]}
    elif key == "demo_booked":
        next_step = {"type": "Demo", "date": None}

    thr = STALE.get(key, 30)
    stale = (days_in is not None and days_in > thr) and next_step is None and not (key == "live" and recalling)

    # last-email recency + "needs a chase" flag (won/near-won deals stalling)
    le = last_email.get(str(d.get("_id")))
    days_since_email = round(days_between(parse(le["date"]), NOW)) if le and le.get("date") else None
    CHASE_STAGES = {"demo_held", "dpa_sent", "dpa_signed"}
    needs_chase = key in CHASE_STAGES and stale

    # time taken in each completed stage transition (for tooltip)
    durations = []
    for j in range(len(STAGES) - 1):
        a_ = parse(d.get(f"hs_v2_date_entered_{STAGES[j][0]}"))
        b_ = parse(d.get(f"hs_v2_date_entered_{STAGES[j+1][0]}"))
        if a_ and b_ and b_ >= a_:
            durations.append({"step": f"{STAGES[j][2]}→{STAGES[j+1][2]}",
                              "days": round((b_ - a_).total_seconds() / 86400)})

    # full stage timeline: when each stage was entered + gap from the previous reached stage
    stage_timeline, _prev_dt = [], None
    for sid, _skey, slabel in STAGES:
        sdt = parse(d.get(f"hs_v2_date_entered_{sid}"))
        if not sdt:
            continue
        gap = round((sdt - _prev_dt).total_seconds() / 86400) if _prev_dt and sdt >= _prev_dt else None
        stage_timeline.append({"stage": slabel, "date": sdt.date().isoformat(),
                               "gap_days": gap, "current": sid == cur})
        _prev_dt = sdt
    patients = p.get("patients")
    rec_months = dict(recalls_by_ods_month.get(ods, {}) if ods else {})
    recalls_tm = recalls_tm_by_ods.get(ods, rec_months.get(CUR_MONTH, 0)) if ods else 0
    if (rec_months or recalls_tm) and CUR_MONTH not in rec_months:  # always show current month for active practices
        rec_months[CUR_MONTH] = recalls_tm                          # (even 0 → "gone quiet this month")
    rbm_recent = {m: rec_months[m] for m in sorted(rec_months)[-6:]}
    bloods_tm = bloods_tm_by_ods.get(ods, 0) if ods else 0
    fy_total, recalls_avg = metric_stats(recalls_by_ods_month, fy_recalls_by_ods, ods)
    bl_total, bloods_avg = metric_stats(bloods_by_ods_month, fy_bloods_by_ods, ods)
    fy_pct = pct_of_list(fy_total, patients)
    bl_pct = pct_of_list(bl_total, patients)
    pctm = lambda rec: ({m: round(c / patients * 100, 1) for m, c in rec.items()} if patients else {})

    rows.append({
        "deal_id": d.get("_id"), "name": name.replace(" - Planner", ""), "ods": ods,
        "stage": key, "stage_label": label, "ehr": d.get("ehr_type") or "Unknown",
        "days_in_stage": round(days_in) if days_in is not None else None,
        "owner": owners.get(str(d.get("hubspot_owner_id"))) or None,
        "next_step": next_step, "recalling": recalling, "stale": stale,
        "fy_recalls": fy_total, "recalls_avg_mo": recalls_avg, "fy_recalls_pct": fy_pct,
        "fy_bloods": bl_total, "bloods_avg_mo": bloods_avg, "fy_bloods_pct": bl_pct,
        "recalls_this_month": recalls_tm, "bloods_this_month": bloods_tm,
        "recalls_this_month_pct": pct_of_list(recalls_tm, patients),
        "recalls_by_month": rbm_recent, "recalls_pct_by_month": pctm(rbm_recent),
        "why": why(key, days_in, recalling, fy_total, recalls_avg, fy_pct, bl_total, bl_pct),
        "source": p.get("source"), "icb": p.get("icb"), "patients": patients,
        "tier": p.get("tier"), "pcn_name": p.get("pcn_name"),
        "stage_durations": durations, "stage_timeline": stage_timeline,
        "onboarding": onboarding_by_ods.get(ods) if ods else None,
        "last_email": le, "days_since_email": days_since_email, "needs_chase": needs_chase,
    })

# ---------- week-by-week funnel reconstructed from stage-entry timestamps ----------
def reached_as_of(cutoff):
    out = []
    for i in range(len(STAGES)):
        c = 0
        for d in planner["deals"]:
            for sid in STAGE_IDS[i:]:
                e = parse(d.get(f"hs_v2_date_entered_{sid}"))
                if e and e <= cutoff:
                    c += 1
                    break
        out.append(c)
    return out

weekly = []
for w in range(7, -1, -1):                       # 7 weeks ago .. now
    cutoff = NOW - timedelta(days=7 * w)
    r = reached_as_of(cutoff)
    conv = {KEYS[i]: (round(r[i] / r[i-1] * 100) if i > 0 and r[i-1] else None) for i in range(len(STAGES))}
    weekly.append({"week": cutoff.date().isoformat(),
                   "reached": {KEYS[i]: r[i] for i in range(len(STAGES))}, "conv": conv})
conv_now = weekly[-1]["conv"]
conv_prev = weekly[-2]["conv"] if len(weekly) > 1 else {}
ever = [weekly[-1]["reached"][k] for k in KEYS]

# ---------- per-stage aggregates ----------
def agg(key):
    sub = [r for r in rows if r["stage"] == key]
    return {"count": len(sub), "stale": sum(1 for r in sub if r["stale"]),
            "no_next": sum(1 for r in sub if r["next_step"] is None and not (key == "live" and r["recalling"]))}

stages_out = []
for i, key in enumerate(KEYS):
    a = agg(key)
    cn, cp = conv_now.get(key), conv_prev.get(key)
    stages_out.append({
        "key": key, "label": KEY2LABEL.get(key, key), "in_stage": a["count"], "ever_reached": ever[i],
        "conv_from_prev": cn, "conv_delta_1w": (cn - cp) if cn is not None and cp is not None else None,
        "stale": a["stale"], "no_next_step": a["no_next"],
    })
live_rows = [r for r in rows if r["stage"] == "live"]
recalling_ct = sum(1 for r in live_rows if r["recalling"])
stages_out.append({
    "key": "recalling", "label": "Recalling", "in_stage": recalling_ct, "ever_reached": recalling_ct,
    "conv_from_prev": round(recalling_ct / len(live_rows) * 100) if live_rows else None,
    "conv_delta_1w": None, "stale": 0, "no_next_step": 0, "is_activation": True})

out = {
    "generated_at": NOW.isoformat(),
    "current_month": CUR_MONTH,
    "next_step_source": "notion_visits + hubspot_meetings" if hs_ok else "notion_visits + demo_booked (meetings unavailable)",
    "stale_thresholds": STALE,
    "stages": stages_out, "weekly": weekly, "deals": rows,
}
dest = ROOT / "apps/primary-care-tech-overview/public/data/funnel_board.json"
dest.write_text(json.dumps(out, indent=2))
unmapped = sum(1 for r in rows if not r["ods"])
print(f"Wrote {len(rows)} active deals · {len(stages_out)} stages · {len(weekly)} weekly snapshots -> {dest.relative_to(ROOT)}")
print(f"  deal->ODS coverage: {len(rows)-unmapped}/{len(rows)} mapped")
for s in stages_out:
    print(f"  {s['label']:<12} in={s['in_stage']:>3}  conv={s['conv_from_prev']}  Δ1w={s['conv_delta_1w']}  stale={s['stale']}")
