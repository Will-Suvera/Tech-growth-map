import React, { useMemo, useState } from "react";
import HealthBadge from "./HealthBadge.jsx";
import HealthBucketChips from "./HealthBucketChips.jsx";
import SourceDropdown from "./SourceDropdown.jsx";
import { TIER_BY_ID, shortenIcb, LIVE_STAGES } from "../utils/funnel.js";

// Section 2 — 🟠 Live but not recalling (FY-to-date == 0).
// Stalled-bucket vocabulary only.
const SECTION_BUCKETS = ["dormant", "vc_paying_not_using", "cadence_dropping"];

const VISIT_ICON = { happened: "✅", scheduled: "📅", none: "❌" };
const VISIT_LABEL = { happened: "Completed", scheduled: "Confirmed", none: "Not logged" };
const VISIT_COLOUR = { happened: "var(--good)", scheduled: "var(--brand)", none: "var(--ink-3)" };

function likelyCause(p) {
  const s = p.practice_visit_status || "none";
  if (s === "happened") return "Adoption blocker — check Problems";
  if (s === "scheduled") return "Intervention upcoming";
  return "Schedule a launch visit";
}

function daysSince(date) {
  if (!date) return null;
  try {
    return Math.round((Date.now() - new Date(date).getTime()) / 86400000);
  } catch { return null; }
}

export default function LiveStalledTable({ practices, onSelect, onOverrideSaved }) {
  const stalled = useMemo(
    () => practices.filter(
      (p) => LIVE_STAGES.has(p.stage) && (p.recalls_fy_to_date || 0) === 0
    ),
    [practices]
  );

  const [bucketFilter, setBucketFilter] = useState(null);

  const bucketCounts = useMemo(() => {
    const out = {};
    for (const p of stalled) {
      const b = p.health_bucket;
      if (SECTION_BUCKETS.includes(b)) out[b] = (out[b] || 0) + 1;
    }
    return out;
  }, [stalled]);

  const filtered = bucketFilter ? stalled.filter((p) => p.health_bucket === bucketFilter) : stalled;

  return (
    <section className="card" style={{ marginBottom: 20 }}>
      <header style={{ marginBottom: 6 }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>
          🔴 Live &amp; not recalling
          <span className="muted" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>
            · {stalled.length} of {practices.filter((p) => LIVE_STAGES.has(p.stage)).length} live · 0 recalls this FY
          </span>
        </h2>
        <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
          Strict "never activated this FY" cohort. Cross-tabbed with practice-visit status.
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
              <th style={{ padding: "8px 6px", textAlign: "left" }}>Practice</th>
              <th style={{ padding: "8px 6px" }}>Tier</th>
              <th style={{ padding: "8px 6px" }}>Source</th>
              <th style={{ padding: "8px 6px", textAlign: "right" }}>Days since go-live</th>
              <th style={{ padding: "8px 6px", textAlign: "left" }}>Practice visit</th>
              <th style={{ padding: "8px 6px", textAlign: "left" }}>Problems (if past visit)</th>
              <th style={{ padding: "8px 6px", textAlign: "left" }}>Likely cause</th>
              <th style={{ padding: "8px 6px" }}>Health</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => {
              const tier = TIER_BY_ID[p.tier || "Freemium"];
              const visitStatus = p.practice_visit_status || "none";
              const days = daysSince(p.go_live_date);
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
                  <td style={{ padding: "8px 6px" }} onClick={(e) => e.stopPropagation()}>
                    <SourceDropdown
                      ods={p.ods}
                      source={p.source}
                      confidence={p.source_confidence}
                      onOverrideSaved={onOverrideSaved}
                    />
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {days != null ? `${days}d` : "—"}
                  </td>
                  <td style={{ padding: "8px 6px", color: VISIT_COLOUR[visitStatus] }}>
                    <span aria-hidden style={{ marginRight: 4 }}>{VISIT_ICON[visitStatus]}</span>
                    {VISIT_LABEL[visitStatus]}
                    {p.practice_visit_date && <span className="muted" style={{ fontSize: 10, marginLeft: 4 }}>{p.practice_visit_date}</span>}
                  </td>
                  <td style={{ padding: "8px 6px", fontSize: 11, maxWidth: 240 }}>
                    {p.practice_visit_problems ? (
                      <span title={p.practice_visit_problems}>
                        {p.practice_visit_problems.slice(0, 80)}{p.practice_visit_problems.length > 80 ? "…" : ""}
                      </span>
                    ) : <span className="muted">—</span>}
                  </td>
                  <td style={{ padding: "8px 6px", fontSize: 11, color: "var(--ink-2)" }}>
                    {likelyCause(p)}
                  </td>
                  <td style={{ padding: "8px 6px" }}>
                    <HealthBadge bucket={p.health_bucket} compact />
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={8} style={{ padding: 16, textAlign: "center", color: "var(--ink-3)" }}>
                {stalled.length === 0 ? "No stalled live practices ✓" : "No practices match the current filter."}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
