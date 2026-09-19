// ---- Tools: what the seats hold, what they could, and the lab that makes more.
//
// waku's own Tools page stays as the first tab. The second is the market, built
// on the Connections card so a tool reads like every other thing you connect:
// a tile, a state pill, a line of description, and an action. The third is the
// lab, which assembles a tool from the parts you type.
//
// Assignment is a file, not a guess. The page writes it and shows what it says.
// A tool has one owner in practice, so the card shows its holders as chips and
// a "+" — not a wall of twenty-four checkboxes, which implies the normal case is
// picking many.
(function () {
  "use strict";

  const base = VIEWS.tools;   // waku's page, kept whole as tab one

  let box = null;             // { tools, roles } from the server

  let note = "";

  // The icons a tool may wear. All vendored under concentric/static/icons/.
  const ICONS = ["tools", "search", "file", "inbox", "clock", "external", "memory",
    "settings", "sparkles", "branch", "users", "lab", "gauge", "chart", "database",
    "shield", "graph", "loop", "models", "gateway", "connections", "home",
    "dashboard", "image", "refresh", "check", "alert", "race", "ops"];

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

  async function save(tool, roles) {
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
        box = { tools: data.tools, roles: box.roles };
        note = roles.length ? `${tool} → ${roles.join(", ")}` : `${tool} → nobody`;
      }
    } catch (e) {
      note = `could not save: ${e}`;
    }
    if (typeof render === "function") render();
  }

  const held = (t) => t.roles || [];
  const byName = (name) => (box.tools || []).find((t) => t.name === name);

  // --- the card --------------------------------------------------------------

  function state(t) {
    if (t.state === "planned") return ["not-configured", "planned"];
    if (t.switch) return ["needs-setup", "needs setup"];
    if (held(t).length) return ["connected", "assigned"];
    return ["not-configured", "nobody"];
  }

  const SHOWN = 2;   // chips printed before the rest are counted

  function chips(t) {
    const who = held(t);
    // The pill above already says "nobody", so saying it twice was noise — and
    // as a wrapping span in a flex row it also broke the row's layout.
    if (!who.length) return "";
    const shown = who.slice(0, SHOWN).map((role) => `<span class="tool-chip">${esc(role)}
      <button type="button" class="tool-x" title="remove"
        onclick="toolDrop('${t.name}','${role}')">${icon("cross")}</button></span>`).join("");
    // A specialised tool has one owner, so a card rarely needs more than a name.
    // When it does, the extra are counted rather than printed: a card is not a
    // place to list a department, and the full list is in the tooltip.
    const rest = who.length - SHOWN;
    const more = rest > 0
      ? `<span class="tool-chip tool-more" title="${esc(who.join(", "))}">+${rest}</span>` : "";
    return `<span class="tool-holders">${shown}${more}</span>`;
  }

  function card(t) {
    const [cls, label] = state(t);
    const gated = t.switch
      ? `<div class="connwhy">switch off: ${esc(t.switch)} — it would do nothing</div>` : "";
    // The source is on the card for anything built here: a tool you cannot read
    // is a tool you cannot judge, and this is the page where you judge it.
    const source = t.state === "generated"
      ? `<details class="tool-src"><summary>What it actually does</summary>
         <pre>${esc(t.source || "")}</pre></details>` : "";
    let actions;
    if (t.state === "planned") {
      actions = `<span class="connwhy">on waku's wish list</span>`;
    } else {
      actions = `${chips(t)}
        <button type="button" class="btn btn-secondary btn-sm"
          onclick="toolGive(this,'${t.name}')">${icon("plus", "ic-lead")}Assign</button>`;
    }
    return uiCard(
      `<span class="provlogo tool-tile">${icon(t.icon || "tools")}</span>
       <div class="connstatus ${cls}"><span class="conndot"></span>${esc(label)}</div>
       ${gated}${source}
       <div class="conndesc">${esc(t.description || "")}</div>
       <div class="provactions connactions">${actions}</div>`,
      { title: esc(t.name), cls: "provcard conncard" });
  }

  function section(title, items) {
    if (!items.length) return "";
    return `<section class="connsection"><h2>${title}</h2>
      <div class="provgrid conngrid">${items.map(card).join("")}</div></section>`;
  }

  function market() {
    if (box === null) {
      setTimeout(load, 0);
      return uiCard(`<p class="meta">reading the toolbox…</p>`);
    }
    const all = box.tools || [];
    const mine = (t) => t.state !== "planned" && held(t).length;
    return `<h2>${icon("tools", "ic-lead")}The market</h2>
      <p class="home-p">Every tool a seat could hold. Nobody has one until this page
      says so, and a seat without a tool cannot use it — the tool is absent, not
      refused.</p>
      ${note ? `<p class="meta">${esc(note)}</p>` : ""}
      ${section("Assigned", all.filter(mine))}
      ${section("Ready to give", all.filter((t) => t.state !== "planned" && !t.switch && !held(t).length))}
      ${section("Present, but switched off", all.filter((t) => t.state !== "planned" && t.switch && !held(t).length))}
      ${section("Planned", all.filter((t) => t.state === "planned"))}`;
  }

  // --- the lab ---------------------------------------------------------------

  const BLANK_BODY =
    'def run(**kwargs) -> str:\n'
    + '    """What this tool does, and what it returns."""\n'
    + '    return ""\n';

  const ARG_TYPES = ["string", "number", "integer", "boolean", "array", "object"];

  function argRow() {
    return `<div class="arg-row">
      <input class="arg-name" placeholder="currency" autocomplete="off">
      <select class="arg-type">${
        ARG_TYPES.map((t) => `<option value="${t}">${t}</option>`).join("")}</select>
      <input class="arg-desc" placeholder="what it means" autocomplete="off">
      <label class="tool-pick"><input type="checkbox" class="arg-req">required</label>
      <button type="button" class="tool-x" title="remove"
        onclick="labDropArg(this)">${icon("cross")}</button></div>`;
  }

  function labTab() {
    return `<h2>${icon("lab", "ic-lead")}The LAB</h2>
      <p class="home-p">Build a tool from its parts: an id the model calls, a
      description it reads to decide when, the arguments it should fill in, and
      the body that runs. Nothing is generated for you here — you are the author,
      which is also why a tool built here can be handed to a seat at once.</p>
      ${uiCard(`<p class="home-p">A tool is a name, a description, the shape of
        its arguments, and a function. The description is the one that decides
        whether it is ever called: the model never reads your code.</p>
        <div class="provactions">${
          uiButton("Open the builder", {level: "primary", onclick: "labOpen()"})}</div>`,
        { title: "New tool" })}`;
  }

  // --- the picker and the builder --------------------------------------------
  //
  // Both are menus and dialogs, which ui.js puts on <body>. That matters: the
  // dashboard rebuilds #view every five seconds, so anything typed inside it
  // would be wiped and the caret thrown to the end.

  // Grouped by ring, not one flat list of twenty-four: you pick a seat by where
  // it sits, which is how the department is described everywhere else. Workers
  // carry their team instead of "ring 2", because that is the useful half.
  window.toolGive = (el, name) => {
    const t = byName(name);
    if (!t) return;
    const already = new Set(held(t));
    const free = (box.roles || []).filter((r) => !already.has(r.role));
    if (!free.length) {
      openMenu(el, uiMenuLabel("every seat already holds it"));
      return;
    }
    let html = "";
    for (const [ring, label] of [[0, "Irina"], [1, "CFOs"], [2, "Workers"]]) {
      const seats = free.filter((r) => r.ring === ring);
      if (!seats.length) continue;
      html += uiMenuLabel(label) + seats.map((r) => uiMenuItem(esc(r.role), {
        sub: r.ring === 2 ? esc(r.parent || "") : `ring ${r.ring}`,
        onclick: `toolAdd('${name}','${r.role}')`,
      })).join("");
    }
    if (already.size) {
      html += uiMenuSep() + uiMenuItem("Remove from everyone", {
        danger: true, onclick: `toolClear('${name}')`});
    }
    openMenu(el, html, { width: "280px" });
  };

  window.toolClear = (name) => {
    closeMenu();
    save(name, []);
  };

  window.toolAdd = (name, role) => {
    closeMenu();
    const t = byName(name);
    if (t) save(name, held(t).concat([role]));
  };
  window.toolDrop = (name, role) => {
    const t = byName(name);
    if (t) save(name, held(t).filter((r) => r !== role));
  };
  window.labOpen = () => {
    openDialog(`
      <h3>Build a tool</h3>
      <p class="connwhy">It lands in the market assigned to nobody.</p>
      <label class="fld"><span>id</span>
        <input id="lab-id" placeholder="lookup_rate" autocomplete="off"></label>
      <label class="fld"><span>description</span>
        <input id="lab-desc" placeholder="one sentence the model reads"
          autocomplete="off"></label>
      <label class="fld"><span>icon</span>
        <select id="lab-icon">${
          ICONS.map((n) => `<option value="${n}">${n}</option>`).join("")}</select></label>
      <div class="fld"><span>arguments the model may pass</span>
        <div id="lab-args">${argRow()}</div>
        <button type="button" class="btn btn-tertiary btn-sm"
          onclick="labAddArg()">${icon("plus", "ic-lead")}Add an argument</button></div>
      <label class="fld"><span>code body &mdash; paste it here</span>
        <textarea id="lab-body" rows="14" spellcheck="false"
          placeholder="def run(**kwargs) -> str:">${esc(BLANK_BODY)}</textarea></label>
      <div class="provactions">
        ${uiButton("Create the tool", {level: "primary", onclick: "labCreate()"})}
        ${uiButton("Cancel", {level: "tertiary", onclick: "closeDialog()"})}</div>
      <div id="lab-err"></div>`,
      { wide: true, label: "Build a tool" });
  };

  window.labAddArg = () => {
    const host = document.getElementById("lab-args");
    if (host) host.insertAdjacentHTML("beforeend", argRow());
  };

  window.labDropArg = (btn) => {
    const row = btn && btn.closest ? btn.closest(".arg-row") : null;
    if (row) row.remove();
  };

  window.labCreate = async () => {
    const val = (id) => (document.getElementById(id) || {}).value || "";
    // A refusal has to be impossible to miss: the reason used to be a faint
    // line at the bottom of the dialog, which reads as "nothing happened".
    const err = (msg) => {
      const el = document.getElementById("lab-err");
      if (el) el.innerHTML = uiNotice("failed", esc(msg));
    };

    // The argument shape is assembled from the rows rather than typed as JSON.
    // A schema is something a page can build; nobody should have to write one by
    // hand, and a typo in one is a tool that never gets called.
    const properties = {};
    const required = [];
    document.querySelectorAll("#lab-args .arg-row").forEach((row) => {
      const name = (row.querySelector(".arg-name").value || "").trim();
      if (!name) return;
      const type = row.querySelector(".arg-type").value;
      const desc = (row.querySelector(".arg-desc").value || "").trim();
      properties[name] = desc ? { type, description: desc } : { type };
      if (row.querySelector(".arg-req").checked) required.push(name);
    });

    try {
      const res = await fetch("/api/toolbox/lab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: val("lab-id").trim(),
          description: val("lab-desc").trim(),
          icon: val("lab-icon") || "tools",
          schema: { type: "object", properties, required },
          body: val("lab-body"),
        }),
      });
      const data = await res.json();
      if (data.error) { err(data.error); return; }
      closeDialog();
      note = `${data.name} created — give it to a seat`;
      await load();
      location.hash = "#tools/market";
    } catch (e) {
      err(String(e));
    }
  };

  VIEWS.tools = (d, sub) => {
    const tabs = uiTabs([
      { label: "Available", href: "#tools", on: !sub },
      { label: "Market", href: "#tools/market", on: sub === "market" },
      { label: "LAB", href: "#tools/lab", on: sub === "lab" },
    ]);
    if (sub === "market") return tabs + market();
    if (sub === "lab") return tabs + labTab();
    return tabs + base(d, sub);
  };
})();
