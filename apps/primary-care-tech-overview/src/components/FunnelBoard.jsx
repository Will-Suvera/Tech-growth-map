import React, { useEffect, useMemo, useState } from "react";

// Onboarding-toggle API (Neon-backed). Dev: local Node server (/api/onboarding on :5175).
// Prod: Netlify Function (/.netlify/functions/onboarding). Override via VITE_ONB_API.
const ONB_BASE =
  (import.meta.env && import.meta.env.VITE_ONB_API) ||
  (import.meta.env && import.meta.env.PROD ? "/.netlify/functions/onboarding" : "http://localhost:5175/api/onboarding");
const STATE_CYCLE = { todo: "pending", pending: "done", done: "todo" };

// merge live (Neon) onboarding state over the static sheet-seeded steps; live wins
function mergeOnboarding(steps, liveForOds) {
  if (!steps || !liveForOds) return steps;
  return steps.map((s) => {
    const live = liveForOds[s.key];
    return live ? { ...s, state: live.state, changed_at: live.changed_at, changed_by: live.changed_by } : s;
  });
}

// Stage KEYS are stable; display labels come live from the data (funnel_board.json),
// so a HubSpot stage rename flows through without touching this file.
const ORDER = ["waitlist", "demo_booked", "demo_held", "dpa_sent", "dpa_signed", "live", "recalling"];
const ACTION = {
  waitlist: "Book demos", demo_held: "Send DPA", dpa_sent: "Chase signature",
  dpa_signed: "Book go-lives", live: "Activation calls",
};
const MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "");
const fmtMon = (ym) => (ym ? `${MON[+ym.slice(5, 7)] || ""} ${ym.slice(2, 4)}`.trim() : "");

const SCOPE_DESC = {
  overview: "The whole flow — signed-up through live, recalling and volumes.",
  partnerships: "Sales: signed-up list → DPA signed. Everything here lives in HubSpot.",
  onboarding: "Onboarding: DPA signed & onboard-ready, not yet live. Each step is a button — changes are timestamped.",
  implementation: "Implementation: live practices — first the activation gap (not yet recalling), then the recallers.",
};

const DEAL_ORDER = ["waitlist", "demo_booked", "demo_held", "dpa_sent", "dpa_signed"];

const PAGE_DESC =
  "The whole flow — signed-up through functionally live, recalling and not. Click a stage for its practices; click a practice for full detail.";

export default function FunnelBoard({ data, auth = null }) {
  const [ehr, setEhr] = useState("All");
  const [open, setOpen] = useState(null); // deal-stage key | "live_gap" | "recalling"
  const [showWeekly, setShowWeekly] = useState(false);
  const [detail, setDetail] = useState(null); // { kind: "deal" | "practice", item }
  const weeklyAvailable = !!data?.weekly_available;

  // live onboarding step state (Neon) — the checklist toggles live in the
  // DPA-Signed slide-over, so this is always on.
  const [liveOnb, setLiveOnb] = useState({});
  const [who, setWho] = useState(() => (typeof localStorage !== "undefined" && localStorage.getItem("pcto.who")) || "");
  useEffect(() => {
    fetch(ONB_BASE).then((r) => r.json()).then(setLiveOnb).catch(() => {});
  }, []);

  const editor = auth?.email || who || null;   // SSO email in prod, name field in local dev

  async function toggleStep(deal, step) {
    const cur = liveOnb[deal.ods]?.[step.key]?.state ?? step.state ?? "todo";
    const next = STATE_CYCLE[cur] || "todo";
    setLiveOnb((prev) => ({
      ...prev,
      [deal.ods]: { ...(prev[deal.ods] || {}), [step.key]: { state: next, changed_by: editor || "(you)", changed_at: new Date().toISOString() } },
    }));
    try {
      await fetch(`${ONB_BASE}/step`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}) },
        body: JSON.stringify({ ods: deal.ods, deal_id: String(deal.deal_id || ""), step_key: step.key, to_state: next, changed_by: editor }),
      });
    } catch { /* keep optimistic update */ }
  }
  const onb = { live: liveOnb, who: editor, toggle: toggleStep };

  const deals = useMemo(() => {
    const all = data?.deals || [];
    return ehr === "All" ? all : all.filter((d) => (d.ehr || "Unknown") === ehr);
  }, [data, ehr]);

  const stageMeta = useMemo(
    () => Object.fromEntries((data?.stages || []).map((s) => [s.key, s])),
    [data]
  );
  const labelOf = (key) => stageMeta[key]?.label || key;

  const stageData = DEAL_ORDER.map((key) => {
    const inStage = deals.filter((d) => d.stage === key);
    return { key, label: labelOf(key), deals: inStage, count: inStage.length, stale: inStage.filter((d) => d.stale) };
  });

  // Functionally-live cohorts: ODS-based (recalls feed + Live sheet), broader
  // than HubSpot deals — includes recallers with no Planner deal.
  const rp = data.recalling_practices || [];
  const lnr = data.live_not_recalling || [];
  const liveTotal = rp.length + lnr.length;
  const recShare = liveTotal ? Math.round((rp.length / liveTotal) * 100) : 0;
  const totRec = rp.reduce((a, p) => a + (p.fy_recalls || 0), 0);
  const totBl = rp.reduce((a, p) => a + (p.fy_bloods || 0), 0);

  const maxCount = Math.max(1, ...stageData.map((s) => s.count), liveTotal);
  const wl = deals.filter((d) => d.stage === "waitlist");
  const emisWl = wl.filter((d) => d.ehr === "EMIS").length;
  const tppWl = wl.filter((d) => d.ehr === "SystmOne").length;
  const actNow = deals.filter((d) => d.stale).length;
  const booked = deals.filter((d) => d.next_step).length;

  const insight = (s) => {
    switch (s.key) {
      case "waitlist": return `${emisWl} EMIS ready · ${tppWl} TPP (live in ~2 wks)`;
      case "demo_booked": return `${s.count} booked`;
      case "demo_held": return s.stale.length ? `${s.stale.length} stale >14d — no DPA sent` : "moving";
      case "dpa_sent": return s.stale.length ? `${s.stale.length} stale — chase signature` : "moving";
      case "dpa_signed": return `${s.stale.length} stuck >21d, no go-live booked — THE bottleneck`;
      default: return "";
    }
  };

  const weeks = data.weekly || []; // full history — the table scrolls horizontally
  const convSteps = ORDER.slice(1);
  const [wkView, setWkView] = useState("growth"); // "growth" | "conversion"
  const growthSteps = ORDER.filter((k) => weeks.some((w) => w.reached?.[k] != null));
  const wlDelta = weeks.length > 1 ? (weeks[weeks.length - 1].reached?.waitlist ?? 0) - (weeks[weeks.length - 2].reached?.waitlist ?? 0) : null;

  const openDeal = (d) => setDetail({ kind: "deal", item: d });
  const openPractice = (p) => setDetail({ kind: "practice", item: p });

  const slideover = detail && (
    <SlideOver onClose={() => setDetail(null)}>
      {detail.kind === "deal"
        ? <DealPanel d={detail.item} labelOf={labelOf} onb={onb} weeklyAvailable={weeklyAvailable} />
        : <PracticePanel p={detail.item} weeklyAvailable={weeklyAvailable} />}
    </SlideOver>
  );

  const openStage = stageData.find((s) => s.key === open);
  return (
    <div className="board">
      <div className="board-head">
        <div className="board-desc">{PAGE_DESC}</div>
        <button className="weekly-toggle" onClick={() => setShowWeekly((v) => !v)}>
          {showWeekly ? "Hide week-by-week" : "Week-by-week"}
        </button>
        {auth?.email
          ? <span className="who-field" style={{ marginLeft: 0 }}>Editing as <b>{auth.email}</b></span>
          : <label className="who-field" style={{ marginLeft: 0 }}>You:
              <input value={who} placeholder="your name" onChange={(e) => { setWho(e.target.value); localStorage.setItem("pcto.who", e.target.value); }} />
            </label>}
      </div>

      <div className="kpis">
        <div className="kpi bad"><div className="kpi-label">Act now</div><div className="kpi-value">{actNow}</div><div className="kpi-sub">stale, nothing booked</div></div>
        <div className="kpi"><div className="kpi-label">Next step booked</div><div className="kpi-value">{booked}</div><div className="kpi-sub">deals with a touchpoint</div></div>
        <div className="kpi"><div className="kpi-label">Waitlist</div><div className="kpi-value">{wl.length}</div><div className="kpi-sub">{emisWl} EMIS · {tppWl} TPP</div></div>
        <div className="kpi bad"><div className="kpi-label">Not yet recalling</div><div className="kpi-value">{lnr.length}</div><div className="kpi-sub">live, zero recalls this FY</div></div>
        <div className="kpi good"><div className="kpi-label">Recalling</div><div className="kpi-value">{rp.length}</div><div className="kpi-sub">{recShare}% of functionally live</div></div>
        <div className="kpi good"><div className="kpi-label">Recalls this FY</div><div className="kpi-value">{totRec.toLocaleString()}</div><div className="kpi-sub">{totBl.toLocaleString()} bloods automated</div></div>
      </div>

      {showWeekly && (
        <section className="card weekly-card">
          <header className="card-head">
            <div>
              <h3 className="card-title">Week-by-week</h3>
              <p className="card-sub">
                {wkView === "growth"
                  ? "Extra practices that reached each stage per week, with the % growth · scroll for history."
                  : "Step conversion per week · HubSpot stage-entry timestamps; Recalling from the recalls feed (VC excluded)."}
              </p>
            </div>
            <div className="gran-toggle" style={{ margin: 0 }}>
              <button className={wkView === "conversion" ? "active" : ""} onClick={() => setWkView("conversion")}>Conversion</button>
              <button className={wkView === "growth" ? "active" : ""} onClick={() => setWkView("growth")}>Growth</button>
            </div>
          </header>
          <div className="weekly-scroll">
            {wkView === "conversion" ? (
              <table className="weekly-table">
                <thead>
                  <tr>
                    <th>Conversion %</th>
                    {weeks.map((w) => <th key={w.week}>{fmtDate(w.week)}</th>)}
                    <th>Δ wk</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="wk-step">Signed up</td>
                    {weeks.map((w, i) => <td key={i}><span className="wk-base">{w.reached?.waitlist ?? "—"}</span></td>)}
                    <td className={"wk-delta " + (wlDelta > 0 ? "up" : wlDelta < 0 ? "down" : "")}>
                      {wlDelta == null ? "—" : (wlDelta > 0 ? `+${wlDelta}` : wlDelta)}
                    </td>
                  </tr>
                  {convSteps.map((key, ci) => {
                    const prevKey = ORDER[ci]; // convSteps[ci] = ORDER[ci + 1]
                    const d = stageMeta[key]?.conv_delta_1w;
                    return (
                      <tr key={key}>
                        <td className="wk-step">↳ {key === "recalling" ? "Recalling (non-VC)" : labelOf(key)}</td>
                        {weeks.map((w, i) => {
                          const v = w.conv[key];
                          const num = w.reached?.[key], den = w.reached?.[prevKey];
                          return (
                            <td key={i}>
                              {v == null ? "—" : <>{v}%{num != null && den != null && <span className="wk-abs">{num}/{den}</span>}</>}
                            </td>
                          );
                        })}
                        <td className={"wk-delta " + (d > 0 ? "up" : d < 0 ? "down" : "")}>
                          {d == null ? "—" : (d > 0 ? `+${d}` : d)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <table className="weekly-table">
                <thead>
                  <tr>
                    <th>Practices reached</th>
                    {weeks.map((w) => <th key={w.week}>{fmtDate(w.week)}</th>)}
                    <th title={`net growth over the ${weeks.length} weeks shown`}>Σ {weeks.length} wks</th>
                  </tr>
                </thead>
                <tbody>
                  {growthSteps.map((key) => {
                    const series = weeks.map((w) => w.reached?.[key]);
                    const withData = series.filter((v) => v != null);
                    const total = withData.length >= 2 ? withData[withData.length - 1] - withData[0] : null;
                    const totalPct = total != null && withData[0] > 0 ? (total / withData[0]) * 100 : null;
                    return (
                      <tr key={key}>
                        <td className="wk-step">{key === "recalling" ? "Recalling (non-VC)" : labelOf(key)}</td>
                        {weeks.map((w, i) => {
                          const cur = series[i];
                          const prev = i > 0 ? series[i - 1] : null;
                          if (cur == null) return <td key={i}>—</td>;
                          if (prev == null) return <td key={i}><span className="wk-tot">{cur}</span></td>;
                          const n = cur - prev;
                          const pct = prev > 0 ? (n / prev) * 100 : null;
                          return (
                            <td key={i}>
                              <span className="wk-tot">{cur}</span>
                              <span className={"wk-abs" + (n > 0 ? " grow" : n < 0 ? " shrink" : "")}>
                                {n === 0 ? "—" : <>{n > 0 ? `+${n}` : n}{pct != null ? ` · ${n > 0 ? "+" : ""}${pct.toFixed(1).replace(/\.0$/, "")}%` : ""}</>}
                              </span>
                            </td>
                          );
                        })}
                        <td className={"wk-growth" + (total > 0 ? " up" : "")}>
                          {total == null ? "—" : <>{total > 0 ? `+${total}` : total}
                            {totalPct != null && <span className="wk-abs">{total > 0 ? "+" : ""}{totalPct.toFixed(1).replace(/\.0$/, "")}%</span>}</>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
          <footer className="card-foot">
            {wkView === "growth"
              ? "Each cell: extra practices vs the week before, % growth, and the running total reached."
              : "n/m beneath each % = how many of the previous stage's practices converted. Recalling counts every non-VC recaller from its first recall month."}
          </footer>
        </section>
      )}

      <div className="ehrchips">
        {["All", "EMIS", "SystmOne", "Unknown"].map((x) => (
          <button key={x} className={ehr === x ? "chip active" : "chip"} onClick={() => setEhr(x)}>
            {x === "SystmOne" ? "TPP/S1" : x}
          </button>
        ))}
        <span className="muted">TPP onboarding goes live in ~2 weeks → its waitlist becomes actionable</span>
      </div>

      <section className="card">
        <header className="card-head">
          <div>
            <h3 className="card-title">Funnel — signed up → recalling</h3>
            <p className="card-sub">Click a stage to see its practices · % = step conversion with week-on-week change.</p>
          </div>
        </header>
        <div className="funnel">
          {stageData.map((s, i) => {
            const meta = stageMeta[s.key] || {};
            const conv = meta.conv_from_prev;
            const delta = meta.conv_delta_1w;
            const isBottleneck = s.key === "dpa_signed";
            const width = `${Math.max(8, (s.count / maxCount) * 100)}%`;
            return (
              <div key={s.key} className="funnel-stage-wrap">
                {i > 0 && conv != null && (
                  <div className={"conv" + (conv < 40 ? " conv-bad" : "")}>
                    ↓ {conv}%
                    {delta != null && delta !== 0 && (
                      <em className={"cd " + (delta > 0 ? "up" : "down")}>
                        {delta > 0 ? `▲ +${delta}` : `▼ ${delta}`} wk
                      </em>
                    )}
                  </div>
                )}
                <div
                  className={
                    "funnel-stage" +
                    (isBottleneck ? " bottleneck" : "") +
                    (open === s.key ? " open" : "")
                  }
                  onClick={() => setOpen(open === s.key ? null : s.key)}
                >
                  <div className="fs-bar-area">
                    <div className="fs-bar" style={{ width }}>
                      <span className="fs-label">{s.label}</span>
                      <span className="fs-count">{s.count}</span>
                    </div>
                  </div>
                  <div className="fs-meta">
                    <span className={"fs-insight" + (isBottleneck ? " bad" : "")}>{insight(s)}</span>
                    {ACTION[s.key] && s.stale.length > 0 && <span className="fs-action">{ACTION[s.key]} →</span>}
                    {s.stale.length > 0 && <span className="fs-stale">▲ {s.stale.length} stale</span>}
                  </div>
                </div>
              </div>
            );
          })}

          {/* ----- functionally live: ODS-based cohorts (recalls feed + Live sheet) ----- */}
          <div className="live-divider">
            <span className="ld-label">Functionally live</span>
            <span className="ld-count">{liveTotal}</span>
            <span className="ld-note">recalls feed + Live sheet · incl. practices with no HubSpot deal</span>
          </div>

          <div className="funnel-stage-wrap">
            <div
              className={"funnel-stage gap" + (open === "live_gap" ? " open" : "")}
              onClick={() => setOpen(open === "live_gap" ? null : "live_gap")}
            >
              <div className="fs-bar-area">
                <div className="fs-bar" style={{ width: `${Math.max(8, (lnr.length / maxCount) * 100)}%` }}>
                  <span className="fs-label">Live — not yet recalling</span>
                  <span className="fs-count">{lnr.length}</span>
                </div>
              </div>
              <div className="fs-meta">
                <span className="fs-insight bad">the activation gap — zero recalls this FY</span>
                <span className="fs-action">Activation calls →</span>
              </div>
            </div>
          </div>

          <div className="conv">↓ {recShare}% of live are recalling</div>

          <div className="funnel-stage-wrap">
            <div
              className={"funnel-stage activation" + (open === "recalling" ? " open" : "")}
              onClick={() => setOpen(open === "recalling" ? null : "recalling")}
            >
              <div className="fs-bar-area">
                <div className="fs-bar" style={{ width: `${Math.max(8, (rp.length / maxCount) * 100)}%` }}>
                  <span className="fs-label">Recalling</span>
                  <span className="fs-count">{rp.length}</span>
                </div>
              </div>
              <div className="fs-meta">
                <span className="fs-insight">{totRec.toLocaleString()} recalls · {totBl.toLocaleString()} bloods this FY</span>
              </div>
            </div>
          </div>
        </div>
        <footer className="card-foot">
          Bars = practices currently in each stage, width scaled to count. Sales stages are HubSpot deals (EHR filter applies);
          the two live cohorts are ODS-based and unfiltered.
          {data.next_step_source.includes("unavailable") && " (HubSpot meetings unavailable this run.)"}
        </footer>
      </section>

      {openStage && (
        <section className="card drill-section">
          <header className="card-head">
            <div>
              <h3 className="card-title">{openStage.label} <span className="count-pill">{openStage.count}</span></h3>
              <p className="card-sub">Click a practice for full detail · stale (act-now) first.</p>
            </div>
            <button className="drill-back" onClick={() => setOpen(null)}>Close ×</button>
          </header>
          <DealTable deals={openStage.deals} stageKey={openStage.key} liveOnb={liveOnb} onOpen={openDeal} />
        </section>
      )}

      {open === "live_gap" && (
        <section className="card drill-section">
          <header className="card-head warn">
            <div>
              <h3 className="card-title">Live — not yet recalling <span className="count-pill">{lnr.length}</span></h3>
              <p className="card-sub">Functionally live but zero recalls this FY — the activation gap. Longest-live first.</p>
            </div>
            <span className="head-flag">Action needed</span>
          </header>
          <LiveNotRecallingTable practices={lnr} onOpen={openPractice} />
        </section>
      )}

      {open === "recalling" && (
        <section className="card drill-section">
          <header className="card-head ok">
            <div>
              <h3 className="card-title">Recalling <span className="count-pill">{rp.length}</span></h3>
              <p className="card-sub">From the Omni recall feed — every recaller, incl. VC-tier and practices with no HubSpot deal. Green shade = % of list recalled.</p>
            </div>
            <span className="head-flag">On track</span>
          </header>
          <RecallingTable practices={rp} onOpen={openPractice} />
        </section>
      )}
      {slideover}
    </div>
  );
}

/* ================= shared bits ================= */

function EmailAge({ days, muteUnknown }) {
  if (days == null) return <span className={muteUnknown ? "t-dim" : "t-bad"}>—</span>;
  return <span className={days > 14 ? "t-bad" : "t-dim"}>{days}d ago</span>;
}

function Badges({ d }) {
  return (
    <>
      {d.ehr === "SystmOne" && <em className="tag">TPP</em>}
      {d.ehr === "EMIS" && <em className="tag emis">EMIS</em>}
      {d.fy_recalls > 1000 && <em className="badge gold" title=">1,000 recalls this FY">1k+ club</em>}
      {d.tier === "Money-back" && <em className="badge mbg" title="Money-back guarantee (paying)">MBG</em>}
      {d.tier === "Freemium" && <em className="badge free">Freemium</em>}
      {d.tier === "VC" && <em className="badge vc">VC</em>}
    </>
  );
}

// green shade scales with recall penetration (% of list); deeper = higher
const recallShade = (pct) =>
  pct == null ? undefined : { background: `hsl(158, 52%, ${Math.max(72, 95 - Math.min(pct, 11) * 2.1)}%)` };

function summarizeOnboarding(steps) {
  const done = steps.filter((s) => s.state === "done").length;
  const next = steps.find((s) => s.state !== "done");
  return { done, total: steps.length, next: next ? next.step : null };
}

function OnboardWhy({ steps }) {
  const { done, total, next } = summarizeOnboarding(steps);
  const pct = Math.round((done / total) * 100);
  return (
    <span className="onb-why">
      <span className="onb-bar"><span className="onb-fill" style={{ width: `${pct}%` }} /></span>
      <b>{done}/{total}</b>
      {next && <span className="onb-next">next: {next}</span>}
    </span>
  );
}

/* ================= stage drill-down table ================= */

function DealTable({ deals, stageKey, liveOnb, onOpen }) {
  const isLive = stageKey === "live" || stageKey === "recalling";
  // null = the smart default order (stale first / deepest recall shade first);
  // clicking a header overrides it, clicking again flips direction.
  const [sort, setSort] = useState(null);
  const clickSort = (key) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
      : { key, dir: key === "name" || key === "owner" ? "asc" : "desc" }));
  const arrow = (key) => (sort?.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : "");

  const shade = (x) => (x.recalling ? (x.fy_recalls_pct ?? 0.01) : x.stale ? -2 : -1);
  const defaultCmp = (a, b) => {
    if (isLive) {
      const d = shade(b.d) - shade(a.d);
      if (d) return d;
      return (b.d.days_in_stage || 0) - (a.d.days_in_stage || 0);
    }
    const sa = a.d.stale ? 0 : 1, sb = b.d.stale ? 0 : 1;
    if (sa !== sb) return sa - sb;
    return (b.d.days_in_stage || 0) - (a.d.days_in_stage || 0);
  };
  const SORTS = {
    name: (r) => (r.d.name || "").toLowerCase(),
    days: (r) => r.d.days_in_stage || 0,
    next: (r) => (r.d.next_step ? (r.d.next_step.date || "0") : "9999"),
    why: (r) => (isLive ? (r.d.fy_recalls || 0)
      : stageKey === "dpa_signed" ? (r.progress == null ? -1 : r.progress)
      : (r.d.why || "").toLowerCase()),
    email: (r) => (r.d.days_since_email == null ? -1 : r.d.days_since_email),
    owner: (r) => (r.d.owner || "").toLowerCase(),
  };
  const rows = deals.map((d) => {
    const effOnb = d.onboarding ? mergeOnboarding(d.onboarding, liveOnb?.[d.ods]) : null;
    const progress = effOnb ? summarizeOnboarding(effOnb).done / effOnb.length : null;
    return { d, effOnb, progress };
  });
  const sorted = rows.sort((a, b) => {
    if (!sort) return defaultCmp(a, b);
    const f = SORTS[sort.key];
    const av = f(a), bv = f(b);
    const c = typeof av === "string" ? av.localeCompare(bv) : av - bv;
    return (sort.dir === "asc" ? c : -c) || defaultCmp(a, b);
  });
  const whyLabel = isLive ? "Recalls this FY" : stageKey === "dpa_signed" ? "Onboarding progress" : "Why";
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th className="sortable" onClick={() => clickSort("name")}>Practice{arrow("name")}</th>
          <th className="sortable" onClick={() => clickSort("days")}>{isLive ? "Live for" : "In stage"}{arrow("days")}</th>
          {!isLive && <th className="sortable" onClick={() => clickSort("next")}>Next step{arrow("next")}</th>}
          <th className="sortable" onClick={() => clickSort("why")}>{whyLabel}{arrow("why")}</th>
          {!isLive && <th className="sortable" onClick={() => clickSort("email")}>Last email{arrow("email")}</th>}
          <th className="sortable" onClick={() => clickSort("owner")}>Owner{arrow("owner")}</th>
        </tr>
      </thead>
      <tbody>
        {!sorted.length && <tr className="empty"><td colSpan={6}>No deals in this stage.</td></tr>}
        {sorted.map(({ d, effOnb }) => {
          const recStyle = d.recalling ? recallShade(d.fy_recalls_pct) : undefined;
          return (
            <tr key={d.deal_id} style={recStyle} className={recStyle ? "row-shaded" : ""} onClick={() => onOpen(d)}>
              <td><span className="t-name">{d.name}<Badges d={d} /></span></td>
              <td className="t-dim">{d.days_in_stage != null ? `${d.days_in_stage}d` : "—"}</td>
              {!isLive && (
                <td>{d.next_step
                  ? <span className="t-good">✓ {d.next_step.type}{d.next_step.date ? " " + fmtDate(d.next_step.date) : ""}</span>
                  : <span className="t-bad">none</span>}</td>
              )}
              <td className={d.stale ? "t-bad" : d.recalling ? "t-good" : "t-dim"}>
                {stageKey === "dpa_signed" && effOnb
                  ? <OnboardWhy steps={effOnb} />
                  : isLive
                    ? <>{(d.fy_recalls || 0).toLocaleString()}{d.fy_recalls_pct != null ? ` (${d.fy_recalls_pct}%)` : ""}</>
                    : d.why}
              </td>
              {!isLive && <td><EmailAge days={d.days_since_email} muteUnknown /></td>}
              <td className="t-dim">{d.owner || "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/* ================= implementation tables ================= */

const RECALL_SORTS = {
  name: (p) => (p.name || "").toLowerCase(),
  fy: (p) => p.fy_recalls || 0,
  bloods: (p) => p.fy_bloods || 0,
  mo: (p) => p.recalls_this_month || 0,
  owner: (p) => (p.owner || "").toLowerCase(),
};

function useSort(defaults, sorts) {
  const [sort, setSort] = useState(defaults);
  const clickSort = (key) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
      : { key, dir: key === "name" || key === "owner" ? "asc" : "desc" }));
  const arrow = (key) => (sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : "");
  const sortFn = (a, b, tiebreak) => {
    const f = sorts[sort.key] || sorts[defaults.key];
    const av = f(a), bv = f(b);
    const c = typeof av === "string" ? av.localeCompare(bv) : av - bv;
    return (sort.dir === "asc" ? c : -c) || tiebreak(a, b);
  };
  return { clickSort, arrow, sortFn };
}

function RecallingTable({ practices, onOpen }) {
  const { clickSort, arrow, sortFn } = useSort({ key: "fy", dir: "desc" }, RECALL_SORTS);
  const sorted = [...practices].sort((a, b) => sortFn(a, b, (x, y) => (y.fy_recalls || 0) - (x.fy_recalls || 0)));
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th className="sortable" onClick={() => clickSort("name")}>Practice{arrow("name")}</th>
          <th className="sortable" onClick={() => clickSort("fy")}>Recalls this FY{arrow("fy")}</th>
          <th className="sortable" onClick={() => clickSort("bloods")}>Bloods{arrow("bloods")}</th>
          <th className="sortable td-num" onClick={() => clickSort("mo")}>This mo{arrow("mo")}</th>
          <th className="sortable" onClick={() => clickSort("owner")}>Owner{arrow("owner")}</th>
        </tr>
      </thead>
      <tbody>
        {!sorted.length && <tr className="empty"><td colSpan={5}>No recalling practices yet.</td></tr>}
        {sorted.map((p) => (
          <tr key={p.ods} style={recallShade(p.fy_recalls_pct)} className="row-shaded" onClick={() => onOpen(p)}>
            <td><span className="t-name">{p.name}<PracticeBadges p={p} /></span></td>
            <td className="t-good">{(p.fy_recalls || 0).toLocaleString()}{p.fy_recalls_pct != null ? ` (${p.fy_recalls_pct}%)` : ""}</td>
            <td className="t-dim">{(p.fy_bloods || 0).toLocaleString()}{p.fy_bloods_pct != null ? ` (${p.fy_bloods_pct}%)` : ""}</td>
            <td className="td-num">{(p.recalls_this_month || 0).toLocaleString()}</td>
            <td className="t-dim">{p.owner || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const LIVE_SORTS = {
  name: (p) => (p.name || "").toLowerCase(),
  patients: (p) => p.patients || 0,
  live: (p) => p.live_days || 0,
  next: (p) => (p.next_step?.date ? p.next_step.date : p.last_visit?.date ? "8" + p.last_visit.date : "9999"),
  owner: (p) => (p.owner || "").toLowerCase(),
};

function PracticeBadges({ p }) {
  return (
    <>
      {p.tier === "VC" && <em className="badge vc">VC</em>}
      {p.tier === "Freemium" && <em className="badge free">Freemium</em>}
      {p.tier === "Money-back" && <em className="badge mbg">MBG</em>}
      {p.fy_recalls > 1000 && <em className="badge gold" title=">1,000 recalls this FY">1k+ club</em>}
      {!p.in_pipeline && <em className="tag" title="no HubSpot Planner deal">no HS deal</em>}
    </>
  );
}

const nextIcon = (t) => (t === "Visit" ? "📍" : t === "Meeting" ? "📅" : "•");
const VISIT_LABEL = { happened: "Completed", scheduled: "Confirmed", proposed: "Proposed", to_contact: "To contact" };
const todayISO = () => new Date().toISOString().slice(0, 10);

// "Next booked" cell: a firm booking (Confirmed visit / HubSpot meeting) wins;
// else a future Proposed launch; else the last completed visit.
function NextCell({ p }) {
  const today = todayISO();
  if (p.next_step && (p.next_step.date || p.next_step.type !== "Demo"))
    return <span className="t-good" title={p.next_step.source ? `from ${p.next_step.source}` : ""}>
      {nextIcon(p.next_step.type)} {p.next_step.date ? fmtDate(p.next_step.date) : p.next_step.type}</span>;
  const visits = p.visits || [];
  const prop = visits.find((v) => v.date && v.date >= today && (v.status === "proposed" || v.status === "to_contact"));
  if (prop) return <span className="t-warn">~{fmtDate(prop.date)} proposed</span>;
  const past = [...visits].reverse().find((v) => v.date && v.date <= today);
  if (past) return <span className="t-dim">visited {fmtDate(past.date)}</span>;
  if (visits.some((v) => v.status === "proposed" || v.status === "to_contact"))
    return <span className="t-warn">proposed (TBC)</span>;
  if (p.last_visit?.date) return <span className="t-dim">visited {fmtDate(p.last_visit.date)}</span>;
  return <span className="t-dim">—</span>;
}

function LiveNotRecallingTable({ practices, onOpen }) {
  const { clickSort, arrow, sortFn } = useSort({ key: "live", dir: "desc" }, LIVE_SORTS);
  const sorted = [...practices].sort((a, b) => sortFn(a, b, (x, y) => (y.patients || 0) - (x.patients || 0)));
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th className="sortable" onClick={() => clickSort("name")}>Practice{arrow("name")}</th>
          <th className="sortable td-num" onClick={() => clickSort("patients")}>List size{arrow("patients")}</th>
          <th className="sortable" onClick={() => clickSort("live")}>Live for{arrow("live")}</th>
          <th className="sortable" onClick={() => clickSort("next")}>Next booked{arrow("next")}</th>
          <th className="sortable" onClick={() => clickSort("owner")}>Owner{arrow("owner")}</th>
        </tr>
      </thead>
      <tbody>
        {!sorted.length && <tr className="empty"><td colSpan={5}>Every live practice is recalling 🎉</td></tr>}
        {sorted.map((p) => (
          <tr key={p.ods} onClick={() => onOpen(p)}>
            <td><span className="t-name">{p.name}<PracticeBadges p={p} /></span></td>
            <td className="td-num t-dim">{p.patients ? p.patients.toLocaleString() : "—"}</td>
            <td className="t-warn">{p.live_days != null ? `${p.live_days}d` : "—"}</td>
            <td><NextCell p={p} /></td>
            <td className="t-dim">{p.owner || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ================= slide-over panel ================= */

function SlideOver({ onClose, children }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [onClose]);
  return (
    <>
      <div className="slideover-backdrop" onClick={onClose} />
      <aside className="slideover" role="dialog" aria-modal="true">
        {children}
      </aside>
    </>
  );
}

function CopyBtn({ text }) {
  const [done, setDone] = useState(false);
  return (
    <button className="copybtn" title="Copy" onClick={(e) => {
      e.stopPropagation();
      navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1200); });
    }}>{done ? "✓" : "⧉"}</button>
  );
}

function MetaItem({ label, value, copy, plain }) {
  return (
    <div className="so-meta-item">
      <div className="so-meta-label">{label}</div>
      <div className={"so-meta-value" + (plain ? " plain" : "")}>{value}{copy && <CopyBtn text={copy} />}</div>
    </div>
  );
}

function SoRow({ label, children }) {
  return <div className="so-row"><span>{label}</span><em>{children}</em></div>;
}

function Sparkbars({ data, current, tone = "recalls", fmt }) {
  const max = Math.max(1, ...data.map((x) => x.value));
  const lbl = fmt || ((k) => MON[+k.slice(5)] || k);
  return (
    <div className={"dd-spark " + tone}>
      {data.map((x) => (
        <div key={x.key} className="spark-col" title={`${lbl(x.key)}: ${x.value}`}>
          <span className="spark-val">{x.value}</span>
          <div
            className="spark-bar"
            data-cur={x.key === current ? "1" : undefined}
            style={{ height: `${Math.max(3, Math.round((x.value / max) * 46))}px` }}
          />
          <span className="spark-m">{lbl(x.key)}</span>
        </div>
      ))}
    </div>
  );
}

// Recalls + Bloods bar charts with an optional Month/Week toggle (toggle shows
// only when weeklyAvailable — i.e. once a daily-granularity feed is connected).
function MonthlyWeeklyGraphs({ item, weeklyAvailable }) {
  const [gran, setGran] = useState("month");
  const g = weeklyAvailable ? gran : "month";
  const recSeries = g === "week" ? (item.recalls_by_week || {}) : (item.recalls_by_month || {});
  const blSeries = g === "week" ? (item.bloods_by_week || {}) : (item.bloods_by_month || {});
  const now = new Date();
  const monday = new Date(now); monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  const current = g === "week" ? monday.toISOString().slice(0, 10) : now.toISOString().slice(0, 7);
  const fmt = g === "week" ? ((k) => fmtDate(k)) : undefined;
  const toBars = (obj) => Object.keys(obj).sort().map((k) => ({ key: k, value: obj[k] }));
  const recBars = toBars(recSeries), blBars = toBars(blSeries);
  return (
    <>
      {weeklyAvailable && (
        <div className="gran-toggle">
          <button className={g === "month" ? "active" : ""} onClick={() => setGran("month")}>Month</button>
          <button className={g === "week" ? "active" : ""} onClick={() => setGran("week")}>Week</button>
        </div>
      )}
      <div className="dd-spark-wrap">
        <div className="dd-spark-head">
          <span className="so-section-title" style={{ margin: 0 }}>Recalls / {g}</span>
          <span className="dd-spark-fy"><b>{(item.fy_recalls || 0).toLocaleString()}</b> this FY
            {item.fy_recalls_pct != null ? ` · ${item.fy_recalls_pct}% of list` : ""}
            {item.recalls_avg_mo ? ` · ~${item.recalls_avg_mo.toLocaleString()}/mo` : ""}</span>
        </div>
        {recBars.length > 0
          ? <Sparkbars data={recBars} current={current} fmt={fmt} />
          : <span className="dd-spark-none">No recalls yet this FY</span>}
      </div>
      <div className="dd-spark-wrap">
        <div className="dd-spark-head">
          <span className="so-section-title" style={{ margin: 0 }}>Bloods (pathology) / {g}</span>
          <span className="dd-spark-fy"><b>{(item.fy_bloods || 0).toLocaleString()}</b> automated this FY
            {item.fy_bloods_pct != null ? ` · ${item.fy_bloods_pct}% of list` : ""}</span>
        </div>
        {blBars.length > 0
          ? <Sparkbars data={blBars} current={current} tone="bloods" fmt={fmt} />
          : <span className="dd-spark-none">No pathology automated yet</span>}
      </div>
    </>
  );
}

function StageTimelineV({ timeline, daysInStage }) {
  return (
    <ol className="dd-timeline">
      {timeline.map((s, i) => (
        <li key={i} className={"tl-node" + (s.current ? " current" : "")}>
          <span className="tl-dot" />
          <span className="tl-stage">{s.stage}</span>
          <span className="tl-date">{fmtDate(s.date)}</span>
          {s.gap_days != null && <span className="tl-gap">+{s.gap_days}d</span>}
          {s.current && daysInStage != null && (
            <span className="tl-gap now">{daysInStage}d &amp; counting</span>
          )}
        </li>
      ))}
    </ol>
  );
}

// Full onboarding checklist. Interactive in the Onboarding tab: each step is a
// button that cycles todo→pending→done→todo and POSTs a timestamped event to Neon.
function OnboardChecklist({ steps, interactive, onToggle }) {
  const { done, total } = summarizeOnboarding(steps);
  const mark = { done: "✓", pending: "•", todo: "○" };
  const tip = (s) =>
    s.changed_at
      ? `${s.state}${s.changed_by ? " · " + s.changed_by : ""} · ${fmtDate(s.changed_at)}`
      : (s.value || s.state);
  const complete = done === total;
  return (
    <div className="so-section">
      <div className={"so-banner" + (complete ? " ok" : "")}>
        <b>Onboard-ready checklist ({done}/{total})</b>
        <span className="head-flag">{complete ? "Complete" : "Incomplete"}</span>
      </div>
      {interactive && <p className="muted" style={{ margin: "0 0 8px" }}>Click a step to advance it — to&nbsp;do → pending → done. Every change is timestamped.</p>}
      <div className="onb-steps">
        {steps.map((s, i) =>
          interactive ? (
            <button key={i} className={"onb-step btn " + s.state} title={tip(s)}
              onClick={(e) => { e.stopPropagation(); onToggle(s); }}>
              <em>{mark[s.state]}</em> {s.step}
              {s.changed_at ? <i className="onb-val">{fmtDate(s.changed_at)}</i> : null}
            </button>
          ) : (
            <span key={i} className={"onb-step " + s.state} title={tip(s)}>
              <em>{mark[s.state]}</em> {s.step}
              {s.value && s.state !== "todo" ? <i className="onb-val">{s.value}</i> : null}
            </span>
          )
        )}
      </div>
    </div>
  );
}

// Horizontal lifecycle axis: HubSpot stage-entry dates → go-live → first recall.
function JourneyTimeline({ timeline, goLive, firstRecallMonth }) {
  const nodes = (timeline || []).map((s) => ({ label: s.stage, date: s.date, gap: s.gap_days, current: s.current }));
  if (goLive && !nodes.some((n) => /live/i.test(n.label))) nodes.push({ label: "Go live", date: goLive });
  nodes.push(firstRecallMonth
    ? { label: "First recall", month: firstRecallMonth, recall: true }
    : { label: "First recall", pending: true, recall: true });
  return (
    <div className="so-section">
      <h4 className="so-section-title">Journey — signup → live → first recall</h4>
      <ol className="journey">
        {nodes.map((n, i) => (
          <li key={i} className={"jn" + (n.recall ? " recall" : "") + (n.pending ? " pending" : "") + (n.current ? " current" : "")}>
            <span className="jn-dot" />
            <span className="jn-label">{n.label}</span>
            <span className="jn-date">{n.pending ? "not yet" : n.month ? fmtMon(n.month) : fmtDate(n.date)}</span>
            {n.gap != null && <span className="jn-gap">+{n.gap}d</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

// All recall launches on record (Notion) — completed + confirmed + proposed, newest first.
function VisitsList({ visits }) {
  if (!visits || !visits.length) return null;
  const ordered = [...visits].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  return (
    <div className="so-section">
      <h4 className="so-section-title">Recall launches (Notion) <em className="cur-key">{visits.length}</em></h4>
      <ul className="visit-list">
        {ordered.map((v, i) => (
          <li key={i} className="vrow">
            <span className={"status-chip " + (v.status || "")}>{VISIT_LABEL[v.status] || v.status || "Visit"}</span>
            <span className="vdate">{v.date ? fmtDate(v.date) : "—"}</span>
            {v.problems && <span className="vproblems" title={v.problems}>⚠ {v.problems}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ----- deal panel (sales pipeline detail) ----- */

function DealPanel({ d, labelOf, onb, weeklyAvailable }) {
  const effOnb = d.onboarding ? mergeOnboarding(d.onboarding, onb?.live?.[d.ods]) : null;
  return (
    <>
      <div className="so-head">
        <div className="so-titlerow">
          <h2 className="so-title">{d.name}<Badges d={d} /></h2>
        </div>
        <div className="so-sync">{labelOf(d.stage)}{d.recalling ? " · recalling" : ""}{d.stale ? " · stale" : ""}{d.why ? ` — ${d.why}` : ""}</div>
        <div className="so-meta">
          {d.ods && <MetaItem label="ODS code" value={d.ods} copy={d.ods} />}
          <MetaItem label="List size" value={d.patients ? d.patients.toLocaleString() : "—"} plain />
          <MetaItem label="In stage" value={d.days_in_stage != null ? `${d.days_in_stage}d` : "—"} plain />
          <MetaItem label="Owner" value={d.owner || "—"} plain />
        </div>
      </div>
      <div className="so-body">
        <div className="so-section">
          <h4 className="so-section-title">Account details</h4>
          <div className="so-rows">
            <SoRow label="Lead source">{d.source || "—"}</SoRow>
            <SoRow label="ICB">{d.icb || "—"}</SoRow>
            <SoRow label="PCN">{d.pcn_name || "—"}</SoRow>
            <SoRow label="Next step">
              {d.next_step
                ? <>{nextIcon(d.next_step.type)} {d.next_step.type}{d.next_step.date ? ` · ${fmtDate(d.next_step.date)}` : ""}</>
                : <span className="muted">none booked</span>}
            </SoRow>
            <SoRow label="Last email">
              {d.last_email
                ? <>“{d.last_email.subject}” · {fmtDate(d.last_email.date)} ({d.last_email.direction})</>
                : "—"}
            </SoRow>
          </div>
        </div>

        {d.stage_timeline?.length > 0 && (
          <div className="so-section">
            <h4 className="so-section-title">Stage timeline</h4>
            <StageTimelineV timeline={d.stage_timeline} daysInStage={d.days_in_stage} />
          </div>
        )}

        {effOnb?.length > 0 && (
          <OnboardChecklist
            steps={effOnb}
            interactive={!!onb}
            onToggle={onb ? (step) => onb.toggle(d, step) : null}
          />
        )}

        <div className="so-section">
          <h4 className="so-section-title">This month so far</h4>
          <div className="so-rows">
            <SoRow label="Recalls">
              {(d.recalls_this_month || 0).toLocaleString()}{d.recalls_this_month_pct != null ? ` (${d.recalls_this_month_pct}%)` : ""}
            </SoRow>
            {d.bloods_this_month != null && <SoRow label="Bloods">{(d.bloods_this_month || 0).toLocaleString()}</SoRow>}
          </div>
        </div>

        <MonthlyWeeklyGraphs item={d} weeklyAvailable={weeklyAvailable} />
      </div>
    </>
  );
}

/* ----- practice panel (implementation detail) ----- */

function PracticePanel({ p, weeklyAvailable }) {
  const recalling = (p.fy_recalls || 0) > 0;
  return (
    <>
      <div className="so-head">
        <div className="so-titlerow">
          <h2 className="so-title">{p.name}<PracticeBadges p={p} /></h2>
        </div>
        <div className="so-sync">
          {p.live ? "Live (onboarding sheet)" : "Not in Live sheet"} · {p.in_pipeline ? "in HubSpot Planner pipeline" : "no HubSpot Planner deal"}
        </div>
        <div className="so-meta">
          <MetaItem label="ODS code" value={p.ods} copy={p.ods} />
          <MetaItem label="List size" value={p.patients ? p.patients.toLocaleString() : "—"} plain />
          <MetaItem label="Tier" value={p.tier || "—"} plain />
          <MetaItem label="Owner" value={p.owner || "—"} plain />
        </div>
      </div>
      <div className="so-body">
        <div className={"so-banner" + (recalling ? " ok" : "")}>
          <b>{recalling
            ? `${(p.fy_recalls || 0).toLocaleString()} recalls this FY${p.fy_recalls_pct != null ? ` · ${p.fy_recalls_pct}% of list` : ""}`
            : "No recalls yet this FY — activation gap"}</b>
          <span className="head-flag">{recalling ? "Recalling" : "Not recalling"}</span>
        </div>

        <div className="so-section">
          <h4 className="so-section-title">Account details</h4>
          <div className="so-rows">
            <SoRow label="Lead source">{p.source || "—"}</SoRow>
            <SoRow label="ICB">{p.icb || "—"}</SoRow>
            <SoRow label="PCN">{p.pcn_name || "—"}</SoRow>
            <SoRow label="Next booked"><NextCell p={p} /></SoRow>
          </div>
        </div>

        <JourneyTimeline timeline={p.stage_timeline} goLive={p.go_live} firstRecallMonth={p.first_recall_month} />
        <VisitsList visits={p.visits} />
        <MonthlyWeeklyGraphs item={p} weeklyAvailable={weeklyAvailable} />
      </div>
    </>
  );
}
