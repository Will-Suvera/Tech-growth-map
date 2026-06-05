// UK Financial Year helpers (Apr 1 → Mar 31). Mirror of scripts/score_practices.py.

export function fyStartFor(date = new Date()) {
  const y = date.getMonth() + 1 >= 4 ? date.getFullYear() : date.getFullYear() - 1;
  return new Date(Date.UTC(y, 3, 1)); // April 1 UTC
}

export function fyLabelFor(date = new Date()) {
  const start = fyStartFor(date);
  const startYear = start.getUTCFullYear();
  return `FY${String(startYear).slice(2)}-${String(startYear + 1).slice(2)}`;
}

export function monthsInFy(date = new Date()) {
  const start = fyStartFor(date);
  const out = [];
  let y = start.getUTCFullYear();
  let m = start.getUTCMonth(); // 0-indexed
  const today = new Date();
  while (y < today.getFullYear() || (y === today.getFullYear() && m <= today.getMonth())) {
    out.push(`${y}-${String(m + 1).padStart(2, "0")}`);
    m += 1;
    if (m > 11) {
      m = 0;
      y += 1;
    }
  }
  return out;
}

// Pound formatter (sentinel for £/patient pricing displays)
export function fmtGbp(n, { compact = false } = {}) {
  if (n == null || isNaN(n)) return "—";
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 0,
    notation: compact ? "compact" : "standard",
  }).format(n);
}

export function fmtInt(n) {
  if (n == null || isNaN(n)) return "—";
  return new Intl.NumberFormat("en-GB").format(n);
}

export function fmtPct(n, { digits = 0 } = {}) {
  if (n == null || isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}
