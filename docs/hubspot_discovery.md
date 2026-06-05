# Phase 0 — Attribution Data Discovery

_Generated 2026-05-22. Sources: HubSpot EU1 portal (143576889) via `scripts/discover_hubspot_attribution.py` + Notion Partner Meeting Library (`collection://8115f0ee-00c8-488a-a05b-57726af0acf4`)._

## Headline

| Question | Answer |
|---|---|
| Can we build the funnel from HubSpot data alone? | **Yes** — `lifecyclestage` is 100% populated; `hs_v2_date_entered_*` gives per-stage entry timestamps for every contact. |
| Is source attribution achievable? | **Partially.** Suvera already has a `um_source_category_1` taxonomy (28 values). But only **42%** of waitlist contacts have any value, and **103 of those 125 are "Import"** — so usable signal is ~7%. |
| Is role analysis achievable? | **Yes.** `jobtitle` is 92% populated. Needs normalisation (~10 variants of "GP Partner"). |
| Can we join Notion meetings to practices? | **Yes with effort.** The `Practice` and `Partner Role` columns are inconsistently populated. Titles follow `"<Practice> — <Contact> (<Date>)"` and can be parsed; needs an edge-case list for PCN/group meetings. |
| Is engagement data available? | **Partially.** Calls / meetings / notes endpoints work with the current token. **Email endpoint returns 403** — needs `sales-email-read` scope added. |

---

## HubSpot — populated % across 295 waitlist contacts

| Property | Populated | % | Use |
|---|---:|---:|---|
| `lifecyclestage` | 295/295 | 100% | Stage classification |
| `hs_v2_date_entered_opportunity` | 291/295 | 98.6% | "Signed up" date proxy |
| `jobtitle` | 272/295 | 92.2% | Role analysis (needs normalisation) |
| `hs_v2_date_entered_lead` | 168/295 | 56.9% | Funnel timing |
| `um_lead_score` | 136/295 | 46.1% | Predictive signal |
| `hs_v2_date_entered_marketingqualifiedlead` | 127/295 | 43.1% | Funnel timing |
| `um_source_category_1` | 125/295 | 42.4% | **Source — but mostly "Import" (see below)** |
| `um_source_category_2` | 116/295 | 39.3% | Source detail (free text) |
| `hs_v2_date_entered_customer` | 115/295 | 39.0% | "Live" date proxy |
| `hs_v2_date_entered_salesqualifiedlead` | 29/295 | 9.8% | Funnel timing |
| `hs_lead_status` | 63/295 | 21.4% | Optional secondary |
| `nhs_partners_visit*` | 2/295 | 0.7% | Effectively unused — ignore |

### `um_source_category_1` value distribution

```
170  <empty>          ← 57.6% have no source at all
103  Import           ← 34.9% are bulk imports (not GTM-attributable)
  7  HubSpot User
  5  Email Extension
  4  Calculator
  3  Webinars
  2  Gated Content
  1  Other Integration
```

**Real GTM-attributable sources cover ~7% (22 of 295 contacts).** Everything else is empty or `Import`.

### `jobtitle` distribution (top, needs normalisation)

```
47  Practice Manager           ┐
 4  practice manager           │ → 51 PMs
32  GP Partner                 ┐
 9  GP Partner/Principal       │
 4  Managing Partner           │ → ~45 GP Partners
22  GP                         ┐
 5  Gp                         │
 3  gp                         │ → ~30 GPs
 8  Salaried GP
 4  Operations Manager
 4  Practice Business Manager
 4  Digital Transformation Lead
 3  Dr
```

Recommend normalisation buckets: `Practice Manager` / `GP Partner` / `Salaried GP` / `Operations` / `Digital/Transformation Lead` / `Other`.

### `lifecyclestage` distribution

```
277  opportunity              ← 94% — virtually everyone at Opportunity
 12  customer                 ← in waitlist list but already Customer (data hygiene)
  3  1709731041 (Inquiry)
  2  1962372335 (Ex-Customer)
  1  salesqualifiedlead
```

The HubSpot waitlist list 1535 is not 1:1 with the `waitlist_ods.json` set — it includes 12 Customers and 2 Ex-Customers. Pipeline should de-dupe against `live_customers.json`.

### Suvera-custom properties (relevant subset)

All defined in the `source_categories` and `analyticsinformation` property groups, all `hubspotDefined: false`:

- `um_source_category` (enum, 9): PPC, Organic, Events, Content Download, Direct Traffic, Other, Sales, Email Marketing, ABM
- `um_source_category_1` (enum, 28): Webinars, Gated Content Download, Form Submission, Google Search, LinkedIn, Facebook, Twitter, Contact Us, Guides & Resources, Case Studies, Conference, Round Table, On Demand Webinar, Email Extension, Import, Calculator, Other Integration, HubSpot User, + 10 more
- `um_source_category_2` (free text)
- `um_lead_score` (calculated)
- `nhs_partners_visit` + `_count` + `_date` — abandoned (0.7%)

### Lifecycle stage pipeline IDs

```
645749455   → None
1709731041  → Inquiry
701959416   → Disqualified
1962372335  → Ex-Customer
```

Plus standard: subscriber, lead, marketingqualifiedlead, salesqualifiedlead, opportunity, customer, evangelist, other.

The pipeline has full per-stage time-in / date-entered / date-exited tracking via `hs_v2_*` properties. **No need to infer stage timestamps from snapshots — they're in HubSpot already.**

---

## Notion Partner Meeting Library — audit

| Aspect | Observation |
|---|---|
| Schema | `Practice` (text), `Partner Role` (select), `Main Theme` (multi-select, 12 themes), `Opportunity Signal` (select H/M/L), `Attendees` (text), `Date`, `Fathom Recording` (url), `Meeting ID` (Fathom recording ID), `Status` (New/Reviewed/Actioned), `Meeting` (title) |
| Date range | Earliest results 2026-03-28, latest 2026-05-20. Roughly **~8 weeks of meeting data**. |
| Volume | 25+ rows in May alone; library is actively growing. Exact total not enumerated (Notion search caps at 25 per query). |
| Title pattern | `<Practice> — <Contact> (<Date>)` — reliable enough to parse |
| `Practice` populated | Inconsistent. Newer rows (e.g. Elm Tree Apr 20) have it; older rows (Clapham Apr 16) leave it empty. Sample suggests ~50-70% populated. |
| `Partner Role` populated | Same pattern — inconsistent. |
| `Main Theme` populated | Generally populated. Themes: Data Accuracy, Automation, SMS and Comms, Onboarding, SystmOne, Recall Workflow, QOF, Booking Links, Churn Risk, Upsell, Feature Request, Competitive Intel |
| `Opportunity Signal` populated | Generally populated. H/M/L. |
| Edge cases | Group meetings ("Suvera Planner group — Beech House + Parkview ..."), PCN demos ("Planner demo: North Devon Coastal PCN"), informal-format titles ("Will <> Sheikh") |

### Practice-name → ODS join strategy

1. Use `Practice` column where populated (exact match against `practices_geocoded.json:name`)
2. Fallback: regex parse title before first `" — "` separator; same exact-match
3. Fallback: fuzzy match (rapidfuzz ratio ≥ 90)
4. Edge cases (group / PCN / informal) logged to `scripts/.notion_unmatched.log` for manual reconciliation
5. Optionally: backfill `Practice` column going forward via the `process-meetings` skill so future joins are deterministic

---

## Engagement endpoint scope check

With the current token (`pat-eu1-d5c7008c-...`):

| Endpoint | Status |
|---|---|
| `/crm/v3/objects/calls/search` | ✅ Works |
| `/crm/v3/objects/meetings/search` | ✅ Works |
| `/crm/v3/objects/notes/search` | ✅ Works |
| `/crm/v3/objects/emails/search` | ❌ 403 — needs `sales-email-read` scope |

For the Clapham Family Practice sample (5 contacts), engagement counts were all 0 except 1 note on one contact — suggesting engagement records may be sparse OR the search filter syntax needs tuning. Worth re-verifying in Phase 1 with a known-active practice.

---

## Implications for the dashboard

### Source data is the bottleneck, not the dashboard

Of 295 waitlist contacts, **only ~22 have real attributable source data**. The other ~270 are either empty or "Import". This means:

- A "Sources" view built today would show one huge "Unknown" bucket and 6 tiny slivers
- That's actually useful — it surfaces the gap and motivates backfill
- But it can't yet answer "which source converts best to Live"

**Two strategy options to put to the user:**

1. **Build now, surface the gap.** Ship the dashboard with `Unknown` as a first-class category. The visualisation pressure motivates backfill. Pair with a CSV export of "contacts missing `um_source_category_1`" for the user to fill in via HubSpot history.

2. **Backfill first, then build.** Spend a focused day going through HubSpot contact history for the 270 contacts, set `um_source_category_1` properly, then build. Slower but the dashboard ships with real signal.

### Funnel timing is ready today

`hs_v2_date_entered_*` gives us real per-contact stage transitions. Combined with the stage IDs, we can produce: time-in-Inquiry, time-Lead-to-MQL, time-MQL-to-Opp, time-Opp-to-Customer, etc. — without snapshot inference.

### Role normalisation is mandatory

Without it, "GP Partner" and "GP Partner/Principal" and "Managing Partner" all show as separate slices. Propose a 6-bucket normaliser baked into `refresh_attribution.py`.

### Notion adds qualitative depth — but title-parsing is required

The Practice-column-empty rows can be salvaged by parsing the title. Worth investing in this since the meeting library is rich (themes + opportunity signal + role + Fathom URL).

---

## Outstanding token / scope items

1. **Email scope.** Add `sales-email-read` to the token's permissions so we can pull email engagements. Without it, "touches to convert" undercounts.
2. **Token rotation.** The token used here is in the conversation transcript. Rotate before this repo goes public.
3. **Notion API token.** For automated hourly refresh, we need a Notion integration token with read access to the Partner Meeting Library DB. The MCP works for ad-hoc but not for CI.
