"""Laminar tracing for the department — optional, off by default.

One `Department.run()` is one Laminar trace; one `Seat.respond()` is one span;
one `delegate` / `consult_peer` call is one handoff span. That is the whole
mapping: the trajectory, the seats it used, and the edges between them.

Tracing is on by default: every trajectory is recorded as it is created. It
stops only when `IRINA_LAMINAR=off` is set, or the `lmnr` SDK is missing, or no
project key is present, or `Laminar.initialize()` fails — and every helper is
then a no-op, so Irina behaves exactly as it does without this module. Tracing
must never be able to break the loop, and it must never be a hard dependency —
optional things live behind an extra (`[laminar]`).

The store is a separate service (`laminar/` in this repo runs it locally). While
it is down the spans for that window are lost, but the local trajectory index
still records that the run happened — a stopped stack must not erase the fact of
a run.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

# Tracing is ON by default: a run that happened should be recorded without
# anyone remembering a switch. `IRINA_LAMINAR=off` is the only way to stop it.
ENV_FLAG = "IRINA_LAMINAR"
_OFF = {"0", "off", "false", "no"}

# How long to wait before a failed init is tried again. A down server has to
# cost one check a minute, not one per turn.
RETRY_SECONDS = 60.0

# Set once by init(); read by every helper. None means tracing is off.
_Laminar: Any = None
_failed_at: float = 0.0

# How deep the current trajectory is nested. A contextvar, not a global: the
# dashboard is a threaded server, and a shared counter would let one request's
# trajectory make another request think it was already inside one.
_DEPTH: ContextVar[int] = ContextVar("irina_tracing_depth", default=0)


def in_trajectory() -> bool:
    """True when a trajectory is already open on this thread."""
    return _DEPTH.get() > 0


def enabled() -> bool:
    """True once the SDK is imported, a key is present, and init succeeded."""
    return _Laminar is not None


def _disabled() -> bool:
    return (os.environ.get(ENV_FLAG) or "").strip().lower() in _OFF


def _load_env_file() -> None:
    """Make the repo's .env visible here.

    waku loads it too, but not necessarily before the first trajectory, and the
    tracing config must not depend on import order. `override=False` so a real
    environment variable always beats the file.
    """
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def init() -> bool:
    """Import and initialise the SDK once. True when tracing is live.

    Called on every trajectory; after the first success it is a cheap bool
    read, and after a failure it is a cheap bool read until the retry window
    passes. A missing SDK, a missing key or an unreachable server is not an
    error — it just leaves this run untraced, which the local index still
    records.
    """
    global _Laminar, _failed_at
    if _Laminar is not None:
        return True
    if _disabled():
        return False
    if _failed_at and (time.monotonic() - _failed_at) < RETRY_SECONDS:
        return False

    _load_env_file()
    key = (os.environ.get("LMNR_PROJECT_API_KEY") or "").strip()
    if not key:
        _failed_at = time.monotonic()
        return False  # nothing to trace to
    try:
        from lmnr import Laminar
    except Exception:
        _failed_at = time.monotonic()
        return False
    try:
        Laminar.initialize(
            project_api_key=key,
            base_url=os.environ.get("LMNR_BASE_URL", "http://localhost"),
            http_port=int(os.environ.get("LMNR_HTTP_PORT", "8000")),
            grpc_port=int(os.environ.get("LMNR_GRPC_PORT", "8001")),
        )
    except Exception:
        _failed_at = time.monotonic()
        return False
    _Laminar = Laminar
    return True


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None,
         span_type: str = "DEFAULT", tags: list[str] | None = None,
         session_id: str | None = None,
         user_id: str | None = None) -> Iterator[Any]:
    """A Laminar span, or a no-op when tracing is off.

    Entering the span is guarded, so a tracing failure can only ever cost us
    the span, never the work inside it.
    """
    if _Laminar is None:
        yield None
        return
    try:
        cm = _Laminar.start_as_current_span(
            name=name, span_type=span_type, attributes=attributes,
            tags=tags, session_id=session_id, user_id=user_id,
        )
        current = cm.__enter__()
    except Exception:
        yield None
        return
    try:
        yield current
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:
            pass


@contextmanager
def trajectory(task: str, entry: str = "irina",
               session_id: str | None = None,
               user_id: str | None = None) -> Iterator[Any]:
    """The whole run: one trace. `session_id` groups several runs together."""
    token = _DEPTH.set(_DEPTH.get() + 1)
    try:
        with span(f"trajectory.{entry}",
                  {"irina.entry": entry, "irina.task": task[:500]},
                  session_id=session_id, user_id=user_id) as current:
            yield current
    finally:
        _DEPTH.reset(token)


@contextmanager
def seat(role: str, ring: int | None = None, parent: str | None = None,
         source: str = "cli") -> Iterator[Any]:
    """One seat's turn: one span, carrying the identity the graph is built on."""
    attributes: dict[str, Any] = {"irina.role": role, "irina.source": source}
    if ring is not None:
        attributes["irina.ring"] = ring
    if parent:
        attributes["irina.parent"] = parent
    with span(f"seat.{role}", attributes) as current:
        yield current


@contextmanager
def handoff(tool: str, frm: str, to: str, task: str) -> Iterator[Any]:
    """One delegation edge: `delegate` down a ring, or `consult_peer` sideways.

    Typed TOOL because that is what it is — a tool call — which is also what
    makes the edges show up in the dashboard's transcript view.
    """
    with span(f"{tool}:{frm}->{to}",
              {"irina.edge": tool, "irina.from": frm, "irina.to": to,
               "irina.task": task[:500]},
              span_type="TOOL") as current:
        yield current


def trace_id() -> str | None:
    """The current trace's id, or None when tracing is off.

    Read inside the trajectory's `with` block — that is the window where the
    current trace exists, and it is what lets the run be indexed in the local
    store without the store knowing anything about Laminar.
    """
    if _Laminar is None:
        return None
    try:
        current = _Laminar.get_trace_id()
    except Exception:
        return None
    return str(current) if current else None


def set_output(text: str) -> None:
    """Attach a seat's reply to the span it was produced in."""
    if _Laminar is None:
        return
    try:
        _Laminar.set_span_output(text)
    except Exception:
        pass


def flush() -> None:
    """Push what has been recorded. Called at the end of every trajectory.

    `force_flush` is deliberately not used here: it tears the span processor
    down and back up, which is right for a one-shot script and wrong for the
    long-lived dashboard process.
    """
    if _Laminar is None:
        return
    try:
        _Laminar.flush()
    except Exception:
        pass
