"""Generate docs/department.svg — the department poster.

    python -m concentric.make_poster

SVG rather than a raster image so the text is real text: every seat is named,
spelled correctly at any size, and the poster stays editable. GitHub renders it
in the README and scales it; click it for full size.

Composition: Irina between four wheels, each CFO the hub of its own circle, its
workers named on cards around the rim. Each team gets one colour, so the four
clusters read apart at a glance without the picture getting loud.

Placement lives here, not in the roster — the roster carries only `ring` and
`parent`. Keep to shapes, gradients and opacity: GitHub sanitises SVG, so no
filters, no <style>, no scripts, no external references.
"""

from __future__ import annotations

import math
from pathlib import Path

from concentric import roster

W, H = 1840, 1660
HEADER = 116
LEGEND_Y = 1520

INK = "#0A1B3A"
EDGE = "#2E6DB4"
GREY = "#5A6B80"
SOFT = "#DCE6F2"

R = 200                    # the worker circle around each hub
CARD_W, CARD_H = 158, 38
HUB_W, HUB_H = 210, 64
IRINA_W, IRINA_H = 268, 92
LABEL_R = 292              # where a worker card sits, measured from the hub

HUBS = [(470, 480), (1350, 480), (1350, 1160), (470, 1160)]   # clockwise
IRINA = (W / 2, 820)

# One colour per team: ink for strokes and fills, tint for the hub's wash.
TEAM = {
    "cfo-1-development": ("#1E4E8C", "#E8F0FA"),
    "cfo-2-validation": ("#0E7490", "#E2F2F5"),
    "cfo-3-governance": ("#B36B00", "#FBF0DF"),
    "cfo-4-audit": ("#6B4FA8", "#EFEAF9"),
}
FALLBACK = (EDGE, "#EAF2FB")


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


def card(x: float, y: float, w: float, h: float, lines: list[str], *,
         fill: str, stroke: str, ink: str, size: float, weight: str = "normal",
         radius: int = 9, opacity: float = 1.0) -> str:
    out = [(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" rx="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5" opacity="{opacity}"/>')]
    step = size + 3
    first = y + h / 2 - (len(lines) - 1) * step / 2 + size * 0.34
    for i, line in enumerate(lines):
        out.append(f'<text x="{x + w / 2:.0f}" y="{first + i * step:.0f}" '
                   f'text-anchor="middle" font-size="{size}" font-weight="{weight}" '
                   f'fill="{ink}">{esc(line)}</text>')
    return "".join(out)


def build() -> str:
    cfos = [s for s in roster.SEATS if s.ring == 1]
    workers = [s for s in roster.SEATS if s.ring == 2]
    hub = {c.role: HUBS[i % len(HUBS)] for i, c in enumerate(cfos)}
    ix, iy = IRINA

    p = [
        (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="\'ING Me\', \'Instrument Sans\', '
         f"'Segoe UI', Helvetica, Arial, sans-serif\">"),
        "<defs>",
        ('<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
         '<stop offset="0%" stop-color="#FCFDFF"/><stop offset="100%" stop-color="#EDF3FA"/>'
         "</linearGradient>"),
        ('<linearGradient id="irina" x1="0" y1="0" x2="1" y2="1">'
         '<stop offset="0%" stop-color="#16305C"/><stop offset="100%" stop-color="#0A1B3A"/>'
         "</linearGradient>"),
        ('<linearGradient id="head" x1="0" y1="0" x2="1" y2="0">'
         '<stop offset="0%" stop-color="#0A1B3A"/><stop offset="100%" stop-color="#1E4E8C"/>'
         "</linearGradient>"),
    ]
    for cfo in cfos:
        ink, tint = TEAM.get(cfo.role, FALLBACK)
        p.append(f'<linearGradient id="hub-{cfo.role}" x1="0" y1="0" x2="0" y2="1">'
                 f'<stop offset="0%" stop-color="{ink}"/>'
                 f'<stop offset="100%" stop-color="{ink}" stop-opacity="0.82"/></linearGradient>')
    p += [
        "</defs>",
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
        f'<rect width="{W}" height="{HEADER}" fill="url(#head)"/>',
        ('<text x="60" y="60" font-size="32" font-weight="700" fill="#FFFFFF">'
         'Irina&#8217;s Department</text>'),
        ('<text x="60" y="90" font-size="15" fill="#A8C4E4">'
         'AI-powered model risk management, built on waku-agent</text>'),
        (f'<text x="{W - 60}" y="60" text-anchor="end" font-size="26" font-weight="700" '
         f'fill="#7FA8D6">24 seats</text>'),
        (f'<text x="{W - 60}" y="90" text-anchor="end" font-size="14" fill="#A8C4E4">'
         f'1 chief model risk officer &#183; 4 CFOs &#183; 19 workers</text>'),
    ]

    # Irina -> each hub, drawn first so the cards sit on top
    for cfo in cfos:
        hx, hy = hub[cfo.role]
        p.append(f'<line x1="{ix:.0f}" y1="{iy + IRINA_H / 2:.0f}" x2="{hx:.0f}" '
                 f'y2="{hy - HUB_H / 2:.0f}" stroke="{EDGE}" stroke-width="2.6" opacity="0.75"/>')

    for cfo in cfos:
        ink, tint = TEAM.get(cfo.role, FALLBACK)
        hx, hy = hub[cfo.role]
        team = [w for w in workers if w.parent == cfo.role]
        step = 360 / len(team)
        # Aim the gap at Irina, so no worker sits on the hub-to-Irina line.
        start = math.degrees(math.atan2(iy - hy, ix - hx)) + step / 2

        p.append(f'<circle cx="{hx:.0f}" cy="{hy:.0f}" r="{R + 46}" fill="{tint}" '
                 f'opacity="0.55"/>')
        p.append(f'<circle cx="{hx:.0f}" cy="{hy:.0f}" r="{R}" fill="none" stroke="{ink}" '
                 f'stroke-width="1.8" stroke-dasharray="8 7" opacity="0.5"/>')

        for i, worker in enumerate(team):
            deg = start + i * step
            wx, wy = polar(hx, hy, R, deg)
            lx, ly = polar(hx, hy, LABEL_R, deg)
            p.append(f'<line x1="{hx:.0f}" y1="{hy:.0f}" x2="{wx:.0f}" y2="{wy:.0f}" '
                     f'stroke="{ink}" stroke-width="1.4" opacity="0.3"/>')
            p.append(f'<line x1="{wx:.0f}" y1="{wy:.0f}" x2="{lx:.0f}" y2="{ly:.0f}" '
                     f'stroke="{ink}" stroke-width="1.4" opacity="0.3"/>')
            p.append(f'<circle cx="{wx:.0f}" cy="{wy:.0f}" r="7" fill="#FFFFFF" '
                     f'stroke="{ink}" stroke-width="2"/>')
            p.append(card(lx - CARD_W / 2, ly - CARD_H / 2, CARD_W, CARD_H,
                          wrap(worker.title, 22), fill="#FFFFFF", stroke=ink,
                          ink=INK, size=10.5, radius=8))

        p.append(card(hx - HUB_W / 2, hy - HUB_H / 2, HUB_W, HUB_H,
                      wrap(cfo.title, 24), fill=f"url(#hub-{cfo.role})", stroke=ink,
                      ink="#FFFFFF", size=13, weight="700", radius=11))
        p.append(f'<text x="{hx:.0f}" y="{hy + HUB_H / 2 + 20:.0f}" text-anchor="middle" '
                 f'font-size="11.5" font-weight="700" fill="{ink}" opacity="0.85">'
                 f'{len(team)} workers</text>')

    p.append(card(ix - IRINA_W / 2, iy - IRINA_H / 2, IRINA_W, IRINA_H,
                  ["Irina", "Chief Model Risk Officer"], fill="url(#irina)", stroke="#0A1B3A",
                  ink="#FFFFFF", size=21, weight="700", radius=13))
    p.append(f'<text x="{ix:.0f}" y="{iy + IRINA_H / 2 + 24:.0f}" text-anchor="middle" '
             f'font-size="11.5" font-weight="700" fill="{GREY}" letter-spacing="0.5">'
             f'DELEGATES DOWN, ANSWERS UP</text>')

    # the legend, carrying what the old ASCII table said
    p.append(f'<line x1="60" y1="{LEGEND_Y - 30}" x2="{W - 60}" y2="{LEGEND_Y - 30}" '
             f'stroke="{SOFT}" stroke-width="1.4"/>')
    rows = [
        ("ring 0", "Irina", "the chief model risk officer", INK, 0),
        ("ring 1", "4 CFOs", "development &#183; validation &#183; governance &#183; audit",
         "#1E4E8C", 1),
        ("ring 2", "19 workers", "five (or four) to a team, on waku&#8217;s building blocks",
         "#B36B00", 2),
    ]
    x = 60
    for ring, who, what, ink, ring_index in rows:
        p.append(f'<circle cx="{x + 9}" cy="{LEGEND_Y + 4}" r="9" fill="none" stroke="{ink}" '
                 f'stroke-width="{1.6 + ring_index * 0.6}"/>')
        p.append(f'<text x="{x + 30}" y="{LEGEND_Y}" font-size="12" font-weight="700" '
                 f'fill="{ink}" letter-spacing="0.6">{ring.upper()}</text>')
        p.append(f'<text x="{x + 30}" y="{LEGEND_Y + 24}" font-size="17" font-weight="700" '
                 f'fill="{INK}">{who}</text>')
        p.append(f'<text x="{x + 30}" y="{LEGEND_Y + 46}" font-size="12" fill="{GREY}">'
                 f'{what}</text>')
        x += 580

    p.append(f'<text x="{W - 60}" y="{H - 26}" text-anchor="end" font-size="12" fill="{GREY}">'
             f'github.com/rderakhshan/waku-agent</text>')
    p.append("</svg>")
    return "\n".join(p)


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "docs" / "department.svg"
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
