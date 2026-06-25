// Netlify Function: onboarding step toggles → Neon (production version of api/server.mjs).
// Reads NEON_DATABASE_URL + GOOGLE_CLIENT_ID from Netlify env.
// Writes (POST) require a valid Google ID token for a @suvera.co.uk account.
// Reads (GET) are open (the frontend gates the whole UI behind sign-in anyway).
import { neon } from "@neondatabase/serverless";

const sql = neon(process.env.NEON_DATABASE_URL);
const CLIENT_ID = process.env.GOOGLE_CLIENT_ID || "";
const ALLOWED_DOMAIN = "suvera.co.uk";

// Best-effort HubSpot note sync. OFF unless HUBSPOT_NOTES_SYNC is set in the
// Netlify env (HUBSPOT_API_TOKEN + crm.objects.notes write scope also required).
// The note is always saved to Neon regardless of HubSpot.
const HS_TOKEN = process.env.HUBSPOT_API_TOKEN || "";
const HS_NOTES_SYNC = !!process.env.HUBSPOT_NOTES_SYNC;
async function syncNoteToHubspot({ deal_id, body, author }) {
  if (!HS_NOTES_SYNC || !HS_TOKEN || !deal_id) return false;
  try {
    const r = await fetch("https://api.hubapi.com/crm/v3/objects/notes", {
      method: "POST",
      headers: { Authorization: `Bearer ${HS_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        properties: { hs_note_body: `${body}${author ? `\n\n— ${author} (Onboarding Hub)` : ""}`, hs_timestamp: Date.now() },
        associations: [{ to: { id: String(deal_id) }, types: [{ associationCategory: "HUBSPOT_DEFINED", associationTypeId: 214 }] }],
      }),
    });
    return r.ok;
  } catch { return false; }
}
const J = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

// Verify a Google ID token via Google's tokeninfo endpoint (no extra deps).
// Returns { email } when valid; null when invalid. If GOOGLE_CLIENT_ID is unset
// (not yet configured), returns { unverified: true } so the API still functions.
async function verifyGoogle(req) {
  if (!CLIENT_ID) return { unverified: true, email: null };
  const auth = req.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) return null;
  try {
    const r = await fetch(`https://oauth2.googleapis.com/tokeninfo?id_token=${encodeURIComponent(token)}`);
    if (!r.ok) return null;
    const p = await r.json();
    if (p.aud !== CLIENT_ID) return null;
    const email = (p.email || "").toLowerCase();
    const domainOk = p.hd === ALLOWED_DOMAIN || email.endsWith("@" + ALLOWED_DOMAIN);
    if (!domainOk || p.email_verified === "false") return null;
    return { email };
  } catch {
    return null;
  }
}

export default async (req) => {
  const url = new URL(req.url);
  const sub = url.pathname.replace(/^.*\/onboarding/, ""); // "" | "/step" | "/history"
  try {
    if (req.method === "GET" && sub === "/history") {
      const ods = url.searchParams.get("ods");
      if (!ods) return J({ error: "ods required" }, 400);
      const rows = await sql`select step_key, from_state, to_state, changed_by, changed_at
        from onboarding_step_events where ods=${ods} order by changed_at asc`;
      return J(rows);
    }
    if (req.method === "GET" && sub === "/notes") {
      const rows = await sql`select id, ods, deal_id, author, body, hs_synced, created_at
        from onboarding_notes order by created_at desc`;
      const out = {};
      for (const r of rows) (out[r.ods] ||= []).push(r);
      return J(out);
    }
    if (req.method === "GET") {
      const rows = await sql`select ods, step_key, state, changed_by, changed_at from onboarding_current`;
      const out = {};
      for (const r of rows) (out[r.ods] ||= {})[r.step_key] = { state: r.state, changed_by: r.changed_by, changed_at: r.changed_at };
      return J(out);
    }
    if (req.method === "POST" && sub === "/step") {
      const auth = await verifyGoogle(req);
      if (!auth) return J({ error: "unauthorized — sign in with a @suvera.co.uk Google account" }, 401);
      const body = await req.json();
      const { ods, deal_id = null, step_key, to_state, note = null } = body;
      const changed_by = auth.email || body.changed_by || null;
      if (!ods || !step_key || !["todo", "pending", "done"].includes(to_state)) {
        return J({ error: "ods, step_key and a valid to_state (todo|pending|done) are required" }, 400);
      }
      const prev = await sql`select state from onboarding_current where ods=${ods} and step_key=${step_key}`;
      const from_state = prev[0]?.state ?? null;
      const ins = await sql`insert into onboarding_step_events
        (ods, deal_id, step_key, from_state, to_state, changed_by, note)
        values (${ods}, ${deal_id}, ${step_key}, ${from_state}, ${to_state}, ${changed_by}, ${note})
        returning changed_at`;
      return J({ ok: true, ods, step_key, state: to_state, from_state, changed_by, changed_at: ins[0].changed_at });
    }
    if (req.method === "POST" && sub === "/notes") {
      const auth = await verifyGoogle(req);
      if (!auth) return J({ error: "unauthorized — sign in with a @suvera.co.uk Google account" }, 401);
      const body = await req.json();
      const { ods, deal_id = null } = body;
      const text = String(body.body || "").trim();
      // first name from the verified Google email (e.g. will@… -> "Will"); spoof-proof
      const fn = auth.email ? (auth.email.split("@")[0].split(/[._-]+/)[0] || "") : "";
      const author = fn ? fn.charAt(0).toUpperCase() + fn.slice(1) : (body.author || null);
      if (!ods || !text) return J({ error: "ods and body are required" }, 400);
      const hs_synced = await syncNoteToHubspot({ deal_id, body: text, author });
      const ins = await sql`insert into onboarding_notes (ods, deal_id, author, body, hs_synced)
        values (${ods}, ${deal_id}, ${author}, ${text}, ${hs_synced})
        returning id, ods, deal_id, author, body, hs_synced, created_at`;
      return J(ins[0]);
    }
    return J({ error: "not found" }, 404);
  } catch (e) {
    return J({ error: String(e) }, 500);
  }
};
