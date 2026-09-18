// ---- Home: the billboard.
//
// The one page in this dashboard that is not a cockpit. Every other page answers
// "what is it doing right now"; this one answers "what is this, and why would I
// want it" before you have to read a trace to find out.
//
// It is built from the same live payload as everything else, so the numbers on
// it are the department's real numbers rather than a screenshot that went stale.
// That is the honest kind of advertisement: the pitch and the proof are the same
// page.
(function () {
  "use strict";

  const ringOf = (dep, n) => (dep.seats || []).filter((s) => s.ring === n);

  // The four claims the README makes, kept to one sentence each. If a claim here
  // stops being true, the README and this page are both wrong — so they say the
  // same thing on purpose.
  const CLAIMS = [
    ["The graph is code",
     "Scope is the delegation tool's role enum and depth is a ring counter. A worker is given "
     + "no delegation tool at all &mdash; the forbidden edges are absent, not refused."],
    ["Local-first",
     "Every seat keeps its own SQLite file under <code>.waku-concentric/agents/</code>. "
     + "Open it. Read it. It is yours."],
    ["Watch it think",
     "A local dashboard draws the department and beats each seat as it works. Every box is a "
     + "real stage of a real turn, not a diagram of one."],
    ["Eval built in",
     "Deterministic tests and LLM-as-judge sit side by side behind one release gate, so a bug "
     + "fix ships with the case that would have caught it."],
  ];

  function hero() {
    return `<section class="home-hero">
      <img class="home-mark" src="/irina-mark.svg" alt="" width="76" height="76">
      <div class="home-hero-body">
        <h2 class="home-name">Irina</h2>
        <p class="home-lede">A department of 24 AI agents for model risk management &mdash;
          in code you can read.</p>
        <p class="home-sub">One chief model risk officer, four CFOs and nineteen workers.
          Every seat is a full agent with its own memory, its own prompt and its own tools,
          and the rules between them are enforced in code rather than asked for in a prompt.</p>
        <div class="home-cta">
          ${uiButton("Open the department", {
            level: "primary", onclick: "location.hash='#overview/multi'"})}
          ${uiButton("The cockpit", {
            level: "secondary", onclick: "location.hash='#ops'"})}
        </div>
      </div>
    </section>`;
  }

  function rings(dep) {
    const rows = [
      ["0", "Irina", "the chief model risk officer", ringOf(dep, 0)],
      ["1", "CFOs", "development, validation, governance and audit", ringOf(dep, 1)],
      ["2", "Workers", "the teams each CFO tasks, one level down", ringOf(dep, 2)],
    ];
    const body = rows.map(([n, name, blurb, list]) => `<div class="home-ring">
        <span class="home-ring-n">${n}</span>
        <div class="home-ring-body">
          <div class="home-ring-name">${name}<span class="home-ring-count">${list.length}</span></div>
          <div class="home-ring-blurb">${blurb}</div>
          <div class="home-ring-roles">${
            list.map((s) => `<code>${esc(s.role)}</code>`).join("")}</div>
        </div>
      </div>`).join("");
    return uiCard(body, { title: "The department, by ring" });
  }

  function loop() {
    const stage = (t, sub) => `<div class="home-stage"><b>${t}</b><span>${sub}</span></div>`;
    return uiCard(
      `<div class="home-loop">${stage("gate", "remember?")}<i>&rarr;</i>`
      + `${stage("llm", "reason")}<i>&rarr;</i>${stage("tool", "act")}<i>&rarr;</i>`
      + `${stage("out", "reply")}</div>
       <p class="home-p">Every seat runs the same loop, whether it is Irina taking the task or a
       worker three rings down. The difference between the seats is their mandate, their memory
       and which tools they hold &mdash; never the machinery.</p>`,
      { title: "One loop, every seat" });
  }

  function provenance() {
    return uiCard(
      `<p class="home-p">Irina is built on <a href="https://github.com/ShenSeanChen/waku-agent"
       target="_blank" rel="noopener noreferrer">waku-agent</a>, a local-first assistant that
       shows the four pillars behind every serious agent &mdash; Harness, Loop, Memory and
       Eval/LLM-Ops &mdash; with no framework hiding the good parts.</p>
       <p class="home-p">This fork adds <code>concentric/</code>: the department. <code>waku/</code>
       itself is unchanged, so <code>localhost:7777</code> is still plain Waku and
       <code>localhost:7778</code> is Irina. Comparing the two is the quickest way to see what
       this repository adds.</p>`,
      { title: "What this is, and what it is built on" });
  }

  VIEWS.home = (d) => {
    const dep = d.department || { seats: [], edges: [] };
    const bySeat = (d.usage && d.usage.by_seat) || [];
    const calls = bySeat.reduce((n, b) => n + (b.calls || 0), 0);
    const cost = bySeat.reduce((n, b) => n + (b.cost || 0), 0);
    const built = (dep.seats || []).filter((s) => s.built).length;

    return hero()
      + uiStatBand([
        { label: "seats", value: String((dep.seats || []).length),
          sub: `${built} have run` },
        { label: "LLM calls", value: calls.toLocaleString(),
          sub: `${bySeat.length} seats active` },
        { label: "spend", value: money(cost), sub: "across the department" },
        { label: "facts", value: String((d.facts || []).length), sub: "semantic memory" },
        { label: "episodes", value: String((d.episodes || []).length), sub: "episodic memory" },
        { label: "turns", value: String((d.stats && d.stats.turns) || 0),
          sub: "Irina's own loop" },
      ])
      + `<div class="home-grid">${
        CLAIMS.map(([t, b]) => uiCard(`<p class="home-p">${b}</p>`, { title: t })).join("")
      }</div>`
      + `<div class="home-grid home-grid-2">${rings(dep)}${loop()}</div>`
      + provenance();
  };
})();
