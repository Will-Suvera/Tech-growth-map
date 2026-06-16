import React from "react";

// ── Planner Revenue Goal — £1m ARR ──────────────────────────────────────────
// A high-level "are we on track for £1m ARR by year-end" panel. The checkpoint
// trajectory is from the agreed plan (Will Gao, 15 Jun 2026).
//
// CURRENT_ARR is a MANUAL constant: there is no automated revenue feed today —
// only the Money-back tier generates ARR and no practice is on it yet, so it is
// genuinely £0. When the first paying practice lands, bump this number (and, if
// you want it live, derive it from the Money-back cohort instead). Everything
// else on the page recomputes off it.
const CURRENT_ARR = 0;
const REVENUE_GOAL = 1_000_000;

// end = last day of the checkpoint period (ISO). target = cumulative ARR target.
const CHECKPOINTS = [
  { label: "End April", end: "2026-04-30", target: 0,         note: "Free usage, demos, pipeline build" },
  { label: "End May",   end: "2026-05-31", target: 20_000,    note: "First paying practices live" },
  { label: "End June",  end: "2026-06-30", target: 100_000,   note: "Monetisation ramp starts" },
  { label: "End Aug",   end: "2026-08-31", target: 250_000,   note: "Compounding referrals + PCN deals" },
  { label: "End Oct",   end: "2026-10-31", target: 500_000,   note: "PCN-level deals carrying the weight" },
  { label: "End Dec",   end: "2026-12-31", target: 1_000_000, note: "Wider adoption, more features" },
];

// £0 · £20k · £100k · £1m
const gbp = (n) => {
  if (!n) return "£0";
  if (n >= 1_000_000) return `£${(n / 1_000_000).toFixed(n % 1_000_000 ? 1 : 0).replace(/\.0$/, "")}m`;
  if (n >= 1_000) return `£${Math.round(n / 1_000)}k`;
  return `£${n.toLocaleString()}`;
};

const daysBetween = (a, b) => Math.round((b - a) / 86_400_000);

export default function RevenueTarget({ arr = CURRENT_ARR }) {
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
      <footer className="card-foot">
        Current ARR is maintained manually — it is £0 until the first Money-back (paying) practice goes live. No practice is on a paying tier yet.
      </footer>
    </section>
  );
}
