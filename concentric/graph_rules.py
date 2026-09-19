"""The department's rules, as functions over what a run actually did.

`roster` already knows who may task whom and how deep a seat sits. Until now
those facts were used to *build* the graph — the delegation tool's role enum, the
ring counter — but never to *check* a run against them. This module closes that:
it takes the tool events a run emitted and answers the questions the graph can
answer about itself.

That is the part most agent evals cannot do. A judge can say whether an answer
reads well; it cannot say whether the audit seat was allowed to task a
development worker, because it does not know the org chart. This does, and it
costs nothing to run.
"""

from __future__ import annotations

import json
from typing import Any

from concentric import roster

HANDOFFS = ("delegate", "consult_peer")


def handoffs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The delegation calls in a run — the edges it actually used."""
    return [e for e in events if e.get("tool") in HANDOFFS]


def _edge(event: dict[str, Any]) -> tuple[str, str]:
    return (str(event.get("role") or ""),
            str((event.get("args") or {}).get("role") or ""))


def out_of_scope(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hand-offs to a seat the sender does not own.

    Structurally this cannot happen — the tool's enum is built from
    `roster.allowed`, so an out-of-scope role is not offerable. It is checked
    anyway, because the thing worth catching is a future change that widens the
    enum by accident, and that change would not announce itself.
    """
    bad = []
    for event in handoffs(events):
        frm, to = _edge(event)
        if frm not in roster.BY_ROLE or not to:
            continue
        if to not in roster.allowed(frm):
            bad.append(event)
    return bad


def over_depth(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A hand-off from a seat already at the deepest ring.

    A leaf has no delegation tool at all, so this is absent rather than refused
    — which is exactly why it is worth asserting: it fires only if a leaf ever
    gets a tool it should not have.
    """
    bad = []
    for event in handoffs(events):
        frm, _ = _edge(event)
        if frm in roster.BY_ROLE and roster.ring(frm) >= roster.MAX_RING:
            bad.append(event)
    return bad


def unanswered(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A hand-off that came back empty, or came back as an error."""
    bad = []
    for event in handoffs(events):
        output = str(event.get("output") or "").strip()
        if not output or output.startswith("ERROR"):
            bad.append(event)
    return bad


def repeated(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The same tool called with the same arguments twice in one run.

    The per-run version of the registry's `step_repetition`: a seat asking the
    identical question again is a loop, and the run is the only place it is
    visible.
    """
    seen: set[str] = set()
    bad = []
    for event in events:
        key = json.dumps([event.get("tool"), event.get("args") or {}],
                         sort_keys=True, default=str)
        if key in seen:
            bad.append(event)
        seen.add(key)
    return bad


def violations(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Every rule, checked once. Empty lists mean the run obeyed the graph."""
    return {
        "out_of_scope": out_of_scope(events),
        "over_depth": over_depth(events),
        "unanswered": unanswered(events),
        "repeated": repeated(events),
    }


def clean(events: list[dict[str, Any]]) -> bool:
    return not any(violations(events).values())
