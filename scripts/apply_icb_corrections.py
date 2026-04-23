#!/usr/bin/env python3
"""One-shot: apply manual ICB corrections to practices_geocoded.json.

The NHS ODS feed occasionally returns blank or malformed `icb` values for
active GP practices (observed: "#N/A", blank string, stray SICBL suffix).
The dashboard's ICB grouping needs these filled in.

Corrections below are human-verified from practice name + PCN + postcode.
Re-run this script after any full `refresh_data.py --practices` — that
path rebuilds practices_geocoded.json from scratch and will wipe these.

Each entry uses the **pre-merger** ICB name so that
`scripts/icb_mapper.resolve_icb` can relabel it to the post-2026-04-01 name
in downstream reports (so Frimley resolves to Thames Valley / Surrey &
Sussex / Hants & IoW via the xlsx practice-move table, etc.).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRACTICES_PATH = ROOT / "public" / "data" / "practices_geocoded.json"

# ODS -> pre-merger ICB name. Any practice not in this dict is left alone.
CORRECTIONS: dict[str, str] = {
    "E85075": "NHS North West London ICB",                          # Acton Gardens (Acton PCN)
    "H85618": "NHS South West London ICB",                          # James O'Riordan (Cheam & South Sutton PCN)
    "G82079": "NHS Kent and Medway ICB",                            # Westgate Surgery (Care Kent PCN)
    "C82096": "NHS Leicester, Leicestershire and Rutland ICB",      # Hugglescote (NW Leics PCN)
    "A81019": "NHS North East and North Cumbria ICB",               # Crossfell Health Centre
    "K81657": "NHS Frimley ICB",                                    # Evergreen Practice — frimley map resolves to Thames Valley
    "H82003": "NHS Sussex ICB",                                     # Meadows Surgery
    "M85600": "NHS Birmingham and Solihull ICB",                    # Rea Valley Health Partnership
    "K84012": "NHS Bristol, North Somerset & South Glos ICB",       # Elm Tree Surgery (Brunel Health Group PCN)
    "L81046": "NHS Bristol, North Somerset & South Glos ICB",       # Leap Valley Medical Centre (BNSSG PCN)
    "L81632": "NHS Bristol, North Somerset & South Glos ICB",       # Emersons Green Medical Centre (BNSSG PCN)
    "M82016": "NHS Shropshire, Telford and Wrekin ICB",             # Radbrook Green Surgery (Shrewsbury) — strip stray SICBL suffix
}


def main() -> None:
    with open(PRACTICES_PATH) as f:
        practices = json.load(f)

    by_ods = {p["ods"].upper(): p for p in practices}

    applied = 0
    skipped_missing: list[str] = []
    skipped_same: list[str] = []

    for ods, new_icb in CORRECTIONS.items():
        p = by_ods.get(ods.upper())
        if p is None:
            skipped_missing.append(ods)
            continue
        existing = (p.get("icb") or "").strip()
        if existing == new_icb:
            skipped_same.append(ods)
            continue
        p["icb"] = new_icb
        applied += 1
        print(f"  {ods}: {existing!r} -> {new_icb!r}")

    if skipped_missing:
        print(f"\n[!] {len(skipped_missing)} correction ODS codes not found in "
              f"practices_geocoded.json: {skipped_missing}")
    if skipped_same:
        print(f"[ok] {len(skipped_same)} already correct: {skipped_same}")

    if applied:
        with open(PRACTICES_PATH, "w") as f:
            json.dump(practices, f)
        print(f"\nApplied {applied} corrections. Wrote {PRACTICES_PATH}.")
    else:
        print("\nNo changes needed.")


if __name__ == "__main__":
    main()
