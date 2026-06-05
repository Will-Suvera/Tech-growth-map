import React from "react";

// Clinical-system badge — EMIS or SystmOne (the two GP EHRs in England).
// Brand-ish colours: EMIS orange, SystmOne (TPP) teal/blue.
const EHR_META = {
  EMIS: { label: "EMIS", short: "EMIS", color: "#e8590c", bg: "#fff4e6" },
  SystmOne: { label: "SystmOne", short: "S1", color: "#1971c2", bg: "#e7f5ff" },
};

function normalise(raw) {
  if (!raw) return null;
  const s = String(raw).toLowerCase().replace(/[^a-z0-9]/g, "");
  if (s.includes("emis")) return "EMIS";
  if (s.includes("systmone") || s.includes("system1") || s.includes("systemone") || s === "s1" || s.includes("tpp")) return "SystmOne";
  return null;
}

export default function EhrBadge({ ehr, compact = false }) {
  const key = normalise(ehr);
  if (!key) {
    // Unrecognised but populated (e.g. "Medicus") — show raw value in grey
    // rather than "—", which would imply we have no data.
    if (ehr) {
      return (
        <span title={ehr} style={{
          display: "inline-block", padding: "2px 7px", fontSize: 11, fontWeight: 500,
          borderRadius: 4, background: "#f1f3f5", color: "var(--ink-2)",
          border: "1px solid var(--rule)", whiteSpace: "nowrap",
        }}>{ehr}</span>
      );
    }
    return <span style={{ color: "var(--ink-3)", fontSize: 11 }}>—</span>;
  }
  const m = EHR_META[key];
  return (
    <span
      title={m.label}
      style={{
        display: "inline-block",
        padding: "2px 7px",
        fontSize: 11,
        fontWeight: 600,
        borderRadius: 4,
        background: m.bg,
        color: m.color,
        border: `1px solid ${m.color}40`,
        whiteSpace: "nowrap",
      }}
    >
      {compact ? m.short : m.label}
    </span>
  );
}
