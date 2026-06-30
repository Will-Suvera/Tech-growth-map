// Shared onboarding state — the Neon-backed step toggle path, used by both the
// Overview tab (FunnelBoard, read-mostly) and the Onboarding Hub tab (the action
// surface). Extracted from FunnelBoard so there is a single write path and the
// two tabs reflect the same live state.
import { useEffect, useState } from "react";

// Onboarding-toggle API (Neon-backed). Dev: local Node server (/api/onboarding on :5175).
// Prod: same-origin /api/onboarding — a Cloudflare Pages Function (functions/api/[[path]].js).
// Override via VITE_ONB_API. (Also works on Netlify, which rewrites /api/onboarding/*
// to its function — see netlify.toml — so the path is correct on either host.)
export const ONB_BASE =
  (import.meta.env && import.meta.env.VITE_ONB_API) ||
  (import.meta.env && import.meta.env.PROD ? "/api/onboarding" : "http://localhost:5175/api/onboarding");

export const STATE_CYCLE = { todo: "pending", pending: "done", done: "todo" };

// "will@suvera.co.uk" -> "Will"; "will.gao@…" -> "Will". Used so the UI attributes
// changes to a person's first name (taken from the Google login) instead of asking
// them to type a name. Falls back to the cleaned local-part, then null.
export function firstNameFromEmail(email) {
  if (!email) return null;
  const local = String(email).split("@")[0] || "";
  const first = (local.split(/[._\-\s]+/)[0] || local).trim();
  return first ? first.charAt(0).toUpperCase() + first.slice(1) : null;
}

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
  // "na" steps (e.g. EMIS/sharing for SystmOne) are not applicable — they don't
  // count toward the total or the next outstanding step.
  const applicable = steps.filter((s) => s.state !== "na");
  const done = applicable.filter((s) => s.state === "done").length;
  const next = applicable.find((s) => s.state !== "done");
  return { done, total: applicable.length, next: next ? next.step : null };
}

// Effective onboarding steps for a practice: the Google-Sheet-derived business
// steps (carried on the deal as `onboarding`) with any in-app Neon toggles merged
// over the top. This is the single step model both tabs render, so the Hub reflects
// the practice's real set-up state rather than a blank slate.
export function onboardingFor(deal, liveForOds) {
  if (!deal?.onboarding?.length) return [];
  return mergeOnboarding(deal.onboarding, liveForOds) || [];
}

// Hook owning the live onboarding state + the timestamped toggle write path.
// `auth` is the signed-in Google user ({ email, token }) in prod, null in local dev.
// Who we're waiting on for a blocked step — display labels.
export const WAITING_ON = ["us", "practice", "third_party"];
export const WAITING_LABEL = { us: "Us / Suvera", practice: "Practice", third_party: "Third-party" };

export function useOnboarding(auth = null) {
  const [liveOnb, setLiveOnb] = useState({});
  const [notes, setNotes] = useState({}); // ods -> [{id, body, author, created_at, hs_synced}] newest-first
  const [blocks, setBlocks] = useState({}); // ods -> { step_key: {waiting_on, reason, blocked_at, blocked_by} }
  const [live, setLive] = useState({});     // ods -> {marked_by, marked_at, hs_synced}
  const [error, setError] = useState(null); // user-visible "something didn't reach the server" hint
  const [who, setWho] = useState(() => (typeof localStorage !== "undefined" && localStorage.getItem("pcto.who")) || "");
  // Surface load/save failures instead of swallowing them: optimistic UI is great
  // until a request silently drops and the user thinks it saved. Neon stays the
  // source of truth; this only flags that a fetch didn't land.
  const onLoadFail = (what) => (e) => { console.error(`onboarding: failed to load ${what}`, e); setError("Couldn't load the latest onboarding data — showing what we have."); };
  const onSaveFail = (what) => (e) => { console.error(`onboarding: failed to save ${what}`, e); setError("A change may not have saved — check your connection and retry."); };
  useEffect(() => {
    // reads are auth-gated in prod (no edge gate in front) — carry the token
    const headers = auth?.token ? { Authorization: `Bearer ${auth.token}` } : {};
    fetch(ONB_BASE, { headers }).then((r) => r.json()).then(setLiveOnb).catch(onLoadFail("steps"));
    fetch(`${ONB_BASE}/notes`, { headers }).then((r) => r.json()).then(setNotes).catch(onLoadFail("notes"));
    fetch(`${ONB_BASE}/blocks`, { headers }).then((r) => r.json()).then(setBlocks).catch(onLoadFail("blocks"));
    fetch(`${ONB_BASE}/live`, { headers }).then((r) => r.json()).then(setLive).catch(onLoadFail("live"));
  }, [auth?.token]);

  // Attribution = the signed-in person's first name (from the Google login) in
  // prod; the local-dev name field is only a fallback when not signed in.
  const editor = (auth?.email && firstNameFromEmail(auth.email)) || who || null;

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
    } catch (e) { onSaveFail("step")(e); /* keep optimistic update */ }
  }

  // Append a timestamped note for a practice (stored in Neon, best-effort synced
  // to HubSpot server-side). Optimistic so it appears immediately.
  async function addNote(deal, bodyText) {
    const body = (bodyText || "").trim();
    if (!deal?.ods || !body) return;
    const tmpId = `tmp-${Date.now()}`;
    const optimistic = { id: tmpId, body, author: editor || "(you)", created_at: new Date().toISOString(), hs_synced: false, pending: true };
    setNotes((prev) => ({ ...prev, [deal.ods]: [optimistic, ...(prev[deal.ods] || [])] }));
    try {
      const r = await fetch(`${ONB_BASE}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}) },
        body: JSON.stringify({ ods: deal.ods, deal_id: String(deal.deal_id || ""), body, author: editor }),
      });
      const saved = await r.json();
      if (saved && saved.id) {
        setNotes((prev) => ({ ...prev, [deal.ods]: [saved, ...(prev[deal.ods] || []).filter((n) => n.id !== tmpId)] }));
      }
    } catch (e) { onSaveFail("note")(e); /* keep optimistic note */ }
  }

  // Edit a note's body in place (optimistic). Propagates to its HubSpot note server-side.
  async function editNote(deal, id, bodyText) {
    const text = (bodyText || "").trim();
    if (!deal?.ods || !id || !text) return;
    setNotes((prev) => ({ ...prev, [deal.ods]: (prev[deal.ods] || []).map((n) => (n.id === id ? { ...n, body: text, updated_at: new Date().toISOString(), pending: true } : n)) }));
    try {
      const r = await fetch(`${ONB_BASE}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}) },
        body: JSON.stringify({ id, body: text, author: editor }),
      });
      const saved = await r.json();
      if (saved && saved.id) setNotes((prev) => ({ ...prev, [deal.ods]: (prev[deal.ods] || []).map((n) => (n.id === id ? saved : n)) }));
    } catch (e) { onSaveFail("note-edit")(e); /* keep optimistic */ }
  }

  // Delete a note (optimistic removal). Archives its HubSpot note server-side.
  async function deleteNote(deal, id) {
    if (!deal?.ods || !id) return;
    const prevList = notes[deal.ods] || [];
    setNotes((prev) => ({ ...prev, [deal.ods]: (prev[deal.ods] || []).filter((n) => n.id !== id) }));
    try {
      await fetch(`${ONB_BASE}/notes`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}) },
        body: JSON.stringify({ id }),
      });
    } catch (e) { onSaveFail("note-delete")(e); setNotes((prev) => ({ ...prev, [deal.ods]: prevList })); /* restore on failure */ }
  }

  // Set or clear a block on a step (orthogonal to its todo/pending/done progress).
  // opts: { action: "block"|"unblock", waiting_on, reason }
  async function setStepBlock(deal, step, { action, waiting_on = null, reason = null }) {
    if (!deal?.ods || !step?.key) return;
    setBlocks((prev) => {
      const cur = { ...(prev[deal.ods] || {}) };
      if (action === "unblock") delete cur[step.key];
      else cur[step.key] = { waiting_on: waiting_on || "us", reason, blocked_by: editor || "(you)", blocked_at: new Date().toISOString() };
      return { ...prev, [deal.ods]: cur };
    });
    try {
      await fetch(`${ONB_BASE}/block`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}) },
        body: JSON.stringify({ ods: deal.ods, deal_id: String(deal.deal_id || ""), step_key: step.key, action, waiting_on, reason, by: editor }),
      });
    } catch (e) { onSaveFail("block")(e); /* keep optimistic */ }
  }

  // Mark a practice live: record a Hub flag + (server-side, gated) move the HubSpot deal stage.
  async function markLive(deal) {
    if (!deal?.ods) return;
    setLive((prev) => ({ ...prev, [deal.ods]: { marked_by: editor || "(you)", marked_at: new Date().toISOString(), hs_synced: false } }));
    try {
      const r = await fetch(`${ONB_BASE}/live`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}) },
        body: JSON.stringify({ ods: deal.ods, deal_id: String(deal.deal_id || ""), by: editor }),
      });
      const saved = await r.json();
      if (saved?.ok) setLive((prev) => ({ ...prev, [deal.ods]: { marked_by: editor || "(you)", marked_at: saved.marked_at, hs_synced: saved.hs_synced } }));
    } catch (e) { onSaveFail("mark-live")(e); /* keep optimistic */ }
  }

  return { liveOnb, setLiveOnb, notes, addNote, editNote, deleteNote, blocks, setStepBlock, live, markLive, who, setWho, editor, toggleStep, error, setError };
}
