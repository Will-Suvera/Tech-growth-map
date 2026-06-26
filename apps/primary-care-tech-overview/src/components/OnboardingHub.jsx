import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import "./OnboardingHub.css";
import { useOnboarding, mergeOnboarding, summarizeOnboarding, firstNameFromEmail, WAITING_ON, WAITING_LABEL } from "../onboarding.js";

// The Onboarding Hub: the CS team's action surface for DPA-signed-onwards
// practices. It answers "who needs to do what, and why can't we move forward":
// progress + blocked-on-whom + booked touchpoints, with one-click mark-live.

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "");
const fmtDateTime = (s) =>
  s ? new Date(s).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
const fmtTime = (s) => { try { return new Date(s).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ") : "");
const MARK = { done: "✓", pending: "•", todo: "○" };
const STALL_DAYS = 14; // fallback when funnel_board.json carries no stage threshold
const daysSince = (iso) => (iso ? Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 86400000)) : null);
const localISO = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
// Calendar day key. A timed ISO (has "T", may carry a UTC offset) is placed on its
// LOCAL day so the cell agrees with the local time we show; a plain "YYYY-MM-DD"
// (Notion visit) is a calendar date already and is used verbatim.
const dayKey = (s) => (s && String(s).includes("T") ? localISO(new Date(s)) : String(s || "").slice(0, 10));

// HubSpot deep link — Suvera is on the EU instance, portal 143576889 (see pipeline/refresh_data.py).
const HS_PORTAL = "143576889";
const hubspotDealUrl = (deal_id) => (deal_id ? `https://app-eu1.hubspot.com/contacts/${HS_PORTAL}/record/0-3/${encodeURIComponent(deal_id)}` : null);

// Cohort = HubSpot Planner deals at DPA-signed or beyond, with an ODS code.
const inCohort = (d) => (d.stage === "dpa_signed" || d.stage === "live") && d.ods;

function statusOf(d) {
  if (d.stage === "dpa_signed") return { key: "st-dpa", label: "DPA signed", group: "dpa" };
  if (d.recalling) return { key: "st-recalling", label: "Live — recalling", group: "recalling" };
  return { key: "st-live", label: "Live — not recalling", group: "live" };
}

// Recall/implementation session lookup (Notion practice_visits.json, keyed by ODS).
function recallFor(visits, ods) {
  if (!visits || !ods) return null;
  return visits[ods] || visits[ods.toUpperCase()] || null;
}
// All recorded occurrences of a practice's recall sessions (current + history).
function recallOccurrences(v) {
  if (!v) return [];
  return [{ date: v.date, status: v.status, times: v.times }, ...(v.history || [])].filter((x) => x.date);
}
function futureRecalls(v, todayStr) {
  return recallOccurrences(v)
    .filter((x) => x.date >= todayStr && ["scheduled", "proposed", "to_contact"].includes(x.status))
    .sort((a, b) => a.date.localeCompare(b.date));
}
// Headline recall-booking status for a practice detail page.
function recallStatus(v, todayStr) {
  if (!v) return { label: "No recall session booked yet", cls: "none", booked: false };
  const up = futureRecalls(v, todayStr);
  if (up.length) {
    const n = up[0];
    const when = `${fmtDate(n.date)}${n.times ? ` · ${n.times}` : ""}`;
    return n.status === "scheduled"
      ? { label: `Booked — ${when}`, cls: "ok", booked: true }
      : { label: `${cap(n.status)} — ${when}`, cls: "warn", booked: "tentative" };
  }
  const past = recallOccurrences(v).filter((x) => x.status === "happened").sort((a, b) => b.date.localeCompare(a.date));
  if (past.length) return { label: `Last session ${fmtDate(past[0].date)} · none upcoming`, cls: "done", booked: "past" };
  return { label: "No recall session booked yet", cls: "none", booked: false };
}

// Active blocks for a practice → labelled items (orthogonal to step progress).
function blockInfo(steps, blocksForOds) {
  const b = blocksForOds || {};
  const label = {};
  steps.forEach((s) => { label[s.key] = s.step; });
  const items = Object.entries(b)
    .map(([key, v]) => ({ key, label: label[key] || key, waiting_on: v.waiting_on, reason: v.reason, days: daysSince(v.blocked_at) }))
    .sort((a, b) => (b.days || 0) - (a.days || 0));
  return { count: items.length, items, oldestDays: items[0]?.days ?? null, waiting: new Set(items.map((i) => i.waiting_on)) };
}

const SORTS = [
  { key: "urgent", label: "Most urgent" },
  { key: "outstanding", label: "Most steps outstanding" },
  { key: "longest", label: "Outstanding longest" },
];
const HUB_NAV = [
  { id: "tracker", label: "Tracker" },
  { id: "all", label: "All practices" },
  { id: "calendar", label: "Calendar" },
];

export default function OnboardingHub({ data, visits = {}, auth = null }) {
  const { liveOnb, toggleStep, editor, notes, addNote, editNote, deleteNote, blocks, setStepBlock, live, markLive, error, setError } = useOnboarding(auth);
  const [selected, setSelected] = useState(() => (typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("practice") : null));
  const [weekOffset, setWeekOffset] = useState(0);
  const [confirmLive, setConfirmLive] = useState(null); // deal pending mark-live confirmation
  const [slot, setSlot] = useState(null);
  useEffect(() => { setSlot(document.getElementById("su-hubslot")); }, []);

  const todayStr = useMemo(() => localISO(new Date()), []);

  // The practice detail is a sub-page of the hub: opening one pushes a history
  // entry (with ?practice=ODS) so browser-back returns to the hub home, not the
  // Overview tab. popstate keeps `selected` in sync with that entry.
  const selectPractice = (ods) => {
    if (!ods) return;
    setSelected(ods);
    const u = new URL(window.location.href);
    u.searchParams.set("practice", ods);
    window.history.pushState({ hp: ods }, "", u.pathname + u.search + u.hash);
  };
  const backToHome = () => {
    if (window.history.state?.hp) { window.history.back(); return; }
    setSelected(null);
    const u = new URL(window.location.href);
    u.searchParams.delete("practice");
    window.history.replaceState({}, "", u.pathname + u.search + u.hash);
  };
  useEffect(() => {
    const onPop = () => setSelected(new URLSearchParams(window.location.search).get("practice") || null);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // sidebar nav → scroll to a home section (or, from a sub-page, just return home)
  const goSection = (id) => {
    if (selected) { backToHome(); return; }
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // cohort enriched with status, progress, blocked info, recall booking, live + flags
  const cohort = useMemo(() => {
    return (data.deals || [])
      .filter(inCohort)
      .map((d) => {
        const steps = d.onboarding?.length ? mergeOnboarding(d.onboarding, liveOnb?.[d.ods]) : [];
        const onb = summarizeOnboarding(steps);
        const blk = blockInfo(steps, blocks?.[d.ods]);
        const markedLive = live?.[d.ods] || null;
        const isLiveStage = d.stage === "live";
        const allDone = onb.total > 0 && onb.done === onb.total;
        const ready = allDone && !markedLive && !isLiveStage;
        const stallDays = data.stale_thresholds?.[d.stage] ?? STALL_DAYS; // stage-specific (dpa_signed/live = 21)
        const stalled = !ready && !markedLive && !isLiveStage && !allDone && (blk.count > 0 || (d.days_in_stage || 0) > stallDays);
        const rec = recallFor(visits, d.ods);
        return {
          ...d, _status: statusOf(d), _steps: steps, _onb: onb, _blk: blk, _live: markedLive,
          _isLive: isLiveStage || !!markedLive, _ready: ready, _stalled: stalled,
          _recall: rec, _recallBooked: !!futureRecalls(rec, todayStr).length, _outstanding: Math.max(0, onb.total - onb.done),
        };
      })
      .sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  }, [data, liveOnb, blocks, live, visits, todayStr]);

  const cohortOds = useMemo(() => new Set(cohort.map((d) => d.ods)), [cohort]);
  const sel = useMemo(() => cohort.find((d) => d.ods === selected) || null, [cohort, selected]);

  // top tracker
  const kpis = useMemo(() => ({
    total: cohort.length,
    onboarding: cohort.filter((d) => !d._isLive).length,
    live: cohort.filter((d) => d._isLive).length,
    stalled: cohort.filter((d) => d._stalled).length,
    blocked: cohort.filter((d) => d._blk.count > 0).length,
    ready: cohort.filter((d) => d._ready).length,
  }), [cohort]);

  // calendar events: onboarding calls (blue, HubSpot meetings) + recall/impl
  // sessions (peach, Notion visits — both cohort practices and live recallers)
  const events = useMemo(() => {
    const out = [];
    const seen = new Set();
    const add = (e) => { const k = `${e.ods}|${dayKey(e.date)}|${e.type}`; if (!seen.has(k)) { seen.add(k); out.push(e); } };
    for (const d of cohort) {
      const ns = d.next_step;
      if (ns?.date) {
        const isVisit = ns.type === "Visit" || ns.source === "Notion";
        add({ date: ns.date, time: fmtTime(ns.date), title: d.name, label: isVisit ? "Recall / impl." : "Onboarding call", type: isVisit ? "recall" : "onboarding", ods: d.ods });
      }
      for (const v of futureRecalls(d._recall, todayStr)) add({ date: v.date, time: v.times || "", title: d.name, label: "Recall / impl.", type: "recall", ods: d.ods });
    }
    for (const p of (data.recalling_practices || [])) {
      if (p.next_step?.date) add({ date: p.next_step.date, time: fmtTime(p.next_step.date), title: p.name, label: "Recall session", type: "recall", ods: p.ods });
      for (const v of (p.visits || [])) {
        if (v.date && v.date >= todayStr && ["scheduled", "proposed", "to_contact"].includes(v.status))
          add({ date: v.date, time: v.times || "", title: p.name, label: "Recall session", type: "recall", ods: p.ods });
      }
    }
    return out;
  }, [cohort, data, todayStr]);

  const openIfCohort = (ods) => { if (cohortOds.has(ods)) selectPractice(ods); };

  const sidebar = (
    <>
      <div className="su-onpage oh-hubnav">
        <div className="su-onpage-title">On this page</div>
        {HUB_NAV.map((s) => (
          <a key={s.id} href={`#${s.id}`} onClick={(e) => { e.preventDefault(); goSection(s.id); }}>{s.label}</a>
        ))}
      </div>
      <div className="su-spacer" />
    </>
  );

  return (
    <>
      {slot && createPortal(sidebar, slot)}
      <div className="oh-main">
        {error && (
          <div className="oh-error" role="alert">
            <span>{error}</span>
            <button onClick={() => setError(null)} aria-label="Dismiss">×</button>
          </div>
        )}
        <div className="oh-topbar">
          {sel ? (
            <>
              <div>
                <h2>{sel.name}</h2>
                <span className="sub">{sel.ods} · {sel._status.label}</span>
              </div>
              <button className="oh-back" onClick={backToHome}>← All practices</button>
            </>
          ) : (
            <>
              <div>
                <h2>Onboarding Hub — who needs what, and why we're stuck</h2>
                <span className="sub">{kpis.total} practices · click a step to update it · changes timestamped{editor ? ` as ${editor}` : ""}.</span>
              </div>
              {auth?.email && (
                <span className="oh-back" style={{ cursor: "default" }}>Editing as <b>{firstNameFromEmail(auth.email)}</b></span>
              )}
            </>
          )}
        </div>

        <div className="oh-scroll">
          {sel ? (
            <HubDetail key={sel.ods} deal={sel} liveOnb={liveOnb} toggleStep={toggleStep}
              notes={notes[sel.ods] || []} addNote={addNote} editNote={editNote} deleteNote={deleteNote}
              blocksForOds={blocks?.[sel.ods] || {}} setStepBlock={setStepBlock}
              recall={recallStatus(sel._recall, todayStr)} onMarkLive={() => setConfirmLive(sel)} />
          ) : (
            <HubHome kpis={kpis} cohort={cohort} events={events}
              weekOffset={weekOffset} setWeekOffset={setWeekOffset}
              onOpen={selectPractice} openIfCohort={openIfCohort} onMarkLive={setConfirmLive} />
          )}
        </div>
      </div>

      {confirmLive && (
        <ConfirmLive deal={confirmLive} onCancel={() => setConfirmLive(null)}
          onConfirm={() => { markLive(confirmLive); setConfirmLive(null); }} />
      )}
    </>
  );
}

/* ---------------- mark-live confirmation ---------------- */

function ConfirmLive({ deal, onCancel, onConfirm }) {
  return (
    <div className="oh-modal-back" onClick={onCancel}>
      <div className="oh-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Mark {deal.name} as live?</h3>
        <p>This records the practice as live in the Hub <b>and moves its deal in HubSpot to “Full Functionality Live”.</b> Only do this once the practice is genuinely live.</p>
        <div className="oh-modal-acts">
          <button className="oh-btn-ghost" onClick={onCancel}>Cancel</button>
          <button className="oh-btn-live" onClick={onConfirm}>Yes, mark live</button>
        </div>
      </div>
    </div>
  );
}

/* ---------------- home (no practice selected) ---------------- */

function naSorter(key) {
  const urgency = (d) => (d._blk.count > 0 ? 0 : d._stalled ? 1 : 2);
  if (key === "outstanding") return (a, b) => (b._outstanding - a._outstanding) || (urgency(a) - urgency(b));
  if (key === "longest") return (a, b) => ((b._blk.oldestDays ?? b.days_in_stage ?? 0) - (a._blk.oldestDays ?? a.days_in_stage ?? 0));
  return (a, b) => urgency(a) - urgency(b)
    || ((b._blk.oldestDays ?? b.days_in_stage ?? 0) - (a._blk.oldestDays ?? a.days_in_stage ?? 0))
    || (a._onb.done - b._onb.done);
}

// The square tracker tiles double as the page's filter tabs: click one to scope
// the single "All practices" list to that group and see what's outstanding.
const TILES = [
  { k: "all", l: "All practices", n: "total" },
  { k: "onboarding", l: "In onboarding", n: "onboarding" },
  { k: "live", l: "Now live", n: "live", good: true },
  { k: "stalled", l: "Stalled — action", n: "stalled", bad: true },
  { k: "blocked", l: "Blocked", n: "blocked", warn: true },
  { k: "ready", l: "Ready to go live", n: "ready", good: true },
];
const TILE_PRED = {
  all: () => true,
  onboarding: (d) => !d._isLive,
  live: (d) => d._isLive,
  stalled: (d) => d._stalled,
  blocked: (d) => d._blk.count > 0,
  ready: (d) => d._ready,
};

function HubHome({ kpis, cohort, events, weekOffset, setWeekOffset, onOpen, openIfCohort, onMarkLive }) {
  const [tile, setTile] = useState("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("urgent");

  const list = useMemo(() => {
    const s = search.trim().toLowerCase();
    return cohort.filter(TILE_PRED[tile]).filter((d) => !s
      || (d.name || "").toLowerCase().includes(s) || (d.ods || "").toLowerCase().includes(s)
      || (d.pcn_name || "").toLowerCase().includes(s) || (d.owner || "").toLowerCase().includes(s)
    ).slice().sort(naSorter(sort));
  }, [cohort, tile, search, sort]);
  const activeLabel = TILES.find((t) => t.k === tile)?.l || "All practices";

  return (
    <>
      <div className="oh-tiles" id="tracker">
        {TILES.map((t) => (
          <button key={t.k}
            className={"oh-tile click" + (t.good ? " good" : "") + (t.bad ? " bad" : "") + (t.warn ? " warn" : "") + (tile === t.k ? " sel" : "")}
            onClick={() => setTile(t.k)}>
            <div className="num">{kpis[t.n]}</div>
            <div className="lbl">{t.l}</div>
          </button>
        ))}
      </div>

      <div className="oh-block" id="all">
        <div className="oh-block-hdr">
          {activeLabel}<span className="n">{list.length}</span>
          <div className="oh-all-tools">
            <input className="oh-all-search" placeholder="Search practice, PCN, owner…" value={search} onChange={(e) => setSearch(e.target.value)} />
            <select className="oh-sort" value={sort} onChange={(e) => setSort(e.target.value)} title="Sort">
              {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        </div>
        <div className="oh-rows">
          {!list.length && <div className="oh-empty">No practices match.</div>}
          {list.map((d) => <PracticeRow key={d.ods} d={d} onOpen={onOpen} onMarkLive={onMarkLive} sort={sort} />)}
        </div>
      </div>

      <div className="oh-block" id="calendar">
        <div className="oh-block-hdr">This week's sessions</div>
        <HubCalendar events={events} weekOffset={weekOffset} setWeekOffset={setWeekOffset} onOpen={openIfCohort} />
      </div>
    </>
  );
}

// One row that adapts to the practice's state — shows exactly what's outstanding
// (blocked-on-whom · next step · days in stage), with an inline Mark-live for
// practices that have finished every step.
function PracticeRow({ d, onOpen, onMarkLive, sort }) {
  const blk = d._blk.items[0];
  const tag = d._blk.count > 0 ? { l: "Blocked", c: "blk" }
    : d._ready ? { l: "Ready", c: "ready" }
    : d._isLive ? { l: "Live", c: "live" }
    : d._stalled ? { l: "Action needed", c: "act" } : null;
  const sub = blk
    ? <>Blocked: <b>{blk.label}</b> · waiting on {WAITING_LABEL[blk.waiting_on]}{blk.days != null ? ` · ${blk.days}d` : ""}{blk.reason ? ` — ${blk.reason}` : ""}</>
    : d._ready ? <>all {d._onb.total} steps done — ready to go live</>
    : d._isLive ? <>live{d._recallBooked ? " · recall booked" : ""}</>
    : <>next: {d._onb.next || "—"}{d.days_in_stage != null ? ` · ${d.days_in_stage}d in stage` : ""}</>;
  return (
    <div className="oh-row oh-prow">
      <button className="oh-row-open" onClick={() => onOpen(d.ods)}>
        <span className={"dot " + d._status.key} />
        <span className="main">
          <span className="nm">{d.name}{tag && <span className={"oh-na-tag " + tag.c}>{tag.l}</span>}</span>
          <span className="sub">{sub}</span>
        </span>
        <span className="bar"><span className="fill" style={{ width: `${d._onb.total ? Math.round((d._onb.done / d._onb.total) * 100) : 0}%` }} /></span>
        <span className="pct">{sort === "outstanding" && !d._isLive ? `${d._outstanding} left` : d._onb.total ? `${d._onb.done}/${d._onb.total}` : "—"}</span>
      </button>
      {d._ready && <button className="oh-mark-live" onClick={() => onMarkLive(d)}>Mark live</button>}
    </div>
  );
}

/* ---------------- weekly calendar ---------------- */

function HubCalendar({ events, weekOffset, setWeekOffset, onOpen }) {
  const base = new Date(); base.setHours(0, 0, 0, 0);
  const monday = new Date(base);
  monday.setDate(base.getDate() - ((base.getDay() + 6) % 7) + weekOffset * 7);
  const days = Array.from({ length: 5 }, (_, i) => { const d = new Date(monday); d.setDate(monday.getDate() + i); return d; });
  const todayKey = localISO(new Date());
  const byDay = {};
  for (const e of events) (byDay[dayKey(e.date)] ||= []).push(e);
  const range = `${monday.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} – ${days[4].toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`;
  return (
    <div className="oh-cal">
      <div className="oh-cal-head">
        <button className="oh-cal-nav" onClick={() => setWeekOffset(weekOffset - 1)}>‹</button>
        <span className="oh-cal-range">{range}</span>
        <button className="oh-cal-nav" onClick={() => setWeekOffset(weekOffset + 1)}>›</button>
        {weekOffset !== 0 && <button className="oh-cal-today" onClick={() => setWeekOffset(0)}>this week</button>}
        <span className="oh-cal-legend">
          <span><i className="lg onboarding" />Onboarding call</span>
          <span><i className="lg recall" />Recall / impl.</span>
        </span>
      </div>
      <div className="oh-cal-grid">
        {days.map((d, i) => {
          const k = localISO(d);
          const evs = (byDay[k] || []).slice().sort((a, b) => (a.date || "").localeCompare(b.date || ""));
          return (
            <div key={i} className={"oh-cal-day" + (k === todayKey ? " today" : "")}>
              <div className="oh-cal-dnum"><span>{d.toLocaleDateString("en-GB", { weekday: "short" })}</span><b>{d.getDate()}</b></div>
              <div className="oh-cal-evs">
                {evs.map((e, j) => (
                  <button key={j} className={"oh-cal-ev " + e.type} onClick={() => onOpen(e.ods)} title={`${e.label}: ${e.title}${e.time ? " · " + e.time : ""}`}>
                    <span className="lbl">{e.label}</span>
                    <span className="nm">{e.title}</span>
                    {e.time && <span className="tm">{e.time}</span>}
                  </button>
                ))}
                {!evs.length && <span className="oh-cal-none">·</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------------- detail (a practice selected) ---------------- */

function CopyBtn({ text }) {
  const [done, setDone] = useState(false);
  return (
    <button className="oh-copy" onClick={() => navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1200); })}>
      {done ? "copied" : "copy"}
    </button>
  );
}

function StepCard({ deal, s, blk, toggleStep, setStepBlock }) {
  const [editing, setEditing] = useState(false);
  return (
    <div className={"oh-step " + s.state + (blk ? " blocked" : "")}>
      <button className="oh-step-main" onClick={() => toggleStep(deal, s)}
        title={s.changed_at ? `${s.state} · ${s.changed_by || ""} · ${fmtDate(s.changed_at)}` : (s.value || s.state)}>
        <span className="ico">{MARK[s.state]}</span>
        <span className="mid">
          <span className="nm">{s.step}</span>
          <span className="st">{s.changed_at ? `${s.state} · ${fmtDate(s.changed_at)}` : (s.value && s.state !== "todo" ? s.value : s.state)}</span>
        </span>
      </button>
      <button className={"oh-flag" + (blk ? " on" : "")} title={blk ? "blocked — edit" : "flag as blocked"} onClick={() => setEditing((v) => !v)}>⚑</button>
      {blk && (
        <div className="oh-step-blk">⚑ waiting on {WAITING_LABEL[blk.waiting_on]}{blk.days != null ? ` · ${blk.days}d` : ""}{blk.reason ? ` — ${blk.reason}` : ""}</div>
      )}
      {editing && <BlockForm blk={blk} onClose={() => setEditing(false)} onSet={(opts) => { setStepBlock(deal, s, opts); setEditing(false); }} />}
    </div>
  );
}

function BlockForm({ blk, onSet, onClose }) {
  const [waiting, setWaiting] = useState(blk?.waiting_on || "third_party");
  const [reason, setReason] = useState(blk?.reason || "");
  return (
    <div className="oh-blockform" onClick={(e) => e.stopPropagation()}>
      <div className="oh-bf-row">
        {WAITING_ON.map((w) => (
          <button key={w} className={"oh-bf-chip" + (waiting === w ? " active" : "")} onClick={() => setWaiting(w)}>{WAITING_LABEL[w]}</button>
        ))}
      </div>
      <input className="oh-bf-reason" placeholder="Why is it blocked? (e.g. labs whitelisting)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="oh-bf-acts">
        {blk && <button className="oh-bf-unblock" onClick={() => onSet({ action: "unblock" })}>Unblock</button>}
        <button className="oh-bf-cancel" onClick={onClose}>Cancel</button>
        <button className="oh-bf-set" onClick={() => onSet({ action: "block", waiting_on: waiting, reason: reason.trim() || null })}>{blk ? "Update" : "Mark blocked"}</button>
      </div>
    </div>
  );
}

function NoteItem({ deal, n, editNote, deleteNote }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(n.body);
  const editable = !n.pending && !String(n.id).startsWith("tmp");
  return (
    <div className={"oh-note" + (n.pending ? " pending" : "")}>
      {editing ? (
        <div className="oh-note-edit">
          <textarea value={val} onChange={(e) => setVal(e.target.value)} rows={2} />
          <div className="oh-note-edit-acts">
            <button className="oh-note-cancel" onClick={() => { setVal(n.body); setEditing(false); }}>Cancel</button>
            <button className="oh-note-save" disabled={!val.trim()} onClick={() => { editNote(deal, n.id, val); setEditing(false); }}>Save</button>
          </div>
        </div>
      ) : (
        <>
          <div className="oh-note-body">{n.body}</div>
          <div className="oh-note-meta">
            <span>{n.author || "—"} · {fmtDateTime(n.created_at)}{n.updated_at ? " · edited" : ""}{n.pending ? " · saving…" : n.hs_synced ? " · synced to HubSpot" : ""}</span>
            {editable && (
              <span className="oh-note-acts">
                <button onClick={() => { setVal(n.body); setEditing(true); }}>edit</button>
                <button onClick={() => { if (window.confirm("Delete this note? This also removes it from HubSpot if it was synced.")) deleteNote(deal, n.id); }}>delete</button>
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function HubDetail({ deal, liveOnb, toggleStep, notes, addNote, editNote, deleteNote, blocksForOds, setStepBlock, recall, onMarkLive }) {
  const [draft, setDraft] = useState("");
  const steps = deal.onboarding?.length ? mergeOnboarding(deal.onboarding, liveOnb?.[deal.ods]) : [];
  const { done, total, next } = summarizeOnboarding(steps);
  const pct = total ? Math.round((done / total) * 100) : 0;
  const _rank = { done: 0, pending: 1, todo: 2 };
  const stepTimeline = [...steps].sort((a, b) =>
    ((_rank[a.state] ?? 3) - (_rank[b.state] ?? 3)) ||
    ((a.changed_at ? Date.parse(a.changed_at) : Infinity) - (b.changed_at ? Date.parse(b.changed_at) : Infinity))
  );
  const facts = [
    { l: "ODS code", v: deal.ods, copy: deal.ods },
    { l: "PCN", v: deal.pcn_name },
    { l: "ICB", v: deal.icb },
    { l: "Owner", v: deal.owner },
    { l: "List size", v: deal.patients ? deal.patients.toLocaleString() : null },
    { l: "EHR", v: deal.ehr },
    { l: "Stage", v: deal.stage_label },
    { l: "In stage", v: deal.days_in_stage != null ? `${deal.days_in_stage}d` : null },
  ];
  const blockedCount = Object.keys(blocksForOds || {}).length;
  const hsUrl = hubspotDealUrl(deal.deal_id);
  const lastContact = deal.last_contact
    ? `${fmtDate(deal.last_contact)}${deal.days_since_contact != null ? ` · ${deal.days_since_contact}d ago` : ""}`
    : "No logged contact";
  const chasedBy = deal.owner ? `${deal.owner}${deal.owner_email ? ` · ${deal.owner_email}` : ""}` : null;
  const emails = deal.last_emails?.length
    ? deal.last_emails
    : (deal.last_email ? [{ subject: deal.last_email.subject, direction: deal.last_email.direction, by: null, date: null, days_ago: deal.days_since_email }] : []);
  return (
    <>
      <div className="oh-detail-top">
        <div className="oh-detail-meta">
          <span className={"oh-pill " + deal._status.key}>{deal._status.label}</span>
          {deal.tier && <span className="oh-tag">{deal.tier}</span>}
          {blockedCount > 0 && <span className="oh-tag blk">⚑ {blockedCount} blocked</span>}
          {deal._live && <span className="oh-tag livemark">✓ marked live{deal._live.hs_synced ? " · HubSpot" : ""}</span>}
          {next ? <span className="oh-tag">Next: {next}</span> : <span className="oh-tag">All steps done</span>}
        </div>
        <div className="oh-detail-actions">
          {hsUrl && <a className="oh-hslink" href={hsUrl} target="_blank" rel="noreferrer">HubSpot deal ↗</a>}
          {deal._ready && <button className="oh-mark-live" onClick={onMarkLive}>Mark live</button>}
        </div>
      </div>

      <div className="oh-prog">
        <div className="oh-prog-top">
          <span className="oh-prog-lbl">Onboarding{next && <> · <span className="next">next: {next}</span></>}</span>
          <span className="oh-prog-pct">{total ? `${done}/${total} · ${pct}%` : "no checklist"}</span>
        </div>
        <div className="oh-prog-bar"><span className="oh-prog-fill" style={{ width: `${pct}%` }} /></div>
      </div>

      <div className="oh-callouts">
        <div className={"oh-callout " + (recall.cls || "")}>
          <div className="l">Recalling session</div>
          <div className="v">{recall.label}</div>
        </div>
        <div className="oh-callout">
          <div className="l">Last chased</div>
          <div className="v">{lastContact}</div>
          {chasedBy && <div className="sub">owner: {chasedBy}</div>}
        </div>
      </div>

      {emails.length > 0 && (
        <div className="oh-emails">
          <div className="oh-emails-hdr">Recent emails on this deal <span>· HubSpot</span></div>
          {emails.map((e, i) => (
            <div key={i} className="oh-email">
              <span className={"oh-email-dir " + (e.direction || "email")}>{e.direction || "email"}</span>
              <span className="oh-email-subj">{e.subject}</span>
              <span className="oh-email-meta">{[e.by, e.days_ago != null ? `${e.days_ago}d ago` : (e.date ? fmtDate(e.date) : null)].filter(Boolean).join(" · ")}</span>
            </div>
          ))}
        </div>
      )}

      <div className="oh-facts">
        {facts.map((f) => (
          <div key={f.l} className="oh-fact">
            <div className="l">{f.l}</div>
            <div className={"v" + (f.v ? "" : " empty")}>{f.v || "—"}{f.copy && f.v ? <CopyBtn text={f.copy} /> : null}</div>
          </div>
        ))}
      </div>

      <h4 className="oh-sec-title">Set-up steps</h4>
      <p className="oh-hint">Click a step to advance it (to&nbsp;do → pending → done). Use the ⚑ to flag a step blocked and say who we're waiting on — it can be blocked <i>and</i> in progress.</p>
      {steps.length ? (
        <div className="oh-steps">
          {steps.map((s) => <StepCard key={s.key} deal={deal} s={s} blk={blocksForOds?.[s.key] ? { ...blocksForOds[s.key], days: daysSince(blocksForOds[s.key].blocked_at) } : null} toggleStep={toggleStep} setStepBlock={setStepBlock} />)}
        </div>
      ) : (
        <p className="oh-hint" style={{ fontStyle: "italic" }}>No onboarding checklist for this practice yet — it appears once the practice is on the tracker sheet.</p>
      )}

      <h4 className="oh-sec-title">Notes</h4>
      <div className="oh-notes">
        <div className="oh-note-new">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a note — saved with your name &amp; the time, and pushed to the HubSpot deal…" rows={2} />
          <button className="oh-note-add" disabled={!draft.trim()}
            onClick={() => { addNote(deal, draft); setDraft(""); }}>Add note</button>
        </div>
        {!notes.length && <div className="oh-empty">No notes logged yet.</div>}
        {notes.map((n) => <NoteItem key={n.id} deal={deal} n={n} editNote={editNote} deleteNote={deleteNote} />)}
      </div>

      {(deal.stage_timeline?.length > 0 || steps.length > 0) && (
        <div className="oh-tl-cols">
          {deal.stage_timeline?.length > 0 && (
            <div className="oh-tl-col">
              <h4 className="oh-sec-title">Where they're at</h4>
              <ol className="oh-tl">
                {deal.stage_timeline.map((s, i) => (
                  <li key={i} className={s.current ? "current" : ""}>
                    <span className="d" />
                    <span className="s">{s.stage}</span>
                    <span className="dt">{fmtDate(s.date)}</span>
                    {s.gap_days != null && <span className="gap">+{s.gap_days}d</span>}
                    {s.current && <span className="oh-here">here now</span>}
                    {s.current && deal.days_in_stage != null && <span className="gap now">{deal.days_in_stage}d &amp; counting</span>}
                  </li>
                ))}
              </ol>
            </div>
          )}
          {steps.length > 0 && (
            <div className="oh-tl-col">
              <h4 className="oh-sec-title">Onboarding steps — when done</h4>
              <ol className="oh-tl oh-tl-steps">
                {stepTimeline.map((s) => (
                  <li key={s.key} className={"st-" + s.state}>
                    <span className="d" />
                    <span className="s">{s.step}</span>
                    {s.changed_at && <span className="dt">{fmtDate(s.changed_at)}</span>}
                    <span className={"oh-stchip " + s.state}>{s.state === "done" ? "done" : s.state === "pending" ? "in progress" : "to do"}</span>
                  </li>
                ))}
              </ol>
              <p className="oh-hint" style={{ marginTop: 4 }}>Dates show where a step was marked done in the Hub. Sheet-imported steps have no recorded date (the tracker sheet has no per-step dates) — re-tick it here to stamp one. Demo &amp; DPA are on the stage timeline.</p>
            </div>
          )}
        </div>
      )}
    </>
  );
}
