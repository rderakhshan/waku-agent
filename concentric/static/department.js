// The department — a force-directed graph, live.
//
// Served by `python -m concentric.dashboard` at /department.js and injected into
// waku's shell by the launcher. One rail item, one view; waku's files are never
// touched.
//
// The layout is the one an Obsidian graph uses: nodes push each other apart,
// edges pull their ends together, and the picture settles into whatever shape
// that produces. Nothing is placed on a ring or a grid, so the department does
// not come out symmetric — teams cluster because their edges are denser, which
// is a fact about the graph rather than a decision about the drawing.
//
// Two things it must keep:
//   1. DETERMINISM. main.js re-renders #view every 5s. A layout seeded from
//      Math.random would reshuffle the graph under the reader's eyes, so every
//      position comes from a hash of the seat's own role, and the result is
//      cached until the set of seats changes.
//   2. THE VIEW. Same reason: the zoom and pan live in module state and are
//      re-applied to each new SVG, so a refresh does not throw the reader back
//      to the whole graph.
//
// Every seat IS a Waku, so every seat runs the same inner flow. Each block holds
// a compact version of it - gate, llm, tool, out - and the part that is working
// beats. It is NOT archSVG: archSVG's ids are global and its animation selects
// them globally, so 24 copies would light all 24 at once. These parts are scoped
// by data-seat, so only the working seat beats.
(function () {
  // node sizes by ring: Irina, CFO (hub), worker. Sized for the names they
  // carry rather than to fit a grid.
  const NODE = { 0: [345, 138], 1: [309, 116], 2: [252, 104] };
  const PART_W = 51, PART_H = 30, PART_GAP = 8;
  const TITLE = { 0: 22.5, 1: 18, 2: 16.5 };

  const BEAT_MS = 1400;
  const PAD = 40;                 // breathing room around the fitted graph
  // Below this scale the names stop being readable. A fit that would go under it
  // is clamped instead: the whole graph stays a pan away, but the view the
  // reader lands on always has legible text.
  const MIN_SCALE = 0.62;

  // The four stages drawn inside every seat, left to right, each mapped to the
  // trace event that lights it — the same idea as diagram.js's STAGE map.
  const PARTS = [
    { key: "gate", label: "gate" },
    { key: "llm", label: "llm" },
    { key: "tool", label: "tool" },
    { key: "out", label: "out" },
  ];
  const EVENT_PART = { gate: "gate", llm: "llm", tool: "tool", turn_end: "out" };

  const CSS = `
  .dep-wrap{position:relative}
  .dep{display:block;width:100%;height:84vh;min-height:520px;
    font-family:"ING Me","Instrument Sans","Segoe UI",Helvetica,Arial,sans-serif;
    cursor:grab;touch-action:none}
  .dep.panning{cursor:grabbing}
  .dep-edge{stroke:var(--border,#9dc2e8);stroke-width:1.4;fill:none}
  .dep-edge.live{stroke:var(--warn,#b36b00);stroke-width:3}
  .dep-peer{stroke:var(--border,#9dc2e8);stroke-width:1;stroke-dasharray:4 4;opacity:.3}
  .dep-peer.live{stroke:var(--warn,#b36b00);stroke-width:2.6;stroke-dasharray:none;opacity:1}
  .dep-card{fill:var(--surface,#fff);stroke:var(--border,#2e6db4);stroke-width:1.6}
  .dep-r0 .dep-card{fill:var(--accent,#1e4e8c);stroke:#0a1b3a}
  .dep-r1 .dep-card{fill:var(--accent-soft,#eaf2fb);stroke:var(--accent,#1e4e8c)}
  .dep-title{fill:var(--text,#0a1b3a);font-family:inherit;pointer-events:none}
  .dep-r0 .dep-title{fill:#fff;font-weight:700}
  .dep-r1 .dep-title{font-weight:700;fill:var(--accent,#1e4e8c)}
  .dep-node.cold .dep-card{opacity:.42}
  .dep-node.cold .dep-title{opacity:.55}
  .dep-part rect{fill:var(--surface,#fff);stroke:var(--border,#9dc2e8);stroke-width:1.2;
    transform-box:fill-box;transform-origin:center}
  .dep-part text{fill:var(--muted,#5a6b80);font-family:inherit;pointer-events:none}
  .dep-r0 .dep-part rect{fill:#2a63a8;stroke:#7fa8d6}
  .dep-r0 .dep-part text{fill:#dbe8f7}
  .dep-part.hot rect{fill:var(--warn,#b36b00);stroke:var(--warn,#b36b00);
    animation:dep-beat .55s ease-in-out 3}
  .dep-part.hot text{fill:#fff;font-weight:700}
  .dep-node.beat .dep-card{stroke-width:4}
  .dep-node{cursor:pointer}
  .dep-bar{display:flex;align-items:center;gap:var(--space-3);margin-top:var(--space-2)}
  .dep-hint{font-size:var(--text-xs);color:var(--text-faint)}
  .dep-zoom{margin-left:auto;display:flex;gap:2px;
    border:var(--rule-width) solid var(--rule);border-radius:10px;overflow:hidden;
    background:var(--surface-paper);box-shadow:var(--shadow-sm)}
  .dep-zoom button{border:0;background:transparent;color:var(--text-muted);cursor:pointer;
    font-family:var(--face-mono);font-size:var(--text-xs);font-weight:600;
    padding:6px 12px;line-height:1;transition:background var(--motion-fast) var(--motion-ease),
    color var(--motion-fast) var(--motion-ease)}
  .dep-zoom button:hover{background:color-mix(in srgb,var(--accent) 16%,transparent);color:var(--text-ink)}
  .dep-zoom button + button{border-left:var(--rule-width) solid var(--rule)}
  .dep-legend{display:flex;gap:var(--space-4);flex-wrap:wrap;margin-top:var(--space-3)}
  .dep-key{display:flex;align-items:center;gap:6px;font-size:var(--text-xs);color:var(--muted,#5a6b80)}
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

  function wrap(text, max) {
    const words = String(text).split(" ");
    const lines = [];
    let cur = "";
    words.forEach((w) => {
      if (!cur) { cur = w; return; }
      if ((cur + " " + w).length <= max) cur += " " + w;
      else { lines.push(cur); cur = w; }
    });
    if (cur) lines.push(cur);
    return lines.length > 2 ? [lines[0], lines.slice(1).join(" ")] : lines;
  }

  // The point where the line centre -> target crosses the node's rectangle, so
  // an edge starts and ends on the card edge instead of under it.
  function edgePoint(cx, cy, hw, hh, tx, ty) {
    const dx = tx - cx, dy = ty - cy;
    if (!dx && !dy) return [cx, cy];
    const sx = dx ? hw / Math.abs(dx) : Infinity;
    const sy = dy ? hh / Math.abs(dy) : Infinity;
    const s = Math.min(sx, sy);
    return [cx + dx * s, cy + dy * s];
  }

  // ---- a deterministic seed per seat. FNV-1a over the role, so a role always
  // starts in the same place and the settled graph is the same on every render.
  function seedOf(role) {
    let h = 2166136261;
    for (let i = 0; i < role.length; i += 1) {
      h ^= role.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0) / 4294967296;
  }

  // ---- the layout: a force simulation, then a settle. No library — 24 nodes
  // and ~65 edges do not need one, and this file may not have dependencies.
  let cache = { key: "", result: null };

  function simulate(dep) {
    const links = dep.edges.map((e) => [e.src, e.dst, 235, 0.9]);
    peerPairs(dep).forEach(([a, b]) => links.push([a, b, 150, 0.22]));

    const nodes = dep.seats.map((s, i) => {
      const r = seedOf(s.role);
      const a = (i / dep.seats.length) * Math.PI * 2 + r * 1.4;
      const rad = s.ring === 0 ? 0 : 260 + r * 260;
      const [w, h] = NODE[s.ring];
      return { role: s.role, ring: s.ring, w, h,
               x: Math.cos(a) * rad, y: Math.sin(a) * rad, vx: 0, vy: 0 };
    });
    const by = {};
    nodes.forEach((n) => { by[n.role] = n; });
    const springs = links.map(([a, b, len, k]) => [by[a], by[b], len, k])
      .filter((l) => l[0] && l[1]);

    const REP = 380000, DAMP = 0.82, STEPS = 420;
    // The panel is wider than it is tall, so the graph is laid out wider than it
    // is tall too: vertical repulsion is damped and the separation pass below is
    // what stops the cards piling up. A square blob in a wide panel is what made
    // the whole-graph view unreadable — fitting it meant zooming out until the
    // names were gone.
    const WIDE = 0.45;
    for (let step = 0; step < STEPS; step += 1) {
      const cool = 1 - step / STEPS;

      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i], b = nodes[j];
          const dx = b.x - a.x, dy = b.y - a.y;
          const d2 = dx * dx + dy * dy || 1;
          const d = Math.sqrt(d2);
          const f = REP / d2;
          const fx = (dx / d) * f, fy = (dy / d) * f * WIDE;
          a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
        }
      }

      springs.forEach(([a, b, len, k]) => {
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const f = (d - len) * k * 0.02;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
      });

      nodes.forEach((n) => {
        // Irina is held near the middle; everyone else only drifts back.
        const pull = n.ring === 0 ? 0.14 : 0.035;
        n.vx -= n.x * pull; n.vy -= n.y * pull;
        n.x += n.vx * cool; n.y += n.vy * cool;
        n.vx *= DAMP; n.vy *= DAMP;
      });

      // Separate rectangles last, so the settle cannot leave cards overlapping.
      for (let pass = 0; pass < 2; pass += 1) {
        for (let i = 0; i < nodes.length; i += 1) {
          for (let j = i + 1; j < nodes.length; j += 1) {
            const a = nodes[i], b = nodes[j];
            const dx = b.x - a.x, dy = b.y - a.y;
            const ox = (a.w + b.w) / 2 + 14 - Math.abs(dx);
            const oy = (a.h + b.h) / 2 + 14 - Math.abs(dy);
            if (ox <= 0 || oy <= 0) continue;
            if (ox < oy) {
              const s = (dx >= 0 ? 1 : -1) * ox * 0.5;
              a.x -= s; b.x += s;
            } else {
              const s = (dy >= 0 ? 1 : -1) * oy * 0.5;
              a.y -= s; b.y += s;
            }
          }
        }
      }
    }
    return { nodes, by };
  }

  function layout(dep) {
    const key = dep.seats.map((s) => `${s.role}:${s.built ? 1 : 0}`).join("|");
    if (cache.key !== key) cache = { key, result: simulate(dep) };
    return cache.result;
  }

  function innerFlow(w, h, ring) {
    const total = PARTS.length * PART_W + (PARTS.length - 1) * PART_GAP;
    const x0 = (w - total) / 2;
    const y = h - PART_H - 12;
    return PARTS.map((p, i) => {
      const x = x0 + i * (PART_W + PART_GAP);
      return `<g class="dep-part" data-part="${p.key}">`
        + `<rect x="${x}" y="${y}" width="${PART_W}" height="${PART_H}" rx="7"/>`
        + `<text x="${x + PART_W / 2}" y="${y + PART_H / 2 + 5}" text-anchor="middle" `
        + `font-size="${ring === 0 ? 16 : 15}">${p.label}</text>`
        + `</g>`;
    }).join("");
  }

  function card(s, x, y) {
    const [w, h] = NODE[s.ring];
    const cls = `dep-node dep-r${s.ring} ${s.built ? "built" : "cold"}`;
    const max = s.ring === 0 ? 26 : s.ring === 1 ? 22 : 19;
    const size = TITLE[s.ring];
    const lines = wrap(s.title, max);
    const step = size + 5;
    const flowTop = h - PART_H - 12;
    const first = lines.length > 1
      ? flowTop / 2 - step / 2 + size * 0.35
      : flowTop / 2 + size * 0.35;
    const title = lines.map((ln, i) =>
      `<text class="dep-title" x="${w / 2}" y="${first + i * step}" text-anchor="middle" `
      + `font-size="${size}">${esc(ln)}</text>`).join("");
    return `<g class="${cls}" data-seat="${s.role}" `
      + `transform="translate(${x - w / 2},${y - h / 2})">`
      + `<rect class="dep-card" width="${w}" height="${h}" rx="13"/>`
      + title + innerFlow(w, h, s.ring)
      + `</g>`;
  }

  // The lateral edges the roster already implies: every pair at one round table
  // — the four CFOs, and each team's workers among themselves. The roster's
  // `peers()` is the same rule, and it is what each seat's consult_peer enum
  // contains, so the picture cannot claim a channel the graph does not have.
  function peerPairs(dep) {
    const out = [];
    const pairs = (group) => {
      for (let i = 0; i < group.length; i += 1) {
        for (let j = i + 1; j < group.length; j += 1) {
          out.push([group[i].role, group[j].role]);
        }
      }
    };
    pairs(dep.seats.filter((s) => s.ring === 1));
    const byTeam = {};
    dep.seats.filter((s) => s.ring === 2).forEach((s) => {
      (byTeam[s.parent] = byTeam[s.parent] || []).push(s);
    });
    Object.values(byTeam).forEach(pairs);
    return out;
  }

  // ---- the view. Module state, so a 5s re-render keeps the reader's zoom.
  let view = null;

  function bounds(nodes) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    nodes.forEach((n) => {
      x0 = Math.min(x0, n.x - n.w / 2); y0 = Math.min(y0, n.y - n.h / 2);
      x1 = Math.max(x1, n.x + n.w / 2); y1 = Math.max(y1, n.y + n.h / 2);
    });
    return { x0, y0, x1, y1 };
  }

  function fit(svg, nodes) {
    const b = bounds(nodes);
    let w = (b.x1 - b.x0) + PAD * 2;
    let h = (b.y1 - b.y0) + PAD * 2;
    const box = svg && svg.getBoundingClientRect();
    if (box && box.width && box.height) {
      const scale = Math.min(box.width / w, box.height / h);
      if (scale < MIN_SCALE) {
        const k = MIN_SCALE / scale;
        w *= k;
        h *= k;
      }
    }
    view = { x: (b.x0 + b.x1) / 2 - w / 2, y: (b.y0 + b.y1) / 2 - h / 2, w, h };
  }

  function paintView(svg) {
    if (!svg || !view) return;
    svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
  }

  function zoomAt(svg, factor, fx, fy) {
    const next = Math.max(view.w / 12, Math.min(view.w * 6, view.w * factor));
    const k = next / view.w;
    view.x += (view.w - next) * fx;
    view.y += (view.h - view.h * k) * fy;
    view.w = next;
    view.h *= k;
    paintView(svg);
  }

  function attachZoom(svg, nodes) {
    if (!svg) return;
    if (!view) fit(svg, nodes);
    paintView(svg);

    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      zoomAt(svg, Math.exp(e.deltaY * 0.0012),
             (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
    }, { passive: false });

    let drag = null;
    svg.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      drag = { x: e.clientX, y: e.clientY };
      svg.classList.add("panning");
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const r = svg.getBoundingClientRect();
      view.x -= (e.clientX - drag.x) * (view.w / r.width);
      view.y -= (e.clientY - drag.y) * (view.h / r.height);
      drag = { x: e.clientX, y: e.clientY };
      paintView(svg);
    });
    const stop = (e) => {
      drag = null;
      svg.classList.remove("panning");
      try { svg.releasePointerCapture(e.pointerId); } catch (err) { /* already gone */ }
    };
    svg.addEventListener("pointerup", stop);
    svg.addEventListener("pointercancel", stop);
  }

  function zoomBar() {
    return `<div class="dep-bar">
      <span class="dep-hint">drag to pan &middot; scroll to zoom &middot; click a seat to
        open its panel</span>
      <div class="dep-zoom">
        <button type="button" data-zoom="in" title="Zoom in">+</button>
        <button type="button" data-zoom="out" title="Zoom out">-</button>
        <button type="button" data-zoom="fit" title="Fit the whole graph">fit</button>
      </div></div>`;
  }

  function wireZoomBar(nodes) {
    const svg = document.querySelector("svg.dep");
    if (!svg) return;
    document.querySelectorAll(".dep-zoom button").forEach((b) => {
      b.onclick = () => {
        const how = b.getAttribute("data-zoom");
        if (how === "fit") { fit(svg, nodes); paintView(svg); return; }
        zoomAt(svg, how === "in" ? 1 / 1.35 : 1.35, 0.5, 0.5);
      };
    });
  }

  function departmentSVG(dep) {
    const L = layout(dep);
    const p = [];
    const seatBy = (role) => dep.seats.find((s) => s.role === role);
    const at = (role) => L.by[role];

    // lateral edges first, so the delegation edges draw on top of them
    peerPairs(dep).forEach(([a, b]) => {
      const pa = at(a), pb = at(b);
      if (!pa || !pb) return;
      const [x0, y0] = edgePoint(pa.x, pa.y, pa.w / 2, pa.h / 2, pb.x, pb.y);
      const [x1, y1] = edgePoint(pb.x, pb.y, pb.w / 2, pb.h / 2, pa.x, pa.y);
      p.push(`<line class="dep-edge dep-peer" data-src="${a}" data-dst="${b}" `
        + `x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" `
        + `y2="${y1.toFixed(1)}"/>`);
    });

    dep.edges.forEach((e) => {
      const pa = at(e.src), pb = at(e.dst);
      if (!pa || !pb) return;
      const [x0, y0] = edgePoint(pa.x, pa.y, pa.w / 2, pa.h / 2, pb.x, pb.y);
      const [x1, y1] = edgePoint(pb.x, pb.y, pb.w / 2, pb.h / 2, pa.x, pa.y);
      p.push(`<line class="dep-edge" data-src="${e.src}" data-dst="${e.dst}" `
        + `x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" `
        + `y2="${y1.toFixed(1)}"/>`);
    });

    dep.seats.forEach((s) => {
      const n = at(s.role);
      if (n) p.push(card(s, n.x, n.y));
    });

    // The viewBox is set by attachZoom after this markup lands, so the graph is
    // fitted to its own bounds rather than to a fixed canvas.
    return `<div class="dep-wrap"><svg class="dep" preserveAspectRatio="xMidYMid meet"`
      + ` role="img" aria-label="The department: ${dep.seats.length} seats and their edges"`
      + `>${p.join("")}</svg></div>` + zoomBar();
  }

  function legend() {
    return `<div class="dep-legend">`
      + `<span class="dep-key"><i class="dep-swatch" style="background:var(--accent,#1e4e8c)"></i>Irina</span>`
      + `<span class="dep-key"><i class="dep-swatch" style="background:var(--accent-soft,#eaf2fb)"></i>CFO</span>`
      + `<span class="dep-key"><i class="dep-swatch"></i>worker</span>`
      + `<span class="dep-key">every seat holds the same flow: gate - llm - tool - out</span>`
      + `<span class="dep-key">solid line = delegation, one level down</span>`
      + `<span class="dep-key">dashed line = peers; it lights when they consult</span>`
      + `</div>`;
  }

  // ---- live. Repaint from maps rather than toggling classes directly: the
  // dashboard re-renders the view on its 5s refresh, which would wipe a class
  // set by a plain setTimeout.
  const activePart = new Map();   // "<role>:<part>" -> expiry
  const activeSeat = new Map();   // "<role>"        -> expiry
  const activeEdge = new Map();   // "<src>><dst>"   -> expiry

  function paint() {
    const now = Date.now();
    const live = (m, k) => (m.get(k) || 0) > now;
    document.querySelectorAll(".dep-node").forEach((el) => {
      el.classList.toggle("beat", live(activeSeat, el.getAttribute("data-seat")));
    });
    document.querySelectorAll(".dep-part").forEach((el) => {
      const seat = el.closest(".dep-node").getAttribute("data-seat");
      el.classList.toggle("hot", live(activePart, seat + ":" + el.getAttribute("data-part")));
    });
    // Only the edge a tool call actually used lights — the hand-off, named. A
    // "the target is busy" rule would light every edge into that seat at once,
    // which for a peer mesh means five chords for one conversation.
    document.querySelectorAll(".dep-edge").forEach((el) => {
      const key = el.getAttribute("data-src") + ">" + el.getAttribute("data-dst");
      el.classList.toggle("live", live(activeEdge, key));
    });
  }

  function beat(ev) {
    if (!ev || !ev.role) return;
    const until = Date.now() + BEAT_MS;
    activeSeat.set(ev.role, until);
    const part = EVENT_PART[ev.type];
    if (part) activePart.set(ev.role + ":" + part, until);
    if (ev.type === "tool" && ev.args && ev.args.role) {
      activeEdge.set(ev.role + ">" + ev.args.role, until);
    }
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

  // ---- the panels are single-harness by design: they render waku's payload for
  // ONE home. collect.py hands them the department's aggregate, but two things
  // it adds have no home in those panels — the per-seat spend, and the seat each
  // row belongs to. So wrap the views and append a section: the same
  // "wrap, don't fork" move as Seat. waku's renderers are untouched.
  const kb = (n) => `${(n / 1024).toFixed(1)} KB`;

  function bySeatSpend(d) {
    const u = d.usage || {};
    const rows = u.by_seat || [];
    if (!rows.length) return "";
    const body = rows.map((b) => `<tr>
        <td><code>${esc(b.seat)}</code></td>
        <td class="meta">${b.calls || 0}</td>
        <td class="meta">${(b.in || 0).toLocaleString()}</td>
        <td class="meta">${(b.out || 0).toLocaleString()}</td>
        <td class="meta">${b.tool_calls || 0}</td>
        <td class="meta">${money(b.cost || 0)}</td></tr>`);
    return `<h2>Spend by seat</h2>
      <div class="meta" style="margin-bottom:var(--space-3)">${esc(u.note || "")}</div>
      ${table(["seat", "LLM calls", "tokens in", "tokens out", "tool calls", "cost"], body)}`;
  }

  function memoryBySeat(d) {
    const rows = (d.db && d.db.seats) || [];
    if (!rows.length) return "";
    const body = rows.map((r) => `<tr>
        <td><code>${esc(r.seat)}</code></td>
        <td class="meta">${r.facts || 0}</td>
        <td class="meta">${r.episodes || 0}</td>
        <td class="meta">${r.chat_log || 0}</td>
        <td class="meta">${kb(r.size || 0)}</td></tr>`);
    return `<h2>Memory by seat</h2>
      <div class="meta" style="margin-bottom:var(--space-3)">Each seat owns its own state.db.
        The tables above are the union of all of them; this is who owns what.</div>
      ${table(["seat", "facts", "episodes", "chat rows", "state.db"], body)}`;
  }

  function sessionsBySeat(d) {
    const rows = d.sessions || [];
    if (!rows.length) return "";
    const body = rows.map((s) => `<tr>
        <td><code>${esc(s.seat || "?")}</code></td>
        <td class="meta">${esc(s.title || s.id || "")}</td>
        <td class="meta">${s.messages || 0}</td>
        <td class="meta">${esc(s.last_at || "")}</td></tr>`);
    return `<h2>Conversations by seat</h2>
      <div class="meta" style="margin-bottom:var(--space-3)">Every seat keeps its own chat log.
        The inbox above is the union; this is which seat each thread belongs to.</div>
      ${table(["seat", "thread", "messages", "last"], body)}`;
  }

  function wrapView(name, extra) {
    const base = VIEWS[name];
    if (typeof base !== "function") return;
    VIEWS[name] = (d, sub) => base(d, sub) + extra(d, sub);
  }
  wrapView("ops", bySeatSpend);
  wrapView("memory", memoryBySeat);
  wrapView("gateway", sessionsBySeat);

  function seatsTable(dep) {
    const rows = dep.seats.filter((s) => s.built || s.activity);
    if (!rows.length) return "";
    const body = rows.map((s) => {
      const a = s.activity || {};
      return `<tr>
        <td><code>${esc(s.role)}</code></td>
        <td class="meta">${s.ring}</td>
        <td class="meta">${esc((s.tools || []).join(", "))}</td>
        <td class="meta">${a.calls || 0}</td>
        <td class="meta">${money(a.cost || 0)}</td></tr>`;
    });
    return `<h2>Seats that have run</h2>
      ${table(["seat", "ring", "tools", "LLM calls", "cost"], body)}`;
  }

  VIEWS.department = (d) => {
    const dep = d.department;
    const head = `<div class="meta" style="margin-bottom:var(--space-3)">Twenty-four seats on
      waku, laid out by force rather than by hand: nodes push each other apart, edges pull their
      ends together, and the teams cluster because their edges are denser. Every seat is a full
      waku agent, so every block holds the same inner flow -
      <b>gate - llm - tool - out</b> - and the part that is working <b>beats</b>.</div>`;
    if (!dep) return head + uiCard(`<span class="empty">no department payload</span>`);
    const built = dep.seats.filter((s) => s.built).length;
    const L = layout(dep);
    // After the DOM swaps in: re-apply the beats, and re-attach the view so a
    // refresh keeps the reader's zoom and pan.
    setTimeout(() => { paint(); attachZoom(document.querySelector("svg.dep"), L.nodes);
                       wireZoomBar(L.nodes); }, 0);
    return head + departmentSVG(dep) + legend()
      + uiCard(`<div class="meta">${built} of ${dep.seats.length} seats have run &middot;
        ${dep.edges.length} delegation edges. Grey = never used.</div>`)
      + seatsTable(dep);
  };
})();
