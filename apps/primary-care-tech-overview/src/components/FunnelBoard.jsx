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
const fmtMonth = (m) => `${MON[+m.slice(5)] || m} ${""}`.trim();
const fmtMon = (ym) => (ym ? `${MON[+ym.slice(5, 7)] || ""} ${ym.slice(2, 4)}`.trim() : "");

const SCOPE_DESC = {
  overview: "The whole flow — signed-up through live, recalling and volumes.",
  partnerships: "Sales: signed-up list → DPA signed. Everything here lives in HubSpot.",
  onboarding: "Onboarding: DPA signed & onboard-ready, not yet live. Each step is a button — changes are timestamped.",
  implementation: "Implementation: live practices — first the activation gap (not yet recalling), then the recallers.",
};

export default function FunnelBoard({ data, scope = "overview", stages = null, auth = null }) {
  const [ehr, setEhr] = useState("All");
  const visibleOrder = stages || ORDER;
  const [open, setOpen] = useState(() =>
    scope === "implementation" ? "live"
      : visibleOrder.includes("dpa_signed") ? "dpa_signed" : visibleOrder[0]
  );
  const [showWeekly, setShowWeekly] = useState(false);
  const showExtras = scope === "overview" || scope === "partnerships";
  const isOnboarding = scope === "onboarding";
  const isImpl = scope === "implementation";
  const weeklyAvailable = !!data?.weekly_available;

  // live onboarding step state (Neon) + who is editing (for changed_by)
  const [liveOnb, setLiveOnb] = useState({});
  const [who, setWho] = useState(() => (typeof localStorage !== "undefined" && localStorage.getItem("pcto.who")) || "");
  useEffect(() => {
    if (!isOnboarding) return;
    fetch(ONB_BASE).then((r) => r.json()).then(setLiveOnb).catch(() => {});
  }, [isOnboarding]);

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
  const onb = isOnboarding ? { live: liveOnb, who: editor, toggle: toggleStep } : null;

  const deals = useMemo(() => {
    const all = data?.deals || [];
    return ehr === "All" ? all : all.filter((d) => (d.ehr || "Unknown") === ehr);
  }, [data, ehr]);

  const stageMeta = useMemo(
    () => Object.fromEntries((data?.stages || []).map((s) => [s.key, s])),
    [data]
  );
  const labelOf = (key) => stageMeta[key]?.label || key;

  const stageData = visibleOrder.map((key) => {
    const inStage =
      key === "recalling"
        ? deals.filter((d) => d.stage === "live" && d.recalling)
        : deals.filter((d) => d.stage === key);
    return { key, label: labelOf(key), deals: inStage, count: inStage.length, stale: inStage.filter((d) => d.stale) };
  });
  const maxCount = Math.max(1, ...stageData.map((s) => s.count));
  const wl = deals.filter((d) => d.stage === "waitlist");
  const emisWl = wl.filter((d) => d.ehr === "EMIS").length;
  const tppWl = wl.filter((d) => d.ehr === "SystmOne").length;
  const ghosts = deals.filter((d) => d.stage === "live" && !d.recalling);
  const actNow = deals.filter((d) => d.stale).length;
  const booked = deals.filter((d) => d.next_step).length;

  const insight = (s) => {
    switch (s.key) {
      case "waitlist": return `${emisWl} EMIS ready · ${tppWl} TPP (live in ~2 wks)`;
      case "demo_booked": return `${s.count} booked`;
      case "demo_held": return s.stale.length ? `${s.stale.length} stale >14d — no DPA sent` : "moving";
      case "dpa_sent": return s.stale.length ? `${s.stale.length} stale — chase signature` : "moving";
      case "dpa_signed": return `${s.stale.length} stuck >21d, no go-live booked — THE bottleneck`;
      case "live": return `${ghosts.length} live but not recalling (ghosts)`;
      case "recalling": return "actively recalling ✅";
      default: return "";
    }
  };

  const weeks = (data.weekly || []).slice(-6);
  const convSteps = visibleOrder.slice(1); // every visible stage after the first has a conv

  // Implementation tab = live practices, ODS-based (recalls.json + the Live sheet), in two groups:
  //   1. Live but NOT yet recalling — the activation gap (first-recall worklist).
  //   2. Recalling — the full recalling cohort (incl. VC + practices with no HubSpot deal).
  if (isImpl) {
    const rp = data.recalling_practices || [];
    const lnr = data.live_not_recalling || [];
    const totRec = rp.reduce((a, p) => a + (p.fy_recalls || 0), 0);
    const totBl = rp.reduce((a, p) => a + (p.fy_bloods || 0), 0);
    return (
      <div className="board">
        <div className="board-head"><div className="board-desc">{SCOPE_DESC.implementation}</div></div>
        <div className="funnel-topstrip">
          <div className="stat bad"><b>{lnr.length}</b><span>live but not yet recalling</span></div>
          <div className="stat"><b>{rp.length}</b><span>actively recalling this FY</span></div>
          <div className="stat"><b>{totRec.toLocaleString()}</b><span>recalls this FY</span></div>
          <div className="stat"><b>{totBl.toLocaleString()}</b><span>bloods automated this FY</span></div>
        </div>

        <div className="impl-section">
          <h3 className="impl-h">⚠️ Live — not yet recalling <em>{lnr.length}</em></h3>
          <p className="impl-sub">Functionally live but zero recalls this FY — the activation gap. Longest-live first.</p>
          <LiveNotRecallingTable practices={lnr} weeklyAvailable={weeklyAvailable} />
        </div>

        <div className="impl-section">
          <h3 className="impl-h">✅ Recalling <em>{rp.length}</em></h3>
          <p className="impl-sub">Sourced from <code>recalls.json</code> (the Omni feed) — every recaller, incl. VC-tier
            and practices with no HubSpot Planner deal. Click a header to sort · green shade = % of list recalled.</p>
          <RecallingTable practices={rp} weeklyAvailable={weeklyAvailable} />
        </div>
      </div>
    );
  }

  return (
    <div className="board">
      <div className="board-head">
        <div className="board-desc">{SCOPE_DESC[scope]}</div>
        {showExtras && (
          <button className="weekly-toggle" onClick={() => setShowWeekly((v) => !v)}>
            {showWeekly ? "Hide" : "📅 Week-by-week"}
          </button>
        )}
        {isOnboarding && auth?.email && <span className="who-field">Editing as <b>{auth.email}</b></span>}
        {isOnboarding && !auth?.email && (
          <label className="who-field">You:
            <input value={who} placeholder="your name" onChange={(e) => { setWho(e.target.value); localStorage.setItem("pcto.who", e.target.value); }} />
          </label>
        )}
      </div>

      {showExtras && (
        <div className="funnel-topstrip">
          <div className="stat bad"><b>{actNow}</b><span>stale · nothing booked → act now</span></div>
          <div className="stat"><b>{booked}</b><span>have a next step booked</span></div>
          <div className="stat"><b>{ghosts.length}</b><span>live but not recalling</span></div>
        </div>
      )}

      {showExtras && <ChaseList deals={deals} labelOf={labelOf} />}

      {showWeekly && (
        <div className="weekly-card">
          <table className="weekly-table">
            <thead>
              <tr>
                <th>Conversion %</th>
                {weeks.map((w) => <th key={w.week}>{fmtDate(w.week)}</th>)}
                <th>Δ wk</th>
              </tr>
            </thead>
            <tbody>
              {convSteps.map((key) => {
                const series = weeks.map((w) => w.conv[key]);
                const d = stageMeta[key]?.conv_delta_1w;
                return (
                  <tr key={key}>
                    <td className="wk-step">↳ {labelOf(key)}</td>
                    {series.map((v, i) => <td key={i}>{v == null ? "—" : `${v}%`}</td>)}
                    <td className={"wk-delta " + (d > 0 ? "up" : d < 0 ? "down" : "")}>
                      {d == null ? "—" : (d > 0 ? `+${d}` : d)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="muted">Reconstructed from HubSpot stage-entry timestamps · overall (all EHR).</div>
        </div>
      )}

      <div className="ehrchips">
        {["All", "EMIS", "SystmOne", "Unknown"].map((x) => (
          <button key={x} className={ehr === x ? "chip active" : "chip"} onClick={() => setEhr(x)}>
            {x === "SystmOne" ? "TPP/S1" : x}
          </button>
        ))}
        <span className="muted">TPP onboarding goes live in ~2 weeks → its waitlist becomes actionable</span>
      </div>

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
                  (s.key === "recalling" ? " activation" : "") +
                  (isBottleneck ? " bottleneck" : "") +
                  (open === s.key ? " open" : "")
                }
                onClick={() => setOpen(open === s.key ? null : s.key)}
              >
                <div className="fs-bar-area">
                  <div className="fs-bar" style={{ width }}>
                    <span className="fs-label">{s.key === "recalling" ? "✅ Recalling" : s.label}</span>
                    <span className="fs-count">{s.count}</span>
                  </div>
                </div>
                <div className="fs-meta">
                  <span className={"fs-insight" + (isBottleneck ? " bad" : "")}>{insight(s)}</span>
                  {ACTION[s.key] && s.stale.length > 0 && <span className="fs-action">{ACTION[s.key]} →</span>}
                  {s.stale.length > 0 && <span className="fs-stale">▲ {s.stale.length} stale</span>}
                </div>
              </div>
              {open === s.key && <DealList deals={s.deals} stageKey={s.key} onb={onb} weeklyAvailable={weeklyAvailable} />}
            </div>
          );
        })}
      </div>

      <div className="muted" style={{ marginTop: 16 }}>
        Bars = deals currently in each stage · % = overall step conversion with week-on-week change ·
        click a deal to expand details · Live is sorted by recall penetration — green shade = % of list recalled (deepest = highest).
        {data.next_step_source.includes("unavailable") && " (HubSpot meetings unavailable this run.)"}
      </div>
    </div>
  );
}

// days-since-last-email cell: red past 14 days or when unknown-but-relevant
function EmailAge({ days, muteUnknown }) {
  if (days == null) return <span className={"d-email" + (muteUnknown ? " muted" : " bad")}>—</span>;
  return <span className={"d-email" + (days > 14 ? " bad" : "")}>{days}d ago</span>;
}

// "Needs a chase" worklist — won/near-won deals that have gone stale (no next step booked)
function ChaseList({ deals, labelOf }) {
  const [open, setOpen] = useState(true);
  const chase = deals.filter((d) => d.needs_chase)
    .sort((a, b) => (b.days_in_stage || 0) - (a.days_in_stage || 0));
  if (!chase.length) return null;
  const CAP = 15;
  const reason = (d) => {
    if (d.stage === "dpa_signed" && d.onboarding) {
      const next = d.onboarding.find((s) => s.state !== "done");
      return next ? `blocked: ${next.step}` : "onboarding complete — book go-live";
    }
    return d.why;
  };
  return (
    <div className="chase-card">
      <button className="chase-head" onClick={() => setOpen((v) => !v)}>
        <span>🔥 Needs a chase <b>{chase.length}</b></span>
        <span className="chase-sub">won / near-won deals gone stale — oldest first {open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="chase-rows">
          <div className="chase-row head">
            <span>Practice</span><span>Stage</span><span>Stalled</span><span>Blocker / why</span><span>Last email</span><span>Owner</span>
          </div>
          {chase.slice(0, CAP).map((d) => (
            <div key={d.deal_id} className="chase-row">
              <span className="c-name">{d.name}{d.ehr === "SystmOne" && <em className="tag">TPP</em>}</span>
              <span className="c-stage">{labelOf(d.stage)}</span>
              <span className="c-days">{d.days_in_stage != null ? `${d.days_in_stage}d` : "—"}</span>
              <span className="c-why">{reason(d)}</span>
              <EmailAge days={d.days_since_email} />
              <span className="c-owner">{d.owner || "—"}</span>
            </div>
          ))}
          {chase.length > CAP && <div className="chase-more">+{chase.length - CAP} more — open the stages below to see all</div>}
        </div>
      )}
    </div>
  );
}

// green shade scales with recall penetration (% of list); deeper = higher
const recallShade = (pct) =>
  pct == null ? undefined : { background: `hsl(158, 52%, ${Math.max(72, 95 - Math.min(pct, 11) * 2.1)}%)` };

function Badges({ d }) {
  return (
    <>
      {d.fy_recalls > 1000 && <em className="badge gold" title=">1,000 recalls this FY">🏆 1k+</em>}
      {d.tier === "Money-back" && <em className="badge mbg" title="Money-back guarantee (paying)">MBG</em>}
      {d.tier === "Freemium" && <em className="badge free">Freemium</em>}
      {d.tier === "VC" && <em className="badge vc">VC</em>}
    </>
  );
}

function DealList({ deals, stageKey, onb, weeklyAvailable }) {
  const [openId, setOpenId] = useState(null);
  const isLive = stageKey === "live" || stageKey === "recalling";
  const shade = (x) => (x.recalling ? (x.fy_recalls_pct ?? 0.01) : x.stale ? -2 : -1);
  const sorted = [...deals].sort((a, b) => {
    if (isLive) {                               // sort by colour shade: deepest green → red
      const d = shade(b) - shade(a);
      if (d) return d;
      return (b.days_in_stage || 0) - (a.days_in_stage || 0);
    }
    const sa = a.stale ? 0 : 1, sb = b.stale ? 0 : 1;   // other stages: stale (act-now) first
    if (sa !== sb) return sa - sb;
    return (b.days_in_stage || 0) - (a.days_in_stage || 0);
  });
  if (!sorted.length) return <div className="deallist empty">No deals in this stage.</div>;
  return (
    <div className={"deallist" + (isLive ? " live" : "")}>
      <div className="dealrow head">
        <span>Practice</span>
        <span>{isLive ? "Live for" : "In stage"}</span>
        {!isLive && <span>Next step</span>}
        <span>{isLive ? "Recalls this FY" : "Why"}</span>
        {!isLive && <span>Last email</span>}
        <span>Owner</span>
      </div>
      {sorted.map((d) => {
        const isOpen = openId === d.deal_id;
        const recStyle = d.recalling ? recallShade(d.fy_recalls_pct) : undefined;
        const effOnb = d.onboarding ? mergeOnboarding(d.onboarding, onb?.live?.[d.ods]) : null;
        return (
          <React.Fragment key={d.deal_id}>
            <div
              className={
                "dealrow" + (d.stale ? " stale" : "") + (d.recalling ? " recalling" : "") +
                (isOpen ? " expanded" : "")
              }
              style={recStyle}
              onClick={() => setOpenId(isOpen ? null : d.deal_id)}
            >
              <span className="d-name">
                <em className="caret">{isOpen ? "▾" : "▸"}</em>
                {d.name}
                {d.ehr === "SystmOne" && <em className="tag">TPP</em>}
                {d.ehr === "EMIS" && <em className="tag emis">EMIS</em>}
                {isLive && <Badges d={d} />}
              </span>
              <span className="d-days">{d.days_in_stage != null ? `${d.days_in_stage}d` : "—"}</span>
              {!isLive && (
                <span className="d-next">
                  {d.next_step
                    ? `✅ ${d.next_step.type}${d.next_step.date ? " " + fmtDate(d.next_step.date) : ""}`
                    : "❌ none"}
                </span>
              )}
              <span className={"d-why" + (d.stale ? " bad" : "") + (d.recalling ? " good" : "")}>
                {stageKey === "dpa_signed" && effOnb ? <OnboardWhy steps={effOnb} /> : d.why}
              </span>
              {!isLive && <EmailAge days={d.days_since_email} muteUnknown />}
              <span className="d-owner">{d.owner || "—"}</span>
            </div>
            {isOpen && <DealDetail d={d} effOnb={effOnb} onb={onb} weeklyAvailable={weeklyAvailable} />}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function summarizeOnboarding(steps) {
  const done = steps.filter((s) => s.state === "done").length;
  const next = steps.find((s) => s.state !== "done");
  return { done, total: steps.length, next: next ? next.step : null };
}

// Compact onboarding progress shown in the DPA-Signed row's "why" cell
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

// Full onboarding checklist shown in the dropdown. Interactive in the Onboarding
// tab: each step is a button that cycles todo→pending→done→todo and POSTs a
// timestamped event to Neon. Tooltip shows who changed it + when.
function OnboardChecklist({ steps, interactive, onToggle }) {
  const { done, total } = summarizeOnboarding(steps);
  const mark = { done: "✓", pending: "•", todo: "○" };
  const tip = (s) =>
    s.changed_at
      ? `${s.state}${s.changed_by ? " · " + s.changed_by : ""} · ${fmtDate(s.changed_at)}`
      : (s.value || s.state);
  return (
    <div className="dd-onboard">
      <span className="dd-spark-label">
        Onboard-ready checklist <em className="cur-key">{done}/{total} done</em>
        {interactive && <em className="onb-hint">— click a step to advance (timestamped)</em>}
      </span>
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
            style={{ height: `${Math.max(3, Math.round((x.value / max) * 42))}px` }}
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
          <span className="dd-spark-label">Recalls / {g}</span>
          <span className="dd-spark-fy"><b>{(item.fy_recalls || 0).toLocaleString()}</b> this FY
            {item.fy_recalls_pct != null ? ` · ${item.fy_recalls_pct}% of list` : ""}
            {item.recalls_avg_mo ? ` · ~${item.recalls_avg_mo.toLocaleString()}/mo` : ""}</span>
          {recBars.length > 0 && <em className="cur-key">▮ current</em>}
        </div>
        {recBars.length > 0
          ? <Sparkbars data={recBars} current={current} fmt={fmt} />
          : <span className="dd-spark-none">No recalls yet this FY</span>}
      </div>
      <div className="dd-spark-wrap">
        <div className="dd-spark-head">
          <span className="dd-spark-label">Bloods (pathology) / {g}</span>
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

function StageTimeline({ timeline, daysInStage }) {
  return (
    <div className="dd-timeline-wrap">
      <span className="dd-spark-label">Stage timeline</span>
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
    </div>
  );
}

function DealDetail({ d, effOnb, onb, weeklyAvailable }) {
  return (
    <div className="deal-detail">
      <div className="dd-grid">
        <div><span>Lead source</span><b>{d.source || "—"}</b></div>
        <div><span>List size</span><b>{d.patients ? d.patients.toLocaleString() : "—"}</b></div>
        <div><span>ICB</span><b>{d.icb || "—"}</b></div>
        <div><span>PCN</span><b>{d.pcn_name || "—"}</b></div>
      </div>
      <div className="dd-line">
        <span>Last email</span>
        <em>{d.last_email
          ? <>“{d.last_email.subject}” · <b>{fmtDate(d.last_email.date)}</b> ({d.last_email.direction})</>
          : "—"}</em>
      </div>
      {d.stage_timeline?.length > 0 && <StageTimeline timeline={d.stage_timeline} daysInStage={d.days_in_stage} />}
      {d.onboarding?.length > 0 && (
        <OnboardChecklist
          steps={effOnb || d.onboarding}
          interactive={!!onb}
          onToggle={onb ? (step) => onb.toggle(d, step) : null}
        />
      )}
      <div className="dd-line traction">
        <span>This month so far</span>
        <em><b>{(d.recalls_this_month || 0).toLocaleString()}</b> recalls
          {d.recalls_this_month_pct != null ? ` (${d.recalls_this_month_pct}%)` : ""}
          {d.bloods_this_month ? ` · ${d.bloods_this_month.toLocaleString()} bloods` : ""}</em>
      </div>
      <MonthlyWeeklyGraphs item={d} weeklyAvailable={weeklyAvailable} />
    </div>
  );
}

// ===== Implementation tab: the full recalling cohort (ODS-based, from recalls.json) =====
const RECALL_SORTS = {
  name: (p) => (p.name || "").toLowerCase(),
  fy: (p) => p.fy_recalls || 0,
  bloods: (p) => p.fy_bloods || 0,
  mo: (p) => p.recalls_this_month || 0,
  owner: (p) => (p.owner || "").toLowerCase(),
};

function RecallingTable({ practices, weeklyAvailable }) {
  const [openId, setOpenId] = useState(null);
  const [sort, setSort] = useState({ key: "fy", dir: "desc" });
  const clickSort = (key) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
      : { key, dir: key === "name" || key === "owner" ? "asc" : "desc" }));
  const arrow = (key) => (sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : "");
  const sorted = [...practices].sort((a, b) => {
    const f = RECALL_SORTS[sort.key] || RECALL_SORTS.fy;
    const av = f(a), bv = f(b);
    const c = typeof av === "string" ? av.localeCompare(bv) : av - bv;
    return (sort.dir === "asc" ? c : -c) || (b.fy_recalls || 0) - (a.fy_recalls || 0);
  });
  if (!sorted.length) return <div className="deallist empty">No recalling practices yet.</div>;
  return (
    <div className="deallist recalls">
      <div className="dealrow head sortable-head">
        <span className="sortable" onClick={() => clickSort("name")}>Practice{arrow("name")}</span>
        <span className="sortable" onClick={() => clickSort("fy")}>Recalls this FY{arrow("fy")}</span>
        <span className="sortable" onClick={() => clickSort("mo")}>This mo{arrow("mo")}</span>
        <span className="sortable" onClick={() => clickSort("owner")}>Owner{arrow("owner")}</span>
      </div>
      {sorted.map((p) => {
        const isOpen = openId === p.ods;
        return (
          <React.Fragment key={p.ods}>
            <div className="dealrow recalling" style={recallShade(p.fy_recalls_pct)} onClick={() => setOpenId(isOpen ? null : p.ods)}>
              <span className="d-name">
                <em className="caret">{isOpen ? "▾" : "▸"}</em>
                {p.name}
                {p.tier === "VC" && <em className="badge vc">VC</em>}
                {p.tier === "Freemium" && <em className="badge free">Freemium</em>}
                {p.tier === "Money-back" && <em className="badge mbg">MBG</em>}
                {p.fy_recalls > 1000 && <em className="badge gold" title=">1,000 recalls this FY">🏆 1k+</em>}
                {!p.in_pipeline && <em className="tag" title="recalling but no HubSpot Planner deal">no HS deal</em>}
              </span>
              <span className="d-why good">
                {(p.fy_recalls || 0).toLocaleString()} recalls{p.fy_recalls_pct != null ? ` (${p.fy_recalls_pct}%)` : ""}
                {" · "}{(p.fy_bloods || 0).toLocaleString()} bloods{p.fy_bloods_pct != null ? ` (${p.fy_bloods_pct}%)` : ""}
              </span>
              <span className="d-email">{(p.recalls_this_month || 0).toLocaleString()}</span>
              <span className="d-owner">{p.owner || "—"}</span>
            </div>
            {isOpen && <RecallingDetail p={p} weeklyAvailable={weeklyAvailable} />}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function RecallingDetail({ p, weeklyAvailable }) {
  return (
    <div className="deal-detail">
      <div className="dd-grid">
        <div><span>List size</span><b>{p.patients ? p.patients.toLocaleString() : "—"}</b></div>
        <div><span>Lead source</span><b>{p.source || "—"}</b></div>
        <div><span>Tier</span><b>{p.tier || "—"}</b></div>
        <div><span>ICB</span><b>{p.icb || "—"}</b></div>
        <div><span>PCN</span><b>{p.pcn_name || "—"}</b></div>
      </div>
      <JourneyTimeline timeline={p.stage_timeline} goLive={p.go_live} firstRecallMonth={p.first_recall_month} />
      <NextStepLine next={p.next_step} />
      <VisitsList visits={p.visits} />
      <div className="dd-line">
        <span>Status</span>
        <em>{p.live ? "Live (onboarding sheet)" : "not in Live sheet"} · {p.in_pipeline ? "in HubSpot Planner pipeline" : "no HubSpot Planner deal"} · ODS {p.ods}</em>
      </div>
      <MonthlyWeeklyGraphs item={p} weeklyAvailable={weeklyAvailable} />
    </div>
  );
}

// Horizontal lifecycle axis: HubSpot stage-entry dates → go-live → first recall.
// Gap labels (+Nd) show dwell time between stages; the terminal recall node is
// green when achieved, a dashed "not yet" when the practice hasn't recalled.
function JourneyTimeline({ timeline, goLive, firstRecallMonth }) {
  const nodes = (timeline || []).map((s) => ({ label: s.stage, date: s.date, gap: s.gap_days, current: s.current }));
  if (goLive && !nodes.some((n) => /live/i.test(n.label))) nodes.push({ label: "Go live", date: goLive });
  nodes.push(firstRecallMonth
    ? { label: "First recall", month: firstRecallMonth, recall: true }
    : { label: "First recall", pending: true, recall: true });
  return (
    <div className="dd-journey">
      <span className="dd-spark-label">Journey — signup → live → first recall</span>
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

const nextIcon = (t) => (t === "Visit" ? "📍" : t === "Meeting" ? "📅" : "•");
const VISIT_LABEL = { happened: "Completed", scheduled: "Confirmed", proposed: "Proposed", to_contact: "To contact" };
const todayISO = () => new Date().toISOString().slice(0, 10);

// "Next booked" cell for the activation table: a firm booking (Confirmed visit /
// HubSpot meeting) wins; else a future Proposed launch; else the last completed visit.
function NextCell({ p }) {
  const today = todayISO();
  if (p.next_step && (p.next_step.date || p.next_step.type !== "Demo"))
    return <span className="d-next booked" title={p.next_step.source ? `from ${p.next_step.source}` : ""}>
      {nextIcon(p.next_step.type)} {p.next_step.date ? fmtDate(p.next_step.date) : p.next_step.type}</span>;
  const visits = p.visits || [];
  const prop = visits.find((v) => v.date && v.date >= today && (v.status === "proposed" || v.status === "to_contact"));
  if (prop) return <span className="d-next prop">~{fmtDate(prop.date)} proposed</span>;
  const past = [...visits].reverse().find((v) => v.date && v.date <= today);
  if (past) return <span className="d-next past">visited {fmtDate(past.date)}</span>;
  if (visits.some((v) => v.status === "proposed" || v.status === "to_contact"))
    return <span className="d-next prop">proposed (TBC)</span>;
  if (p.last_visit?.date) return <span className="d-next past">visited {fmtDate(p.last_visit.date)}</span>;
  return <span className="d-next none">—</span>;
}

// "Next booked" detail line — the next firm touchpoint (Confirmed visit / HubSpot meeting).
function NextStepLine({ next }) {
  const hasNext = next && (next.date || next.type !== "Demo");
  return (
    <div className="dd-line">
      <span>Next booked</span>
      <em>
        {hasNext
          ? <><b>{nextIcon(next.type)} {next.type}</b>{next.date ? ` · ${fmtDate(next.date)}` : ""}{next.source ? ` (${next.source})` : ""}</>
          : <span className="muted">none upcoming</span>}
      </em>
    </div>
  );
}

// All recall launches on record (Notion) — completed + confirmed + proposed, newest first.
function VisitsList({ visits }) {
  if (!visits || !visits.length) return null;
  const ordered = [...visits].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  return (
    <div className="dd-visits">
      <span className="dd-spark-label">Recall launches (Notion) <em className="cur-key">{visits.length}</em></span>
      <ul className="visit-list">
        {ordered.map((v, i) => (
          <li key={i} className={"vrow " + (v.status || "")}>
            <span className={"vstatus " + (v.status || "")}>{VISIT_LABEL[v.status] || v.status || "Visit"}</span>
            <span className="vdate">{v.date ? fmtDate(v.date) : "—"}</span>
            {v.problems && <span className="vproblems" title={v.problems}>⚠ {v.problems}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ===== Implementation tab, group 1: live but NOT yet recalling (the activation gap) =====
const LIVE_SORTS = {
  name: (p) => (p.name || "").toLowerCase(),
  patients: (p) => p.patients || 0,
  live: (p) => p.live_days || 0,
  next: (p) => (p.next_step?.date ? p.next_step.date : p.last_visit?.date ? "8" + p.last_visit.date : "9999"),
  owner: (p) => (p.owner || "").toLowerCase(),
};

function LiveNotRecallingTable({ practices, weeklyAvailable }) {
  const [openId, setOpenId] = useState(null);
  const [sort, setSort] = useState({ key: "live", dir: "desc" });
  const clickSort = (key) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
      : { key, dir: key === "name" || key === "owner" ? "asc" : "desc" }));
  const arrow = (key) => (sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : "");
  const sorted = [...practices].sort((a, b) => {
    const f = LIVE_SORTS[sort.key] || LIVE_SORTS.live;
    const av = f(a), bv = f(b);
    const c = typeof av === "string" ? av.localeCompare(bv) : av - bv;
    return (sort.dir === "asc" ? c : -c) || (b.patients || 0) - (a.patients || 0);
  });
  if (!sorted.length) return <div className="deallist empty">Every live practice is recalling 🎉</div>;
  return (
    <div className="deallist livegap">
      <div className="dealrow head sortable-head">
        <span className="sortable" onClick={() => clickSort("name")}>Practice{arrow("name")}</span>
        <span className="sortable" onClick={() => clickSort("patients")}>List size{arrow("patients")}</span>
        <span className="sortable" onClick={() => clickSort("live")}>Live for{arrow("live")}</span>
        <span className="sortable" onClick={() => clickSort("next")}>Next booked{arrow("next")}</span>
        <span className="sortable" onClick={() => clickSort("owner")}>Owner{arrow("owner")}</span>
      </div>
      {sorted.map((p) => {
        const isOpen = openId === p.ods;
        return (
          <React.Fragment key={p.ods}>
            <div className="dealrow" onClick={() => setOpenId(isOpen ? null : p.ods)}>
              <span className="d-name">
                <em className="caret">{isOpen ? "▾" : "▸"}</em>
                {p.name}
                {p.tier === "VC" && <em className="badge vc">VC</em>}
                {p.tier === "Freemium" && <em className="badge free">Freemium</em>}
                {p.tier === "Money-back" && <em className="badge mbg">MBG</em>}
                {!p.in_pipeline && <em className="tag" title="live but no HubSpot Planner deal">no HS deal</em>}
              </span>
              <span className="d-why">{p.patients ? p.patients.toLocaleString() : "—"}</span>
              <span className="d-email">{p.live_days != null ? `${p.live_days}d` : "—"}</span>
              <NextCell p={p} />
              <span className="d-owner">{p.owner || "—"}</span>
            </div>
            {isOpen && <RecallingDetail p={p} weeklyAvailable={weeklyAvailable} />}
          </React.Fragment>
        );
      })}
    </div>
  );
}
