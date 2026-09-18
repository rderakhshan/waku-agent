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
      "mandate_breaches", "mast_reasoning_action_mismatch",
      "mast_information_withholding", "mast_annotator_agreement",
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

  function verdict(m, d) {
    const turns = (d.stats && d.stats.turns) || 0;
    const val = (id) => (m[id] && m[id].value !== null) ? m[id].value : null;
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
      .map((id) => m[id])
      .filter((s) => s && typeof s.value === "number" && s.value > 0);
    const gaps = rows.filter((s) => s.value === null && s.state !== "placeholder");
    const body = [];
    if (flagged.length) {
      body.push(table(["what", "count", "unit"], flagged.map((s) => [
        `<b>${esc(s.label)}</b>`, `<code>${show(s.value)}</code>`,
        `<span class="meta">${esc(s.unit)}</span>`])));
    } else {
      body.push(`<p class="lab-quiet">Nothing in the health instruments is above zero.</p>`);
    }
    if (gaps.length) {
      body.push(`<p class="lab-gap">${gaps.length} instruments have no value yet. `
        + `They are listed with what would fill them under Instruments.</p>`);
    }
    return uiCard(body.join(""), { title: "Needs attention" });
  }

  function lensCard([name, question, ids], m) {
    const slots = ids.map((id) => m[id]).filter(Boolean);
    if (!slots.length) return "";
    const body = slots.map((s) => `<div class="lab-row">
        <div class="lab-row-head">
          <span class="lab-row-label">${esc(s.label)}</span>
          ${stateBadge(s)}
        </div>
        <div class="lab-row-value"><code>${esc(show(s.value))}</code>
          <span class="lab-row-unit">${esc(s.unit)}</span></div>
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
        `<code>${esc(s.id)}</code><div class="meta">${esc(s.label)}</div>`,
        `<code>${esc(show(s.value))}</code>`,
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
    return head + verdict(m, d) + band
      + attention(m, rows)
      + `<h2>The lenses</h2>`
      + `<div class="lab-grid">${LENSES.map((l) => lensCard(l, m)).join("")}</div>`
      + `<h2>Instruments</h2>`
      + instruments(rows);
  };
})();
