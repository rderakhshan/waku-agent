"""The evaluators are pure functions, so they are testable here.

They score the executor's output — the reply plus the tool events the run
emitted. The graph rules are exact and free, which is the point: correctness
against Irina's own org chart needs no judge. The other half of the guarantee is
that importing this module must not drag waku in, or the evaluators could not be
tested without a live department.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from concentric import graph_rules, roster
from concentric import laminar_evals as le

ROOT = Path(__file__).resolve().parents[2]


def _handoff(frm: str, to: str, output: str = "ok"):
    return {"tool": "delegate", "args": {"role": to, "task": "t"},
            "output": output, "role": frm}


def _worker() -> str:
    return next(s.role for s in roster.SEATS if s.ring == roster.MAX_RING)


def test_delegated_is_one_only_when_an_edge_was_used():
    assert le.delegated({"events": [_handoff("irina", roster.children("irina")[0])]}, {}) == 1.0
    assert le.delegated({"events": []}, {}) == 0.0


def test_reached_expected_is_one_when_the_seat_was_reached():
    cfo = roster.children("irina")[0]
    output = {"events": [_handoff("irina", cfo)]}
    assert le.reached_expected(output, {"expect_seat": cfo}) == 1.0
    assert le.reached_expected(output, {"expect_seat": roster.children("irina")[1]}) == 0.0


def test_no_expectation_is_not_a_miss():
    """A task that needs no edge cannot fail by not using one."""
    assert le.reached_expected({"events": []}, {"expect_seat": None}) == 1.0
    assert le.reached_expected({"events": []}, {}) == 1.0


def test_reply_non_empty_rejects_whitespace():
    assert le.reply_non_empty({"reply": "done"}, {}) == 1.0
    assert le.reply_non_empty({"reply": "   \n"}, {}) == 0.0
    assert le.reply_non_empty({}, {}) == 0.0


# --- the rule scores ---------------------------------------------------------

def test_every_rule_scores_one_on_a_healthy_run():
    cfo = roster.children("irina")[0]
    output = {"events": [_handoff("irina", cfo)], "reply": "done"}
    for name, evaluator in le.RULES.items():
        assert evaluator(output, {}) == 1.0, name


def test_the_scope_rule_scores_zero_on_a_run_that_broke_it():
    output = {"events": [_handoff("irina", _worker())], "reply": "done"}
    assert le.RULES["in_scope"](output, {}) == 0.0


def test_a_rule_score_is_the_wrapper_of_its_check():
    """The evaluator is a delivery slot for the rule, not a second copy of it."""
    events = [_handoff("irina", _worker())]
    assert graph_rules.out_of_scope(events)
    assert le.RULES["in_scope"]({"events": events}, {}) == 0.0


# --- coverage ----------------------------------------------------------------
#
# The point of these two is that a gap fails here instead of going unnoticed: a
# rule added to the graph without a score, or a pass-through that quietly selects
# nothing and reports an empty eval forever.

def test_every_rule_the_graph_checks_is_scored_under_a_name():
    assert set(le.RULE_CHECKS) == set(graph_rules.violations([]))
    assert set(le.RULE_CHECKS) == set(le.RULE_NAMES)
    assert set(le.RULE_NAMES.values()) <= set(le.RULES)


def test_the_registry_still_has_judge_metrics_to_report():
    from concentric import metrics

    assert le.judge_ids(metrics.registry())


# --- the dataset -------------------------------------------------------------

def test_every_datapoint_carries_a_task_and_a_target():
    for item in le.DATASET:
        assert item["data"]["task"].strip()
        assert "expect_seat" in item["target"]


def test_the_eval_loads_dot_env_before_reading_the_key(monkeypatch):
    """An eval run imports no waku, so nothing else loads `.env` for it. Without
    this the key in `.env` is invisible and the run refuses to start — which is
    exactly what it did."""
    monkeypatch.delenv("LMNR_PROJECT_API_KEY", raising=False)

    def fake_load():
        os.environ["LMNR_PROJECT_API_KEY"] = "from-dot-env"

    monkeypatch.setattr("concentric.tracing.load_env", fake_load)
    assert le.project_key() == "from-dot-env"


def test_failure_datapoints_skip_runs_whose_ask_was_not_kept(monkeypatch):
    monkeypatch.setattr("concentric.history.failures", lambda limit=50: [
        {"task": "a real ask", "entry": "irina", "violations": "in_scope"},
        {"task": None, "entry": "irina", "violations": "repeated"},
    ])
    rows = le.failure_datapoints()
    assert [r["data"]["task"] for r in rows] == ["a real ask"]
    assert rows[0]["target"]["broke"] == "in_scope"


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
