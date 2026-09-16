"""The delegation edge — the one mechanism waku does not have.

The tool IS the edge. Scope is the tool's `role` enum, re-checked inside `fn`;
depth is the ring counter. At MAX_RING the factory returns `None`, so a worker
physically cannot delegate: the capability is absent, not refused.

`wants_notify=True` is waku's tool-streaming seam (tools/registry.py): the loop
passes its observer through as `_notify`, so the child's events surface at the
parent's observer, stamped with the child's identity. That is what makes the
whole tree visible from one place.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from concentric import roster
from waku.tools.registry import Tool


def _edge_tool(name: str, description: str, allowed: tuple[str, ...],
               seat_for: Callable[[str], Any]) -> Tool:
    def fn(role: str, task: str, _notify=None) -> str:
        if role not in allowed:
            return "ERROR: out of scope"
        # stream=True so a delegated seat's text reaches the same observer as
        # the parent's. Clients without streaming ignore it (waku checks).
        return seat_for(role).respond(task, observer=_notify, stream=True).reply

    return Tool(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": list(allowed),
                         "description": "which seat to hand the task to"},
                "task": {"type": "string",
                         "description": "the task, self-contained and specific"},
            },
            "required": ["role", "task"],
        },
        fn=fn,
        wants_notify=True,
    )


def make_delegate(spec: roster.SeatSpec, *, seat_for: Callable[[str], Any]) -> Tool | None:
    """The vertical edge: one level down, to the seats this role owns."""
    if spec.ring >= roster.MAX_RING:
        return None  # a worker is a leaf: no delegate tool is registered at all
    allowed = roster.children(spec.role)
    if not allowed:
        return None
    return _edge_tool("delegate",
                      f"Hand a task to a seat you own: {', '.join(allowed)}.",
                      allowed, seat_for)


def make_peer(spec: roster.SeatSpec, *, seat_for: Callable[[str], Any]) -> Tool | None:
    """The lateral edge: the other seats at your own round table only."""
    allowed = roster.peers(spec.role)
    if not allowed:
        return None
    return _edge_tool("consult_peer",
                      f"Ask a peer at your own round table: {', '.join(allowed)}.",
                      allowed, seat_for)
