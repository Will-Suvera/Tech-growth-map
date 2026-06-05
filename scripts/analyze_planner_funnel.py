#!/usr/bin/env python3
"""Compute funnel conversion + velocity + stall analysis from outputs/planner_deals.json."""
import json, statistics
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
data = json.loads((ROOT / "outputs" / "planner_deals.json").read_text())
deals = data["deals"]
STAGES = [(s["id"], s["label"]) for s in data["stage_order"]]   # funnel order
DROP_ID, DROP_LABEL = data["dropped_stage"]["id"], data["dropped_stage"]["label"]
ID2LABEL = {sid: lab for sid, lab in STAGES} | {DROP_ID: DROP_LABEL}
LABELS = [lab for _, lab in STAGES]
NOW = datetime.now(timezone.utc)

def parse(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def days(a, b):
    return (b - a).total_seconds() / 86400.0

# ---- per-deal enrichment ----
for d in deals:
    d["_entries"] = {sid: parse(d.get(f"hs_v2_date_entered_{sid}")) for sid, _ in STAGES}
    d["_drop"] = parse(d.get(f"hs_v2_date_entered_{DROP_ID}"))
    d["_created"] = parse(d.get("createdate"))
    # furthest funnel stage index ever reached (by presence of an entry timestamp)
    reached = [i for i, (sid, _) in enumerate(STAGES) if d["_entries"][sid]]
    cur = d.get("dealstage")
    if cur in dict(STAGES):
        reached.append([i for i, (sid, _) in enumerate(STAGES)].index(
            [i for i, (sid, _) in enumerate(STAGES) if sid == cur][0]))
    d["_reached_idx"] = max(reached) if reached else -1
    d["_dropped"] = (cur == DROP_ID) or (d["_drop"] is not None)

N = len(deals)
print(f"=== PLANNER (SaaS) ONBOARDING PIPELINE — {N} deals  (as of {NOW.date()}) ===\n")

# ---- current stage distribution ----
from collections import Counter
cur_dist = Counter(ID2LABEL.get(d.get("dealstage"), d.get("dealstage")) for d in deals)
print("CURRENT STAGE (where each deal sits right now):")
for lab in LABELS + [DROP_LABEL]:
    print(f"  {lab:<14} {cur_dist.get(lab,0):>4}")
other = {k:v for k,v in cur_dist.items() if k not in LABELS + [DROP_LABEL]}
if other: print("  OTHER:", other)

# ---- EVER-REACHED funnel + step conversion ----
print("\nEVER REACHED stage X (cumulative, incl. deals that later dropped/advanced):")
ever = [sum(1 for d in deals if d["_reached_idx"] >= i) for i in range(len(STAGES))]
for i, lab in enumerate(LABELS):
    conv = ""
    if i > 0 and ever[i-1] > 0:
        conv = f"   step conv from {LABELS[i-1]}: {ever[i]/ever[i-1]*100:4.1f}%  (lost {ever[i-1]-ever[i]})"
    print(f"  {lab:<14} {ever[i]:>4}{conv}")
if ever[0] > 0:
    print(f"\n  END-TO-END  Waitlist->Live: {ever[-1]/ever[0]*100:.1f}%   "
          f"DemoHeld->Live: {ever[-1]/ever[2]*100:.1f}% (of {ever[2]})" if ever[2] else "")

# ---- VELOCITY: median days between consecutive stage entries ----
print("\nVELOCITY — days between entering consecutive stages (deals with both timestamps):")
for i in range(len(STAGES)-1):
    sidA, labA = STAGES[i]; sidB, labB = STAGES[i+1]
    gaps = [days(d["_entries"][sidA], d["_entries"][sidB]) for d in deals
            if d["_entries"][sidA] and d["_entries"][sidB]
            and d["_entries"][sidB] >= d["_entries"][sidA]]
    if gaps:
        print(f"  {labA:>12} -> {labB:<12}  n={len(gaps):>3}  "
              f"median={statistics.median(gaps):6.1f}d  mean={statistics.mean(gaps):6.1f}d  "
              f"max={max(gaps):6.0f}d")
    else:
        print(f"  {labA:>12} -> {labB:<12}  n=0")

# ---- STALL: deals currently in a stage, how long they've sat there ----
print("\nSTALL — deals CURRENTLY in each stage & days since they entered it:")
for sid, lab in STAGES:
    cohort = [d for d in deals if d.get("dealstage") == sid]
    if not cohort:
        print(f"  {lab:<14} 0"); continue
    ages = [days(d["_entries"][sid], NOW) for d in cohort if d["_entries"][sid]]
    if not ages:
        print(f"  {lab:<14} {len(cohort):>3}  (no entry ts)"); continue
    stalled30 = sum(1 for a in ages if a > 30)
    stalled60 = sum(1 for a in ages if a > 60)
    print(f"  {lab:<14} {len(cohort):>3}  median age={statistics.median(ages):6.1f}d  "
          f">30d={stalled30}  >60d={stalled60}  oldest={max(ages):.0f}d")

# ---- DROPPED OUT: how many, furthest stage reached before drop ----
dropped = [d for d in deals if d["_dropped"]]
print(f"\nDROPPED OUT: {len(dropped)} deals.  Furthest funnel stage reached before dropping:")
drop_by_stage = Counter()
for d in dropped:
    idx = d["_reached_idx"]
    drop_by_stage[LABELS[idx] if 0 <= idx < len(LABELS) else "(none)"] += 1
for lab in LABELS:
    if drop_by_stage.get(lab):
        print(f"  reached {lab:<14} then dropped: {drop_by_stage[lab]}")

# ---- COHORT RECENCY: when did these deals enter the funnel ----
print("\nDEAL AGE (createdate -> now) — is the funnel young or mature?")
ages = sorted(days(d["_created"], NOW) for d in deals if d["_created"])
for lbl, lo, hi in [("<=14d",0,14),("15-30d",14,30),("31-60d",30,60),
                    ("61-90d",60,90),("91-180d",90,180),(">180d",180,1e9)]:
    print(f"  {lbl:<8} {sum(1 for a in ages if lo < a <= hi):>4}")
if ages:
    print(f"  median deal age: {statistics.median(ages):.0f}d   oldest: {max(ages):.0f}d")

# ---- DPA Signed -> Live specifically (the activation handoff) ----
print("\nKEY HANDOFFS:")
for (sidA,labA),(sidB,labB) in [((STAGES[2]),(STAGES[4])),  # Demo Held -> DPA Signed
                                ((STAGES[4]),(STAGES[5]))]: # DPA Signed -> Live
    both = [d for d in deals if d["_entries"][sidA] and d["_entries"][sidB]]
    reachedA = sum(1 for d in deals if d["_reached_idx"] >= [s for s,_ in STAGES].index(sidA))
    reachedB = sum(1 for d in deals if d["_reached_idx"] >= [s for s,_ in STAGES].index(sidB))
    print(f"  {labA} -> {labB}: {reachedB}/{reachedA} reached "
          f"({reachedB/reachedA*100:.0f}%)" if reachedA else f"  {labA}->{labB}: n/a")
