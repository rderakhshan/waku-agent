"""End to end, offline: Irina -> CFO-2 -> Challenger Modeler.

The same path the demo prints, pinned as an eval so a regression in the wiring
is caught without spending a token.
"""

from __future__ import annotations

from concentric.run import build_department
from evals.helpers import ScriptedClient, response, text_block, tool_block

GATE_NO = '{"retrieve": false, "reason": "self-contained"}'


def _scripts() -> dict[str, list]:
    return {
        "irina": [
            response([text_block(GATE_NO)]),
            response([tool_block("delegate", {"role": "cfo-2-validation",
                                              "task": "Tier the IFRS 9 model."})],
                     "tool_use"),
            response([text_block("CFO-2 has tiered the IFRS 9 model.")]),
        ],
        "cfo-2-validation": [
            response([text_block(GATE_NO)]),
            response([tool_block("delegate", {"role": "challenger-modeler",
                                              "task": "Challenge the tiering."})],
                     "tool_use"),
            response([text_block("The challenger reviewed it; the tiering stands.")]),
        ],
        "challenger-modeler": [
            response([text_block(GATE_NO)]),
            response([text_block("Challenger: the tiering is sound.")]),
        ],
    }


def _department(tmp_path):
    scripts = _scripts()
    return build_department(
        client_factory=lambda role: ScriptedClient(scripts[role]), root=tmp_path)


def test_the_department_runs_end_to_end(tmp_path):
    department = _department(tmp_path)
    path: list[tuple[str, str]] = []

    def observer(kind: str, event: dict) -> None:
        if kind == "tool" and event.get("tool") == "delegate":
            path.append((event["role"], event["args"]["role"]))

    reply = department.run("Tier the IFRS 9 model.", observer=observer)
    assert reply == "CFO-2 has tiered the IFRS 9 model."
    # A child's events arrive while its parent's delegate call is still running,
    # so compare as edges, not as emit order.
    assert set(path) == {("irina", "cfo-2-validation"),
                         ("cfo-2-validation", "challenger-modeler")}


def test_seats_are_built_lazily(tmp_path):
    department = _department(tmp_path)
    assert department._seats == {}
    department.seat_for("irina")
    assert set(department._seats) == {"irina"}


def test_only_the_seats_actually_used_are_built(tmp_path):
    department = _department(tmp_path)
    department.run("Tier the IFRS 9 model.")
    assert set(department._seats) == {"irina", "cfo-2-validation", "challenger-modeler"}


def test_every_seat_gets_its_own_database(tmp_path):
    _department(tmp_path).run("Tier the IFRS 9 model.")
    homes = sorted(p.parent.name for p in tmp_path.rglob("state.db"))
    assert homes == ["cfo-2-validation", "challenger-modeler", "irina"]


def test_the_run_is_recorded_in_each_seat_trace(tmp_path):
    _department(tmp_path).run("Tier the IFRS 9 model.")
    for role in ("irina", "cfo-2-validation", "challenger-modeler"):
        traces = list((tmp_path / role / "traces").glob("*.jsonl"))
        assert traces, f"{role} wrote no trace"


def _events(tmp_path, role):
    import json

    return [json.loads(line)
            for path in (tmp_path / role / "traces").glob("*.jsonl")
            for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_seat_own_events_carry_its_role(tmp_path):
    """The emitter must be identified in its OWN trace, not only on the way out
    to its parent — otherwise a seat's trace reads as unattributed."""
    _department(tmp_path).run("Tier the IFRS 9 model.")
    own = [e for e in _events(tmp_path, "irina") if e.get("type") == "llm"]
    assert own, "irina wrote no llm event"
    assert "irina" in {e.get("role") for e in own}, "irina's own events are unattributed"


def test_a_child_keeps_its_own_role_in_the_parent_trace(tmp_path):
    """Forwarded events are attributed to the child, not relabelled as the parent.
    A parent's trace legitimately holds both its own events and its children's."""
    _department(tmp_path).run("Tier the IFRS 9 model.")
    roles = {e.get("role") for e in _events(tmp_path, "irina") if e.get("type") == "llm"}
    assert {"irina", "cfo-2-validation", "challenger-modeler"} <= roles
