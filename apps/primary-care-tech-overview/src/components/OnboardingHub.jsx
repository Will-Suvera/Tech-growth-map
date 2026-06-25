import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import "./OnboardingHub.css";
import { useOnboarding, mergeOnboarding, summarizeOnboarding, firstNameFromEmail } from "../onboarding.js";

// The Onboarding Hub: the CS team's action surface for DPA-signed-onwards
// practices. Cohort + "where they're at" come live from funnel_board.json; the
// real set-up steps (Google Sheet, merged with in-app Neon toggles) are the
// action model, so the hub reflects each practice's actual onboarding state and
// changes flow straight back into the Overview tab's roll-up.

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "");
const fmtDateTime = (s) =>
  s ? new Date(s).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
const MARK = { done: "✓", pending: "•", todo: "○" };

// Effective onboarding progress for a practice (real steps + Neon toggles).
const progressFor = (d, liveOnb) =>
  summarizeOnboarding(d.onboarding?.length ? mergeOnboarding(d.onboarding, liveOnb?.[d.ods]) : []);

// Cohort = HubSpot Planner deals at DPA-signed or beyond, with an ODS code.
const inCohort = (d) => (d.stage === "dpa_signed" || d.stage === "live") && d.ods;

function statusOf(d) {
  if (d.stage === "dpa_signed") return { key: "st-dpa", label: "DPA signed", group: "dpa" };
  if (d.recalling) return { key: "st-recalling", label: "Live — recalling", group: "recalling" };
  return { key: "st-live", label: "Live — not recalling", group: "live" };
}

const FILTERS = [
  { key: "all", label: "All" },
  { key: "dpa", label: "DPA signed" },
  { key: "live", label: "Live" },
  { key: "recalling", label: "Recalling" },
];
const GROUP_ORDER = [
  { key: "dpa", label: "DPA signed" },
  { key: "live", label: "Live — not recalling" },
  { key: "recalling", label: "Live — recalling" },
];

export default function OnboardingHub({ data, auth = null }) {
  const { liveOnb, toggleStep, editor, notes, addNote } = useOnboarding(auth);
  const [selected, setSelected] = useState(null); // ods
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  // the practice list renders into the app sidebar (one column) via a portal
  const [slot, setSlot] = useState(null);
  useEffect(() => { setSlot(document.getElementById("su-hubslot")); }, []);

  // cohort enriched with derived status + live onboarding progress (recomputes on toggle)
  const cohort = useMemo(() => {
    return (data.deals || [])
      .filter(inCohort)
      .map((d) => ({ ...d, _status: statusOf(d), _onb: progressFor(d, liveOnb) }))
      .sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  }, [data, liveOnb]);

  const visible = useMemo(() => {
    const s = search.trim().toLowerCase();
    return cohort.filter((d) => {
      if (filter !== "all" && d._status.group !== filter) return false;
      if (!s) return true;
      return (d.name || "").toLowerCase().includes(s) || (d.ods || "").toLowerCase().includes(s)
        || (d.pcn_name || "").toLowerCase().includes(s) || (d.owner || "").toLowerCase().includes(s);
    });
  }, [cohort, search, filter]);

  const sel = useMemo(() => cohort.find((d) => d.ods === selected) || null, [cohort, selected]);

  // KPIs (over the whole cohort, not the filtered view)
  const kpis = useMemo(() => {
    const total = cohort.length;
    const dpa = cohort.filter((d) => d._status.group === "dpa").length;
    const live = cohort.filter((d) => d.stage === "live").length;
    const recalling = cohort.filter((d) => d._status.group === "recalling").length;
    const provisioned = cohort.filter((d) => d._onb.total > 0 && d._onb.done === d._onb.total).length;
    return { total, dpa, live, recalling, provisioned };
  }, [cohort]);

  // home view lists
  const outstanding = useMemo(
    () => cohort.filter((d) => d._onb.total > 0 && d._onb.done < d._onb.total)
      .sort((a, b) => (a._onb.done - b._onb.done) || ((b.days_in_stage || 0) - (a.days_in_stage || 0))),
    [cohort]
  );
  const touchpoints = useMemo(
    () => cohort.filter((d) => d.next_step?.date)
      .sort((a, b) => (a.next_step.date || "").localeCompare(b.next_step.date || "")),
    [cohort]
  );

  const grouped = GROUP_ORDER
    .map((g) => ({ ...g, items: visible.filter((d) => d._status.group === g.key) }))
    .filter((g) => g.items.length);

  const sidebar = (
    <div className="oh-side">
      <div className="oh-search">
        <input placeholder="Search practice, PCN, owner…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="oh-chips">
        {FILTERS.map((f) => (
          <button key={f.key} className={"oh-chip" + (filter === f.key ? " active" : "")} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
      </div>
      <div className="oh-list">
        {!grouped.length && <div className="oh-empty">No practices match.</div>}
        {grouped.map((g) => (
          <div key={g.key} className="oh-grp">
            <div className="oh-grp-hdr">{g.label}<span className="n">{g.items.length}</span></div>
            {g.items.map((d) => (
              <button key={d.ods} className={"oh-card" + (selected === d.ods ? " active" : "")} onClick={() => setSelected(d.ods)}>
                <span className={"dot " + d._status.key} />
                <span className="nm">{d.name}</span>
                <span className={"pg" + (d._onb.total > 0 && d._onb.done === d._onb.total ? " done" : "")}>
                  {d._onb.total ? `${d._onb.done}/${d._onb.total}` : "—"}
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <>
      {slot && createPortal(sidebar, slot)}
      <div className="oh-main">
        <div className="oh-topbar">
          {sel ? (
            <>
              <div>
                <h2>{sel.name}</h2>
                <span className="sub">{sel.ods} · {sel._status.label}</span>
              </div>
              <button className="oh-back" onClick={() => setSelected(null)}>← All practices</button>
            </>
          ) : (
            <>
              <div>
                <h2>What's next — DPA-signed onwards</h2>
                <span className="sub">{kpis.total} practices · click a step to update it · changes are timestamped{editor ? ` as ${editor}` : ""}.</span>
              </div>
              {auth?.email && (
                <span className="oh-back" style={{ cursor: "default" }}>Editing as <b>{firstNameFromEmail(auth.email)}</b></span>
              )}
            </>
          )}
        </div>

        <div className="oh-scroll">
          {sel ? <HubDetail key={sel.ods} deal={sel} liveOnb={liveOnb} toggleStep={toggleStep} notes={notes[sel.ods] || []} addNote={addNote} />
               : <HubHome kpis={kpis} outstanding={outstanding} touchpoints={touchpoints} filter={filter} setFilter={setFilter} onOpen={setSelected} />}
        </div>
      </div>
    </>
  );
}

/* ---------------- home (no practice selected) ---------------- */

function HubHome({ kpis, outstanding, touchpoints, filter, setFilter, onOpen }) {
  const tiles = [
    { k: "total", n: kpis.total, l: "In onboarding", f: "all" },
    { k: "dpa", n: kpis.dpa, l: "DPA signed", f: "dpa" },
    { k: "live", n: kpis.live, l: "Live", f: "live" },
    { k: "recalling", n: kpis.recalling, l: "Recalling", f: "recalling", good: true },
    { k: "prov", n: kpis.provisioned, l: "Fully onboarded", good: true },
  ];
  return (
    <>
      <div className="oh-tiles">
        {tiles.map((t) => (
          <button key={t.k}
            className={"oh-tile" + (t.good ? " good" : "") + (t.f ? " click" : "") + (t.f && filter === t.f ? " sel" : "")}
            onClick={t.f ? () => setFilter(t.f) : undefined}>
            <div className="num">{t.n}</div>
            <div className="lbl">{t.l}</div>
          </button>
        ))}
      </div>

      <div className="oh-cols">
        <div className="oh-block">
          <div className="oh-block-hdr">Outstanding — needs a next action<span className="n">{outstanding.length}</span></div>
          <div className="oh-rows">
            {!outstanding.length && <div className="oh-empty">Everyone is fully provisioned 🎉</div>}
            {outstanding.map((d) => (
              <button key={d.ods} className="oh-row" onClick={() => onOpen(d.ods)}>
                <span className={"dot " + d._status.key} />
                <span className="main">
                  <span className="nm">{d.name}</span>
                  <span className="sub">next: {d._onb.next || "—"}{d.days_in_stage != null ? ` · ${d.days_in_stage}d in stage` : ""}</span>
                </span>
                <span className="bar"><span className="fill" style={{ width: `${Math.round((d._onb.done / d._onb.total) * 100)}%` }} /></span>
                <span className="pct">{d._onb.done}/{d._onb.total}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="oh-block">
          <div className="oh-block-hdr">Upcoming touchpoints<span className="n">{touchpoints.length}</span></div>
          <div className="oh-rows">
            {!touchpoints.length && <div className="oh-empty">No visits or meetings booked.</div>}
            {touchpoints.map((d) => (
              <button key={d.ods} className="oh-row" onClick={() => onOpen(d.ods)}>
                <span className={"dot " + d._status.key} />
                <span className="main">
                  <span className="nm">{d.name}</span>
                  <span className="sub">{d.next_step.type}{d.next_step.source ? ` · ${d.next_step.source}` : ""}</span>
                </span>
                <span className="when">{fmtDate(d.next_step.date)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
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

function HubDetail({ deal, liveOnb, toggleStep, notes, addNote }) {
  const [draft, setDraft] = useState("");
  const steps = deal.onboarding?.length ? mergeOnboarding(deal.onboarding, liveOnb?.[deal.ods]) : [];
  const { done, total, next } = summarizeOnboarding(steps);
  const pct = total ? Math.round((done / total) * 100) : 0;
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
  return (
    <>
      <div className="oh-detail-top">
        <div className="oh-detail-meta">
          <span className={"oh-pill " + deal._status.key}>{deal._status.label}</span>
          {deal.tier && <span className="oh-tag">{deal.tier}</span>}
          {next ? <span className="oh-tag">Next: {next}</span> : <span className="oh-tag">Fully provisioned</span>}
        </div>
      </div>

      <div className="oh-prog">
        <div className="oh-prog-top">
          <span className="oh-prog-lbl">Onboarding{next && <> · <span className="next">next: {next}</span></>}</span>
          <span className="oh-prog-pct">{total ? `${done}/${total} · ${pct}%` : "no checklist"}</span>
        </div>
        <div className="oh-prog-bar"><span className="oh-prog-fill" style={{ width: `${pct}%` }} /></div>
      </div>

      <div className="oh-facts">
        {facts.map((f) => (
          <div key={f.l} className="oh-fact">
            <div className="l">{f.l}</div>
            <div className={"v" + (f.v ? "" : " empty")}>{f.v || "—"}{f.copy && f.v ? <CopyBtn text={f.copy} /> : null}</div>
          </div>
        ))}
      </div>

      <h4 className="oh-sec-title">Set-up steps</h4>
      <p className="oh-hint">Click a step to advance it — to&nbsp;do → pending → done. Every change is saved &amp; timestamped.</p>
      {steps.length ? (
        <div className="oh-steps">
          {steps.map((s) => (
            <button key={s.key} className={"oh-step " + s.state}
              title={s.changed_at ? `${s.state} · ${s.changed_by || ""} · ${fmtDate(s.changed_at)}` : (s.value || s.state)}
              onClick={() => toggleStep(deal, s)}>
              <span className="ico">{MARK[s.state]}</span>
              <span className="mid">
                <span className="nm">{s.step}</span>
                <span className="st">{s.changed_at ? `${s.state} · ${fmtDate(s.changed_at)}` : (s.value && s.state !== "todo" ? s.value : s.state)}</span>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="oh-hint" style={{ fontStyle: "italic" }}>No onboarding checklist for this practice yet — it appears once the practice is on the tracker sheet.</p>
      )}

      <h4 className="oh-sec-title">Notes</h4>
      <div className="oh-notes">
        <div className="oh-note-new">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a note — saved with your name &amp; the time…" rows={2} />
          <button className="oh-note-add" disabled={!draft.trim()}
            onClick={() => { addNote(deal, draft); setDraft(""); }}>Add note</button>
        </div>
        {!notes.length && <div className="oh-empty">No notes logged yet.</div>}
        {notes.map((n) => (
          <div key={n.id} className={"oh-note" + (n.pending ? " pending" : "")}>
            <div className="oh-note-body">{n.body}</div>
            <div className="oh-note-meta">
              {n.author || "—"} · {fmtDateTime(n.created_at)}
              {n.pending ? " · saving…" : n.hs_synced ? " · synced to HubSpot" : ""}
            </div>
          </div>
        ))}
      </div>

      {deal.stage_timeline?.length > 0 && (
        <>
          <h4 className="oh-sec-title">Where they're at</h4>
          <ol className="oh-tl">
            {deal.stage_timeline.map((s, i) => (
              <li key={i} className={s.current ? "current" : ""}>
                <span className="d" />
                <span className="s">{s.stage}</span>
                <span className="dt">{fmtDate(s.date)}</span>
                {s.gap_days != null && <span className="gap">+{s.gap_days}d</span>}
                {s.current && deal.days_in_stage != null && <span className="gap now">{deal.days_in_stage}d &amp; counting</span>}
              </li>
            ))}
          </ol>
        </>
      )}

      <h4 className="oh-sec-title">Activation this FY</h4>
      <div className="oh-mini">
        <div><div className="k">Recalls</div><div className="val">{(deal.fy_recalls || 0).toLocaleString()}</div></div>
        <div><div className="k">Bloods</div><div className="val">{(deal.fy_bloods || 0).toLocaleString()}</div></div>
        <div><div className="k">This month</div><div className="val">{(deal.recalls_this_month || 0).toLocaleString()}</div></div>
      </div>
    </>
  );
}
