// Single source of truth for stage + Health bucket vocabulary.
// Mirrors scripts/score_practices.py — keep in sync.

export const STAGES = [
  { id: "signed_up", label: "Signed up", short: "Signed" },
  { id: "onboarding", label: "Signed DPA", short: "DPA" },
  { id: "live_partial", label: "Live", short: "Live" },
  { id: "live_full", label: "Live (Full Planner)", short: "Live+" },
];

export const STAGE_ORDER = ["signed_up", "onboarding", "live_partial", "live_full"];

export const LIVE_STAGES = new Set(["live_partial", "live_full"]);

export function prettyStage(stageId) {
  const s = STAGES.find((s) => s.id === stageId);
  return s ? s.label : stageId || "—";
}

export function isLive(row) {
  return LIVE_STAGES.has(row?.stage);
}

// Health buckets — priority order (high to low).
// Single displayed pill follows this order on ties.
export const HEALTH_BUCKETS = [
  { id: "near_cap",            emoji: "🔥", label: "Near freemium cap",   color: "#fb923c", bucket: "revenue"    },
  { id: "testimonial_ready",   emoji: "🏆", label: "Testimonial-ready",   color: "#f59e0b", bucket: "revenue"    },
  { id: "expansion_super_user", emoji: "💎", label: "Expansion super-user", color: "#a855f7", bucket: "revenue"   },
  { id: "vc_paying_not_using", emoji: "⚡", label: "VC paying-not-using", color: "#eab308", bucket: "activation" },
  { id: "cadence_dropping",    emoji: "🟠", label: "Cadence dropping",    color: "#f97316", bucket: "activation" },
  { id: "dormant",             emoji: "🔴", label: "Dormant",             color: "#ef4444", bucket: "activation" },
  { id: "healthy",             emoji: "🟢", label: "Healthy",             color: "#22c55e", bucket: null         },
  { id: "pre_live",            emoji: "⚪", label: "Pre-live",            color: "#94a3b8", bucket: null         },
];

export const HEALTH_BUCKET_BY_ID = Object.fromEntries(HEALTH_BUCKETS.map((b) => [b.id, b]));

export function bucketMeta(id) {
  return HEALTH_BUCKET_BY_ID[id] || HEALTH_BUCKET_BY_ID.pre_live;
}

// Action-card buckets (the three top-level groupings on the home page)
export const ACTION_BUCKETS = [
  { id: "revenue",   emoji: "💰", label: "Revenue moves",   subtitle: "money on the table" },
  { id: "activation", emoji: "⚡", label: "Activation moves", subtitle: "signed but not getting value" },
  { id: "pipeline",  emoji: "🔴", label: "Pipeline moves",  subtitle: "deals at risk" },
];

// Tier display + ARR multiplier (mirror of TIER_ARR_MULTIPLIER in score_practices.py)
export const TIERS = [
  { id: "Freemium",   label: "Freemium",   color: "#94a3b8", arrMultiplier: 0.0 }, // £0 actual
  { id: "Money-back", label: "Money-back", color: "#22c55e", arrMultiplier: 1.0 }, // contributes ARR
  { id: "VC",         label: "VC bundle",  color: "#a855f7", arrMultiplier: 0.0 }, // £0 actual
];

export const TIER_BY_ID = Object.fromEntries(TIERS.map((t) => [t.id, t]));

export function shortenIcb(icb) {
  if (!icb) return "";
  return icb.replace(/^NHS\s+/, "").replace(/\s+Integrated Care Board$/i, "").replace(/\s+ICB$/i, "");
}
