"""The department's rules, checked against a run's own events.

This is the half a judge cannot do. A judge can say an answer reads well; it
cannot say whether the audit seat was allowed to task a development worker,
because it does not know the org chart. The roster does, and the run's events say
what actually happened, so the comparison is exact and free.

Every case here is built from the roster rather than hard-coded, so it stays true
if the roster changes.
"""

from __future__ import annotations

from concentric import graph_rules, roster


def _handoff(frm: str, to: str, output: str = "ok", tool: str = "delegate"):
    return {"tool": tool, "args": {"role": to, "task": "t"}, "output": output, "role": frm}


def _worker() -> str:
    return next(s.role for s in roster.SEATS if s.ring == roster.MAX_RING)


# --- in scope ----------------------------------------------------------------

def test_an_allowed_hand_off_is_not_flagged():
    cfo = roster.children("irina")[0]
    assert graph_rules.out_of_scope([_handoff("irina", cfo)]) == []


def test_a_hand_off_past_your_own_ring_is_flagged():
    """Irina may task her CFOs, not a worker two rings down."""
    assert graph_rules.out_of_scope([_handoff("irina", _worker())])


def test_a_worker_handing_off_is_flagged():
    """A leaf has no delegation tool at all, so this only fires if one appears."""
    worker = _worker()
    assert graph_rules.out_of_scope([_handoff(worker, "irina")])


# --- depth -------------------------------------------------------------------

def test_a_hand_off_from_a_leaf_is_over_depth():
    assert graph_rules.over_depth([_handoff(_worker(), "irina")])


def test_a_hand_off_from_the_top_is_not():
    assert graph_rules.over_depth([_handoff("irina", roster.children("irina")[0])]) == []


# --- answered ----------------------------------------------------------------

def test_an_empty_answer_is_unanswered():
    assert graph_rules.unanswered([_handoff("irina", roster.children("irina")[0], "")])


def test_an_error_answer_is_unanswered():
    assert graph_rules.unanswered([_handoff("irina", roster.children("irina")[0],
                                            "ERROR: out of scope")])


def test_a_real_answer_counts_as_answered():
    assert graph_rules.unanswered([_handoff("irina", roster.children("irina")[0],
                                            "the control is X")]) == []


# --- repetition --------------------------------------------------------------

def test_the_same_call_twice_is_a_repeat():
    a = _handoff("irina", roster.children("irina")[0])
    assert graph_rules.repeated([a, dict(a)])


def test_the_same_tool_with_a_different_ask_is_not():
    cfo = roster.children("irina")[0]
    first = _handoff("irina", cfo)
    second = _handoff("irina", cfo)
    second["args"] = {"role": cfo, "task": "a different ask"}
    assert graph_rules.repeated([first, second]) == []


# --- together ----------------------------------------------------------------

def test_a_healthy_run_is_clean():
    cfo = roster.children("irina")[0]
    events = [_handoff("irina", cfo, "answer"), _handoff(cfo, roster.children(cfo)[0], "answer")]
    assert graph_rules.clean(events) is True


def test_a_run_that_broke_one_rule_is_not_clean():
    assert graph_rules.clean([_handoff("irina", _worker())]) is False


def test_violations_names_only_what_broke():
    """`violations` reports every rule; only the broken ones have hits."""
    report = graph_rules.violations([_handoff("irina", _worker())])
    broken = {name for name, hits in report.items() if hits}
    assert broken == {"out_of_scope"}
