"""The delegation edge — scope and depth enforced by construction.

These are the tests that cannot be written against prompt-only enforcement:
they call the tool directly and watch a cross-team role bounce.
"""

from __future__ import annotations

from types import SimpleNamespace

from concentric import roster
from concentric.run import DEFAULT_CONFIG
from concentric.seat import build_seat
from evals.helpers import ScriptedClient


class _Recorder:
    """Stands in for a child seat: records the task, returns a canned reply."""

    def __init__(self) -> None:
        self.tasks: list[str] = []

    def respond(self, task: str, observer=None, stream=False) -> SimpleNamespace:
        self.tasks.append(task)
        return SimpleNamespace(reply=f"done: {task}")


def _build(role: str, tmp_path, seat_for):
    return build_seat(roster.BY_ROLE[role], config=DEFAULT_CONFIG,
                      seat_for=seat_for, client=ScriptedClient([]), root=tmp_path)


def test_a_worker_has_no_delegate_tool_at_all(tmp_path):
    assert "delegate" not in _build("model-developer", tmp_path, lambda _r: None).tool_names()


def test_a_cfo_delegates_to_its_own_team(tmp_path):
    child = _Recorder()
    seat = _build("cfo-2-validation", tmp_path, lambda _r: child)
    out = seat.app.tools._tools["delegate"].fn(role="challenger-modeler",
                                               task="challenge it")
    assert out == "done: challenge it"
    assert child.tasks == ["challenge it"]


def test_cross_team_delegation_is_refused(tmp_path):
    seat = _build("cfo-2-validation", tmp_path, lambda _r: None)
    tool = seat.app.tools._tools["delegate"]
    assert tool.fn(role="model-developer", task="x") == "ERROR: out of scope"


def test_scope_is_baked_into_the_enum(tmp_path):
    seat = _build("cfo-2-validation", tmp_path, lambda _r: None)
    enum = seat.app.tools._tools["delegate"].input_schema["properties"]["role"]["enum"]
    assert set(enum) == set(roster.children("cfo-2-validation"))


def test_a_validator_cannot_name_a_development_worker(tmp_path):
    seat = _build("conceptual-soundness-validator", tmp_path, lambda _r: None)
    assert "delegate" not in seat.tool_names()
    enum = seat.app.tools._tools["consult_peer"].input_schema["properties"]["role"]["enum"]
    assert "model-developer" not in enum


def test_a_peer_edge_is_lateral_not_downward(tmp_path):
    """A worker's consult_peer reaches peers, never its CFO or Irina."""
    seat = _build("challenger-modeler", tmp_path, lambda _r: None)
    enum = seat.app.tools._tools["consult_peer"].input_schema["properties"]["role"]["enum"]
    assert set(enum) == set(roster.peers("challenger-modeler"))
    assert "cfo-2-validation" not in enum
    assert "irina" not in enum


def test_irina_has_no_peer_edge(tmp_path):
    assert "consult_peer" not in _build("irina", tmp_path, lambda _r: None).tool_names()
