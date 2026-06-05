// Local dev API for the Primary Care Tech Overview dashboard.
// Onboarding step toggles → Neon Postgres (append-only event log, timestamped).
// Phase 1: runs locally alongside Vite (see package.json "dev").
// Phase 2: this same logic moves to a Netlify Function + Google-domain auth.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { neon } from "@neondatabase/serverless";

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

    // current state per practice: { ods: { step_key: {state, changed_by, changed_at} } }
    if (req.method === "GET" && url.pathname === "/api/onboarding") {
      const rows = await sql`select ods, step_key, state, changed_by, changed_at from onboarding_current`;
      const out = {};
      for (const r of rows) {
        (out[r.ods] ||= {})[r.step_key] = { state: r.state, changed_by: r.changed_by, changed_at: r.changed_at };
      }
      return json(res, 200, out);
    }

    // full event history for one practice (for time-in-step / audit)
    if (req.method === "GET" && url.pathname === "/api/onboarding/history") {
      const ods = url.searchParams.get("ods");
      if (!ods) return json(res, 400, { error: "ods required" });
      const rows = await sql`select step_key, from_state, to_state, changed_by, changed_at
        from onboarding_step_events where ods=${ods} order by changed_at asc`;
      return json(res, 200, rows);
    }

    // toggle a step → append a timestamped event
    if (req.method === "POST" && url.pathname === "/api/onboarding/step") {
      const { ods, deal_id = null, step_key, to_state, changed_by = null, note = null } = await readBody(req);
      if (!ods || !step_key || !["todo", "pending", "done"].includes(to_state)) {
        return json(res, 400, { error: "ods, step_key and a valid to_state (todo|pending|done) are required" });
      }
      const prev = await sql`select state from onboarding_current where ods=${ods} and step_key=${step_key}`;
      const from_state = prev[0]?.state ?? null;
      const ins = await sql`insert into onboarding_step_events
        (ods, deal_id, step_key, from_state, to_state, changed_by, note)
        values (${ods}, ${deal_id}, ${step_key}, ${from_state}, ${to_state}, ${changed_by}, ${note})
        returning changed_at`;
      return json(res, 200, { ok: true, ods, step_key, state: to_state, from_state, changed_by, changed_at: ins[0].changed_at });
    }

    return json(res, 404, { error: "not found" });
  } catch (e) {
    console.error(e);
    return json(res, 500, { error: String(e) });
  }
});

server.listen(PORT, () => console.log(`onboarding API → http://localhost:${PORT} (Neon)`));
