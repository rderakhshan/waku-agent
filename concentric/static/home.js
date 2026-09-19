// ---- Home: the pitch, and the billboard.
//
// The one page in this dashboard that is not a cockpit. Every other page answers
// "what is it doing right now"; this one answers "what is this, and why would I
// want it" before you have to read a trace to find out.
//
// The top block is the pitch. Under it: a billboard that cycles a bank of images
// at random, and beside it the advert in words. The bank is whatever is in
// assets/images/ â€” the dashboard reads the directory, so dropping a file in
// there adds it to the rotation without anyone maintaining a carousel by hand.
//
// The two sit in one row measured to the space left under the hero, so the page
// fits the window rather than asking the reader to scroll past the pitch.
(function () {
  "use strict";

  const DWELL_MS = 5000;   // how long one image stays up
  const FADE_MS = 600;     // the cross-fade, matched to .billboard-img in ui.css

  let bank = null;         // image urls, fetched once
  let current = null;      // the one on screen, so a re-render does not restart it
  let timer = null;
  let routeError = false;  // the server answered, but not with the bank

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
          ${uiButton(icon("dashboard") + "Open the department", {
            level: "primary", onclick: "location.hash='#overview/multi'"})}
          ${uiButton(icon("gauge") + "The cockpit", {
            level: "secondary", onclick: "location.hash='#ops'"})}
        </div>
      </div>
    </section>`;
  }

  function billboard() {
    // No src at all until there is one: an empty src makes the browser fetch the
    // page again, which is a request per render for nothing.
    let inner;
    if (routeError) {
      inner = `<p class="billboard-empty">${icon("refresh", "ic-lead")}This dashboard predates
        the billboard route â€” restart it to pick up <code>dashboard.py</code>.</p>`;
    } else if (bank !== null && !bank.length) {
      inner = `<p class="billboard-empty">${icon("image", "ic-lead")}No images in
        <code>assets/images/</code>.</p>`;
    } else if (current) {
      inner = `<img class="billboard-img" src="${esc(current)}" alt="">`;
    } else {
      inner = `<img class="billboard-img is-out" alt="">`;
    }
    return `<section class="billboard" id="billboard">${inner}</section>`;
  }

  // The row takes the rest of the window, whatever is left after the hero. A
  // fixed aspect ratio could not do this: at this width it is taller than the
  // viewport, which is what made the page scroll. The billboard fills its cell;
  // the advert scrolls inside its own if it ever outgrows the space.
  function fit() {
    const el = document.getElementById("home-cols");
    if (!el) return;
    const top = el.getBoundingClientRect().top;
    const column = document.querySelector("main");
    const bottom = column
      ? Math.min(column.getBoundingClientRect().bottom, window.innerHeight)
      : window.innerHeight;
    el.style.height = `${Math.max(200, Math.round(bottom - top - 16))}px`;
  }

  // The advert beside the frame. No box, no border, no bullets: type alone, at
  // two sizes, so the eye lands on the claim and then reads the sentence that
  // backs it. The words are the README's, because a claim that drifts from the
  // code is the one thing an advertisement here cannot afford.
  function advert() {
    const beat = (big, body) =>
      `<p class="ad-big">${big}</p><p class="ad-body">${body}</p>`;
    return `<aside class="home-ad">
      <p class="ad-kicker">Model risk, as a department</p>
      <p class="ad-abstract-label">Abstract</p>
      <p class="ad-abstract">Irina is a 24-seat department of AI agents for model risk
        management, assembled from the building blocks of a local-first assistant. One chief
        model risk officer delegates to four CFOs, who task nineteen workers; every seat is a
        full agent with its own memory, its own prompt and its own tools. The rules between
        them &mdash; who may task whom, and how deep &mdash; are enforced in code rather than
        asked for in a prompt, and every run is traced, scored and kept on the machine that
        ran it.</p>
      <figure class="ad-figure">
        <img src="/assets/images/workdesk.png"
          alt="The department graph: Irina at the centre, four CFOs around her, workers below."
          onerror="this.closest('figure').hidden = true">
      </figure>
      ${beat(`${icon("users", "ic-lead")}<span class="ad-huge">24</span> seats, one department.`,
             "One chief model risk officer, four CFOs and nineteen workers &mdash; every one a "
             + "full agent with its own memory, its own prompt and its own tools.")}
      ${beat(`${icon("branch", "ic-lead")}The org chart is code.`,
             "Scope is the delegation tool's role enum and depth is a ring counter. A worker "
             + "holds no delegation tool at all, so a forbidden edge is absent, not refused.")}
      ${beat(`${icon("database", "ic-lead")}It runs on your machine.`,
             "One SQLite file per seat, under <code>.waku-concentric/agents/</code>. Traces, "
             + "memory and spend never leave the laptop.")}
      ${beat(`${icon("chart", "ic-lead")}Watch it work, then prove it.`,
             "A live graph beats each seat as it runs, and the chords between CFOs turn solid "
             + "when they compare notes. Deterministic evals and an LLM judge sit behind one "
             + "release gate, so a fix ships with the case that would have caught it.")}
      <p class="ad-pillars">Harness &middot; Loop &middot; Memory &middot; Eval</p>
      <p class="ad-body">DeepSeek by default. Anthropic, OpenAI, Gemini, Kimi, GLM &mdash;
        one line changes the whole department's brain.</p>
    </aside>`;
  }

  // A different image each time, never the one already up. With a bank of one
  // there is nothing to change to, so it just stays.
  function pick() {
    if (!bank || !bank.length) return null;
    if (bank.length === 1) return bank[0];
    let next = current;
    while (next === current) next = bank[Math.floor(Math.random() * bank.length)];
    return next;
  }

  function show(url) {
    const img = document.querySelector(".billboard-img");
    if (!img) return;
    img.classList.add("is-out");
    setTimeout(() => {
      img.src = url;
      // Cached images may not fire load, so the fade back is unconditional.
      img.classList.remove("is-out");
    }, FADE_MS);
  }

  async function loadBank() {
    try {
      const res = await fetch("/api/billboard");
      const data = await res.json();
      bank = data.images || [];
      routeError = false;
    } catch (e) {
      // A server that predates the route answers with the dashboard's own HTML,
      // so res.json() throws. Blaming the directory then sends the reader to
      // the wrong place, which is exactly what happened once.
      routeError = true;
      if (bank === null) bank = [];
    }
  }

  async function start() {
    if (timer !== null) return;   // one timer, however many re-renders
    await loadBank();
    if (!bank.length) return;     // nothing there yet; the next render tries again
    current = pick();
    const img = document.querySelector(".billboard-img");
    if (img) { img.src = current; img.classList.remove("is-out"); }
    timer = setInterval(async () => {
      // Re-read the bank every cycle, not once per page: images dropped into the
      // directory while this page is open should join the rotation on their own.
      await loadBank();
      if (!bank.length) return;
      current = pick();
      show(current);
    }, DWELL_MS);
  }

  VIEWS.home = () => {
    setTimeout(() => { fit(); start(); }, 0);
    return hero()
      + `<section class="home-cols" id="home-cols">${billboard()}${advert()}</section>`;
  };

  window.addEventListener("resize", fit);
})();
