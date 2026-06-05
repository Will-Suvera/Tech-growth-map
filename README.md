# Suvera — Growth & Primary Care Tech monorepo

Two independent front-end apps that share one Python data pipeline. They are
**decoupled on purpose**: working on one must never break the other.

```
.
├── apps/
│   ├── tech-growth-map/            # "Tech Growth Map" — Leaflet map of every England GP
│   │   ├── src/                    #   practice, colour-coded by sign-up/onboarding/live status
│   │   ├── public/data/            #   ← shared upstream data lives here (see Data contract)
│   │   ├── public/snapshots/       #   time-travel snapshots
│   │   └── vite.config.js          #   base '/Tech-growth-map/' → deployed to GitHub Pages
│   └── primary-care-tech-overview/ # "Primary Care Tech Overview" — Planner funnel/onboarding
│       ├── src/                    #   dashboard (stages, chase list, onboarding checklist,
│       └── public/data/            #   recall %, last-email). Its own derived JSON lives here.
├── pipeline/                       # shared Python data pipeline (+ override_server.js)
├── tests/                          # pytest/unittest suite for the pipeline
├── docs/                           # analysis + planning docs
└── .github/workflows/              # CI: data refresh + GitHub Pages deploy
```

## The two apps

| App | Dir | What it is | Hosting |
|---|---|---|---|
| **Tech Growth Map** | `apps/tech-growth-map/` | React + Leaflet map of ~6,400 England GP practices, colour-coded by pipeline status, with stats/sparklines/targets. | **Live** on GitHub Pages, rebuilt every ~5 min by `refresh-waitlist.yml`. |
| **Primary Care Tech Overview** | `apps/primary-care-tech-overview/` | React dashboard of the Planner sales→onboarding→live→recalling funnel: per-stage conversions, a "needs a chase" worklist, the onboarding checklist, recall %-of-list, last-email per deal. | Local (`npm run dev`, port 5174) today; Netlify + Google-domain SSO planned. |

## The shared pipeline (`pipeline/`)

Python scripts that fetch from NHS ODS, HubSpot, Google Sheets and Notion, and
write JSON the apps consume. Run from the repo root (each resolves paths from
its own location):

```bash
python3 pipeline/refresh_data.py --waitlist   # waitlist/live/onboarding/recalls → map data
python3 pipeline/snapshot.py                  # daily snapshot for the time-travel slider
python3 pipeline/pull_planner_funnel.py       # HubSpot Planner deals → outputs/planner_deals.json
python3 pipeline/build_funnel_board.py        # → primary-care-tech-overview funnel_board.json
python3 -m unittest discover -s tests         # pipeline tests
```

### Data contract (important)

Shared upstream JSONs — `waitlist_ods`, `live_customers*`, `onboarding_ods`,
`recalls`, `practices_geocoded`, `practice_tiers`, snapshots — live in
**`apps/tech-growth-map/public/data/`** (the map is their home and primary
consumer). The dashboard's pipeline scripts *read* them cross-app and *write*
the dashboard's own derived JSON (`funnel_board.json`, `attribution.json`, …)
into **`apps/primary-care-tech-overview/public/data/`**. **The Google Sheet
onboarding tracker is read-only — never written to.**

## Run an app

```bash
cd apps/tech-growth-map         && npm ci && npm run dev   # map  (Vite default port)
cd apps/primary-care-tech-overview && npm ci && npm run dev # dashboard (port 5174 + override API 5175)
```

## CI / deploy

- `refresh-waitlist.yml` — every ~5 min: refresh map data, snapshot, **build & deploy `apps/tech-growth-map` to GitHub Pages**.
- `refresh-funnel-board.yml` — daily: rebuild `apps/primary-care-tech-overview/public/data/funnel_board.json`.
- `push-signups-to-sheet.yml` — daily: push signups + hitlist to Google Sheets.
- `test.yml` — pipeline tests on push/PR.

Secrets: `HUBSPOT_API_TOKEN`, `GOOGLE_SHEETS_SA_JSON`, `NOTION_API_TOKEN`, `PAT_DISPATCH` (Actions secrets; `.env` locally, gitignored).

> Project reference for AI assistants: `CLAUDE.md`. Funnel analysis + playbook: `docs/planner_analytics.md`.
