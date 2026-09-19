"""The per-trajectory evaluators are pure functions, so they are testable here.

They score the executor's output — the reply plus the edges the run used — and
the three rules that matter are all decisions, not arithmetic: did it use an
edge, did it reach the seat the task needed, and did it say anything. The other
half of the guarantee is that importing this module must not drag waku in, or
the evaluators could not be tested without a live department.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from concentric import laminar_evals as le

ROOT = Path(__file__).resolve().parents[2]


def test_delegated_is_one_only_when_an_edge_was_used():
    assert le.delegated({"handoffs": [{"to": "cfo-4-audit"}]}, {}) == 1.0
    assert le.delegated({"handoffs": []}, {}) == 0.0


def test_delegated_to_expected_is_one_when_the_seat_was_reached():
    output = {"targets": ["cfo-4-audit"]}
    assert le.delegated_to_expected(output, {"expect_seat": "cfo-4-audit"}) == 1.0
    assert le.delegated_to_expected(output, {"expect_seat": "cfo-1-development"}) == 0.0


def test_no_expectation_is_not_a_miss():
    """A task that needs no edge cannot fail by not using one."""
    assert le.delegated_to_expected({"targets": []}, {"expect_seat": None}) == 1.0
    assert le.delegated_to_expected({"targets": []}, {}) == 1.0


def test_reply_non_empty_rejects_whitespace():
    assert le.reply_non_empty({"reply": "done"}, {}) == 1.0
    assert le.reply_non_empty({"reply": "   \n"}, {}) == 0.0
    assert le.reply_non_empty({}, {}) == 0.0


def test_every_datapoint_carries_a_task_and_a_target():
    for item in le.DATASET:
        assert item["data"]["task"].strip()
        assert "expect_seat" in item["target"]


def test_importing_the_evaluators_does_not_pull_waku_in():
    code = (
        "import sys;"
        "import concentric.laminar_evals as le;"
        "assert callable(le.delegated);"
        "print('waku' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
