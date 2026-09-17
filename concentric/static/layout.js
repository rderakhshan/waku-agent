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
