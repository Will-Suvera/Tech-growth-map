#!/usr/bin/env python3
"""Fetch the Notion "Practice Visits" DB into notion_practice_visits.json (the sidecar
that ingest_practice_visits.py normalises into practice_visits.json).

Scriptable / CI-friendly: uses the Notion REST API with NOTION_API_TOKEN — an
*internal integration* token shared with the DB — so it runs daily in GitHub
Actions. (The earlier path pulled Notion via the claude.ai MCP connector, which is
interactively authenticated and CANNOT run headless.)

Setup (one-time):
  1. Create an internal integration at https://www.notion.so/my-integrations
  2. Share the "Practice Visits" database (and its parent page) with that integration.
  3. Put the secret token in `.env` as NOTION_API_TOKEN=... (and add the same as a
     GitHub Actions repo secret named NOTION_API_TOKEN).

The query is comprehensive (full DB, paginated) — every completed + confirmed +
proposed visit with its date — so it REPLACES the sidecar each run.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_ID = "a80fc303d664476f8a45b66f4d27953b"   # Practice Visits database (2026)
SIDECAR = ROOT / "notion_practice_visits.json"
NOTION_VERSION = "2022-06-28"


def get_token() -> str:
    t = os.environ.get("NOTION_API_TOKEN", "").strip()
    if t:
        return t
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("NOTION_API_TOKEN"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


TOKEN = get_token()


def api(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        "https://api.notion.com/v1" + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def rich(prop: dict | None) -> str | None:
    """Concatenate the plain_text of a title or rich_text property."""
    if not prop:
        return None
    arr = prop.get("rich_text") or prop.get("title") or []
    txt = "".join(x.get("plain_text", "") for x in arr).strip()
    return txt or None


def main() -> None:
    if not TOKEN:
        print("ERROR: NOTION_API_TOKEN not set. Create an internal integration, share the "
              "'Practice Visits' DB with it, and set NOTION_API_TOKEN (see module docstring).",
              file=sys.stderr)
        sys.exit(1)

    rows: list[dict] = []
    cursor = None
    pages = 0
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = api(f"/databases/{DB_ID}/query", body)
        for pg in resp.get("results", []):
            pages += 1
            props = pg.get("properties", {})
            title = rich(props.get("Practice"))
            if not title:
                continue
            base = {
                "status": (props.get("Status", {}).get("select") or {}).get("name"),
                "date": ((props.get("Date", {}).get("date") or {}).get("start") or "")[:10] or None,
                "times": rich(props.get("Times")),
                "site_address": rich(props.get("Site Address")),
                "problems": rich(props.get("Problems")),
                "outcome": rich(props.get("Outcome")),
                "attendees": [p.get("name") for p in (props.get("Attendees", {}).get("people") or [])
                              if p.get("name")],
            }
            # A single Notion row sometimes lists several practices ("A, B & C") for a
            # bulk visit — split into one record each, sharing the visit's fields.
            parts = [p.strip() for p in re.split(r",|\s&\s", title) if p.strip()]
            for name in (parts or [title]):
                rows.append({"practice": name, **base})
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    # Keep only rows carrying signal: a date OR a non-blank status. (Drops the
    # date-less, status-less "planning list" bulk pages that add no visit info.)
    rows = [r for r in rows if (r.get("date") or (r.get("status") or "").strip())]

    SIDECAR.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"Wrote {SIDECAR.name}: {len(rows)} visit rows from {pages} Notion pages")
    print("  statuses:", dict(Counter((r.get("status") or "(blank)") for r in rows)))


if __name__ == "__main__":
    main()
