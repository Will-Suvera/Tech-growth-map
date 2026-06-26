# Primary Care Tech Overview · `[OVERVIEW]`

React dashboard of the Planner funnel: **sales → DPA → onboarding → Live →
recalling**. Two tabs — a read-only **Overview** (funnel, KPIs, revenue goal,
lead-source, week-by-week) and the **Onboarding Hub** (the CS action surface:
per-practice set-up steps + timestamped notes, written to Neon).

| | |
|---|---|
| **Audience** | Planner CS + sales (internal, behind a `@suvera.co.uk` Google gate) |
| **Hosting** | **Netlify** (base `/`, `netlify.toml`) + Neon Postgres + Google SSO |
| **Refresh** | data daily via `refresh-funnel-board.yml`; code on push via `deploy-planner.yml` |
| **Backend** | `api/server.mjs` (local dev, :5175) + `netlify/functions/onboarding.mjs` (prod, SSO-gated) over Neon |

## Data

Reads the **upstream** contract from `apps/tech-growth-map/public/data/`
(cross-app, **read-only**) and emits its own **derived** JSON into `public/data/`
(`funnel_board.json`, `attribution.json`, …) via the shared `pipeline/`.

## Run

```bash
npm ci && npm run dev     # Vite (5174) + Neon onboarding API (5175), concurrently
npm run build             # → dist/  (Netlify publishes this)
```

Needs `NEON_DATABASE_URL` in the repo-root `.env`. Full project reference: root
[`README.md`](../../README.md) and [`CLAUDE.md`](../../CLAUDE.md).
