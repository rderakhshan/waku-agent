// ---- Observation Lab.
//
// Four questions, four sections, and the numbers are one click deeper than the
// answers. Every other page in this dashboard says what the department is doing;
// this one says which part of it is the problem.
//
// The shape follows from two observations about how a reader actually uses it:
//
//   * The thing they want first is ONE seat to look at, not a list of findings.
//   * The thing they want second is WHOSE problem it is — and the department
//     already knows, because the roster carries a parent for every seat.
//
// So the main table is the org tree, not a flat list, and the outlier finds the
// reader through a bar rather than through arithmetic. Nothing is computed here
// that the registry did not already compute; this file only decides what to show
// first.
(function () {
  "use strict";

  let batchRunning = false;
  let batchText = "";
  let problemsOnly = false;
  let openSeat = null;

  // The health metrics. A seat is "a problem" if any of them is above zero —
  // which is what the problems-only filter tests, and what the verdict ranks by.
  const PROBLEM_IDS = ["step_repetition", "premature_terminations",
                       "tool_errors", "mandate_breaches"];

  // --- reading the registry ---------------------------------------------------

  function cellOf(slot, key) {
    const value = slot && slot.value;
    if (!value || typeof value !== "object") return null;
    const cell = value[key];
    if (cell === null || cell === undefined) return null;
    return (typeof cell === "object") ? cell.value : cell;
  }

  function seatCell(m, id, role) {
    return cellOf(m[id], role);
  }

  function totalOf(slot) {
    const value = slot && slot.value;
    if (value === null || value === undefined) return null;
    if (typeof value !== "object") return value;
    return Object.values(value).reduce(
      (n, cell) => n + ((cell && typeof cell === "object") ? cell.value : cell || 0), 0);
  }

  // A seat's sample size, taken as the largest of the metrics that count things
  // it did. It travels with every row because a seat with two turns and a seat
  // with forty are not comparable, and the page must not imply they are.
  function seatN(m, role) {
    let best = null;
    for (const id of ["tokens_in", "cost", "tool_errors", "step_repetition"]) {
      const value = m[id] && m[id].value;
      const cell = value && value[role];
      const n = (cell && typeof cell === "object") ? cell.n : null;
      if (typeof n === "number") best = (best === null) ? n : Math.max(best, n);
    }
    return best;
  }

  function isProblem(m, role) {
    return PROBLEM_IDS.some((id) => (seatCell(m, id, role) || 0) > 0);
  }

  // The worst row of a metric, and how big it is — "data-steward · 15".
  function worstOf(slot) {
    const value = slot && slot.value;
    if (!value || typeof value !== "object") return null;
    const rows = Object.entries(value)
      .map(([key, cell]) => ({ key, n: (cell && typeof cell === "object") ? cell.value : cell }))
      .filter((r) => typeof r.n === "number" && r.n > 0)
      .sort((a, b) => b.n - a.n);
    return rows.length ? rows[0] : null;
  }

  // --- formatting -------------------------------------------------------------

  const usd = (n) => "$" + Number(n).toFixed(3);
  const secs = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + "s" : Math.round(n) + "ms");
  const plain = (n) => String(n);

  function ago(iso) {
    if (!iso) return "never";
    const then = Date.parse(iso);
    if (isNaN(then)) return "unknown";
    const mins = Math.round((Date.now() - then) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.round(mins / 60);
    return hours < 24 ? `${hours}h ago` : `${Math.round(hours / 24)}d ago`;
  }

  // A bar is a fraction of the column's largest value, so the eye finds the
  // outlier without reading a single number. Trivial to draw and it does more
  // work than any amount of sorting.
  function bar(value, max) {
    if (value === null || !max) return "";
    const width = Math.round(Math.max(0, Math.min(1, value / max)) * 100);
    return `<span class="lab-bar"><i style="width:${width}%"></i></span>`;
  }

  // --- the verdict ------------------------------------------------------------
  //
  // One seat, not a list. A reader does one thing with a verdict, and it is not
  // reading three findings and deciding which matters.

  function verdict(m, d) {
    const ranked = PROBLEM_IDS
      .map((id) => ({ id, slot: m[id], worst: worstOf(m[id]) }))
      .filter((x) => x.worst)
      .sort((a, b) => b.worst.n - a.worst.n);

    if (!ranked.length) {
      return uiCard(`<p class="lab-verdict">Nothing in the health instruments is
        above zero. No seat is repeating itself, stopping early, or breaking
        scope.</p>`);
    }

    const top = ranked[0];
    const seat = top.worst.key;
    const share = totalOf(top.slot);
    const rest = ranked.slice(1)
      .map((x) => `${x.slot.label.toLowerCase()} ${totalOf(x.slot)}`);

    const tail = rest.length
      ? ` The rest of the department: ${rest.join(", ")}.`
      : "";
    const owner = (d.department && d.department.seats || [])
      .find((s) => s.role === seat);
    const ownerText = (owner && owner.parent)
      ? `, who sits under ${owner.parent}` : "";

    return uiCard(`<p class="lab-verdict"><b>${esc(seat)}</b> is the one to look
      at: ${top.worst.n} of the department's ${share}
      ${esc(top.slot.unit)}${ownerText}.${tail}</p>`);
  }

  // --- the batch bar ----------------------------------------------------------

  function batchBar(d) {
    const b = d.batch || {};
    const limit = b.limit || 20;
    const cost = b.calls ? `${b.calls} model calls` : "an unknown number of calls";
    const note = b.embeddings ? ""
      : " The four semantic metrics stay empty: no OPENAI_API_KEY is set.";
    return `<div class="lab-batch">
      <div class="lab-batch-txt"><b>Last run:</b> ${esc(ago(b.last_run))}.
        The next one scores the last ${esc(limit)} turns for ${esc(cost)}.${note}</div>
      <button type="button" class="btn btn-primary lab-run" id="lab-run">Run the batch</button>
      <div class="lab-progress" id="lab-progress" hidden></div>
    </div>`;
  }

  function wireBatch() {
    const btn = document.getElementById("lab-run");
    if (!btn) return;
    const barEl = document.getElementById("lab-progress");
    if (batchRunning) {
      btn.disabled = true;
      if (barEl) { barEl.hidden = false; barEl.textContent = batchText; }
    }
    btn.addEventListener("click", async () => {
      if (batchRunning) return;
      batchRunning = true;
      batchText = "starting…";
      btn.disabled = true;
      if (barEl) { barEl.hidden = false; barEl.textContent = batchText; }
      try {
        const res = await fetch("/api/metrics/run", { method: "POST" });
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buf += dec.decode(chunk.value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop();
          for (const part of parts) {
            const line = part.replace(/^data: /, "").trim();
            if (!line) continue;
            let ev;
            try { ev = JSON.parse(line); } catch (e) { continue; }
            if (ev.kind === "start") batchText = `running · 0 of ${ev.calls}`;
            else if (ev.kind === "progress") batchText = `running · ${ev.done} of ${ev.of}`;
            else if (ev.kind === "error") batchText = `stopped: ${ev.message}`;
            else if (ev.kind === "done") batchText = `done · ${ev.scored} answers scored`;
            if (barEl) barEl.textContent = batchText;
          }
        }
      } catch (e) {
        batchText = `the run failed: ${e}`;
        if (barEl) { barEl.hidden = false; barEl.textContent = batchText; }
      }
      batchRunning = false;
      btn.disabled = false;
      if (typeof refresh === "function") refresh();
    });
  }

  // --- the summary line -------------------------------------------------------
  //
  // The stat band was five boxes for five counts. One line reads faster and the
  // counts are not the point — what is missing is.

  function summaryLine(rows) {
    const has = (s) => rows.filter((r) => r.value !== null && r.state === s).length;
    const waiting = rows.filter((r) => r.value === null && r.state === "computed").length;
    const ready = rows.filter((r) => r.value === null && r.state === "ready").length;
    const planned = rows.filter((r) => r.value === null && r.state === "placeholder").length;
    return `<p class="lab-summary">${rows.length} instruments ·
      <b>${has("computed")}</b> measured ·
      ${waiting} waiting on a run · ${ready} ready to build · ${planned} planned</p>`;
  }

  // --- the department tree ----------------------------------------------------
  //
  // The roster carries a parent for every seat, so the table can be the org
  // chart. That does something a sorted list cannot: it shows whose problem a
  // problem is. A worker looping is its CFO's problem, and the indentation says
  // so without a word of copy.

  const COLS = [
    { id: "cost", label: "cost", fmt: usd },
    { id: "latency_avg", label: "latency", fmt: secs },
    { id: "tool_errors", label: "errors", fmt: plain },
    { id: "step_repetition", label: "repeats", fmt: plain },
  ];

  function treeOrder(seats) {
    const byParent = {};
    seats.forEach((s) => {
      const key = s.parent || "";
      (byParent[key] = byParent[key] || []).push(s);
    });
    const out = [];
    const walk = (parent, depth) => {
      (byParent[parent] || []).forEach((s) => {
        out.push({ seat: s, depth });
        walk(s.role, depth + 1);
      });
    };
    walk("", 0);
    return out;
  }

  function departmentTable(d, m) {
    const seats = (d.department && d.department.seats) || [];
    if (!seats.length) return "";
    const ordered = treeOrder(seats);

    // With the filter on, keep the problem seats AND their ancestors — a tree
    // that drops the parent leaves an orphan with no owner.
    const problems = new Set(ordered.filter((r) => isProblem(m, r.seat.role))
      .map((r) => r.seat.role));
    const keep = new Set(problems);
    if (problemsOnly) {
      const parentOf = {};
      seats.forEach((s) => { parentOf[s.role] = s.parent; });
      problems.forEach((role) => {
        for (let p = parentOf[role]; p; p = parentOf[p]) keep.add(p);
      });
    }
    const shown = problemsOnly ? ordered.filter((r) => keep.has(r.seat.role)) : ordered;

    // One scale per column, taken from the full roster rather than the shown
    // rows, so a bar does not grow just because the filter hid its neighbours.
    const maxima = {};
    COLS.forEach((c) => {
      maxima[c.id] = Math.max(0, ...ordered.map((r) => seatCell(m, c.id, r.seat.role) || 0));
    });

    const head = `<tr><th>seat</th><th class="num">n</th>`
      + COLS.map((c) => `<th class="num">${esc(c.label)}</th>`).join("")
      + `</tr>`;

    const body = shown.map((r) => {
      const s = r.seat;
      const cells = COLS.map((c) => {
        const v = seatCell(m, c.id, s.role);
        return `<td class="num">${v === null ? `<span class="lab-dash">·</span>`
          : esc(c.fmt(v))}${bar(v, maxima[c.id])}</td>`;
      }).join("");
      const open = openSeat === s.role;
      const detail = open ? detailRow(m, s) : "";
      return `<tr class="lab-seat${open ? " open" : ""}" data-seat="${esc(s.role)}">
          <td><span class="lab-indent" style="--d:${r.depth}"></span>
            <code>${esc(s.role)}</code></td>
          <td class="num"><span class="meta">${esc(seatN(m, s.role) || "·")}</span></td>
          ${cells}</tr>${detail}`;
    }).join("");

    const hidden = ordered.length - shown.length;
    const foot = problemsOnly && hidden
      ? `<p class="lab-foot">${hidden} more seat${hidden === 1 ? "" : "s"} hidden —
         they have nothing in the health columns.</p>`
      : "";

    const toggle = `<label class="lab-toggle">
      <input type="checkbox" id="lab-problems"${problemsOnly ? " checked" : ""}>
      problems only</label>`;

    return `<div class="lab-dept-head"><h2>The department</h2>
        <span class="meta">${shown.length} of ${ordered.length} shown</span>${toggle}</div>
      <div class="tbl-wrap"><table class="tbl lab-tree">${head}${body}</table></div>
      ${foot}
      <p class="lab-foot">Click a seat for its full readings.</p>`;
  }

  function detailRow(m, seat) {
    const rows = Object.values(m)
      .map((slot) => {
        const v = seatCell(m, slot.id, seat.role);
        if (v === null) return null;
        return `<div class="lab-detail-row">
          <code>${esc(slot.id)}</code>
          <span class="lab-detail-v">${esc(show(v))}
            <span class="meta">${esc(slot.unit)}</span></span></div>`;
      })
      .filter(Boolean).join("");
    return `<tr class="lab-detail"><td colspan="${COLS.length + 2}">${rows
      || `<span class="meta">no per-seat readings for this seat yet</span>`}</td></tr>`;
  }

  function show(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "number") return String(Math.round(v * 10000) / 10000);
    if (Array.isArray(v)) return v.join(", ");
    return String(v);
  }

  function wireDept() {
    const box = document.getElementById("lab-problems");
    if (box) {
      box.addEventListener("change", () => {
        problemsOnly = box.checked;
        if (typeof render === "function") render();
      });
    }
    document.querySelectorAll(".lab-seat").forEach((row) => {
      row.addEventListener("click", () => {
        const seat = row.getAttribute("data-seat");
        openSeat = (openSeat === seat) ? null : seat;
        if (typeof render === "function") render();
      });
    });
  }

  // --- the hand-offs ----------------------------------------------------------
  //
  // An arrow, not a row. `irina ──23──▶ cfo-1` says how often and in which
  // direction in one glance, which a table of two columns does not.

  function handoffFlows(m) {
    // The slots, not their values: cellOf reads a slot's value map, and passing
    // the map itself made every field null — which rendered as "never answered"
    // on all fifty-seven pairs, including the ones that were answered instantly.
    const counts = m.peer_pairs_used || {};
    const latency = m.handoff_latency || {};
    const unanswered = m.unanswered_handoffs || {};
    const keys = Object.keys(counts.value || {});
    if (!keys.length) return "";

    const rows = keys.map((key) => {
      const parts = key.split(">");
      return {
        key, from: parts[0], to: parts[1],
        count: cellOf(counts, key),
        latency: cellOf(latency, key),
        unanswered: cellOf(unanswered, key),
      };
    });
    // Worst first: a slow hand-off, then one that was never answered, then the
    // busiest. The healthy ones sort to the bottom where they belong.
    rows.sort((a, b) => (b.latency || 0) - (a.latency || 0)
      || (b.unanswered || 0) - (a.unanswered || 0)
      || (b.count || 0) - (a.count || 0));

    // A pair with no latency is not a failure — it is a consultation, which has
    // no hand-off to time. Saying "never answered" about it was a lie the page
    // told confidently, which is worse than saying nothing.
    const note = (r) => {
      const bits = [];
      if (r.latency !== null) bits.push(esc(secs(r.latency)) + " median");
      if (r.unanswered) bits.push(esc(r.unanswered) + " unanswered");
      if (!bits.length) bits.push("consults only");
      return bits.join(" · ");
    };

    const body = rows.slice(0, 10).map((r) => `<div class="lab-flow">
        <code class="lab-flow-from">${esc(r.from)}</code>
        <span class="lab-flow-line"><i>${esc(r.count)}</i></span>
        <code class="lab-flow-to">${esc(r.to)}</code>
        <span class="lab-flow-note meta">${note(r)}</span>
      </div>`).join("");

    const more = rows.length > 10
      ? `<p class="lab-foot">${rows.length} pairs in all · showing the 10 worst.</p>` : "";
    return `<h2>The hand-offs</h2>${body}${more}`;
  }

  // --- the gaps ---------------------------------------------------------------
  //
  // A checklist, not a table. This is the one section where "unfinished" is the
  // point, so it should look unfinished — and each line names what would close it.

  function gaps(rows) {
    const open = rows.filter((s) => s.value === null);
    if (!open.length) {
      return uiCard(`<p class="lab-quiet">Every instrument holds a value.</p>`,
        { title: "What we can't measure yet" });
    }
    const body = open.map((s) => `<div class="lab-gap-row">
        <span class="lab-gap-box">${s.state === "placeholder" ? "[-]" : "[ ]"}</span>
        <code>${esc(s.id)}</code>
        <span class="meta">${esc(s.filler || "")}</span></div>`).join("");
    return uiCard(body, { title: `What we can't measure yet — ${open.length} open` });
  }

  // --- the page ---------------------------------------------------------------

  VIEWS.observation = (d) => {
    const m = d.metrics || {};
    const rows = Object.values(m);
    if (!rows.length) {
      return uiCard(`<span class="empty">No registry in the payload. The launcher
        computes it in concentric/metrics.py; restart the server if this page is
        empty after an update.</span>`);
    }
    setTimeout(() => { wireBatch(); wireDept(); }, 0);
    return verdict(m, d)
      + batchBar(d)
      + summaryLine(rows)
      + departmentTable(d, m)
      + handoffFlows(m)
      + gaps(rows);
  };
})();
