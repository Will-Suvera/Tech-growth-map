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
    ("EMIS Notified",              "emis_notified",        {"yes"}),
    ("IM1 User created",           "im1_user_created",     {"yes"}),
    ("Sharing agreement accepted", "sharing_agreement",    {"yes"}),
    ("Patient Data Sync",          "patient_data_sync",    {"yes"}),
    ("Practice on dashboard",      "practice_on_dashboard",{"yes"}),
    ("HeroHealth",                 "herohealth",           {"set up"}),
    ("Onboarding Call",            "onboarding_call",      {"held"}),
    ("Appt Config",                "appt_config",          {"uploaded"}),
    ("Recall Session",             "recall_session",       {"held"}),
    ("Bloods automation",          "bloods_automation",    {"done"}),
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
            for col, key, done_vals in ONBOARD_STEPS:
                v = (row[idx[col]].strip() if col in idx and idx[col] < len(row) else "")
                state = "done" if v.lower() in done_vals else ("pending" if v else "todo")
                steps.append({"step": col, "key": key, "state": state, "value": v})
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
# bloods has no plain by_ods_month — derive per-month totals from the clinician
# breakdown ({ods: {month: {clinician: n, _total: N}}}) so we can chart bloods/month too.
_bl_clin = _bl.get("by_ods_month_clinician", {}) or {}
bloods_by_ods_month = {
    ods.upper(): {m: (v.get("_total", 0) if isinstance(v, dict) else v) for m, v in (months or {}).items()}
    for ods, months in _bl_clin.items()
}
# Per-week series (Monday-of-week) — present but only surfaced when weekly_available.
recalls_by_ods_week = {k.upper(): v for k, v in (_rec.get("by_ods_week", {}) or {}).items()}
bloods_by_ods_week = {k.upper(): v for k, v in (_bl.get("by_ods_week", {}) or {}).items()}
WEEKLY_AVAILABLE = bool(recalls.get("weekly_available", False))
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

# ---------- practice visits (Notion) — read the normalised file DIRECTLY ----------
# Gives the full per-practice visit history (completed + confirmed + proposed),
# fresh from `ingest_practice_visits.py`, without a heavy attribution rebuild.
# Shape: {ods: {status, date, history:[{date,status,problems,...}], ...}}
try:
    _pv = json.loads((ROOT / "apps/primary-care-tech-overview/public/data/practice_visits.json").read_text())
    pv_by_ods = {k.upper(): v for k, v in _pv.items()}
except Exception:
    pv_by_ods = {}
TODAY = NOW.date().isoformat()

def _visit_list(ods):
    """All dated visits for an ODS, oldest→newest: [{date, status, problems, times, attendees}]."""
    v = pv_by_ods.get(ods) if ods else None
    if not v:
        return []
    hist = v.get("history") or [v]
    out, seen = [], set()
    for h in hist:
        d = (h.get("date") or "")[:10] or None
        sig = (d, h.get("status"))
        if sig in seen:                 # dedup same-date/same-status (name-variant dupes)
            continue
        seen.add(sig)
        out.append({"date": d, "status": h.get("status"), "problems": h.get("problems") or None,
                    "times": h.get("times"), "attendees": h.get("attendees") or []})
    return sorted(out, key=lambda x: x["date"] or "")

# next_step = the next BOOKED touchpoint: a future *Confirmed* Notion visit, else a
# future HubSpot meeting. (Proposed/To-Contact visits are surfaced separately via the
# visits list — they are NOT a firm booking, so they don't clear the "stale" flag.)
def next_step_for(ods, key=None):
    if ods:
        conf = [v for v in _visit_list(ods) if v["date"] and v["date"] >= TODAY and v["status"] == "scheduled"]
        if conf:
            return {"type": "Visit", "date": conf[0]["date"], "source": "Notion"}
        if ods in future_meetings:
            return {"type": "Meeting", "date": future_meetings[ods], "source": "HubSpot"}
    return {"type": "Demo", "date": None} if key == "demo_booked" else None

def visit_info(ods):
    """Headline visit for the detail: most recent past visit, else the soonest upcoming."""
    visits = _visit_list(ods)
    if not visits:
        return None
    past = [v for v in visits if v["date"] and v["date"] <= TODAY]
    chosen = past[-1] if past else visits[0]
    return {"date": chosen["date"], "status": chosen["status"], "problems": chosen["problems"]}

# The onboarding sheet is the operational source of truth for "live" — HubSpot
# deal stages lag behind it (e.g. a practice marked Live + recalling while its
# deal still sits in dpa_signed). Loaded here so per-deal rows can be promoted.
def _live_sheet(fn):
    try:
        return set(x.upper() for x in json.loads((ROOT / "apps/tech-growth-map/public/data" / fn).read_text()))
    except Exception:
        return set()
SHEET_LIVE = _live_sheet("live_customers.json") | _live_sheet("live_customers_full_planner.json")

# Per-deal ODS pins where both automatic routes resolve wrongly:
#  - 443250439387 "Farnham Road Medical Group": its HubSpot company association
#    points at Holmwood Corner's company (H84042); the practice is K81075 (Slough).
#  - 496792727769 "Oakleaf Medical Practice": attribution joined it under
#    neighbouring Amaanah (Y01068); Oakleaf is Y02794 (Birmingham B8 3SW).
DEAL_ODS_OVERRIDES = {
    "443250439387": "K81075",
    "496792727769": "Y02794",
}

# ---------- per-deal rows ----------
rows = []
skipped_blank = 0
promoted_live = []
for d in planner["deals"]:
    cur = d.get("dealstage")
    key = ID2KEY.get(cur)
    if cur == DROP_ID or key is None:
        continue
    label = KEY2LABEL.get(key, key)   # live display label
    entry = parse(d.get(f"hs_v2_date_entered_{cur}"))
    days_in = days_between(entry, NOW)
    name = d.get("dealname", "")
    # Junk guard: a 2026-05-21 channel-partner bulk import created 13 deals
    # literally named " - Planner" (no practice). They carry no company and the
    # name->ODS fallback mis-attributes them all to one ODS. Skip them.
    if not name.replace(" - Planner", "").strip():
        skipped_blank += 1
        continue
    ods = (DEAL_ODS_OVERRIDES.get(str(d.get("_id")))
           or deal_id2ods.get(str(d.get("_id"))) or dealname2ods.get(name.strip().lower()))
    p = ods2p.get(ods, {})
    recalling = ods in recalling_ods if ods else False
    if ods and ods in SHEET_LIVE and key != "live":
        promoted_live.append(f"{name.replace(' - Planner', '').strip()} ({ods}: {key} -> live)")
        key, label = "live", KEY2LABEL.get("live", "live")

    # next step booked? — only FUTURE visits/meetings count (past "scheduled" visits = completed)
    next_step = next_step_for(ods, key)

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
    bl_months = dict(bloods_by_ods_month.get(ods, {}) if ods else {})
    if (bl_months or bloods_tm) and CUR_MONTH not in bl_months:
        bl_months[CUR_MONTH] = bloods_tm
    blm_recent = {m: bl_months[m] for m in sorted(bl_months)[-6:]}
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
        "bloods_by_month": blm_recent,
        "recalls_by_week": {w: c for w, c in sorted((recalls_by_ods_week.get(ods, {}) or {}).items())[-8:]} if ods else {},
        "bloods_by_week": {w: c for w, c in sorted((bloods_by_ods_week.get(ods, {}) or {}).items())[-8:]} if ods else {},
        "why": why(key, days_in, recalling, fy_total, recalls_avg, fy_pct, bl_total, bl_pct),
        "source": p.get("source"), "icb": p.get("icb"), "patients": patients,
        "tier": p.get("tier"), "pcn_name": p.get("pcn_name"),
        "stage_durations": durations, "stage_timeline": stage_timeline,
        "onboarding": onboarding_by_ods.get(ods) if ods else None,
        "last_email": le, "days_since_email": days_since_email, "needs_chase": needs_chase,
    })

# Dedupe deals that share an ODS (e.g. two HubSpot deals for the same practice):
# keep the furthest-along stage; tie-break on longest time in stage, then deal id.
_rank = {k: i for i, k in enumerate(KEYS)}
_by_ods = {}
for r in rows:
    if not r.get("ods"):
        continue
    _by_ods.setdefault(r["ods"], []).append(r)
dropped_dups = []
for ods, group in _by_ods.items():
    if len(group) < 2:
        continue
    group.sort(key=lambda r: (-_rank.get(r["stage"], -1), -(r["days_in_stage"] or 0), str(r["deal_id"])))
    for r in group[1:]:
        dropped_dups.append(f"{r['name']} ({ods}, deal {r['deal_id']})")
        rows.remove(r)
if skipped_blank or dropped_dups or promoted_live:
    print(f"  hygiene: skipped {skipped_blank} blank-name deals · "
          f"dropped {len(dropped_dups)} ODS duplicates {dropped_dups or ''} · "
          f"promoted to live (sheet) {promoted_live or 'none'}")

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

# Operational recallers per week (recalls feed, VC tier excluded — VC practices
# aren't part of the Planner sales motion): a practice counts from the month of
# its first recall. HubSpot's "recalling" stage entry dates are unreliable.
try:
    _tiers_wk = json.loads((ROOT / "apps/tech-growth-map/public/data/practice_tiers.json").read_text())
except Exception:
    _tiers_wk = {}
def _tier_of(o):
    v = _tiers_wk.get(o)
    return (v.get("tier") if isinstance(v, dict) else v) or None
first_recall_month = {}
for _o, _months in recalls_by_ods_month.items():
    _pos = [m for m, c in _months.items() if c]
    if _pos and _tier_of(_o) != "VC":
        first_recall_month[_o] = min(_pos)

weekly = []
for w in range(7, -1, -1):                       # 7 weeks ago .. now
    cutoff = NOW - timedelta(days=7 * w)
    r = reached_as_of(cutoff)
    conv = {KEYS[i]: (round(r[i] / r[i-1] * 100) if i > 0 and r[i-1] else None) for i in range(len(STAGES))}
    reached = {KEYS[i]: r[i] for i in range(len(STAGES))}
    cm = cutoff.strftime("%Y-%m")
    rec_n = sum(1 for m in first_recall_month.values() if m <= cm)
    live_n = reached.get("live")
    reached["recalling"] = rec_n
    conv["recalling"] = round(rec_n / live_n * 100) if live_n else None
    weekly.append({"week": cutoff.date().isoformat(), "reached": reached, "conv": conv})
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

# ---------- recalling cohort (ODS-based, from recalls.json — matches the Omni feed) ----------
# The Implementation tab uses THIS, not the HubSpot-deal funnel, so it shows EVERY
# live/recalling practice (incl. VC + Sheet-Live practices without a matched Planner deal).
geo = json.loads((ROOT / "apps/tech-growth-map/public/data/practices_geocoded.json").read_text())
ods_info = {p["ods"].upper(): p for p in geo}
try:
    _tiers = json.loads((ROOT / "apps/tech-growth-map/public/data/practice_tiers.json").read_text())
except Exception:
    _tiers = {}
def _tier(o):
    v = _tiers.get(o)
    return (v.get("tier") if isinstance(v, dict) else v) or None
def _sheet(fn):
    try: return set(x.upper() for x in json.loads((ROOT / "apps/tech-growth-map/public/data" / fn).read_text()))
    except Exception: return set()
sheet_live = _sheet("live_customers.json") | _sheet("live_customers_full_planner.json")
owner_by_ods = {r["ods"]: r.get("owner") for r in rows if r.get("ods") and r.get("owner")}
pipeline_ods = {r["ods"] for r in rows if r.get("ods")}

# ---------- per-practice journey: HubSpot stage dates + go-live + first recall ----------
# Lets the Implementation detail render a horizontal lifecycle (signup → live → first recall).
LIVE_ID = next((sid for sid, k, _ in STAGES if k == "live"), None)
go_live_by_ods, stage_timeline_by_ods = {}, {}
for d in planner["deals"]:
    o = deal_id2ods.get(str(d.get("_id")))
    if not o:
        continue
    gl = parse(d.get(f"hs_v2_date_entered_{LIVE_ID}")) if LIVE_ID else None
    if gl:
        iso = gl.date().isoformat()
        if o not in go_live_by_ods or iso < go_live_by_ods[o]:
            go_live_by_ods[o] = iso
for r in rows:
    o = r.get("ods")
    if o and r.get("stage_timeline") and (
        o not in stage_timeline_by_ods or len(r["stage_timeline"]) > len(stage_timeline_by_ods[o])):
        stage_timeline_by_ods[o] = r["stage_timeline"]

def first_recall_month(ods):
    months = [m for m, c in (recalls_by_ods_month.get(ods, {}) or {}).items() if c]
    return min(months) if months else None

recalling_practices = []
for ods, fyv in fy_recalls_by_ods.items():
    if not fyv:
        continue
    info = ods_info.get(ods, {})
    pat = info.get("patients")
    fy_total, recalls_avg = metric_stats(recalls_by_ods_month, fy_recalls_by_ods, ods)
    bl_total, bloods_avg = metric_stats(bloods_by_ods_month, fy_bloods_by_ods, ods)
    rbm = {m: c for m, c in sorted((recalls_by_ods_month.get(ods, {}) or {}).items())[-6:]}
    blm = {m: c for m, c in sorted((bloods_by_ods_month.get(ods, {}) or {}).items())[-6:]}
    recalling_practices.append({
        "ods": ods,
        "name": info.get("name") or (ods2p.get(ods, {}) or {}).get("name") or ods,
        "patients": pat, "tier": _tier(ods) or (ods2p.get(ods, {}) or {}).get("tier"),
        "icb": info.get("icb"), "pcn_name": info.get("pcn_name"),
        "fy_recalls": fy_total, "fy_recalls_pct": pct_of_list(fy_total, pat), "recalls_avg_mo": recalls_avg,
        "recalls_this_month": recalls_tm_by_ods.get(ods, 0),
        "fy_bloods": bl_total, "fy_bloods_pct": pct_of_list(bl_total, pat),
        "bloods_this_month": bloods_tm_by_ods.get(ods, 0),
        "recalls_by_month": rbm, "bloods_by_month": blm,
        "recalls_by_week": {w: c for w, c in sorted((recalls_by_ods_week.get(ods, {}) or {}).items())[-8:]},
        "bloods_by_week": {w: c for w, c in sorted((bloods_by_ods_week.get(ods, {}) or {}).items())[-8:]},
        "live": ods in sheet_live,
        "in_pipeline": ods in pipeline_ods,
        "owner": owner_by_ods.get(ods),
        "source": (ods2p.get(ods, {}) or {}).get("source"),
        "stage_timeline": stage_timeline_by_ods.get(ods),
        "go_live": go_live_by_ods.get(ods),
        "first_recall_month": first_recall_month(ods),
        "next_step": next_step_for(ods), "last_visit": visit_info(ods), "visits": _visit_list(ods),
    })
recalling_practices.sort(key=lambda x: (-(x["fy_recalls_pct"] or 0), -(x["fy_recalls"] or 0)))

# ---------- live but NOT recalling (the activation gap) ----------
# Implementation team's first-recall worklist: practices that are functionally
# live (Google Sheet Status=Live, or at the HubSpot "Full Functionality Live"
# stage) but have recalled nothing this FY. Longest-live-without-recall first.
live_days_by_ods = {r["ods"]: r["days_in_stage"] for r in rows
                    if r["stage"] == "live" and r.get("ods")}
live_ods_all = set(sheet_live) | {r["ods"] for r in live_rows if r.get("ods")}
live_not_recalling = []
for ods in sorted(live_ods_all - recalling_ods):
    info = ods_info.get(ods, {})
    pat = info.get("patients")
    bl_total, bloods_avg = metric_stats(bloods_by_ods_month, fy_bloods_by_ods, ods)
    blm = {m: c for m, c in sorted((bloods_by_ods_month.get(ods, {}) or {}).items())[-6:]}
    live_not_recalling.append({
        "ods": ods,
        "name": info.get("name") or (ods2p.get(ods, {}) or {}).get("name") or ods,
        "patients": pat, "tier": _tier(ods) or (ods2p.get(ods, {}) or {}).get("tier"),
        "icb": info.get("icb"), "pcn_name": info.get("pcn_name"),
        "fy_recalls": 0, "fy_recalls_pct": None, "recalls_avg_mo": 0, "recalls_this_month": 0,
        "fy_bloods": bl_total, "fy_bloods_pct": pct_of_list(bl_total, pat),
        "bloods_this_month": bloods_tm_by_ods.get(ods, 0),
        "recalls_by_month": {}, "bloods_by_month": blm,
        "recalls_by_week": {},
        "bloods_by_week": {w: c for w, c in sorted((bloods_by_ods_week.get(ods, {}) or {}).items())[-8:]},
        "live": ods in sheet_live, "in_pipeline": ods in pipeline_ods,
        "live_days": live_days_by_ods.get(ods),
        "owner": owner_by_ods.get(ods),
        "source": (ods2p.get(ods, {}) or {}).get("source"),
        "stage_timeline": stage_timeline_by_ods.get(ods),
        "go_live": go_live_by_ods.get(ods),
        "first_recall_month": None,
        "next_step": next_step_for(ods), "last_visit": visit_info(ods), "visits": _visit_list(ods),
    })
live_not_recalling.sort(key=lambda x: (-(x["live_days"] or 0), -(x["patients"] or 0)))

out = {
    "generated_at": NOW.isoformat(),
    "current_month": CUR_MONTH,
    "next_step_source": "notion_visits + hubspot_meetings" if hs_ok else "notion_visits + demo_booked (meetings unavailable)",
    "stale_thresholds": STALE,
    "stages": stages_out, "weekly": weekly, "deals": rows,
    "recalling_practices": recalling_practices,
    "live_not_recalling": live_not_recalling,
    "weekly_available": WEEKLY_AVAILABLE,
}
dest = ROOT / "apps/primary-care-tech-overview/public/data/funnel_board.json"
dest.write_text(json.dumps(out, indent=2))
unmapped = sum(1 for r in rows if not r["ods"])
print(f"Wrote {len(rows)} active deals · {len(stages_out)} stages · {len(weekly)} weekly snapshots -> {dest.relative_to(ROOT)}")
print(f"  deal->ODS coverage: {len(rows)-unmapped}/{len(rows)} mapped")
print(f"  implementation: {len(recalling_practices)} recalling · {len(live_not_recalling)} live-not-recalling")
for s in stages_out:
    print(f"  {s['label']:<12} in={s['in_stage']:>3}  conv={s['conv_from_prev']}  Δ1w={s['conv_delta_1w']}  stale={s['stale']}")
