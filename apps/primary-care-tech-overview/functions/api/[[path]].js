// Cloudflare Pages Function: production transport for the onboarding API.
// Same shared handlers as local dev (api/onboarding-core.mjs) and the (legacy)
// Netlify function — only the wrapper differs. Runs at /api/onboarding* on the
// Cloudflare Pages project, same origin as the SPA (no CORS).
//
// Secrets/vars come from `context.env` (set in the Pages project → Settings →
// Environment variables, or via `wrangler pages secret put`):
//   NEON_DATABASE_URL   (required) — Neon Postgres connection string
//   GOOGLE_CLIENT_ID    (required) — OAuth client id; verifies the @suvera.co.uk Google token on every read + write
//   HUBSPOT_API_TOKEN   (optional) — only used when the sync flags below are set
//   HUBSPOT_NOTES_SYNC  (optional) — truthy → push notes to the HubSpot deal
//   HUBSPOT_DEAL_WRITE  (optional) — truthy → mark-live moves the HubSpot deal stage
//
// This is the ONLY gate (no Cloudflare Access in front): every read AND write
// requires a valid @suvera.co.uk Google token, so the deal/CS data stays private.
import { neon } from "@neondatabase/serverless";
import {
  makeNotesHub, makeDealLiveSetter, firstNameFromEmail,
  getCurrent, getHistory, getNotes, postStep, postNote, editNote, deleteNote,
  getBlocks, setBlock, getLive, markLive,
} from "../../api/onboarding-core.mjs";
// The dashboard data (generated fresh in CI) is bundled into this Function and
// served only to authenticated users — NOT a public static asset, so the internal
// data stays private without an edge gate. CI overwrites these before the deploy;
// the committed copies are empty placeholders.
import boardData from "../../server-data/funnel_board.json";
import visitsData from "../../server-data/practice_visits.json";

const ALLOWED_DOMAIN = "suvera.co.uk";
const J = (r) => new Response(JSON.stringify(r.body), { status: r.status, headers: { "content-type": "application/json" } });
const err = (obj, status) => new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

// Verify a Google ID token via Google's tokeninfo endpoint (no extra deps).
// Returns { email } when valid; null otherwise. FAILS CLOSED: without a client id
// we can't verify anyone, so every write is rejected rather than accepted
// unauthenticated (these endpoints write Neon + move HubSpot deals). Reads stay open.
async function verifyGoogle(req, clientId) {
  if (!clientId) return null;
  const auth = req.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) return null;
  try {
    const r = await fetch(`https://oauth2.googleapis.com/tokeninfo?id_token=${encodeURIComponent(token)}`);
    if (!r.ok) return null;
    const p = await r.json();
    if (p.aud !== clientId) return null;
    const email = (p.email || "").toLowerCase();
    const domainOk = p.hd === ALLOWED_DOMAIN || email.endsWith("@" + ALLOWED_DOMAIN);
    if (!domainOk || p.email_verified === "false") return null;
    return { email };
  } catch {
    return null;
  }
}

export async function onRequest(context) {
  const { request: req, env } = context;
  // Pages Functions expose env per-request, so build the clients here (not at module scope).
  const sql = neon(env.NEON_DATABASE_URL);
  const CLIENT_ID = env.GOOGLE_CLIENT_ID || "";
  const notesHub = makeNotesHub({ token: env.HUBSPOT_API_TOKEN || "", enabled: !!env.HUBSPOT_NOTES_SYNC });
  const setDealLive = makeDealLiveSetter({ token: env.HUBSPOT_API_TOKEN || "", enabled: !!env.HUBSPOT_DEAL_WRITE });

  const url = new URL(req.url);
  const sub = url.pathname.replace(/^.*\/onboarding/, ""); // "" | "/step" | "/history" | "/notes" | ...
  // anything under /api/ that isn't /api/onboarding* is not ours
  if (!url.pathname.includes("/onboarding")) return err({ error: "not found" }, 404);

  const gate = async () => {
    const a = await verifyGoogle(req, CLIENT_ID);
    return a?.email ? a : null;
  };
  const unauth = () => err({ error: "unauthorized — sign in with a @suvera.co.uk Google account" }, 401);

  try {
    // Every GET is auth-gated (the data is private, served only to a signed-in
    // @suvera.co.uk user). /board + /visits serve the bundled dashboard data.
    if (req.method === "GET") {
      const auth = await gate(); if (!auth) return unauth();
      if (sub === "/board") return J({ status: 200, body: boardData });
      if (sub === "/visits") return J({ status: 200, body: visitsData });
      if (sub === "/history") return J(await getHistory(sql, url.searchParams.get("ods")));
      if (sub === "/notes") return J(await getNotes(sql));
      if (sub === "/blocks") return J(await getBlocks(sql));
      if (sub === "/live") return J(await getLive(sql));
      return J(await getCurrent(sql));
    }

    if (req.method === "POST" && sub === "/step") {
      const auth = await gate(); if (!auth) return unauth();
      const body = await req.json();
      return J(await postStep(sql, { ...body, changed_by: auth.email || body.changed_by || null }));
    }
    if (req.method === "POST" && sub === "/notes") {
      const auth = await gate(); if (!auth) return unauth();
      const body = await req.json();
      const author = firstNameFromEmail(auth.email) || body.author || null;
      return J(await postNote(sql, notesHub, { ods: body.ods, deal_id: body.deal_id ?? null, body: body.body, author }));
    }
    if (req.method === "PATCH" && sub === "/notes") {
      const auth = await gate(); if (!auth) return unauth();
      const body = await req.json();
      const author = firstNameFromEmail(auth.email) || body.author || null;
      return J(await editNote(sql, notesHub, { id: body.id, body: body.body, author }));
    }
    if (req.method === "DELETE" && sub === "/notes") {
      const auth = await gate(); if (!auth) return unauth();
      const body = await req.json();
      return J(await deleteNote(sql, notesHub, { id: body.id }));
    }
    if (req.method === "POST" && sub === "/block") {
      const auth = await gate(); if (!auth) return unauth();
      const body = await req.json();
      return J(await setBlock(sql, { ...body, by: firstNameFromEmail(auth.email) || body.by || null }));
    }
    if (req.method === "POST" && sub === "/live") {
      const auth = await gate(); if (!auth) return unauth();
      const body = await req.json();
      return J(await markLive(sql, setDealLive, { ods: body.ods, deal_id: body.deal_id ?? null, by: firstNameFromEmail(auth.email) || body.by || null }));
    }
    return err({ error: "not found" }, 404);
  } catch (e) {
    return err({ error: String(e) }, 500);
  }
}
