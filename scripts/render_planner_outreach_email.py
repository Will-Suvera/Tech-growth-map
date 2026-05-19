#!/usr/bin/env python3
"""Render a personalised Planner outreach email for a target practice.

Three email variants form a sequence (send one per week):

  V1 — "Planner is growing in your area"
       Heavy on local social proof. Full map. Three theme-led value lines
       (recall-that-runs-itself / one-patient-one-invite / LES into your
       area). CTA: book a demo.

  V2 — "Your ICB has signed off Planner"
       Punchier. Leads with the ICB-level data-processing agreement +
       (if applicable) the named local incentive scheme. Same map.
       CTA: book a demo.

  V3 — "Done by December. Q1 is yours."
       Punchiest. QOF-year urgency tied to a real NHS deadline. Same map.
       CTA: book a demo. Closes with a "not this year" P.S.

The opener in V1 adapts by tier (PCN / doorstep / area).

ICB-specific schemes (V2 only)
  - North West London ICB    -> NWL Enhanced Services
  - North Central London ICB -> NCL LTC LCS Scheme
  - Black Country ICB        -> Primary Care Capacity Fund (PCCF)
  - Central East ICB         -> Enhanced Capacity Framework (ECF)
  - all others               -> "We can build LIS/LES into Planner for
                                 your ICB"

Pin colours on the map (all variants)
  RED   = the target practice (you)
  GREEN = Live + actively recalling anchors
  BLUE  = In Progress (onboarding) practices nearby
  AMBER = Signed-up practices nearby

Usage
-----
    python3 scripts/render_planner_outreach_email.py F85007              # V1
    python3 scripts/render_planner_outreach_email.py F85007 --variant 2  # V2
    python3 scripts/render_planner_outreach_email.py F85007 --variant all
    python3 scripts/render_planner_outreach_email.py --top 5 --variant all

Output
------
HTML files land in public/email/, named:
    outreach_<ODS>_<slug>_v<N>.html
"""

from __future__ import annotations

import argparse
import base64
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import push_hitlist_to_sheet as phs  # noqa: E402
from icb_mapper import SicblCache  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "public" / "email"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CTA_URL = "https://www.suvera.com/planner"
CTA_DISPLAY = "suvera.com/planner"
CTA_LABEL = "Book a demo"

MAP_RADIUS_MI = 5.0
MAX_BLUE = 5
MAX_AMBER = 6


# ICB → local scheme. Match against the practice's pre-merger `icb` value
# (case-insensitive substring) because the scheme names were defined before
# the April 2026 ICB mergers.
ICB_SCHEMES: list[tuple[str, str, str]] = [
    # (pre-merger-ICB substring, scheme display name, ICB pretty name)
    ("north west london", "NWL Enhanced Services", "NHS North West London ICB"),
    ("north central london", "NCL LTC LCS Scheme", "NHS North Central London ICB"),
    ("black country", "Primary Care Capacity Fund (PCCF)", "NHS Black Country ICB"),
    ("central east", "Enhanced Capacity Framework (ECF)", "NHS Central East ICB"),
]


def find_scheme(pre_icb: str, post_icb: str = "") -> tuple[str, str] | None:
    """Return (scheme_name, icb_pretty) or None if not a named ICB.

    Checks both pre- and post-merger ICB names so that practices in the new
    Central East ICB (which was formed by merger from Herts/Beds/Cambs/etc.)
    still match when only the post-merger label contains 'central east'.
    NWL and NCL are pre-merger names — matching either side keeps them
    working as the West & North London ICB transition takes hold.
    """
    s_pre  = (pre_icb or "").lower()
    s_post = (post_icb or "").lower()
    for needle, scheme, pretty in ICB_SCHEMES:
        if needle in s_pre or needle in s_post:
            return scheme, pretty
    return None


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


def _zoom_for_spread(distances: list[float]) -> int:
    """Pick an OSM zoom level so the bulk of pins fit tightly.
    Uses the 70th-percentile pin distance instead of max so a single
    outlier (e.g. one onboarding practice 4mi away among nine that
    are 2-3mi away) doesn't yank the zoom out and waste the frame
    on empty space.

    OSM zoom widths at UK latitudes (900px viewport):
      z=14 ~3mi, z=13 ~6.5mi, z=12 ~13mi, z=11 ~26mi, z=10 ~53mi.
    """
    if not distances:
        return 13
    s = sorted(distances)
    p70 = s[min(int(len(s) * 0.7), len(s) - 1)]
    if p70 < 1.0:
        return 14
    if p70 < 2.5:
        return 13
    if p70 < 5.0:
        return 12
    if p70 < 11.0:
        return 11
    return 10


def render_map(target: dict, green_practices: list[dict],
               blue_practices: list[dict], amber_practices: list[dict]) -> bytes:
    """Render the OSM static map centered on target. Returns JPEG bytes."""
    from staticmap import StaticMap, IconMarker  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    pins = _write_pin_files()
    m = StaticMap(900, 540, padding_x=10, padding_y=10,
                  url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")
    for p in amber_practices:
        m.add_marker(IconMarker((p["lng"], p["lat"]), pins["amber"], 20, 38))
    for p in blue_practices:
        m.add_marker(IconMarker((p["lng"], p["lat"]), pins["blue"], 20, 38))
    for p in green_practices:
        m.add_marker(IconMarker((p["lng"], p["lat"]), pins["green"], 24, 46))
    m.add_marker(IconMarker((target["lng"], target["lat"]), pins["red"], 28, 54))

    # Pick zoom by the spread of pins. Uses the 70th-percentile distance
    # so an outlier pin doesn't pull the frame out and waste real estate.
    all_pins = green_practices + blue_practices + amber_practices
    distances = [
        phs.haversine_mi(target["lat"], target["lng"], p["lat"], p["lng"])
        for p in all_pins if p.get("lat") and p.get("lng")
    ]
    zoom = _zoom_for_spread(distances)

    img = m.render(zoom=zoom, center=[target["lng"], target["lat"]])
    buf = io.BytesIO()
    img.convert("RGB").resize(
        (1120, int(540 * 1120 / 900)), Image.LANCZOS,
    ).save(buf, format="JPEG", quality=82, optimize=True, progressive=True)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Picking pins from the hitlist row
# ----------------------------------------------------------------------------

def _pins_for_row(row: dict, inputs: dict) -> tuple[list[dict], list[dict], list[dict], str]:
    by_ods = {p["ods"].upper(): p for p in inputs["practices"]}
    target = row["target"]

    def dist(p: dict) -> float:
        return phs.haversine_mi(target["lat"], target["lng"], p["lat"], p["lng"])

    # Same-PCN anchors are always included regardless of distance — they're
    # the strongest signal even if the physical site is past the 5-mile
    # map radius (e.g. Whitewater Health -> Chineham at ~7mi, same PCN).
    # Other tiers (within-10mi / same-ICB) are added only if they fall
    # inside the map radius so the cluster reads cleanly.
    green_within_radius = [a for a, _ in row["live_same_pcn"]]
    for a, _ in row["live_within_10mi"]:
        if dist(a) <= MAP_RADIUS_MI and a not in green_within_radius:
            green_within_radius.append(a)
    for a, _ in row["live_same_icb"]:
        if dist(a) <= MAP_RADIUS_MI and a not in green_within_radius:
            green_within_radius.append(a)
    if not green_within_radius:
        all_anchors = (
            [a for a, _ in row["live_same_pcn"]]
            + [a for a, _ in row["live_within_10mi"]]
            + [a for a, _ in row["live_same_icb"]]
        )
        if all_anchors:
            green_within_radius = [all_anchors[0]]

    # Pipeline radius scales with the green-pin spread so sparse rural
    # clusters don't drop nearby onboarding / signed-up practices that
    # actually fit on the (auto-zoomed-out) map. Caps at 18 mi so very
    # remote targets still get a finite list.
    green_max_d = max(
        (dist(g) for g in green_within_radius if g.get("lat") and g.get("lng")),
        default=0.0,
    )
    pipeline_radius = min(18.0, max(MAP_RADIUS_MI, green_max_d * 1.6))

    inprog_pool = [by_ods[c] for c in inputs["onboarding"]
                   if c in by_ods and c != target["ods"].upper()]
    blue = sorted([p for p in inprog_pool if dist(p) <= pipeline_radius], key=dist)[:MAX_BLUE]

    signed_pool = [by_ods[c] for c in inputs["waitlist"]
                   if c in by_ods and c not in inputs["onboarding"]
                   and c != target["ods"].upper()]
    amber = sorted([p for p in signed_pool if dist(p) <= pipeline_radius], key=dist)[:MAX_AMBER]

    if row["tier"] in (1, 2, 3):
        opener = "Practices in your PCN have taken it on, and we thought you'd want to see."
    elif row["tier"] == 4:
        opener = "Practices on your doorstep have taken it on, and we thought you'd want to see."
    else:
        opener = "Practices in your area have taken it on, and we thought you'd want to see."

    return green_within_radius, blue, amber, opener


# ----------------------------------------------------------------------------
# Shared HTML components
# ----------------------------------------------------------------------------

# All three variants share <head>, logo strip, map block, sig and footer. The
# {body} placeholder is filled per-variant.
EMAIL_SHELL = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:28px 16px;font-family:Arial,Helvetica,sans-serif;background:#EAF0F6;color:#23496d;-webkit-font-smoothing:antialiased;line-height:1.55;font-size:15px;">

  <div style="text-align:center;padding:8px 0 18px;">
    <img alt="Suvera"
         src="https://hub.suvera.co.uk/hs-fs/hubfs/Logo-1.png?width=260&amp;upscale=true&amp;name=Logo-1.png"
         width="130"
         style="display:inline-block;width:130px;max-width:50%;height:auto;border:0;outline:none;text-decoration:none;" />
  </div>

  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:6px;padding:36px 36px 40px;">

    {body}

    <div style="margin-top:32px;padding-top:20px;border-top:1px solid #d4dbe6;font-size:15px;color:#23496d;line-height:1.6;">
      <p style="margin:0 0 2px;line-height:175%;">Best Wishes,</p>
      <p style="margin:0 0 2px;line-height:175%;font-weight:700;">Dr. Will Gao</p>
      <p style="margin:0 0 2px;line-height:175%;">Co-Founder, CCO</p>
      <p style="margin:0;padding-top:6px;line-height:175%;font-weight:700;">Suvera</p>
      <p style="margin:0;line-height:175%;font-weight:700;">Proactive Care. Trusted Outcomes.</p>
    </div>

  </div>

  <div style="max-width:600px;margin:0 auto;text-align:center;padding:18px 10px 0;font-size:12px;color:#23496d;line-height:1.5;">
    <p style="margin:0 0 6px;">Suvera, 1st Floor, Aylesbury Works, 19 Aylesbury Street, London, England EC1R 0DB</p>
    <p style="margin:0;font-style:italic;">If you&rsquo;d prefer not to receive messages, please reply &ldquo;not interested&rdquo;.</p>
  </div>

</body>
</html>
"""


def headline(text: str) -> str:
    return (
        '<h1 style="font-family:Arial,Helvetica,sans-serif;font-weight:700;'
        'font-size:28px;line-height:1.2;letter-spacing:-0.3px;margin:0 0 18px;'
        f'color:#0E3D89;">{text}</h1>'
    )


def intro_para(text: str) -> str:
    return (
        '<p style="font-size:15px;color:#23496d;margin:0 0 14px;line-height:175%;">'
        f"{text}</p>"
    )


def body_para(text: str) -> str:
    return (
        '<p style="font-size:15px;color:#23496d;margin:0 0 14px;line-height:175%;">'
        f"{text}</p>"
    )


def map_block(map_b64: str, target_name: str) -> str:
    return (
        f'<img alt="Map of Planner adoption near {target_name}" '
        f'src="data:image/jpeg;base64,{map_b64}" '
        'width="100%" '
        'style="display:block;width:100%;height:auto;margin:8px 0 0;'
        'border:1px solid #d4dbe6;border-radius:8px;outline:none;'
        'text-decoration:none;" />'
    )


def legend_block(target_name: str) -> str:
    items = [
        ("#16a34a", "#0e7c37", "Live &amp; recalling"),
        ("#2563eb", "#1e40af", "Currently onboarding"),
        ("#f59e0b", "#b45309", "Signed up"),
        ("#e63946", "#a91d2b", f"You &middot; {target_name}"),
    ]
    spans = []
    for bg, br, label in items:
        spans.append(
            '<span style="display:inline-block;margin-right:18px;white-space:nowrap;">'
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
            f'background:{bg};border:1.5px solid {br};margin-right:7px;vertical-align:middle;"></span>'
            f'{label}</span>'
        )
    return (
        '<div style="padding:12px 4px 6px;font-size:13px;color:#23496d;line-height:22px;">'
        + " ".join(spans)
        + "</div>"
    )


def caption_block(html: str) -> str:
    return (
        '<div style="font-size:14px;color:#23496d;margin:6px 2px 26px;line-height:1.55;">'
        + html
        + "</div>"
    )


def cta_block(lead: str = "Try Planner risk-free here:",
              label: str = "Risk Free Planner Sign-up",
              url: str = CTA_URL) -> str:
    return (
        '<div style="margin:26px 0 6px;">'
        f'<p style="font-size:15px;color:#23496d;margin:0 0 14px;line-height:175%;">{lead}</p>'
        f'<a href="{url}" style="display:inline-block;background:#0E3D89;color:#ffffff;'
        'padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">'
        f'{label} &rarr;</a>'
        "</div>"
    )


WEBINAR_URL = (
    "https://events.teams.microsoft.com/event/"
    "000fc863-6e98-48ee-8e2c-86c52b61eef8@ed70d66f-04c3-46dd-833c-8f81ff836d33"
)


DEFAULT_CTA_LEAD = (
    "Try Planner risk-free here or sign-up to our webinar on "
    "Thursday 28th to watch it first hand."
)


def dual_cta_block(
    lead: str = DEFAULT_CTA_LEAD,
    primary_label: str = "Risk Free Planner Sign-up",
    primary_url: str = CTA_URL,
    secondary_label: str = "Secure your Webinar place",
    secondary_url: str = WEBINAR_URL,
) -> str:
    """Two side-by-side CTAs: solid navy primary + outlined secondary."""
    primary_btn = (
        f'<a href="{primary_url}" style="display:inline-block;background:#0E3D89;'
        'color:#ffffff;padding:12px 22px;border-radius:8px;text-decoration:none;'
        f'font-weight:700;font-size:15px;border:2px solid #0E3D89;">{primary_label} &rarr;</a>'
    )
    secondary_btn = (
        f'<a href="{secondary_url}" style="display:inline-block;background:#ffffff;'
        'color:#0E3D89;padding:12px 22px;border-radius:8px;text-decoration:none;'
        f'font-weight:700;font-size:15px;border:2px solid #0E3D89;">{secondary_label} &rarr;</a>'
    )
    return (
        '<div style="margin:26px 0 6px;">'
        f'<p style="font-size:15px;color:#23496d;margin:0 0 14px;line-height:175%;">{lead}</p>'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="border-collapse:collapse;border-spacing:0;">'
        '<tr>'
        f'<td style="padding:0 8px 8px 0;">{primary_btn}</td>'
        f'<td style="padding:0 0 8px 0;">{secondary_btn}</td>'
        '</tr>'
        '</table>'
        '</div>'
    )


def value_line(strong: str, rest: str) -> str:
    """One of the three theme-led value lines (stacked)."""
    return (
        '<p style="font-size:15px;color:#23496d;margin:0 0 14px;line-height:175%;">'
        f'<strong style="color:#0E3D89;">{strong}</strong> {rest}</p>'
    )


def value_columns(items: list[tuple[str, str]]) -> str:
    """Email-safe 3-column value strip styled like the testimonial cards.
    All three cards inherit equal height because they share a <tr>; the inner
    div uses height:100% + min-height so the pale-blue fill extends fully
    even where copy is short."""
    assert len(items) == 3, "value_columns expects exactly 3 items"
    cells = []
    pads = ["0 7px 0 0", "0 7px", "0 0 0 7px"]
    for (heading, subtitle), pad in zip(items, pads):
        card = (
            '<div style="background:#EAF0F6;padding:16px 18px 14px;border-radius:6px;'
            'height:100%;min-height:140px;box-sizing:border-box;">'
            '<h3 style="font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:700;'
            f'color:#0E3D89;margin:0 0 6px;line-height:1.3;">{heading}</h3>'
            '<p style="font-size:13px;line-height:1.55;color:#23496d;margin:0;">'
            f'{subtitle}</p>'
            '</div>'
        )
        cells.append(
            f'<td valign="top" style="width:33.33%;padding:{pad};">{card}</td>'
        )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="border-collapse:collapse;border-spacing:0;margin:16px 0 22px;">'
        '<tr>' + "".join(cells) + '</tr></table>'
    )


# ----------------------------------------------------------------------------
# Caption builder (shared)
# ----------------------------------------------------------------------------

def _practice_display_name(name: str) -> str:
    return name.title().replace("'S", "'s").replace(" Pcn", " PCN").replace("Gp ", "GP ")


def build_caption(row: dict, green: list[dict], blue: list[dict], amber: list[dict]) -> str:
    """Kept as a fallback / single-line summary. The primary breakdown is now
    rendered as an HTML table in `practice_table()` below."""
    target = row["target"]
    pcn = target.get("pcn_name") or "your PCN"
    if row["live_same_pcn"]:
        anchor = _practice_display_name(row["live_same_pcn"][0][0]["name"])
        return f"In {pcn}, <b>{anchor}</b> is already live &amp; recalling. Local breakdown below."
    if row["live_within_10mi"]:
        a, d = row["live_within_10mi"][0]
        return f"<b>{_practice_display_name(a['name'])}</b> is live &amp; recalling just {d:.1f} miles from you. Local breakdown below."
    if row["live_same_icb"]:
        a, _ = row["live_same_icb"][0]
        return f"<b>{_practice_display_name(a['name'])}</b> in your ICB is already live &amp; recalling. Local breakdown below."
    return "Local breakdown below."


# --- Practice breakdown (compact text form) ---------------------------------

MAX_NAMES_PER_LINE = 8


def _name_list(practices: list[dict], target: dict) -> str:
    """Display names, comma-joined, PCN partners surfaced first."""
    def _rank(p):
        if phs._norm_pcn(target) and phs._norm_pcn(p) == phs._norm_pcn(target):
            return -1.0
        if target.get("lat") and p.get("lat"):
            return phs.haversine_mi(target["lat"], target["lng"], p["lat"], p["lng"])
        return 999.0

    sorted_p = sorted(practices, key=_rank)
    names = [_practice_display_name(p.get("name", "")) for p in sorted_p[:MAX_NAMES_PER_LINE]]
    extra = len(sorted_p) - MAX_NAMES_PER_LINE
    text = ", ".join(names)
    if extra > 0:
        text += f", and {extra} more"
    return text


def practice_table(row: dict, green: list[dict], blue: list[dict], amber: list[dict]) -> str:
    """Plain-text breakdown of nearby practices. Doubles as the map legend:
    "You" line in red sits at the top with the target practice name,
    then Live / Onboarding / Signed up. No outer card."""
    target = row["target"]
    target_name = _practice_display_name(target.get("name", ""))

    line_style = "margin:0 0 6px;font-size:14px;line-height:1.6;color:#23496d;"
    dot_style_tmpl = (
        "display:inline-block;width:9px;height:9px;border-radius:50%;"
        "background:{bg};border:1.5px solid {br};margin-right:8px;vertical-align:middle;"
    )

    lines = []
    lines.append(
        f'<p style="{line_style}">'
        f'<span style="{dot_style_tmpl.format(bg="#e63946", br="#a91d2b")}"></span>'
        f'<b style="color:#a91d2b;">You:</b> {target_name}</p>'
    )
    if green:
        lines.append(
            f'<p style="{line_style}">'
            f'<span style="{dot_style_tmpl.format(bg="#16a34a", br="#0e7c37")}"></span>'
            '<b style="color:#16a34a;">Live and recalling patients:</b> '
            f'{_name_list(green, target)}</p>'
        )
    if blue:
        lines.append(
            f'<p style="{line_style}">'
            f'<span style="{dot_style_tmpl.format(bg="#2563eb", br="#1e40af")}"></span>'
            '<b style="color:#1e40af;">Onboarding now:</b> '
            f'{_name_list(blue, target)}</p>'
        )
    if amber:
        lines.append(
            f'<p style="{line_style}">'
            f'<span style="{dot_style_tmpl.format(bg="#f59e0b", br="#b45309")}"></span>'
            '<b style="color:#b45309;">Signed up:</b> '
            f'{_name_list(amber, target)}</p>'
        )

    return '<div style="margin:14px 0 24px;">' + "".join(lines) + '</div>'


# ----------------------------------------------------------------------------
# Variant bodies
# ----------------------------------------------------------------------------

def quotes_block() -> str:
    """The two-column 'Don't just take our word for it' testimonial pair."""
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:700;'
        'color:#0E3D89;margin:6px 0 4px;letter-spacing:-0.2px;">Don&rsquo;t just take our word for it</div>'
        '<div style="font-size:13px;color:#23496d;opacity:0.8;margin:0 0 14px;">What practices are saying</div>'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="border-spacing:0;margin:4px 0 22px;">'
        '<tr>'
        + '<td valign="top" style="width:50%;padding:0 7px 0 0;">'
        + _quote_card(
            "This is the difference between &lsquo;needing improvement&rsquo; and being &lsquo;good&rsquo; "
            "in CQC. I feel like this is ChatGPT for recall.",
            "Practice Manager &middot; Twyford Surgery",
        )
        + '</td>'
        '<td valign="top" style="width:50%;padding:0 0 0 7px;">'
        + _quote_card(
            "It&rsquo;s absolutely amazing. It saves so much time, and the integrated blood forms is "
            "going to be a real winner for us. It&rsquo;s a no-brainer.",
            "GP Partner &middot; Standish Medical Practice",
        )
        + '</td>'
        '</tr></table>'
    )


def _quote_card(body_text: str, attribution: str) -> str:
    return (
        '<div style="background:#EAF0F6;border-left:3px solid #0E3D89;padding:16px 18px 14px;'
        'border-radius:0 4px 4px 0;">'
        '<div style="font-family:Georgia,serif;font-size:28px;font-weight:700;color:#0E3D89;'
        'line-height:1;margin:-2px 0 4px;">&ldquo;</div>'
        '<p style="font-style:italic;font-size:13.5px;line-height:1.55;color:#23496d;margin:0 0 10px;">'
        f"{body_text}</p>"
        '<div style="font-size:12px;color:#0E3D89;font-weight:700;">'
        f"{attribution}</div>"
        "</div>"
    )


def body_v1(row: dict, green, blue, amber, opener: str, map_b64: str, target_name: str) -> str:
    """V1 — local social proof + testimonials. Map heavy, voice-of-customer lead."""
    bits = []
    bits.append(headline("Planner is growing in your area"))
    bits.append(intro_para("Hi (First name),"))
    bits.append(intro_para(f"Practices are automating their recall fully end-to-end. {opener}"))
    bits.append(map_block(map_b64, target_name))
    bits.append(practice_table(row, green, blue, amber))
    bits.append(quotes_block())
    bits.append(body_para(
        "Planner puts the entire recall on auto-pilot: recall, blood form generation and booking "
        "patients into multi-morbidity clinics, saving you time and admin."
    ))
    bits.append(dual_cta_block())
    return "\n".join(bits)


def body_v2(row: dict, green, blue, amber, map_b64: str, target_name: str) -> str:
    """V2 — feature-led. Three theme-led value lines lead, map below as
    social proof, ICB sign-off as a small "blocker removed" hook."""
    target = row["target"]
    pre_icb = target.get("icb") or ""
    post_icb = row.get("target_icb_post") or pre_icb or "your ICB"
    scheme = find_scheme(pre_icb, post_icb)

    bits = []
    bits.append(headline("Recall, on autopilot."))
    bits.append(intro_para("Hi (First name),"))
    bits.append(intro_para(
        "Following on from last week - here is why Planner is being adopted around you."
    ))

    bits.append(value_columns([
        ("Recall that runs itself.",
         "Patients pulled in at the right time. Blood forms generated in ICE/T-quest, coded back to your EMR."),
        ("One invite per pt.",
         "Every condition due in one appointment. No more six texts to a multi-condition patient."),
        ("LES built in.",
         "Local targets fully built in (e.g CVD targets, smoking cessation) run alongside QOF."),
    ]))

    # Map as social proof
    bits.append(body_para("Here is what adoption looks like around you:"))
    bits.append(map_block(map_b64, target_name))
    bits.append(practice_table(row, green, blue, amber))

    # ICB sign-off as a small "blocker removed" hook
    if scheme:
        scheme_name, _ = scheme
        bits.append(body_para(
            f"And one less thing to worry about: <b>{post_icb}</b> has signed Planner's DPA at ICB level, "
            f"and <b>{scheme_name}</b> is designed into Planner."
        ))
    else:
        bits.append(body_para(
            f"And one less thing to worry about: <b>{post_icb}</b> has signed Planner's DPA at ICB level. "
            "We can build LIS / LES schemes into Planner for your ICB."
        ))

    bits.append(cta_block("Try Planner risk-free here:"))
    return "\n".join(bits)


def _short_quote_card(body_text: str, attribution: str) -> str:
    """Compact testimonial card for V3 (no opening quote glyph, slim padding)."""
    return (
        '<div style="background:#EAF0F6;border-left:3px solid #0E3D89;padding:12px 14px;'
        'border-radius:0 4px 4px 0;margin:0 0 10px;">'
        '<p style="font-style:italic;font-size:13.5px;line-height:1.5;color:#23496d;margin:0 0 6px;">'
        f"&ldquo;{body_text}&rdquo;</p>"
        '<div style="font-size:12px;color:#0E3D89;font-weight:700;">'
        f"{attribution}</div>"
        "</div>"
    )


def body_v3(row, green, blue, amber, map_b64: str, target_name: str) -> str:
    """V3 — short, no map. Testimonials + feature recap. QOF-year urgency."""
    bits = []
    bits.append(headline("Avoid the end of year scramble."))
    bits.append(intro_para("Hi (First name),"))
    bits.append(body_para(
        "Practices going live on Planner now will be able to recall patients early and avoid the classic "
        "end of year scramble. Saving time, stress whilst improving patient care."
    ))

    # Same testimonials as V1 (per user request — consistent voice across sequence)
    bits.append(_short_quote_card(
        "This is the difference between &lsquo;needing improvement&rsquo; and being &lsquo;good&rsquo; in CQC. "
        "I feel like this is ChatGPT for recall.",
        "Practice Manager &middot; Twyford Surgery",
    ))
    bits.append(_short_quote_card(
        "It&rsquo;s absolutely amazing. It saves so much time, and the integrated blood forms is "
        "going to be a real winner for us. It&rsquo;s a no-brainer.",
        "GP Partner &middot; Standish Medical Practice",
    ))

    # Feature recap as a tight 3-bullet list
    bits.append(
        '<ul style="margin:8px 0 18px 18px;padding:0;color:#23496d;font-size:15px;line-height:175%;">'
        '<li><b>Recall that runs itself.</b> Blood forms generated in ICE, outcomes coded back to EMIS or SystmOne.</li>'
        '<li><b>One patient. One invite.</b> Every condition due in one appointment.</li>'
        '<li><b>QOF + LES in one run.</b> The local income lines you are already commissioned for, delivered automatically.</li>'
        '</ul>'
    )

    bits.append(body_para(
        "We&rsquo;d be delighted to show this to you and support in automating your recalls."
    ))

    bits.append(cta_block("Try Planner risk-free here:"))
    return "\n".join(bits)


VARIANT_TITLES = {
    1: "Planner is growing in your area",
    2: "Your ICB has signed off Planner",
    3: "Avoid the end of year scramble",
}
VARIANT_BUILDERS = {
    1: body_v1,
    2: body_v2,
    3: body_v3,
}


def render_email_for_row(row: dict, inputs: dict, variant: int) -> Path:
    target = row["target"]
    green, blue, amber, opener = _pins_for_row(row, inputs)
    target_name = _practice_display_name(target["name"])

    # V3 has no map, so skip the (slow, network-bound) map render entirely.
    map_b64 = ""
    if variant in (1, 2):
        map_jpeg = render_map(target, green, blue, amber)
        map_b64 = base64.b64encode(map_jpeg).decode()

    if variant == 1:
        body = body_v1(row, green, blue, amber, opener, map_b64, target_name)
    elif variant == 2:
        body = body_v2(row, green, blue, amber, map_b64, target_name)
    elif variant == 3:
        body = body_v3(row, green, blue, amber, map_b64, target_name)
    else:
        raise ValueError(f"Unknown variant {variant}")

    html = EMAIL_SHELL.format(title=VARIANT_TITLES[variant], body=body)
    assert "—" not in html and "&mdash;" not in html, "em-dash slipped in"

    out_path = OUT_DIR / f"outreach_{target['ods']}_{_slugify(target['name'])}_v{variant}.html"
    out_path.write_text(html)
    return out_path


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ods", nargs="?", help="Target ODS code (e.g. F85007).")
    ap.add_argument("--top", type=int, help="Render the top N targets from the hitlist.")
    ap.add_argument("--status", choices=["In Progress", "Signed-up", "Not signed up"],
                    help="Filter --top / --tier by status.")
    ap.add_argument("--tier", type=int, choices=[1, 2, 3, 4, 5],
                    help="Render every target at this tier. Combine with --status to narrow.")
    ap.add_argument("--variant", default="1", help="Email variant: 1, 2, 3, or 'all' (default 1).")
    args = ap.parse_args()

    if not args.ods and not args.top and not args.tier:
        ap.error("Provide an ODS code, --top N, or --tier N")

    if args.variant == "all":
        variants = [1, 2, 3]
    else:
        try:
            v = int(args.variant)
            if v not in (1, 2, 3):
                raise ValueError
            variants = [v]
        except ValueError:
            ap.error("--variant must be 1, 2, 3, or 'all'")

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

    if args.ods:
        ods = args.ods.upper()
        matched = [r for r in rows if r["target"]["ods"].upper() == ods]
        if not matched:
            print(f"ODS {ods} not in the hitlist. Nothing to do.")
            sys.exit(1)
        targets = matched
    else:
        filtered = rows
        if args.tier:
            filtered = [r for r in filtered if r["tier"] == args.tier]
        if args.status:
            filtered = [r for r in filtered if r["status"] == args.status]
        targets = filtered if args.tier and not args.top else filtered[: args.top]
        if not targets:
            print("No targets matched the filter.")
            sys.exit(1)

    total = len(targets) * len(variants)
    print(f"Rendering {total} email{'s' if total != 1 else ''}...")
    for r in targets:
        for v in variants:
            path = render_email_for_row(r, inputs, v)
            t = r["target"]
            print(f"  V{v} | T{r['tier']} | {r['status']:<14} | {t['ods']} | "
                  f"{_practice_display_name(t['name'])}  ->  {path.name}")


if __name__ == "__main__":
    main()
