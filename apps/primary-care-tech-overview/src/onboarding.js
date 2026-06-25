// Shared onboarding state — the Neon-backed step toggle path, used by both the
// Overview tab (FunnelBoard, read-mostly) and the Onboarding Hub tab (the action
// surface). Extracted from FunnelBoard so there is a single write path and the
// two tabs reflect the same live state.
import { useEffect, useState } from "react";

// Onboarding-toggle API (Neon-backed). Dev: local Node server (/api/onboarding on :5175).
// Prod: Netlify Function (/.netlify/functions/onboarding). Override via VITE_ONB_API.
export const ONB_BASE =
  (import.meta.env && import.meta.env.VITE_ONB_API) ||
  (import.meta.env && import.meta.env.PROD ? "/.netlify/functions/onboarding" : "http://localhost:5175/api/onboarding");

export const STATE_CYCLE = { todo: "pending", pending: "done", done: "todo" };

// Merge live (Neon) onboarding state over the sheet-derived steps.
//
// A human in-app toggle is the source of truth and wins. A record that was only
// ever seeded from the Google Sheet ('sheet-seed') defers to the fresh sheet
// value baked into `steps` — funnel_board.json is rebuilt from the read-only
// onboarding sheet on every data refresh, so ongoing sheet edits keep flowing
// through instead of being frozen at the one-time seed. (Without this, a step
// the sheet later marks done stays masked by its stale 5-Jun seed value.)
export function mergeOnboarding(steps, liveForOds) {
  if (!steps || !liveForOds) return steps;
  return steps.map((s) => {
    const live = liveForOds[s.key];
    if (live && live.changed_by !== "sheet-seed") {
      return { ...s, state: live.state, changed_at: live.changed_at, changed_by: live.changed_by };
    }
    return s; // untouched seed → the fresh sheet value (from funnel_board.json) wins
  });
}

export function summarizeOnboarding(steps) {
  const done = steps.filter((s) => s.state === "done").length;
  const next = steps.find((s) => s.state !== "done");
  return { done, total: steps.length, next: next ? next.step : null };
}

// The 9 technical (IT-provisioning) onboarding steps that the Onboarding Hub
// tracks for DPA-signed-onwards practices. These are Neon-only (NOT in the
// Google Sheet, so they are never seeded) — they default to "todo" until a CS
// teammate first toggles them in the hub. The `tech_` prefix namespaces them
// away from the 10 business steps that live in the same onboarding_current table.
export const TECH_STEPS = [
  { key: "tech_sharing_agreement", step: "Sharing agreement", hint: "EMIS sharing agreement activated" },
  { key: "tech_suvera_user", step: "Add Suvera user", hint: "Suvera service account created in the EHR" },
  { key: "tech_suvera_rbac", step: "Suvera role & RBAC", hint: "Suvera user given the correct role / RBAC" },
  { key: "tech_herohealth_user", step: "Add HeroHealth user", hint: "HeroHealth service account created" },
  { key: "tech_herohealth_rbac", step: "HeroHealth role & RBAC", hint: "HeroHealth user given the correct role / RBAC" },
  { key: "tech_partner_api", step: "Partner API", hint: "Partner / IM1 API enabled for the practice" },
  { key: "tech_api_passwords", step: "API passwords", hint: "API credentials issued" },
  { key: "tech_login_access", step: "Login access", hint: "Login access confirmed working" },
  { key: "tech_booking_links", step: "Booking links", hint: "Booking links live on the practice site" },
];

// Build a practice's working technical-step array from the live Neon state.
export function techStepsFor(liveForOds) {
  return TECH_STEPS.map((t) => {
    const live = liveForOds?.[t.key];
    return { ...t, state: live?.state || "todo", changed_at: live?.changed_at, changed_by: live?.changed_by };
  });
}

// Read-only roll-up of the 9 technical steps for one practice (used by the
// Overview tab to reflect Hub progress, and by the Hub sidebar/cards).
export function techProgress(liveForOds) {
  let done = 0;
  for (const t of TECH_STEPS) if (liveForOds?.[t.key]?.state === "done") done++;
  const next = TECH_STEPS.find((t) => (liveForOds?.[t.key]?.state || "todo") !== "done");
  return { done, total: TECH_STEPS.length, next: next ? next.step : null };
}

// Hook owning the live onboarding state + the timestamped toggle write path.
// `auth` is the signed-in Google user ({ email, token }) in prod, null in local dev.
export function useOnboarding(auth = null) {
  const [liveOnb, setLiveOnb] = useState({});
  const [who, setWho] = useState(() => (typeof localStorage !== "undefined" && localStorage.getItem("pcto.who")) || "");
  useEffect(() => {
    fetch(ONB_BASE).then((r) => r.json()).then(setLiveOnb).catch(() => {});
  }, []);

  const editor = auth?.email || who || null; // SSO email in prod, name field in local dev

  // Cycle a step todo→pending→done→todo, optimistically, and POST a timestamped
  // event to Neon. Skips practices with no ODS (the API keys on ods).
  async function toggleStep(deal, step) {
    if (!deal?.ods) return;
    const cur = liveOnb[deal.ods]?.[step.key]?.state ?? step.state ?? "todo";
    const next = STATE_CYCLE[cur] || "todo";
    setLiveOnb((prev) => ({
      ...prev,
      [deal.ods]: { ...(prev[deal.ods] || {}), [step.key]: { state: next, changed_by: editor || "(you)", changed_at: new Date().toISOString() } },
    }));
    try {
      await fetch(`${ONB_BASE}/step`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}) },
        body: JSON.stringify({ ods: deal.ods, deal_id: String(deal.deal_id || ""), step_key: step.key, to_state: next, changed_by: editor }),
      });
    } catch { /* keep optimistic update */ }
  }

  return { liveOnb, setLiveOnb, who, setWho, editor, toggleStep };
}
