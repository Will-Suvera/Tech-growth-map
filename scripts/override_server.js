// Tiny dev-only HTTP endpoint for the Planner Growth Dashboard's
// in-drilldown override editor. Uses node:http (no Express dependency)
// so it adds zero npm install cost.
//
// Behaviour:
//   GET  /api/overrides         -> current overrides JSON
//   POST /api/overrides         -> body {ods, source?, role?, confidence?, notes?}
//                                  merged into manual_overrides.json (updated_at stamped)
//   DELETE /api/overrides/:ods  -> remove an entry
//
// Writes to: attribution-dashboard/public/data/manual_overrides.json
// (git-tracked; Vite serves it as a static file under /data/manual_overrides.json)
//
// Listens on port 5175 by default (one above Vite's 5174). The frontend posts
// to http://localhost:5175 in dev. Production build doesn't use this server —
// overrides are applied at refresh-time by scripts/refresh_attribution.py.
//
// Run via: node scripts/override_server.js  (or wired into npm run dev via concurrently)

import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OVERRIDES_PATH = resolve(__dirname, "..", "attribution-dashboard", "public", "data", "manual_overrides.json");
const PORT = Number(process.env.OVERRIDE_PORT || 5175);

async function readOverrides() {
  try {
    return JSON.parse(await readFile(OVERRIDES_PATH, "utf8"));
  } catch (err) {
    if (err.code === "ENOENT") return {};
    throw err;
  }
}

async function writeOverrides(data) {
  await mkdir(dirname(OVERRIDES_PATH), { recursive: true });
  await writeFile(OVERRIDES_PATH, JSON.stringify(data, null, 2) + "\n");
}

function cors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
}

function send(res, status, body) {
  cors(res);
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

const server = createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    cors(res);
    res.statusCode = 204;
    return res.end();
  }
  try {
    if (req.url === "/api/overrides" && req.method === "GET") {
      return send(res, 200, await readOverrides());
    }
    if (req.url === "/api/overrides" && req.method === "POST") {
      let body = "";
      for await (const chunk of req) body += chunk;
      const payload = JSON.parse(body || "{}");
      const ods = (payload.ods || "").toUpperCase();
      if (!ods) return send(res, 400, { error: "ods required" });
      const overrides = await readOverrides();
      const existing = overrides[ods] || {};
      const merged = { ...existing };
      for (const k of ["source", "role", "confidence", "notes"]) {
        if (payload[k] === null) delete merged[k];
        else if (payload[k] !== undefined) merged[k] = payload[k];
      }
      merged.updated_at = new Date().toISOString();
      overrides[ods] = merged;
      await writeOverrides(overrides);
      return send(res, 200, { ods, override: merged });
    }
    const del = req.url?.match(/^\/api\/overrides\/([A-Z0-9]+)$/i);
    if (del && req.method === "DELETE") {
      const ods = del[1].toUpperCase();
      const overrides = await readOverrides();
      delete overrides[ods];
      await writeOverrides(overrides);
      return send(res, 200, { ods, deleted: true });
    }
    send(res, 404, { error: "not found" });
  } catch (err) {
    send(res, 500, { error: String(err) });
  }
});

server.listen(PORT, () => {
  console.log(`override_server.js listening on http://localhost:${PORT}`);
  console.log(`Writing to ${OVERRIDES_PATH}`);
});
