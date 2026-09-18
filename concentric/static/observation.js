// ---- Observation Lab: the instruments, and the gaps.
//
// Every other page answers "what is it doing now". This one answers "what can we
// say about it at all" — including the things we cannot say yet. The registry
// behind it is `concentric/metrics.py`, and each slot's state is a fact rather
// than a wish: a metric with no value names what would give it one.
//
// The page never calls a model. Everything on it is arithmetic over traces and
// state already on disk, which is why it can ride the 5s poll. Anything that
// needs a judge is a batch run, and shows up here as a number with a last-run
// stamp or as a named gap.
(function () {
  "use strict";

  // The lenses are the questions, not the taxonomy's sections. Flow, Effort,
  // Health and Memory came out of reading the first catalogue: those are the
  // four ways the same trace and state answer four different things.
  const LENSES = [
    ["Health", "How it fails, and whether it holds together", [
      "premature_terminations", "unanswered_handoffs", "step_repetition",
      "mandate_breaches", "hallucination_rate",
      "mast_reasoning_action_mismatch", "mast_information_withholding",
      "mast_annotator_agreement",
      "stance_convergence", "stance_shift", "semantic_diversity"]],
    ["Effort", "Where the time and money go", [
      "cost", "cost_per_ring", "latency_avg", "latency_p95", "throughput",
      "tokens_in", "tokens_out", "context_growth", "tool_errors"]],
    ["Flow", "How work moves", [
      "delegation_depth", "delegation_breadth", "handoff_latency",
      "consultations", "peer_pairs_used", "gate_retrieval_ratio"]],
    ["Memory", "What the ecosystem learns", [
      "memory_growth", "fact_writers", "seats_without_memory", "idle_seats",
      "consolidation_backlog", "context_retention", "factual_grounding",
      "bleu_rouge_meteor", "bertscore"]],
  ];

  // Health is the one lens whose numbers are all bad news when they are high, so
  // it is the one that raises a flag rather than a row.
  const WATCH = ["premature_terminations", "unanswered_handoffs", "step_repetition",
                 "mandate_breaches"];

  function show(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "number") return String(Math.round(v * 10000) / 10000);
    if (Array.isArray(v)) {
      const head = v.slice(0, 3).join(", ");
      return v.length > 3 ? `${head} +${v.length - 3} more` : head;
    }
    if (typeof v === "object") {
      return Object.entries(v).slice(0, 3)
        .map(([k, x]) => `${k}: ${x}`).join(", ");
    }
    return String(v);
  }

  // A wired slot with no value is not the same as a slot nobody wired. The badge
  // says which, because that is the difference between "nothing happened yet"
  // and "nobody is looking".
  function stateBadge(slot) {
    if (slot.value !== null) return uiBadge("measured", "ok");
    if (slot.state === "computed") return uiBadge("no data yet", "warn");
    if (slot.state === "ready") return uiBadge("ready", "warn");
    if (slot.state === "blocked") return uiBadge("blocked", "bad");
    return uiBadge("planned", "neutral");
  }

  // ---- the run button.
  //
  // The only control on this page that spends money. Three rules, all of them
  // about the reader being able to decide rather than discover:
  //
  //   * it says what the run will cost before it is pressed
  //   * it refuses to start a second run while one is going
  //   * it refreshes the view the moment the numbers land, rather than leaving
  //     the reader waiting up to five seconds for the next poll
  //
  // Nothing here runs on a timer. The batch is a decision, not a background job.

  let batchRunning = false;
  let batchText = "";

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

  function batchBar(d) {
    const b = d.batch || {};
    const limit = b.limit || 20;
    const cost = b.calls ? `${b.calls} model calls` : "an unknown number of calls";
    const note = b.embeddings ? ""
      : " The four semantic metrics stay empty: no OPENAI_API_KEY is set.";
    return `<div class="lab-batch">
      <div class="lab-batch-txt"><b>Last batch run:</b> ${esc(ago(b.last_run))}.
        The next one scores the last ${esc(limit)} turns for ${esc(cost)}.${note}</div>
      <button type="button" class="btn btn-primary lab-run" id="lab-run">Run the batch</button>
      <div class="lab-progress" id="lab-progress" hidden></div>
    </div>`;
  }

  function wireBatch() {
    const btn = document.getElementById("lab-run");
    if (!btn) return;
    const bar = document.getElementById("lab-progress");
    // The view is rebuilt on every poll, so a run in flight has to be restored
    // rather than forgotten: the button comes back enabled otherwise, and a
    // second press would be refused by the server after the click.
    if (batchRunning) {
      btn.disabled = true;
      if (bar) { bar.hidden = false; bar.textContent = batchText; }
    }
    btn.addEventListener("click", async () => {
      if (batchRunning) return;
      batchRunning = true;
      batchText = "starting…";
      btn.disabled = true;
      if (bar) { bar.hidden = false; bar.textContent = batchText; }
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
            else if (ev.kind === "done") batchText = `done · ${ev.scored} turns scored`;
            if (bar) bar.textContent = batchText;
          }
        }
      } catch (e) {
        batchText = `the run failed: ${e}`;
        if (bar) { bar.hidden = false; bar.textContent = batchText; }
      }
      batchRunning = false;
      btn.disabled = false;
      // main.js's own refresh, so the new report shows up now rather than at the
      // next poll.
      if (typeof refresh === "function") refresh();
    });
  }

  // A per-seat value is a dict; the department-level sentences need one number.
  // The tables stay per-seat — only the verdict and the watch list collapse.
  function totalOf(slot) {
    const v = slot && slot.value;
    if (v === null || v === undefined) return null;
    if (typeof v !== "object") return v;
    return Object.values(v).reduce((n, cell) => n + ((cell && cell.value) || 0), 0);
  }

  function verdict(m, d) {
    const turns = (d.stats && d.stats.turns) || 0;
    const val = (id) => totalOf(m[id]);
    const parts = [];
    const stopped = val("premature_terminations");
    const silent = val("unanswered_handoffs");
    const repeated = val("step_repetition");
    if (stopped !== null && turns) parts.push(`${stopped} of ${turns} turns never finished`);
    if (silent) parts.push(`${silent} hand-offs were never answered`);
    if (repeated) parts.push(`${repeated} tool calls repeated inside a turn`);
    const lede = parts.length
      ? `Health reads first, because it is the only lens where a number is bad news: ${parts.join("; ")}.`
      : "Health reads clean: no turn stopped early, no hand-off went unanswered, nothing repeated.";
    return uiCard(`<p class="lab-verdict">${lede}</p>`);
  }

  function attention(m, rows) {
    const flagged = WATCH
      .map((id) => ({ slot: m[id], total: totalOf(m[id]) }))
      .filter((x) => x.slot && typeof x.total === "number" && x.total > 0);
    const gaps = rows.filter((s) => s.value === null && s.state !== "placeholder");
    const body = [];
    if (flagged.length) {
      body.push(table(["what", "count", "unit"], flagged.map((x) => [
        `<b>${esc(x.slot.label)}</b>`, `<code>${show(x.total)}</code>`,
        `<span class="meta">${esc(x.slot.unit)}</span>`])));
    } else {
      body.push(`<p class="lab-quiet">Nothing in the health instruments is above zero.</p>`);
    }
    if (gaps.length) {
      body.push(`<p class="lab-gap">${gaps.length} instruments have no value yet. `
        + `They are listed with what would fill them under Instruments.</p>`);
    }
    return uiCard(body.join(""), { title: "Needs attention" });
  }

  // A per-seat or per-pair value renders as a table, not one number. Sorted
  // worst-first, because that is the entire reason for splitting a department
  // mean back into its seats: "23 repeats" becomes "audit-planner repeated 9".
  //
  // `n` rides every row. A mean over two turns and a mean over forty are not the
  // same claim, and showing them side by side without saying so invites a wrong
  // conclusion.
  function seriesTable(value, direction, unit) {
    const rows = Object.entries(value).map(([key, cell]) => {
      const isCell = cell && typeof cell === "object";
      return { key, v: isCell ? cell.value : cell, n: isCell ? cell.n : null };
    });
    if (!rows.length) return `<span class="meta">nothing to show</span>`;
    const num = (x) => (typeof x === "number" ? x : Number(x));
    if (direction === "lower") rows.sort((a, b) => num(b.v) - num(a.v));
    else if (direction === "higher") rows.sort((a, b) => num(a.v) - num(b.v));
    else rows.sort((a, b) => String(a.key).localeCompare(String(b.key)));
    const body = rows.map((r) => `<tr>
      <td><code>${esc(r.key)}</code></td>
      <td class="num"><code>${esc(show(r.v))}</code></td>
      <td class="meta">${r.n == null ? "" : "n=" + esc(r.n)}</td></tr>`).join("");
    return `<table class="lab-series"><thead><tr>
      <th>who</th><th>${esc(unit || "")}</th><th></th></tr></thead>
      <tbody>${body}</tbody></table>`;
  }

  function valueCell(s) {
    if (s.value === null || s.value === undefined) {
      return `<code>—</code> <span class="lab-row-unit">${esc(s.unit)}</span>`;
    }
    if (typeof s.value === "object") {
      return seriesTable(s.value, s.direction, s.unit);
    }
    return `<code>${esc(show(s.value))}</code>
      <span class="lab-row-unit">${esc(s.unit)}</span>
      ${s.as_of ? `<span class="lab-row-asof">run ${esc(ago(s.as_of))}</span>` : ""}`;
  }

  function lensCard([name, question, ids], m) {
    const slots = ids.map((id) => m[id]).filter(Boolean);
    if (!slots.length) return "";
    const body = slots.map((s) => `<div class="lab-row">
        <div class="lab-row-head">
          <span class="lab-row-label">${esc(s.label)}</span>
          ${stateBadge(s)}
        </div>
        <div class="lab-row-value">${valueCell(s)}</div>
        ${s.value === null && s.filler
          ? `<div class="lab-row-filler">${esc(s.filler)}</div>` : ""}
      </div>`).join("");
    return uiCard(body, { title: `${name} — ${question}` });
  }

  function instruments(rows) {
    const groups = [
      ["measured", rows.filter((s) => s.value !== null)],
      ["wired, no data yet",
       rows.filter((s) => s.value === null && s.state === "computed")],
      ["ready to build", rows.filter((s) => s.value === null && s.state === "ready")],
      ["blocked", rows.filter((s) => s.value === null && s.state === "blocked")],
      ["planned", rows.filter((s) => s.value === null && s.state === "placeholder")],
    ];
    return groups.filter(([, g]) => g.length).map(([title, group]) => {
      const body = group.map((s) => [
        `<code>${esc(s.id)}</code><div class="meta">${esc(s.label)} · ${esc(s.level)}</div>`,
        valueCell(s),
        stateBadge(s),
        `<span class="meta">${esc(s.unit)} · ${esc(s.changes)} · `
        + `${esc(s.source)}</span>`,
        s.value === null && s.filler
          ? `<span class="meta">${esc(s.filler)}</span>` : "",
      ]);
      return uiCard(
        table(["instrument", "value", "state", "", "what would fill it"], body),
        { title: `${title} — ${group.length}` });
    }).join("");
  }

  VIEWS.observation = (d) => {
    const m = d.metrics || {};
    const rows = Object.values(m);
    if (!rows.length) {
      return uiCard(`<span class="empty">No registry in the payload. The launcher
        computes it in concentric/metrics.py; restart the server if this page is
        empty after an update.</span>`);
    }
    const measured = rows.filter((s) => s.value !== null).length;
    const head = `<div class="meta" style="margin-bottom:var(--space-3)">Every metric
      the evaluation taxonomy names, one row each — the ones this repository can
      already answer from its traces and its state, and the ones it cannot, with
      what would close each gap. Nothing here calls a model.</div>`;
    const band = uiStatBand([
      { label: "instruments", value: String(rows.length) },
      { label: "measured", value: String(measured), tone: "ok" },
      { label: "no data yet",
        value: String(rows.filter((s) => s.value === null && s.state === "computed").length) },
      { label: "ready to build",
        value: String(rows.filter((s) => s.value === null && s.state === "ready").length) },
      { label: "blocked",
        value: String(rows.filter((s) => s.value === null && s.state === "blocked").length) },
    ]);
    // After the DOM swaps in: the button's listener, and a run in flight
    // restored. The same deferred wiring department.js does for its own view.
    setTimeout(wireBatch, 0);
    return head + verdict(m, d) + batchBar(d) + band
      + attention(m, rows)
      + `<h2>The lenses</h2>`
      + `<div class="lab-grid">${LENSES.map((l) => lensCard(l, m)).join("")}</div>`
      + `<h2>Instruments</h2>`
      + instruments(rows);
  };
})();
