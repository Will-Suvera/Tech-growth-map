import React, { useMemo, useState } from "react";

// Section 3 — 🟡 Middle of funnel. Three side-by-side panels.
function daysSince(date) {
  if (!date) return null;
  try { return Math.round((Date.now() - new Date(date).getTime()) / 86400000); }
  catch { return null; }
}

function lastMeetingDate(p) {
  const meetings = p.meetings || [];
  if (!meetings.length) return null;
  return meetings.map((m) => m.date).filter(Boolean).sort().slice(-1)[0] || null;
}

export default function MofuPanels({ practices, onSelect }) {
  const data = useMemo(() => {
    const scheduledVisits = [];
    const dpaWithoutVisit = [];
    const meetingsWithoutDpa = [];

    for (const p of practices) {
      // Panel 1: scheduled visits (any stage qualifies)
      if (p.practice_visit_status === "scheduled") {
        scheduledVisits.push(p);
      }
      // Panel 2: signed-DPA stage with no visit booked
      if (p.stage === "onboarding" && (p.practice_visit_status || "none") === "none") {
        dpaWithoutVisit.push(p);
      }
      // Panel 3: signed_up + meeting held + no DPA + last meeting ≥ 14 days ago
      if (p.stage === "signed_up" && (p.meeting_count || 0) > 0) {
        const last = lastMeetingDate(p);
        const days = daysSince(last);
        if (days !== null && days >= 14) {
          meetingsWithoutDpa.push({ ...p, _last_meeting: last, _days: days });
        }
      }
    }

    scheduledVisits.sort((a, b) => (a.practice_visit_date || "").localeCompare(b.practice_visit_date || ""));
    // Longest since DPA-signing first (oldest opportunity-entry date = most stalled)
    const dpaDate = (p) => p.company_props?.hs_date_entered_opportunity || "9999";
    dpaWithoutVisit.sort((a, b) => dpaDate(a).localeCompare(dpaDate(b)));
    meetingsWithoutDpa.sort((a, b) => b._days - a._days);
    return { scheduledVisits, dpaWithoutVisit, meetingsWithoutDpa };
  }, [practices]);

  return (
    <section style={{ marginBottom: 20 }}>
      <h2 style={{ margin: "0 0 8px 4px", fontSize: 16 }}>🟡 Middle of funnel</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        <Panel
          title="Booked practice visits"
          subtitle="From Notion Practice Visits · Confirmed"
          count={data.scheduledVisits.length}
          rows={data.scheduledVisits}
          render={(p) => (
            <div>
              <div style={{ fontWeight: 500 }}>{p.name || p.ods}</div>
              <div className="muted" style={{ fontSize: 10 }}>
                {p.practice_visit_date || "no date"}
                {p.practice_visit_times && ` · ${String(p.practice_visit_times).split("\n")[0]}`}
              </div>
              {p.practice_visit_attendees?.length > 0 && (
                <div className="muted" style={{ fontSize: 10, fontStyle: "italic" }}>
                  with {p.practice_visit_attendees.slice(0, 2).join(", ")}
                  {p.practice_visit_attendees.length > 2 && ` +${p.practice_visit_attendees.length - 2}`}
                </div>
              )}
              {p.practice_visit_problems && (
                <div style={{ fontSize: 10, color: "var(--warn)", marginTop: 2 }}>
                  ⚠ {p.practice_visit_problems.slice(0, 60)}{p.practice_visit_problems.length > 60 ? "…" : ""}
                </div>
              )}
            </div>
          )}
          onSelect={onSelect}
          emptyMessage="No visits scheduled. Pull Notion → notion_practice_visits.json."
        />
        <Panel
          title="Signed DPA, no practice visit booked"
          subtitle="Likely in progress · onboarding stage"
          count={data.dpaWithoutVisit.length}
          rows={data.dpaWithoutVisit}
          render={(p) => {
            // DPA-signing proxy = when the company entered the opportunity/deal
            // stage (company_props.hs_date_entered_opportunity).
            const dpaDate = p.company_props?.hs_date_entered_opportunity;
            const days = daysSince(dpaDate);
            return (
              <div>
                <div style={{ fontWeight: 500 }}>{p.name || p.ods}</div>
                {days != null && (
                  <div className="muted" style={{ fontSize: 10 }}>
                    {days}d since signing DPA
                  </div>
                )}
              </div>
            );
          }}
          onSelect={onSelect}
          emptyMessage="None — every DPA has a visit booked or done ✓"
        />
        <Panel
          title="Meeting held, no DPA in 14+ days"
          subtitle="Cold post-demo — chase or close lost"
          count={data.meetingsWithoutDpa.length}
          rows={data.meetingsWithoutDpa}
          render={(p) => (
            <div>
              <div style={{ fontWeight: 500 }}>{p.name || p.ods}</div>
              <div className="muted" style={{ fontSize: 10 }}>
                last meeting {p._last_meeting} · {p._days}d quiet
              </div>
            </div>
          )}
          onSelect={onSelect}
          emptyMessage="No stale post-demo practices ✓"
        />
      </div>
    </section>
  );
}

function Panel({ title, subtitle, count, rows, render, onSelect, emptyMessage }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? rows : rows.slice(0, 10);
  return (
    <div className="card" style={{ padding: 12 }}>
      <header style={{ marginBottom: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div style={{ fontSize: 13, fontWeight: 500 }}>{title}</div>
          <div style={{ fontSize: 18, fontWeight: 600, color: "var(--brand)" }}>{count}</div>
        </div>
        <div className="muted" style={{ fontSize: 11 }}>{subtitle}</div>
      </header>
      {rows.length === 0 ? (
        <div className="muted" style={{ fontSize: 12, fontStyle: "italic" }}>{emptyMessage}</div>
      ) : (
        <>
          {visible.map((p) => (
            <button
              key={p.ods}
              onClick={() => onSelect(p)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "6px 8px",
                marginBottom: 4,
                background: "#fafafa",
                border: "1px solid var(--rule)",
                borderRadius: 4,
                cursor: "pointer",
                fontSize: 12,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#f1f5f9")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "#fafafa")}
            >
              {render(p)}
            </button>
          ))}
          {rows.length > 10 && (
            <button
              onClick={() => setExpanded((e) => !e)}
              style={{ background: "none", border: "none", color: "var(--brand)", fontSize: 11, padding: 4, cursor: "pointer" }}
            >
              {expanded ? "Show less" : `Show ${rows.length - 10} more…`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
