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
_RAIL = ('<div class="r-grp">Department</div>\n'
         '<a href="#department" data-v="department" data-short="D" '
         'aria-label="Department"><span class="lbl">Department</span></a>\n')
_SCRIPT = ('<script src="/theme.js"></script>\n'
           '<script src="/department.js"></script>\n')
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


def _inject(html: str) -> str:
    """Rename the shell to Irina, give it her mark, a theme picker and the
    department view. Additive and in-memory; waku's index.html is never written."""
    html = re.sub(r"<title>.*?</title>", "<title>Irina</title>", html, count=1)
    html = html.replace('href="/static/waku-mark.svg"', 'href="/irina-mark.svg"', 1)
    html = html.replace('<span class="r-name">WAKU</span>',
                        '<span class="r-name">IRINA</span>', 1)
    html = html.replace('<div class="r-grp">System</div>',
                        _RAIL + '<div class="r-grp">System</div>', 1)
    html = html.replace('<div class="r-bottom">', _picker(), 1)
    html = html.replace("</head>", _BRAND + "</head>", 1)
    return html.replace('<script src="/static/js/main.js"></script>',
                        _SCRIPT + '<script src="/static/js/main.js"></script>', 1)


def _handler_class():
    """waku's request handler, plus three routes for the department view.

    Everything else falls through to waku's own handler, so the stock dashboard
    behaviour is exactly preserved."""
    import json

    from waku.ops import dashboard as wd

    class DepartmentHandler(wd.Handler):
        def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler's name
            path = self.path.split("?", 1)[0]
            if path == "/department.js":
                body = (Path(__file__).parent / "static" / "department.js").read_bytes()
                self._send(body, "text/javascript", no_cache=True)
                return
            if path == "/irina-mark.svg":
                body = (Path(__file__).parent / "static" / "irina-mark.svg").read_bytes()
                self._send(body, "image/svg+xml", no_cache=True)
                return
            if path == "/ui.css":
                body = (Path(__file__).parent / "static" / "ui.css").read_bytes()
                self._send(body, "text/css", no_cache=True)
                return
            if path == "/themes.css":
                body = (Path(__file__).parent / "static" / "themes.css").read_bytes()
                self._send(body, "text/css", no_cache=True)
                return
            if path == "/theme.js":
                body = (Path(__file__).parent / "static" / "theme.js").read_bytes()
                self._send(body, "text/javascript", no_cache=True)
                return
            if path == "/":
                html = (wd.STATIC / "index.html").read_text(encoding="utf-8")
                self._send(_inject(html).encode("utf-8"),
                           "text/html; charset=utf-8", no_cache=True)
                return
            if path == "/api/data":
                from concentric.collect import collect_department

                self._send(json.dumps(collect_department()).encode("utf-8"),
                           "application/json")
                return
            super().do_GET()

    return DepartmentHandler


def main() -> None:
    from concentric import roster
    from waku.ops import dashboard as wd

    wd.Handler = _handler_class()   # before serve() binds it to the server
    print(f"Department dashboard - {len(roster.SEATS)} seats, Irina at "
          f"{seat_home(IRINA)}")
    wd.main()


if __name__ == "__main__":
    main()
