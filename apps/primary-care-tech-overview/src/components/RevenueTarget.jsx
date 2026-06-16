import React, { useMemo, useState } from "react";

// ── Planner Revenue Goal — £1m ARR ──────────────────────────────────────────
// A high-level "are we on track for £1m ARR by year-end" panel. The checkpoint
// trajectory is from the agreed plan (Will Gao, 15 Jun 2026).
//
// Two numbers live here:
//   • Current (committed) ARR — from HubSpot via funnel_board.json `data.revenue`:
//     the sum of real deal amounts for practices that have signed (DPA-signed
//     onward, incl. live). FALLBACK_ARR is used only if the board predates it.
//   • Forecast ARR — committed + a modelled value for the rest of the pipeline:
//     list_size × PRICE_PER_PATIENT × P(reach live | stage). The conversion
//     probabilities come from a scenario toggle (Conservative / Base / Optimistic).
const FALLBACK_ARR = 0;
const REVENUE_GOAL = 1_000_000;

// Average ARR per registered patient. Validated against the first signed deals:
// Chapelford landed at exactly £0.65/patient; Alvaston higher (£0.91, larger
// package). 65p is the conservative base — change here if pricing shifts.
const PRICE_PER_PATIENT = 0.65;

// end = last day of the checkpoint period (ISO). target = cumulative ARR target.
const CHECKPOINTS = [
  { label: "End April", end: "2026-04-30", target: 0,         note: "Free usage, demos, pipeline build" },
  { label: "End May",   end: "2026-05-31", target: 20_000,    note: "First paying practices live" },
  { label: "End June",  end: "2026-06-30", target: 100_000,   note: "Monetisation ramp starts" },
  { label: "End Aug",   end: "2026-08-31", target: 250_000,   note: "Compounding referrals + PCN deals" },
  { label: "End Oct",   end: "2026-10-31", target: 500_000,   note: "PCN-level deals carrying the weight" },
  { label: "End Dec",   end: "2026-12-31", target: 1_000_000, note: "Wider adoption, more features" },
];

// Pipeline stages, earliest → live. Each scenario gives P(a practice at this
// stage eventually reaches live and pays). Live = already there = 100%.
const STAGE_ORDER = ["waitlist", "demo_booked", "demo_held", "dpa_sent", "dpa_signed", "live"];
const STAGE_LABEL = {
  waitlist: "Signed-up", demo_booked: "Demo booked", demo_held: "Demo held",
  dpa_sent: "DPA sent", dpa_signed: "DPA signed", live: "Live",
};
const SCENARIOS = {
  conservative: { label: "Conservative", conv: { waitlist: 0.04, demo_booked: 0.08, demo_held: 0.20, dpa_sent: 0.55, dpa_signed: 0.85, live: 1 } },
  base:         { label: "Base",         conv: { waitlist: 0.08, demo_booked: 0.15, demo_held: 0.35, dpa_sent: 0.70, dpa_signed: 0.95, live: 1 } },
  optimistic:   { label: "Optimistic",   conv: { waitlist: 0.15, demo_booked: 0.30, demo_held: 0.55, dpa_sent: 0.85, dpa_signed: 1.00, live: 1 } },
};

// £0 · £20k · £100k · £1m
const gbp = (n) => {
  if (!n) return "£0";
  if (n >= 1_000_000) return `£${(n / 1_000_000).toFixed(n % 1_000_000 ? 1 : 0).replace(/\.0$/, "")}m`;
  if (n >= 1_000) return `£${Math.round(n / 1_000)}k`;
  return `£${Math.round(n).toLocaleString()}`;
};

const daysBetween = (a, b) => Math.round((b - a) / 86_400_000);

export default function RevenueTarget({ revenue, deals = [] }) {
  const arr = revenue?.current_arr ?? FALLBACK_ARR;
  const signedDeals = revenue?.deals || [];
  const [scenario, setScenario] = useState("base");
  const today = new Date();
  const todayISO = today.toISOString().slice(0, 10);

  // active checkpoint = the first period that hasn't ended yet (else the last)
  let activeIdx = CHECKPOINTS.findIndex((c) => c.end >= todayISO);
  if (activeIdx === -1) activeIdx = CHECKPOINTS.length - 1;
  const active = CHECKPOINTS[activeIdx];

  const goalPct = Math.min(100, Math.round((arr / REVENUE_GOAL) * 100));
  const gap = Math.max(0, active.target - arr);
  const checkpointPct = active.target ? Math.min(100, Math.round((arr / active.target) * 100)) : 100;
  const daysLeft = daysBetween(today, new Date(active.end + "T23:59:59"));

  const rows = CHECKPOINTS.map((c, i) => {
    const newArr = i === 0 ? 0 : c.target - CHECKPOINTS[i - 1].target;
    let status, tone;
    if (i < activeIdx) {
      const hit = arr >= c.target;
      status = hit ? "Hit" : `Behind by ${gbp(c.target - arr)}`;
      tone = hit ? "good" : "bad";
    } else if (i === activeIdx) {
      status = c.target <= arr ? "On track" : `${gbp(gap)} to go${daysLeft >= 0 ? ` · ${daysLeft}d left` : ""}`;
      tone = c.target <= arr ? "good" : "now";
    } else {
      status = "Upcoming";
      tone = "dim";
    }
    return { ...c, newArr, status, tone, current: i === activeIdx };
  });

  const onTrack = arr >= active.target;

  // ── forecast: committed (real £) + modelled pipeline (list × 65p × P) ──
  // Practices already counted in committed ARR (their real HubSpot amount) are
  // excluded from the modelled side so they aren't double-counted.
  const committedOds = useMemo(
    () => new Set(signedDeals.map((d) => d.ods).filter(Boolean)),
    [signedDeals]
  );
  const forecast = useMemo(() => {
    const conv = SCENARIOS[scenario].conv;
    const byStage = Object.fromEntries(STAGE_ORDER.map((s) => [s, { practices: 0, patients: 0, expected: 0 }]));
    let modelled = 0;
    for (const d of deals) {
      if (committedOds.has(d.ods)) continue;
      const stage = d.stage;
      if (!(stage in byStage)) continue;
      const pat = d.patients || 0;
      const p = conv[stage] ?? 0;
      const val = pat * PRICE_PER_PATIENT * p;
      byStage[stage].practices += 1;
      byStage[stage].patients += pat;
      byStage[stage].expected += val;
      modelled += val;
    }
    return { modelled, total: arr + modelled, byStage };
  }, [deals, committedOds, scenario, arr]);

  const forecastPct = Math.min(100, Math.round((forecast.total / REVENUE_GOAL) * 100));
  const stageRows = STAGE_ORDER.map((s) => ({ stage: s, ...forecast.byStage[s] })).filter((r) => r.practices > 0);

  return (
    <section className="card revtarget">
      <header className={"card-head " + (onTrack ? "ok" : "warn")}>
        <div>
          <h3 className="card-title">
            Planner revenue goal — £1m ARR <span className="count-pill">{goalPct}%</span>
          </h3>
          <p className="card-sub">
            Cumulative ARR against the year-end target · checkpoint trajectory agreed 15 Jun 2026.
          </p>
        </div>
        <span className="head-flag">{onTrack ? "On track" : "Behind plan"}</span>
      </header>

      <div className="revtarget-hero">
        <div className="rt-now">
          <div className="rt-now-value">{gbp(arr)}</div>
          <div className="rt-now-label">current ARR · of {gbp(REVENUE_GOAL)} goal</div>
        </div>
        <div className="rt-bar-wrap">
          <div className="rt-bar-track">
            <div className="rt-bar-fill" style={{ width: `${Math.max(goalPct, 1.5)}%` }} />
            <div className="rt-bar-forecast" style={{ width: `${Math.max(forecastPct, 1.5)}%` }} title={`Forecast (${SCENARIOS[scenario].label}): ${gbp(forecast.total)}`} />
            {CHECKPOINTS.slice(0, -1).map((c) => (
              <span
                key={c.label}
                className="rt-tick"
                style={{ left: `${(c.target / REVENUE_GOAL) * 100}%` }}
                title={`${c.label}: ${gbp(c.target)}`}
              />
            ))}
          </div>
          <div className="rt-bar-foot">
            <span>
              Next checkpoint <b>{active.label}</b> — {gbp(active.target)} target
            </span>
            <span className={onTrack ? "t-good" : "t-warn"}>
              {onTrack ? "target met" : `${gbp(gap)} to go (${checkpointPct}%)${daysLeft >= 0 ? ` · ${daysLeft}d left` : ""}`}
            </span>
          </div>
        </div>
      </div>

      <table className="dtable revtarget-table">
        <thead>
          <tr>
            <th>Checkpoint</th>
            <th className="td-num">ARR target</th>
            <th className="td-num">New ARR in period</th>
            <th>Implied pace</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className={r.current ? "rt-current" : ""}>
              <td className="t-name">{r.current ? "▸ " : ""}{r.label}</td>
              <td className="td-num">{gbp(r.target)}</td>
              <td className="td-num t-dim">{r.newArr ? `+${gbp(r.newArr)}` : "—"}</td>
              <td className="t-dim">{r.note}</td>
              <td className={"rt-status " + r.tone}>{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ── forecast from pipeline patient volume ── */}
      <div className="rt-forecast">
        <div className="rt-forecast-head">
          <div>
            <h4 className="rt-forecast-title">Forecast — pipeline at {Math.round(PRICE_PER_PATIENT * 100)}p / patient</h4>
            <p className="card-sub">
              Committed signed ARR + the rest of the pipeline valued at list size × {Math.round(PRICE_PER_PATIENT * 100)}p,
              weighted by each stage's chance of reaching live.
            </p>
          </div>
          <div className="gran-toggle rt-scenario">
            {Object.entries(SCENARIOS).map(([k, s]) => (
              <button key={k} className={scenario === k ? "active" : ""} onClick={() => setScenario(k)}>{s.label}</button>
            ))}
          </div>
        </div>

        <div className="rt-forecast-figs">
          <div className="rt-fig">
            <div className="rt-fig-value">{gbp(arr)}</div>
            <div className="rt-fig-label">committed · signed (real HubSpot £)</div>
          </div>
          <div className="rt-fig op">+</div>
          <div className="rt-fig">
            <div className="rt-fig-value">{gbp(forecast.modelled)}</div>
            <div className="rt-fig-label">modelled pipeline · list × {Math.round(PRICE_PER_PATIENT * 100)}p × conv</div>
          </div>
          <div className="rt-fig op">=</div>
          <div className="rt-fig strong">
            <div className="rt-fig-value">{gbp(forecast.total)}</div>
            <div className="rt-fig-label">forecast ARR · {forecastPct}% of £1m ({SCENARIOS[scenario].label})</div>
          </div>
        </div>

        <table className="dtable revtarget-table rt-stage-table">
          <thead>
            <tr>
              <th>Stage</th>
              <th className="td-num">Practices</th>
              <th className="td-num">Patients</th>
              <th className="td-num">Conv → live</th>
              <th className="td-num">Expected ARR</th>
            </tr>
          </thead>
          <tbody>
            {stageRows.map((r) => (
              <tr key={r.stage}>
                <td className="t-name">{STAGE_LABEL[r.stage]}</td>
                <td className="td-num t-dim">{r.practices}</td>
                <td className="td-num t-dim">{r.patients.toLocaleString()}</td>
                <td className="td-num t-dim">{Math.round(SCENARIOS[scenario].conv[r.stage] * 100)}%</td>
                <td className="td-num">{gbp(r.expected)}</td>
              </tr>
            ))}
            <tr className="rt-stage-total">
              <td className="t-name">Modelled pipeline</td>
              <td className="td-num t-dim">{stageRows.reduce((a, r) => a + r.practices, 0)}</td>
              <td className="td-num t-dim">{stageRows.reduce((a, r) => a + r.patients, 0).toLocaleString()}</td>
              <td className="td-num t-dim">—</td>
              <td className="td-num">{gbp(forecast.modelled)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer className="card-foot">
        Current ARR = signed deal value from HubSpot (DPA-signed onward, incl. live){signedDeals.length ? ": " : ""}
        {signedDeals.map((d, i) => (
          <span key={d.ods || d.name}>{i ? " · " : ""}{d.name} {gbp(d.amount)}</span>
        ))}
        {signedDeals.length ? ". " : " — £0 until the first practice signs. "}
        Forecast values the rest of the pipeline at {Math.round(PRICE_PER_PATIENT * 100)}p/patient × stage conversion — a planning estimate, not booked revenue.
      </footer>
    </section>
  );
}
