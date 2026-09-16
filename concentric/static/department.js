// The department chart — 24 seats on three concentric rings, live.
//
// Served by `python -m concentric.dashboard` at /department.js and injected into
// waku's shell by the launcher. It adds ONE rail item and ONE view; waku's files
// on disk are never touched, so the stock dashboard and its tests are unaffected.
//
// It reuses waku's globals (VIEWS, esc, uiCard, hot) and its design tokens, and
// its live animation follows the same rule as diagram.js: the trace stream drives
// it, so a turn started in the CLI or the dock beats here too.
(function () {
  const ARC = 88;              // the slice of the outer ring one team owns
  const R1 = 155, R2 = 330;    // the CFO ring and the worker ring
  const W = 940, H = 900;
  const BEAT_MS = 1200;

  const polar = (cx, cy, r, deg) => {
    const a = (deg * Math.PI) / 180;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };

  const CSS = `
  .dep-wrap{display:flex;justify-content:center}
  .dep{width:100%;max-width:940px;height:auto}
  .dep-ring{fill:none;stroke:var(--border,#dce6f2);stroke-width:1.4}
  .dep-ring-cfo{stroke:var(--warn,#b36b00);stroke-dasharray:8 6;opacity:.45}
  .dep-arc{fill:none;stroke:var(--warn,#b36b00);stroke-width:2;stroke-dasharray:8 6;opacity:.5}
  .dep-edge{stroke:var(--border,#9dc2e8);stroke-width:1.1}
  .dep-edge.live{stroke:var(--accent,#2e6db4);stroke-width:2.6}
  .dep-node rect{fill:var(--surface,#fff);stroke:var(--border,#2e6db4);stroke-width:1.3;
    transform-box:fill-box;transform-origin:center}
  .dep-node text{font-size:11px;fill:var(--text,#0a1b3a);font-family:inherit;pointer-events:none}
  .dep-r0 rect{fill:var(--accent,#1e4e8c)}
  .dep-r0 text{fill:#fff;font-weight:700;font-size:12.5px}
  .dep-r1 rect{fill:var(--accent-soft,#eaf2fb);stroke:var(--accent,#1e4e8c)}
  .dep-node.cold rect{opacity:.4}
  .dep-node.hot rect{stroke-width:3;animation:dep-beat .55s ease-in-out 3}
  @keyframes dep-beat{0%,100%{transform:scale(1)}50%{transform:scale(1.12)}}
  .dep-legend{display:flex;gap:var(--space-4);flex-wrap:wrap;margin-top:var(--space-3)}
  .dep-key{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted,#5a6b80)}
  .dep-swatch{width:14px;height:10px;border-radius:3px;border:1.3px solid var(--border,#2e6db4)}
  `;

  function style() {
    if (document.getElementById("dep-style")) return;
    const el = document.createElement("style");
    el.id = "dep-style";
    el.textContent = CSS;
    document.head.appendChild(el);
  }

  function layout(dep) {
    const cx = W / 2, cy = H / 2;
    const pos = {};
    dep.seats.forEach((s) => {
      pos[s.role] = s.ring === 0
        ? [cx, cy]
        : polar(cx, cy, s.ring === 1 ? R1 : R2, s.angle || 0);
    });
    return { cx, cy, pos };
  }

  function departmentSVG(dep) {
    const { cx, cy, pos } = layout(dep);
    const p = [];

    p.push(`<circle class="dep-ring" cx="${cx}" cy="${cy}" r="${R2}"/>`);
    p.push(`<circle class="dep-ring dep-ring-cfo" cx="${cx}" cy="${cy}" r="${R1}"/>`);

    dep.seats.filter((s) => s.ring === 1).forEach((cfo) => {
      const [x0, y0] = polar(cx, cy, R2, cfo.angle - ARC / 2);
      const [x1, y1] = polar(cx, cy, R2, cfo.angle + ARC / 2);
      p.push(`<path class="dep-arc" d="M${x0},${y0} A${R2},${R2} 0 0 1 ${x1},${y1}"/>`);
    });

    dep.edges.forEach((e) => {
      const a = pos[e.src], b = pos[e.dst];
      if (!a || !b) return;
      p.push(`<line class="dep-edge" data-src="${e.src}" data-dst="${e.dst}" `
        + `x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"/>`);
    });

    dep.seats.forEach((s) => {
      const [x, y] = pos[s.role];
      const w = s.ring === 0 ? 190 : s.ring === 1 ? 180 : 152;
      const h = s.ring === 0 ? 56 : s.ring === 1 ? 46 : 28;
      const cls = `dep-node dep-r${s.ring} ${s.built ? "built" : "cold"}`;
      p.push(`<g class="${cls}" data-node="${s.role}" `
        + `transform="translate(${x - w / 2},${y - h / 2})">`
        + `<rect width="${w}" height="${h}" rx="9"/>`
        + `<text x="${w / 2}" y="${h / 2 + 4}" text-anchor="middle">${esc(s.title)}</text>`
        + `</g>`);
    });

    return `<div class="dep-wrap"><svg class="dep" viewBox="0 0 ${W} ${H}" role="img"`
      + ` aria-label="The department: ${dep.seats.length} seats on three concentric rings">`
      + `${p.join("")}</svg></div>`;
  }

  function legend() {
    return `<div class="dep-legend">`
      + `<span class="dep-key"><i class="dep-swatch" style="background:var(--accent,#1e4e8c)"></i>Irina - ring 0</span>`
      + `<span class="dep-key"><i class="dep-swatch" style="background:var(--accent-soft,#eaf2fb)"></i>CFO - ring 1</span>`
      + `<span class="dep-key"><i class="dep-swatch"></i>worker - ring 2</span>`
      + `<span class="dep-key">solid line = delegation, one level down</span>`
      + `<span class="dep-key">amber dash = a round table (peers)</span>`
      + `</div>`;
  }

  // ---- live: a seat beats while it is working, and its outgoing edge lights.
  // We repaint from a map instead of toggling classes directly, because the
  // dashboard re-renders the view on its 5s refresh and that would wipe a class
  // set by a plain setTimeout.
  const active = new Map();     // role -> expiry (ms since epoch)

  function paint() {
    const now = Date.now();
    const live = (role) => (active.get(role) || 0) > now;
    document.querySelectorAll(".dep-node").forEach((el) => {
      el.classList.toggle("hot", live(el.getAttribute("data-node")));
    });
    document.querySelectorAll(".dep-edge").forEach((el) => {
      el.classList.toggle("live", live(el.getAttribute("data-src")));
    });
  }

  function beat(ev) {
    if (ev && ev.role) active.set(ev.role, Date.now() + BEAT_MS);
  }

  let cursor = null;
  async function poll() {
    if ((location.hash || "").slice(1).split("/")[0] !== "department") return;
    try {
      const r = await (await fetch("/api/events" + (cursor == null ? "" : "?cursor=" + cursor))).json();
      if (cursor != null) r.events.forEach(beat);
      cursor = r.cursor;
      paint();
    } catch (e) { /* server busy */ }
  }

  style();
  setInterval(poll, 1000);
  setInterval(paint, 300);

  VIEWS.department = (d) => {
    const dep = d.department;
    const head = `<div class="meta" style="margin-bottom:var(--space-3)">Twenty-four seats on three
      rings: Irina at the centre, the four CFOs on the inner round table, nineteen workers on the
      outer. A seat <b>beats</b> while it is working and the edge lights as a delegation fires -
      driven by the trace, so a turn started in the CLI or the dock animates here too.</div>`;
    if (!dep) return head + uiCard(`<span class="empty">no department payload</span>`);
    const built = dep.seats.filter((s) => s.built).length;
    const edges = dep.edges.length;
    setTimeout(paint, 0);   // re-apply beats after this render replaces the DOM
    return head + departmentSVG(dep) + legend()
      + uiCard(`<div class="meta">${built} of ${dep.seats.length} seats have run &middot;
        ${edges} delegation edges. Grey = never used.</div>`);
  };
})();
