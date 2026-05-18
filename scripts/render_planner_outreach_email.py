#!/usr/bin/env python3
"""Render a personalised Planner outreach email for a target practice.

For each target ODS, generates:
  - A static OpenStreetMap PNG centered on the target, with pins for:
      RED   = the target practice (you)
      GREEN = Live + actively recalling anchors
      BLUE  = In Progress (onboarding) practices nearby
      AMBER = Signed-up practices nearby
  - A single self-contained HTML email file with the Suvera brand palette,
    map embedded as base64, two practice quotes, primary CTA pointing to
    suvera.com/planner, and Dr. Will Gao's signature.

The intro and map caption auto-personalise to the target's PCN and the
counts of nearby Live / In Progress / Signed-up practices. The opener
("Practices in your PCN have taken it on") adapts by tier:
  T1-T3 (PCN match)  -> "Practices in your PCN have taken it on"
  T4 (within 10mi)   -> "Practices on your doorstep have taken it on"
  T5 (same ICB)      -> "Practices in your area have taken it on"

Usage
-----
    python3 scripts/render_planner_outreach_email.py <ODS>
    python3 scripts/render_planner_outreach_email.py --top 5
    python3 scripts/render_planner_outreach_email.py --top 10 --status "Not signed up"

Output
------
HTML files land in public/email/, named:
    outreach_<ODS>_<slug>.html
e.g. outreach_F85007_lawrence-house-surgery.html
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import push_hitlist_to_sheet as phs  # noqa: E402
from icb_mapper import SicblCache  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "public" / "email"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MAP_RADIUS_MI = 5.0
MAX_BLUE = 5
MAX_AMBER = 6

# ----------------------------------------------------------------------------
# Map rendering
# ----------------------------------------------------------------------------

def _make_pin(fill: str, outline: str, size: int = 44):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    W, H = size, int(size * 1.4)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W // 2
    head_r = int(W * 0.42)
    head_top = 0
    head_bot = head_top + head_r * 2
    head_cy = head_top + head_r
    d.ellipse([cx - head_r, head_top, cx + head_r, head_bot], fill=fill, outline=outline, width=2)
    tip_y = H - 2
    tri = [(cx - int(head_r * 0.55), head_bot - 4),
           (cx + int(head_r * 0.55), head_bot - 4),
           (cx, tip_y)]
    d.polygon(tri, fill=fill, outline=outline)
    inner_r = int(head_r * 0.32)
    d.ellipse([cx - inner_r, head_cy - inner_r, cx + inner_r, head_cy + inner_r], fill="white")
    return img


def _write_pin_files() -> dict[str, str]:
    """Write the four pin PNGs once into /tmp and return their paths."""
    paths = {
        "red":   "/tmp/_pin_red.png",
        "green": "/tmp/_pin_green.png",
        "blue":  "/tmp/_pin_blue.png",
        "amber": "/tmp/_pin_amber.png",
    }
    _make_pin("#e63946", "#a91d2b", size=56).save(paths["red"])
    _make_pin("#16a34a", "#0e7c37", size=48).save(paths["green"])
    _make_pin("#2563eb", "#1e40af", size=40).save(paths["blue"])
    _make_pin("#f59e0b", "#b45309", size=40).save(paths["amber"])
    return paths


def render_map(target: dict, green_practices: list[dict],
               blue_practices: list[dict], amber_practices: list[dict]) -> bytes:
    """Render the OSM static map centered on target. Returns JPEG bytes."""
    from staticmap import StaticMap, IconMarker  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    pins = _write_pin_files()
    m = StaticMap(900, 540, padding_x=10, padding_y=10,
                  url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")

    # Order: amber/blue first (under), green next, red last so red sits on top
    for p in amber_practices:
        m.add_marker(IconMarker((p["lng"], p["lat"]), pins["amber"], 20, 38))
    for p in blue_practices:
        m.add_marker(IconMarker((p["lng"], p["lat"]), pins["blue"], 20, 38))
    for p in green_practices:
        m.add_marker(IconMarker((p["lng"], p["lat"]), pins["green"], 24, 46))
    m.add_marker(IconMarker((target["lng"], target["lat"]), pins["red"], 28, 54))

    img = m.render(zoom=13, center=[target["lng"], target["lat"]])

    buf = io.BytesIO()
    img.convert("RGB").resize(
        (1120, int(540 * 1120 / 900)), Image.LANCZOS,
    ).save(buf, format="JPEG", quality=82, optimize=True, progressive=True)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Picking pins from the hitlist row
# ----------------------------------------------------------------------------

def _pins_for_row(row: dict, inputs: dict) -> tuple[list[dict], list[dict], list[dict], str]:
    """Pick green/blue/amber pin sets + the tier-appropriate opener phrase.

    Returns (green_practices, blue_practices, amber_practices, opener_phrase).
    Practices are filtered to within MAP_RADIUS_MI of the target so the map
    stays visually centered on them.
    """
    by_ods = {p["ods"].upper(): p for p in inputs["practices"]}
    target = row["target"]

    def dist(p: dict) -> float:
        return phs.haversine_mi(target["lat"], target["lng"], p["lat"], p["lng"])

    # Green: prioritise same-PCN anchors, then within-10mi, then same-ICB.
    # Always include the strongest anchor even if at edge of map.
    green_candidates = (
        [a for a, _ in row["live_same_pcn"]]
        + [a for a, _ in row["live_within_10mi"]]
        + [a for a, _ in row["live_same_icb"]]
    )
    green_within_radius = [g for g in green_candidates if dist(g) <= MAP_RADIUS_MI]
    if not green_within_radius and green_candidates:
        # Fall back to the single strongest, even if outside the cluster
        green_within_radius = [green_candidates[0]]

    # Blue: nearby In Progress
    inprog_pool = [by_ods[c] for c in inputs["onboarding"]
                   if c in by_ods and c != target["ods"].upper()]
    blue = sorted([p for p in inprog_pool if dist(p) <= MAP_RADIUS_MI], key=dist)[:MAX_BLUE]

    # Amber: nearby Signed-up (excluding In Progress and the target itself)
    signed_pool = [by_ods[c] for c in inputs["waitlist"]
                   if c in by_ods and c not in inputs["onboarding"]
                   and c != target["ods"].upper()]
    amber = sorted([p for p in signed_pool if dist(p) <= MAP_RADIUS_MI], key=dist)[:MAX_AMBER]

    # Tier-appropriate opener
    if row["tier"] in (1, 2, 3):
        opener = "Practices in your PCN have taken it on, and we thought you'd want to see."
    elif row["tier"] == 4:
        opener = "Practices on your doorstep have taken it on, and we thought you'd want to see."
    else:
        opener = "Practices in your area have taken it on, and we thought you'd want to see."

    return green_within_radius, blue, amber, opener


# ----------------------------------------------------------------------------
# HTML template
# ----------------------------------------------------------------------------

EMAIL_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Planner is growing in your area</title>
  <style>
    body {{
      margin: 0;
      padding: 28px 16px;
      font-family: Arial, Helvetica, sans-serif;
      background: #EAF0F6;
      color: #23496d;
      -webkit-font-smoothing: antialiased;
      line-height: 1.55;
      font-size: 15px;
    }}
    .logo-row {{ text-align: center; padding: 8px 0 18px; }}
    .logo-row img {{ width: 130px; max-width: 50%; height: auto; }}
    .email {{
      max-width: 600px;
      margin: 0 auto;
      background: #ffffff;
      border-radius: 6px;
      padding: 36px 36px 40px;
    }}
    .headline {{
      font-family: Arial, Helvetica, sans-serif;
      font-weight: 700;
      font-size: 28px;
      line-height: 1.2;
      letter-spacing: -0.3px;
      margin: 0 0 18px;
      color: #0E3D89;
    }}
    p {{ margin: 0 0 16px; color: #23496d; line-height: 175%; }}
    .intro {{ font-size: 15px; color: #23496d; margin-bottom: 22px; }}
    .map-wrap {{
      border-radius: 8px;
      overflow: hidden;
      background: #EAF0F6;
      border: 1px solid #d4dbe6;
      margin: 8px 0 0;
    }}
    .map-wrap img {{ display: block; width: 100%; height: auto; }}
    .map-legend {{
      display: flex;
      gap: 18px;
      padding: 12px 4px 6px;
      font-size: 13px;
      color: #23496d;
      flex-wrap: wrap;
    }}
    .map-legend .pin {{
      display: inline-block;
      width: 10px; height: 10px; border-radius: 50%;
      margin-right: 7px; vertical-align: middle;
      border: 1.5px solid;
    }}
    .pin.green  {{ background: #16a34a; border-color: #0e7c37; }}
    .pin.blue   {{ background: #2563eb; border-color: #1e40af; }}
    .pin.amber  {{ background: #f59e0b; border-color: #b45309; }}
    .pin.red    {{ background: #e63946; border-color: #a91d2b; }}
    .map-caption {{
      font-size: 14px;
      color: #23496d;
      margin: 6px 2px 26px;
      line-height: 1.55;
    }}
    .map-caption b {{ color: #0E3D89; font-weight: 700; }}
    .quote-section-head {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 20px;
      font-weight: 700;
      color: #0E3D89;
      margin: 6px 0 4px;
      letter-spacing: -0.2px;
    }}
    .quote-section-sub {{
      font-size: 13px;
      color: #23496d;
      opacity: 0.8;
      margin: 0 0 14px;
    }}
    .quotes {{
      display: table;
      width: 100%;
      border-spacing: 14px 0;
      margin: 4px -14px 22px;
    }}
    .quote {{
      display: table-cell;
      width: 50%;
      background: #EAF0F6;
      border-left: 3px solid #0E3D89;
      padding: 16px 18px 14px;
      border-radius: 0 4px 4px 0;
      vertical-align: top;
    }}
    .quote .open-quote {{
      font-family: Georgia, serif;
      font-size: 28px;
      font-weight: 700;
      color: #0E3D89;
      line-height: 1;
      margin: -2px 0 4px;
    }}
    .quote-body {{
      font-style: italic;
      font-size: 13.5px;
      line-height: 1.55;
      color: #23496d;
      margin: 0 0 10px;
    }}
    .quote-attr {{
      font-size: 12px;
      color: #0E3D89;
      font-weight: 700;
    }}
    .body-copy {{ font-size: 15px; color: #23496d; line-height: 175%; }}
    .cta-block {{ margin: 26px 0 6px; }}
    .cta-lead {{
      font-size: 15px;
      color: #23496d;
      margin: 0 0 14px;
      line-height: 175%;
    }}
    .cta-primary {{
      display: inline-block;
      background: #0E3D89;
      color: #ffffff;
      padding: 12px 22px;
      border-radius: 8px;
      text-decoration: none;
      font-weight: 700;
      font-size: 15px;
    }}
    .cta-primary:visited, .cta-primary:hover {{ color: #ffffff; }}
    a {{ color: #00a4bd; text-decoration: underline; }}
    .sig {{
      margin-top: 32px;
      padding-top: 20px;
      border-top: 1px solid #d4dbe6;
      font-size: 15px;
      color: #23496d;
      line-height: 1.6;
    }}
    .sig p {{ margin: 0 0 2px; line-height: 175%; }}
    .sig .name {{ font-weight: 700; }}
    .sig .brand {{ font-weight: 700; padding-top: 6px; display: block; }}
    .sig .tag {{ font-weight: 700; }}
    .footer {{
      max-width: 600px;
      margin: 0 auto;
      text-align: center;
      padding: 18px 10px 0;
      font-size: 12px;
      color: #23496d;
      line-height: 1.5;
    }}
    .footer a {{ color: #00a4bd; }}
  </style>
</head>
<body>

  <div class="logo-row">
    <img alt="Suvera" src="https://hub.suvera.co.uk/hs-fs/hubfs/Logo-1.png?width=260&amp;upscale=true&amp;name=Logo-1.png" />
  </div>

  <div class="email">

    <h1 class="headline">Planner is growing in your area</h1>

    <p class="intro">Hi (First name),</p>
    <p class="intro">Practices are automating their recall fully end-to-end. {opener}</p>

    <div class="map-wrap">
      <img alt="Map of Planner adoption near {target_name}"
           src="data:image/jpeg;base64,{map_b64}" />
    </div>
    <div class="map-legend">
      <span><span class="pin green"></span>Live &amp; recalling</span>
      <span><span class="pin blue"></span>Currently onboarding</span>
      <span><span class="pin amber"></span>Signed up</span>
      <span><span class="pin red"></span>You &middot; {target_name}</span>
    </div>
    <div class="map-caption">
      {caption_html}
    </div>

    <div class="quote-section-head">Don&rsquo;t just take our word for it</div>
    <div class="quote-section-sub">What practices are saying</div>

    <div class="quotes">
      <div class="quote">
        <div class="open-quote">&ldquo;</div>
        <p class="quote-body">This is the difference between &lsquo;needing improvement&rsquo; and being &lsquo;good&rsquo; in CQC. I feel like this is ChatGPT for recall.</p>
        <div class="quote-attr">Practice Manager &middot; Twyford Surgery</div>
      </div>
      <div class="quote">
        <div class="open-quote">&ldquo;</div>
        <p class="quote-body">It&rsquo;s absolutely amazing. It saves so much time, and the integrated blood forms is going to be a real winner for us. It&rsquo;s a no-brainer.</p>
        <div class="quote-attr">GP Partner &middot; Standish Medical Practice</div>
      </div>
    </div>

    <p class="body-copy">Planner runs the entire workflow: recall, blood form generation, and booking patients into multi-morbidity clinics. The point is giving you back your time.</p>

    <div class="cta-block">
      <p class="cta-lead">Sign up to try Planner risk-free here:</p>
      <a class="cta-primary" href="https://www.suvera.com/planner">suvera.com/planner &rarr;</a>
    </div>

    <div class="sig">
      <p>Best Wishes,</p>
      <p class="name">Dr. Will Gao</p>
      <p>Co-Founder, CCO</p>
      <p class="brand">Suvera</p>
      <p class="tag">Proactive Care. Trusted Outcomes.</p>
    </div>

  </div>

  <div class="footer">
    <p>Suvera, 1st Floor, Aylesbury Works, 19 Aylesbury Street, London, England EC1R 0DB</p>
    <p><a href="*|UNSUB|*">Unsubscribe</a></p>
  </div>

</body>
</html>
"""


def _practice_display_name(name: str) -> str:
    """Convert SCREAMING_SNAKE / ALL CAPS practice names to Title Case."""
    return name.title().replace("'S", "'s").replace(" Pcn", " PCN").replace("Gp ", "GP ")


def build_caption(row: dict, green: list[dict], blue: list[dict], amber: list[dict]) -> str:
    """Build the personalised map caption from the row + pin counts."""
    target = row["target"]
    pcn = target.get("pcn_name") or "your PCN"
    parts = []

    # Lead with the strongest specific signal we have
    if row["live_same_pcn"]:
        anchor = _practice_display_name(row["live_same_pcn"][0][0]["name"])
        parts.append(f"In {pcn}, <b>{anchor}</b> is already live &amp; recalling")
        if row["signedup_same_pcn"]:
            partner = _practice_display_name(row["signedup_same_pcn"][0]["name"])
            parts[-1] += f" and <b>{partner}</b> has just signed up"
        if row["inprogress_same_pcn"]:
            partner = _practice_display_name(row["inprogress_same_pcn"][0]["name"])
            parts[-1] += f" and <b>{partner}</b> is mid-onboarding"
        parts[-1] += "."
    elif row["live_within_10mi"]:
        a, d = row["live_within_10mi"][0]
        parts.append(f"<b>{_practice_display_name(a['name'])}</b> is live &amp; recalling just {d:.1f} miles from you.")
    elif row["live_same_icb"]:
        a, _ = row["live_same_icb"][0]
        parts.append(f"<b>{_practice_display_name(a['name'])}</b> in your ICB is already live &amp; recalling.")

    # Add the cluster summary
    cluster_bits = []
    if len(green) >= 1:
        cluster_bits.append(f"<b>{len(green)} Live</b> practice" + ("s" if len(green) != 1 else ""))
    if blue:
        cluster_bits.append(f"<b>{len(blue)} currently onboarding</b>")
    if amber:
        cluster_bits.append(f"<b>{len(amber)}+ signed up</b>")
    if cluster_bits:
        parts.append("Within five miles of you there " +
                     ("are " if (sum(len(p) for p in (blue, amber)) + len(green)) > 1 else "is ") +
                     ", ".join(cluster_bits[:-1]) +
                     (", and " if len(cluster_bits) > 1 else "") +
                     cluster_bits[-1] +
                     ", all on Planner for intelligent patient recall.")

    return " ".join(parts)


# ----------------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------------

def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60]


def render_email_for_row(row: dict, inputs: dict) -> Path:
    """Render one HTML email for a hitlist row. Returns the output path."""
    target = row["target"]
    green, blue, amber, opener = _pins_for_row(row, inputs)
    map_jpeg = render_map(target, green, blue, amber)
    map_b64 = base64.b64encode(map_jpeg).decode()

    target_name = _practice_display_name(target["name"])
    caption_html = build_caption(row, green, blue, amber)

    html = EMAIL_HTML.format(
        opener=opener,
        target_name=target_name,
        map_b64=map_b64,
        caption_html=caption_html,
    )
    assert "—" not in html and "&mdash;" not in html, "em-dash slipped in"

    out_path = OUT_DIR / f"outreach_{target['ods']}_{_slugify(target['name'])}.html"
    out_path.write_text(html)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ods", nargs="?", help="Target ODS code (e.g. F85007). Omit if using --top.")
    ap.add_argument("--top", type=int, help="Render the top N targets from the hitlist.")
    ap.add_argument("--status", choices=["In Progress", "Signed-up", "Not signed up"],
                    help="Filter --top by status.")
    args = ap.parse_args()

    if not args.ods and not args.top:
        ap.error("Provide an ODS code or --top N")

    inputs = phs.load_inputs()
    sicbl = SicblCache(phs.SICBL_CACHE)
    rows = phs.build_hitlist(
        practices=inputs["practices"],
        waitlist=inputs["waitlist"],
        full_planner=inputs["full_planner"],
        onboarding=inputs["onboarding"],
        active=inputs["active"],
        sicbl_lookup=sicbl,
        frimley_map=inputs["frimley_map"],
    )

    targets: list[dict] = []
    if args.ods:
        ods = args.ods.upper()
        matched = [r for r in rows if r["target"]["ods"].upper() == ods]
        if not matched:
            print(f"ODS {ods} not in the hitlist (no Live anchor nearby, "
                  f"or it's Live/excluded). Nothing to do.")
            sys.exit(1)
        targets = matched
    else:
        filtered = rows if not args.status else [r for r in rows if r["status"] == args.status]
        targets = filtered[: args.top]
        if not targets:
            print("No targets matched the filter. Nothing to do.")
            sys.exit(1)

    print(f"Rendering {len(targets)} email{'s' if len(targets) != 1 else ''}...")
    for r in targets:
        path = render_email_for_row(r, inputs)
        t = r["target"]
        print(f"  T{r['tier']} | {r['status']:<14} | {t['ods']} | "
              f"{_practice_display_name(t['name'])}  ->  {path}")


if __name__ == "__main__":
    main()
