# Tech Growth Map · `[MAP]`

React + Leaflet map of every England GP practice (~6,400), colour-coded by Suvera
pipeline status (signed-up / onboarding / live / not-signed-up), with stats,
sparklines, month-on-month targets and a time-travel snapshot slider.

| | |
|---|---|
| **Audience** | Leadership / whole-of-England view |
| **Hosting** | **GitHub Pages** — `vite.config.js` base `/Tech-growth-map/` |
| **Refresh** | every ~5 min via `.github/workflows/refresh-waitlist.yml` |
| **Backend** | none (fully static) |

## Owns the upstream data contract

`public/data/` is the **single source of truth** for the GP universe and pipeline
status — `practices_geocoded`, `waitlist_ods`, `live_customers*`, `onboarding_ods`,
`recalls`, `practice_tiers`, `icb_boundaries` — plus `public/snapshots/`. The shared
`pipeline/` writes these; the **overview dashboard reads them cross-app, never
writes them**.

## Run

```bash
npm ci && npm run dev     # Vite dev server
npm run build             # → dist/  (published to GitHub Pages)
npm test                  # vitest component tests
```

Data is produced by the shared `pipeline/` (run from the repo root). Full project
reference: root [`README.md`](../../README.md) and [`CLAUDE.md`](../../CLAUDE.md).
