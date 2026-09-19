"""Tracing is off unless it is asked for — and off must be a true no-op.

The whole integration is optional: if the flag is unset, or the SDK is missing,
or the local Laminar is not running, Irina must behave exactly as it did before.
These tests pin that, because a tracing call that raises would take the seat
loop down with it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from concentric import tracing

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _tracing_off(monkeypatch):
    monkeypatch.delenv("IRINA_LAMINAR", raising=False)
    monkeypatch.delenv("LMNR_PROJECT_API_KEY", raising=False)
    monkeypatch.setattr(tracing, "_Laminar", None)


def test_init_is_false_when_the_flag_is_unset():
    assert tracing.init() is False
    assert tracing.enabled() is False


def test_init_is_false_when_the_flag_is_set_but_there_is_no_key(monkeypatch):
    monkeypatch.setenv("IRINA_LAMINAR", "on")
    assert tracing.init() is False
    assert tracing.enabled() is False


def test_a_flag_of_zero_does_not_enable(monkeypatch):
    monkeypatch.setenv("IRINA_LAMINAR", "0")
    assert tracing.init() is False


def test_every_helper_is_a_no_op_when_off():
    with tracing.span("x", {"a": 1}) as s:
        assert s is None
    with tracing.trajectory("t") as t:
        assert t is None
    with tracing.seat("irina", ring=0, parent="") as s:
        assert s is None
    with tracing.handoff("delegate", "irina", "cfo-1-development", "task") as h:
        assert h is None
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
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
