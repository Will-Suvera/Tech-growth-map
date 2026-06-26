// Netlify Function: production transport for the onboarding API — a thin wrapper
// around the SAME shared handlers as local dev (api/onboarding-core.mjs).
// Reads NEON_DATABASE_URL + GOOGLE_CLIENT_ID from the Netlify env.
// Writes (POST) require a valid Google ID token for a @suvera.co.uk account;
// reads (GET) are open (the frontend gates the whole UI behind sign-in anyway).
import { neon } from "@neondatabase/serverless";
import {
  makeNoteSyncer, firstNameFromEmail,
  getCurrent, getHistory, getNotes, postStep, postNote,
} from "../../api/onboarding-core.mjs";

const sql = neon(process.env.NEON_DATABASE_URL);
const CLIENT_ID = process.env.GOOGLE_CLIENT_ID || "";
const ALLOWED_DOMAIN = "suvera.co.uk";

// Best-effort HubSpot note sync — OFF unless HUBSPOT_NOTES_SYNC is set in the
// Netlify env (HUBSPOT_API_TOKEN + crm.objects.notes write scope also required).
const syncNote = makeNoteSyncer({ token: process.env.HUBSPOT_API_TOKEN || "", enabled: !!process.env.HUBSPOT_NOTES_SYNC });

const J = (r) => new Response(JSON.stringify(r.body), { status: r.status, headers: { "content-type": "application/json" } });
const err = (obj, status) => new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

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
  const sub = url.pathname.replace(/^.*\/onboarding/, ""); // "" | "/step" | "/history" | "/notes"
  try {
    if (req.method === "GET" && sub === "/history") return J(await getHistory(sql, url.searchParams.get("ods")));
    if (req.method === "GET" && sub === "/notes") return J(await getNotes(sql));
    if (req.method === "GET") return J(await getCurrent(sql));

    if (req.method === "POST" && sub === "/step") {
      const auth = await verifyGoogle(req);
      if (!auth) return err({ error: "unauthorized — sign in with a @suvera.co.uk Google account" }, 401);
      const body = await req.json();
      // attribution comes from the verified token, not the client
      return J(await postStep(sql, { ...body, changed_by: auth.email || body.changed_by || null }));
    }

    if (req.method === "POST" && sub === "/notes") {
      const auth = await verifyGoogle(req);
      if (!auth) return err({ error: "unauthorized — sign in with a @suvera.co.uk Google account" }, 401);
      const body = await req.json();
      const author = firstNameFromEmail(auth.email) || body.author || null;
      return J(await postNote(sql, syncNote, { ods: body.ods, deal_id: body.deal_id ?? null, body: body.body, author }));
    }

    return err({ error: "not found" }, 404);
  } catch (e) {
    return err({ error: String(e) }, 500);
  }
};
