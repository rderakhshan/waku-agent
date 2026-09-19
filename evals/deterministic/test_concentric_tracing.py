"""Tracing is on by default, and off must still be a true no-op.

A run that happened should be recorded without anyone remembering a switch, so
the tests are the other way round from the first cut: the default is ON, and
`IRINA_LAMINAR=off` is the exception. Whatever the outcome, a tracing failure
must never take the seat loop down with it — so the failure path is pinned too.

The SDK is faked, not imported: the real one would try to reach a server, and a
test that needs a running Laminar is not a deterministic eval.
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path
from typing import ClassVar

import pytest

from concentric import tracing

ROOT = Path(__file__).resolve().parents[2]


class FakeLaminar:
    calls: ClassVar[list[dict]] = []
    fail: ClassVar[bool] = False

    @classmethod
    def initialize(cls, **kwargs):
        if cls.fail:
            raise RuntimeError("server down")
        cls.calls.append(kwargs)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("IRINA_LAMINAR", raising=False)
    monkeypatch.setenv("LMNR_PROJECT_API_KEY", "test-key")
    monkeypatch.setattr(tracing, "_Laminar", None)
    monkeypatch.setattr(tracing, "_failed_at", 0.0)
    monkeypatch.setitem(sys.modules, "lmnr",
                        types.SimpleNamespace(Laminar=FakeLaminar))
    FakeLaminar.calls = []
    FakeLaminar.fail = False


# --- the gate ---------------------------------------------------------------

def test_on_by_default():
    """No flag, no ceremony: a key is the only thing needed."""
    assert tracing.init() is True
    assert FakeLaminar.calls and FakeLaminar.calls[0]["project_api_key"] == "test-key"


def test_the_off_flag_is_the_only_thing_that_disables_it(monkeypatch):
    monkeypatch.setenv("IRINA_LAMINAR", "off")
    assert tracing.init() is False
    assert FakeLaminar.calls == []


def test_no_key_is_off_and_does_not_raise(monkeypatch):
    monkeypatch.setenv("LMNR_PROJECT_API_KEY", "")
    assert tracing.init() is False
    assert FakeLaminar.calls == []


def test_a_missing_sdk_is_off(monkeypatch):
    monkeypatch.setitem(sys.modules, "lmnr", None)
    assert tracing.init() is False


# --- the retry memo ---------------------------------------------------------

def test_a_failed_init_is_not_retried_every_turn():
    """A down server must cost one check a minute, not one per trajectory."""
    FakeLaminar.fail = True
    assert tracing.init() is False
    before = len(FakeLaminar.calls)
    for _ in range(5):
        assert tracing.init() is False
    assert len(FakeLaminar.calls) == before  # the failure was remembered


def test_a_failed_init_is_retried_after_the_window(monkeypatch):
    FakeLaminar.fail = True
    assert tracing.init() is False
    monkeypatch.setattr(tracing, "_failed_at", 0.0)
    FakeLaminar.fail = False
    assert tracing.init() is True


# --- the no-op path ---------------------------------------------------------

def test_every_helper_is_a_no_op_when_off(monkeypatch):
    monkeypatch.setenv("IRINA_LAMINAR", "off")
    with tracing.span("x", {"a": 1}) as s:
        assert s is None
    with tracing.trajectory("t") as t:
        assert t is None
    with tracing.seat("irina", ring=0, parent="") as s:
        assert s is None
    with tracing.handoff("delegate", "irina", "cfo-1-development", "task") as h:
        assert h is None
    assert tracing.trace_id() is None
    tracing.set_output("reply")  # must not raise
    tracing.flush()  # must not raise


def test_a_no_op_span_does_not_swallow_the_caller_error():
    with pytest.raises(ValueError), tracing.span("x"):
        raise ValueError("boom")


def test_in_trajectory_is_false_outside_and_true_inside():
    """The guard the seat uses to decide whether it is the boundary. It has to
    be true even with tracing off, or the CLI would open two trajectories."""
    assert tracing.in_trajectory() is False
    with tracing.trajectory("t"):
        assert tracing.in_trajectory() is True
    assert tracing.in_trajectory() is False


def test_nested_trajectories_unwind_cleanly():
    with tracing.trajectory("outer"):
        with tracing.trajectory("inner"):
            assert tracing.in_trajectory() is True
        assert tracing.in_trajectory() is True
    assert tracing.in_trajectory() is False


def test_the_sdk_is_never_imported_when_off():
    """The strongest form of "optional": a clean process must not pull lmnr in."""
    code = (
        "import sys;"
        "import concentric.tracing as t;"
        "assert t.init() is False;"
        "print('lmnr' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True, check=True,
                         env={"IRINA_LAMINAR": "off", "PATH": ""})
    assert out.stdout.strip() == "False"
