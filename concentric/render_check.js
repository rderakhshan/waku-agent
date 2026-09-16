// Headless check for the department view's render functions.
//
//   node concentric/render_check.js [payload.json]
//
// The dashboard's JavaScript has no test runner — a frontend change is normally
// verified in a browser. That is how a real bug reached the panel: the wrapped
// sections handed waku's `table()` a joined string, and `table` maps over its
// second argument (render.js: `rows.map(rowCells)`), so every wrapped view threw
// on render, the panel kept its previous content, and it looked dead.
//
// This executes the view functions with the globals waku's classic scripts share
// stubbed, and its `table` stub throws exactly the way waku's does. It needs
// node, it is not in CI, and it checks the view renders — not that it looks
// right. The browser is still the only judge of that.
const fs = require("fs");

global.VIEWS = { ops: () => "<ops-base>", memory: () => "<memory-base>",
                 gateway: () => "<gateway-base>" };
global.esc = (s) => String(s == null ? "" : s);
global.money = (n) => "$" + (n < 0.01 ? n.toFixed(4) : n.toFixed(2));
global.uiCard = (h) => `<card>${h}</card>`;
global.table = (heads, rows) => {
  if (!Array.isArray(rows)) throw new TypeError("rows.map is not a function");
  return `<tbl cols="${heads.length}" rows="${rows.length}">${rows.join("")}</tbl>`;
};
global.document = {
  getElementById: () => null,
  createElement: () => ({}),
  head: { appendChild: () => {} },
  querySelectorAll: () => [],
};
global.location = { hash: "#department" };
global.setInterval = () => 0;
global.setTimeout = () => 0;
global.fetch = () => Promise.resolve({ json: () => Promise.resolve({ events: [], cursor: 0 }) });

// A payload small enough to read, broad enough to exercise every wrapper.
const FIXTURE = {
  provider: "deepseek", model: "deepseek-v4-pro",
  usage: {
    total_cost: 0.015, calls: 3, total_in: 300, total_out: 150,
    by_seat: [{ seat: "irina", calls: 2, in: 200, out: 100, tool_calls: 1, cost: 0.01 },
              { seat: "cfo-2-validation", calls: 1, in: 100, out: 50, tool_calls: 0, cost: 0.005 }],
    note: "total from the entry seat's ledger",
  },
  db: { seats: [{ seat: "irina", size: 4096, facts: 2, episodes: 1, chat_log: 3 }],
        tables: [], all_tables: [], fts: [], path: "", size: 4096 },
  sessions: [{ seat: "irina", id: "s1", title: "hello", messages: 2,
               last_at: "2026-09-16 12:00:00" }],
  facts: [], episodes: [], chat_log: [], calendar: [], stats: { turns: 1 },
  department: {
    entry: "irina",
    seats: [
      { role: "irina", title: "Irina - Chief Model Risk Officer", ring: 0, parent: "",
        built: true, tools: ["delegate", "manage_memory", "save_note"],
        activity: { seat: "irina", calls: 2, in: 200, out: 100, tool_calls: 1, cost: 0.01 } },
      { role: "cfo-2-validation", title: "CFO-2 - Validation & monitoring", ring: 1,
        parent: "irina", built: true, tools: ["consult_peer", "delegate"],
        activity: { seat: "cfo-2-validation", calls: 1, in: 100, out: 50, tool_calls: 0,
                    cost: 0.005 } },
      { role: "challenger-modeler", title: "Challenger Modeler", ring: 2,
        parent: "cfo-2-validation", built: false, tools: ["consult_peer"], activity: null },
      { role: "data-quality-reviewer", title: "Data-Quality Reviewer", ring: 2,
        parent: "cfo-2-validation", built: false, tools: ["consult_peer"], activity: null },
    ],
    edges: [{ src: "irina", dst: "cfo-2-validation", kind: "delegate" },
            { src: "cfo-2-validation", dst: "challenger-modeler", kind: "delegate" },
            { src: "cfo-2-validation", dst: "data-quality-reviewer", kind: "delegate" }],
  },
};

const payload = process.argv[2]
  ? JSON.parse(fs.readFileSync(process.argv[2], "utf8"))
  : FIXTURE;

eval(fs.readFileSync(require("path").join(__dirname, "static", "department.js"), "utf8"));

const WANT = {
  department: "Seats that have run",
  ops: "Spend by seat",
  memory: "Memory by seat",
  gateway: "Conversations by seat",
};

let failed = false;
for (const [name, marker] of Object.entries(WANT)) {
  const fn = VIEWS[name];
  if (typeof fn !== "function") {
    console.log(`${name.padEnd(11)}: MISSING`);
    failed = true;
    continue;
  }
  try {
    const html = fn(payload, name === "memory" || name === "gateway" ? "overview" : undefined);
    const ok = html.includes(marker);
    console.log(`${name.padEnd(11)}: ok  ${String(html.length).padStart(6)} chars  "${marker}" ${ok}`);
    if (!ok) failed = true;
  } catch (e) {
    console.log(`${name.padEnd(11)}: THREW  ${e.message}`);
    failed = true;
  }
}
process.exit(failed ? 1 : 0);
