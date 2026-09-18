"""Aggregate the department's seats into the shape waku's panels already read.

Every panel in the dashboard renders the payload from waku's `collect()`, and
that payload describes ONE home. The department has 24. So rather than rewrite
panels, this module calls waku's own `collect()` and overlays the home-scoped
keys with aggregates over every seat that has ever run — the same move as
`Seat`, which wrapped one `Waku` so a single-harness API could serve a graph.

One thing must NOT be summed naively: spend. A child's LLM call is written to
its own ledger AND to its parent's, so adding up 24 ledgers counts the deepest
seat three times. The total therefore comes from the entry seat's ledger, which
already contains the whole subtree; the per-seat rows are attribution, and the
payload carries a note saying so.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator

from concentric import ENTRY, STATE_ROOT, roster, seat_home
from waku.ops.pricing import price_for

# What every seat can do, before the graph's own tools are added. Mirrors
# seat.BASE_TOOLS; kept here so listing a seat's tools never builds an agent.
BASE_TOOLS = ("save_note", "manage_memory")

_TOOL_BLURB = {
    "save_note": "Save a durable note.",
    "manage_memory": "Correct or forget a fact.",
    "delegate": "Hand a task to a seat you own — one level down.",
    "consult_peer": "Ask a peer at your own round table.",
}

_FACTS = "id, subject, content, source, created_at"
_EPISODES = "id, happened_at, summary"
_CHAT = "role, content, consolidated, source, session_id, created_at"


def _each_seat() -> Iterator[tuple[str, sqlite3.Connection]]:
    """(role, read-only connection) for every seat that has ever run."""
    for spec in roster.SEATS:
        path = seat_home(spec.role) / "state.db"
        if not path.exists():
            continue
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield spec.role, conn
        finally:
            conn.close()


def _union(table: str, cols: str, order: str, limit: int) -> list[dict]:
    """One table, read from every seat that has one, newest first, seat-tagged."""
    rows: list[dict] = []
    for role, conn in _each_seat():
        try:
            found = conn.execute(
                f"SELECT {cols} FROM {table} ORDER BY {order} DESC LIMIT {limit}"
            ).fetchall()
        except sqlite3.Error:
            continue
        for r in found:
            rows.append({**dict(r), "seat": role})
    rows.sort(key=lambda d: str(d.get(order) or ""), reverse=True)
    return rows[:limit]


def _sessions(limit: int = 40) -> list[dict]:
    from waku.ops.dashboard import session_list

    out: list[dict] = []
    for role, conn in _each_seat():
        try:
            for s in session_list(conn):
                out.append({**s, "seat": role})
        except sqlite3.Error:
            continue
    out.sort(key=lambda s: str(s.get("last_at") or ""), reverse=True)
    return out[:limit]


def _events() -> list[dict]:
    """The entry seat's trace. It already contains the WHOLE subtree: a child's
    events are forwarded to its parent's observer, so one file holds them all,
    each stamped with the seat that emitted it."""
    from waku.ops.dashboard import iter_trace_lines

    events: list[dict] = []
    for path in sorted((seat_home(ENTRY) / "traces").glob("*.jsonl")):
        try:
            lines = list(iter_trace_lines(path))
        except (UnicodeError, OSError):
            continue
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _per_seat(events: list[dict], provider: str, model: str) -> list[dict]:
    """Spend and activity attributed to the seat that emitted each LLM call."""
    pin, pout = price_for(provider, model or "")
    per: dict[str, dict] = {}
    for ev in events:
        if ev.get("type") != "llm":
            continue
        role = ev.get("role") or "unattributed"
        usage = ev.get("usage") or {}
        b = per.setdefault(role, {"seat": role, "calls": 0, "in": 0, "out": 0,
                                  "tool_calls": 0, "cost": 0.0})
        b["calls"] += 1
        b["in"] += usage.get("in", 0)
        b["out"] += usage.get("out", 0)
    for ev in events:
        if ev.get("type") != "tool":
            continue
        role = ev.get("role") or "unattributed"
        if role in per:
            per[role]["tool_calls"] += 1
    for b in per.values():
        b["cost"] = round(b["in"] / 1e6 * pin + b["out"] / 1e6 * pout, 4)
    return sorted(per.values(), key=lambda b: -b["cost"])


def _seat_tools(role: str) -> set[str]:
    spec = roster.BY_ROLE[role]
    names = set(BASE_TOOLS)
    if spec.ring < roster.MAX_RING and roster.children(role):
        names.add("delegate")
    if roster.peers(role):
        names.add("consult_peer")
    return names


def _tools(base: dict) -> dict:
    """The capabilities the ecosystem holds, and how many seats hold each."""
    from waku.ops.dashboard import _tool_source

    holders: dict[str, list[str]] = {}
    for spec in roster.SEATS:
        for name in _seat_tools(spec.role):
            holders.setdefault(name, []).append(spec.role)
    catalog = [
        {"name": name,
         "description": f"{_TOOL_BLURB.get(name, name)} Held by {len(seats)} of "
                        f"{len(roster.SEATS)} seats.",
         "source": _tool_source(name, []),
         "seats": seats}
        for name, seats in sorted(holders.items())
    ]
    return {**base, "catalog": catalog}


def _db(base: dict) -> dict:
    """Aggregate the persistence layer: one row per seat, plus the sums.

    Columns, types and the sample stay as the entry seat's — the schema is the
    same in every home — so the per-table sub-tabs keep working while the row
    counts become the department's."""
    counts = {t.get("name"): 0 for t in base.get("tables", [])}
    total = 0
    per_seat: list[dict] = []
    for role, conn in _each_seat():
        size = (seat_home(role) / "state.db").stat().st_size
        total += size
        row = {"seat": role, "size": size}
        for name in counts:
            try:
                c = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            except sqlite3.Error:
                c = 0
            counts[name] += c
            row[name] = c
        per_seat.append(row)
    tables = [{**t, "count": counts.get(t.get("name"), t.get("count", 0))}
              for t in base.get("tables", [])]
    return {**base, "path": str(STATE_ROOT), "size": total, "tables": tables,
            "seats": sorted(per_seat, key=lambda r: -r["size"])}


def department_payload() -> dict:
    """The topology and per-seat state the department view draws. Angles are not
    here on purpose — placement is the view's business."""
    seats = []
    for spec in roster.SEATS:
        seats.append({"role": spec.role, "title": spec.title, "ring": spec.ring,
                      "parent": spec.parent,
                      "built": (seat_home(spec.role) / "state.db").exists()})
    edges = [{"src": s.parent, "dst": s.role, "kind": "delegate"}
             for s in roster.SEATS if s.parent]
    return {"entry": ENTRY, "seats": seats, "edges": edges}


def collect_department() -> dict:
    """waku's own payload, with the home-scoped keys aggregated over every seat."""
    from waku.ops.dashboard import collect

    data = collect()
    events = _events()
    per_seat = _per_seat(events, data.get("provider", ""), data.get("model", ""))
    by_seat = {b["seat"]: b for b in per_seat}

    department = department_payload()
    for seat in department["seats"]:
        seat["tools"] = sorted(_seat_tools(seat["role"]))
        seat["activity"] = by_seat.get(seat["role"])

    data["home"] = str(STATE_ROOT.resolve())
    data["facts"] = _union("facts", _FACTS, "created_at", 200)
    data["episodes"] = _union("episodes", _EPISODES, "happened_at", 200)
    data["chat_log"] = _union("chat_log", _CHAT, "created_at", 80)
    data["sessions"] = _sessions()
    data["tools"] = _tools(data.get("tools") or {})
    data["db"] = _db(data.get("db") or {})
    data["usage"] = {
        **(data.get("usage") or {}),
        "by_seat": per_seat,
        # Both sides count each call once: the total from the entry seat's ledger,
        # which holds the whole subtree, and the per-seat rows from that same
        # trace, attributed to the seat that made each call. Summing the 24
        # LEDGERS instead would triple-count the deepest seat, which is why the
        # total is not computed that way.
        "note": "total from the entry seat's ledger; per-seat rows are those same calls "
                "attributed to the seat that made them",
    }
    data["department"] = department
    # The Observation Lab's instruments. Computed here rather than in a view so
    # the same registry serves the page, the catalogue CLI and the eval — and so
    # the numbers a reader sees are the ones the tests assert on.
    from concentric import metrics

    data["metrics"] = metrics.compute({
        "events": events,
        "stats": data.get("stats"),
        "usage": data.get("usage"),
        "department": department,
        "db": data.get("db"),
        "facts": data.get("facts"),
        "chat_pending": data.get("chat_pending"),
        "eval_report": data.get("eval_report"),
    })
    return data
