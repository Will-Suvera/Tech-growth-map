import React from "react";
import { fmtGbp, fmtInt } from "../utils/fy.js";
import { TIERS, TIER_BY_ID } from "../utils/funnel.js";

const TARGET_ARR = 1_000_000;

export default function ArrProgressHeader({
  stats,
  pricePerPatient,
  setPricePerPatient,
  confirmedOnly,
  setConfirmedOnly,
  generatedAt,
}) {
  const pct = Math.min(1, stats.actual_arr / TARGET_ARR);
  return (
    <header style={{ marginBottom: 24 }}>
      <div className="topbar">
        <div>
          <h1>Planner Growth</h1>
          <div className="meta">
            {fmtInt(stats.total)} practices in pipeline ·{" "}
            {generatedAt ? `data refreshed ${new Date(generatedAt).toLocaleString("en-GB")}` : ""}
          </div>
        </div>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <label style={{ display: "flex", flexDirection: "column", fontSize: 11, color: "var(--ink-3)" }}>
            <span>£ per patient (Money-back tier)</span>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="number"
                step="0.05"
                min="0"
                max="5"
                value={pricePerPatient}
                onChange={(e) => setPricePerPatient(Number(e.target.value) || 0)}
                style={{
                  width: 72,
                  padding: "4px 6px",
                  border: "1px solid var(--rule)",
                  borderRadius: 4,
                  fontSize: 13,
                }}
              />
              <span style={{ fontSize: 12, color: "var(--ink-2)" }}>
                {(pricePerPatient || 0).toFixed(2)} × patients = ARR per practice
              </span>
            </div>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--ink-2)" }}>
            <input
              type="checkbox"
              checked={confirmedOnly}
              onChange={(e) => setConfirmedOnly(e.target.checked)}
            />
            Confirmed source only
          </label>
        </div>
      </div>

      {/* ARR progress bar */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12 }}>
          <span style={{ color: "var(--ink-2)" }}>
            <strong style={{ color: "var(--ink)" }}>{fmtGbp(stats.actual_arr)}</strong> actual ARR
            {" · "}
            <span style={{ color: "var(--ink-3)" }}>
              {fmtGbp(stats.potential_arr)} potential at {(pricePerPatient || 0).toFixed(2)} £/patient
            </span>
          </span>
          <span style={{ color: "var(--ink-3)" }}>
            target {fmtGbp(TARGET_ARR)} · {(pct * 100).toFixed(1)}%
          </span>
        </div>
        <div style={{
          height: 8,
          background: "var(--rule)",
          borderRadius: 4,
          overflow: "hidden",
          position: "relative",
        }}>
          <div style={{
            width: `${pct * 100}%`,
            height: "100%",
            background: pct > 0 ? "var(--brand)" : "transparent",
            borderRadius: 4,
          }} />
        </div>
      </div>

      {/* Tier mix chips */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {TIERS.map((t) => {
          const n = stats.by_tier[t.id] || 0;
          return (
            <span key={t.id} style={{
              padding: "4px 10px",
              borderRadius: 6,
              background: `${t.color}15`,
              border: `1px solid ${t.color}40`,
              color: t.color,
              fontSize: 12,
              fontWeight: 500,
            }}>
              <strong style={{ color: t.color }}>{n}</strong>{" "}
              <span style={{ color: "var(--ink-2)" }}>{t.label}</span>
            </span>
          );
        })}
      </div>
    </header>
  );
}
