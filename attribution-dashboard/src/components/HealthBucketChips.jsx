import React from "react";
import { bucketMeta } from "../utils/funnel.js";

// Scoped Health-bucket filter strip — accepts an allow-list of bucket IDs
// so each section only surfaces buckets relevant to its cohort
// (positive buckets in Section 1, stalled buckets in Section 2).
//
// Props:
//   buckets    — array of bucket IDs to render as chips
//   selected   — currently-selected bucket id, or null for "All"
//   onChange   — (bucketId | null) => void
//   counts     — { [bucketId]: number } optional, displayed as "(N)"
export default function HealthBucketChips({ buckets, selected, onChange, counts = {} }) {
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
      <Chip
        label="All"
        active={!selected}
        onClick={() => onChange(null)}
      />
      {buckets.map((b) => {
        const meta = bucketMeta(b);
        const n = counts[b];
        return (
          <Chip
            key={b}
            label={
              <>
                <span style={{ marginRight: 4 }}>{meta.emoji}</span>
                {meta.label}
                {n != null && <span style={{ marginLeft: 4, opacity: 0.6 }}>({n})</span>}
              </>
            }
            colour={meta.color}
            active={selected === b}
            onClick={() => onChange(selected === b ? null : b)}
          />
        );
      })}
    </div>
  );
}

function Chip({ label, active, onClick, colour }) {
  const c = colour || "var(--brand)";
  return (
    <button
      onClick={onClick}
      style={{
        padding: "4px 10px",
        fontSize: 11,
        borderRadius: 999,
        border: `1px solid ${active ? c : "var(--rule)"}`,
        background: active ? `${c}20` : "white",
        color: active ? c : "var(--ink-2)",
        cursor: "pointer",
        fontWeight: active ? 500 : 400,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </button>
  );
}
