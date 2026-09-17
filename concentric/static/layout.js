// Let the chat dock grow to 80% of the page.
//
// waku caps the drag at 680px (main.js: dockMax = Math.min(680, ...)) and holds
// the main view to --main-min (544px in type.css). Together those stop the dock
// at roughly a third of a wide screen, which is where the replies got cramped.
//
// ui.css re-states --main-min, which fixes the CSS clamp. This file fixes the
// DRAG: it re-wires the same handle waku wired, with the cap at 80% of what is
// left after the rail and the handle. It runs after main.js, so both the helper
// and the bootstrap that calls it already exist.
//
// One resizer is enough for both halves: dragging the dock out to 80% leaves the
// main 20%, and dragging it back leaves the main 80%. waku/ is untouched.
(function () {
  const FRACTION = 0.8;
  const MIN_DOCK = 260;
  const rail = document.getElementById("nav");
  const handle = document.getElementById("dock-resizer");
  if (!rail || !handle || typeof wireResizer !== "function") return;

  const dockMax = () => {
    const chrome = rail.getBoundingClientRect().width
      + handle.getBoundingClientRect().width;
    return Math.max(MIN_DOCK, Math.round(FRACTION * (window.innerWidth - chrome)));
  };

  wireResizer("dock-resizer", "--dock-w", "dockW", true, MIN_DOCK, dockMax);

  // A width remembered from before this change can sit above the new cap, and
  // the CSS clamp would then silently disagree with the handle's limit.
  const saved = parseInt(localStorage.getItem("dockW") || "0", 10);
  if (saved > dockMax()) {
    document.documentElement.style.setProperty("--dock-w", dockMax() + "px");
    localStorage.setItem("dockW", String(dockMax()));
  }
})();

// Stop the 5s refresh throwing the reader back to the top of the page.
//
// render() rebuilds #view's innerHTML, which collapses <main> for an instant and
// takes the scroll position down with it. waku knows this — it saves and restores
// main.scrollTop for the views it rebuilds in place (main.js:56, "Rebuilding #view
// innerHTML resets the scroll"). But the branch that handles "overview" and
// "graph" has no such guard, and the department graph lives in overview. So every
// poll jumped the page to the top.
//
// Same save and restore, wrapped around render() rather than edited into it.
// Only for a same-page refresh: the hash is what separates a poll from a
// navigation, and a navigation should land at the top.
//
// Both scroll containers are covered. <main> scrolls on a wide screen
// (style.css: height:100vh; overflow-y:auto), the document scrolls on a narrow
// one (the same rule drops to height:auto). Preserving the wrong one is free.
//
// This file runs after main.js, so render exists. The hashchange listener main.js
// registered keeps the ORIGINAL render — which is what we want, since navigation
// is exactly the case that should not preserve the scroll.
(function () {
  if (typeof render !== "function") return;
  const base = render;
  render = function () {
    const main = document.querySelector("main");
    const hash = location.hash;
    const y = main ? main.scrollTop : 0;
    const winY = window.scrollY;
    base();
    if (location.hash !== hash) return;   // a navigation, not a refresh
    if (main) main.scrollTop = y;
    window.scrollTo(0, winY);
  };
})();

// The LLMOps fold: the cockpit pages fold away behind one row.
//
// waku's rail has no nesting beyond its section headings, so the fold IS the
// heading — same type, same rule — plus a caret and a click. aria-expanded on
// the row is the single source of state: the stylesheet keys off it and so does
// this file, so there is no second copy to drift.
//
// It runs after main.js, so the rail is parsed and main.js has already bound its
// own handlers. The fold does not touch them: main.js lights the current page by
// class on the anchors, and hiding an anchor does not stop that.
(function () {
  const fold = document.getElementById("llmops");
  if (!fold) return;

  // The pages the fold holds. Arriving at one must never leave it hidden behind
  // a closed fold, so these open it.
  const INSIDE = new Set(["gateway", "loop", "graph", "memory", "tools",
                          "database", "ops", "compare"]);
  const KEY = "llmopsOpen";

  // aria-expanded IS the state — the stylesheet hides the pages off it, so
  // setting the attribute is the whole change.
  function set(open) {
    fold.setAttribute("aria-expanded", open ? "true" : "false");
  }

  // The reader's own choice, in memory as well as in storage: reveal() needs to
  // put the rail back the way they left it.
  let pref = false;
  try { pref = localStorage.getItem(KEY) === "1"; } catch (e) { /* private mode */ }
  set(pref);   // closed until the reader says otherwise

  function store(open) {
    pref = open;
    try { localStorage.setItem(KEY, open ? "1" : "0"); }
    catch (e) { /* private mode: the fold simply will not remember */ }
  }

  function toggle() {
    const open = fold.getAttribute("aria-expanded") !== "true";
    set(open);
    store(open);
  }

  fold.addEventListener("click", toggle);
  fold.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
  });

  // The fold follows where you are: forced open on a page it holds, so a page is
  // never hidden behind a closed fold, and otherwise put back to the reader's own
  // choice. Arriving somewhere is not itself a preference — opening on arrival is
  // deliberately not stored, or one visit to Memory would un-shorten the rail for
  // good. Only a click is.
  const reveal = () => {
    const view = (location.hash || "").slice(1).split("/")[0];
    set(INSIDE.has(view) ? true : pref);
  };
  reveal();
  window.addEventListener("hashchange", reveal);
})();
