import React, { useMemo, useState } from "react";

// ── Planner Revenue Goal — £1m ARR ──────────────────────────────────────────
// A high-level "are we on track for £1m ARR by year-end" model. In the Flow 2
// overview it surfaces two ways:
//   • <RevenueHero> — the signature gradient hero (right column, top). Compact:
//     signed ARR, % of goal, status, the next checkpoint, and forecast. Clicking
//     it opens the full breakdown.
//   • <RevenueDetail> — the checkpoint trajectory table + the pipeline forecast,
//     rendered inside the slide-over (the hero's drill-in).
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
// stage becomes a paying premium customer).
//   • Stages below "live" → P(reaches live AND pays).
//   • "live" here means live but NOT yet paying — every practice currently at
//     the live stage is on Freemium (£0). Already-paying live deals carry a real
//     amount and are counted in committed ARR, so they never reach this side.
//     So live's weight is the chance a live Freemium practice UPGRADES to
//     premium — an upsell rate, not 100%.
const STAGE_ORDER = ["waitlist", "demo_booked", "demo_held", "dpa_sent", "dpa_signed", "live"];
const STAGE_LABEL = {
  waitlist: "Signed-up", demo_booked: "Demo booked", demo_held: "Demo held",
  dpa_sent: "Proposal sent", dpa_signed: "DPA signed", live: "Live (freemium)",
};
const SCENARIOS = {
  conservative: { label: "Conservative", conv: { waitlist: 0.04, demo_booked: 0.08, demo_held: 0.20, dpa_sent: 0.55, dpa_signed: 0.85, live: 0.30 } },
  base:         { label: "Base",         conv: { waitlist: 0.08, demo_booked: 0.15, demo_held: 0.35, dpa_sent: 0.70, dpa_signed: 0.95, live: 0.50 } },
  optimistic:   { label: "Optimistic",   conv: { waitlist: 0.15, demo_booked: 0.30, demo_held: 0.55, dpa_sent: 0.85, dpa_signed: 1.00, live: 0.75 } },
};

// £0 · £20k · £100k · £1m
const gbp = (n) => {
  if (!n) return "£0";
  if (n >= 1_000_000) return `£${(n / 1_000_000).toFixed(n % 1_000_000 ? 1 : 0).replace(/\.0$/, "")}m`;
  if (n >= 1_000) return `£${Math.round(n / 1_000)}k`;
  return `£${Math.round(n).toLocaleString()}`;
};

const daysBetween = (a, b) => Math.round((b - a) / 86_400_000);

// Shared revenue model — committed ARR, the active checkpoint, and a
// scenario-weighted pipeline forecast. Both the hero and the detail consume it.
function useRevenueModel(revenue, deals = [], scenario = "base") {
  const arr = revenue?.current_arr ?? FALLBACK_ARR;
  const signedDeals = revenue?.deals || [];
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
  const onTrack = arr >= active.target;

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

  // ── forecast: committed (real £) + modelled pipeline (list × 65p × P) ──
  const committedOds = useMemo(
    () => new Set(signedDeals.map((d) => d.ods).filter(Boolean)),
    [signedDeals]
  );
  const forecast = useMemo(() => {
    const conv = SCENARIOS[scenario].conv;
    const byStage = Object.fromEntries(STAGE_ORDER.map((s) => [s, { practices: 0, patients: 0, contracted: 0, value: 0, expected: 0 }]));
    let modelled = 0, contractedCount = 0, contractedValue = 0;
    for (const d of deals) {
      if (committedOds.has(d.ods)) continue;
      const stage = d.stage;
      if (!(stage in byStage)) continue;
      const pat = d.patients || 0;
      const p = conv[stage] ?? 0;
      const hasContract = (d.amount || 0) > 0;
      const value = hasContract ? d.amount : pat * PRICE_PER_PATIENT;
      const val = value * p;
      byStage[stage].practices += 1;
      byStage[stage].patients += pat;
      byStage[stage].value += value;
      byStage[stage].expected += val;
      if (hasContract) { byStage[stage].contracted += 1; contractedCount += 1; contractedValue += d.amount; }
      modelled += val;
    }
    return { modelled, total: arr + modelled, byStage, contractedCount, contractedValue };
  }, [deals, committedOds, scenario, arr]);

  const forecastPct = Math.min(100, Math.round((forecast.total / REVENUE_GOAL) * 100));

  return {
    arr, signedDeals, active, activeIdx, goalPct, gap, checkpointPct, daysLeft,
    onTrack, rows, forecast, forecastPct, REVENUE_GOAL, PRICE_PER_PATIENT, gbp,
  };
}

// ── Hero: the signature gradient block (Flow 2 right column, top). ──
// Clicking anywhere opens the full breakdown via `onOpen` (the slide-over drill-in).
export function RevenueHero({ revenue, deals = [], onOpen }) {
  const m = useRevenueModel(revenue, deals, "base");
  return (
    <div
      className="ov-hero su-num"
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen?.(); } }}
    >
      <div className="ov-hero-top">
        <span className="ov-hero-eyebrow">Revenue goal · {gbp(m.REVENUE_GOAL)} ARR</span>
        <span className="ov-hero-pill">{m.onTrack ? "ON TRACK" : "BEHIND PLAN"}</span>
      </div>
      <div className="ov-hero-metric">
        <span className="ov-hero-num">{gbp(m.arr)}</span>
        <span className="ov-hero-cap">signed &amp; paid<br />{m.goalPct}% of goal</span>
      </div>
      <div className="ov-hero-bar">
        <div className="ov-hero-fill" style={{ width: `${Math.max(m.goalPct, 0.6)}%` }} />
      </div>
      <div className="ov-hero-foot">
        <div className="ov-hero-next">
          Next: {m.active.label} {gbp(m.active.target)}
          <br />
          <b>{m.onTrack ? "target met" : `${gbp(m.gap)} to go`}{!m.onTrack && m.daysLeft >= 0 ? ` · ${m.daysLeft}d` : ""}</b>
        </div>
        <div className="ov-hero-fc">
          <div className="ov-hero-fc-num">{gbp(m.forecast.total)}</div>
          <div className="ov-hero-fc-lbl">forecast · {m.forecastPct}%</div>
        </div>
      </div>
    </div>
  );
}

// ── Detail: checkpoint trajectory + pipeline forecast. Rendered in the
// slide-over when the hero is clicked. ──
export function RevenueDetail({ revenue, deals = [] }) {
  const [scenario, setScenario] = useState("base");
  const m = useRevenueModel(revenue, deals, scenario);
  const stageRows = STAGE_ORDER
    .map((s) => ({ stage: s, ...m.forecast.byStage[s] }))
    .filter((r) => r.practices > 0);

  return (
    <>
      <div className="so-head">
        <div className="so-titlerow">
          <h2 className="so-title">Revenue goal — {gbp(m.REVENUE_GOAL)} ARR</h2>
        </div>
        <div className="so-sync">
          {gbp(m.arr)} signed &amp; paid · {m.goalPct}% of goal · forecast {gbp(m.forecast.total)} ({SCENARIOS[scenario].label})
          {m.onTrack ? "" : ` · behind plan`}
        </div>
        <div className="so-meta">
          <MetaItem label="Signed & paid" value={gbp(m.arr)} />
          <MetaItem label="Next checkpoint" value={`${m.active.label} ${gbp(m.active.target)}`} />
          <MetaItem label="Gap" value={m.onTrack ? "met" : gbp(m.gap)} />
          <MetaItem label="Days left" value={m.daysLeft >= 0 ? `${m.daysLeft}d` : "—"} />
        </div>
      </div>

      <div className="so-body">
        <div className="so-section">
          <h4 className="so-section-title">Checkpoint trajectory <em className="cur-key">agreed 15 Jun 2026</em></h4>
          <table className="dtable revtarget-table">
            <thead>
              <tr>
                <th>Checkpoint</th>
                <th className="td-num">ARR target</th>
                <th className="td-num">New in period</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {m.rows.map((r) => (
                <tr key={r.label} className={r.current ? "rt-current" : ""}>
                  <td className="t-name">{r.current ? "▸ " : ""}{r.label}</td>
                  <td className="td-num">{gbp(r.target)}</td>
                  <td className="td-num t-dim">{r.newArr ? `+${gbp(r.newArr)}` : "—"}</td>
                  <td className={"rt-status " + r.tone}>{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="so-section">
          <div className="rt-forecast-head">
            <div>
              <h4 className="so-section-title" style={{ margin: 0 }}>Forecast — pipeline at {Math.round(PRICE_PER_PATIENT * 100)}p / patient</h4>
            </div>
            <div className="gran-toggle rt-scenario">
              {Object.entries(SCENARIOS).map(([k, s]) => (
                <button key={k} className={scenario === k ? "active" : ""} onClick={() => setScenario(k)}>{s.label}</button>
              ))}
            </div>
          </div>

          <div className="rt-forecast-figs">
            <div className="rt-fig">
              <div className="rt-fig-value su-num">{gbp(m.arr)}</div>
              <div className="rt-fig-label">signed &amp; paid</div>
            </div>
            <div className="rt-fig op">+</div>
            <div className="rt-fig">
              <div className="rt-fig-value su-num">{gbp(m.forecast.modelled)}</div>
              <div className="rt-fig-label">modelled pipeline</div>
            </div>
            <div className="rt-fig op">=</div>
            <div className="rt-fig strong">
              <div className="rt-fig-value su-num">{gbp(m.forecast.total)}</div>
              <div className="rt-fig-label">forecast · {m.forecastPct}% of {gbp(m.REVENUE_GOAL)}</div>
            </div>
          </div>

          <table className="dtable revtarget-table rt-stage-table">
            <thead>
              <tr>
                <th>Stage</th>
                <th className="td-num">Practices</th>
                <th className="td-num">Patients</th>
                <th className="td-num">Conv → paid</th>
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
                <td className="td-num">{gbp(m.forecast.modelled)}</td>
              </tr>
            </tbody>
          </table>

          <p className="card-foot" style={{ marginTop: 14 }}>
            <b>Signed &amp; paid</b> = a genuinely signed, paying contract
            {m.signedDeals.length ? ": " : " — £0 until the first deal signs. "}
            {m.signedDeals.map((d, i) => (
              <span key={d.ods || d.name}>{i ? " · " : ""}{d.name} {gbp(d.amount)}</span>
            ))}
            {m.signedDeals.length ? ". " : ""}
            Everything else is <b>not yet signed</b> — HubSpot prices are <i>quotes</i>, valued at their quote
            {m.forecast.contractedCount ? ` (${m.forecast.contractedCount} deal${m.forecast.contractedCount > 1 ? "s" : ""}, ${gbp(m.forecast.contractedValue)} quoted)` : ""},
            else {Math.round(PRICE_PER_PATIENT * 100)}p/patient, × each stage's conversion. The {STAGE_LABEL.live} row is
            Freemium (£0 today) — counted at its chance of upgrading.
          </p>
        </div>
      </div>
    </>
  );
}

// Small local copy of the slide-over meta cell (kept here so RevenueDetail is
// self-contained when imported into the funnel board's slide-over).
function MetaItem({ label, value }) {
  return (
    <div className="so-meta-item">
      <div className="so-meta-label">{label}</div>
      <div className="so-meta-value plain su-num">{value}</div>
    </div>
  );
}

export default RevenueHero;
