// ---- Laminar.
//
// Laminar's own trace and eval UI, embedded as a page in the rail.
//
// It cannot live inside #view: main.js replaces #view's innerHTML on the 5s
// refresh, and re-inserting an <iframe> reloads it — the page would blink and
// lose its state every five seconds. So the frame lives in a panel of its own,
// positioned over #view and shown only while this page is the selected one.
//
// Nothing inside it is redrawn here. It is Laminar's UI, and the launcher's
// only job is to get out of its way.
(function () {
  "use strict";

  const ID = "laminar-panel";
  const PLACEHOLDER = `<p class="lab-quiet">Laminar opens in the panel over this
    area. If it stays empty, the stack is not running — start it with
    <code>laminar\\run.ps1</code>, then reload.</p>`;

  function panel() {
    let el = document.getElementById(ID);
    if (!el) {
      el = document.createElement("div");
      el.id = ID;
      el.innerHTML = '<iframe class="laminar-frame" src="/laminar/" '
        + 'title="Laminar"></iframe>';
      document.body.appendChild(el);
    }
    return el;
  }

  function active() {
    return (location.hash || "").replace("#", "").split("/")[0] === "laminar";
  }

  // The panel is fixed and anchored to #view's top-left, but its HEIGHT comes
  // from the content column, not from #view itself: #view is height:auto, so it
  // is only as tall as its content — the placeholder below is one line, and
  // sizing to it made the frame a strip.
  function sync() {
    const el = document.getElementById(ID);
    if (!active()) {
      if (el) el.hidden = true;
      return;
    }
    const host = panel();
    host.hidden = false;
    const box = document.getElementById("view");
    const column = document.querySelector("main");
    if (!box || !column) return;
    const v = box.getBoundingClientRect();
    const c = column.getBoundingClientRect();
    const bottom = Math.min(c.bottom, window.innerHeight);
    host.style.top = `${Math.round(v.top)}px`;
    host.style.left = `${Math.round(v.left)}px`;
    host.style.width = `${Math.round(v.width)}px`;
    host.style.height = `${Math.max(240, Math.round(bottom - v.top - 12))}px`;
  }

  VIEWS.laminar = () => {
    setTimeout(sync, 0);
    return PLACEHOLDER;
  };

  window.addEventListener("hashchange", () => setTimeout(sync, 0));
  window.addEventListener("resize", sync);
  window.addEventListener("scroll", sync, true);
  setInterval(sync, 1000);
})();
