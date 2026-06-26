// Shared onboarding logic for the Neon-backed onboarding API — the single source
// of truth behind BOTH transports:
//   • local dev   → api/server.mjs (node http)
//   • production  → netlify/functions/onboarding.mjs (Web Request/Response, SSO-gated)
//
// Each handler is transport-agnostic: it takes the `sql` client (+ already-parsed
// inputs) and returns `{ status, body }`. The wrappers own transport, env loading
// and auth — so the two can never drift (e.g. adding an endpoint is a one-file change).

const VALID_STATES = ["todo", "pending", "done"];
const result = (body, status = 200) => ({ status, body });

// First name from a verified Google email (e.g. "will@suvera.co.uk" -> "Will").
export function firstNameFromEmail(email) {
  if (!email) return null;
  const fn = email.split("@")[0].split(/[._-]+/)[0] || "";
  return fn ? fn.charAt(0).toUpperCase() + fn.slice(1) : null;
}

// Build a best-effort HubSpot note syncer. Returns false (never throws) unless
// `enabled` + a `token` + a `deal_id` are all present. note→deal associationTypeId = 214.
export function makeNoteSyncer({ token, enabled }) {
  return async function syncNoteToHubspot({ deal_id, body, author }) {
    if (!enabled || !token || !deal_id) return false;
    try {
      const r = await fetch("https://api.hubapi.com/crm/v3/objects/notes", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          properties: { hs_note_body: `${body}${author ? `\n\n— ${author} (Onboarding Hub)` : ""}`, hs_timestamp: Date.now() },
          associations: [{ to: { id: String(deal_id) }, types: [{ associationCategory: "HUBSPOT_DEFINED", associationTypeId: 214 }] }],
        }),
      });
      return r.ok;
    } catch {
      return false;
    }
  };
}

// GET /api/onboarding → current state per practice: { ods: { step_key: {state, changed_by, changed_at} } }
export async function getCurrent(sql) {
  const rows = await sql`select ods, step_key, state, changed_by, changed_at from onboarding_current`;
  const out = {};
  for (const r of rows) (out[r.ods] ||= {})[r.step_key] = { state: r.state, changed_by: r.changed_by, changed_at: r.changed_at };
  return result(out);
}

// GET /api/onboarding/history?ods= → full event log for one practice (time-in-step / audit)
export async function getHistory(sql, ods) {
  if (!ods) return result({ error: "ods required" }, 400);
  const rows = await sql`select step_key, from_state, to_state, changed_by, changed_at
    from onboarding_step_events where ods=${ods} order by changed_at asc`;
  return result(rows);
}

// GET /api/onboarding/notes → { ods: [ {id, body, author, created_at, hs_synced}, … ] } newest-first
export async function getNotes(sql) {
  const rows = await sql`select id, ods, deal_id, author, body, hs_synced, created_at
    from onboarding_notes order by created_at desc`;
  const out = {};
  for (const r of rows) (out[r.ods] ||= []).push(r);
  return result(out);
}

// POST /api/onboarding/step → append a timestamped state-change event
export async function postStep(sql, { ods, deal_id = null, step_key, to_state, changed_by = null, note = null }) {
  if (!ods || !step_key || !VALID_STATES.includes(to_state)) {
    return result({ error: "ods, step_key and a valid to_state (todo|pending|done) are required" }, 400);
  }
  const prev = await sql`select state from onboarding_current where ods=${ods} and step_key=${step_key}`;
  const from_state = prev[0]?.state ?? null;
  const ins = await sql`insert into onboarding_step_events
    (ods, deal_id, step_key, from_state, to_state, changed_by, note)
    values (${ods}, ${deal_id}, ${step_key}, ${from_state}, ${to_state}, ${changed_by}, ${note})
    returning changed_at`;
  return result({ ok: true, ods, step_key, state: to_state, from_state, changed_by, changed_at: ins[0].changed_at });
}

// POST /api/onboarding/notes → save a note to Neon (best-effort HubSpot sync via syncNote)
export async function postNote(sql, syncNote, { ods, deal_id = null, body, author = null }) {
  const text = String(body || "").trim();
  if (!ods || !text) return result({ error: "ods and body are required" }, 400);
  const hs_synced = await syncNote({ deal_id, body: text, author });
  const ins = await sql`insert into onboarding_notes (ods, deal_id, author, body, hs_synced)
    values (${ods}, ${deal_id}, ${author}, ${text}, ${hs_synced})
    returning id, ods, deal_id, author, body, hs_synced, created_at`;
  return result(ins[0]);
}
