#!/usr/bin/env python3
"""Pull every deal in the Planner (SaaS) Onboarding pipeline with its full
stage-entry timeline, so we can compute funnel conversion + velocity locally.

Stage IDs are STABLE (renaming a stage in HubSpot keeps its ID); display LABELS
are fetched live from the pipeline so a HubSpot rename flows through to the
dashboard automatically. Downstream logic keys off the stable `key`, not labels.

Writes outputs/planner_deals.json. Auth: HUBSPOT_API_TOKEN (pat-eu1) from env or .env.
"""
import json, os, sys, time, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone

BASE = "https://api-eu1.hubapi.com"
PIPELINE = "3277290730"

# (stageId, stable_key, fallback_label) in funnel order. `key` never changes;
# `fallback_label` is only used if the live label fetch fails.
STAGE_DEFS = [
    ("4489053409", "waitlist",    "Signed-up List"),
    ("5147362520", "demo_booked", "Demo Booked"),
    ("5017986288", "demo_held",   "Demo Held"),
    ("4489053410", "dpa_sent",    "DPA Sent"),
    ("4489053411", "dpa_signed",  "DPA Signed Onboard Ready"),
    ("4487571659", "live",        "Full Functionality Live"),
]
DROPPED = ("4527836370", "dropped", "Dropped Out")

ROOT = Path(__file__).resolve().parent.parent

def get_token():
    t = os.environ.get("HUBSPOT_API_TOKEN", "").strip()
    if t:
        return t
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line.startswith("HUBSPOT_API_TOKEN"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: HUBSPOT_API_TOKEN not found in env or .env", file=sys.stderr)
    sys.exit(1)

TOKEN = get_token()

def hs_post(endpoint, body):
    url = BASE + endpoint
    data = json.dumps(body).encode()
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            print(f"HTTP {e.code}: {e.read().decode()[:500]}", file=sys.stderr)
            raise
    raise RuntimeError("unreachable")

props = ["dealname", "dealstage", "pipeline", "createdate", "closedate",
         "hs_lastmodifieddate", "amount", "hubspot_owner_id", "ehr_type",
         "notes_last_contacted", "hs_lastactivitydate"]
props += [f"hs_v2_date_entered_{sid}" for sid, _, _ in STAGE_DEFS]
props += [f"hs_v2_date_entered_{DROPPED[0]}"]

def hs_get(endpoint):
    req = urllib.request.Request(BASE + endpoint, method="GET", headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def fetch_live_labels():
    """Map stageId -> current HubSpot label for this pipeline. Falls back to the
    hardcoded labels if the pipeline API is unavailable."""
    labels = {sid: lab for sid, _, lab in STAGE_DEFS}
    labels[DROPPED[0]] = DROPPED[2]
    try:
        resp = hs_get(f"/crm/v3/pipelines/deals/{PIPELINE}")
        for st in resp.get("stages", []):
            if st.get("id") in labels:
                labels[st["id"]] = st.get("label") or labels[st["id"]]
        print("  fetched live stage labels from HubSpot pipeline")
    except Exception as e:
        print(f"  WARN: could not fetch live labels ({e}); using fallbacks")
    return labels

def pull_deals():
    out, after = [], None
    while True:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "pipeline", "operator": "EQ", "value": PIPELINE}]}],
            "properties": props,
            "limit": 100,
        }
        if after:
            body["after"] = after
        resp = hs_post("/crm/v3/objects/deals/search", body)
        out.extend(resp.get("results", []))
        paging = resp.get("paging", {}).get("next", {})
        after = paging.get("after")
        if not after:
            break
        time.sleep(0.2)
    return out

def main():
    deals = pull_deals()
    labels = fetch_live_labels()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": PIPELINE,
        # id = stable HubSpot stage id · key = stable internal key · label = live HubSpot label
        "stage_order": [{"id": sid, "key": key, "label": labels.get(sid, fb)}
                        for sid, key, fb in STAGE_DEFS],
        "dropped_stage": {"id": DROPPED[0], "key": DROPPED[1], "label": labels.get(DROPPED[0], DROPPED[2])},
        "count": len(deals),
        "deals": [d.get("properties", {}) | {"_id": d.get("id")} for d in deals],
    }
    outdir = ROOT / "outputs"
    outdir.mkdir(exist_ok=True)
    (outdir / "planner_deals.json").write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(deals)} deals -> outputs/planner_deals.json")

if __name__ == "__main__":
    main()
