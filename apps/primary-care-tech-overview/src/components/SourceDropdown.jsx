import React, { useState, useRef, useEffect } from "react";

// Canonical source taxonomy — mirrors scripts/enrich_live_practices.py.
// Keep in sync if the classifier vocabulary grows.
export const SOURCE_OPTIONS = [
  "Webinar (registered)",
  "Webinar (attended)",
  "Event (attended)",
  "Content download",
  "Existing relationship",
  "LinkedIn",
  "Outbound (Suvera)",
  "Notion meeting",
  "Unknown",
];

const CONF_COLOUR = {
  manual: "#0f766e",
  confirmed: "#0f766e",
  high: "#0f766e",
  medium: "#b35c00",
  low: "#8a949e",
  unknown: "#8a949e",
};

const OVERRIDE_API = "http://localhost:5175/api/overrides";

export default function SourceDropdown({ ods, source, confidence, onOverrideSaved }) {
  const current = source || "Unknown";
  const [open, setOpen] = useState(false);
  const [showOther, setShowOther] = useState(false);
  const [otherValue, setOtherValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const save = async (newSource) => {
    if (!newSource || newSource === current) { setOpen(false); return; }
    setSaving(true); setError(null);
    try {
      const r = await fetch(OVERRIDE_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ods, source: newSource, confidence: "manual" }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      onOverrideSaved?.({ ods, source: newSource, source_confidence: "manual" });
      setOpen(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const colour = CONF_COLOUR[confidence] || CONF_COLOUR.unknown;

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        title={`Confidence: ${confidence || "unknown"} — click to override`}
        style={{
          padding: "3px 8px",
          fontSize: 11,
          background: `${colour}15`,
          color: colour,
          border: `1px solid ${colour}40`,
          borderRadius: 4,
          cursor: "pointer",
          maxWidth: 180,
          textAlign: "left",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {saving ? "…" : current}
        <span style={{ marginLeft: 4, opacity: 0.6 }}>▾</span>
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            zIndex: 50,
            marginTop: 2,
            minWidth: 220,
            background: "white",
            border: "1px solid var(--rule)",
            borderRadius: 4,
            boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
            padding: 4,
          }}
        >
          {SOURCE_OPTIONS.map((opt) => (
            <button
              key={opt}
              onClick={() => save(opt)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "5px 8px",
                background: opt === current ? "var(--brand-soft)" : "transparent",
                color: opt === current ? "var(--brand)" : "var(--ink)",
                border: "none",
                borderRadius: 3,
                fontSize: 12,
                cursor: "pointer",
              }}
              onMouseEnter={(e) => { if (opt !== current) e.currentTarget.style.background = "#f1f5f9"; }}
              onMouseLeave={(e) => { if (opt !== current) e.currentTarget.style.background = "transparent"; }}
            >
              {opt}
            </button>
          ))}
          <div style={{ borderTop: "1px solid var(--rule)", marginTop: 4, paddingTop: 4 }}>
            {!showOther ? (
              <button
                onClick={() => setShowOther(true)}
                style={{ width: "100%", textAlign: "left", padding: "5px 8px", background: "transparent",
                         border: "none", fontSize: 12, color: "var(--ink-2)", cursor: "pointer", fontStyle: "italic" }}
              >Other…</button>
            ) : (
              <div style={{ padding: 4, display: "flex", gap: 4 }}>
                <input
                  autoFocus
                  value={otherValue}
                  onChange={(e) => setOtherValue(e.target.value)}
                  placeholder="Custom source…"
                  onKeyDown={(e) => e.key === "Enter" && save(otherValue)}
                  style={{ flex: 1, padding: "4px 6px", border: "1px solid var(--rule)", borderRadius: 3, fontSize: 12 }}
                />
                <button onClick={() => save(otherValue)} disabled={!otherValue}
                  style={{ padding: "4px 10px", background: "var(--brand)", color: "white", border: "none", borderRadius: 3, fontSize: 12, cursor: "pointer" }}
                >Save</button>
              </div>
            )}
          </div>
          {error && (
            <div style={{ padding: "4px 8px", fontSize: 11, color: "var(--bad)" }}>{error}</div>
          )}
        </div>
      )}
    </div>
  );
}
