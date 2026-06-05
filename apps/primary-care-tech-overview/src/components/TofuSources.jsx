import React, { useMemo, useState } from "react";
import { fmtInt, fmtPct } from "../utils/fy.js";
import { shortenIcb } from "../utils/funnel.js";

// Section 4 — 🔵 Top of funnel — source of signed-ups.
// For practices in the signed_up stage, group by source. Click a bar → list expansion.
export default function TofuSources({ practices, onSelect }) {
  const data = useMemo(() => {
    const signedUp = practices.filter((p) => p.stage === "signed_up");
    const buckets = new Map();
    for (const p of signedUp) {
      const src = p.source || "unknown";
      const b = buckets.get(src) || { source: src, count: 0, practices: [] };
      b.count += 1;
      b.practices.push(p);
      buckets.set(src, b);
    }
    const total = signedUp.length;
    return {
      total,
      rows: [...buckets.values()]
        .map((b) => ({ ...b, pct: total ? b.count / total : 0 }))
        .sort((a, b) => b.count - a.count),
    };
  }, [practices]);

  const [expanded, setExpanded] = useState(null);
  const max = data.rows[0]?.count || 1;

  return (
    <section className="card" style={{ marginBottom: 20 }}>
      <header style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>
          🔵 Top of funnel — sources of {fmtInt(data.total)} signed-ups
        </h2>
        <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
          Click a source to expand the practice list.
        </div>
      </header>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {data.rows.map((r) => (
          <div key={r.source}>
            <button
              onClick={() => setExpanded(expanded === r.source ? null : r.source)}
              style={{
                display: "flex",
                width: "100%",
                alignItems: "center",
                gap: 12,
                padding: "8px 12px",
                background: expanded === r.source ? "var(--brand-soft)" : "white",
                border: "1px solid var(--rule)",
                borderRadius: 6,
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <div style={{ width: 200, flexShrink: 0, fontSize: 13, fontWeight: 500 }}>{r.source}</div>
              <div style={{ flex: 1, position: "relative", height: 18, background: "#f1f5f9", borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                  height: "100%",
                  width: `${(r.count / max) * 100}%`,
                  background: "var(--brand)",
                  borderRadius: 3,
                }} />
              </div>
              <div style={{ width: 80, textAlign: "right", fontVariantNumeric: "tabular-nums", fontSize: 13, fontWeight: 600 }}>
                {r.count}
              </div>
              <div style={{ width: 50, textAlign: "right", fontSize: 11, color: "var(--ink-3)" }}>
                {fmtPct(r.pct, { digits: 0 })}
              </div>
            </button>
            {expanded === r.source && (
              <div style={{ padding: "8px 12px", background: "#fafafa", border: "1px solid var(--rule)", borderTop: "none", borderRadius: "0 0 6px 6px" }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 4 }}>
                  {r.practices.map((p) => (
                    <button
                      key={p.ods}
                      onClick={() => onSelect(p)}
                      style={{ textAlign: "left", padding: "4px 6px", background: "white", border: "1px solid var(--rule)", borderRadius: 3, cursor: "pointer", fontSize: 11 }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "#f1f5f9")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "white")}
                    >
                      <div style={{ fontWeight: 500 }}>{p.name || p.ods}</div>
                      <div className="muted" style={{ fontSize: 10 }}>{p.ods}{p.icb && ` · ${shortenIcb(p.icb)}`}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
