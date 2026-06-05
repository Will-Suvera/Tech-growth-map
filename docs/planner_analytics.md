# Planner Funnel Analytics — diagnosis, data lineage & playbook

> **Purpose:** a single place to pick this project back up fast. Captures *where the
> Planner SaaS funnel is stalling*, how every number was derived, the data sources,
> the scripts to reproduce it, open questions, and the B2B SaaS conversion playbook.
>
> **Last updated:** 2026-06-03 · **Owner:** Will Gao (will@suvera.co.uk)

---

## TL;DR — where it's stalling

Path to revenue today: **281 waitlisted → 19 live (6.8%) → 7 actively recalling (2.5%) → 0 paying (0%)**.

The funnel is **leaky, not slow** — every sales step takes 0.6–2.9 days median — with **one** slow, leaky step that is the real problem:

1. 🔴 **DPA Signed → Live: 36% convert, ~7 weeks (50d median, max 112d).** The worst *and* slowest step. Won deals (signed DPA) leak during onboarding. **EHR-independent** (identical 36% for EMIS-only), so it's a genuine implementation problem, not a data artifact. Friction = the EMIS integration chain: EMIS Notified → IM1 user → patient data sync → appt config.
2. 🟠 **Live → actually recalling: only ~7 of 19 live practices recall in a given month** (21 ever this FY). Ghost activation — practices go live but don't use it.
3. 🟠 **Nobody pays.** £0 ARR; nobody on the paid money-back tier despite live Freemium/VC users.
4. 🟡 **Demo → DPA Signed loses ~half** (mid-funnel close); ~20 deals die specifically at "DPA Sent" (proposal out, never signed — likely DPA/data-governance friction).

### Where to spend the most time (recommendation, 2026-06-03)
**Fix the bottom of the funnel, not the top.** The top is the healthiest part (fast, 54–93% steps); the constraint is `DPA Signed → Live`. Ranked:
1. 🥇 **DPA Signed → Live → first recall (time-to-value).** Biggest + slowest + most *controllable* leak (internal EMIS integration chain), and **33 won deals are parked here right now**. Converting them ~doubles the live base with zero new sales. Target: 7wk→2–3wk, 36%→~70%.
2. 🥈 **Live → habitual recalling (activation).** 7/19 active → creates reference-able, monetisable customers.
3. 🥉 **Build the money-back monetisation motion.** £0 is a *missing motion*, not a leak; build it for the value-proven cohort.
- ⚡ Cheap win: recover the ~20 deals dying at "DPA Sent" (DPA friction). ⬇️ Deprioritise pure top-of-funnel volume.
- Rationale: revenue chain is `paying ⟸ recalling ⟸ live`; FY volume concentrates in ~23 practices → **depth > breadth**.

---

## The funnel (HubSpot "Planner (SaaS) Onboarding" pipeline `3277290730`)

281 deals total. Stages, *ever-reached* (cumulative), blended vs addressable EMIS-only:

| Stage | Blended (all EHR) | EMIS-only (addressable) | Median time in prev. step |
|---|---|---|---|
| Waitlist | 281 | 160 | — |
| Demo Booked | 126 · 45% | 87 · **54%** | 2.7d |
| Demo Held | 115 · 91% | 81 · 93% | 2.9d |
| DPA Sent | 78 · 68% | 63 · 78% | 0.6d |
| DPA Signed | 53 · 68% | 39 · 62% | 1.8d |
| **Live** | **19 · 36%** | **14 · 36%** | **49.6d** ⬅ |
| **End-to-end** | **6.8%** | **8.8%** | |

### EHR correction (important)
Suvera only onboards **EMIS** today; **SystmOne/TPP = "not yet onboarding"** (parked, not stalled).

- EHR mix of 281 deals: **EMIS 160 (57%) · SystmOne 85 (30%) · Unknown 34 (12%) · Medicus 2**.
- Of the **105 deals stuck in "Waitlist"**: **58 are SystmOne (parked latent demand)**, only **26 EMIS (actionable)**, 19 Unknown, 2 Medicus.
- Stripping non-EMIS lifts Waitlist→Demo from 45% → **54%** and end-to-end from 6.8% → **8.8%**.
- **The DPA→Live 36% does NOT move** with the EHR filter → proven genuine bottleneck.
- **TPP status (confirmed):** the 3 "Live SystmOne" + 7 signed are **intentional early pilots** — TPP isn't generally supported yet, these are deliberate pilots. So SystmOne in the waitlist is genuinely parked, not stalled. 12% of deals still have no `ehr_type`.
- **Business case for TPP support:** 85 SystmOne deals (58 waitlisted) = captured demand. Treat as a **roadmap bet** (prove pilots → unlock 85 deals), separate from funnel optimisation.

### Velocity & stalls
- All sales steps fast (median 0.6–2.9d). **Only DPA Signed → Live is slow (50d median).**
- Currently parked: **33 deals in "DPA Signed"** (21 >30d, 10 >60d, oldest 133d); 105 in Waitlist (mostly TPP).

### Drop-outs
- **86 dropped (HubSpot)** / 75 "Dropped Out" (sheet). By furthest stage: **56 Waitlist** (never demoed), **20 DPA Sent** (proposal, never signed), 6 Demo Held, 2 each Demo Booked / DPA Signed.
- **76 of 86 drops are EMIS** — the real losses are EMIS practices; SystmOne mostly just sits parked (only 4 dropped).
- ⚠️ Drop timing Apr 19 → May 42 → Jun 21 looks like a **stale-waitlist cleanup**, not real-time churn.

### Go-live history (HubSpot `Live` stage-entry timestamps)
19 SaaS-pipeline go-lives — matches the sheet's 19 "Live" exactly. By month: Jan 1, Mar 2, **Apr 8, May 0, Jun 8**.
⚠️ The 8 June go-lives were all stamped 1–2 Jun with 41–112d DPA→Live gaps → almost certainly a **bulk HubSpot stage catch-up**, so `Live` timestamps may lag true go-live. (VC tab has a separate 16 "Live" on a different pipeline/motion.)

---

## Data sources & lineage

| Signal | Source | How it's read |
|---|---|---|
| Sales/onboarding funnel + stage-entry timestamps | HubSpot deal pipeline `3277290730` (EU1, account `143576889`) | `hs_v2_date_entered_<stageId>` per deal; pulled via `scripts/pull_planner_funnel.py` → `outputs/planner_deals.json` |
| EHR per practice | HubSpot deal `ehr_type` (EMIS / SystmOne / Medicus) | same pull |
| Live / onboarding status | Google Sheet onboarding tracker (**read-only published CSV**) | SaaS tab `gid=0` (ODS col G, Status col I, EHR col), VC tab `gid=993386637` |
| Recalls + bloods (the FY metric) | Omni → daily Google Sheet export → `public/data/recalls.json` | `recalls.total`, `recalls.monthly`, `recalls.fy_by_practice` (FY Apr→Mar), `active_ods_this_month`, `active_ods_recent` |
| Tiers | `public/data/practice_tiers.json` | Freemium / VC / Money-back |

### Stage IDs (pipeline `3277290730`) — IDs stable, labels live from HubSpot
`4489053409` **Signed-up List** → `5147362520` Demo Booked → `5017986288` Demo Held → `4489053410` DPA Sent → `4489053411` **DPA Signed Onboard Ready** → `4487571659` **Full Functionality Live** · (`4527836370` Dropped Out)

Labels were renamed in HubSpot on 2026-06-04. The pipeline is **rename-resilient**: all logic keys off stable internal keys + stage IDs, and display labels are fetched live (`GET /crm/v3/pipelines/deals/3277290730`) by `pull_planner_funnel.py` → carried through `stage_order` → `funnel_board.json` → `FunnelBoard.jsx`. Future renames flow through with zero code change.

### How "recalls" were counted
The figures reported are **practice counts** (how many practices recall), not recall *volume*.
- "7 recalling this month" = `active_ods_this_month`; "21 this FY" = of 23 in `active_ods_recent`, 21 are in the Live set.
- **Volumes:** recalls — all-time 6,533 / FY-to-date 5,653 (23 practices) / June 189. Bloods — all-time 3,917 / FY-to-date 3,844 (21 practices). Monthly recall ramp: Apr 1,363 → May 4,118 → Jun 189. Heavily concentrated in ~23 practices.
- `query_crm_data` (HubSpot SQL) is blocked (missing `reporting-base-read` scope) — use `search_crm_objects` + local compute.

---

## Reproduce it

```bash
python3 scripts/pull_planner_funnel.py        # HubSpot Planner deals + stage timeline -> outputs/planner_deals.json
python3 scripts/analyze_planner_funnel.py     # conversion, velocity, stalls, drop-outs
python3 scripts/analyze_by_ehr.py             # EHR-segmented (addressable EMIS) funnel
python3 scripts/funnel_livedates_and_sheet.py # go-live dates + drop-outs + read-only sheet cross-check
python3 scripts/build_funnel_board.py         # build the Funnel Movement board data (funnel_board.json)
```

---

## The Funnel Movement board (the dashboard)

The `attribution-dashboard` was reworked (2026-06-03) into a **single vertical funnel** —
"what's moving, what's stuck" — replacing the old multi-section layout (old components kept
on disk in `src/components/`, no longer rendered; `App.jsx` now renders only `FunnelBoard.jsx`).

**Run it:** `cd attribution-dashboard && npm run dev` → http://localhost:5174

**What it shows:** each pipeline stage as a band (Waitlist → … → Live → Recalling), with overall
step-conversion ribbons, a one-line insight + action per stage, and a red "stale" flag. Click a band
to expand its deals: Practice · days-in-stage · **next step** (✅ visit/meeting + date or ❌ none) ·
**why it's stuck** · owner. Stale-with-nothing-booked rows pin to the top in red. EHR chips filter
EMIS / TPP / Unknown. Top strip: # act-now · # next-step-booked · # ghosts.

Each conversion shows a **week-on-week Δ** (▲/▼ pts), reconstructed from stage-entry timestamps — no
stored history needed; a "📅 Week-by-week" toggle opens a full per-step conversion table (last 6 weeks).
**Click any deal** to expand a dropdown: source · time-in-each-stage · list size · ICB · PCN · recalls/month. Rows are colour-coded: **red** = stale/ghost, **green** = recalling.

**Data:** `scripts/build_funnel_board.py` → `attribution-dashboard/public/data/funnel_board.json`,
joining `outputs/planner_deals.json` (stage + days-in-stage + EHR) + `attribution.json` (Notion visit,
tier, pcn) + `recalls.json` + a live pull of deal→company→ODS and future HubSpot meetings.

**Daily sync:** `.github/workflows/refresh-funnel-board.yml` rebuilds `funnel_board.json` every day at
06:30 UTC (re-pull deals → rebuild) and commits it. `recalls.json` is already refreshed every 5 min by
`refresh-waitlist.yml`; `attribution.json` (source / ICB / Notion visits) only refreshes on a manual
run, so add `refresh_attribution.py` to the job if you want those daily too. Manual rebuild anytime:
`python3 scripts/build_funnel_board.py`.

**Definitions / caveats:**
- **"Next step booked"** = a future Notion *Practice Visit* OR a future HubSpot meeting (OR currently in Demo-Booked stage).
- **"Recalling / activated"** = recalled at all **this FY** (not just this calendar month — else top recallers like Fernlea get mislabelled ghosts in early-FY months). Live rows show **FY-to-date recalls · % of list · avg/month since April** (avg over months actually recalled, so a slow current month doesn't dilute it) and are tinted green; ghosts show "0 recalls this FY". **% of list** = FY recalls ÷ list size — the size-normalised penetration metric. The Live stage is **sorted by colour shade**: rows are graded green by % of list (deepest = highest penetration), fading down through light green and white (just-live) to red stale ghosts at the bottom. Each Live row also shows **automated pathology (bloods) this FY + % of list** next to recalls (e.g. Fernlea `1,103 recalls (9.1%) · 814 bloods (6.7%)`). The expand dropdown adds a recalls-by-month table (each month's % of list) plus FY pathology total + % — `bloods` has no per-practice monthly feed (`fy_by_practice` only), so it's FY-only. The Live/Recalling stages **drop the "next step" column** (irrelevant post-funnel) and show **status badges**: 🏆 >1,000 recalls this FY, plus tier (Freemium / MBG / VC). The dropdown also shows **this-month recalls + bloods (live traction)** and a **small per-practice bar graph of recalls/month** with the current month highlighted (always shown even at 0, so a quiet month reads as a drop). Per-practice `this_month` comes from `recalls.json` `fy_by_practice[ods].this_month`.

### Onboard-ready checklist (DPA Signed is NOT one step)
"DPA Signed Onboard Ready" is a 10-step implementation checklist pulled live (read-only) from the onboarding Google Sheet SaaS tab: EMIS Notified · IM1 User created · Sharing agreement accepted · Patient Data Sync · Practice on dashboard · HeroHealth · Onboarding Call · Appt Config · Recall Session · Bloods automation. Each step is `done` (e.g. "Yes"/"Held"/"Done"/"Uploaded"/"Set up") / `pending` (any other non-empty value — "Booked"/"Sent"/"To do"/"Needs upload") / `todo` (blank). DPA-Signed rows show a mini progress bar + `N/10` + **"next: <first incomplete step>"** (the actual blocker); the dropdown shows the full chip checklist. Matched by ODS in `scripts/build_funnel_board.py` (`load_onboarding_steps`). Insight: the long-stuck deals (130+ days) are nearly all blocked at **IM1 User created = "To do"** — the integration step.

### "Needs a chase" worklist (top of page) + last-email column
A red **chase panel** pins above the funnel: won/near-won deals that have gone stale (stages demo_held / dpa_sent / dpa_signed with no next step booked), oldest-first, showing practice · stage · days stalled · **blocker** (for DPA-Signed: the first incomplete onboarding step) · **days since last email** (red >14d) · owner. Computed as `needs_chase` in `build_funnel_board.py`. Every non-live deal row also has a **Last email** column (days-since, red past 14 days; muted "—" when unknown). Insight at launch: the chase list is topped by DPA-signed deals stuck 100–136 days, almost all **blocked at IM1 User created**, several not emailed in 70–87 days.

### Last email per deal
The dropdown shows the **last HubSpot email** (subject · date · sent/received) for each deal. Source: deal→email associations + email metadata. ⚠️ The CI Private App token currently lacks `sales-email-read` (build logs a 403 and falls back to `outputs/deal_last_email.json`, a sidecar populated via the connected HubSpot app). **Add `sales-email-read` to the Private App** and the daily build pulls last-email for every deal automatically (`pull_last_emails` in `build_funnel_board.py`).
- **Stale thresholds:** Waitlist 30d · Demo Held 14d · DPA Sent 10d · DPA Signed 21d · Live 21d (no recall).
- **deal→ODS coverage ≈ 148/196** — gaps are HubSpot companies missing `ods_unique`/`practice_code`; those deals still show but lack visit/recall/owner enrichment.
- The funnel is **deal-pipeline-based** (19 Planner-pipeline Live deals), distinct from the 37 live ODS in `live_customers.json` (which includes VC-tab practices on a separate motion).

---

## Open questions / data caveats

1. ~~**TPP rule** — is SystmOne truly "not yet onboarding"?~~ **Resolved:** the 3 Live + 7 signed SystmOne are intentional **early pilots**; TPP not generally supported. Waitlisted SystmOne is genuinely parked.
2. **Unknown EHR (34 deals, 12%)** — cross-fill from the sheet's EHR column + "EMIS number" to tighten the addressable figure.
3. **Slack DPA dates** — `#planner-onboarding-alerts` has more accurate DPA-signed dates than HubSpot. No Slack connector in-session; **paste to re-run DPA→Live velocity** (the June batch likely inflates the 7-week figure).
4. **VC vs SaaS** — 16 VC "Live" sit on a separate pipeline/motion (bundled, no per-patient fee); not in the 281 SaaS deals.

---

## Playbook — B2B SaaS conversion tactics (research-backed)

_Generated by the 13-agent `planner-conversion-playbook` research workflow on 2026-06-03; every benchmark was independently fact-checked and unverifiable stats dropped. Run ID `wf_6283c9f0-863`._

*Decision-ready. Every play is tied to Suvera's real numbers (EMIS-only addressable funnel = 160 deals): Waitlist 160 → Demo Booked 87 (54%) → Demo Held 81 (93%) → DPA Sent 63 (78%) → DPA Signed 39 (62%) → Live 14 (36%). End-to-end 8.8%. Of 19 live practices, only ~7 recalled this month / 21 this FY. £0 ARR; nobody on the paid money-back tier.*

---

## 1. TL;DR — the 4 plays that matter most

Ranked by impact on Suvera's actual leaks. The two biggest leaks are **DPA-Signed→Live** (worst conversion *and* slowest) and **Live→recalling** (ghost activation). The revenue blocker is that nobody pays.

1. **Turn "DPA Signed → Live" into a time-boxed implementation project with a hard SLA and a named owner, and pre-start the NHS IT plumbing *before* signature.** This is the single worst number versus benchmark (36% convert, ~50-day median, 33 deals stuck). Assign one implementation owner within 48h of signature; run a dated mutual action plan; start the IM1 integration-user request on day 1; go live read-only on a minimum data set. **If you move 36% → 60%, ~9 of the 33 stuck deals become Live — roughly +64% on today's 14-practice live base, with zero new top-of-funnel spend.**

2. **Redefine "Live" as "first recall batch sent," not "switched on" — and white-glove every practice to that event.** Going live closes the implementation ticket; it does not deliver value or predict retention. Today only ~7 of 19 live practices recall (~37% true activation). Never let a practice "go live" without a booked session where they send their first real recall cohort *with* a Suvera CSM on the call; alert the owner if no recall fires within 7–14 days. Recover even half the ~12 ghost practices and you roughly double the actively-recalling base.

3. **Fix activation first, then convert the activated few to the paid money-back tier via a PQL motion — that is the only path off £0 ARR.** You cannot charge a practice that has never felt the value. Gate the paid pitch on a reached value moment (e.g. "first 100 recalls sent + first bloods automated"). Treat an activated practice approaching its free cap as a Product-Qualified Lead and route it to a human who *celebrates the milestone* and presents the money-back guarantee. The ~7 actively-recalling practices are your monetization-ready cohort **today**.

4. **Close the DPA-Sent→Signed leak (~20 lost deals) with a self-serve IG/Data-Governance pack, multi-threading, and e-signature + 24h follow-up.** NHS practices legally require an Article 28 DPA and a DSPT check before they can sign — pre-answer that checklist so their IG lead can say yes in days, engage the actual approver (not just the demo attendee), and treat the DPA like a hot proposal. 62% sent→signed is roughly at par, but ~20 stalled proposals are the second-largest absolute leak after onboarding.

---

## 2. Benchmark scorecard

| Funnel step | Suvera's number | Industry par (cited) | Verdict |
|---|---|---|---|
| Waitlist → Demo Booked | 54% (87/160) | Lead→MQL ~41%, MQL→SQL ~39% (The Digital Bloom 2025, $10M–$100M ARR) | **Ahead** of typical lead-progression marks |
| Demo Booked → Demo Held | 93% (81/87) | No-shows are a meaningful tax; 90%+ show is excellent | **Ahead / at par** |
| Demo Held → DPA Sent | 78% (63/81) | Demo-to-close SaaS ~30%; this is an interim "proposal-out" step, not a close | **At/above par** for the interim step |
| DPA Sent → DPA Signed | 62% (39/63) | Opportunity-to-close ~39% (The Digital Bloom); proposal/contract stage | **At par** (but ~20 lost deals = 2nd-biggest absolute leak) |
| DPA Signed → Live | 36% (14/39) | Onboard.io target Days-to-Launch ~7 days; mid-market 30–45 days "healthy" DTL (Onboard.io); negotiation→close/provisioning = 35–40% of enterprise cycle (Optifai, N=939) | **Below par** — worst + slowest number |
| Onboarding time (signed→live) | ~50-day median, max 112d | ~7-day target DTL (Onboard.io); median B2B sales cycle 84 days *end-to-end* (Optifai) | **Far below par** (one step eats ~50 of 84 typical days) |
| Live → actually recalling (activation) | ~37% (7/19) | Cross-SaaS avg 37.5% / median 37%; **sales-led 41.6%**; "good" = 60th pctile (Userpilot, N=62 B2B) | **At median, below the sales-led bar** — and activation *is* the product value |
| Freemium/VC → paid | 0% (£0 ARR) | Freemium self-serve good 3–5%; **sales-assist good 5–7%** (Lenny's / OpenView / Pendo, 1,000+ products) | **Below the floor** |
| End-to-end | 8.8% | Closed-won healthy ~6–9% (The Digital Bloom) | At par on the headline — *but masks the two structural leaks above* |

**Read of the scorecard:** the top of funnel is healthy and should be left alone. The losses concentrate in **DPA-Signed→Live** (below par) and **Live→recalling** (at-median but value-critical), with **0% paid** as the revenue blocker. Note also: ~56 of the waitlist non-converters are the parked **SystmOne** practices Suvera can't yet serve — that "drop" is a product-coverage gap, not a sales failure, and shouldn't count against the 54%.

---

## 3. Per-bottleneck plays (priority order)

### (a) DPA Signed → Live: onboarding & time-to-value *(the #1 leak: 36%, ~50-day median, 33 stuck)*

**Play A1 — Set a hard implementation SLA ("21 days from DPA-signed to first recall") and write it into the DPA.**
- *Tactic:* Replace "we'll go live when IT is ready" with a published, contractual time-to-live target. Run two clocks: Days-to-Launch (from signature) and a faster Time-to-First-Value ending at the first recall batch. Put "21 days to first recall (14 for EMIS-ready practices)" on the DPA cover note and report every stuck deal's day-count weekly; anything past 21 days escalates.
- *Why it works:* Open-ended timelines have no forcing function, so "DPA Signed" becomes a parking lot. A named date makes it a project — and because the SLA is visible to the practice, the practice's own staff start chasing their EMIS/IM1 admin instead of Suvera chasing alone.
- *Evidence:* Onboard.io: self-serve TTV <7 days is excellent, **mid-market SaaS 30–45 days Days-to-Launch is "healthy," enterprise-with-integrations 60–90 days**, and the principle that **TTV should be shorter than DTL**. *(Onboard.io — Onboarding Metrics: Days to Launch & Time to Value.)* Suvera's ~50-day median sits in the slow tail of even mid-market.
- **Apply to Suvera:** Add a "days-since-DPA" clock column to the HubSpot Planner SaaS Onboarding pipeline. Moving 36% → 60% converts ~9 of the 33 stuck deals into Live (14 → ~23 live, +64%) with no new lead spend.

**Play A2 — Assign one named Implementation Owner per signed practice within 48 hours.**
- *Tactic:* The moment a DPA is signed, auto-assign a single named owner (not the AE who closed it). They send a personal intro, book the kickoff within 48h, run the whole EHR-notified → IM1-user-created → data-sync → appointment-config → go-live chain, and own that practice's "days-since-DPA" metric.
- *Why it works:* Without an owner, an IM1 request that bounces between Suvera, the practice manager and the EMIS admin has no one accountable for the 7-week median — it just sits.
- *Evidence:* Appcues: Calendly **"saw significantly higher activation on enterprise accounts after assigning a dedicated onboarding specialist within two days of signup."** Onramp: **62% of CS/onboarding leaders still lack real-time visibility into onboarding progress** (survey of 161 leaders). *(Appcues — How to shorten time to value; Onramp — Top Customer Onboarding Metrics.)*
- **Apply to Suvera:** With only ~33 stuck + 14 live, one full-time implementation owner can white-glove the entire backlog. Make DPA-signature in HubSpot trigger an instant owner assignment + 48h kickoff task. White-glove is affordable precisely because Suvera is early.

**Play A3 — Run a dated mutual action plan, and parallelise the NHS IT dependency from day 1 (ideally pre-signature).**
- *Tactic:* At kickoff, walk the practice through a shared, dated plan over the 5 onboarding steps, each with an owner (Suvera vs practice vs EMIS/IM1) and a target date. Sequence steps in **parallel**: start the IM1 integration-user request on day 1 (the slow, third-party-gated step) while doing appointment config alongside. Better still, pre-start IM1 + data-sync scoping during the **DPA-Sent** phase (63 deals) so that on the day a DPA is signed, go-live is days away, not weeks.
- *Why it works:* Suvera's velocity data shows every step is fast (0.6–2.9 days) *except* the one gated by external NHS IT. You can't speed up EMIS/IM1 itself — you remove it from the critical path by starting it earlier. A dated plan surfaces the IT dependency as a tracked task with a name against it.
- *Evidence:* SanoWorks (Epic EHR): hospital/IT approval is **4–16 weeks, "the phase founders most underestimate… not in your control"** — so it must be started first and tracked. Optifai (N=939): the negotiation-to-close / **post-agreement provisioning stage is 35–40% of total enterprise cycle time.** Gainsight's onboarding-template guidance: define objectives, clearly assign who handles each aspect on both sides, and set realistic milestone timeframes. *(SanoWorks — Epic EHR Integration Timeline & Cost; Optifai — Sales Cycle Length Benchmark; Gainsight — Customer Onboarding Template.)*
- **Apply to Suvera:** Build one templated mutual action plan for the EMIS→Planner path with the 5 named steps. Make IM1 provisioning Day-1 Step-1, started at DPA-Sent. Tracking which step the 33 stuck deals sit in will reveal whether the 50-day median is one bad step (likely IM1) or death-by-a-thousand-cuts.

**Play A4 — Strip IT dependencies out of the critical path: go live read-only on a minimum data set, defer the rest.**
- *Tactic:* Define "minimum-viable-live" for EMIS = whatever is needed to fire the **first recall batch** (read-only patient list + recall send). Defer pathology/bloods write-back, full appointment config and edge-case data mapping to a "phase 2" after first value. Pre-stage everything that doesn't need the practice (compliance docs, IM1 request template, config defaults) before kickoff.
- *Why it works:* In health-tech integration, scope creep ("pulling 15+ data types instead of the minimum viable set") is a named time-killer; the fix is read-only-first, then add write capability later. Shrinking the integration surface that has to be approved before go-live directly attacks the ~50-day median.
- *Evidence:* SanoWorks: accelerators include **"starting with read-only access before adding write capabilities," "limiting scope to a defined minimum data set," and "completing security compliance work pre-integration"**; pulling 15+ data types on a first integration is a named mistake. *(SanoWorks — Epic EHR Integration Timeline & Cost.)*
- **Apply to Suvera:** Pre-build the IM1-integration-user request as a one-click template the practice manager forwards to their admin, so Suvera isn't drafting it per-deal. Phase pathology write-back to after first recall.

**Play A5 — Move repeatable onboarding to a 1:many cohort go-live with persona quick-starts.**
- *Tactic:* Batch newly-DPA-signed practices into a weekly "Planner go-live cohort." Move repeatable steps (training, "how to send your first recall," appointment-config walkthrough) into a recurring 1:many webinar plus three one-page persona quick-starts: practice manager (owns IM1/config), recalling nurse/admin (sends recalls = the value event), GP (sign-off). Reserve scarce 1:1 owner time for the genuinely bespoke part — the IM1/EMIS integration.
- *Why it works:* A closely-analogous digital-health SaaS for SMB health practices **cut onboarding time 67% (90 → 30 days) and lifted team productivity ~60%** by (a) reducing touchpoints, (b) switching 1:1 training to a 1:many webinar, and (c) building persona-based training — while fighting a churn surge (6.7% → 14.2%), directly relevant to Suvera's ghost-activation risk. *(ESG Success — Case Study: Transforming Onboarding for Digital Health SMB Practices.)*
- **Apply to Suvera:** Capped cohorts also let the team batch IM1/data-sync per cohort instead of 33 one-off fire drills — and the cap doubles as honest scarcity for the waitlist (see play D3).

**Play A6 — Instrument a 6-step onboarding checklist and report stuck-step visibility weekly.**
- *Tactic:* Add a 6-step checklist as HubSpot deal properties inside "DPA Signed": EHR notified | IM1 user created | data synced | appointments configured | go-live | **first recall sent**. Auto-flag any of the 33 stuck deals with no step movement in 7 days.
- *Why it works:* A visible per-step view puts Suvera ahead of the 62% of CS teams with no real-time onboarding visibility, and tells you whether the 50-day median is one bad step or many. Checklist completion is also a leading paid-conversion signal.
- *Evidence:* Userpilot TTV Benchmark Report (547 SaaS companies): Sked Social users who completed the onboarding checklist were **3x more likely to upgrade to paid**; The Room saw a **75% increase in activation within 10 days**; Attention Insight a **47% activation increase** over six months. Onramp: **62% of CS teams lack real-time onboarding visibility.** *(Userpilot — Time-to-Value Benchmark Report 2024/2025; Onramp — Top Customer Onboarding Metrics.)*
- **Apply to Suvera:** A practice that has completed the checklist *and* is actively recalling is the only credible candidate to later convert to the paid money-back tier — so this checklist double-serves problem (e) below.

---

### (b) Live → actively recalling: activation & adoption *(the ghost-activation gap: ~37%, 7 of 19)*

**Play B1 — Make the activation/aha metric an outcome event: "recalls sent," measured as a habit, not "switched on."**
- *Tactic:* Stop counting a practice as activated at go-live. Define the activation event as the first batch of recalls actually **sent to patients** (ideally first pathology form auto-generated), instrument it server-side, and report it as the headline number — replacing "Live = 19." Set the habit threshold as **"recalled in 3 of the last 4 weeks,"** not "recalled once." Surface "recalling this month" as the primary live tier off `recalls.json`.
- *Why it works:* The #1 activation mistake is counting *setup* as value delivered. Going live is setup; a recall reaching a patient is value. Measuring the wrong event hides the zombie-account problem.
- *Evidence:* Elena Verna: **"90% of the monetization and retention issues stem from incorrect activation"**; prescribes measuring habit as **"active 3 out of last 4 weeks."** Amplitude (2025 Product Benchmark, 2,600+ companies): products with strong early (7-day) activation correlate strongly with strong 3-month retention, and **>98% of users churn within two weeks if they haven't experienced value.** *(Elena Verna — "I bet you are doing product activation all wrong"; Amplitude — Time to Value Drives User Retention.)*
- **Apply to Suvera:** Reframe the end state: of 19 live, 7 are activated, ~12 are ghost. Re-running the funnel on this definition makes end-to-end conversion *worse* than the headline 8.8% — that's the real story to manage to.

**Play B2 — Make the first recall a scheduled, white-glove "go-live + send" event, not a self-serve handoff.**
- *Tactic:* Never let a practice "go live" without a booked 30-minute session where the CSM sits with them and they send their **first real recall cohort together on the call.** Pick a small, safe, high-yield register (one chronic-disease cohort they care about most) so they see patients booked / bloods triggered the same week. Make the session a gate to "done," not an optional follow-up; pre-fill it with a short discovery form to tailor which register to recall first.
- *Why it works:* Suvera goes live but 12 of 19 never recall — a classic "dropped into the product" failure. Staging the aha on a call beats hoping they reach it alone.
- *Evidence:* First Round / Superhuman: **65%+ of customers fully transitioned with human-led onboarding — "more than double" self-serve**; when onboarding was made optional, attendance fell **from 100% to 15%.** Amplitude (Lindywell case): fixing the first 48 hours lifted **activation +47% and 3-month retention +45.6%.** *(First Round Review — Superhuman Onboarding Playbook; Amplitude — Time to Value Drives User Retention.)*
- **Apply to Suvera:** With ~14–19 live practices, white-glove is entirely affordable (Superhuman ran it at thousands/week). Target moving the 37% recall rate toward the 60–65% Superhuman-style band.

**Play B3 — Set a 14-day "first recall sent" SLA with a per-practice TTV countdown and day-7 escalation.**
- *Tactic:* Every newly-live practice must send its first real recall within 14 days of go-live. Track time-to-first-recall per practice with a visible countdown; trigger CSM escalation at day 7 if no recall has fired. Treat day-14-no-recall as a red health flag equal to churn risk.
- *Why it works:* The value window is brutally short, and for implementation-heavy B2B the danger zone is exactly where accounts go dormant — so compress first-*value* (the recall) separately from go-live.
- *Evidence:* Amplitude: **>98% of users churn within two weeks without a value moment; up to 91% drop off within 14 days**; activation falls Day1 21% → Day7 12% → Day14 9% (90th percentile). Count.co: B2B enterprise time-to-first-value is **2–8 weeks** (the danger zone to compress). *(Amplitude — Time to Value Drives User Retention; Count.co — Time to First Value.)*
- **Apply to Suvera:** Track this on the dashboard next to "recalling this month," off `recalls.json` — it turns the abstract ghost problem into a weekly operational countdown.

**Play B4 — Recruit a clinical "Planner champion" (volunteer, not appointed) inside each live practice.**
- *Tactic:* For each live practice, identify and equip ONE internal champion — ideally a recall/admin lead or practice nurse who **volunteers** rather than being assigned. Give them a one-page "why this is safer for patients" framing, a standing monthly nudge, and a direct CSM line. Have them run the recall send and explain *why* to colleagues. Avoid a top-down appointed, reluctant owner.
- *Why it works:* This is a near-perfect EHR analogue, and adoption is socially transmitted by an engaged insider, not by vendor docs.
- *Evidence:* NCBI super-user study: the unit with **volunteer, proactive super-users scored 3.25 vs 2.58 proficiency (p=0.003) despite having FEWER super-users (6 of 42 staff vs 9 of 48)**; effective behaviours were proactivity, explaining *why*, and a "safer for patients" framing. The appointed super-user's reaction: *"I'm not wearing that thing!"* *(NCBI PMC — How clinician "super users" influence others during EHR implementation.)*
- **Apply to Suvera:** Suvera's buyer (partner/PM) is often not the daily user. At go-live, explicitly ask *"who WANTS to own recalls here?"* and back that volunteer — the cheapest lever to convert the ~12 ghosts.

**Play B5 — Build a 90-day habit ladder: weekly recall cadence + monthly outcome scorecard.**
- *Tactic:* After the first recall, install a recurring trigger so recalls become a ritual: a standing recall schedule per chronic-disease register, a weekly "recalls due" nudge to the champion, and a monthly one-page outcome scorecard ("X patients recalled, Y bloods automated, Z hours saved") tied to QOF / FY targets. Get the champion to verbally commit to a fixed monthly recall slot.
- *Why it works:* Activation only completes when a habit forms at the product's natural frequency; the aha→habit transition must be designed, not assumed.
- *Evidence:* Elena Verna: habit = **"active 3 of last 4 weeks."** Superhuman: customers **"verbally committed to using Superhuman daily for 30 days."** *(Elena Verna; First Round Review — Superhuman Onboarding Playbook.)* *(SaaSFactor's "fewer than 40% transition aha→habit" is directional content-marketing color only.)*
- **Apply to Suvera:** Recalls are inherently recurring (chronic-disease reviews run year-round; the UK FY Apr→Mar recall/bloods target is THE metric) — a natural weekly/monthly-habit product, but only if Suvera installs the cadence.

**Play B6 — Triage the ~12 ghost practices by WHY they're dormant, then run matched reactivation plays.**
- *Tactic:* Don't blast all ghosts with one "come back" email. Triage into (a) **never-activated** (went live, never recalled — likely most of Suvera's ghosts), (b) **activated-then-drifted**, (c) **external blocker** (staff turnover, IT issue, no champion). For (a) run the white-glove "send your first recall with us" call; for (b) send a behaviour-specific nudge referencing their last recall plus an outcome stat; for (c) fix the blocker or re-identify a champion. Survey: "what would need to be different for recalls to be worth your time?"
- *Why it works:* Matching the campaign to the specific dormancy reason is what separates a working reactivation program from a failed broadcast.
- *Evidence:* Userpilot: three dormancy segments need different interventions; behaviour-specific subject lines lifted opens from **~18% baseline to ~31%**; land users on last saved work, not an empty dashboard. *(Userpilot — Re-engage Inactive Users in SaaS.)*
- **Apply to Suvera:** The ~12 ghosts of 19 live are the most winnable pool — already integrated, no new sales/DPA needed. Suvera can read recall counts in `recalls.json` to triage. Reviving even half would roughly double the 7 actively-recalling practices.

**Play B7 — Activate at the practice/team level (2–3 seats live) before calling it "Live."**
- *Tactic:* Make multi-user activation part of the go-live definition: at least 2–3 staff (recall lead + nurse + practice manager) have logged in, can run a recall, and have seen the outcome — so a single departure doesn't silently kill usage.
- *Why it works:* Single-user activation is fragile; in high-turnover clinical settings, single-champion dependence is a known failure mode.
- *Evidence:* Elena Verna: B2B activation must occur **at the team level, not the individual user level** — "distributed collaboration matters more than siloed individual engagement." Reinforced by the NCBI study's finding that broad info-sharing beat support concentrated on a few people. *(Elena Verna — B2B Activation.)*
- **Apply to Suvera:** Pair with the volunteer-champion play plus one backup, to harden the 7 currently-recalling practices against relapse.

---

### (c) Demo → DPA Signed: close + DPA/data-governance friction *(2nd-biggest leak: ~20 lost at "DPA Sent")*

**Play C1 — Ship a self-serve "Data Governance Pack" / Trust Center so DPA review starts on day 1, not week 3.**
- *Tactic:* Build one downloadable pack / always-current web page holding: Suvera's current-year DSPT submission, a pre-filled DPIA template, the standard UK-GDPR Article 28 DPA (with non-negotiable clauses flagged), Cyber Essentials / ISO 27001 evidence, the sub-processor list, and a one-page "what data we touch and where it lives" summary. Link it inside the demo follow-up and the DPA email so the practice's IG lead can validate trust without waiting on Suvera.
- *Why it works:* NHS controllers are *required* to hold a legally binding Article 28 agreement and to check supplier DSPT status before contracting — so the buyer's IG checklist is knowable in advance and can be pre-answered. Enterprise/regulated deals stall because buyers can't validate trust quickly enough; a self-serve trust center collapses the questionnaire round-trips.
- *Evidence:* NHS England Digital DSPT Guide 10: NHS controllers must hold a UK-GDPR **Article 28 agreement** and **review supplier DSPT status** before contracting, with ISO 27001 / Cyber Essentials acting as procurement shortcuts. Directional: proactively supplied security/legal packages shorten procurement cycles by roughly 2–3 weeks. *(NHS England Digital — DSPT Guide 10: Your suppliers and contracts; Ciphrix — Why Enterprise Deals Stall at Security Review.)*
- **Apply to Suvera:** Reusable across all 160 EMIS deals and ready for the 58 parked SystmOne practices later. If pre-supplied IG artefacts move DPA-Sent→Signed from 62% toward 75%, that's ~8 more signed deals from the current 63 sent.

**Play C2 — Run a shared mutual action plan (MAP) from demo through go-live.**
- *Tactic:* At the end of every demo, co-create a one-page MAP listing every step from "DPA review" through "EHR notified → IM1 user → data sync → appointment config → first recall sent," each with an owner (practice vs Suvera), a target date, and the success criterion ("first recall batch sent"). Make "go-live" explicitly mean *recalls actually sent.* Share it as a living doc both sides update.
- *Why it works:* MAPs create shared accountability and surface the hidden internal blockers (IG lead, IT, EHR admin) before they silently stall a deal — directly attacking "no-decision" losses, the dominant B2B failure mode.
- *Evidence:* Outreach: deals using a mutual action plan have a **26% higher win rate.** Forrester State of Business Buying 2024: **86% of B2B purchases stall** during the buying process (81% of buyers dissatisfied with the chosen provider). *(Outreach — Mutual Action Plans; Forrester — The State of Business Buying 2024.)*
- **Apply to Suvera:** Apply to the 33 stuck DPA-Signed deals and the 81 demos held. A MAP naming the EHR/IM1 steps with dates attacks the 50-day median directly; a 26% relative lift on the demo→live chain (81 demos → 14 live) is several extra live practices per cohort.

**Play C3 — Multi-thread: engage the Practice Manager AND the IG/IT contact before sending the DPA.**
- *Tactic:* Stage-gate it: no DPA goes out until you have a second named contact — specifically the person who owns information governance / IT integration at the practice or PCN. Ask in the demo: *"Who signs off data sharing here, and can we add them to the next email?"* Send the Data Governance Pack to that person directly; for PCN-level deals, thread the PCN manager too.
- *Why it works:* DPA sign-off in a GP practice is rarely the demo attendee's decision — it routes to a PM, an IG lead, sometimes the PCN. If only one person is engaged, the deal dies the moment the DPA hits an internal inbox nobody owns.
- *Evidence:* Forecastio (via ORM): deals with **3+ stakeholders engaged close at 68% vs 23% single-threaded.** Gong (1.8M opportunities): won deals carry ~2x the buyer contacts of lost (~8 email contacts won vs ~3 lost) and multi-threading boosts win rate ~130% on deals over $50K; Aviso: ~42% win-rate lift from multi-threaded conversations. Gartner: complex B2B buying groups average 6–10 stakeholders. *(ORM Tech — Sales Cycle Length Guide, citing Forecastio 2024; Gong; Aviso.)*
- **Apply to Suvera:** The ~20 deals lost at "DPA Sent" are prime single-threading suspects. Cheap to operationalise: one extra qualifying question in the demo + a CC on the follow-up.

**Play C4 — Treat the DPA like a hot proposal: e-signature, view-tracking, and 24-hour follow-up.**
- *Tactic:* Send the DPA via an e-signature tool with view-tracking. The moment it's opened, the AE follows up within 24 hours ("saw you opened it — happy to jump on a 10-min call with your IG lead to walk through the Article 28 clauses"). Set a fixed cadence of 4–5 touches over 2–3 weeks across email + phone; pre-fill the practice's details so there's nothing to draft.
- *Why it works:* Signed agreements are won fast or not at all; the longer a DPA sits, the lower the odds. Proactive follow-up and frictionless signing convert deals that would otherwise drift into "no decision."
- *Evidence:* Proposify (State of Proposals): e-signature makes a proposal **3.4x more likely to close and ~33% faster**; **~43% of won proposals close within 24 hours of opening**; proposals followed up within 24 hours **win 2x more.** *(Proposify — State of Proposals.)*
- **Apply to Suvera:** Lowest-effort, highest-leverage fix in the funnel. With e-sign (3.4x) and tracked 24h follow-up (2x on followed-up proposals), DPA-Sent→Signed should move well above 62%; even +13pts recovers ~8 of the lost deals per 63 sent.

**Play C5 — Pre-package the DPA: standard template, flagged non-negotiables, pre-approved fallback positions.**
- *Tactic:* Maintain one standard Suvera DPA with clearly-marked non-negotiables and pre-approved positions on the 4–5 points NHS IG leads always raise (sub-processors, data location/residency, breach-notification window, retention/deletion, processor-not-controller status), plus a documented escalation path. When a practice pushes its own data-protection addendum, respond same-day with a redline instead of routing to a lawyer and losing a week.
- *Why it works:* A weak or slow DPA is itself a deal-killer in regulated buying: the buyer's compliance team will demand weeks of revisions or reject the product. Pre-approved positions turn a multi-week legal loop into a same-day exchange.
- *Evidence:* Consistent with the verified NHS Article 28 requirement (above); standard-template-plus-documented-non-negotiables is the recognised fix when a customer pushes their own DPA template. *(Contract Nerds — How to Negotiate a DPA When the Customer Pushes Their Template; NHS England Digital — DSPT Guide 10.)*
- **Apply to Suvera:** Applies to the slowest of the 63 DPA-Sent deals — the ones forwarded to a practice's own IG/legal contact. Pre-approved fallbacks keep them moving instead of joining the ~20 that never sign.

**Play C6 — Reframe the offer as a time-boxed "recall pilot" with a written success criterion.**
- *Tactic:* Instead of "sign up free," pitch a fixed 6–8 week pilot with one agreed success metric defined with the practice upfront (e.g. "send X chronic-disease recalls and automate Y blood-test forms in the first 6 weeks"). Put the named end-date and metric in the MAP. The DPA becomes "the paperwork to start the pilot we already agreed," not a fresh hurdle — and the pilot's end-date is the natural moment to convert to the paid money-back tier.
- *Why it works:* Structured pilots with explicit success criteria convert far better than open-ended free access because both sides agree in advance what "working" looks like — which also pre-empts ghost activation.
- *Evidence:* Structured pilots convert at **~40–60% vs <10% for open-ended free trials** in enterprise software (directional; attributed to a McKinsey 2023 study), with a fixed 6–8 week timeframe recommended. *(GetMonetizely — How to Structure Enterprise Pilot Program Pricing.)*
- **Apply to Suvera:** Bakes "first recalls sent" into the pilot success criterion before go-live (attacking ghost activation), and the fixed end-date bridges to the paid money-back tier.

---

### (d) Waitlist → Demo (EMIS) + handling the parked TPP demand *(healthy step — protect it; ~56 lost mostly = SystmOne coverage gap)*

**Play D1 — Put a sub-5-minute speed-to-lead SLA on every new EMIS waitlist sign-up.**
- *Tactic:* Treat a fresh EMIS-eligible sign-up as a high-intent inbound. Auto-route to the rep within 5 minutes with a templated "book your demo" message + embedded scheduling link, and trigger an outbound call/text the same hour. Write the SLA down (respond <5 min in working hours, <1 hr overnight) — a documented SLA is what makes teams hit it.
- *Why it works:* Speed-to-lead is the single highest-leverage conversion lever in B2B SaaS and almost everyone fails it, so it's cheap differentiation.
- *Evidence:* Optifai (939 B2B SaaS companies, Q2'25–Q1'26): leads contacted in **<5 min close at 32% vs 12% for 24h+ (2.6x).** Blazeo 2026 (573 companies): teams with a formal SLA hit the 15-min standard **54.9% of the time vs 29.5% without**; only ~23% of B2B SaaS firms respond within 5 min. The famous **21x-qualify / 100x-connect / –80%-after-5-min** figures are the MIT/Oldroyd Lead Response Management study (2007). *(DigitalApplied — Speed-to-Lead Benchmarks 2026.)*
- **Apply to Suvera:** The 54% waitlist→demo rate likely hides a follow-up-speed problem. First step: measure Suvera's current median response time on a new sign-up; if it's hours/days, this is the cheapest available win. (Top of funnel is already at/above par, so this is "protect and tune," not "rebuild.")

**Play D2 — Run a 3–5 touch, segmented waitlist nurture sequence built for the 30-day decay window.**
- *Tactic:* For any EMIS sign-up who doesn't book on first contact, run a short sequence (3–5 messages over ~2–3 weeks), one clear CTA each (the scheduling link), segmented by practice attributes (list size, ICB, recall backlog). Add "days since waitlist join" as a field and trigger at day 2/5/12/21 before the lead goes cold.
- *Why it works:* Single emails get ignored and waitlist intent has a short half-life.
- *Evidence:* ScaleMath: digital-product waitlists convert **~50% if members are activated within one month, dropping below 20% past three months.** (Treat as directional industry assertion.) *(ScaleMath — What Is A Good Waitlist Conversion Rate?)*
- **Apply to Suvera:** Of the ~56 lost at waitlist, many are simply aging out past the 30-day window without structured follow-up. Recovering even 20–30% = +11 to +17 demos. (Note: some of these 56 are SystmOne — route those to play D5, not this sequence.)

**Play D3 — Frame demos as limited monthly onboarding cohorts (turn the 7-week onboarding constraint into honest scarcity).**
- *Tactic:* Repackage the waitlist as capped monthly go-live cohorts: "We onboard ~N EMIS practices per cohort; the [Month] cohort has X spots left — book a demo to claim one." Use a visible "spots claimed" indicator in nurture emails.
- *Why it works:* Unlimited supply kills urgency; a credible cap forces a decision now. This is operationally *true* for Suvera (the DPA-Signed→Live step already takes ~7 weeks, so you literally cannot onboard everyone at once), and capped cohorts smooth the onboarding load.
- *Evidence:* Stormy AI SaaS Waitlist Playbook: Cleo capped its first cohort at 500 users and the cap "drove thousands of signups." *(Stormy AI — The SaaS Waitlist Playbook.)* Evidence is consumer/pre-launch, so confidence is low for NHS B2B.
- **Apply to Suvera:** Keep on operational merit, not on the cited evidence. **Test on one ICB first.** Does double duty: a real reason to book a demo now, *and* lets onboarding batch the technical steps per cohort instead of 33 one-off fire drills.

**Play D4 — Re-engage the aging/lost waitlist (~56 never-demoed) with a quarterly one-line reactivation sequence.**
- *Tactic:* Build a reactivation list of EMIS practices that went cold without a demo. Send a short 2–3 step sequence — one-line, plain-text, from the original rep (~9 words: "Is automating chronic-disease recalls still a priority for [Practice]?"). Trigger at 60–90 days since last contact; refresh quarterly with a new local proof point (a new nearby live practice, or "we recalled N patients across [ICB] this quarter").
- *Why it works:* Reactivating existing leads is far cheaper than net-new acquisition; short, personal, single-question emails from the original owner outperform branded blasts; 60–90 days is the documented sweet spot.
- *Evidence:* Mixmax: a "good" reactivation rate is **8–15%**; optimal re-engagement window **60–90 days**; reactivation **~5x cheaper** than new acquisition; use a 3–5 step sequence over 2–3 weeks. (8–15% and 5x are uncited heuristics — directional.) *(Mixmax — Re-Engagement Email Templates for Stale Leads.)*
- **Apply to Suvera:** At 8–15% on the ~56 EMIS lost-at-waitlist deals, that's ~4–8 recovered conversations — nearly free, reusing existing local-proof assets.

**Play D5 — Add a lightweight EMIS-fit qualifier on the waitlist form so reps spend speed on bookable demos.**
- *Tactic:* Add 2–3 self-qualifying questions at sign-up: EHR (EMIS / SystmOne / other), practice list size, approximate recall backlog. Auto-route EMIS into the 5-min fast lane; auto-route SystmOne into the parked-demand track (play D6). Keep qualification light (BANT/SPICED "need + timing"), not enterprise MEDDIC, for a short-cycle per-practice tool.
- *Why it works:* Structured-but-light qualification stops reps burning fast-response capacity on practices the product can't serve.
- *Evidence:* Nimitai (350+ B2B sales calls): deals with structured first-call qualification closed at **3.2x** the rate of straight-to-pitch deals. (Single practitioner's proprietary dataset — directional.) Framework guidance: BANT/SPICED for high-velocity/SMB, MEDDIC for enterprise. *(Nimitai — Sales Qualification Frameworks for B2B SaaS 2026.)*
- **Apply to Suvera:** Keeps the 5-min fast lane focused on the ~160 EMIS-bookable practices (protecting the 93% demo-held rate) while routing SystmOne cleanly. Capturing recall-backlog at sign-up arms the rep's first touch with a personalised hook ("you noted N patients overdue a review").

**Play D6 — Lead every demo invite with a named, LOCAL live-recalling reference practice.**
- *Tactic:* Don't sell features in the booking message — sell the local peer. Reference a real named practice nearby already live and recalling on Planner ("X Surgery in [their ICB] sent N recalls last month") and offer "happy to connect you with them." You already have the data (live + recalling practices, the geocoded map). Use ICB / same-PCN framing.
- *Why it works:* GP practices are conservative, risk-averse, peer-driven buyers; a verifiable local peer doing the thing is the strongest de-risking signal.
- *Evidence:* TrustRadius 2025 Buyer Research: **77% of B2B tech buyers consult user reviews**, and peer/prior experience are the most influential resources. *(TrustRadius 2025 Buyer Research Report.)* *(Note: earlier "+41% conversion" Edelman-B2B figures were dropped as unverifiable.)*
- **Apply to Suvera:** Suvera has ~7 practices recalling this month / 21 this FY plus a geocoded map — enough for a credible local reference in most ICBs. Build the reference list once: it also fixes the Live→recalling problem (play B4) and the DPA pack (play C1).

**Play D7 — Treat the ~58 parked SystmOne practices as a managed pre-launch waitlist, not dead leads.**
- *Tactic:* Give SystmOne sign-ups an explicit, honest status ("Planner doesn't support SystmOne yet — you're on the priority list, we'll notify you the moment it's ready"). Keep them warm as a demand panel: quarterly progress notes, plus a one-time survey on recall pain, list size and willingness to pay. Use the count itself as a roadmap/prioritisation signal and an external "demand is real" proof point. When TPP support ships, convert them as a scarcity-framed launch cohort (play D3).
- *Why it works:* A waitlist for an unsupported segment is a demand-validation and pre-sell asset — *provided* you set honest expectations and keep nurturing. SystmOne/TPP is the second-largest GP EHR in England, so this latent pool is structurally large.
- *Evidence:* Waitlists for not-yet-available products work as demand-shaping research panels; warm, surveyed segments convert far above cold lists. *(GetWaitlist — Waitlist Marketing Strategy 2025.)* Specific "40% faster / 60% higher conversion" figures are uncited vendor claims — use directionally only.
- **Apply to Suvera:** ~58 SystmOne practices = a ~36% expansion of the addressable funnel (160 → ~218) before any new marketing. Frame TPP integration spend against this concrete, already-captured demand. **Do not count these in the 54% waitlist→demo rate** — they make it look artificially low; the gap is product coverage, not sales.

---

### (e) Freemium / VC → paid money-back tier *(the revenue blocker: £0 ARR, nobody on paid)*

**Play E1 — Keep the value metric as "patients recalled," set the free cap on the same unit, and scale free→paid ~20x.**
- *Tactic:* Suvera's £0.75/patient money-back tier is already a usage/value metric — operationalise it as the explicit upgrade axis. Set the Freemium cap on the SAME unit you charge on (patients recalled per period), so free is a smaller dose of the exact thing paid sells more of. Publish a simple ladder: Free = up to N recalls/quarter; Paid money-back = unlimited recalls + bloods at £0.75/patient. Avoid bolting on seat- or feature-based pricing. Aim for ~20x spread smallest-to-largest account for expansion headroom.
- *Why it works:* A metric that rises as the customer succeeds expands revenue with no sales touch.
- *Evidence:* ProfitWell / Patrick Campbell (~5,000 companies): value-metric pricers **grow ~2x faster, with ~half the churn and ~2x the expansion revenue** vs flat/feature pricing; **multiple value metrics add ~30% growth**; recommended **20x spread**. OpenView (2,200 companies): **39% of companies now charge on usage**; value-based pricing adoption rises from 35% (<$5k deals) to 51% (>$100k). *(ProfitWell — Benchmarks for Value-Metric Pricing; OpenView — SaaS Pricing Insights.)*
- **Apply to Suvera:** Set the free cap on recalls (e.g. ~250 recalls/quarter) so a typical 8,000-patient practice running a full chronic-disease cycle blows past it and the paid tier is the only way to finish the job. At £0.75/patient, an 8k-patient practice recalling ~2,000 chronic patients/year ≈ ~£1,500 ARR; migrating the 14 Live alone could seed ~£20k ARR, with the 39 DPA-Signed deals as the real pipeline.

**Play E2 — Fix ghost activation first: gate the paid pitch on a reached value moment; re-activate dormant Live practices before any upsell.**
- *Tactic:* Do NOT pitch the paid tier to a practice that hasn't hit its value moment (first successful recall batch + first bloods automated). Make **"first 100 recalls sent successfully"** the trigger that flips a Live practice from "onboarded" to "activated." Only activated practices enter the monetization motion; the rest go to the re-activation queue (play B6), not the upsell queue.
- *Why it works:* Pricing on a value metric only works if the customer actually experiences the value — otherwise there's nothing to charge against, and you'd burn the guarantee's credibility.
- *Evidence:* ProductLed (600+ companies, Feb 2025): **activations are tracked only 34% of the time** across PLG companies despite being the prime value-signal — so instrumenting it is a cheap edge. The value moment being the highest-converting upgrade opportunity is standard PLG doctrine. *(ProductLed — PLG Benchmarks.)*
- **Apply to Suvera:** Of the live practices, only ~7 recalled this month / 21 this FY. The ~7 active practices are your monetization-ready cohort NOW; the ~12 Live-but-dormant are a re-activation queue. Track activation in the dashboard alongside the `recalls.json` bloods key.

**Play E3 — Instrument the recall-cap as the upgrade trigger with an in-context prompt at ~80% usage.**
- *Tactic:* When an activated Freemium practice crosses ~80% of its free recall cap, fire an in-product banner tied to the work they're mid-flow on: "You've recalled 200 of your 250 free patients this quarter. 1,400 of your diabetes/CVD patients are still due a review — upgrade to recall all of them, money-back guaranteed." Pair the in-app trigger with an email to the practice manager. Make the *locked action* (recalling the next cohort) surface the prompt, not a generic "upgrade" button.
- *Why it works:* Usage-cap / "locked feature clicked" moments are the highest-signal upgrade events because the prompt lands exactly when the value need is live.
- *Evidence:* Usage-approaching-limit prompts are a recognised core conversion lever ("You're using 4 of your 5 free dashboards…"). *(Kinde — freemium-to-premium guide.)* *(Note: specific 3.4x / 2.1x / –67% figures from a content-mill source were dropped as unverifiable.)*
- **Apply to Suvera:** Set the free cap so an active 8k-patient practice predictably hits 80% mid-quarter. Wire the trigger off `recalls.json` counts. Target the ~7 currently-recalling practices first — they hit the cap fastest and are the warmest paid candidates.

**Play E4 — Use Product-Qualified Leads (PQLs) to convert PLG into sales-assist — recall volume IS the buying signal.**
- *Tactic:* Treat a Freemium/VC practice that (a) has activated, (b) recalls consistently, and (c) is approaching/over the free cap as a PQL, and route it to a human for the upgrade conversation rather than self-serve checkout (NHS practices rarely self-purchase). The rep *celebrates the milestone* ("you've recalled 1,000 patients and automated 300 bloods this quarter") and presents the money-back offer — not a cold pitch.
- *Why it works:* The buying signal (recall volume) is observable in-product, and the buyer needs human help to clear DPA/procurement — exactly the hybrid motion that fits Suvera. PQLs are underexploited (only ~24% of PLG firms use them).
- *Evidence:* ProductLed (600+ companies, Feb 2025): PQLs lift free-account conversion **~3x vs the 9% baseline**; conversion reaches **30% at $1k–$5k ACV and 39% at $5k–$10k ACV**; only **~24% of PLG firms use PQLs.** Hybrid PLG+sales-led companies hit NRR targets more often (**67% vs 58% pure-PLG**, OpenView 2024). *(ProductLed — PLG Benchmarks; OpenView 2024 SaaS Benchmarks.)*
- **Apply to Suvera:** Add a PQL stage to the HubSpot Planner SaaS Onboarding pipeline, fed by dashboard recall data. Define PQL = activated Live practice ≥70% of free cap. The ~7 actively-recalling practices are PQLs today. At ~£1–2k ACV (the $1k–$5k band), PQL conversion runs ~30% — so even a handful is the realistic first paid revenue, without building self-serve billing.

**Play E5 — Lead with the money-back guarantee as the closing mechanism (it's your named tier — say it loud).**
- *Tactic:* Make the guarantee the headline of the paid offer, not the fine print: "Pay £0.75/patient. If Planner doesn't recall your outstanding chronic-disease patients and automate the bloods, you pay nothing." Tie a specific, measurable refund threshold (e.g. "X recalls sent + Y bloods automated within 90 days") so "doesn't deliver" is unambiguous. Use it as a closing device with a date ("start before end of quarter").
- *Why it works:* Risk reversal matters most in B2B because the buyer is risking their reputation; guarantees work best on higher-perceived-risk purchases — exactly a per-patient NHS commitment by a practice manager. Suvera already runs a free tier, so the guarantee is the right tool for the *paid* step (where the friction is commitment risk, not trying the product).
- *Evidence:* Quicksprout split test: a visible 30-day money-back guarantee lifted sales **+21%** at a 12% refund rate (net ~+6.5% monthly revenue); a free trial beat the guarantee on revenue by ~18% when both were offered. *(Quicksprout — Free Trial vs Money-Back Guarantee.)* This is a single, non-generalisable test — treat as a directional signal, not a benchmark.
- **Apply to Suvera:** The tier is literally "Money-back guarantee" at ~£0.75/patient, but it's never deployed at a measurable trigger. Define the refund threshold against `recalls.json` + bloods (e.g. "if we don't recall 80% of your due chronic patients in 90 days, full refund"). Present it at the PQL moment to the ~7 active practices. Budget for a ~10–15% refund rate; even net of refunds, this is the path from £0 to first revenue.

**Play E6 — Convert the VC-bundled cohort with a reverse-trial of full-planner features (loss aversion).**
- *Tactic:* For VC-bundled and Freemium practices that have activated, switch on the FULL paid experience (uncapped recalls + bloods, full-planner tier) for a fixed 30–60 day window, clearly framed as a trial. At the end, they either move to the £0.75/patient money-back tier or downgrade to the capped free tier and LOSE the ability to finish recalling their cohort. The downgrade — losing momentum on a half-finished recall cycle — is the conversion driver.
- *Why it works:* Loss aversion (~2x as motivating as gain) makes losing premium access the lever; ideal for already-engaged free users who've never had a reason to pay.
- *Evidence:* Reverse trials convert at **~7–21% vs ~3–7% for plain freemium** (OpenView); **Toggl doubled premium-plan revenue** after a 30-day reverse trial; Calendly/Airtable/Canva use the same mechanic. *(Inflection — Complete Guide to Reverse Trials, citing OpenView/Toggl.)* (OpenView's freemium baseline is sometimes quoted 3–15%, so don't overstate the delta.)
- **Apply to Suvera:** VC-bundled + Freemium active practices pay £0/patient today — the reverse-trial target. Turn on full-planner for 60 days for the activated ones, then require the money-back paid tier or downgrade-with-cap. Pair with the guarantee (E5) so the upgrade is both loss-framed and risk-reversed. Start with the ~7 recalling practices, then the re-activated ones.

**Play E7 — Price and message against demonstrated ROI (recalls + bloods = QOF/clinical value).**
- *Tactic:* Build a per-practice ROI/value receipt from the recall + bloods data: "This quarter Planner recalled X chronic patients and automated Y blood-test forms — equivalent to Z hours of clinical/admin time and contributing to QOF / long-term-condition targets." Use it (a) as activation proof before any upsell, (b) as the success measure baked into the money-back guarantee, and (c) as the expansion story.
- *Why it works:* Outcome/value framing is what justifies a per-patient price to a budget-holding practice manager — and outcome pricing works precisely where success is *clearly defined and measurable*, which "recalls sent" and "bloods automated" are.
- *Evidence:* L.E.K.: outcome-based pricing is viable where success is clearly defined/measurable (Riskified pays-per-approved-transaction; Intercom Fin at $0.99/resolution). *(L.E.K. Consulting — The Rise of Outcome-Based Pricing in SaaS.)* *(Note: "23% higher retention (HBR)" and "78% of CIOs (KLAS 2022)" figures were dropped as unverifiable.)*
- **Apply to Suvera:** Suvera's outcome is already counted in `recalls.json` — turn it into a per-practice ROI receipt surfaced in the dashboard. Keep charging per recalled patient (attribution is unambiguous, cleaner than pricing on downstream clinical outcomes) and use the receipt to justify it.

---

## 4. 30 / 60 / 90-day action plan

### Days 0–30 — Make the worst leak visible and stop the bleed (owner: **Head of CS / Ops** + **Sales lead**)
1. **Appoint one named Implementation Owner** and route every DPA-signature in HubSpot to an instant owner-assignment + 48h kickoff task. *(A2 — CS lead)*
2. **Add the onboarding checklist + "days-since-DPA" clock** to the Planner SaaS Onboarding pipeline (6 steps: EHR notified → IM1 → data synced → appts configured → go-live → **first recall sent**). Run the first weekly stuck-deal standup; triage all 33 stuck deals into which step they're sitting in. *(A1/A6 — Ops + CS)*
3. **Publish the implementation SLA ("21 days to first recall") and add it to the DPA cover note.** *(A1 — CS lead + founder)*
4. **Stand up the Data Governance Pack / Trust Center** (DSPT, Article 28 DPA with flagged non-negotiables, DPIA template, Cyber Essentials/ISO evidence, sub-processor list, data-flow one-pager) and link it in the demo recap + DPA email. *(C1/C5 — founder/IG owner)*
5. **Switch the DPA to e-signature with view-tracking; mandate 24h follow-up.** *(C4 — Sales lead)*
6. **Redefine "Live" internally as "first recall batch sent"; instrument it server-side off `recalls.json`** and start reporting "recalling this month / 3-of-4-weeks" as the headline number. *(B1/E2 — Ops/data)*
7. **Measure current median speed-to-lead** on new EMIS waitlist sign-ups; if it's hours/days, install the <5-min routing SLA. *(D1 — Sales lead)*

### Days 31–60 — Drive first value and recover stalled deals (owner: **CS** + **Sales**)
8. **Make "send your first recall with us" a mandatory white-glove go-live session**; alert the owner at day 7 if no recall has fired (14-day hard SLA). *(B2/B3 — CS)*
9. **Pre-start IM1 + data-sync at DPA-Sent**, run a dated mutual action plan from kickoff, and go live read-only on a minimum data set (defer pathology write-back to phase 2). *(A3/A4/C2 — Implementation Owner)*
10. **Triage the ~12 ghost practices** (never-activated / drifted / blocked) and run matched plays — white-glove call for never-activated, behaviour-specific nudge for drifted. *(B6 — CS)*
11. **Multi-thread every open deal**: no DPA goes out without the IG/IT approver engaged; CC them the Data Governance Pack. *(C3 — Sales)*
12. **Recruit a volunteer Planner champion per live practice** and require 2–3 active seats before declaring "Live." *(B4/B7 — CS)*
13. **Launch the segmented 3–5 touch waitlist nurture + the quarterly one-line reactivation sequence** for the ~56 EMIS non-bookers; tag the ~58 SystmOne practices into the parked-demand track with an honest status + WTP survey. *(D2/D4/D7 — Marketing/Sales)*
14. **Add the EMIS-fit qualifier to the waitlist form** (EHR / list size / recall backlog). *(D5 — Marketing/Ops)*

### Days 61–90 — Turn activated practices into first revenue (owner: **Founder/Commercial** + **CS**)
15. **Build the per-practice ROI/value receipt** from `recalls.json` + bloods and surface it on the dashboard. *(E7 — data/Ops)*
16. **Set the Freemium cap on recalls-per-quarter** and wire the ~80% in-context upgrade prompt + email-to-PM. *(E1/E3 — Product + Ops)*
17. **Add a PQL stage to HubSpot** (activated + ≥70% of cap) and route the ~7 actively-recalling practices to a human upgrade conversation that *celebrates the milestone* and presents the **money-back guarantee with a measurable 90-day threshold**. *(E4/E5 — Commercial)*
18. **Run a 60-day reverse-trial** of full-planner for the activated VC-bundled cohort; at expiry, require the paid tier or downgrade-with-cap. *(E6 — Commercial)*
19. **Pilot capped monthly go-live cohorts in one ICB** + the 1:many cohort webinar with three persona quick-starts; batch IM1/data-sync per cohort. *(A5/D3 — CS)*
20. **Build the SystmOne/TPP business case** off the ~58-practice parked demand for the product roadmap. *(D7 — Founder)*
21. **Lead demo invites with a named local live-recalling reference** (build the reference list once; reuse in the DPA pack). *(D6 — Marketing/Sales)*

**Target outcomes by day 90:** DPA-Signed→Live from 36% toward 60% (~9 of 33 stuck deals converted → ~23 live); first-recall-within-14-days SLA live; ghost practices halved (≈7 recalling → ≈12+); **first non-zero ARR** from 1–2 PQL'd, value-proven practices on the money-back tier.

---

## 5. Sources

- **Onboard.io — Onboarding Metrics: Days to Launch & Time to Value** — https://onboard.io/blog/onboarding-metrics-days-to-launch-time-to-value
- **Appcues — How to shorten time to value with better user onboarding** — https://www.appcues.com/blog/time-to-value
- **Onramp — Top Customer Onboarding Metrics to Prioritize** — https://onramp.us/blog/customer-onboarding-metrics
- **SanoWorks — Epic EHR Integration Timeline & Cost for Healthtech Startups** — https://www.sanoworks.com/blog/epic-ehr-integration-timeline-cost-for-healthtech-startups/
- **Gainsight — Customer Onboarding Template** — https://www.gainsight.com/blog/customer-onboarding-template/
- **Userpilot — Time-to-Value Benchmark Report (2024/2025)** — https://userpilot.com/blog/time-to-value-benchmark-report-2024/
- **Userpilot — User Activation Rate Benchmark Report 2024** — https://userpilot.com/blog/user-activation-rate-benchmark-report-2024/
- **Userpilot — Re-engage Inactive Users in SaaS** — https://userpilot.com/blog/reengage-inactive-users-saas/
- **ESG Success — Case Study: Transforming Onboarding for Digital Health SMB Practices** — https://esgsuccess.com/pillar/case-study-transforming-onboarding-for-enhanced-efficiency-improved-adoption-and-increased-retention/
- **Amplitude — Time to Value Drives User Retention (2025 Product Benchmark Report)** — https://amplitude.com/blog/time-to-value-drives-user-retention
- **First Round Review — Superhuman Onboarding Playbook** — https://review.firstround.com/superhuman-onboarding-playbook/
- **NCBI PMC — How clinician "super users" influence others during EHR implementation** — https://pmc.ncbi.nlm.nih.gov/articles/PMC4407776/
- **Elena Verna — "I bet you are doing product activation all wrong"** — https://www.elenaverna.com/p/hey-b2b-i-bet-you-are-measuring-activation
- **Count.co — Time to First Value metric** — https://count.co/metric/time-to-first-value
- **Outreach — How to improve win rates with a Mutual Action Plan** — https://www.outreach.ai/resources/blog/how-to-use-mutual-action-plans
- **Forrester — The State of Business Buying 2024** — https://www.forrester.com/press-newsroom/forrester-the-state-of-business-buying-2024/
- **ORM Tech — Sales Cycle Length Guide (citing Forecastio 2024)** — https://orm-tech.com/blog/sales-cycle-length-guide/
- **Proposify — State of Proposals** — https://www.proposify.com/state-of-proposals
- **Contract Nerds — How to Negotiate a DPA When the Customer Pushes Their Template** — https://contractnerds.com/negotiate-customer-data-protection-addendum-dpa/
- **GetMonetizely — How to Structure Enterprise Pilot Program Pricing** — https://www.getmonetizely.com/articles/how-to-structure-enterprise-pilot-program-pricing-effective-proof-of-concept-strategies
- **Ciphrix — Why Enterprise Deals Stall at Security Review** — https://ciphrix.com/blog/why-enterprise-deals-stall-at-security-review-and-how-to-prevent-it
- **NHS England Digital — DSPT Guide 10: Your suppliers and contracts** — https://digital.nhs.uk/cyber-and-data-security/guidance-and-assurance/data-security-and-protection-toolkit-assessment-guides/guide-10---accountable-suppliers/your-suppliers-and-contracts/
- **DigitalApplied — Speed-to-Lead Response Time Benchmarks 2026 (citing Optifai, Blazeo; MIT/Oldroyd 2007)** — https://www.digitalapplied.com/blog/speed-to-lead-response-time-benchmarks-2026-data-playbook
- **ScaleMath — What Is A Good Waitlist Conversion Rate?** — https://scalemath.com/blog/what-is-a-good-waitlist-conversion-rate/
- **Stormy AI — The SaaS Waitlist Playbook** — https://stormy.ai/blog/saas-waitlist-playbook-build-demand
- **Mixmax — Re-Engagement Email Templates for Stale Leads** — https://www.mixmax.com/blog/re-engagement-email-templates-stale-leads
- **Nimitai — Sales Qualification: BANT, MEDDIC & SPICED for B2B SaaS (2026)** — https://nimitai.com/blog/sales-qualification-framework
- **TrustRadius — 2025 Buyer Research Report** — https://www.trustradius.com/ (B2B Buying Disconnect / Buyer Research 2025)
- **GetWaitlist — Waitlist Marketing Strategy 2025: Build Demand Before Launch** — https://getwaitlist.com/blog/waitlist-marketing-strategy-2025-how-to-build-demand-before-launch
- **ProfitWell (Patrick Campbell) — Benchmarks for Value-Metric Pricing** — https://www.profitwell.com/benchmarks-for-value-metric-pricing
- **OpenView — SaaS Pricing Insights / 2024 SaaS Benchmarks** — https://openviewpartners.com/blog/saas-pricing-insights/
- **ProductLed — Product-Led Growth Benchmarks (600+ B2B SaaS, Feb 2025)** — https://productled.com/blog/product-led-growth-benchmarks
- **Lenny's Newsletter — What is a good free-to-paid conversion rate (OpenView/Pendo)** — https://www.lennysnewsletter.com/p/what-is-a-good-free-to-paid-conversion
- **Quicksprout — Free Trial vs Money-Back Guarantee split test** — https://www.quicksprout.com/what-converts-better-free-trial-versus-money-back-guarantee/
- **Inflection — Complete Guide to Reverse Trials (citing OpenView/Toggl)** — https://www.inflection.io/post/complete-guide-to-reverse-trials
- **L.E.K. Consulting — The Rise of Outcome-Based Pricing in SaaS** — https://www.lek.com/insights/tmt/us/ei/rise-outcome-based-pricing-saas-aligning-value-cost
- **Optifai — B2B SaaS Sales Cycle Length Benchmark 2025/26 (N=939)** — https://optif.ai/learn/questions/sales-cycle-length-benchmark/
- **Optifai — Demo-to-Close Conversion Rate Benchmark (N=939)** — https://optif.ai/learn/questions/demo-to-close-conversion-rate/
- **SaaS Mag — Time-to-Value: The New SaaS Retention Battleground (2026)** — https://www.saasmag.com/time-to-value-saas-onboarding-retention-2026/
- **The Digital Bloom — 2025 B2B SaaS Funnel Benchmarks ($10M–$100M ARR)** — https://www.thedigitalbloom.com/
- **Kinde — Freemium-to-premium conversion guide** — https://kinde.com/
