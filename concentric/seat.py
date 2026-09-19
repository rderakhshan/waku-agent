"""One seat = one configured Waku: its own memory, prompt, model and tools.

Identity is not stored inside waku. It is pushed into four seams waku already
has: `home` (memory), `SOUL.md` (the prompt), the filtered `ToolRegistry`
(tools), and an observer that stamps role/ring/parent on every event — so the
concentric graph can be rebuilt from the event stream alone.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from concentric import roster, seat_home
from concentric.delegate import make_delegate, make_peer
from waku.app import Waku
from waku.config import Settings
from waku.loop.agent import LoopResult, Observer

# What every seat may do before the graph's own tools are added. Deliberately
# small: this prototype is proving the edges, not the domain toolset.
BASE_TOOLS = ("save_note", "manage_memory")


def _soul(spec: roster.SeatSpec) -> str:
    return (
        f"You are {spec.title} — a seat in a model-risk department.\n"
        f"Role: {spec.role} (ring {spec.ring}).\n"
        f"Mandate: {spec.mandate}\n\n"
        "Stay inside your mandate. When a task belongs to another seat, hand it "
        "over with your delegation tool instead of answering it yourself. Be "
        "concise, and say plainly what you did and what you could not do."
    )


@dataclass
class Seat:
    """A configured waku agent plus the identity the graph needs."""

    spec: roster.SeatSpec
    app: Waku

    def _stamp(self, outer: Observer | None) -> Observer:
        def observe(kind: str, event: dict) -> None:
            # `**event` last: an inner seat's stamp survives an outer one, so
            # every event is attributed to the seat that emitted it.
            event = {"role": self.spec.role, "ring": self.spec.ring,
                     "parent": self.spec.parent, **event}
            if outer is not None:
                outer(kind, event)
        return observe

    def respond(self, task: str, observer: Observer | None = None,
                source: str = "cli", stream: bool = False,
                session_id: str | None = None, **kwargs) -> LoopResult:
        # A Seat stands in wherever a Waku does, so it must accept every argument
        # Waku.respond does — the dashboard passes source="dashboard" and
        # stream=True, and a narrower signature broke the dock with a TypeError.
        # Anything unrecognised is forwarded, and Waku.respond rejects it there.
        #
        # `session_id` is the one argument waku does not know: it is consumed
        # here to group a trace, and never forwarded.
        from concentric import tracing

        # A ring-0 seat is never reached from below — workers cannot name irina —
        # so it is where a trajectory begins. `in_trajectory()` stops the CLI
        # path (Department.run opens one, then calls down) from opening a second,
        # and it is what makes the dashboard's direct call to Irina trace too.
        if self.spec.ring == 0 and not tracing.in_trajectory():
            return self._run_trajectory(task, observer, source, stream,
                                        session_id, kwargs)
        return self._turn(task, observer, source, stream, kwargs)

    def _turn(self, task, observer, source, stream, kwargs) -> LoopResult:
        from concentric import tracing

        with tracing.seat(self.spec.role, ring=self.spec.ring,
                          parent=self.spec.parent, source=source):
            result = self.app.respond(task, observer=self._stamp(observer),
                                      source=source, stream=stream, **kwargs)
            tracing.set_output(result.reply)
            return result

    def _run_trajectory(self, task, observer, source, stream, session_id,
                        kwargs) -> LoopResult:
        """One trajectory: the trace, and the local index row that points at it.

        The counts cannot be read off the reply, so they come from the event
        stream — the same one the CLI prints, which is the only place the edges
        are visible.
        """
        from concentric import history, tracing

        tracing.init()
        # An explicit id wins; otherwise waku's conversation id, so the dashboard
        # groups too — it calls this seat directly and never passes one.
        session = session_id or _session_of(self.app)
        started = time.monotonic()
        seats: list[str] = []
        handoffs = 0
        events: list[dict] = []

        def watch(kind: str, event: dict) -> None:
            nonlocal handoffs
            role = event.get("role")
            if role and role not in seats:
                seats.append(role)
            if kind == "tool":
                # The whole event, not just the edge: `output` is what tells a
                # hand-off that came back empty from one that answered, and the
                # graph rules need it.
                events.append({"tool": event.get("tool"),
                               "args": event.get("args") or {},
                               "output": event.get("output"), "role": role})
                if event.get("tool") in ("delegate", "consult_peer"):
                    handoffs += 1
            if observer is not None:
                observer(kind, event)

        reply = None
        with tracing.trajectory(task, entry=self.spec.role, session_id=session):
            try:
                result = self._turn(task, watch, source, stream, kwargs)
                reply = result.reply
                return result
            finally:
                tracing.flush()
                try:
                    # The trace id is None when Laminar was unreachable; the row
                    # is written either way, so an outage costs the detail and
                    # never the fact. The ask and the answer are kept with it so
                    # a run that went wrong can be run again later.
                    history.record_trajectory(
                        tracing.trace_id(), session_id=session,
                        entry=self.spec.role, seats=seats, handoffs=handoffs,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        task=task, reply=reply, violations=_violations(events))
                except Exception:
                    pass  # the store must never take the run down

    def tool_names(self) -> set[str]:
        return set(self.app.tools._tools)

    def __getattr__(self, name: str):
        # Anything waku's dashboard expects on a Waku — settings, conn, session,
        # tools, memory, mcp_bridge, close, ... — comes from the wrapped agent,
        # so a Seat can stand in wherever a Waku is expected.
        return getattr(self.app, name)


def _stamp_tracer(app: Waku, spec: roster.SeatSpec) -> None:
    """Stamp identity onto this seat's OWN trace events.

    `Seat._stamp` wraps the observer, which is the path events take OUT (to the
    parent, and up to the dashboard). It does not touch the path events take IN
    to the tracer — and `compose()` hands every observer the same dict, so a
    seat's own llm/tool events were landing in its own trace with no `role`.

    Wrapping the tracer closes that: the emitter's events are stamped too, and a
    forwarded child event (already stamped) keeps its own role, because `**event`
    wins over the default. `Waku.respond` reads `self.tracer.event` per call, so
    rebinding it on the instance is enough.
    """
    write = app.tracer.event

    def stamped(kind: str, event: dict) -> None:
        write(kind, {"role": spec.role, "ring": spec.ring, "parent": spec.parent, **event})

    app.tracer.event = stamped


def _session_of(app: Waku) -> str | None:
    """waku's own conversation id.

    It is the same id `chat_log` groups by, so a Laminar session is the
    conversation the dashboard already shows under History — not a second
    notion of "session" invented here.
    """
    session = getattr(app, "session", None)
    return getattr(session, "session_id", None) or None


def _violations(events: list[dict]) -> list[str]:
    """The department's own rules this run broke, by name.

    Checked here rather than at eval time so a bad run is flagged as it happens:
    the index is local, so this works with Laminar down, and the eval later has
    a list of cases instead of a corpus to search.
    """
    from concentric import graph_rules

    return [name for name, hits in graph_rules.violations(events).items() if hits]


def build_seat(spec: roster.SeatSpec, *, config: dict[str, Any],
               seat_for: Callable[[str], Any], client=None,
               root: Path | None = None,
               conn_factory: Callable[[Path], Any] | None = None) -> Seat:
    """Turn one SeatSpec into a live, role-correct Waku. No API call is made.

    `conn_factory` exists for a long-lived seat used from a thread pool — the
    dashboard is a ThreadingHTTPServer, and waku's `connect()` defaults to
    check_same_thread=True, so a seat built in one request thread raised
    "SQLite objects created in a thread can only be used in that same thread"
    when the next request ran the turn on a different thread.
    """
    home = seat_home(spec.role, root)
    home.mkdir(parents=True, exist_ok=True)
    # SOUL.md must exist BEFORE the first respond(): load_soul() writes waku's
    # default persona when the file is missing, which would erase the mandate.
    (home / "SOUL.md").write_text(_soul(spec), encoding="utf-8")

    app = Waku(settings=Settings(home=home, **config), client=client,
               conn=conn_factory(home) if conn_factory else None)
    _stamp_tracer(app, spec)

    # Scope is the registry: a tool the role does not own is never registered,
    # so a seat cannot exceed its remit by asking nicely. What it owns is
    # BASE_TOOLS plus whatever the toolbox grants this role — a file, so the
    # grant is visible and reviewable rather than implied by a prompt.
    from concentric import toolbox

    granted = toolbox.tools_for(spec.role)
    keep = set(BASE_TOOLS) | set(granted)
    for name in list(app.tools._tools):
        if name not in keep:
            del app.tools._tools[name]

    # A generated tool was never in waku's registry, so the ones this seat holds
    # are imported and added here. This is the only place generated code runs.
    for name in granted:
        if name not in app.tools._tools:
            tool = toolbox.make_tool(name)
            if tool is not None:
                app.tools.register(tool)

    for tool in (make_delegate(spec, seat_for=seat_for),
                 make_peer(spec, seat_for=seat_for)):
        if tool is not None:
            app.tools.register(tool)

    return Seat(spec=spec, app=app)
