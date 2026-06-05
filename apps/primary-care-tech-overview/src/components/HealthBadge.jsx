import React from "react";
import { bucketMeta } from "../utils/funnel.js";

export default function HealthBadge({ bucket, compact = false, title }) {
  const meta = bucketMeta(bucket);
  return (
    <span
      title={title || meta.label}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 11,
        lineHeight: 1.2,
        padding: compact ? "2px 6px" : "3px 8px",
        borderRadius: 999,
        background: `${meta.color}22`,
        color: meta.color,
        border: `1px solid ${meta.color}44`,
        fontWeight: 500,
        whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden>{meta.emoji}</span>
      {!compact && <span>{meta.label}</span>}
    </span>
  );
}
