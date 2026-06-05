import React, { useMemo, useState } from "react";
import HealthBadge from "./HealthBadge.jsx";
import HealthBucketChips from "./HealthBucketChips.jsx";
import SourceDropdown from "./SourceDropdown.jsx";
import EhrBadge from "./EhrBadge.jsx";
import PaidStatusCell, { TestimonialCell } from "./PaidStatusCell.jsx";
import { TIER_BY_ID, shortenIcb, LIVE_STAGES } from "../utils/funnel.js";
import { fmtInt, fyLabelFor } from "../utils/fy.js";

// Section 1 — 🟢 Live Cohort.
// Buckets relevant here: only positive-engagement ones. Sorted by FY recalls desc.
const SECTION_BUCKETS = ["healthy", "near_cap", "testimonial_ready", "expansion_super_user"];

const SORT_COLS = {
  patients: { label: "Patients", get: (p) => p.patients || 0 },
  fy_recalls: { label: "FY recalls", get: (p) => p.recalls_fy_to_date || 0 },
  fy_bloods: { label: "FY forms", get: (p) => p.bloods_fy_to_date || 0 },
  this_month: { label: "This month", get: (p) => p.recalls_this_month || 0 },
  recalls_per_patient: { label: "Recalls/patient", get: (p) => p.recalls_per_patient_fy || 0 },
  go_live: { label: "Go-live", get: (p) => p.go_live_date || "9999" },
  name: { label: "Practice", get: (p) => (p.name || "").toLowerCase() },
};

export default function LiveCohortTable({ practices, onSelect, onOverrideSaved }) {
  // Section 1 = Live AND recalling this FY (recalls_fy_to_date > 0).
  // The not-recalling cohort (FY == 0) lives in Section 2 (LiveStalledTable),
  // so the two are mutually exclusive and together cover every Live practice.
  const live = useMemo(
    () => practices.filter(
      (p) => LIVE_STAGES.has(p.stage) && (p.recalls_fy_to_date || 0) > 0
    ),
    [practices]
  );
  const totalLive = useMemo(
    () => practices.filter((p) => LIVE_STAGES.has(p.stage)).length,
    [practices]
  );

  const [bucketFilter, setBucketFilter] = useState(null);
  const [sortId, setSortId] = useState("fy_recalls");
  const [sortDir, setSortDir] = useState("desc");

  const bucketCounts = useMemo(() => {
    const out = {};
    for (const p of live) {
      const b = p.health_bucket;
      if (SECTION_BUCKETS.includes(b)) out[b] = (out[b] || 0) + 1;
    }
    return out;
  }, [live]);

  const filtered = useMemo(() => {
    let rows = live;
    if (bucketFilter) rows = rows.filter((p) => p.health_bucket === bucketFilter);
    const col = SORT_COLS[sortId];
    if (col) {
      rows = [...rows].sort((a, b) => {
        const av = col.get(a); const bv = col.get(b);
        if (av < bv) return sortDir === "asc" ? -1 : 1;
        if (av > bv) return sortDir === "asc" ? 1 : -1;
        return 0;
      });
    }
    return rows;
  }, [live, bucketFilter, sortId, sortDir]);

  const toggleSort = (id) => {
    if (sortId === id) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortId(id); setSortDir(id === "name" ? "asc" : "desc"); }
  };

  return (
    <section className="card" style={{ marginBottom: 20 }}>
      <header style={{ marginBottom: 6 }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>
          🟢 Live &amp; recalling
          <span className="muted" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>
            · {live.length} of {totalLive} live · {fyLabelFor()}
          </span>
        </h2>
        <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
          Live practices with ≥1 recall this financial year, sorted by FY recalls.
          The {totalLive - live.length} live-but-not-recalling practices are in the next section.
        </div>
      </header>

      <HealthBucketChips
        buckets={SECTION_BUCKETS}
        selected={bucketFilter}
        onChange={setBucketFilter}
        counts={bucketCounts}
      />

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ color: "var(--ink-3)", borderBottom: "1px solid var(--rule)" }}>
              <Th id="name" sortId={sortId} sortDir={sortDir} onClick={toggleSort} align="left">Practice</Th>
              <Th>Tier</Th>
              <Th>EHR</Th>
              <Th id="go_live" sortId={sortId} sortDir={sortDir} onClick={toggleSort}>Go-live</Th>
              <Th>Source</Th>
              <Th id="patients" sortId={sortId} sortDir={sortDir} onClick={toggleSort}>Patients</Th>
              <Th id="fy_recalls" sortId={sortId} sortDir={sortDir} onClick={toggleSort}>FY recalls</Th>
              <Th id="recalls_per_patient" sortId={sortId} sortDir={sortDir} onClick={toggleSort}>Recalls / patient</Th>
              <Th id="fy_bloods" sortId={sortId} sortDir={sortDir} onClick={toggleSort}>FY forms</Th>
              <Th id="this_month" sortId={sortId} sortDir={sortDir} onClick={toggleSort}>This month</Th>
              <Th>Testimonial</Th>
              <Th>Paid status</Th>
              <Th>Health</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => {
              const tier = TIER_BY_ID[p.tier || "Freemium"];
              return (
                <tr key={p.ods}
                    onClick={() => onSelect(p)}
                    style={{ cursor: "pointer", borderBottom: "1px solid var(--rule)" }}>
                  <td style={{ padding: "8px 6px" }}>
                    <div style={{ fontWeight: 500 }}>{p.name || p.ods}</div>
                    <div className="muted" style={{ fontSize: 10 }}>
                      {p.ods}{p.icb ? ` · ${shortenIcb(p.icb)}` : ""}
                    </div>
                  </td>
                  <td style={{ padding: "8px 6px" }}>
                    <span style={{ color: tier.color, fontSize: 11 }}>{tier.label}</span>
                  </td>
                  <td style={{ padding: "8px 6px" }}>
                    <EhrBadge ehr={p.ehr_type} compact />
                  </td>
                  <td style={{ padding: "8px 6px", fontSize: 11, color: "var(--ink-2)" }}>
                    {p.go_live_date || "—"}
                    {p.go_live_date_source === "snapshot" && (
                      <span title="from snapshot — edit in drilldown to confirm" className="muted" style={{ fontSize: 9, marginLeft: 3 }}>~</span>
                    )}
                  </td>
                  <td style={{ padding: "8px 6px" }} onClick={(e) => e.stopPropagation()}>
                    <SourceDropdown
                      ods={p.ods}
                      source={p.source}
                      confidence={p.source_confidence}
                      onOverrideSaved={onOverrideSaved}
                    />
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--ink-2)" }}>
                    {fmtInt(p.patients)}
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 500 }}>
                    {fmtInt(p.recalls_fy_to_date)}
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: (p.recalls_per_patient_fy || 0) > 0.05 ? "var(--good)" : "var(--ink-2)" }}>
                    {p.recalls_per_patient_fy != null ? p.recalls_per_patient_fy.toFixed(3) : "—"}
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {fmtInt(p.bloods_fy_to_date)}
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--ink-2)" }}>
                    {fmtInt(p.recalls_this_month)}
                  </td>
                  <td style={{ padding: "8px 6px" }}>
                    <TestimonialCell recallsFy={p.recalls_fy_to_date} />
                  </td>
                  <td style={{ padding: "8px 6px" }}>
                    <PaidStatusCell tier={p.tier || "Freemium"} recallsFy={p.recalls_fy_to_date} />
                  </td>
                  <td style={{ padding: "8px 6px" }}>
                    <HealthBadge bucket={p.health_bucket} compact />
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={13} style={{ padding: 16, textAlign: "center", color: "var(--ink-3)" }}>
                No live practices match the current filter.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Th({ id, sortId, sortDir, onClick, children, align = "right" }) {
  const sortable = id && onClick;
  const active = sortable && sortId === id;
  return (
    <th
      onClick={sortable ? () => onClick(id) : undefined}
      style={{
        padding: "8px 6px",
        textAlign: align,
        cursor: sortable ? "pointer" : "default",
        userSelect: "none",
        whiteSpace: "nowrap",
      }}
    >
      {children}{active ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
    </th>
  );
}
