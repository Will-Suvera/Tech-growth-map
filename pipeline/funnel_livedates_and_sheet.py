#!/usr/bin/env python3
"""When did deals turn Live (HubSpot timestamps) + drop-out detail + READ-ONLY
cross-check against the published Google Sheet (SaaS + VC tabs)."""
import json, csv, io, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
data = json.loads((ROOT / "outputs" / "planner_deals.json").read_text())
deals = data["deals"]
LIVE_ID = "4487571659"; DPA_ID = "4489053411"; DROP_ID = "4527836370"
STAGES = [(s["id"], s["label"]) for s in data["stage_order"]]
ID2LABEL = {s["id"]: s["label"] for s in data["stage_order"]} | {DROP_ID: "Dropped Out"}

def parse(s):
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z","+00:00"))
    except Exception: return None

# ---------- A) GO-LIVE DATES (HubSpot Planner pipeline) ----------
lives = []
for d in deals:
    lv = parse(d.get(f"hs_v2_date_entered_{LIVE_ID}"))
    if lv:
        dpa = parse(d.get(f"hs_v2_date_entered_{DPA_ID}"))
        gap = (lv - dpa).days if dpa else None
        lives.append((lv, d.get("dealname","?"), dpa, gap, d.get("dealstage")))
lives.sort()
print(f"=== WENT LIVE (HubSpot 'Live' stage-entry timestamp) — {len(lives)} deals ===")
for lv, name, dpa, gap, cur in lives:
    cur_lab = ID2LABEL.get(cur, cur)
    note = f"  (DPA->Live {gap}d)" if gap is not None else "  (no DPA ts)"
    flag = "  [now: "+cur_lab+"]" if cur != LIVE_ID else ""
    print(f"  {lv.date()}  {name[:48]:<48}{note}{flag}")
print("\nGo-lives by month:")
for m, c in sorted(Counter(lv.strftime('%Y-%m') for lv,_,_,_,_ in lives).items()):
    print(f"  {m}: {c}")

# ---------- B) DROPPED OUT ----------
dropped = [d for d in deals if d.get("dealstage")==DROP_ID or parse(d.get(f"hs_v2_date_entered_{DROP_ID}"))]
print(f"\n=== DROPPED OUT — {len(dropped)} deals ===")
furthest = Counter()
for d in dropped:
    reached = [i for i,(sid,_) in enumerate(STAGES) if parse(d.get(f'hs_v2_date_entered_{sid}'))]
    idx = max(reached) if reached else -1
    furthest[STAGES[idx][1] if idx>=0 else "(none)"] += 1
for sid,lab in STAGES:
    if furthest.get(lab): print(f"  reached {lab:<12} then dropped: {furthest[lab]}")
drop_dates = [parse(d.get(f"hs_v2_date_entered_{DROP_ID}")) for d in dropped]
drop_dates = [x for x in drop_dates if x]
if drop_dates:
    print("\nDrop-outs by month:")
    for m,c in sorted(Counter(x.strftime('%Y-%m') for x in drop_dates).items()):
        print(f"  {m}: {c}")

# ---------- C) GOOGLE SHEET (READ ONLY published CSV) ----------
BASE = ("https://docs.google.com/spreadsheets/d/e/2PACX-1vRa6zIwdwnNSfjjU_gVYdZ7Pm6Sy6"
        "XWsyVe0gR6AZP55IzeVW9qisAUb0Hvo4Nr7qdGhWLnK1l4SDnl/pub?output=csv")
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent":"SuveraReadOnly/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8-sig")

print("\n=== GOOGLE SHEET — SaaS tab (READ ONLY) ===")
try:
    rows = list(csv.reader(io.StringIO(fetch(BASE+"&gid=0"))))
    hdr = rows[0]
    print("Header cols:", [f"{i}:{h}" for i,h in enumerate(hdr) if h.strip()][:14])
    statuses = Counter()
    for row in rows[1:]:
        st = row[8].strip() if len(row)>8 else ""
        if any(c.strip() for c in row):
            statuses[st or "(blank)"] += 1
    print("Status (col I) distribution:", dict(statuses))
except Exception as e:
    print("  ERR:", e)

print("\n=== GOOGLE SHEET — VC tab (READ ONLY) ===")
try:
    rows = list(csv.reader(io.StringIO(fetch(BASE+"&gid=993386637"))))
    hdr = rows[0]
    print("Header cols:", [f"{i}:{h}" for i,h in enumerate(hdr) if h.strip()][:16])
    statuses = Counter()
    for row in rows[1:]:
        st = row[10].strip() if len(row)>10 else ""
        if row and row[0].strip():
            statuses[st or "(blank)"] += 1
    print("Status (col K) distribution:", dict(statuses))
except Exception as e:
    print("  ERR:", e)
