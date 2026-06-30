// Cloudflare Pages Function: production transport for the onboarding API.
// Same shared handlers as local dev (api/onboarding-core.mjs) and the (legacy)
// Netlify function — only the wrapper differs. Runs at /api/onboarding* on the
// Cloudflare Pages project, same origin as the SPA (no CORS).
//
// Secrets/vars come from `context.env` (set in the Pages project → Settings →
// Environment variables, or via `wrangler pages secret put`):
//   NEON_DATABASE_URL   (required) — Neon Postgres connection string
//   HUBSPOT_API_TOKEN   (optional) — only used when the sync flags below are set
//   HUBSPOT_NOTES_SYNC  (optional) — truthy → push notes to the HubSpot deal
//   HUBSPOT_DEAL_WRITE  (optional) — truthy → mark-live moves the HubSpot deal stage
//
// AUTH: Cloudflare Access gates this whole hostname (site + /api/*) to
// @suvera.co.uk, so there is no app-level sign-in. Every request that reaches
// this function has already passed Access; we read the user's email from the
// signed Access JWT it stamps on the request, purely for attribution.
import { neon } from "@neondatabase/serverless";
import {
  makeNotesHub, makeDealLiveSetter, firstNameFromEmail,
  getCurrent, getHistory, getNotes, postStep, postNote, editNote, deleteNote,
  getBlocks, setBlock, getLive, markLive,
} from "../../api/onboarding-core.mjs";

const ALLOWED_DOMAIN = "suvera.co.uk";
const J = (r) => new Response(JSON.stringify(r.body), { status: r.status, headers: { "content-type": "application/json" } });
const err = (obj, status) => new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

// Read the authenticated user from Cloudflare Access. Access stamps every request
// it lets through with the user's email (header) and a signed JWT; we read the
// email for attribution (who made the change). FAILS CLOSED: a write with no
// Access identity (which should be impossible behind Access) is rejected. Reads
// stay open. No Google token / bearer header is involved.
function b64urlJson(seg) {
  let s = (seg || "").replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  return JSON.parse(atob(s));
}
function accessIdentity(req) {
  // Header Access sets directly on every authenticated request…
  let email = (req.headers.get("cf-access-authenticated-user-email") || "").toLowerCase();
  // …or the email claim inside the signed Access JWT it stamps on the request.
  if (!email) {
    const jwt = req.headers.get("cf-access-jwt-assertion") || "";
    if (jwt) { try { email = (b64urlJson(jwt.split(".")[1]).email || "").toLowerCase(); } catch { /* ignore */ } }
  }
  return email.endsWith("@" + ALLOWED_DOMAIN) ? { email } : null;
}

export async function onRequest(context) {
  const { request: req, env } = context;
  // Pages Functions expose env per-request, so build the clients here (not at module scope).
  const sql = neon(env.NEON_DATABASE_URL);
  const notesHub = makeNotesHub({ token: env.HUBSPOT_API_TOKEN || "", enabled: !!env.HUBSPOT_NOTES_SYNC });
  const setDealLive = makeDealLiveSetter({ token: env.HUBSPOT_API_TOKEN || "", enabled: !!env.HUBSPOT_DEAL_WRITE });

  const url = new URL(req.url);
  const sub = url.pathname.replace(/^.*\/onboarding/, ""); // "" | "/step" | "/history" | "/notes" | ...
  // anything under /api/ that isn't /api/onboarding* is not ours
  if (!url.pathname.includes("/onboarding")) return err({ error: "not found" }, 404);

  const gate = () => accessIdentity(req);
  const unauth = () => err({ error: "unauthorized — Cloudflare Access identity missing" }, 401);

  try {
    if (req.method === "GET" && sub === "/history") return J(await getHistory(sql, url.searchParams.get("ods")));
    if (req.method === "GET" && sub === "/notes") return J(await getNotes(sql));
    if (req.method === "GET" && sub === "/blocks") return J(await getBlocks(sql));
    if (req.method === "GET" && sub === "/live") return J(await getLive(sql));
    if (req.method === "GET") return J(await getCurrent(sql));

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
