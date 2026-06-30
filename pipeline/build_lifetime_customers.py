#!/usr/bin/env python3
"""Build a deduplicated 'lifetime customers' sheet — every org that has ever
worked with Suvera, across the VC cohort (hand-pasted) and the Planner funnel
(post-DPA-signed deals from funnel_board.json).

Output columns: Practice | ODS | Signed up | For What | ICB | PCN | Org Type | Stage | Source
One row per ODS (deduped, uppercased). Blank-ODS rows are kept individually.
"""
import csv
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUNNEL = os.path.join(ROOT, "apps/primary-care-tech-overview/public/data/funnel_board.json")
GEO = os.path.join(ROOT, "apps/tech-growth-map/public/data/practices_geocoded.json")
PCN_CACHE = os.path.join(ROOT, "pipeline/.pcn_members_cache.json")
OUT = os.path.join(ROOT, "lifetime_customers.csv")

# ---------------------------------------------------------------------------
# Cohort A — first paste. (ods, icb, icb_ods, org_type, name)  -> VC
# ---------------------------------------------------------------------------
COHORT_A = [
    ("Y02842", "NHS North West London ICB", "QRV", "GP", "HALF PENNY STEPS HEALTH CENTRE"),
    ("D81008", "NHS Cambridgeshire and Peterborough ICB", "QUE", "GP", "NORTH BRINK PRACTICE"),
    ("E87742", "NHS North West London ICB", "QRV", "GP", "THE GOLBORNE MEDICAL CENTRE"),
    ("U12200", "NHS Staffordshire and Stoke-on-Trent ICB", "QNC", "PCN", "CANNOCK NORTH PCN"),
    ("U79015", "NHS Cambridgeshire and Peterborough ICB", "QUE", "PCN", "WISBECH PCN"),
    ("U53562", "NHS North West London ICB", "QRV", "PCN", "NORTH SOUTHALL PCN"),
    ("U81324", "NHS North West London ICB", "QRV", "PCN", "ACTON PCN"),
    ("G82014", "NHS Kent and Medway ICB", "QKS", "GP", "WOODLANDS FAMILY PRACTICE"),
    ("U76908", "NHS Kent and Medway ICB", "QKS", "PCN", "GILLINGHAM SOUTH PCN"),
    # ROCHESTER PCN (U82359) moved to AGGREGATE_DEALS — dissolved, no members in ODS.
    ("D81008", "NHS Cambridgeshire and Peterborough ICB", "QUE", "GP", "NORTH BRINK PRACTICE"),
    ("U23362", "NHS North East London ICB", "QMF", "PCN", "SOUTH ONE NEWHAM PCN"),
    ("U96386", "NHS Sussex ICB", "QNX", "PCN", "HORSHAM COLLABORATIVE PCN"),
    ("U56757", "NHS Kent and Medway ICB", "QKS", "PCN", "MEDWAY PENINSULA PCN"),
    ("U36687", "NHS North Central London ICB", "QMJ", "PCN", "ENFIELD SOUTH WEST PCN"),
    ("U09072", "NHS Sussex ICB", "QNX", "PCN", "PRESTON PARK COMMUNITY PCN"),
    ("U47975", "NHS Norfolk and Waveney ICB", "QMM", "PCN", "SOUTH WAVENEY PCN"),
    ("U26715", "NHS Black Country ICB", "QUA", "PCN", "WOLVERHAMPTON SOUTH EAST PCN"),
    ("U58312", "NHS North Central London ICB", "QMJ", "PCN", "ENFIELD UNITY PCN"),
    ("U60057", "NHS Shropshire, Telford and Wrekin ICB", "QOC", "PCN", "SHREWSBURY PCN"),
    ("D81645", "NHS Cambridgeshire and Peterborough ICB", "QUE", "GP", "THE GRANGE MEDICAL CENTRE"),
    ("U33832", "NHS Lincolnshire ICB", "QJM", "PCN", "MERIDIAN MEDICAL PCN"),
    ("U16083", "NHS North West London ICB", "QRV", "PCN", "SOUTH CENTRAL EALING PCN"),
    ("U34632", "NHS Lancashire and South Cumbria ICB", "QE1", "PCN", "BRIDGEDALE SOUTH RIBBLE PCN"),
    ("Y00316", "NHS North Central London ICB", "QMJ", "GP", "WOODLANDS MEDICAL PRACTICE"),
    ("U91471", "NHS North West London ICB", "QRV", "PCN", "INCLUSIVE HEALTH PCN"),
    ("U52468", "NHS Suffolk and North East Essex ICB", "QJG", "PCN", "TENDRING PCN"),
    ("U68649", "NHS Devon ICB", "QJK", "PCN", "WATERSIDE HEALTH NETWORK PCN"),
    ("U27139", "NHS North Central London ICB", "QMJ", "PCN", "HARINGEY - SOUTH WEST PCN"),
    # NHS NORTH EAST LONDON CCG (9-practice ICB-level deal) moved to AGGREGATE_DEALS —
    # members not tracked; counted at deal level. (U70230 is actually Leigh PCN, below.)
    ("U45703", "NHS North West London ICB", "QRV", "PCN", "GREENWELL PCN"),
    ("U70230", "NHS Greater Manchester ICB", "QOP", "PCN", "LEIGH PCN"),
    ("E81037", "NHS Bedfordshire, Luton and Milton Keynes ICB", "QHG", "GP", "THE DE PARYS GROUP"),
    ("U40502", "NHS North East and North Cumbria ICB", "QHM", "PCN", "HARTLEPOOL HEALTH PCN"),
    ("U02731", "NHS Cheshire and Merseyside ICB", "QYG", "PCN", "IGPC PCN"),
    ("U27664", "NHS Kent and Medway ICB", "QKS", "PCN", "STROOD PCN"),
    ("U68696", "NHS Buckinghamshire, Oxfordshire and Berkshire West ICB", "QU9", "PCN", "EARLEY+ PCN"),
    ("U25882", "NHS Derby and Derbyshire ICB", "QJ2", "PCN", "EREWASH PCN"),
    ("U98116", "NHS Hampshire and Isle of Wight ICB", "QRL", "PCN", "CAMROSE, GILLIES & HACKWOOD PARTNERSHIP PCN"),
    ("C86019", "NHS South Yorkshire ICB", "QF7", "GP", "THE SCOTT PRACTICE"),
    ("U05784", "NHS North West London ICB", "QRV", "PCN", "BROMPTON HEALTH PCN"),
    # SEL "11 practices" deal = Modality Lewisham + Lewisham Care Partnership PCNs
    # (each a single large GP-practice ODS spanning multiple sites). Expanded.
    ("U22506", "NHS South East London ICB", "QKK", "PCN", "MODALITY LEWISHAM PCN"),
    ("U11059", "NHS South East London ICB", "QKK", "PCN", "LEWISHAM CARE PARTNERSHIP PCN"),
    ("U58312", "NHS North Central London ICB", "QMJ", "PCN", "ENFIELD UNITY PCN"),
    ("", "NHS Kent and Medway ICB", "QKS", "GP", "INVICTA HEALTH CONNECT FOLKESTONE"),
    ("J82218", "NHS Hampshire and Isle of Wight ICB", "QRL", "GP", "Chineham Medical Practice"),
    # HIOW "ICB" 9-practice deal is already covered by the 9 named HIOW VC/Planner
    # practices below (Camrose, Coastal, Meon, Chineham, Winchester Rural South x3,
    # + Planner Bramblys/Alma Road), so the aggregate row is dropped to avoid double count.
    ("U13655", "NHS Birmingham and Solihull ICB", "QHL", "PCN", "SBA"),
    ("U06079", "NHS Hertfordshire and West Essex ICB", "QM7", "PCN", "Abbey Health PCN"),
    ("U02610", "NHS Cornwall and the Isles of Scilly ICB", "QT6", "PCN", "East Cornwall PCN"),
    ("H81031", "NHS Surrey Heartlands ICB", "QXU", "GP", "Witley Medical Practice"),
    ("M88006", "NHS Black Country ICB", "QUA", "GP", "Cape Hill"),
    ("H82066", "NHS Sussex ICB", "QNX", "GP", "Fitzalan Medical Group"),
    ("U92600", "NHS Hampshire and Isle of Wight ICB", "QRL", "PCN", "Meon Health"),
    ("P84068", "NHS Greater Manchester ICB", "QOP", "GP", "Chorlton Family Practice"),
    ("P84038", "NHS Greater Manchester ICB", "QOP", "GP", "Ashville Surgery"),
    ("U51153", "NHS Birmingham and Solihull ICB", "QHL", "PCN", "W&R PCN"),
    ("P84650", "NHS Greater Manchester ICB", "QOP", "GP", "The Alexndra Practice and Princess Road Surgery"),
    ("U34811", "NHS North Central London ICB", "QMJ", "PCN", "West and Central PCN"),
    ("U93573", "NHS Bedfordshire, Luton and Milton Keynes ICB", "QHG", "PCN", "The Bridge MK PCN"),
    # North East and North Cornwall ICA (15-practice deal) — 11 identified via
    # East Cornwall + Three Harbours PCNs below; remainder in AGGREGATE_DEALS.
    ("L82010", "NHS Cornwall and the Isles of Scilly ICB", "QT6", "GP", "Bosvena Health"),
    ("J82034", "NHS Hampshire and Isle of Wight ICB", "QRL", "GP", "Wickham Surgery"),
    ("J82007", "NHS Hampshire and Isle of Wight ICB", "QRL", "PCN", "Coastal (West Hampshire) PCN"),
    ("U13655", "NHS Birmingham and Solihull ICB", "QHL", "PCN", "South Birmingham Alliance"),
    ("M88006", "NHS Black Country ICB", "QUA", "GP", "Cape Hill"),
    ("J82218", "NHS Hampshire and Isle of Wight ICB", "QRL", "GP", "Chineham Medical Practice"),
    ("E85075", "NHS North West London ICB", "QRV", "GP", "GP Surgery @ Acton Gardens"),
    ("U16083", "NHS North West London ICB", "QRV", "PCN", "SOUTH CENTRAL EALING PCN"),
    ("U06079", "NHS Hertfordshire and West Essex ICB", "QM7", "PCN, GP", "Abbey Health PCN (Maltings)"),
    ("U73966", "NHS Hertfordshire and West Essex ICB", "QYG", "GP", "HaLo PCN"),
    ("", "", "", "", "Novartis"),
    ("G82014", "NHS Kent and Medway ICB", "QKS", "PCN", "Woodlands Family Practice"),
    ("U45703", "NHS North West London ICB", "QRV", "PCN", "GREENWELL PCN"),
    ("K81047", "NHS Buckinghamshire, Oxfordshire and Berkshire West ICB", "QU9", "PCN", "Brookside (Earley+)"),
    ("U06978", "NHS North East London ICB", "QMF", "PCN", "Newham North East 2 PCN"),
    ("H83024", "NHS South West London ICB", "QWE", "GP", "Woodcote Medical"),
    ("F86700", "NHS North East London ICB", "QMF", "GP", "Kings Head Medical Practice"),
    ("E84013", "NHS North West London ICB", "QRV", "GP", "Church End Medical Centre"),
    ("D81015", "NHS Cambridgeshire and Peterborough ICB", "QUE", "GP", "Parson Drove Surgery"),
    ("C83626", "NHS Lincolnshire ICB", "QJM", "GP", "Brayford Medical Practice"),
    ("C82096", "NHS Leicester, Leicestershire and Rutland ICB", "QK1", "GP", "Hugglescote Surgery"),
    ("H82005", "NHS Sussex ICB", "QNX", "GP", "Cuckfield Medical Practice"),
    ("G84023", "NHS South East London ICB", "QKK", "GP", "Southborough Lane Surgery"),
    ("F82647", "NHS North East London ICB", "QMF", "GP", "Salisbury Avenue Surgery"),
]

# ---------------------------------------------------------------------------
# Cohort C — second paste, PCN -> constituent GP practices.
# (icb, pcn, pcn_ods, practice_name, practice_ods)  -> VC, org_type GP
# ---------------------------------------------------------------------------
COHORT_C = [
    ("Hertfordshire and West Essex ICB", "Abbey Health PCN", "U06079", "Maltings Surgery", "E82031"),
    ("Hertfordshire and West Essex ICB", "Abbey Health PCN", "U06079", "Summerfield Health Centre", "E82107"),
    ("Hampshire and Isle of Wight ICB", "Whitewater Loddon PCN", "U34184", "Chineham Medical Practice", "J82218"),
    ("Black Country ICB", "SWB Caritas PCN", "U57294", "Cape Hill Medical Centre", "M88006"),
    ("Bedfordshire Luton and Milton Keynes ICB", "The Bridge MK PCN", "U93573", "Newport Pagnell Medical Centre", "K82016"),
    ("Hampshire and Isle of Wight ICB", "Meon Health", "U92600", "Meon Health Practice", "J82154"),
    ("Cornwall and Isles of Scilly", "North and East Cornwall ICA (Three Habours PCN)", "U60113", "Bosvena Health", "L82010"),
    ("Cornwall and Isles of Scilly", "North and East Cornwall ICA (Three Habours PCN)", "U60113", "Fowey River Practice", "L82035"),
    ("Cornwall and Isles of Scilly", "North and East Cornwall ICA (Three Habours PCN)", "U60113", "Lostwithiel Medical Practice", "L82039"),
    ("Cornwall and Isles of Scilly", "North and East Cornwall ICA (Three Habours PCN)", "U60113", "Middleway Surgery", "L82026"),
    ("Hampshire and Isle of Wight ICB", "Winchester Rural South PCN", "U11181", "Wickham Surgery", "J82034"),
    ("Hampshire and Isle of Wight ICB", "Winchester Rural South PCN", "U11181", "Bishops Waltham Surgery", "J82064"),
    ("Hampshire and Isle of Wight ICB", "Winchester Rural South PCN", "U11181", "Twyford Surgery", "J82116"),
    ("Birmingham and Solihull ICB", "South Birmingham Alliance PCN", "U13655", "Rea Valley Health Partnership", "M85600"),
    ("Hertfordshire and West Essex ICB", "HaLo PCN", "U73966", "Harvey Group Practice", "E82084"),
    ("Hertfordshire and West Essex ICB", "HaLo PCN", "U73966", "Lodge Highfield Redborne", "E82014"),
    ("Greater Manchester ICB", "West Central Manchester PCN", "", "Ashville Surgery", "P84038"),
    ("Greater Manchester ICB", "West Central Manchester PCN", "", "Chorlton Family Practice", "P84068"),
    ("North West London ICB", "South Central Ealing", "U16083", "Ealing Park Health Centre", "E85657"),
    ("North West London ICB", "South Central Ealing", "U16083", "Elthorne Park Surgery", "E85628"),
    ("North West London ICB", "South Central Ealing", "U16083", "Grosvenor House Surgery", "E85034"),
    ("North West London ICB", "South Central Ealing", "U16083", "Northfields Surgery", "E85014"),
    ("North West London ICB", "South Central Ealing", "U16083", "The Florence Road Surgery", "E85122"),
    ("Cornwall and Isles of Scilly ICB", "Bosvena and Three Harbours", "U60113", "Bosvena Health", "L82010"),
    ("Hampshire and Isle of Wight ICB", "COASTAL (WEST HAMPSHIRE) PCN", "U56140", "Coastal Medical Partnership", "J82007"),
    ("Sussex ICB", "Angmering Coppice Fitzalan PCN", "U04748", "Fitzalan Medical Group", "H82066"),
    ("North West London ICB", "Acton PCN", "U81324", "GP Surgery @ Acton Gardens", "E85075"),
    ("Lincolnshire ICB", "Lincoln Health Partnership PCN", "U38661", "Brayford Medical Practice", "C83626"),
    ("Leicester, Leicestershire and Rutland ICB", "North West Leicestershire PCN", "U42007", "Hugglescote Surgery", "C82096"),
    ("Sussex ICB", "Haywards Health Villages PCN", "U03364", "Cuckfield Medical Centre", "H82005"),
    ("Hertfordshire and West Essex ICB", "Icknield PCN", "U82047", "Ashwell Surgery", "D81047"),
    ("Hertfordshire and West Essex ICB", "Icknield PCN", "U82047", "The Nevells Road Surgery", "E82008"),
    ("Hertfordshire and West Essex ICB", "Icknield PCN", "U82047", "The Birchwood and Sollershott Surgeries", "E82082"),
    ("Hertfordshire and West Essex ICB", "Icknield PCN", "U82047", "The Baldock Surgery", "E82099"),
    ("Hertfordshire and West Essex ICB", "Icknield PCN", "U82047", "The Garden City Surgery", "E82661"),
    ("North West London ICB", "Harness South PCN", "U11559", "Oxgate Gardens Surgery", "E84076"),
    ("Shropshire, Telford and Wrekin ICB", "Shrewsbury PCN", "U60057", "Rabrook Green Surgery", "M82016"),
    ("Kent and Medway ICB", "Gillingham South PCN", "U76908", "Woodlands Family Practice", "G82014"),
    ("North East London ICB", "Newham North East 2 PCN", "U06978", "Lathom Road Medical Centre", "F84070"),
    ("Bristol, North Somerset & South Glos ICB", "Pier Health PCN", "U63843", "168 Medical Group", "L81051"),
    ("South East London ICB", "Five Elms PCN", "U77447", "Southborough Lane Surgery", "G84023"),
    ("North West London ICB", "Inclusive Health PCN", "U91471", "Half Penny Steps Health Centre", "Y02842"),
]

# ---------------------------------------------------------------------------
# Cohort D — Planner "DPA Signed onwards", from the onboarding tracker Google
# Sheet (1b9Lncxb...), the operational source of truth. 53 practices where the
# DPA column == "Signed". (ods, name, tracker_pcn, status)  -> Planner
# Names/PCN are the tracker's operational labels; ICB resolved from
# practices_geocoded / funnel at runtime.
# ---------------------------------------------------------------------------
COHORT_D = [
    ("K81075", "Farnham Road Practice", "Spine PCN", "On hold"),
    ("H84042", "Holmwood Corner Surgery", "New Malden & Worcester Park PCN", "On hold"),
    ("M91621", "Palfrey Health Centre", "Walsall South 2 PCN", "In Progress"),
    ("H85055", "West Barnes Surgery", "New Malden & Worcester Park PCN", "Live"),
    ("K81030", "Ringmead Medical Group", "The Health Triangle PCN", "In Progress"),
    ("H84635", "Manor Drive Surgery", "New Malden & Worcester Park PCN", "In Progress"),
    ("K81047", "Brookside Group Practice", "Earley + PCN", "On hold"),
    ("E83034", "Colney Hatch Lane Surgery", "Barnet 2 PCN", "In Progress"),
    ("F85071", "Fernlea Surgery", "", "Live"),
    ("E84074", "Freuchen Medical Centre", "Harness South PCN", "Live"),
    ("F83063", "Killick Street Health Centre", "South Islington PCN", "In Progress"),
    ("E83003", "Oakleigh Road Health Centre", "Barnet 2 PCN", "Live"),
    ("E84021", "The Willesden Medical Centre", "", "Live"),
    ("H85095", "Robin Hood Lane Health Centre", "", "Live"),
    ("H85051", "Thornton Road and Valley Park", "Bourne Health", "In Progress"),
    ("J82067", "Voyager Health", "", "Live"),
    ("P84683", "The Docs Surgery", "", "Live"),
    ("C81634", "Arden House Medical Practice", "", "Live"),
    ("M85077", "Northwood Medical Centre", "", "Live"),
    ("G82224", "Old Parsonage Surgery", "Weald PCN", "Live"),
    ("F82647", "Salisbury Avenue Surgery", "", "In Progress"),
    ("P89008", "Ashton Medical Group Ltd", "Ashton PCN", "In Progress"),
    ("J82058", "Bramblys Grange Medical Practice", "", "Live"),
    ("B86024", "Priory View Medical Centre", "", "Live"),
    ("J82074", "Alma Road Surgery", "", "Live"),  # ODS blank in tracker; J82074 from funnel
    ("E82051", "Everest House Surgery", "Dacorum Beta PCN", "Live"),
    ("C84660", "Hounsfield Surgery", "", "Live"),
    ("P92014", "Standish Medical Practice", "", "Live"),
    ("E82013", "Bridgewater Surgeries", "", "In Progress"),
    ("A81608", "Elm Tree Surgery", "Stockton PCN", "In Progress"),
    ("Y00560", "Wootton Vale Healthy Living Centre", "", "Live"),
    ("E86030", "Brunel Medical Centre", "Synergy PCN", "In Progress"),
    ("Y01068", "Amaanah Medical Practice", "Washwood Heath PCN", "In Progress"),
    ("Y02794", "Oakleaf Medical Practice", "Washwood Heath PCN", "In Progress"),
    ("M88015", "Great Barr Practice", "Swb Central Health Partnerships PCN", "In Progress"),
    ("G84624", "anerley surgery", "", "Live"),
    ("P88012", "Beech House Medical Practice", "", "In Progress"),
    ("G85011", "clapham family practice", "", "In Progress"),
    ("Y02769", "St Neots Health Centre (OneMedical)", "", "In Progress"),
    ("M85071", "wychall lane surgery", "Bournville and Northfield PCN", "In Progress"),
    ("P81771", "Primrose Bank Medical Centre & Ewood Medical Centre", "", "In Progress"),
    ("H84030", "Central Surgery Surbiton", "", "In Progress"),
    ("E86017", "Hayes Medical Centre", "", "In Progress"),
    ("E84709", "Wembley Park Medical Centre", "Harness North PCN", "In Progress"),
    ("K82030", "Wye Valley Surgery", "", "In Progress"),
    ("H85006", "Mayfield Surgery (SWL)", "Prime Wandsworth PCN", "In Progress"),
    ("E86009", "Belmont Medical Centre", "Synergy PCN", "In Progress"),
    ("Y02900", "Brooklands Health Centre (OneMedical)", "", "In Progress"),
    ("L85019", "Minehead Medical Centre (OneMedical)", "", "In Progress"),
    ("L82050", "Rosedean House (OneMedical)", "", "In Progress"),
    ("Y02002", "The Light Surgery (OneMedical)", "", "In Progress"),
    ("B86029", "Westgate Surgery (OneMedical)", "", "In Progress"),
    ("Y06810", "Whitehouse Health Centre (OneMedical)", "", "In Progress"),
]

# ICB for the 3 OneMedical/Washwood codes absent from geo+funnel
MANUAL_ICB = {
    "Y02794": "NHS Birmingham and Solihull ICB",
    "Y02769": "NHS Cambridgeshire and Peterborough ICB",
    "Y02900": "NHS Bedfordshire, Luton and Milton Keynes ICB",
}

# ---------------------------------------------------------------------------
# Aggregate / count-only deals — VC contracts at ICB/PCN level whose individual
# member practices cannot be resolved to ODS codes (dissolved PCN or ICB-level
# deal with no membership list). Counted toward the lifetime total but listed as
# a single annotated row each. (icb, label, practice_count, note)
# ---------------------------------------------------------------------------
AGGREGATE_DEALS = [
    ("NHS North East London ICB", "NHS NORTH EAST LONDON CCG", 9,
     "ICB-level deal — member practices not tracked (per will@, counted as 9)"),
    ("NHS Kent and Medway ICB", "ROCHESTER PCN", 4,
     "PCN dissolved — members not in ODS directory; counted at deal size"),
]


def norm(s):
    return (s or "").strip()


# practice ODS -> display name, from the local England GP universe
GEO_NAME = {p["ods"].upper(): p.get("name", "") for p in json.load(open(GEO))}


def _load_cache():
    try:
        return json.load(open(PCN_CACHE))
    except Exception:
        return {}


def expand_pcn(pcn_ods, cache):
    """Return list of (practice_ods, practice_name) that are active members of
    the PCN, via NHS ODS ORD search (relationship RE8 -> PCN). Cached to disk."""
    pcn_ods = pcn_ods.upper()
    if pcn_ods in cache:
        return cache[pcn_ods]

    def _query(status_clause):
        url = ("https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations?"
               f"TargetOrgId={pcn_ods}&RelTypeId=RE8{status_clause}&Limit=200")
        req = urllib.request.Request(url, headers={"User-Agent": "suvera-dash"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        return [[o["OrgId"].upper(), GEO_NAME.get(o["OrgId"].upper()) or o.get("Name", "")]
                for o in d.get("Organisations", [])]

    members = []
    try:
        members = _query("&RelStatus=active")
        if not members:  # retry incl. inactive (dissolved PCNs)
            members = _query("")
    except Exception as e:
        print(f"  ! PCN {pcn_ods} expand failed: {e}")
    cache[pcn_ods] = members
    json.dump(cache, open(PCN_CACHE, "w"), indent=0)
    return members


def main():
    # key by practice ODS; everything is resolved to GP-practice level.
    by_ods = {}
    blank = []          # practice rows with no ODS
    unresolved_pcn = []  # PCN-level rows that returned no members

    def upsert(ods, name, icb, pcn, for_what, stage, source):
        ods = norm(ods).upper()
        rec = dict(name=norm(name), ods=ods, icb=norm(icb), pcn=norm(pcn),
                   for_what={for_what}, stage=norm(stage), source={source})
        if not ods:
            blank.append(rec)
            return
        if ods in by_ods:
            cur = by_ods[ods]
            cur["for_what"] |= rec["for_what"]
            cur["source"] |= rec["source"]
            if not cur["name"] and rec["name"]:
                cur["name"] = rec["name"]
            for f in ("icb", "pcn", "stage"):
                if not cur[f] and rec[f]:
                    cur[f] = rec[f]
        else:
            by_ods[ods] = rec

    cache = _load_cache()

    # Cohort A (VC) — GP rows kept as-is; PCN rows expanded to member practices.
    for ods, icb, _icb_ods, org_type, name in COHORT_A:
        ot = org_type.upper()
        if ot.startswith("PCN"):
            members = expand_pcn(ods, cache) if ods else []
            if members:
                for m_ods, m_name in members:
                    upsert(m_ods, m_name, icb, name, "VC", "", "VC list (PCN expanded)")
            elif ods.upper() in GEO_NAME:
                # labelled PCN but the code is actually a GP practice
                upsert(ods, GEO_NAME[ods.upper()], icb, "", "VC", "", "VC list")
            else:
                unresolved_pcn.append((ods, icb, name))
        elif ot == "GP":
            upsert(ods, name, icb, "", "VC", "", "VC list")
        else:  # ICB / other non-practice rows
            unresolved_pcn.append((ods, icb, name))

    # fill PCN for cohort-A GP rows from the local universe where known
    geo_pcn = {p["ods"].upper(): p.get("pcn_name", "") for p in json.load(open(GEO))}

    # Cohort C (VC, already practice-level with PCN)
    for icb, pcn, _pcn_ods, name, ods in COHORT_C:
        upsert(ods, name, icb, pcn, "VC", "", "VC PCN breakdown")

    # Cohort D (Planner, DPA-signed onwards) — from the onboarding tracker.
    # ICB resolved: funnel deal ICB -> geocoded ICB -> manual.
    fb = json.load(open(FUNNEL))
    funnel_icb = {d["ods"].upper(): d.get("icb", "") for d in fb["deals"] if d.get("ods")}
    geo_icb = {p["ods"].upper(): p.get("icb", "") for p in json.load(open(GEO))}
    for ods, name, pcn, status in COHORT_D:
        o = ods.upper()
        icb = funnel_icb.get(o) or geo_icb.get(o) or MANUAL_ICB.get(o, "")
        upsert(ods, name, icb, pcn, "Planner", status, "Onboarding tracker (DPA signed+)")

    # backfill missing PCN names from the local universe
    for r in by_ods.values():
        if not r["pcn"] and geo_pcn.get(r["ods"]):
            r["pcn"] = geo_pcn[r["ods"]]

    rows = list(by_ods.values())

    def fw(rec):
        order = {"VC": 0, "Planner": 1}
        return ", ".join(sorted(rec["for_what"], key=lambda x: order.get(x, 9)))

    rows.sort(key=lambda r: (r["icb"].lstrip("NHS ").lower(), r["pcn"].lower(), r["name"].lower()))

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ICB", "PCN", "GP Practice", "ODS", "For What", "Planner Stage", "Source"])
        for r in rows:
            w.writerow([r["icb"], r["pcn"], r["name"], r["ods"], fw(r), r["stage"],
                        ", ".join(sorted(r["source"]))])
        # practices we couldn't resolve to an ODS (kept for completeness)
        for r in blank:
            w.writerow([r["icb"], r["pcn"], r["name"], "", fw(r), r["stage"],
                        ", ".join(sorted(r["source"])) + " (no ODS)"])
        # PCN/ICB-level rows that returned no member practices
        for ods, icb, name in unresolved_pcn:
            w.writerow([icb, name, "", ods, "VC", "", "VC list (unresolved — no members)"])
        # Aggregate / count-only deals (no per-practice ODS resolvable)
        for icb, label, count, note in AGGREGATE_DEALS:
            w.writerow([icb, label, f"({count} practices — aggregate)", "", "VC", "",
                        f"VC list (aggregate deal) — {note}"])

    vc = [r for r in rows if "VC" in r["for_what"]]
    planner = [r for r in rows if "Planner" in r["for_what"]]
    both = [r for r in rows if {"VC", "Planner"} <= r["for_what"]]
    agg_count = sum(c for _, _, c, _ in AGGREGATE_DEALS)
    total = len(rows) + agg_count

    print(f"Wrote {OUT}")
    print(f"  Unique GP practices (by ODS): {len(rows)}")
    print(f"    VC:            {len(vc)}")
    print(f"    Planner:       {len(planner)}")
    print(f"    Both VC+Plan:  {len(both)} -> {[r['name'] for r in both]}")
    print(f"  Aggregate count-only deals: {agg_count} practices across "
          f"{len(AGGREGATE_DEALS)} deals -> {[l for _,l,_,_ in AGGREGATE_DEALS]}")
    print(f"  ==> LIFETIME TOTAL (identified + aggregate): {total}")
    print(f"  Practices with no ODS: {len(blank)} -> {[r['name'] for r in blank]}")
    print(f"  Unresolved PCN/ICB rows: {len(unresolved_pcn)} -> {[n for _,_,n in unresolved_pcn]}")


if __name__ == "__main__":
    main()
