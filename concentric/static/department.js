// The department — four wheels around Irina, live.
//
// Served by `python -m concentric.dashboard` at /department.js and injected into
// waku's shell by the launcher. One rail item, one view; waku's files are never
// touched. This file is the whole of the change: layout is the view's business,
// and the roster carries only `ring` and `parent`.
//
// Each CFO is the HUB of its own wheel - the centre of the circle its workers
// sit on - and one spoke runs from the hub out to each worker. Irina sits
// between the four wheels and reaches each hub. So the spoke that lights names
// the exact seat that is working.
//
// Every seat IS a Waku, so every seat runs the same inner flow. Each block holds
// a compact version of it - gate, llm, tool, out - and the part that is working
// beats. It is NOT archSVG: archSVG's ids are global and its animation selects
// them globally, so 24 copies would light all 24 at once. These parts are scoped
// by data-seat, so only the working seat beats.
(function () {
  // node sizes by ring: Irina, CFO (hub), worker
  const NODE = { 0: [230, 88], 1: [206, 74], 2: [168, 66] };

  const W = 1240, H = 1240;
  const RING_R = 160;                        // the worker circle around each hub
  const IRINA = [W / 2, H / 2];
  const HUBS = [[340, 340], [900, 340], [900, 900], [340, 900]];  // clockwise
  const BEAT_MS = 1400;

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
  .dep-wrap{display:flex;justify-content:center;overflow:auto}
  .dep{width:100%;min-width:900px;max-width:1240px;height:auto}
  .dep-wheel{fill:none;stroke:var(--border,#dce6f2);stroke-width:1.4;stroke-dasharray:6 6;
    opacity:.7}
  .dep-edge{stroke:var(--border,#9dc2e8);stroke-width:1.3;fill:none}
  .dep-edge.live{stroke:var(--warn,#b36b00);stroke-width:3}
  .dep-peer{stroke:var(--border,#9dc2e8);stroke-width:1;stroke-dasharray:4 4;opacity:.28}
  .dep-peer.live{stroke:var(--warn,#b36b00);stroke-width:2.6;stroke-dasharray:none;opacity:1}
  .dep-card{fill:var(--surface,#fff);stroke:var(--border,#2e6db4);stroke-width:1.4}
  .dep-r0 .dep-card{fill:var(--accent,#1e4e8c);stroke:#0a1b3a}
  .dep-r1 .dep-card{fill:var(--accent-soft,#eaf2fb);stroke:var(--accent,#1e4e8c)}
  .dep-title{font-size:11px;fill:var(--text,#0a1b3a);font-family:inherit;pointer-events:none}
  .dep-r0 .dep-title{font-size:15px;fill:#fff;font-weight:700}
  .dep-r1 .dep-title{font-size:12px;font-weight:700;fill:var(--accent,#1e4e8c)}
  .dep-node.cold .dep-card{opacity:.42}
  .dep-node.cold .dep-title{opacity:.55}
  .dep-part rect{fill:var(--surface,#fff);stroke:var(--border,#9dc2e8);stroke-width:1;
    transform-box:fill-box;transform-origin:center}
  .dep-part text{font-size:10px;fill:var(--muted,#5a6b80);font-family:inherit;pointer-events:none}
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

  // Long role names overflowed their card before. Wrap to at most two lines so
  // the title stays inside the box instead of bleeding across its neighbours.
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
  // a spoke starts and ends on the card edge instead of under it.
  function edgePoint(cx, cy, hw, hh, tx, ty) {
    const dx = tx - cx, dy = ty - cy;
    if (!dx && !dy) return [cx, cy];
    const sx = dx ? hw / Math.abs(dx) : Infinity;
    const sy = dy ? hh / Math.abs(dy) : Infinity;
    const s = Math.min(sx, sy);
    return [cx + dx * s, cy + dy * s];
  }

  // ---- layout. CFOs take the four hubs in roster order; each team's workers
  // sit on that hub's circle, rotated so the gap faces Irina.
  function layout(dep) {
    const cfos = dep.seats.filter((s) => s.ring === 1);
    const pos = {};
    const hubOf = {};

    pos[dep.entry] = IRINA;
    cfos.forEach((c, i) => {
      const [hx, hy] = HUBS[i % HUBS.length];
      hubOf[c.role] = [hx, hy];
      pos[c.role] = [hx, hy];
    });

    cfos.forEach((c) => {
      const [hx, hy] = hubOf[c.role];
      const team = dep.seats.filter((s) => s.parent === c.role);
      const n = team.length || 1;
      const step = 360 / n;
      // Aim the gap at Irina: start half a step past the direction to her, so no
      // worker sits on the hub-to-Irina line.
      const toIrina = Math.atan2(IRINA[1] - hy, IRINA[0] - hx) * 180 / Math.PI;
      const start = toIrina + step / 2;
      team.forEach((w, i) => {
        const a = (start + i * step) * Math.PI / 180;
        pos[w.role] = [hx + RING_R * Math.cos(a), hy + RING_R * Math.sin(a)];
      });
    });

    return { pos, hubOf, cfos };
  }

  function innerFlow(w, h) {
    const bw = 34, bh = 20, gap = 5;
    const total = PARTS.length * bw + (PARTS.length - 1) * gap;
    const x0 = (w - total) / 2;
    const y = h - bh - 8;
    return PARTS.map((p, i) => {
      const x = x0 + i * (bw + gap);
      return `<g class="dep-part" data-part="${p.key}">`
        + `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="5"/>`
        + `<text x="${x + bw / 2}" y="${y + bh / 2 + 4}" text-anchor="middle">${p.label}</text>`
        + `</g>`;
    }).join("");
  }

  function card(s, x, y) {
    const [w, h] = NODE[s.ring];
    const cls = `dep-node dep-r${s.ring} ${s.built ? "built" : "cold"}`;
    const max = s.ring === 0 ? 30 : s.ring === 1 ? 26 : 21;
    const lines = wrap(s.title, max);
    const firstY = s.ring === 0 ? 30 : lines.length > 1 ? 18 : 24;
    const title = lines.map((ln, i) =>
      `<text class="dep-title" x="${w / 2}" y="${firstY + i * 14}" text-anchor="middle">`
      + `${esc(ln)}</text>`).join("");
    return `<g class="${cls}" data-seat="${s.role}" transform="translate(${x - w / 2},${y - h / 2})">`
      + `<rect class="dep-card" width="${w}" height="${h}" rx="10"/>`
      + title + innerFlow(w, h)
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

  function departmentSVG(dep) {
    const L = layout(dep);
    const p = [];
    const seatBy = (role) => dep.seats.find((s) => s.role === role);

    // the circles the workers sit on
    Object.values(L.hubOf).forEach(([hx, hy]) => {
      p.push(`<circle class="dep-wheel" cx="${hx}" cy="${hy}" r="${RING_R}"/>`);
    });

    // lateral edges first, so the delegation edges draw on top of them
    peerPairs(dep).forEach(([a, b]) => {
      const pa = L.pos[a], pb = L.pos[b];
      if (!pa || !pb) return;
      const [aw, ah] = NODE[seatBy(a).ring];
      const [bw, bh] = NODE[seatBy(b).ring];
      const [x0, y0] = edgePoint(pa[0], pa[1], aw / 2, ah / 2, pb[0], pb[1]);
      const [x1, y1] = edgePoint(pb[0], pb[1], bw / 2, bh / 2, pa[0], pa[1]);
      p.push(`<line class="dep-edge dep-peer" data-src="${a}" data-dst="${b}" `
        + `x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}"/>`);
    });

    dep.edges.forEach((e) => {
      const a = L.pos[e.src], b = L.pos[e.dst];
      if (!a || !b) return;
      const [sw, sh] = NODE[seatBy(e.src).ring];
      const [dw, dh] = NODE[seatBy(e.dst).ring];
      const [x0, y0] = edgePoint(a[0], a[1], sw / 2, sh / 2, b[0], b[1]);
      const [x1, y1] = edgePoint(b[0], b[1], dw / 2, dh / 2, a[0], a[1]);
      p.push(`<line class="dep-edge" data-src="${e.src}" data-dst="${e.dst}" `
        + `x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}"/>`);
    });

    dep.seats.forEach((s) => {
      const [x, y] = L.pos[s.role];
      p.push(card(s, x, y));
    });

    return `<div class="dep-wrap"><svg class="dep" viewBox="0 0 ${W} ${H}" role="img"`
      + ` aria-label="The department: ${dep.seats.length} seats, each holding its own flow"`
      + `>${p.join("")}</svg></div>`;
  }

  function legend() {
    return `<div class="dep-legend">`
      + `<span class="dep-key"><i class="dep-swatch" style="background:var(--accent,#1e4e8c)"></i>Irina</span>`
      + `<span class="dep-key"><i class="dep-swatch" style="background:var(--accent-soft,#eaf2fb)"></i>CFO - the hub of its wheel</span>`
      + `<span class="dep-key"><i class="dep-swatch"></i>worker - on the circle</span>`
      + `<span class="dep-key">every seat holds the same flow: gate - llm - tool - out</span>`
      + `<span class="dep-key">solid spoke = delegation, one level down</span>`
      + `<span class="dep-key">faint chord = peers (they may consult each other); it lights when they do</span>`
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
    // `table()` maps over an ARRAY of <tr> strings; handing it a joined string
    // threw "rows.map is not a function" and killed the whole view render.
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
    const head = `<div class="meta" style="margin-bottom:var(--space-3)">Twenty-four seats, four
      wheels. Each CFO is the hub of its own circle, its workers on the rim, one spoke to each.
      Every seat is a full waku agent, so every block holds the same inner flow -
      <b>gate - llm - tool - out</b> - and the part that is working <b>beats</b>. Driven by the
      trace, so a turn started in the CLI or the dock animates here too.</div>`;
    if (!dep) return head + uiCard(`<span class="empty">no department payload</span>`);
    const built = dep.seats.filter((s) => s.built).length;
    setTimeout(paint, 0);   // re-apply beats after this render replaces the DOM
    return head + departmentSVG(dep) + legend()
      + uiCard(`<div class="meta">${built} of ${dep.seats.length} seats have run &middot;
        ${dep.edges.length} spokes. Grey = never used.</div>`)
      + seatsTable(dep);
  };
})();
