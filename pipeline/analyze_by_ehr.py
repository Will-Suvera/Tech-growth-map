#!/usr/bin/env python3
"""Re-segment the Planner funnel by EHR. Planner currently onboards EMIS;
SystmOne (TPP/S1) practices are parked ('not yet onboarding'), so they should
not count as funnel stalls. Produces the addressable (EMIS) funnel."""
import json, statistics
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
data = json.loads((ROOT / "outputs" / "planner_deals.json").read_text())
deals = data["deals"]
STAGES = [(s["id"], s["label"]) for s in data["stage_order"]]
LABELS = [l for _, l in STAGES]
DROP_ID = data["dropped_stage"]["id"]
NOW = datetime.now(timezone.utc)

def parse(s):
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z","+00:00"))
    except Exception: return None

def ehr_of(d):
    e = (d.get("ehr_type") or "").strip()
    return e if e else "Unknown"

for d in deals:
    reached = [i for i,(sid,_) in enumerate(STAGES) if parse(d.get(f"hs_v2_date_entered_{sid}"))]
    cur = d.get("dealstage")
    if cur in dict(STAGES):
        reached.append([s for s,_ in STAGES].index(cur))
    d["_idx"] = max(reached) if reached else 0   # everyone entered Waitlist
    d["_ehr"] = ehr_of(d)
    d["_dropped"] = (cur == DROP_ID) or bool(parse(d.get(f"hs_v2_date_entered_{DROP_ID}")))

N = len(deals)
print(f"=== EHR COVERAGE across {N} Planner deals ===")
for k,v in Counter(d["_ehr"] for d in deals).most_common():
    print(f"  {k:<10} {v:>4}  ({v/N*100:.0f}%)")

print("\n=== EHR split of deals CURRENTLY in Waitlist ===")
wait_now = [d for d in deals if d.get("dealstage")==STAGES[0][0]]
print(f"  {len(wait_now)} deals currently in Waitlist:")
for k,v in Counter(d["_ehr"] for d in wait_now).most_common():
    print(f"    {k:<10} {v:>4}")

def funnel(subset, title):
    n=len(subset)
    print(f"\n=== {title}  (n={n}) ===")
    ever=[sum(1 for d in subset if d["_idx"]>=i) for i in range(len(STAGES))]
    for i,lab in enumerate(LABELS):
        conv = f"  conv {ever[i]/ever[i-1]*100:5.1f}%" if i>0 and ever[i-1] else ""
        print(f"  {lab:<13} {ever[i]:>4}{conv}")
    if ever[0]:
        print(f"  END-TO-END Waitlist->Live: {ever[-1]/ever[0]*100:.1f}%")
    return ever

allf  = funnel(deals, "ALL EHR (original)")
emis  = funnel([d for d in deals if d["_ehr"]=="EMIS"], "EMIS ONLY (addressable)")
s1    = [d for d in deals if d["_ehr"]=="SystmOne"]
medi  = [d for d in deals if d["_ehr"]=="Medicus"]
unk   = [d for d in deals if d["_ehr"]=="Unknown"]

print(f"\n=== PARKED / NON-ADDRESSABLE (not a stall) ===")
print(f"  SystmOne (TPP/S1): {len(s1)} deals — where they sit now:")
for k,v in Counter([dict(STAGES).get(d.get('dealstage')) or 'Dropped/other' for d in s1]).most_common():
    print(f"      {k:<13} {v}")
print(f"  Medicus: {len(medi)} deals;  Unknown EHR: {len(unk)} deals")

# Corrected Waitlist->Demo conversion: drop SystmOne (and optionally Unknown) from denom
emis_n = len([d for d in deals if d["_ehr"]=="EMIS"])
emis_demo = sum(1 for d in deals if d["_ehr"]=="EMIS" and d["_idx"]>=1)
print(f"\n=== CORRECTED TOP-OF-FUNNEL ===")
print(f"  Original Waitlist->Demo:        {allf[1]}/{allf[0]} = {allf[1]/allf[0]*100:.0f}%")
if emis_n:
    print(f"  EMIS-only Waitlist->Demo:       {emis_demo}/{emis_n} = {emis_demo/emis_n*100:.0f}%")
# Of the currently-stuck waitlist, how many are genuinely actionable (EMIS)?
c = Counter(d["_ehr"] for d in wait_now)
print(f"\n  Of {len(wait_now)} stuck in Waitlist now: "
      f"{c.get('EMIS',0)} EMIS (actionable), {c.get('SystmOne',0)} SystmOne (parked), "
      f"{c.get('Medicus',0)} Medicus, {c.get('Unknown',0)} Unknown")

# Dropped-out by EHR (were SystmOne unfairly counted as drops?)
print(f"\n=== DROPPED OUT by EHR ===")
for k,v in Counter(d["_ehr"] for d in deals if d["_dropped"]).most_common():
    print(f"  {k:<10} {v}")
