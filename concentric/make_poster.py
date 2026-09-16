"""Generate docs/department.svg — the department poster.

    python -m concentric.make_poster

SVG rather than a raster image for one reason: the text is real text, so the
role names are spelled correctly at any size and the poster stays editable.
GitHub renders SVG in a README, and it exports cleanly to PNG or PDF for a slide.

It is a structural poster, not a roster: the CFOs and Irina are named, and each
team's workers are dots on the hub's circle with a count. Naming all nineteen
would need a canvas far wider than a README column, and the names are one
`from concentric import roster` away.

The layout is the one the dashboard draws: Irina between four wheels, each CFO
the hub of its own circle. Placement lives here, not in the roster — the roster
carries only `ring` and `parent`.
"""

from __future__ import annotations

import math
from pathlib import Path

from concentric import roster

W, H = 1600, 1080
HEADER = 104
LEGEND_Y = 1002

NAVY = "#0A1B3A"
BLUE = "#1E4E8C"
EDGE = "#2E6DB4"
AMBER = "#B36B00"
LIGHT = "#F7F9FC"
GREY = "#5A6B80"
SOFT = "#DCE6F2"

R = 175                                   # the worker circle around each hub
DOT = 13
IRINA = (W / 2, 566)
HUBS = [(420, 340), (1180, 340), (1180, 760), (420, 760)]   # clockwise
HUB_W, HUB_H = 196, 60
IRINA_W, IRINA_H = 250, 78


def esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wrap(text: str, limit: int) -> list[str]:
    words, lines, cur = str(text).split(" "), [], ""
    for word in words:
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= limit:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines[:2]


def polar(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def build() -> str:
    p = [
        (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="Segoe UI, Helvetica, Arial, sans-serif">'),
        f'<rect width="{W}" height="{H}" fill="{LIGHT}"/>',
        f'<rect width="{W}" height="{HEADER}" fill="{NAVY}"/>',
        ('<text x="56" y="56" font-size="30" font-weight="700" fill="#FFFFFF">'
         'Irina&#8217;s Department</text>'),
        ('<text x="56" y="84" font-size="15" fill="#A8C4E4">'
         'AI-powered model risk management, built on waku-agent</text>'),
        (f'<text x="{W - 56}" y="56" text-anchor="end" font-size="24" font-weight="700" '
         f'fill="#7FA8D6">24 seats</text>'),
        (f'<text x="{W - 56}" y="84" text-anchor="end" font-size="14" fill="#A8C4E4">'
         f'1 chief model risk officer &#183; 4 CFOs &#183; 19 workers</text>'),
    ]

    cfos = [s for s in roster.SEATS if s.ring == 1]
    workers = [s for s in roster.SEATS if s.ring == 2]
    hub = {c.role: HUBS[i % len(HUBS)] for i, c in enumerate(cfos)}

    ix, iy = IRINA
    for cfo in cfos:
        hx, hy = hub[cfo.role]
        p.append(f'<line x1="{ix:.0f}" y1="{iy + IRINA_H / 2:.0f}" x2="{hx:.0f}" '
                 f'y2="{hy - HUB_H / 2:.0f}" stroke="{EDGE}" stroke-width="2.6"/>')

    for cfo in cfos:
        hx, hy = hub[cfo.role]
        team = [w for w in workers if w.parent == cfo.role]
        step = 360 / len(team)
        # Aim the gap at Irina, so no worker sits on the hub-to-Irina line.
        start = math.degrees(math.atan2(iy - hy, ix - hx)) + step / 2
        p.append(f'<circle cx="{hx:.0f}" cy="{hy:.0f}" r="{R}" fill="none" '
                 f'stroke="{SOFT}" stroke-width="1.6" stroke-dasharray="7 6"/>')
        for i, _worker in enumerate(team):
            wx, wy = polar(hx, hy, R, start + i * step)
            p.append(f'<line x1="{hx:.0f}" y1="{hy:.0f}" x2="{wx:.0f}" y2="{wy:.0f}" '
                     f'stroke="{SOFT}" stroke-width="1.6"/>')
            p.append(f'<circle cx="{wx:.0f}" cy="{wy:.0f}" r="{DOT}" fill="#FFFFFF" '
                     f'stroke="{EDGE}" stroke-width="1.8"/>')
        lines = wrap(cfo.title, 24)
        first = hy - HUB_H / 2 + 24
        p.append(f'<rect x="{hx - HUB_W / 2:.0f}" y="{hy - HUB_H / 2:.0f}" width="{HUB_W}" '
                 f'height="{HUB_H}" rx="9" fill="#EAF2FB" stroke="{BLUE}" stroke-width="1.5"/>')
        for i, line in enumerate(lines):
            p.append(f'<text x="{hx:.0f}" y="{first + i * 15:.0f}" text-anchor="middle" '
                     f'font-size="12" font-weight="700" fill="{BLUE}">{esc(line)}</text>')
        p.append(f'<text x="{hx:.0f}" y="{hy + HUB_H / 2 + 22:.0f}" text-anchor="middle" '
                 f'font-size="11.5" fill="{GREY}">{len(team)} workers</text>')

    p.append(f'<rect x="{ix - IRINA_W / 2:.0f}" y="{iy - IRINA_H / 2:.0f}" width="{IRINA_W}" '
             f'height="{IRINA_H}" rx="11" fill="{NAVY}" stroke="{NAVY}"/>')
    p.append(f'<text x="{ix:.0f}" y="{iy - 4:.0f}" text-anchor="middle" font-size="19" '
             f'font-weight="700" fill="#FFFFFF">Irina</text>')
    p.append(f'<text x="{ix:.0f}" y="{iy + 20:.0f}" text-anchor="middle" font-size="12" '
             f'fill="#9CC0E8">Chief Model Risk Officer</text>')

    # the legend, carrying what the old ASCII table said
    p.append(f'<line x1="56" y1="{LEGEND_Y - 26}" x2="{W - 56}" y2="{LEGEND_Y - 26}" '
             f'stroke="{SOFT}" stroke-width="1.4"/>')
    rows = [
        ("ring 0", "Irina", "the chief model risk officer", NAVY),
        ("ring 1", "4 CFOs", "development &#183; validation &#183; governance &#183; audit", BLUE),
        ("ring 2", "19 workers", "five (or four) to a team, on waku&#8217;s building blocks", AMBER),
    ]
    x = 56
    for ring, who, what, ink in rows:
        p.append(f'<text x="{x}" y="{LEGEND_Y + 10}" font-size="12" font-weight="700" '
                 f'fill="{ink}" letter-spacing="0.6">{ring.upper()}</text>')
        p.append(f'<text x="{x + 64}" y="{LEGEND_Y + 10}" font-size="16" font-weight="700" '
                 f'fill="{NAVY}">{who}</text>')
        p.append(f'<text x="{x + 64}" y="{LEGEND_Y + 32}" font-size="12" fill="{GREY}">'
                 f'{what}</text>')
        x += 500

    p.append("</svg>")
    return "\n".join(p)


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "docs" / "department.svg"
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
