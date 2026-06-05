import React, { useMemo } from "react";
import HealthBadge from "./HealthBadge.jsx";
import EhrBadge from "./EhrBadge.jsx";
import { prettyStage, shortenIcb, TIER_BY_ID } from "../utils/funnel.js";
import { fmtGbp, fmtInt } from "../utils/fy.js";

export default function PracticeDrilldown({ practice, pricePerPatient, onClose, onOverrideSaved }) {
  const p = practice;
  const tier = TIER_BY_ID[p.tier || "Freemium"];
  const arrPotential = (p.patients || 0) * (pricePerPatient || 0);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 880 }}>
        <span className="close-x" onClick={onClose}>×</span>
        <h2 style={{ marginBottom: 4 }}>{p.name || p.ods}</h2>
        <div style={{ color: "var(--ink-3)", fontSize: 12, marginBottom: 8 }}>
          {p.ods}
          {p.icb && ` · ${shortenIcb(p.icb)}`}
          {p.pcn_name && ` · ${p.pcn_name}`}
          {p.patients && ` · ${fmtInt(p.patients)} patients`}
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16, alignItems: "center" }}>
          <span className="pill" style={{ background: `${tier.color}20`, color: tier.color, border: `1px solid ${tier.color}50` }}>
            {tier.label}
          </span>
          <HealthBadge bucket={p.health_bucket} />
          {p.ehr_type && <EhrBadge ehr={p.ehr_type} />}
          <span className="pill pill-confirmed" title="Funnel stage">{prettyStage(p.stage)}</span>
          {p.go_live_date && (
            <span className="pill" style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
                  title={p.go_live_date_source === "manual" ? "Manually set" : "From snapshot — edit override to confirm"}>
              Go-live {p.go_live_date}{p.go_live_date_source === "snapshot" && " ~"}
            </span>
          )}
          <span className="pill" style={{ background: "#fafafa", color: "var(--ink-2)" }}>
            ARR potential {fmtGbp(arrPotential)}
          </span>
        </div>

        <SourceSection p={p} />
        <JourneyTimeline p={p} />
        <PracticeVisitSection p={p} />
        <DecisionMakers p={p} />
        <UsageSection p={p} pricePerPatient={pricePerPatient} />
        <TerritorySection p={p} pricePerPatient={pricePerPatient} />
      </div>
    </div>
  );
}

function SourceSection({ p }) {
  const evidence = p.source_inferred_evidence || [];
  return (
    <section>
      <h3>Source</h3>
      <div>
        <strong>{p.source || "unknown"}</strong>{" "}
        <span className={`pill pill-${p.source_confidence}`}>{p.source_confidence}</span>
      </div>
      {evidence.length > 0 && (
        <ul style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 6, paddingLeft: 18 }}>
          {evidence.slice(0, 5).map((e, i) => (
            <li key={i}>{typeof e === "string" ? e : `${e.channel || ""}: ${e.list || e.contact || ""}`}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function JourneyTimeline({ p }) {
  // Build chronological event list: signed_up_date, contact engagement proxies,
  // meetings, practice visit, recall starts (only first month).
  const events = useMemo(() => {
    const out = [];
    if (p.signed_up_date) out.push({ date: p.signed_up_date.slice(0, 10), label: "Earliest contact created", kind: "contact" });
    let emailOut = 0, emailIn = 0;
    for (const c of p.contacts || []) {
      const ep = c.engagement_proxy || {};
      if (ep.first_email_send_date) emailOut += 1;
      if (ep.first_email_reply_date) emailIn += 1;
    }
    if (emailOut || emailIn) {
      out.push({
        date: null, // sticks at "engagement cluster" without a specific date
        label: `Email cluster — ${emailOut} outbound contacts, ${emailIn} reply contacts`,
        kind: "cluster",
      });
    }
    for (const m of p.meetings || []) {
      out.push({
        date: (m.date || "").slice(0, 10) || null,
        label: `Sync call: ${m.title || "meeting"}${m.partner_role ? ` (${m.partner_role})` : ""}`,
        kind: "meeting",
        signal: m.opportunity_signal,
      });
    }
    if (p.practice_visit_status && p.practice_visit_status !== "none") {
      out.push({
        date: (p.practice_visit_date || "").slice(0, 10) || null,
        label: `Practice visit — ${p.practice_visit_status}`,
        kind: "visit",
      });
    }
    // Sort: dated events chronologically, then undated at the bottom
    out.sort((a, b) => {
      if (!a.date && !b.date) return 0;
      if (!a.date) return 1;
      if (!b.date) return -1;
      return a.date.localeCompare(b.date);
    });
    // Inject "days between" annotations
    let prevDate = null;
    return out.map((e) => {
      let gap = null;
      if (e.date && prevDate) {
        const days = Math.round((new Date(e.date) - new Date(prevDate)) / 86400000);
        if (days > 0) gap = `${days}d`;
      }
      if (e.date) prevDate = e.date;
      return { ...e, gap };
    });
  }, [p]);

  if (events.length === 0) return null;
  return (
    <section>
      <h3>Journey timeline</h3>
      <div style={{ borderLeft: "2px solid var(--rule)", paddingLeft: 12, marginLeft: 4 }}>
        {events.map((e, i) => (
          <div key={i} style={{ position: "relative", marginBottom: 8, fontSize: 12 }}>
            <div style={{
              position: "absolute", left: -18, top: 5, width: 8, height: 8,
              borderRadius: "50%",
              background: e.kind === "meeting" ? "var(--brand)" : e.kind === "visit" ? "var(--good)" : "var(--ink-3)",
            }} />
            <div>
              <strong>{e.label}</strong>
              {e.signal && <span className={`pill pill-${e.signal?.toLowerCase()}`} style={{ marginLeft: 6 }}>{e.signal}</span>}
            </div>
            <div className="muted" style={{ fontSize: 10 }}>
              {e.date || "no date"}{e.gap && ` · +${e.gap} since previous`}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function PracticeVisitSection({ p }) {
  const status = p.practice_visit_status || "none";
  const colour = status === "happened" ? "var(--good)" : status === "scheduled" ? "var(--brand)" : "var(--ink-3)";
  const icon = status === "happened" ? "✅" : status === "scheduled" ? "📅" : "❌";
  const label = status === "happened" ? `Visit happened ${p.practice_visit_date ? `on ${p.practice_visit_date}` : ""}` :
                 status === "scheduled" ? `Visit scheduled ${p.practice_visit_date ? `for ${p.practice_visit_date}` : ""}` :
                 "No visit logged";
  return (
    <section>
      <h3>Practice visit</h3>
      <div style={{ display: "flex", alignItems: "center", gap: 8, color: colour, fontSize: 13, marginBottom: 6 }}>
        <span aria-hidden style={{ fontSize: 18 }}>{icon}</span>
        <span>{label}</span>
      </div>
      {(p.practice_visit_attendees?.length || p.practice_visit_times || p.practice_visit_site_address || p.practice_visit_problems || p.practice_visit_outcome) && (
        <div style={{ fontSize: 12, color: "var(--ink-2)", paddingLeft: 26 }}>
          {p.practice_visit_attendees?.length > 0 && (
            <div>👥 {p.practice_visit_attendees.join(", ")}</div>
          )}
          {p.practice_visit_times && (
            <div style={{ whiteSpace: "pre-line" }}>🕒 {p.practice_visit_times}</div>
          )}
          {p.practice_visit_site_address && (
            <div>📍 {p.practice_visit_site_address}</div>
          )}
          {p.practice_visit_outcome && (
            <div style={{ marginTop: 6, padding: 8, background: "#ecfdf5", border: "1px solid #6ee7b7", borderRadius: 4, color: "#065f46", whiteSpace: "pre-line" }}>
              ✅ <strong>Outcome:</strong> {p.practice_visit_outcome}
            </div>
          )}
          {p.practice_visit_problems && (
            <div style={{ marginTop: 6, padding: 8, background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 4, color: "#9a3412", whiteSpace: "pre-line" }}>
              ⚠ <strong>Problems:</strong> {p.practice_visit_problems}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function DecisionMakers({ p }) {
  const roleEntries = Object.entries(p.role_counts || {});
  if (!roleEntries.length) return (
    <section><h3>Decision-makers</h3><em style={{ fontSize: 12 }}>No identified roles.</em></section>
  );
  const hasPartner = roleEntries.some(([r]) => r === "GP Partner");
  const hasPm = roleEntries.some(([r]) => r === "Practice Manager");
  return (
    <section>
      <h3>Decision-makers</h3>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {roleEntries.map(([r, n]) => (
          <span key={r} className="pill pill-low">{r} · {n}</span>
        ))}
      </div>
      {hasPartner && hasPm && (
        <div style={{ marginTop: 6, fontSize: 12, color: "var(--good)" }}>
          ✓ GP Partner + Practice Manager both engaged — the converting pair.
        </div>
      )}
      {!hasPartner && !hasPm && (
        <div style={{ marginTop: 6, fontSize: 12, color: "var(--warn)" }}>
          ⚠ Neither GP Partner nor Practice Manager engaged — high-risk profile.
        </div>
      )}
    </section>
  );
}

function UsageSection({ p, pricePerPatient }) {
  const recallsFy = p.recalls_fy_to_date || 0;
  const formsFy = p.bloods_fy_to_date || 0;
  const milestones = [];
  if ((p.tier || "Freemium") === "Freemium") {
    const remaining = Math.max(0, 2000 - recallsFy);
    milestones.push({ label: `${fmtInt(remaining)} recalls until freemium cap`, color: remaining < 500 ? "var(--warn)" : "var(--ink-2)" });
  }
  const testimonialGap = 500 - recallsFy;
  if (testimonialGap > 0 && testimonialGap < 500) {
    milestones.push({ label: `${fmtInt(testimonialGap)} from testimonial-ready`, color: "var(--brand)" });
  } else if (testimonialGap <= 0) {
    milestones.push({ label: `${fmtInt(-testimonialGap)} past testimonial threshold ✓`, color: "var(--good)" });
  }
  return (
    <section>
      <h3>Usage today</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
        <Kpi label="FY recalls" value={fmtInt(recallsFy)} />
        <Kpi label="FY forms" value={fmtInt(formsFy)} />
        <Kpi label="Recalls / patient" value={p.recalls_per_patient_fy != null ? p.recalls_per_patient_fy.toFixed(4) : "—"} />
        <Kpi label="Forms / patient" value={p.bloods_per_patient_fy != null ? p.bloods_per_patient_fy.toFixed(4) : "—"} />
      </div>
      {p.forms_to_recalls_ratio != null && (
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          Forms : recalls ratio = {p.forms_to_recalls_ratio.toFixed(2)}
        </div>
      )}
      {milestones.length > 0 && (
        <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
          {milestones.map((m, i) => (
            <span key={i} style={{ fontSize: 11, color: m.color, padding: "3px 8px", border: `1px solid ${m.color}40`, borderRadius: 999 }}>
              {m.label}
            </span>
          ))}
        </div>
      )}
      <ClinicianBreakdown p={p} />
    </section>
  );
}

function ClinicianBreakdown({ p }) {
  const recallsByMonth = p.recalls_by_month;
  const bloodsByMonthClinician = p.bloods_by_month_clinician;
  if (!recallsByMonth && !bloodsByMonthClinician) return null;
  return (
    <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 14 }}>
      {recallsByMonth && (
        <div>
          <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
            Recalls by month
          </div>
          <table style={{ fontSize: 12, width: "100%" }}>
            <tbody>
              {Object.entries(recallsByMonth).map(([m, n]) => (
                <tr key={m} style={{ borderBottom: "1px solid var(--rule)" }}>
                  <td style={{ padding: "3px 0", color: "var(--ink-2)" }}>{m}</td>
                  <td style={{ padding: "3px 0", textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 500 }}>{n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {bloodsByMonthClinician && (
        <div>
          <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
            Forms by month + clinician
          </div>
          {Object.entries(bloodsByMonthClinician).map(([m, clinicians]) => (
            <div key={m} style={{ marginBottom: 6 }}>
              <div style={{ fontSize: 11, color: "var(--ink-2)", marginBottom: 2 }}>{m}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {Object.entries(clinicians).map(([clin, n]) => (
                  <span key={clin}
                        style={{
                          padding: "2px 7px",
                          fontSize: 11,
                          borderRadius: 999,
                          background: "#f1f5f9",
                          color: "var(--ink)",
                          border: "1px solid var(--rule)",
                          whiteSpace: "nowrap",
                        }}>
                    {clin} <strong style={{ color: "var(--brand)" }}>{n}</strong>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TerritorySection({ p, pricePerPatient }) {
  if (!p.pcn_name && !p.icb) return null;
  return (
    <section>
      <h3>🌍 Territory</h3>
      {p.pcn_name && (
        <div style={{ fontSize: 12, marginBottom: 6 }}>
          <strong>{p.pcn_name}</strong>: {p.pcn_total_practices ?? "?"} practices in the PCN ·{" "}
          {p.pcn_signed_count ?? 0} ours · {p.pcn_recalling_count ?? 0} recalling ·{" "}
          <span style={{ color: "var(--brand)" }}>{p.pcn_untapped_count ?? 0} untapped</span>
          {p.pcn_untapped_count > 0 && (
            <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
              Untapped neighbours: {(p.pcn_untapped_ods || []).slice(0, 8).join(", ")}
              {(p.pcn_untapped_ods || []).length > 8 && "…"}
            </div>
          )}
        </div>
      )}
      {p.icb && (
        <div style={{ fontSize: 12 }}>
          <strong>{shortenIcb(p.icb)}</strong> ICB: {p.icb_signed_count ?? 0} signed · {p.icb_live_count ?? 0} live ·{" "}
          {p.icb_recalling_count ?? 0} recalling
        </div>
      )}
    </section>
  );
}

function Kpi({ label, value }) {
  return (
    <div style={{ padding: 8, background: "#fafafa", border: "1px solid var(--rule)", borderRadius: 4 }}>
      <div className="muted" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>{value}</div>
    </div>
  );
}
