# Plan: Planner Growth Dashboard (v4 — Live-first storyline)

## Context

The v3 build (now live at `attribution-dashboard/`, port 5174) has the right data pipelines but the wrong information architecture. Reviewing it, the user concluded: the cards/funnel/hot-zones layout surfaces too many simultaneous threads. The dashboard needs to read like a top-down storyline:

> **Show me the Live cohort first. Then show me which of them are stalled, and why. Then middle-of-funnel. Then top-of-funnel. Strip everything else. Build from simplicity to complexity.**

This v4 plan keeps the entire data layer (pipelines, JSON outputs, refresh scripts) and rewrites only the home page. It also fixes one critical data-completeness gap that's blocking the user's primary metric.

**Hard constraint:** `src/` (the tech-growth map at port 5173) is a separate project. Not a single file in `src/` changes. We share data files in `public/data/` and HubSpot/Sheet connections; the dashboards live independently.

---

## Data fix (unblocks everything)

The user's primary metric is **per-practice FY-to-date recalls** (UK FY = Apr 1 → Mar 31). The v3 build acknowledged this as a known limitation because we thought the Omni feed only published current-month per-practice counts. **It doesn't — that's a parser limitation, not a data limitation.**

`scripts/refresh_data.py:884` (`_fetch_breakdown`) already reads a row-per-event CSV with `(month, practice_name, count)` triples. It accumulates per-practice counts for *all* months it sees in `by_month_practice`, but only emits per-practice rows for the months passed in `months` (default: current month only).

**Fix:** pass the FY-to-date month list as `months`, so `practices_by_month` contains every FY month. Then sum across months per practice to produce `recalls_fy_to_date` and `bloods_fy_to_date` per ODS.

Schema additions to `public/data/recalls.json`:

```jsonc
{
  "recalls": {
    "total": …,
    "monthly": { "2026-04": 632, … },              // existing
    "practices_this_month": [ … ],                  // existing
    "fy_by_practice": { "J82122": { "fy_to_date": 1240, "this_month": 287 }, … }  // NEW
  },
  "bloods": { … same shape … }
}
```

`compute_fy_metrics()` in `scripts/refresh_attribution.py` reads `fy_by_practice` to populate `recalls_fy_to_date` / `bloods_fy_to_date` / ratios with real values (today they're a current-month floor).

---

## Practice Visits — full Notion ingestion (schema confirmed)

Notion DB title is **"Practice Visits"** (not "Launch Visits"). Has three views:

- **Upcoming** — Status = `Confirmed`. Future visits scheduled.
- **Completed** — Status = `Completed`. Past visits that happened.
- **Table** — both, raw.

Columns (verified from screenshots):

| Notion column | Type | Used in dashboard |
|---|---|---|
| Status | select: `Confirmed` / `Completed` | maps to our `status`: `scheduled` / `happened` |
| Practice | text (free, e.g. "Bramblys Grange") | fuzzy-match to ODS via `practices_geocoded.json:name` |
| Date | date | `date` |
| Times | text (free, may be multi-line with travel slots) | shown verbatim in drilldown |
| Site Address | text | shown in drilldown |
| Attendees | person multi-select (e.g. Amy Wei-Krkoska, Caitlin Griffiths) | `attendees: [names]` |
| Problems | text (optional) | shown in drilldown as "blockers" — surfaces issues from past visits |

**File renames** (mechanical):
- `scripts/ingest_launch_visits.py` → `scripts/ingest_practice_visits.py`
- `notion_launch_visits.json` (sidecar) → `notion_practice_visits.json`
- `attribution-dashboard/public/data/launch_visits.json` → `practice_visits.json`
- Row field `practice_visit_status` keeps its name (still semantically correct), but Section 2's "Why?" heuristic now distinguishes:
  - `Confirmed` (scheduled) → "Intervention upcoming"
  - `Completed` (happened) AND no recalls → "Adoption blocker — investigate Problems field"
  - `none` → "Schedule a visit"

The Notion MCP pull happens in a Claude session (same pattern as `notion_meetings.json`). Sidecar must pull **both Upcoming and Completed views** so we have a full visit history per practice.

---

## Manual go-live date (new override field)

Per the user's brief: "Ideally we have a go-live date for them also. Something we can manually add."

- `manual_overrides.json` schema extended:
  ```json
  {"J82122": {"source": "…", "role": "…", "go_live_date": "2026-03-14", "notes": "…", "updated_at": "…"}}
  ```
- `scripts/override_server.js` already merges arbitrary keys → zero change there.
- `scripts/refresh_attribution.py` reads `go_live_date` from the override and surfaces `row.go_live_date`. Falls back to snapshot-derived `live_at` (the date the ODS first appeared in `live_customers.json` across `public/snapshots/*.json`) when no manual override exists.
- `PracticeDrilldown.jsx` override editor gains a date input.

---

## Inline Source editing (used in Sections 1 & 2)

Every practice row in the Live Cohort and Live-but-not-recalling tables displays the **Source** in an inline-editable dropdown. The dropdown options come from the canonical source taxonomy already used by `scripts/enrich_live_practices.py`:

- Webinar (registered)
- Webinar (attended)
- Event (attended)
- Content download
- Existing relationship (PCN / federation / current partners)
- LinkedIn
- Outbound (Suvera-sent)
- Notion meeting
- Unknown
- (free-text "Other…" option that opens a small input)

When changed, the dropdown POSTs `{ods, source}` to `scripts/override_server.js` (the existing endpoint). The server writes to `manual_overrides.json`, the row's `source_confidence` flips to `"manual"`, and the page updates optimistically. Next refresh of `attribution.json` picks it up permanently. A small pill on the dropdown shows the current confidence (`high` / `medium` / `low` / `manual` / `unknown`) so the user sees at a glance which sources need correcting.

This is a friction-reduction win — corrections take one click in the table instead of opening the drilldown's full override editor. The drilldown editor stays (for role + notes + go-live date), but Source can be fixed without leaving the list.

---

## The new home page (4 sections, top-down)

The Header (ARR / £/patient slider / tier mix / confirmed-only toggle) stays as-is. Below it, four stacked sections — no tabs.

### Section 1 — 🟢 Live Cohort

Single table, one row per Live practice (`stage ∈ {live_partial, live_full}`). Default sort: `recalls_fy_to_date` desc.

| Column | Source |
|---|---|
| Practice + ODS + ICB | attribution.json |
| Tier badge | practice_tiers.json |
| Go-live date | manual override → snapshot-derived `live_at` |
| Source (inline-editable) | attribution.json `source` + `source_confidence`; dropdown → POSTs to override server, confidence flips to `manual` |
| FY recalls | recalls.json `fy_by_practice` |
| FY pathology forms | recalls.json `bloods.fy_by_practice` |
| Recalls this month | recalls.json `practices_this_month` |
| Testimonial status | ✓ Passed / "N from 500" |
| Paid status | Freemium: "N to cap" + tiny bar (2000 cap) · VC: "Bundled" · Money-back: "Paying ✓" |
| Health bucket pill | `HealthBadge` — Healthy 🟢 / Near cap 🔥 / Testimonial-ready 🏆 / Expansion 💎 |

**Filter chip strip above the table** (Section-1 scope only): "All / Healthy / Near cap / Testimonial-ready / Expansion super-user". Clicking a chip narrows the table. Only positive-engagement buckets surface here; stalled buckets are the subject of Section 2.

Click any row → existing `PracticeDrilldown` modal.

### Section 2 — 🟠 Live but not recalling

Sub-table of Live practices where `recalls_fy_to_date == 0`. This is the strict "never activated this FY" cohort — what the user asked for.

| Column | Source |
|---|---|
| Practice + ODS | attribution.json |
| Tier | practice_tiers.json |
| Source (inline-editable) | dropdown; same edit path as Section 1 |
| Days since go-live | derived from go-live date |
| Practice visit | ✅ Completed (date) · 📅 Confirmed (date) · ❌ not logged |
| Problems (if past visit) | from Notion `Problems` column — shown inline when present |
| Likely cause | Completed visit → adoption blocker · Confirmed → intervention upcoming · none → schedule visit |
| Health bucket pill | Dormant 🔴 / VC paying-not-using ⚡ / Cadence dropping 🟠 |

**Filter chip strip above the table** (Section-2 scope only): "All / Dormant / VC paying-not-using / Cadence dropping". Stalled-bucket vocabulary only. The bucket pill + visit status together encode the diagnosis.

Click row → drilldown.

### Section 3 — 🟡 Middle of funnel

Three side-by-side panels, each a counter + a small list (≤10 rows visible, expand to see all). The Pre-live ⚪ Health bucket applies to all rows in this section, so we don't render a per-row pill here — the section header makes the pre-live context obvious.

1. **Booked practice visits** — practices with `practice_visit_status == "scheduled"` (Notion Status = `Confirmed`). Shows practice · visit date · attendees · `Times` field · `Problems` field if any pre-flagged.
2. **Signed DPA, no practice visit booked** — `stage == "onboarding"` AND `practice_visit_status == "none"`. Shows practice · days in onboarding (likely-in-progress).
3. **Signed up + meeting held + no DPA in 14 days+** — `stage == "signed_up"` AND `meeting_count > 0` AND `days_since_last_meeting >= 14`. Shows practice · last meeting date · days since.

### Section 4 — 🔵 Top of funnel — source of signed-ups

For `stage == "signed_up"` practices only: group by `source` field, count per source, render as a sorted horizontal bar list (count + percentage of waitlist total). Click a source → filtered list of those practices. (Pre-live ⚪ bucket implicit; not surfaced as a pill.)

---

## What's deleted

Frontend components — removed from `attribution-dashboard/src/components/`:
- `TheNumber.jsx`
- `DecisionCards.jsx`
- `HotZones.jsx`
- `Funnel.jsx`
- `PriorityList.jsx`
- `ChannelTable.jsx`

App-level cleanup:
- `App.jsx` — single tab (no more "Home" + "Channels"); just the four sections stacked.
- All tab navigation removed.

**Data pipelines are NOT deleted.** `scripts/decisions.py`, `scripts/compute_territory.py`, `scripts/score_practices.py` continue to run and write their JSONs. Cheap insurance — if a v5 wants those signals back, the data is there. Only the *views* are stripped.

---

## What stays

- All Python pipelines (`refresh_data.py`, `refresh_attribution.py`, `score_practices.py`, `compute_territory.py`, `decisions.py`, `ingest_launch_visits.py`)
- `scripts/override_server.js` (still drives the override editor)
- `ArrProgressHeader.jsx` (header)
- `HealthBadge.jsx` (used in drilldown)
- `PracticeDrilldown.jsx` (extended with go-live date input)
- `utils/funnel.js`, `utils/fy.js` (utilities)

---

## New components

| File | Section | Responsibility |
|---|---|---|
| `attribution-dashboard/src/components/LiveCohortTable.jsx` | 1 | All-live table with FY metrics + testimonial/paid status + scoped Health-bucket filter chips |
| `attribution-dashboard/src/components/LiveStalledTable.jsx` | 2 | Live with FY=0 + practice-visit cross-tab + Notion `Problems` surfacing |
| `attribution-dashboard/src/components/MofuPanels.jsx` | 3 | Three side-by-side panels (visits booked / no-visit / cold-post-demo) |
| `attribution-dashboard/src/components/TofuSources.jsx` | 4 | Source bar list for waitlist practices |
| `attribution-dashboard/src/components/PaidStatusCell.jsx` | shared | Inline "X from cap" / "Bundled" / "Paying ✓" cell used in Sections 1 & 2 |
| `attribution-dashboard/src/components/HealthBucketChips.jsx` | shared | Reusable filter chip strip — accepts a scoped bucket list per section |
| `attribution-dashboard/src/components/SourceDropdown.jsx` | shared | Inline-editable source select used by LiveCohortTable + LiveStalledTable; POSTs to override server, shows confidence pill |

---

## Critical files modified

**Backend (additive only):**
- `scripts/refresh_data.py` — `_fetch_breakdown` now keeps all FY months; `refresh_recalls` writes `fy_by_practice` to `recalls.json`. ~15 lines changed.
- `scripts/refresh_attribution.py` — `compute_fy_metrics()` reads new keys; `compose_practice()` adds `go_live_date` from overrides (falls back to snapshot-derived). ~30 lines changed.
- `scripts/override_server.js` — schema doc updated; the merge code already handles `go_live_date`.

**Frontend (rewritten):**
- `attribution-dashboard/src/App.jsx` — full rewrite; remove tabs; stack four section components.
- `attribution-dashboard/src/components/PracticeDrilldown.jsx` — add `<input type="date">` for go-live date in the override editor; display the go-live date (manual or snapshot) prominently in the header.

**Frontend (deleted):** see the "What's deleted" list above.

**Untouched:**
- `src/` (tech-growth map) — separate project, do not touch a single file.
- `scripts/refresh_data.py` 5-min `--waitlist` cron path — the new FY backfill only runs in the recalls-refresh path, which isn't called every 5 minutes anyway.
- Google Sheet (read-only).

---

## Refresh sequence (unchanged externally)

```bash
python3 scripts/refresh_data.py            # now writes fy_by_practice to recalls.json
python3 scripts/refresh_attribution.py     # uses real FY metrics + go_live_date override
python3 scripts/ingest_launch_visits.py    # if sidecar is populated via Notion MCP
python3 scripts/score_practices.py         # still runs (unused on home page in v4)
python3 scripts/compute_territory.py       # still runs (unused on home page in v4)
python3 scripts/decisions.py               # still runs (unused on home page in v4)
```

---

## Verification

Named-practice spot-checks (the same examples we validated for v3):

1. **Fernlea** — Section 1, top row. FY recalls now shows real cumulative (not just this-month=887). Testimonial = ✓ Passed. Paid status = "N to cap" with progress bar.
2. **Cape Hill** — Section 1. VC tier badge → Paid status = "Bundled". High FY recalls + forms.
3. **Chorlton, 168 Medical, Northwood, Robin Hood, West Barnes, Oak Leigh** — Section 2 (Live but not recalling). Each row shows practice-visit status; "Likely cause" column reads sensibly.
4. **Southborough, Voygar** — Section 1 if Live + non-zero FY recalls.
5. **Ashville** — depends on whether Feb-high/Mar-May-low sums to FY > 0; should appear in Section 1.

Functional invariants:

- Section 1 row count + Section 2 row count = total Live practices.
- Section 3 panel counts: practices_with_scheduled_visit + onboarding_without_visit ≤ total onboarding.
- Section 4 source counts sum to waitlist total (signed_up stage).
- Editing go-live date in drilldown → save → reload → date appears in Section 1 column and persists in `manual_overrides.json`.
- `recalls.json` after refresh contains `fy_by_practice` key with ODS → `{fy_to_date, this_month}` for both recalls and bloods.

---

## Open trade-offs (acknowledged)

1. **Practice Visits DB** is populated via Notion MCP in a Claude session — sidecar `notion_practice_visits.json` must include both `Confirmed` (Upcoming) and `Completed` views. Until populated, Section 2's practice-visit column reads "not logged" for everyone, and Section 3 panel 1 is empty.
2. **Money-back tier** is still empty by design (no practices on it). Header shows £0 actual / £x potential. When the first practice lands in Money-back, the Live Cohort row's Paid Status flips to "Paying ✓" automatically.
3. **Per-practice FY history** depends on the Omni CSV exposing date-stamped rows back to April. If the CSV only goes back N months, FY-to-date is truncated to N months — flagged in `compute_fy_metrics()` docstring; a one-time backfill from snapshots would close any gap (deferred to v5 if needed).
