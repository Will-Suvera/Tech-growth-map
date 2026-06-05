import React from "react";
import { TIER_BY_ID } from "../utils/funnel.js";
import { fmtInt } from "../utils/fy.js";

const FREEMIUM_CAP = 2000;
const TESTIMONIAL_THRESHOLD = 500;

// "Paid status" cell — tier-aware. Used in Live Cohort + Live Stalled tables.
//   Freemium     → "N to cap" + tiny progress bar
//   VC           → "Bundled" badge
//   Money-back   → "Paying ✓"
export default function PaidStatusCell({ tier = "Freemium", recallsFy = 0, compact = false }) {
  const tierMeta = TIER_BY_ID[tier];

  if (tier === "Money-back") {
    return (
      <span style={pillStyle("var(--good)")}>Paying ✓</span>
    );
  }
  if (tier === "VC") {
    return (
      <span style={pillStyle(tierMeta?.color || "#a855f7")}>Bundled</span>
    );
  }
  // Freemium — colour escalates as they approach the 2,000 cap.
  // Threshold matches NEAR_CAP_THRESHOLD in scripts/score_practices.py:
  // ≥1,000 FY recalls (≤1,000 remaining) = nearing end of freemium.
  const remaining = Math.max(0, FREEMIUM_CAP - (recallsFy || 0));
  const pct = Math.min(1, (recallsFy || 0) / FREEMIUM_CAP);
  const colour = remaining < 500 ? "#ef4444" : remaining <= 1000 ? "#fb923c" : "#94a3b8";
  return (
    <div style={{ minWidth: 110 }}>
      <div style={{ fontSize: 11, color: colour, marginBottom: 2, fontVariantNumeric: "tabular-nums" }}>
        {fmtInt(remaining)} to cap
      </div>
      {!compact && (
        <div style={{ height: 4, width: "100%", background: "#e2e8f0", borderRadius: 2, overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${pct * 100}%`, background: colour }} />
        </div>
      )}
    </div>
  );
}

export function TestimonialCell({ recallsFy = 0 }) {
  if (recallsFy >= TESTIMONIAL_THRESHOLD) {
    return <span style={pillStyle("var(--good)")}>✓ Past 500</span>;
  }
  const remaining = TESTIMONIAL_THRESHOLD - recallsFy;
  return (
    <span style={{ fontSize: 11, color: "var(--ink-3)" }}>
      {fmtInt(remaining)} to go
    </span>
  );
}

function pillStyle(colour) {
  return {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: 11,
    borderRadius: 999,
    background: `${colour}20`,
    color: colour,
    border: `1px solid ${colour}40`,
    fontWeight: 500,
    whiteSpace: "nowrap",
  };
}
