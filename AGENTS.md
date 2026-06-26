# AGENTS.md — agent quick-reference

> **Authoritative project reference: [`CLAUDE.md`](./CLAUDE.md).** Human-facing
> architecture overview: [`README.md`](./README.md). This file is intentionally a
> short pointer (not a second copy of the pipeline docs) so agents don't follow a
> stale duplicate. Read `CLAUDE.md` for data files, status tiers, the ICB merger
> logic, patient-list sizes, testing and the full gotchas list.

## Monorepo shape (restructured 2026-06-05)

Two independent React frontends over one shared Python pipeline:

- **`apps/tech-growth-map/`** — Leaflet map of every England GP practice (the
  "Tech Growth Map"). GitHub Pages. Owns the **upstream** data contract in its
  `public/data/`. See [`apps/tech-growth-map/README.md`](./apps/tech-growth-map/README.md).
- **`apps/primary-care-tech-overview/`** — Planner funnel + onboarding **overview
  dashboard**. Netlify + Neon + Google SSO. Reads the map's data cross-app; writes
  its own **derived** JSON. See
  [`apps/primary-care-tech-overview/README.md`](./apps/primary-care-tech-overview/README.md).
- **`pipeline/`** — shared Python (+ `override_server.js`); scripts resolve paths
  from the repo root. (Older docs may say `scripts/` — that directory was renamed
  to `pipeline/` in the restructure.)

## Run

```bash
cd apps/tech-growth-map && npm ci && npm run dev            # map
cd apps/primary-care-tech-overview && npm ci && npm run dev # dashboard (Vite 5174 + onboarding API 5175)
python3 -m unittest discover tests                          # pipeline tests (from repo root)
```

## Load-bearing gotchas (full list in CLAUDE.md)

- **Google Sheets onboarding tracker is READ-ONLY** — never write to it.
- **Never `git add -A` / `git add .`** — repo root holds `.env` + large xlsx; stage by path.
- **Don't rename `waitlist_ods.json`** — the shrink-guard keys on the filename.
- **ODS codes must be uppercased** everywhere (set-membership tests fail silently otherwise).
- **The 5-min map refresh cadence matters** — stale data only shows a 15-min freshness banner.
