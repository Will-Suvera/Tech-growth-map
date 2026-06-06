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

const SCOPE_DESC = {
  overview: "The whole flow — signed-up through live, recalling and volumes.",
  partnerships: "Sales: signed-up list → DPA signed. Everything here lives in HubSpot.",
  onboarding: "Onboarding: DPA signed → fully live. Each step is a button — changes are timestamped.",
  implementation: "Implementation: live → actively recalling, with recall volumes.",
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
              {open === s.key && <DealList deals={s.deals} stageKey={s.key} onb={onb} />}
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

function DealList({ deals, stageKey, onb }) {
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
            {isOpen && <DealDetail d={d} effOnb={effOnb} onb={onb} />}
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

function Sparkbars({ data, current }) {
  const max = Math.max(1, ...data.map((x) => x.value));
  return (
    <div className="dd-spark">
      {data.map((x) => (
        <div key={x.month} className="spark-col" title={`${x.month}: ${x.value} recalls`}>
          <span className="spark-val">{x.value}</span>
          <div
            className="spark-bar"
            data-cur={x.month === current ? "1" : undefined}
            style={{ height: `${Math.max(3, Math.round((x.value / max) * 42))}px` }}
          />
          <span className="spark-m">{MON[+x.month.slice(5)] || x.month}</span>
        </div>
      ))}
    </div>
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

function DealDetail({ d, effOnb, onb }) {
  const recM = d.recalls_by_month || {};
  const months = Object.keys(recM).sort();
  const cur = new Date().toISOString().slice(0, 7);
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
      <div className="dd-line">
        <span>Recalls this FY</span>
        <em><b>{(d.fy_recalls || 0).toLocaleString()}</b>
          {d.fy_recalls_pct != null ? ` · ${d.fy_recalls_pct}% of list` : ""}
          {d.recalls_avg_mo ? ` · ~${d.recalls_avg_mo.toLocaleString()}/mo` : ""}</em>
      </div>
      <div className="dd-line">
        <span>Pathology this FY</span>
        <em><b>{(d.fy_bloods || 0).toLocaleString()}</b> automated
          {d.fy_bloods_pct != null ? ` · ${d.fy_bloods_pct}% of list` : ""}</em>
      </div>
      {months.length > 0 && (
        <div className="dd-spark-wrap">
          <span className="dd-spark-label">Recalls / month <em className="cur-key">▮ this month</em></span>
          <Sparkbars data={months.map((m) => ({ month: m, value: recM[m] }))} current={cur} />
        </div>
      )}
    </div>
  );
}
