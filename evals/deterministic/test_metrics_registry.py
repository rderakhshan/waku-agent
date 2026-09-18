"""DETERMINISTIC EVAL — the metric registry keeps its shape and its null rule.

Two things this module can get wrong silently, and both are cheap to check:

  1. A slot loses a field. The catalogue then prints a column of blanks and
     nobody notices which metric stopped saying what it measures.
  2. A missing measurement becomes a zero. That is the failure mode
     `waku/memory/semantic/base.py` names — a fallback that looks defensive and
     quietly answers wrong — and in a metrics table it is worse, because the
     zero is summed into aggregates that then read as real.

No filesystem, no model, no network: `compute()` is pure, so these run anywhere.
"""

from __future__ import annotations

from concentric import metrics

REQUIRED = ("id", "label", "state", "kind", "changes", "unit", "direction",
            "source", "filler", "value", "cost_ms", "as_of")
STATES = {"computed", "ready", "blocked", "placeholder"}

# One turn with a delegate that was never answered, one repeated tool call, and
# one turn that never ended. Small enough to reason about by hand.
EVENTS = [
    {"type": "turn_start", "user_message": "tier the model", "ts": "2026-01-01T00:00:00+00:00"},
    {"type": "llm", "role": "irina", "ring": 0, "iteration": 1,
     "usage": {"in": 100, "out": 10}, "ts": "2026-01-01T00:00:02+00:00"},
    {"type": "tool", "role": "irina", "ring": 0, "tool": "delegate",
     "args": {"role": "cfo-1-development"}, "output": "ok", "ts": "2026-01-01T00:00:03+00:00"},
    {"type": "tool", "role": "irina", "ring": 0, "tool": "save_note",
     "args": {"text": "a"}, "output": "ok", "ts": "2026-01-01T00:00:04+00:00"},
    {"type": "tool", "role": "irina", "ring": 0, "tool": "save_note",
     "args": {"text": "a"}, "output": "ok", "ts": "2026-01-01T00:00:05+00:00"},
    {"type": "turn_end", "reply": "done", "iterations": 1, "ts": "2026-01-01T00:00:06+00:00"},
    {"type": "turn_start", "user_message": "and again", "ts": "2026-01-01T00:10:00+00:00"},
    {"type": "llm", "role": "irina", "ring": 0, "iteration": 1,
     "usage": {"in": 120, "out": 10}, "ts": "2026-01-01T00:10:01+00:00"},
]

CTX = {
    "events": EVENTS,
    "stats": {"turns": 2, "latency_avg": 2000, "latency_p95": 3000, "tokens_in": 220,
              "tokens_out": 20, "cost": 0.01, "tool_errors": 0,
              "gate_skips": 1, "gate_retrieves": 0},
    "usage": {"by_seat": [{"seat": "irina", "cost": 0.01, "calls": 2}]},
    "department": {"seats": [
        {"role": "irina", "ring": 0, "built": True, "activity": {"calls": 2},
         "tools": ["delegate", "save_note", "manage_memory"]},
        {"role": "cfo-1-development", "ring": 1, "built": True, "activity": None,
         "tools": ["manage_memory"]},
    ]},
    "db": {"seats": [{"seat": "irina", "facts": 3, "episodes": 1},
                     {"seat": "cfo-1-development", "facts": 0, "episodes": 0}]},
    "facts": [{"seat": "irina", "content": "x"}],
    "episodes": [],
    "chat_pending": 4,
    "eval_report": None,
}


def test_every_slot_has_every_field():
    for slot in metrics.compute(CTX).values():
        missing = [k for k in REQUIRED if k not in slot]
        assert not missing, f"{slot.get('id')} is missing {missing}"
        assert slot["state"] in STATES, f"{slot['id']} has state {slot['state']!r}"


def test_slot_ids_are_unique():
    ids = [s["id"] for s in metrics.SLOTS]
    assert len(ids) == len(set(ids)), "two slots share an id"


def test_a_missing_measurement_is_never_zero():
    """The rule the whole registry rests on: an unmeasured metric is None, and a
    metric that is not wired up never carries a number."""
    reg = metrics.compute(CTX)
    for slot in reg.values():
        if slot["state"] in ("ready", "blocked", "placeholder"):
            assert slot["value"] is None, (
                f"{slot['id']} is {slot['state']} but carries {slot['value']!r}")
    for slot in reg.values():
        assert slot["value"] != 0 or slot["state"] == "computed", (
            f"{slot['id']} reports a bare zero without being wired up")


def test_every_empty_slot_says_what_would_fill_it():
    for slot in metrics.compute(CTX).values():
        if slot["value"] is None:
            assert slot["filler"], f"{slot['id']} is empty and does not say why"


def test_none_renders_as_a_dash_not_a_zero():
    assert metrics._render(None) == "—"
    assert "0" not in metrics._render(None)


def test_compute_survives_an_empty_world():
    """A fresh install has no traces, no seats and no eval report. The registry
    must still come back whole, and still be honest about every gap."""
    reg = metrics.compute({})
    assert len(reg) == len(metrics.SLOTS)
    assert all(s["value"] is None for s in reg.values())
    assert all(s["filler"] for s in reg.values())


def test_the_trace_metrics_read_the_trace():
    """The deterministic half: these are pattern matches over the events above,
    and each one has a hand-checkable answer."""
    reg = metrics.compute(CTX)
    assert reg["step_repetition"]["value"] == 1          # save_note fired twice
    assert reg["unanswered_handoffs"]["value"] == 1      # cfo-1 never answered
    assert reg["premature_terminations"]["value"] == 1   # the second turn never ended
    assert reg["delegation_breadth"]["value"] == 1       # one distinct target
    assert reg["mandate_breaches"]["value"] == 0         # nobody used a foreign tool


def test_the_throughput_is_the_inverse_of_active_time():
    """A turn runs to its LAST llm call, which is waku's own definition. So turn
    one is 2s (00:00:00 to its llm at 00:00:02) and turn two is 1s: two turns of
    work in three seconds, forty a minute. The wall-clock span would have said
    0.003, which is why it is computed this way."""
    value = metrics.compute(CTX)["throughput"]["value"]
    assert value is not None and 39 < value < 41, value


# --- the batch report --------------------------------------------------------

REPORT = {
    "ran_at": "2026-01-01T00:00:00+00:00",
    "scored": 12,
    "of_turns": 20,
    "values": {
        "average_reward": 0.72,
        "mast_reasoning_action_mismatch": 3,
        "mast_information_withholding": 0,
    },
}


def test_a_report_fills_only_the_slots_it_is_allowed_to():
    reg = metrics.compute({**CTX, "report": REPORT})
    assert reg["average_reward"]["value"] == 0.72
    assert reg["mast_reasoning_action_mismatch"]["value"] == 3
    # A judge number must never overwrite something the trace already knows.
    assert reg["step_repetition"]["value"] == 1
    assert reg["latency_avg"]["value"] == 2000


def test_a_report_cannot_write_into_a_slot_that_is_not_a_judge_metric():
    reg = metrics.compute({**CTX, "report": {
        "values": {"latency_avg": 999, "not_a_metric": 1}}})
    assert reg["latency_avg"]["value"] == 2000, "the report overwrote a live metric"


def test_a_null_in_the_report_does_not_become_a_zero():
    """The rule again, one layer out: a judge that scored nothing must leave the
    slot empty rather than report a confident zero."""
    reg = metrics.compute({**CTX, "report": {"values": {"average_reward": None}}})
    assert reg["average_reward"]["value"] is None


def test_no_report_leaves_every_judge_slot_empty():
    reg = metrics.compute(CTX)
    for mid in metrics.JUDGE_METRICS:
        assert reg[mid]["value"] is None, f"{mid} has a value with no report"


# --- the semantic metrics ----------------------------------------------------

def test_bleu_is_one_for_an_identical_answer_and_zero_for_no_overlap():
    assert metrics.bleu("the model is tiered", "the model is tiered") == 1.0
    assert metrics.bleu("alpha beta", "gamma delta") == 0.0


def test_rouge_is_recall_over_the_reference():
    assert metrics.rouge("the model is tiered today", "the model is tiered") == 1.0
    partial = metrics.rouge("the model", "the model is tiered")
    assert 0 < partial < 1, partial


def test_cosine_handles_parallel_orthogonal_and_empty_vectors():
    from concentric import embeddings

    assert round(embeddings.cosine([1, 0], [2, 0]), 6) == 1.0
    assert embeddings.cosine([1, 0], [0, 1]) == 0.0
    # A seat that said nothing has no position; 0 is the honest stand-in.
    assert embeddings.cosine([0, 0], [1, 1]) == 0.0


def _semantic_events(second_answer: str) -> list[dict]:
    return [
        {"type": "turn_start", "user_message": "q", "ts": "2026-01-01T00:00:00+00:00"},
        {"type": "tool", "role": "irina", "tool": "delegate", "args": {"role": "a"},
         "output": "alpha " + "x" * 60, "ts": "2026-01-01T00:00:01+00:00"},
        {"type": "tool", "role": "irina", "tool": "delegate", "args": {"role": "b"},
         "output": second_answer + " " + "y" * 60, "ts": "2026-01-01T00:00:02+00:00"},
        {"type": "turn_end", "reply": "done", "ts": "2026-01-01T00:00:03+00:00"},
    ]


def _fake_vectors(monkeypatch):
    from concentric import embeddings

    monkeypatch.setattr(embeddings, "available", lambda: True)
    monkeypatch.setattr(embeddings, "embed", lambda texts: [
        [1.0, 0.0] if t.startswith("alpha") else [0.0, 1.0] for t in texts])


def test_two_seats_saying_the_same_thing_converge(monkeypatch):
    _fake_vectors(monkeypatch)
    values = metrics._semantic_values(_semantic_events("alpha"))
    assert values["stance_convergence"] == 1.0
    assert values["semantic_diversity"] == 0.0


def test_two_seats_disagreeing_do_not(monkeypatch):
    _fake_vectors(monkeypatch)
    values = metrics._semantic_values(_semantic_events("beta"))
    assert values["stance_convergence"] == 0.0
    assert values["semantic_diversity"] == 1.0


def test_no_embedding_key_means_no_semantic_metrics(monkeypatch):
    """The designed answer to a keyless install: None, with the filler saying
    which variable would fix it. Never a zero."""
    from concentric import embeddings

    monkeypatch.setattr(embeddings, "available", lambda: False)
    assert metrics._semantic_values(_semantic_events("alpha")) == {}
    reg = metrics.compute({**CTX, "events": _semantic_events("alpha")})
    for mid in ("stance_convergence", "stance_shift", "semantic_diversity"):
        assert reg[mid]["value"] is None


# --- grounding and labeler agreement -----------------------------------------

def _grounding_events() -> list[dict]:
    """Two turns, each with something a tool returned and a reply to check."""
    out = []
    for i in range(2):
        out += [
            {"type": "turn_start", "user_message": f"q{i}",
             "ts": f"2026-01-01T00:0{i}:00+00:00"},
            {"type": "tool", "role": "irina", "tool": "manage_memory",
             "args": {"action": "search"}, "output": f"fact {i}",
             "ts": f"2026-01-01T00:0{i}:01+00:00"},
            {"type": "turn_end", "reply": f"answer {i}",
             "ts": f"2026-01-01T00:0{i}:02+00:00"},
        ]
    return out


def test_grounding_is_scored_two_ways_from_one_judgement(monkeypatch):
    replies = iter(['{"grounded": 1}', '{"grounded": 0}'])
    monkeypatch.setattr(metrics, "_ask", lambda p, max_tokens=700: next(replies))
    values = metrics._grounding_values(metrics._turns_of(_grounding_events()))
    assert values["factual_grounding"] == 0.5
    assert values["hallucination_rate"] == 0.5


def test_a_judge_that_cannot_answer_is_no_measurement(monkeypatch):
    monkeypatch.setattr(metrics, "_ask",
                        lambda p, max_tokens=700: "I am unable to help with that")
    assert metrics._grounding_values(metrics._turns_of(_grounding_events())) == {}


def test_the_run_limit_bounds_the_grounding_pass(monkeypatch):
    """The limit has to bound every pass, not just the sampled ones. It used to
    score grounding over the whole corpus, so a run got more expensive as the
    trace grew while the other two passes stayed at the limit."""
    seen = []
    monkeypatch.setattr(metrics, "_ask",
                        lambda p, max_tokens=700: seen.append(1) or '{"grounded": 1}')
    turns = metrics._turns_of(_grounding_events())
    assert len(turns) == 2
    metrics._grounding_values(turns[:1])
    assert len(seen) == 1, "grounding scored more turns than it was given"


def test_kappa_is_one_when_two_labelers_agree_on_a_varied_set():
    assert metrics.kappa([0, 1, 0, 1, 1], [0, 1, 0, 1, 1]) == 1.0


def test_kappa_is_zero_when_the_agreement_is_only_chance():
    assert metrics.kappa([0, 1, 0, 1], [0, 0, 1, 1]) == 0.0


def test_kappa_is_undefined_when_a_labeler_never_varies():
    """Both saying "no failure" every time is perfect agreement that measured
    nothing. This is why the taxonomy asks for kappa rather than a percentage."""
    assert metrics.kappa([0, 0, 0], [0, 0, 0]) is None


def test_kappa_needs_two_lists_of_the_same_length():
    assert metrics.kappa([0, 1], [0]) is None
    assert metrics.kappa([], []) is None


# --- the eval and arena inputs -----------------------------------------------

def test_tool_accuracy_is_the_share_of_dataset_cases_that_passed():
    assert metrics._tool_accuracy({"passed": 3, "total": 4}) == 0.75
    assert metrics._tool_accuracy({"passed": 0, "total": 4}) == 0.0
    # No report at all is not a zero: nobody ran the suite.
    assert metrics._tool_accuracy({}) is None
    assert metrics._tool_accuracy({"passed": 0, "total": 0}) is None


def _race(scores: dict[str, float]) -> dict:
    return {"results": [{"spec": spec, "quality": {"score": score}}
                        for spec, score in scores.items()]}


def test_preference_rate_counts_races_the_configured_model_won():
    runs = [_race({"deepseek:pro": 8.0, "openai:gpt": 6.0}),
            _race({"deepseek:pro": 4.0, "openai:gpt": 9.0}),
            _race({"deepseek:pro": 7.0, "openai:gpt": 7.0})]
    assert metrics._preference_rate(runs, "deepseek:pro") == round(2 / 3, 4)


def test_preference_rate_needs_a_field_to_prefer_against():
    # One model scored is not a preference, and no races is not a zero.
    assert metrics._preference_rate([_race({"deepseek:pro": 8.0})], "deepseek:pro") is None
    assert metrics._preference_rate([], "deepseek:pro") is None


def _raced_case(case: str, outcomes: list[bool]) -> list[dict]:
    return [{"results": [{"completion": {"case": case, "passed": p}}]} for p in outcomes]


def test_pass_at_k_counts_a_capability_that_is_reachable():
    """One pass in k is the whole point: the question is whether the capability
    is reachable at all, not how often it lands. A pass rate would say 10%."""
    runs = _raced_case("schedule-basic", [False] * 9 + [True]) \
        + _raced_case("book-alex", [False, False])
    assert metrics._pass_at_k(runs, k=2) == 0.5


def test_pass_at_k_needs_a_case_run_more_than_once():
    assert metrics._pass_at_k(_raced_case("schedule-basic", [True]), k=2) is None
    assert metrics._pass_at_k([], k=2) is None


# --- the batch run: progress and the estimate, with no money spent -----------

JUDGE_REPLY = ('{"grounded": 1, "reward": 0.5, "reasoning_action_mismatch": 0, '
               '"information_withholding": 0}')


def test_a_run_reports_progress_and_the_estimate_is_the_truth(monkeypatch, tmp_path):
    """The button states a call count before anyone presses it. That number has
    to be what the run actually does, and progress has to reach the end — a bar
    that stops at 60 of 75 is worse than no bar.

    Every judge call is stubbed, so this costs nothing.
    """
    from pathlib import Path

    monkeypatch.setattr(metrics, "_ask", lambda p, max_tokens=700: JUDGE_REPLY)
    monkeypatch.setattr(metrics, "context", lambda: CTX)
    monkeypatch.setattr(metrics, "report_path", lambda: Path(tmp_path) / "report.json")
    monkeypatch.setattr(metrics, "references_path", lambda: Path(tmp_path) / "none.jsonl")

    seen = []
    record = metrics.run(limit=2, on_progress=lambda done, total: seen.append((done, total)))

    assert record["scored"] == 2, "the rubric pass did not score both sampled turns"
    assert seen, "progress was never reported"
    assert seen[-1][0] == seen[-1][1], f"progress stopped at {seen[-1]}"
    assert seen[-1][1] == metrics.estimate_calls(CTX["events"], 2), (
        "the estimate the button shows is not the number of calls the run makes")


def test_the_estimate_bounds_every_pass(monkeypatch):
    """Three passes, three counts, and none of them may exceed the limit."""
    turns = [t for t in metrics._turns_of(_grounding_events())]
    assert len(turns) == 2
    # two turns, both groundable: 2 rubric + 2 grounding + 4 agreement = 8
    assert metrics.estimate_calls(_grounding_events(), 2) == 8
