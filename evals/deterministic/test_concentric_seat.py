"""The seat builder — prompt, tools, model and memory, all role-correct, offline.

Every seat here is built with a scripted client, so no API call is ever made.
"""

from __future__ import annotations

from concentric import roster
from concentric.run import DEFAULT_CONFIG
from concentric.seat import build_seat
from evals.helpers import ScriptedClient, response, text_block


def _build(role: str, tmp_path, seat_for=None):
    return build_seat(
        roster.BY_ROLE[role],
        config=DEFAULT_CONFIG,
        seat_for=seat_for or (lambda _role: None),
        client=ScriptedClient([]),
        root=tmp_path,
    )


def test_each_seat_gets_its_own_home(tmp_path):
    seat = _build("irina", tmp_path)
    assert seat.app.settings.home == tmp_path / "irina"
    assert (tmp_path / "irina" / "state.db").is_file()


def test_the_soul_carries_the_mandate(tmp_path):
    spec = roster.BY_ROLE["challenger-modeler"]
    _build("challenger-modeler", tmp_path)
    soul = (tmp_path / "challenger-modeler" / "SOUL.md").read_text(encoding="utf-8")
    assert spec.mandate in soul
    assert spec.role in soul


def test_the_config_is_applied_to_every_seat(tmp_path):
    seat = _build("irina", tmp_path)
    assert seat.app.settings.provider == "deepseek"
    assert seat.app.settings.model == "deepseek-v4-pro"
    assert seat.app.settings.small_model == "deepseek-v4-flash"


def test_irina_can_delegate_but_has_no_peer(tmp_path):
    names = _build("irina", tmp_path).tool_names()
    assert "delegate" in names
    assert "consult_peer" not in names


def test_a_worker_has_no_delegate_tool(tmp_path):
    assert "delegate" not in _build("challenger-modeler", tmp_path).tool_names()


def test_a_worker_peers_only_within_its_team(tmp_path):
    tool = _build("challenger-modeler", tmp_path).app.tools._tools["consult_peer"]
    enum = tool.input_schema["properties"]["role"]["enum"]
    assert enum
    assert all(roster.team(r) == "cfo-2-validation" for r in enum)
    assert "model-developer" not in enum


def test_the_registry_is_only_base_tools_plus_edges(tmp_path):
    names = _build("challenger-modeler", tmp_path).tool_names()
    assert names == {"save_note", "manage_memory", "consult_peer"}


GATE_NO = '{"retrieve": false, "reason": "test"}'


def _run_on_another_thread(seat) -> list:
    import threading

    errors: list = []

    def run() -> None:
        try:
            seat.respond("hello")
        except Exception as exc:  # noqa: BLE001 — the test asserts on this
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    return errors


def _scripted():
    return ScriptedClient([response([text_block(GATE_NO)]),
                           response([text_block("ok")])])


def test_a_seat_cannot_cross_threads_without_a_conn_factory(tmp_path):
    """Documents why conn_factory exists. waku's connect() defaults to
    check_same_thread=True, so a seat built on one thread cannot run a turn on
    another — which is exactly what a ThreadingHTTPServer does."""
    seat = build_seat(roster.BY_ROLE["irina"], config=DEFAULT_CONFIG,
                      seat_for=lambda _r: None, client=_scripted(), root=tmp_path)
    errors = _run_on_another_thread(seat)
    assert errors and "thread" in str(errors[0]).lower()


def test_a_cross_thread_seat_runs_a_turn_from_another_thread(tmp_path):
    """The fix the dashboard relies on: a connection opened for any thread."""
    from waku.db import connect

    seat = build_seat(roster.BY_ROLE["irina"], config=DEFAULT_CONFIG,
                      seat_for=lambda _r: None, client=_scripted(), root=tmp_path,
                      conn_factory=lambda home: connect(home, check_same_thread=False))
    assert _run_on_another_thread(seat) == []


def test_a_seat_accepts_every_argument_waku_respond_takes(tmp_path):
    """A Seat stands in for a Waku, so its signature must be at least as wide.
    The dashboard passes source="dashboard" and stream=True; a narrower
    Seat.respond broke the chat dock with a TypeError."""
    seat = build_seat(roster.BY_ROLE["irina"], config=DEFAULT_CONFIG,
                      seat_for=lambda _r: None, client=_scripted(), root=tmp_path)
    result = seat.respond("hello", source="dashboard", stream=True)
    assert result.reply == "ok"
