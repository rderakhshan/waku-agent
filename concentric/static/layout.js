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
