// ---- Tools: what the seats hold, and what they could hold.
//
// waku's own Tools page stays as the first tab. The second is the market: every
// tool that exists, every one that is only planned, and — the part that makes it
// more than a list — who has each one.
//
// Assignment is a file, not a guess. The page writes it and shows what it says.
// A generated tool cannot be handed to anyone until it has been read, because
// generated code runs inside the agent with the agent's reach.
(function () {
  "use strict";

  const base = VIEWS.tools;   // waku's page, kept whole as tab one

  let box = null;             // { tools, roles } from the server
  let draft = {};             // tool -> Set(role), ticks not yet saved
  let reviewed = {};          // tool -> true once its source has been read
  let note = "";

  async function load() {
    try {
      const res = await fetch("/api/toolbox");
      box = await res.json();
    } catch (e) {
      note = `could not read the toolbox: ${e}`;
      box = { tools: [], roles: [] };
    }
    if (typeof render === "function") render();
  }

  async function save(tool) {
    const roles = Array.from(draft[tool] || []);
    try {
      const res = await fetch("/api/toolbox", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool, roles }),
      });
      const data = await res.json();
      if (data.error) {
        note = data.error;
      } else {
        box = data.box;
        delete draft[tool];
        note = `${tool}: ${roles.length ? roles.length + " seat(s)" : "nobody"}`;
      }
    } catch (e) {
      note = `could not save: ${e}`;
    }
    if (typeof render === "function") render();
  }

  function ticks(tool, roles) {
    const chosen = draft[tool] || new Set(roles || []);
    const byRing = [[0, "Irina"], [1, "CFOs"], [2, "workers"]];
    return byRing.map(([ring, label]) => {
      const seats = roles === null ? [] : (box.roles || []).filter((r) => r.ring === ring);
      if (!seats.length) return "";
      return `<div class="tool-ring"><span class="tool-ring-l">${label}</span>${
        seats.map((r) => `<label class="tool-pick"><input type="checkbox"
          ${chosen.has(r.role) ? "checked" : ""}
          onchange="toolPick('${tool}','${r.role}',this.checked)"><code>${r.role}</code></label>`)
          .join("")}</div>`;
    }).join("");
  }

  function card(t) {
    const gated = t.switch
      ? `<p class="meta">${icon("alert", "ic-lead")}Present, but switched off
         (<code>${esc(t.switch)}</code>) — it would do nothing until that changes.</p>`
      : "";
    const state = t.state === "planned" ? "miss" : t.roles && t.roles.length ? "ok" : "neutral";
    const who = t.state === "planned" ? "not built"
      : (t.roles && t.roles.length) ? `${t.roles.length} seat(s)` : "nobody";
    const source = t.state === "generated"
      ? `<details class="tool-src"><summary>Read the code before handing it out</summary>
         <pre>${esc(t.source || "")}</pre></details>
         <label class="tool-pick"><input type="checkbox"
           ${reviewed[t.name] ? "checked" : ""}
           onchange="toolReviewed('${t.name}',this.checked)">I have read it</label>`
      : "";
    const controls = t.state === "planned"
      ? `<p class="meta">On waku's wish list. Nothing to assign yet.</p>`
      : `${ticks(t.name, t.roles)}<button type="button" class="btn btn-primary btn-sm"
           ${t.state === "generated" && !reviewed[t.name] ? "disabled" : ""}
           onclick="toolSave('${t.name}')">Save</button>`;
    return uiCard(`${t.description ? `<p class="home-p">${esc(t.description)}</p>` : ""}
      ${gated}${source}${controls}`,
      { title: `${esc(t.name)} ${uiBadge(who, state)}` });
  }

  function market() {
    if (box === null) { setTimeout(load, 0); return uiCard(`<p class="meta">reading the toolbox…</p>`); }
    const cards = (box.tools || []).map(card).join("");
    return `<h2>${icon("tools", "ic-lead")}The market</h2>
      <p class="home-p">Every tool a seat could hold. Nobody has one until this page
      says so, and a seat without a tool cannot use it — the tool is absent, not refused.</p>
      ${note ? `<p class="meta">${esc(note)}</p>` : ""}
      <div class="home-grid home-grid-2">${cards}</div>`;
  }

  window.toolPick = (tool, role, on) => {
    const set = draft[tool] || new Set();
    if (on) set.add(role); else set.delete(role);
    draft[tool] = set;
  };
  window.toolReviewed = (tool, on) => { reviewed[tool] = on; if (typeof render === "function") render(); };
  window.toolSave = (tool) => save(tool);

  VIEWS.tools = (d, sub) => {
    const tabs = uiTabs([
      { label: "Available", href: "#tools", on: sub !== "market" },
      { label: "Market", href: "#tools/market", on: sub === "market" },
    ]);
    return sub === "market" ? tabs + market() : tabs + base(d, sub);
  };
})();
