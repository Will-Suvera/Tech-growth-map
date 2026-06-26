// Local dev API for the Primary Care Tech Overview dashboard — a thin node-http
// wrapper around the shared handlers in onboarding-core.mjs (the prod Netlify
// Function wraps the SAME core). Onboarding step toggles + notes → Neon Postgres.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { neon } from "@neondatabase/serverless";
import { makeNoteSyncer, getCurrent, getHistory, getNotes, postStep, postNote } from "./onboarding-core.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));

function loadEnv(key) {
  if (process.env[key]) return process.env[key];
  // repo-root .env (this file is apps/primary-care-tech-overview/api/)
  try {
    const env = readFileSync(resolve(__dirname, "..", "..", "..", ".env"), "utf8");
    for (const line of env.split("\n")) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
      if (m && m[1] === key) return m[2].trim().replace(/^["']|["']$/g, "");
    }
  } catch { /* ignore */ }
  return null;
}

const DATABASE_URL = loadEnv("NEON_DATABASE_URL");
if (!DATABASE_URL) {
  console.error("ERROR: NEON_DATABASE_URL not set (in env or repo-root .env)");
  process.exit(1);
}
const sql = neon(DATABASE_URL);
const PORT = process.env.ONBOARDING_API_PORT || 5175;

// Best-effort HubSpot note sync. OFF unless HUBSPOT_NOTES_SYNC is set, so the
// first real write to HubSpot is a deliberate choice (token + crm.objects.notes
// write scope also required). Notes are always saved to Neon regardless.
const syncNote = makeNoteSyncer({ token: loadEnv("HUBSPOT_API_TOKEN"), enabled: !!loadEnv("HUBSPOT_NOTES_SYNC") });

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const json = (res, code, body) => {
  res.writeHead(code, { "Content-Type": "application/json", ...CORS });
  res.end(JSON.stringify(body));
};
const readBody = (req) =>
  new Promise((res, rej) => {
    let b = "";
    req.on("data", (c) => (b += c));
    req.on("end", () => { try { res(b ? JSON.parse(b) : {}); } catch (e) { rej(e); } });
    req.on("error", rej);
  });

const server = createServer(async (req, res) => {
  if (req.method === "OPTIONS") { res.writeHead(204, CORS); return res.end(); }
  try {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const p = url.pathname;
    const send = (r) => json(res, r.status, r.body);

    if (req.method === "GET" && p === "/api/onboarding") return send(await getCurrent(sql));
    if (req.method === "GET" && p === "/api/onboarding/history") return send(await getHistory(sql, url.searchParams.get("ods")));
    if (req.method === "GET" && p === "/api/onboarding/notes") return send(await getNotes(sql));
    if (req.method === "POST" && p === "/api/onboarding/step") return send(await postStep(sql, await readBody(req)));
    if (req.method === "POST" && p === "/api/onboarding/notes") return send(await postNote(sql, syncNote, await readBody(req)));

    return json(res, 404, { error: "not found" });
  } catch (e) {
    console.error(e);
    return json(res, 500, { error: String(e) });
  }
});

server.listen(PORT, () => console.log(`onboarding API → http://localhost:${PORT} (Neon)`));
