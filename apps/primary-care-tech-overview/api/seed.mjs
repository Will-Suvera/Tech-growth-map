// One-time seed: load each practice's current onboarding-step state from
// funnel_board.json (which derives it from the read-only Google Sheet) into the
// Neon event log. Idempotent — skips if events already exist. After this, the
// app is the source of truth; the sheet is never written.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { neon } from "@neondatabase/serverless";

const __dirname = dirname(fileURLToPath(import.meta.url));
function loadEnv(key) {
  if (process.env[key]) return process.env[key];
  try {
    const env = readFileSync(resolve(__dirname, "..", "..", "..", ".env"), "utf8");
    for (const line of env.split("\n")) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
      if (m && m[1] === key) return m[2].trim().replace(/^["']|["']$/g, "");
    }
  } catch { /* ignore */ }
  return null;
}
const sql = neon(loadEnv("NEON_DATABASE_URL"));

const board = JSON.parse(
  readFileSync(resolve(__dirname, "..", "public", "data", "funnel_board.json"), "utf8")
);

const existing = await sql`select count(*)::int as n from onboarding_step_events`;
if (existing[0].n > 0) {
  console.log(`onboarding_step_events already has ${existing[0].n} rows — skipping seed (idempotent).`);
  process.exit(0);
}

let n = 0, practices = 0;
for (const d of board.deals) {
  if (!d.ods || !Array.isArray(d.onboarding) || !d.onboarding.length) continue;
  practices++;
  for (const s of d.onboarding) {
    await sql`insert into onboarding_step_events
      (ods, deal_id, step_key, from_state, to_state, changed_by, note)
      values (${d.ods}, ${String(d.deal_id || "")}, ${s.key}, null, ${s.state}, 'sheet-seed', 'initial seed from onboarding sheet')`;
    n++;
  }
}
console.log(`Seeded ${n} step events across ${practices} practices.`);
process.exit(0);
