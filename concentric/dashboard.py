"""Serve waku's dashboard over Irina — the existing UI, pointed at the department.

    python -m concentric.dashboard        # http://localhost:7778

No new view, no new endpoint, no change to waku. The dashboard is home-driven:
every panel reads `settings.home`, and the chat talks to one shared agent. So
this launcher does two things BEFORE waku's dashboard is imported:

  1. points WAKU_HOME at Irina's seat home, so Overview / Loop / Gateway /
     Memory / Tools / Database / Ops all read her state. Because a child's events
     are forwarded to its parent's observer, her trace and her usage ledger
     already contain the WHOLE department's activity — so the Loop and Ops views
     show the delegation tree and the true spend with no frontend change.
  2. swaps browser_agent.get_agent / rebuild for the department's Irina seat, so
     a message in the dock delegates for real instead of running a bare Waku.

The dependency still points one way (concentric -> waku). That is why the swap
lives here and not in browser_agent.py: waku must not learn about the department.
"""

from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path

from concentric import MODEL, PROVIDER, SMALL_MODEL, seat_home

# waku's startup banner contains a '→', and Windows' default console codec
# (cp1252) cannot encode it — the server died on that print before it served a
# single request. Fix our own stdout rather than pass -X utf8 and hope.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass

# Before anything imports waku.config: load_dotenv() does not override an env var
# that is already set, so these win over the developer's .env and the department
# and the dashboard agree on one provider, one model and one home.
os.environ.setdefault("WAKU_HOME", str(seat_home("irina")))
os.environ.setdefault("WAKU_PROVIDER", PROVIDER)
os.environ.setdefault("WAKU_MODEL", MODEL)
os.environ.setdefault("WAKU_SMALL_MODEL", SMALL_MODEL)
# 7778 so this never collides with `make dashboard` (7777).
os.environ.setdefault("WAKU_DASHBOARD_PORT", "7778")

from concentric.run import DEFAULT_CONFIG, build_department  # noqa: E402
from waku.ops import browser_agent  # noqa: E402

IRINA = "irina"
_department = None


def _config() -> dict:
    """The department config, steered by the live Settings so the dashboard's
    Models page (which writes WAKU_PROVIDER / WAKU_MODEL and then calls rebuild)
    actually changes the department's brain. A blank env value keeps the default."""
    from waku.config import load_settings

    settings = load_settings()
    config = dict(DEFAULT_CONFIG)
    for field in ("provider", "model", "small_model"):
        value = getattr(settings, field, "")
        if value:
            config[field] = value
    return config


def _build_irina():
    global _department
    _department = build_department(config=_config(), conn_factory=_cross_thread)
    return _department.seat_for(IRINA)


def _cross_thread(home):
    """The dashboard is a ThreadingHTTPServer: a seat is built on the thread of
    whichever request first chatted, then reused by later requests on other
    threads. waku's own browser agent opens its connection the same way."""
    from waku.db import connect

    return connect(home, check_same_thread=False)


def get_agent():
    """Stand-in for browser_agent.get_agent(): the department's Irina seat."""
    if browser_agent._agent is None:  # noqa: SLF001 — we are the factory here
        seat = _build_irina()
        session_id = browser_agent.resume_or_new_session(seat.conn)
        seat.session.session_id = session_id
        browser_agent._dashboard_session = session_id  # noqa: SLF001
        browser_agent._agent = seat  # noqa: SLF001
    return browser_agent._agent  # noqa: SLF001


def rebuild():
    """Stand-in for browser_agent.rebuild(): swap in a freshly configured
    department. On failure the old seat keeps running, same contract as waku's."""
    with browser_agent.agent_lock:
        old = browser_agent._agent  # noqa: SLF001
        try:
            seat = _build_irina()
            seat.session.session_id = (
                old.session.session_id if old is not None
                else browser_agent.resume_or_new_session(seat.conn))
            browser_agent._dashboard_session = seat.session.session_id  # noqa: SLF001
            browser_agent._agent = seat  # noqa: SLF001
        except (Exception, SystemExit) as exc:  # get_client raises SystemExit
            browser_agent._agent = old  # noqa: SLF001
            return str(exc)
    if old is not None:
        old.close()
    return None


# Patch BEFORE waku.ops.dashboard imports these names (dashboard.py binds
# `get_agent` at import time, so a later patch would not reach it).
browser_agent.get_agent = get_agent
browser_agent.rebuild = rebuild


def department_payload() -> dict:
    """Kept for callers that only want the topology; collect.py owns the real one."""
    from concentric.collect import department_payload as build

    return build()


# Injected into waku's shell in memory. The files on disk are never touched, so
# the stock dashboard (7777) and the tests that guard it are unaffected.
#
# There is no Department rail item: the department is the second tab of the
# Overview page (see department.js), so the rail keeps one entry for both.
_SCRIPT = ('<script src="/theme.js"></script>\n'
           '<script src="/home.js"></script>\n'
           '<script src="/observation.js"></script>\n'
           '<script src="/department.js"></script>\n')
# After main.js, because it re-wires the resizer main.js has just wired.
_AFTER = '<script src="/layout.js"></script>\n'
# The sidebar mark is a CSS mask pointing at waku's svg, so the URL lives in
# style.css and cannot be swapped by editing markup. A later stylesheet wins at
# equal specificity, so one rule at the end of <head> repoints it. themes.css is
# linked last of all: a chosen theme has to beat both waku's tokens and ui.css.
_BRAND = ('<style>\n'
          '.r-top .mark{-webkit-mask:url(/irina-mark.svg) center/contain no-repeat;'
          'mask:url(/irina-mark.svg) center/contain no-repeat}\n'
          '</style>\n'
          '<link rel="stylesheet" href="/ui.css">\n'
          '<link rel="stylesheet" href="/themes.css">\n')


def theme_names() -> list[str]:
    """The themes themes.css defines, read out of it rather than listed twice."""
    css = (Path(__file__).parent / "static" / "themes.css").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'\[data-irina-theme="([^"]+)"\]', css)))


def _picker() -> str:
    options = "".join(f'<option value="{name}">{name}</option>' for name in theme_names())
    return ('<div class="r-bottom">\n'
            '<label class="irina-theme" title="Dashboard theme">'
            '<span class="irina-theme-lbl">Theme</span>'
            f'<select id="irina-theme"><option value="">Default</option>{options}</select>'
            '</label>\n')


# The rail's folds: a heading you click, and the pages it holds. Order is the
# order the rail lists them in.
_FOLDS = (
    ("llmops", "LLMOps", ("gateway", "loop", "graph", "memory", "tools",
                          "database", "ops", "compare/models", "compare/memory")),
    ("setup", "Setup", ("models", "connections", "settings")),
)


def _fold(html: str, key: str, label: str, pages: tuple[str, ...]) -> str:
    """Turn a heading and the rows under it into a fold.

    The heading keeps the type and the rule it already had; it gains a caret, a
    click and aria-expanded. Its rows gain data-grp so the toggle can find them,
    and `hidden` so they are gone on the FIRST paint rather than a moment after
    layout.js runs — the state lives in the markup, not in a script that has not
    run yet. Folds ship closed: the point of one is a short rail."""
    first = f'<a href="#{pages[0]}"'
    if first not in html:
        return html
    html = html.replace(
        first,
        f'<div class="r-grp r-fold" id="{key}" role="button" tabindex="0" '
        f'aria-expanded="false" aria-controls="nav">{label}'
        f'<i class="r-fold-rule" aria-hidden="true"></i>'
        f'<i class="r-caret" aria-hidden="true"></i></div>\n  '
        f'<a data-grp="{key}" hidden href="#{pages[0]}"', 1)
    for page in pages[1:]:
        html = html.replace(f'<a href="#{page}"',
                            f'<a data-grp="{key}" hidden href="#{page}"', 1)
    return html


def _rail(html: str) -> str:
    """Home above the Work Desk, and the rest of the rail behind two folds.

    waku's rail has no nesting beyond its section headings, so a fold IS the
    heading it already draws — same type, same rule — plus a caret and a click.
    Nothing about the pages themselves changes: only whether the rail is showing
    them, which is why this is string surgery on the shell and not a single edit
    to a view.

    The anchors stay DIRECT children of <nav>: `.rail > a` is what styles them, so
    wrapping them in a container would take their look away. Each carries its own
    hidden state instead, and layout.js toggles that."""
    # The headings the folds replace. "System" held the cockpit pages and "Arena"
    # the two races — both become LLMOps. "Setup" becomes a fold of its own.
    html = html.replace('<div class="r-grp">System</div>', "", 1)
    html = html.replace('<div class="r-grp">Arena</div>', "", 1)
    html = html.replace('<div class="r-grp">Setup</div>', "", 1)
    # Home is new. The Work Desk keeps its own row and its monogram — it is the
    # page both tabs live on, so it is named for the page, not for one of them.
    html = html.replace(
        '<a href="#overview" data-v="overview" data-short="O" aria-label="Overview">'
        '<span class="lbl">Overview</span></a>',
        '<a href="#home" data-v="home" data-short="H" aria-label="Home">'
        '<span class="lbl">Home</span></a>\n  '
        '<a href="#overview" data-v="overview" data-short="W" aria-label="Work Desk">'
        '<span class="lbl">Work Desk</span></a>', 1)
    # The Observation Lab is a page this launcher adds rather than one waku ships,
    # so its row is inserted rather than retagged. It is marked as a fold member
    # here because _fold() only retags rows that already exist in the shell.
    html = html.replace(
        '<a href="#compare/models"',
        '<a data-grp="llmops" hidden href="#observation" data-v="observation" '
        'data-short="L" aria-label="Observation Lab">'
        '<span class="lbl">Observation Lab</span></a>\n  '
        '<a href="#compare/models"', 1)
    for key, label, pages in _FOLDS:
        html = _fold(html, key, label, pages)
    return html


def _inject(html: str) -> str:
    """Rename the shell to Irina, give it her mark, a theme picker and the
    department view. Additive and in-memory; waku's index.html is never written."""
    html = re.sub(r"<title>.*?</title>", "<title>Irina</title>", html, count=1)
    html = html.replace('href="/static/waku-mark.svg"', 'href="/irina-mark.svg"', 1)
    html = html.replace('<span class="r-name">WAKU</span>',
                        '<span class="r-name">IRINA</span>', 1)
    html = _rail(html)
    # The head's initial text, before the router writes it. Without this the page
    # flashes "Overview" for the first frame.
    html = html.replace('<h1 id="title">Overview</h1>',
                        '<h1 id="title">Work Desk</h1>', 1)
    html = html.replace('<div class="r-bottom">', _picker(), 1)
    html = html.replace("</head>", _BRAND + "</head>", 1)
    html = html.replace('<script src="/static/js/main.js"></script>',
                        _SCRIPT + '<script src="/static/js/main.js"></script>'
                        + _AFTER, 1)
    return html


# A browser that reloads, navigates, or closes a tab mid-response leaves the
# socket dead, and writing to it raises. waku already treats that as benign in
# four places — `chat_stream` catches it with the note "the browser navigated
# away mid-stream — fine" — but its `_send` does not, so every abandoned poll
# prints a traceback to the console the reader is watching.
#
# The dashboard polls /api/data every five seconds and /api/events every 450ms,
# so an abandoned connection is routine rather than exceptional. Swallowing it
# here covers this launcher's route and waku's, without editing waku.
ABORTED = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)

# One batch at a time. Two tabs pressing the button would otherwise start two
# runs, and the reader would pay for both without seeing either finish.
_batch_lock = threading.Lock()


def _handler_class():
    """waku's request handler, plus three routes for the department view.

    Everything else falls through to waku's own handler, so the stock dashboard
    behaviour is exactly preserved."""
    import json

    from waku.ops import dashboard as wd

    class DepartmentHandler(wd.Handler):
        def _frontend(self, body: bytes, ctype: str) -> None:
            """Send a file that must never be cached.

            waku's `_send(no_cache=True)` sets `no-cache, must-revalidate` — and
            no ETag and no Last-Modified. A cache with nothing to revalidate
            against has no way to check, so a browser may keep serving the copy
            it holds and an edited file looks unchanged after an ordinary reload.
            That has cost this project several rounds of "the change is not
            there" when the change was on disk the whole time.

            `no-store` removes the decision rather than asking for it: the file
            is fetched every time, and a hard reload stops being load-bearing.
            """
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.end_headers()
            try:
                self.wfile.write(body)
            except ABORTED:
                pass

        def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler's name
            path = self.path.split("?", 1)[0]
            if path == "/department.js":
                body = (Path(__file__).parent / "static" / "department.js").read_bytes()
                self._frontend(body, "text/javascript")
                return
            if path == "/home.js":
                body = (Path(__file__).parent / "static" / "home.js").read_bytes()
                self._frontend(body, "text/javascript")
                return
            if path == "/observation.js":
                body = (Path(__file__).parent / "static" / "observation.js").read_bytes()
                self._frontend(body, "text/javascript")
                return
            if path == "/irina-mark.svg":
                body = (Path(__file__).parent / "static" / "irina-mark.svg").read_bytes()
                self._frontend(body, "image/svg+xml")
                return
            if path == "/ui.css":
                body = (Path(__file__).parent / "static" / "ui.css").read_bytes()
                self._frontend(body, "text/css")
                return
            if path == "/themes.css":
                body = (Path(__file__).parent / "static" / "themes.css").read_bytes()
                self._frontend(body, "text/css")
                return
            if path == "/theme.js":
                body = (Path(__file__).parent / "static" / "theme.js").read_bytes()
                self._frontend(body, "text/javascript")
                return
            if path == "/layout.js":
                body = (Path(__file__).parent / "static" / "layout.js").read_bytes()
                self._frontend(body, "text/javascript")
                return
            if path == "/":
                html = (wd.STATIC / "index.html").read_text(encoding="utf-8")
                self._send(_inject(html).encode("utf-8"),
                           "text/html; charset=utf-8", no_cache=True)
                return
            if path == "/api/data":
                from concentric.collect import collect_department

                try:
                    self._send(json.dumps(collect_department()).encode("utf-8"),
                               "application/json")
                except ABORTED:
                    pass
                return
            try:
                super().do_GET()
            except ABORTED:
                pass

        def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler's name
            """The Lab's run button. Everything else falls through to waku.

            Server-sent events rather than one blocking request, because a batch
            takes minutes: a plain POST would time out and the reader would watch
            a spinner with nothing behind it. This mirrors /api/compare/stream,
            which is the arena's version of the same idea.
            """
            if self.path.split("?", 1)[0] != "/api/metrics/run":
                try:
                    super().do_POST()
                except ABORTED:
                    pass
                return

            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def emit(kind: str, payload: dict) -> None:
                try:
                    line = json.dumps({"kind": kind, **payload}, default=str)
                    self.wfile.write(f"data: {line}\n\n".encode())
                    self.wfile.flush()
                except ABORTED:
                    pass  # the reader navigated away mid-run — the run finishes

            if not _batch_lock.acquire(blocking=False):
                emit("error", {"message": "a batch is already running"})
                return
            try:
                from concentric import metrics

                emit("start", {"limit": metrics.BATCH_LIMIT,
                               "calls": metrics.estimate_calls(
                                   metrics.context().get("events") or [])})
                record = metrics.run(
                    limit=metrics.BATCH_LIMIT,
                    on_progress=lambda done, total: emit(
                        "progress", {"done": done, "of": total}))
                emit("done", {"ran_at": record["ran_at"],
                              "scored": record["scored"],
                              "values": record["values"]})
            except Exception as exc:  # noqa: BLE001 — surface it, never 500
                emit("error", {"message": f"{type(exc).__name__}: {exc}"})
            finally:
                _batch_lock.release()

    return DepartmentHandler


def _record_once(reason: str) -> int | None:
    """Take one snapshot of the registry. Returns the snapshot id, or None.

    Never raises: the recorder runs on a timer and a failure there must not take
    the dashboard down with it. A missed snapshot is a gap in a chart; a dead
    server is a dead server.
    """
    try:
        from concentric import history, metrics

        conn = history.connect()
        try:
            # One context, not two: it reads every seat's SQLite file, and asking
            # for it twice doubled the cost of every snapshot.
            ctx = metrics.context()
            registry = metrics.compute(ctx)
            turns = sum(1 for t in metrics._turns_of(ctx.get("events") or []) if len(t) > 1)
            snapshot = history.record(registry, metrics.AGG, reason=reason,
                                      turns=turns, conn=conn)
            history.prune(conn)
            return snapshot
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — see the docstring
        return None


def _start_recorder() -> int:
    """Snapshot the registry on a timer, so the history accumulates on its own.

    The interval is `WAKU_METRICS_EVERY` minutes, default 15. Fifteen minutes is
    four readings an hour: fine enough that a change has a time, coarse enough
    that a day is a hundred rows rather than seventeen thousand.

    The first snapshot is taken immediately, so the page has a baseline from the
    moment it starts rather than from a quarter of an hour later.
    """
    import threading
    import time

    minutes = int(os.getenv("WAKU_METRICS_EVERY", "15") or "15")
    if minutes <= 0:
        return 0

    def loop() -> None:
        while True:
            _record_once("timer")
            time.sleep(minutes * 60)

    threading.Thread(target=loop, name="metrics-recorder", daemon=True).start()
    return minutes


def main() -> None:
    from concentric import roster
    from waku.ops import dashboard as wd

    wd.Handler = _handler_class()   # before serve() binds it to the server
    print(f"Department dashboard - {len(roster.SEATS)} seats, Irina at "
          f"{seat_home(IRINA)}")
    every = _start_recorder()
    if every:
        print(f"Metrics history - a snapshot every {every} min, "
              f"into {seat_home(IRINA).parent.parent / 'metrics.db'}")
    wd.main()


if __name__ == "__main__":
    main()
