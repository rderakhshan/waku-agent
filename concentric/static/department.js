// The department chart — 24 seats on three concentric rings, each holding its
// own inner flow, live.
//
// Served by `python -m concentric.dashboard` at /department.js and injected into
// waku's shell by the launcher. One rail item, one view; waku's files are never
// touched.
//
// Every seat IS a Waku, so every seat runs the same internal flow. We draw a
// compact version of it inside each block — in -> gate -> llm -> tools -> out —
// and beat the part that is active. It is NOT archSVG: archSVG's ids are global
// and its live animation selects them globally, so 24 copies would light all 24
// at once. These parts are scoped by data-seat, so only the working seat beats.
(function () {
  const ARC = 88;                 // the slice of the outer ring one team owns
  const R1 = 300, R2 = 660;       // the CFO ring and the worker ring
  const W = 1640, H = 1640;
  const BEAT_MS = 1400;

  // The four stages drawn inside every seat, left to right. Each maps to the
  // trace event that lights it — the same idea as diagram.js's STAGE map.
  const PARTS = [
    { key: "gate", label: "gate" },
    { key: "llm", label: "llm" },
    { key: "tool", label: "tool" },
    { key: "out", label: "out" },
  ];
  const EVENT_PART = { gate: "gate", llm: "llm", tool: "tool", turn_end: "out" };

  const polar = (cx, cy, r, deg) => {
    const a = (deg * Math.PI) / 180;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };

  const SIZES = { 0: [260, 96], 1: [230, 84], 2: [190, 64] };

  const CSS = `
  .dep-wrap{display:flex;justify-content:center;overflow:auto}
  .dep{width:100%;min-width:1180px;max-width:1640px;height:auto}
  .dep-ring{fill:none;stroke:var(--border,#dce6f2);stroke-width:1.4}
  .dep-ring-cfo{stroke:var(--warn,#b36b00);stroke-dasharray:8 6;opacity:.45}
  .dep-arc{fill:none;stroke:var(--warn,#b36b00);stroke-width:2;stroke-dasharray:8 6;opacity:.5}
  .dep-edge{stroke:var(--border,#9dc2e8);stroke-width:1.2}
  .dep-edge.live{stroke:var(--accent,#2e6db4);stroke-width:3}
  .dep-card{fill:var(--surface,#fff);stroke:var(--border,#2e6db4);stroke-width:1.4}
  .dep-r0 .dep-card{fill:var(--accent,#1e4e8c);stroke:#0a1b3a}
  .dep-r1 .dep-card{fill:var(--accent-soft,#eaf2fb);stroke:var(--accent,#1e4e8c)}
  .dep-title{font-size:14px;fill:var(--text,#0a1b3a);font-family:inherit;pointer-events:none}
  .dep-r0 .dep-title{fill:#fff;font-weight:700}
  .dep-node.cold .dep-card{opacity:.42}
  .dep-part rect{fill:var(--surface,#fff);stroke:var(--border,#9dc2e8);stroke-width:1;
    transform-box:fill-box;transform-origin:center}
  .dep-part text{font-size:11px;fill:var(--muted,#5a6b80);font-family:inherit;pointer-events:none}
  .dep-r0 .dep-part rect{fill:#2a63a8;stroke:#7fa8d6}
  .dep-r0 .dep-part text{fill:#dbe8f7}
  .dep-part.hot rect{fill:var(--warn,#b36b00);stroke:var(--warn,#b36b00);
    animation:dep-beat .55s ease-in-out 3}
  .dep-part.hot text{fill:#fff;font-weight:700}
  .dep-node.beat .dep-card{stroke-width:3.4}
  .dep-legend{display:flex;gap:var(--space-4);flex-wrap:wrap;margin-top:var(--space-3)}
  .dep-key{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted,#5a6b80)}
  .dep-swatch{width:14px;height:10px;border-radius:3px;border:1.3px solid var(--border,#2e6db4)}
  @keyframes dep-beat{0%,100%{transform:scale(1)}50%{transform:scale(1.18)}}
  `;

  function style() {
    if (document.getElementById("dep-style")) return;
    const el = document.createElement("style");
    el.id = "dep-style";
    el.textContent = CSS;
    document.head.appendChild(el);
  }

  function positions(dep) {
    const cx = W / 2, cy = H / 2;
    const pos = {};
    dep.seats.forEach((s) => {
      pos[s.role] = s.ring === 0
        ? [cx, cy]
        : polar(cx, cy, s.ring === 1 ? R1 : R2, s.angle || 0);
    });
    return { cx, cy, pos };
  }

  // The inner flow: four stage boxes in a row, each carrying data-part so the
  // live layer can beat just that one.
  function innerFlow(ring, w, h) {
    const bw = 38, bh = 20, gap = 6;
    const total = PARTS.length * bw + (PARTS.length - 1) * gap;
    const x0 = (w - total) / 2;
    const y = h - bh - 10;
    return PARTS.map((p, i) => {
      const x = x0 + i * (bw + gap);
      return `<g class="dep-part" data-part="${p.key}">`
        + `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="5"/>`
        + `<text x="${x + bw / 2}" y="${y + bh / 2 + 4}" text-anchor="middle">${p.label}</text>`
        + `</g>`;
    }).join("");
  }

  function departmentSVG(dep) {
    const { cx, cy, pos } = positions(dep);
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
      const [w, h] = SIZES[s.ring];
      const cls = `dep-node dep-r${s.ring} ${s.built ? "built" : "cold"}`;
      p.push(`<g class="${cls}" data-seat="${s.role}" `
        + `transform="translate(${x - w / 2},${y - h / 2})">`
        + `<rect class="dep-card" width="${w}" height="${h}" rx="10"/>`
        + `<text class="dep-title" x="${w / 2}" y="24" text-anchor="middle">${esc(s.title)}</text>`
        + innerFlow(s.ring, w, h)
        + `</g>`);
    });

    return `<div class="dep-wrap"><svg class="dep" viewBox="0 0 ${W} ${H}" role="img"`
      + ` aria-label="The department: ${dep.seats.length} seats on three concentric rings,`
      + ` each holding its own flow">${p.join("")}</svg></div>`;
  }

  function legend() {
    return `<div class="dep-legend">`
      + `<span class="dep-key"><i class="dep-swatch" style="background:var(--accent,#1e4e8c)"></i>Irina - ring 0</span>`
      + `<span class="dep-key"><i class="dep-swatch" style="background:var(--accent-soft,#eaf2fb)"></i>CFO - ring 1</span>`
      + `<span class="dep-key"><i class="dep-swatch"></i>worker - ring 2</span>`
      + `<span class="dep-key">every seat holds the same flow: gate - llm - tool - out</span>`
      + `<span class="dep-key">the part that is working beats</span>`
      + `<span class="dep-key">solid line = delegation, one level down</span>`
      + `</div>`;
  }

  // ---- live. Repaint from maps rather than toggling classes directly: the
  // dashboard re-renders the view on its 5s refresh, which would wipe a class
  // set by a plain setTimeout.
  const activePart = new Map();   // "<role>:<part>" -> expiry
  const activeSeat = new Map();   // "<role>"        -> expiry

  function paint() {
    const now = Date.now();
    document.querySelectorAll(".dep-node").forEach((el) => {
      el.classList.toggle("beat", (activeSeat.get(el.getAttribute("data-seat")) || 0) > now);
    });
    document.querySelectorAll(".dep-part").forEach((el) => {
      const seat = el.closest(".dep-node").getAttribute("data-seat");
      const key = seat + ":" + el.getAttribute("data-part");
      el.classList.toggle("hot", (activePart.get(key) || 0) > now);
    });
    document.querySelectorAll(".dep-edge").forEach((el) => {
      el.classList.toggle("live", (activeSeat.get(el.getAttribute("data-src")) || 0) > now);
    });
  }

  function beat(ev) {
    if (!ev || !ev.role) return;
    const until = Date.now() + BEAT_MS;
    activeSeat.set(ev.role, until);
    const part = EVENT_PART[ev.type];
    if (part) activePart.set(ev.role + ":" + part, until);
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
      rings. Each seat is a full waku agent, so each block holds the same inner flow -
      <b>gate - llm - tool - out</b> - and the part that is working <b>beats</b>. Driven by the
      trace, so a turn started in the CLI or the dock animates here too.</div>`;
    if (!dep) return head + uiCard(`<span class="empty">no department payload</span>`);
    const built = dep.seats.filter((s) => s.built).length;
    setTimeout(paint, 0);   // re-apply beats after this render replaces the DOM
    return head + departmentSVG(dep) + legend()
      + uiCard(`<div class="meta">${built} of ${dep.seats.length} seats have run &middot;
        ${dep.edges.length} delegation edges. Grey = never used.</div>`);
  };
})();
