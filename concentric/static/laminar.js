// ---- Laminar.
//
// Laminar's own trace and eval UI, embedded as a page in the rail.
//
// It cannot live inside #view: main.js replaces #view's innerHTML on the 5s
// refresh, and re-inserting an <iframe> reloads it — the page would blink and
// lose its state every five seconds. So the frame lives in a panel of its own,
// positioned over #view and shown only while this page is the selected one.
//
// The proxy in dashboard.py serves it from Irina's own origin, which is what
// makes the theme bridge possible: same-origin means we can reach into the
// frame's document. Laminar is Tailwind v4, so its real knobs are the
// `--color-surface-*` and `--color-foreground-*` scales — rebuild those from
// Irina's palette and the whole UI follows. No fork, no rebuild.
(function () {
  "use strict";

  const ID = "laminar-panel";
  const STYLE_ID = "irina-theme-bridge";

  const PLACEHOLDER = `<p class="lab-quiet">Laminar opens in the panel over this
    area. If it stays empty, the stack is not running — start it with
    <code>laminar\\run.ps1</code>, then reload.</p>`;

  // --- reading Irina's palette ------------------------------------------------
  //
  // A custom property computes to the token it was written as, not a colour —
  // `color-mix(...)` comes back verbatim. Setting `color` on a probe makes the
  // browser resolve it, and a canvas makes the result sRGB whatever syntax it
  // arrived in. Only the legacy triplet names need this; the scale below is
  // built from Irina's own tokens with color-mix, so it never has to be parsed.

  const probe = document.createElement("span");
  probe.setAttribute("aria-hidden", "true");
  probe.style.cssText = "position:absolute;left:-9999px;top:0;width:0;height:0";
  // It has to be IN the document: custom properties are inherited, and a
  // detached node inherits nothing, so every read would come back empty.
  document.body.appendChild(probe);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;

  function toRgb(text) {
    const m = /^rgba?\(([^)]+)\)/.exec(text);
    if (m) {
      const p = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
      if (p.length >= 3) return p.slice(0, 3);
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = "#000";
    ctx.fillStyle = text; // invalid leaves the previous value
    ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2]];
  }

  function hslTriplet(rgb) {
    const [r0, g0, b0] = rgb.map((v) => v / 255);
    const max = Math.max(r0, g0, b0);
    const min = Math.min(r0, g0, b0);
    const l = (max + min) / 2;
    const d = max - min;
    let h = 0;
    let s = 0;
    if (d) {
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r0) h = (g0 - b0) / d + (g0 < b0 ? 6 : 0);
      else if (max === g0) h = (b0 - r0) / d + 2;
      else h = (r0 - g0) / d + 4;
      h *= 60;
    }
    return `${Math.round(h)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
  }

  // Laminar still reads a few legacy names through `hsl(var(--x))`, so those
  // need the `H S% L%` form rather than a colour.
  const TRIPLETS = {
    "--background": "--surface-bg",
    "--card": "--surface-paper",
    "--popover": "--surface-paper",
    "--secondary": "--surface-raised",
    "--muted": "--surface-raised",
    "--accent": "--surface-raised",
    "--destructive": "--bad",
    "--border": "--rule",
    "--input": "--rule",
    "--ring": "--accent",
    "--chart-1": "--chart-1",
    "--chart-2": "--chart-2",
    // The sidebar keeps a palette of its own — shadcn's sidebar reads
    // `hsl(var(--sidebar-*))`, not the surface scale, so it stayed dark while
    // everything around it followed.
    "--sidebar-background": "--surface-paper",
    "--sidebar-primary": "--accent",
    "--sidebar-accent": "--surface-raised",
    "--sidebar-border": "--rule",
    "--sidebar-ring": "--accent",
  };

  // Every text token, flat black. Laminar gets its hierarchy from a foreground
  // scale plus opacity classes (`text-foreground/70`), which is what read as
  // grey on Irina's light ground; one colour is the request, so one colour is
  // what this sets.
  const TEXT_TOKENS = [
    "--foreground", "--card-foreground", "--popover-foreground",
    "--secondary-foreground", "--accent-foreground", "--muted-foreground",
    "--primary-foreground", "--sidebar-foreground",
    "--sidebar-accent-foreground", "--sidebar-primary-foreground",
  ];

  // --- building the theme -----------------------------------------------------

  const SURFACE = ["00", "100", "150", "200", "250", "300", "350", "400",
    "450", "500", "550", "600", "650", "700", "750", "800"];
  const FOREGROUND = { 50: 0, 100: 0, 200: 8, 300: 15, 400: 22, 500: 35, 600: 50 };

  // `pct` is how far toward `a` the result sits, so `mix(bg, 0, ink)` is bg and
  // `mix(ink, 30, bg)` is a surface a third of the way to the text colour.
  const mix = (a, pct, b) => `color-mix(in srgb, ${a} ${pct}%, ${b})`;

  // Resolve one of Irina's tokens to a concrete sRGB colour, via the probe.
  function resolved(name) {
    probe.style.color = "";
    probe.style.color = `var(${name})`;
    const rgb = toRgb(getComputedStyle(probe).color);
    return rgb ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : null;
  }

  function themeCss() {
    const root = getComputedStyle(document.documentElement);
    const raw = (name) => root.getPropertyValue(name).trim();
    const bg = raw("--surface-bg");
    const ink = raw("--text-ink");
    if (!bg || !ink) return ""; // a theme that does not define the base palette

    const lines = [];
    // Mixing toward the text colour is what makes one scale serve both: it
    // lightens a dark palette and darkens a light one, so the surface steps
    // keep meaning "further from the page".
    SURFACE.forEach((step, i) => {
      lines.push(`--color-surface-${step}:${mix(ink, i * 2, bg)}`);
    });
    for (const [step, pct] of Object.entries(FOREGROUND)) {
      lines.push(`--color-foreground-${step}:${mix(ink, pct, bg)}`);
    }
    const accent = raw("--accent");
    if (accent) {
      lines.push(`--color-primary-100:${mix(accent, 30, bg)}`);
      lines.push(`--color-primary-200:${mix(accent, 20, bg)}`);
      lines.push(`--color-primary-300:${mix(accent, 10, bg)}`);
      lines.push(`--color-primary-400:${accent}`);
    }
    const paper = raw("--surface-paper");
    if (paper) {
      lines.push(`--color-card:${paper}`);
      lines.push(`--color-popover:${paper}`);
    }

    for (const [mine, theirs] of Object.entries(TRIPLETS)) {
      if (!raw(theirs)) continue;
      probe.style.color = "";
      probe.style.color = `var(${theirs})`;
      const rgb = toRgb(getComputedStyle(probe).color);
      if (rgb) lines.push(`${mine}:${hslTriplet(rgb)}`);
    }
    for (const name of TEXT_TOKENS) lines.push(`${name}:0 0% 0%`);
    for (const step of Object.keys(FOREGROUND)) {
      lines.push(`--color-foreground-${step}:#000`);
    }
    const radius = raw("--radius");
    if (radius) lines.push(`--radius:${radius}`);

    const important = lines.map((d) => `${d} !important`).join(";");
    let css = `:root,.dark,.light{${important}}`;
    // The token chain is Laminar's, and the page ground turned out not to be
    // drawn through the surface scale. Painting the two elements that hold it
    // directly is ours, and it is what actually makes the page follow.
    const bgRgb = resolved("--surface-bg");
    if (bgRgb) css += `html,body{background-color:${bgRgb} !important}`;
    // The trace panels are CodeMirror, and CodeMirror themes itself in
    // JavaScript — hardcoded `#c9d1d9` for text and the literal string "gray"
    // for the gutter. No token reaches it, so the text is forced from here.
    css += `.cm-editor,.cm-editor .cm-content,.cm-editor .cm-line,`
      + `.cm-editor .cm-gutters,.cm-editor .cm-gutterElement,`
      + `.cm-editor span{color:#000 !important}`;
    return css;
  }

  // --- the panel --------------------------------------------------------------

  function panel() {
    let el = document.getElementById(ID);
    if (!el) {
      el = document.createElement("div");
      el.id = ID;
      el.innerHTML = '<iframe class="laminar-frame" src="/laminar/" '
        + 'title="Laminar"></iframe>';
      document.body.appendChild(el);
      el.firstChild.addEventListener("load", applyTheme);
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

  // --- the bridge -------------------------------------------------------------

  function applyTheme() {
    const el = document.getElementById(ID);
    const frame = el && el.querySelector(".laminar-frame");
    const doc = frame && frame.contentDocument;
    if (!doc || !doc.head) return;
    const css = themeCss();
    if (!css) return;
    // `!important` because we are overriding a third party's own tokens, some of
    // which it sets on `.dark` — equal specificity, and order is not ours to
    // rely on. The rule is re-applied on a timer, so a rebuild loses it for at
    // most a second.
    let style = doc.getElementById(STYLE_ID);
    if (!style) {
      style = doc.createElement("style");
      style.id = STYLE_ID;
      doc.head.appendChild(style);
    }
    style.textContent = css;
  }

  VIEWS.laminar = () => {
    setTimeout(() => { sync(); applyTheme(); }, 0);
    return PLACEHOLDER;
  };

  window.addEventListener("hashchange", () => setTimeout(sync, 0));
  window.addEventListener("resize", sync);
  window.addEventListener("scroll", sync, true);
  // A theme is one attribute on <html>, so watching that is watching the theme.
  new MutationObserver(() => { sync(); applyTheme(); })
    .observe(document.documentElement, { attributes: true,
      attributeFilter: ["data-irina-theme", "data-theme"] });
  setInterval(() => { sync(); applyTheme(); }, 1000);
})();
