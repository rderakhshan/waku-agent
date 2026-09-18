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

// The rail's folds: each one's pages fold away behind a single row.
//
// waku's rail has no nesting beyond its section headings, so a fold IS the
// heading — same type, same rule — plus a caret and a click. Every fold in the
// markup is picked up by class, so adding another is a change to dashboard.py
// alone; nothing here names a group.
//
// The rows carry their own `hidden`, which is what the server shipped them with,
// so a fold is already closed on the first paint. This file only ever flips that
// attribute and the fold's aria-expanded.
//
// It runs after main.js, so the rail is parsed and main.js has already bound its
// own handlers. The folds do not touch them: main.js lights the current page by
// class on the anchors, and hiding an anchor does not stop that.
(function () {
  const folds = [...document.querySelectorAll(".r-fold")];
  if (!folds.length) return;

  const groups = folds.map((fold) => {
    const key = fold.id;
    const rows = [...document.querySelectorAll(`a[data-grp="${key}"]`)];
    // Which views this fold holds. The first path segment, because two rows can
    // share a view (#compare/models and #compare/memory are both "compare").
    const views = new Set(rows.map(
      (a) => (a.getAttribute("href") || "").slice(1).split("/")[0]));
    const store = `fold:${key}`;

    // The reader's own choice, in memory as well as in storage: sync() needs to
    // put the rail back the way they left it.
    let pref = false;
    try { pref = localStorage.getItem(store) === "1"; }
    catch (e) { /* private mode: the fold simply will not remember */ }

    const set = (open) => {
      fold.setAttribute("aria-expanded", open ? "true" : "false");
      rows.forEach((a) => { a.hidden = !open; });
    };

    const toggle = () => {
      const open = fold.getAttribute("aria-expanded") !== "true";
      pref = open;
      set(open);
      try { localStorage.setItem(store, open ? "1" : "0"); }
      catch (e) { /* private mode */ }
    };

    fold.addEventListener("click", toggle);
    fold.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
    });

    set(pref);   // closed until the reader says otherwise
    return { views, set, pref: () => pref };
  });

  // Each fold follows where you are: forced open on a page it holds, so a page is
  // never hidden behind a closed fold, and otherwise put back to the reader's own
  // choice. Arriving somewhere is not itself a preference — opening on arrival is
  // deliberately not stored, or one visit to Memory would un-shorten the rail for
  // good. Only a click is.
  const sync = () => {
    const view = (location.hash || "").slice(1).split("/")[0];
    groups.forEach((g) => g.set(g.views.has(view) ? true : g.pref()));
  };
  sync();
  window.addEventListener("hashchange", sync);
})();
