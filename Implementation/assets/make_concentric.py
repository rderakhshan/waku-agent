import io, math

W, H = 2240, 1810
NAVY = "#0A1B3A"
BLUE = "#1E4E8C"
EDGE = "#2E6DB4"
LIGHTSTROKE = "#9DC2E8"
AMBER = "#B36B00"
AMBERSTROKE = "#E8A33D"
RED = "#B02A2A"
GREY = "#5A6B80"
SOFT = "#8FB4DC"

parts = []
add = parts.append

def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def text(x, y, t, size=13, fill=NAVY, weight="normal", anchor="start", mono=False):
    fam = "Consolas, 'Courier New', monospace" if mono else "'Segoe UI', Arial, sans-serif"
    add('<text x="%s" y="%s" font-size="%s" fill="%s" font-weight="%s" '
        'text-anchor="%s" font-family="%s">%s</text>'
        % (x, y, size, fill, weight, anchor, fam, esc(t)))

def box(x, y, w, h, fill, stroke, rx=10, sw=1.6, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    add('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s" '
        'stroke="%s" stroke-width="%s"%s/>' % (x, y, w, h, rx, fill, stroke, sw, d))

def line(x1, y1, x2, y2, color, sw=1.4, dash=None, m1=None, m2=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    a = ' marker-start="url(#%s)"' % m1 if m1 else ""
    b = ' marker-end="url(#%s)"' % m2 if m2 else ""
    add('<path d="M%s,%s L%s,%s" fill="none" stroke="%s" stroke-width="%s"%s%s%s/>'
        % (x1, y1, x2, y2, color, sw, d, a, b))

def circle(cx, cy, r, stroke, sw=1.8, dash=None, fill="none"):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    add('<circle cx="%s" cy="%s" r="%s" fill="%s" stroke="%s" stroke-width="%s"%s/>'
        % (cx, cy, r, fill, stroke, sw, d))

def path(d, color, sw=1.8, dash=None, m1=None, m2=None):
    ds = ' stroke-dasharray="%s"' % dash if dash else ""
    a = ' marker-start="url(#%s)"' % m1 if m1 else ""
    b = ' marker-end="url(#%s)"' % m2 if m2 else ""
    add('<path d="%s" fill="none" stroke="%s" stroke-width="%s"%s%s%s/>'
        % (d, color, sw, ds, a, b))

add('<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s">' % (W, H, W, H))
add('<defs>')
for mid, col in (("arrow-blue", EDGE), ("arrow-amber", AMBER), ("arrow-red", RED),
                 ("arrow-soft", SOFT), ("arrow-soft-rev", SOFT)):
    add('<marker id="%s" markerWidth="9" markerHeight="7" refX="8.5" refY="3.5" orient="auto">'
        '<path d="M0,0 L9,3.5 L0,7 Z" fill="%s"/></marker>' % (mid, col))
for mid, col in (("arrow-blue-rev", EDGE), ("arrow-amber-rev", AMBER)):
    add('<marker id="%s" markerWidth="9" markerHeight="7" refX="0.5" refY="3.5" '
        'orient="auto-start-reverse"><path d="M9,0 L0,3.5 L9,7 Z" fill="%s"/></marker>' % (mid, col))
add('<linearGradient id="ceo" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0%" stop-color="#12305C"/><stop offset="100%" stop-color="#0A1B3A"/></linearGradient>')
add('<linearGradient id="cfo" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0%" stop-color="#2A63A8"/><stop offset="100%" stop-color="#1E4E8C"/></linearGradient>')
add('</defs>')
add('<rect width="%s" height="%s" fill="#F7F9FC"/>' % (W, H))

# header
add('<rect x="0" y="0" width="%s" height="112" fill="%s"/>' % (W, NAVY))
text(60, 50, "Irina's Department \u2014 Concentric Round Tables", 30, "#FFFFFF", "700")
text(60, 82, "circle 1: Irina \u00b7 circle 2: the four CFOs (they peer) \u00b7 circle 3: the workers "
             "(they peer inside their own team only)", 14, "#A8C4E4")
text(2180, 50, "24 seats", 26, "#7FA8D6", "700", "end")
text(2180, 78, "1 CEO \u00b7 4 CFOs \u00b7 19 workers", 13, "#A8C4E4", "normal", "end")

# anatomy strip
box(60, 126, 2120, 46, "#FFFFFF", LIGHTSTROKE, 8, 1.2)
text(78, 155, "NODE ANATOMY", 12, BLUE, "700")
x = 232
for k, v in (("SOUL.md", "the role's mandate"),
             ("ToolRegistry", "the capability it may use"),
             ("Settings", "its model & provider"),
             ("home/", "its own memory & traces")):
    text(x, 155, k, 12.5, NAVY, "700")
    text(x + 14 + len(k) * 7.5, 155, "\u2192 " + v, 12, GREY)
    x += 350

text(60, 212, "\u2460  THE DEPARTMENT  \u2014  three concentric circles", 17, NAVY, "700")

CX, CY = 820, 900
R1, R2 = 330, 640

CFO = [
    ("CFO-1 \u00b7 Development & ownership", -90,
     ["Model Owner", "Model Developer", "Data Steward", "Documentation Analyst", "MLOps Engineer"]),
    ("CFO-2 \u00b7 Validation & monitoring", 0,
     ["Conceptual-Soundness Validator", "Outcomes Analyst", "Ongoing-Monitoring Analyst",
      "Challenger Modeler", "Data-Quality Reviewer"]),
    ("CFO-3 \u00b7 Governance & reporting", 90,
     ["Inventory & Tiering Analyst", "Policy Analyst", "Model-Risk Reporting Analyst",
      "Findings & Remediation Manager", "Committee Secretary"]),
    ("CFO-4 \u00b7 Model audit", 180,
     ["Audit Planner", "Control Tester", "Evidence Analyst", "Audit Report Writer"]),
]
ARC = 88.0

def polar(r, deg):
    a = math.radians(deg)
    return CX + r * math.cos(a), CY + r * math.sin(a)

# circle 3 boundary + circle 2 (the CFO round table)
circle(CX, CY, R2, "#DCE6F2", 1.6, None, "#FBFDFF")
circle(CX, CY, R1, AMBERSTROKE, 1.8, "8 6", "#F1F7FD")

# team arcs on circle 3 = each team's own round table
geom = []
for (title, ang, members) in CFO:
    step = ARC / len(members)
    angles = [ang - ARC / 2 + step * (i + 0.5) for i in range(len(members))]
    cx_, cy_ = polar(R1, ang)
    geom.append((title, ang, members, angles, cx_, cy_))
    a0, a1 = math.radians(ang - ARC / 2), math.radians(ang + ARC / 2)
    x0, y0 = CX + R2 * math.cos(a0), CY + R2 * math.sin(a0)
    x1, y1 = CX + R2 * math.cos(a1), CY + R2 * math.sin(a1)
    path("M%.1f,%.1f A%s,%s 0 0 1 %.1f,%.1f" % (x0, y0, R2, R2, x1, y1), AMBER, 2.2, "8 6")

# CFO peer ticks on circle 2
for mid in (-45, 45, 135, 225):
    x0, y0 = polar(R1 - 14, mid)
    x1, y1 = polar(R1 + 14, mid)
    line(x0, y0, x1, y1, AMBER, 1.6, None, "arrow-amber-rev", "arrow-amber")

# edges: Irina -> CFO
for (title, ang, members, angles, cx_, cy_) in geom:
    line(CX, CY, cx_, cy_, EDGE, 2.2, None, None, "arrow-blue")
    line(CX, CY, cx_, cy_, EDGE, 1.2, "4 4", "arrow-blue-rev", None)

# edges: each worker -> its own CFO
for (title, ang, members, angles, cx_, cy_) in geom:
    for a in angles:
        wx, wy = polar(R2, a)
        line(wx, wy, cx_, cy_, SOFT, 1.1)

# the relayed cross-team example
relay = "M1460,900 L1150,900 C1150,718 1002,570 820,570 L820,260"
path(relay, RED, 2.0, "6 5")
text(1320, 942, "cross-team", 10, RED, "700", "middle")

# nodes: workers (circle 3)
for (title, ang, members, angles, cx_, cy_) in geom:
    for a, name in zip(angles, members):
        wx, wy = polar(R2, a)
        box(wx - 95, wy - 17, 190, 34, "#FFFFFF", EDGE, 8, 1.4)
        text(wx, wy + 4, name, 11, NAVY, "normal", "middle")

# nodes: CFOs (circle 2)
for (title, ang, members, angles, cx_, cy_) in geom:
    box(cx_ - 125, cy_ - 38, 250, 76, "url(#cfo)", "#12305C", 11)
    text(cx_, cy_ - 12, title, 11.5, "#FFFFFF", "700", "middle")
    text(cx_, cy_ + 6, "depth 1  \u00b7  waku node", 10.5, "#9CC0E8", "normal", "middle")
    text(cx_, cy_ + 24, "peers with the other 3 CFOs", 10, "#7FA8D6", "normal", "middle")

# node: Irina (circle 1)
box(CX - 140, CY - 46, 280, 92, "url(#ceo)", "#0A1B3A", 12)
text(CX, CY - 16, "Irina  \u00b7  CEO", 19, "#FFFFFF", "700", "middle")
text(CX, CY + 6, "depth 0  \u00b7  waku node", 11.5, "#9CC0E8", "normal", "middle")
text(CX, CY + 26, "talks to every CFO \u00b7 no peers", 10.5, "#7FA8D6", "normal", "middle")

# ring captions
text(537, 617, "ROUND TABLE \u00b7 DEPTH 1", 10.5, AMBER, "700", "middle")
for (title, ang, members, angles, cx_, cy_) in geom:
    st = ARC / len(members)
    ca = ang + (st / 2 if len(members) % 2 == 1 else 0)
    lx, ly = polar(R2 + 46, ca)
    text(lx, ly + 4, "ROUND TABLE \u00b7 DEPTH 2  \u00b7  %d workers" % len(members),
         10.5, AMBER, "700", "middle")

# notes
text(820, 1640, "workers peer inside their own team only \u2014 a validation worker cannot reach a development "
                "worker; the message goes up to their CFOs and back down", 12, GREY, "normal", "middle")
text(820, 1664, "\u2298 no skip-level and no cross-team edge: worker \u2194 worker (same team), "
                "worker \u2194 its CFO, CFO \u2194 CFO, CFO \u2194 Irina", 11.5, RED, "normal", "middle")

# legend
add('<line x1="60" y1="1700" x2="1560" y2="1700" stroke="#D6E0EC" stroke-width="1.4"/>')
text(60, 1732, "MESSAGE RULES", 12, BLUE, "700")
line(210, 1727, 270, 1727, EDGE, 2.2, None, None, "arrow-blue")
text(282, 1732, "Irina \u2194 CFO", 12, GREY)
line(430, 1727, 490, 1727, SOFT, 1.2, None, "arrow-soft-rev", "arrow-soft")
text(502, 1732, "worker \u2194 its CFO", 12, GREY)
line(680, 1727, 742, 1727, AMBER, 2.0, "8 6", "arrow-amber-rev", "arrow-amber")
text(754, 1732, "peer \u2014 inside one round table", 12, GREY)
line(1010, 1727, 1072, 1727, RED, 2.0, "6 5")
text(1084, 1732, "relayed cross-team message", 12, GREY)

# ---- right column: the prompt ----
PX, PW = 1640, 540
box(PX, 240, PW, 600, "#FFFFFF", LIGHTSTROKE, 10, 1.4)
text(PX + 20, 272, "PROMPT  \u2014  PSEUDO-CODE", 13, BLUE, "700")
code = [
    "DATA",
    "  CEO    = Irina            depth 0",
    "  CFOs   = 4 roles          depth 1",
    "  TEAM   = { cfo -> [w...] } depth 2",
    "",
    "PLACE  (concentric rings)",
    "  CEO    at centre",
    "  cfo    at polar(R1, cfo.angle)",
    "  worker at polar(R2,",
    "           cfo.angle - arc/2",
    "           + step*(i + 0.5))",
    "",
    "EDGES",
    "  CEO    <-> cfo        one level",
    "  worker <-> its cfo    one level",
    "  cfo    <-> cfo        circle 2",
    "  worker <-> worker     SAME team only",
    "",
    "FORBID",
    "  worker  -/- other team's worker",
    "  worker  -/- other cfo",
    "  worker  -/- CEO",
    "",
    "HIGHLIGHT",
    "  worker -> its cfo",
    "         -> the other cfo",
    "         -> that team's worker",
]
y = 302
for ln in code:
    col = AMBER if ln.strip() in ("DATA", "PLACE  (concentric rings)", "EDGES", "FORBID", "HIGHLIGHT") else NAVY
    wt = "700" if ln.strip() in ("DATA", "PLACE  (concentric rings)", "EDGES", "FORBID", "HIGHLIGHT") else "normal"
    text(PX + 20, y, ln, 11, col, wt, "start", mono=True)
    y += 20

box(PX, 870, PW, 250, "#FFFFFF", LIGHTSTROKE, 10, 1.4)
text(PX + 20, 902, "THE RULE IN ONE LINE", 13, BLUE, "700")
text(PX + 20, 934, "Vertical edges go exactly one level.", 12, NAVY)
text(PX + 20, 960, "Lateral edges exist only inside a round", 12, NAVY)
text(PX + 20, 982, "table: circle 2 for the CFOs, and one", 12, NAVY)
text(PX + 20, 1004, "per team on circle 3.", 12, NAVY)
text(PX + 20, 1040, "Everything else is relayed:", 12, NAVY)
text(PX + 20, 1062, "worker \u2192 its CFO \u2192 the other CFO \u2192", 12, RED, "700")
text(PX + 20, 1084, "that team's worker.", 12, RED, "700")

box(PX, 1150, PW, 220, "#FFFFFF", LIGHTSTROKE, 10, 1.4)
text(PX + 20, 1182, "WHY IT MATTERS", 13, BLUE, "700")
text(PX + 20, 1214, "The second line has no direct channel to", 12, NAVY)
text(PX + 20, 1236, "the first: a validation worker cannot", 12, NAVY)
text(PX + 20, 1258, "message a development worker.", 12, NAVY)
text(PX + 20, 1294, "Cross-team traffic is visible, because it", 12, NAVY)
text(PX + 20, 1316, "passes through two CFOs \u2014 and every hop", 12, NAVY)
text(PX + 20, 1338, "is a waku agent with its own memory.", 12, NAVY)

add('<rect x="0" y="1750" width="%s" height="60" fill="%s"/>' % (W, NAVY))
text(60, 1786, "RESPONSIBLE AI FOR A STRONGER FINANCIAL FUTURE", 13, "#7FA8D6", "700")
text(2180, 1786, "sketch \u00b7 concentric round tables \u00b7 waku agent as the node",
     12, "#5E86B8", "normal", "end")
add('</svg>')

html = ("<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:#F7F9FC;}</style></head>"
        "<body>" + "".join(parts) + "</body></html>")

out = r"C:\Users\Riemann\AppData\Local\Temp\opencode\irina-concentric.html"
with io.open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("ok", len(html))
