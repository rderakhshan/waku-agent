"""Assemble the department and run it.

Seats are built lazily, on first use. That keeps start-up to one SQLite file
instead of twenty-four, and it is also what keeps a later threaded fan-out safe:
a seat built in the thread that uses it owns a connection created in that same
thread (waku's `connect()` is check_same_thread=True).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from concentric import MODEL, PROVIDER, SMALL_MODEL, roster
from concentric.seat import Seat, build_seat
from waku.loop.agent import Observer

# One configuration for all 24 seats. The switches are pinned so the department
# describes its own world instead of inheriting the developer's .env — the same
# reason evals/helpers.make_waku pins them.
DEFAULT_CONFIG: dict[str, Any] = {
    "provider": PROVIDER,
    "model": MODEL,
    "small_model": SMALL_MODEL,
    "max_iterations": 6,
    "max_tokens": 2048,
    "history_turns": 8,
    "apple_calendar": False,
    "google_calendar": False,
    "apple_tools": False,
    "gh_tool": False,
    "experimental": False,
    "graph_workflows": False,
    "semantic_store": "sqlite",
    "episodic_store": "sqlite",
    "otel_endpoint": "",
}


@dataclass
class Department:
    config: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_CONFIG))
    client_factory: Callable[[str], Any] | None = None
    root: Path | None = None
    # How each seat opens its state.db. Left None, waku's default applies
    # (check_same_thread=True), which is right for a single-threaded run. A
    # long-lived seat used from a thread pool needs the cross-thread form —
    # see build_seat's docstring.
    conn_factory: Callable[[Path], Any] | None = None
    # Groups this department's trajectories into one Laminar session. Left None,
    # it is minted on the first run so every turn of this instance shares it.
    session_id: str | None = None
    _seats: dict[str, Seat] = field(default_factory=dict)
    _resolved_session: str | None = field(default=None, init=False, repr=False)

    def seat_for(self, role: str) -> Seat:
        if role not in self._seats:
            self._seats[role] = build_seat(
                roster.BY_ROLE[role],
                config=self.config,
                seat_for=self.seat_for,
                client=self.client_factory(role) if self.client_factory else None,
                root=self.root,
                conn_factory=self.conn_factory,
            )
        return self._seats[role]

    def run(self, task: str, entry: str = "irina",
            observer: Observer | None = None, stream: bool = False,
            session_id: str | None = None) -> str:
        """One trajectory. The seat it enters through opens the trace.

        The trace and its index row live in `Seat.respond`, not here, because
        the dashboard reaches Irina without going through this method — one
        boundary in the seat covers both callers.
        """
        session = session_id or self.session_id or self._resolved_session
        if session is None:
            session = self._resolved_session = f"irina-{datetime.now():%Y%m%d-%H%M%S}"
        return self.seat_for(entry).respond(
            task, observer=observer, stream=stream, session_id=session).reply


def build_department(*, config: dict[str, Any] | None = None,
                     client_factory: Callable[[str], Any] | None = None,
                     root: Path | None = None,
                     conn_factory: Callable[[Path], Any] | None = None) -> Department:
    return Department(config={**DEFAULT_CONFIG, **(config or {})},
                      client_factory=client_factory, root=root,
                      conn_factory=conn_factory)
