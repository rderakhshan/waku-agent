"""DETERMINISTIC EVAL — the metric history keeps its shape and its arithmetic.

Three things this store can get wrong quietly, and all three make a trend chart
lie rather than fail:

  1. A slot with no aggregation rule. Summing a latency gives a number with no
     unit; averaging a week of counts gives one with no meaning.
  2. A reading written without its `n`. A value drawn from two turns and one
     drawn from forty render as the same line.
  3. A bucket that mixes the two. The store must not decide this per query.

Everything here runs against a temporary database — no home, no traces, no model.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from concentric import history, metrics

REQUIRED_AGG = {"delta", "last"}


def _registry(**values) -> dict:
    """A registry with only the slots named, so a test reads as its data."""
    reg = metrics.registry()
    for mid, value in values.items():
        reg[mid]["value"] = value
    return reg


@pytest.fixture()
def conn(tmp_path):
    c = history.connect(tmp_path / "metrics.db")
    yield c
    c.close()


# --- the aggregation rule ----------------------------------------------------

def test_every_slot_declares_how_it_aggregates():
    """A slot with no rule would silently default, and a default is wrong for
    half of them."""
    declared = {slot["id"] for slot in metrics.SLOTS}
    assert declared == set(metrics.AGG), (
        f"missing: {sorted(declared - set(metrics.AGG))}; "
        f"extra: {sorted(set(metrics.AGG) - declared)}")
    for mid, how in metrics.AGG.items():
        assert how in REQUIRED_AGG, f"{mid} aggregates as {how!r}"


def test_counters_delta_and_levels_last():
    """A spot check against the meaning, not the map.

    Every metric here is computed over the whole corpus, so a reading is a
    snapshot of a running total. A counter's bucket is therefore how much it
    MOVED; a level's bucket is where it ENDED UP. Neither is a sum, and the first
    version of this map said sum — it drew 255 for a metric whose value was 15.
    """
    for mid in ("step_repetition", "tool_errors", "cost", "tokens_in", "consultations"):
        assert metrics.AGG[mid] == "delta", mid
    for mid in ("latency_avg", "factual_grounding", "average_reward", "hallucination_rate"):
        assert metrics.AGG[mid] == "last", mid


# --- flattening --------------------------------------------------------------

def test_a_breakdown_becomes_one_row_per_subject():
    reg = _registry(cost={"a": {"value": 1.5, "n": 3}, "b": {"value": 2.5, "n": 4}})
    rows = [r for r in history.readings_of(reg, metrics.AGG) if r[0] == "cost"]
    assert (("cost", "agent", "a", 1.5, 3)) in rows
    assert (("cost", "agent", "b", 2.5, 4)) in rows


def test_a_scalar_becomes_one_row_with_an_empty_subject():
    reg = _registry(consolidation_backlog=6)
    rows = [r for r in history.readings_of(reg, metrics.AGG)
            if r[0] == "consolidation_backlog"]
    assert rows == [("consolidation_backlog", "system", "", 6.0, None)]


def test_a_list_of_seats_becomes_its_count():
    """The membership is a view of the traces. What a series wants from it is how
    many, and storing 20 seat names per snapshot would be storing the traces
    twice."""
    reg = _registry(fact_writers=["a", "b", "c"])
    rows = [r for r in history.readings_of(reg, metrics.AGG) if r[0] == "fact_writers"]
    assert rows == [("fact_writers", "agent", "", 3.0, 3)]


def test_a_slot_with_no_value_writes_nothing():
    reg = _registry(average_reward=None)
    assert not [r for r in history.readings_of(reg, metrics.AGG)
                if r[0] == "average_reward"]


# --- the round trip ----------------------------------------------------------

def test_record_then_read_gives_the_value_back(conn):
    history.record(_registry(cost={"a": {"value": 1.5, "n": 3}}), metrics.AGG, conn=conn)
    result = history.series("cost", "a", "daily", agg="last", conn=conn)
    assert [p["value"] for p in result["points"]] == [1.5]
    assert result["points"][0]["n"] == 3


def test_a_counter_reports_how_much_it_moved(conn):
    """Two readings of a running total, so the bucket's answer is the change —
    1.0 to 2.0 is one unit of activity, not three."""
    history.record(_registry(cost={"a": {"value": 1.0, "n": 1}}), metrics.AGG, conn=conn)
    history.record(_registry(cost={"a": {"value": 2.0, "n": 1}}), metrics.AGG, conn=conn)
    result = history.series("cost", "a", "daily", agg="delta", conn=conn)
    assert result["points"][0]["value"] == 1.0
    assert result["points"][0]["n"] == 1


def test_one_reading_is_no_change_rather_than_zero(conn):
    """A change needs two readings. Reporting zero would say "nothing happened"
    about a period nobody watched — the same lie as a placeholder drawn as a
    zero, one layer up."""
    history.record(_registry(cost={"a": {"value": 1.0, "n": 1}}), metrics.AGG, conn=conn)
    result = history.series("cost", "a", "daily", agg="delta", conn=conn)
    assert result["points"][0]["value"] is None
    assert result["points"][0]["n"] == 0


def test_a_level_reports_where_it_ended_up(conn):
    """A mean does not accumulate, so the bucket's answer is the latest reading
    rather than the distance travelled."""
    history.record(_registry(latency_avg={"a": {"value": 10.0, "n": 1}}),
                   metrics.AGG, conn=conn)
    history.record(_registry(latency_avg={"a": {"value": 20.0, "n": 3}}),
                   metrics.AGG, conn=conn)
    result = history.series("latency_avg", "a", "daily", agg="last", conn=conn)
    assert result["points"][0]["value"] == 20.0


def test_a_level_with_no_samples_still_reads(conn):
    """A value with no n is still worth recording; inventing a weight for it
    would not be."""
    history.record(_registry(consolidation_backlog=4), metrics.AGG, conn=conn)
    history.record(_registry(consolidation_backlog=8), metrics.AGG, conn=conn)
    result = history.series("consolidation_backlog", "", "daily", agg="last", conn=conn)
    assert result["points"][0]["value"] == 8.0


# --- buckets -----------------------------------------------------------------

def test_every_granularity_produces_a_bucket(conn):
    history.record(_registry(cost={"a": {"value": 1.0, "n": 1}}), metrics.AGG, conn=conn)
    for granularity in history.BUCKETS:
        result = history.series("cost", "a", granularity, agg="last", conn=conn)
        assert result["points"], f"{granularity} produced nothing"
        assert result["points"][0]["bucket"]


def test_an_unknown_granularity_is_refused_rather_than_guessed(conn):
    with pytest.raises(ValueError):
        history.series("cost", "a", "fortnightly", conn=conn)


def test_the_baseline_needs_a_few_points_before_it_claims_one(conn):
    """Two readings are not a range. A baseline from two points would flag
    everything outside them as unusual."""
    for value in (1.0, 2.0):
        history.record(_registry(cost={"a": {"value": value, "n": 1}}), metrics.AGG, conn=conn)
    assert history.series("cost", "a", "daily", agg="last", conn=conn)["baseline"] is None


# --- marks and retention -----------------------------------------------------

def test_a_mark_round_trips_and_updates(conn):
    assert history.get_mark(conn, "last_scored_ts") is None
    history.set_mark(conn, "last_scored_ts", "2026-01-01T00:00:00+00:00")
    assert history.get_mark(conn, "last_scored_ts") == "2026-01-01T00:00:00+00:00"
    history.set_mark(conn, "last_scored_ts", "2026-02-02T00:00:00+00:00")
    assert history.get_mark(conn, "last_scored_ts") == "2026-02-02T00:00:00+00:00"


def test_prune_drops_what_is_past_retention(conn):
    history.record(_registry(cost={"a": {"value": 1.0, "n": 1}}), metrics.AGG, conn=conn)
    old = (datetime.now(UTC) - timedelta(days=history.KEEP_DAYS + 1)).isoformat(timespec="seconds")
    conn.execute("UPDATE snapshots SET ts = ?", (old,))
    conn.commit()
    history.prune(conn)
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0


def test_prune_keeps_what_is_inside_retention(conn):
    history.record(_registry(cost={"a": {"value": 1.0, "n": 1}}), metrics.AGG, conn=conn)
    history.prune(conn)
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1


# --- the recorder ------------------------------------------------------------

def test_the_recorder_never_raises(monkeypatch):
    """It runs on a timer, unattended. A failure there must leave a gap in a
    chart, not take the dashboard down with it."""
    from concentric import dashboard

    def boom():
        raise RuntimeError("the seats are unreadable")

    monkeypatch.setattr(metrics, "context", boom)
    assert dashboard._record_once("timer") is None


def test_the_recorder_writes_a_snapshot(monkeypatch, tmp_path):
    from concentric import dashboard

    monkeypatch.setattr(metrics, "context", lambda: {"events": CTX_EVENTS})
    monkeypatch.setattr(history, "db_path", lambda: tmp_path / "m.db")
    snapshot = dashboard._record_once("timer")
    assert snapshot is not None
    conn = history.connect(tmp_path / "m.db")
    try:
        row = conn.execute("SELECT reason, turns FROM snapshots WHERE id = ?",
                           (snapshot,)).fetchone()
        assert row["reason"] == "timer"
        assert row["turns"] == 2
        assert conn.execute("SELECT COUNT(*) FROM readings WHERE snapshot = ?",
                            (snapshot,)).fetchone()[0] > 0
    finally:
        conn.close()


CTX_EVENTS = [
    {"type": "turn_start", "user_message": "q1", "ts": "2026-01-01T00:00:00+00:00"},
    {"type": "llm", "role": "irina", "iteration": 1, "usage": {"in": 10, "out": 5},
     "ts": "2026-01-01T00:00:01+00:00"},
    {"type": "turn_end", "reply": "a1", "ts": "2026-01-01T00:00:02+00:00"},
    {"type": "turn_start", "user_message": "q2", "ts": "2026-01-01T00:01:00+00:00"},
    {"type": "llm", "role": "irina", "iteration": 1, "usage": {"in": 12, "out": 6},
     "ts": "2026-01-01T00:01:01+00:00"},
    {"type": "turn_end", "reply": "a2", "ts": "2026-01-01T00:01:02+00:00"},
]


# --- the bookmark: never score a turn twice --------------------------------

def test_only_unscored_turns_are_picked_up():
    """The whole reason the bookmark exists. Without it every press would
    re-score the same conversations and pay for them again."""
    assert len(metrics.unscored(CTX_EVENTS, None)) == 2
    assert len(metrics.unscored(CTX_EVENTS, "2026-01-01T00:00:30+00:00")) == 1
    assert metrics.unscored(CTX_EVENTS, "2026-01-01T00:02:00+00:00") == []


def test_the_bookmark_is_compared_as_a_time_not_as_a_string():
    """The trace stamps carry microseconds and the bookmark is written to the
    second. `.` sorts below `+`, so a string comparison would call a turn at
    10.000 older than one at 10+00:00 — which is the same moment."""
    assert metrics._after("2026-01-01T00:00:10.500+00:00", "2026-01-01T00:00:10+00:00")
    assert not metrics._after("2026-01-01T00:00:09.999+00:00", "2026-01-01T00:00:10+00:00")


def test_the_estimate_only_counts_the_new_turns():
    """The button quotes the price of the work it will actually do. Without the
    bookmark it would quote a price for turns already paid for."""
    everything = metrics.estimate_calls(CTX_EVENTS, 20, None)
    nothing_new = metrics.estimate_calls(CTX_EVENTS, 20, "2026-01-01T00:02:00+00:00")
    assert everything > 0
    assert nothing_new == 0


def test_a_run_moves_the_bookmark_and_records_its_reading(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.setattr(metrics, "context", lambda: {"events": CTX_EVENTS})
    monkeypatch.setattr(metrics, "report_path", lambda: Path(tmp_path) / "report.json")
    monkeypatch.setattr(metrics, "references_path", lambda: Path(tmp_path) / "none.jsonl")
    monkeypatch.setattr(history, "db_path", lambda: Path(tmp_path) / "metrics.db")
    monkeypatch.setattr(metrics, "_ask", lambda p, max_tokens=700:
                        '{"grounded": 1, "reward": 0.5, "reasoning_action_mismatch": 0, '
                        '"information_withholding": 0}')

    metrics.run(limit=20)
    conn = history.connect(tmp_path / "metrics.db")
    try:
        assert history.get_mark(conn, "last_scored_ts") == "2026-01-01T00:01:00+00:00"
        reasons = [r["reason"] for r in conn.execute("SELECT reason FROM snapshots")]
        assert reasons == ["batch"]
    finally:
        conn.close()

    # and the second press has nothing to do
    assert metrics.estimate_calls(CTX_EVENTS, 20,
                                  history.get_mark(history.connect(tmp_path / "metrics.db"),
                                                   "last_scored_ts")) == 0


# --- the eval loop: a regression is a claim, and a claim needs a case --------
#
# Both bugs below shipped, both were silent, and nothing caught either. They live
# here rather than in a changelog because a changelog does not fail.

def _record_at(conn, mid, value, days_ago, subject="a"):
    """One reading, dated, so two of them land in different buckets."""
    sid = history.record(_registry(**{mid: {subject: {"value": value, "n": 1}}}),
                         metrics.AGG, conn=conn)
    ts = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(timespec="seconds")
    conn.execute("UPDATE snapshots SET ts = ? WHERE id = ?", (ts, sid))
    conn.commit()
    return sid


def _moved(conn, mid, start, end, days_ago, subject="a"):
    """A counter's movement inside one bucket, which takes two readings.

    A counter is a running total over the whole corpus, so its bucket's answer is
    how far it travelled — and one reading cannot say that. It is also why a
    regression for a counter is a LARGER move than the bucket before, not a
    higher number.
    """
    _record_at(conn, mid, start, days_ago, subject)
    _record_at(conn, mid, end, days_ago, subject)


def test_a_regression_is_a_move_against_the_direction(conn):
    """`step_repetition` is a metric where lower is better, so a bigger move is
    the bad one. Without the registry's direction a chart can only say the number
    changed, and a change is not a finding."""
    _moved(conn, "step_repetition", 0.0, 2.0, days_ago=1)
    _moved(conn, "step_repetition", 2.0, 9.0, days_ago=0)
    found = history.regressions("daily", conn=conn)
    assert [r["metric"] for r in found] == ["step_repetition"]
    assert found[0]["was"] == 2.0 and found[0]["now"] == 7.0


def test_a_metric_improving_is_not_a_regression(conn):
    """The same two buckets the other way round. A store that flagged any change
    would report this one too, and every fix would read as a fault."""
    _moved(conn, "step_repetition", 0.0, 9.0, days_ago=1)
    _moved(conn, "step_repetition", 9.0, 11.0, days_ago=0)
    assert history.regressions("daily", conn=conn) == []


def test_a_metric_that_has_not_said_which_way_is_better_cannot_regress(conn):
    """`neutral` is a refusal to have an opinion, not a missing one. Guessing one
    turns noise into a finding with a colour."""
    neutral = next(s["id"] for s in metrics.SLOTS
                   if s.get("direction") == "neutral" and s["id"] in metrics.AGG)
    _moved(conn, neutral, 1.0, 2.0, days_ago=1)
    _moved(conn, neutral, 2.0, 99.0, days_ago=0)
    assert history.regressions("daily", conn=conn) == []


def test_one_bucket_is_not_a_regression(conn):
    """A change needs two buckets. One is a fact about the present, not a move
    away from anything."""
    _moved(conn, "step_repetition", 0.0, 9.0, days_ago=0)
    assert history.regressions("daily", conn=conn) == []


def test_a_move_off_zero_sorts_above_a_measurable_one(conn):
    """Relative change is the only thing comparable across metrics — a cent and a
    millisecond do not share a scale. A series leaving zero has no baseline to be
    relative to, so it has to sort somewhere, and "new" beats "worse by a known
    amount"."""
    _moved(conn, "step_repetition", 0.0, 0.0, days_ago=1)
    _moved(conn, "step_repetition", 0.0, 3.0, days_ago=0)
    _moved(conn, "tool_errors", 0.0, 10.0, days_ago=1)
    _moved(conn, "tool_errors", 10.0, 30.0, days_ago=0)
    found = history.regressions("daily", conn=conn)
    assert found[0]["metric"] == "step_repetition"
    assert found[0]["relative"] is None
    # 10 repeats of movement a bucket, then 20: double, so +100%.
    assert found[1]["relative"] == 1.0


# --- the cause: which turns fed the number -----------------------------------
#
# The panel this feeds was dead on arrival and said nothing about it: the check
# compared the cause's subject against the seat OBJECT, and a role string never
# equals an object, so it was false every time.

CAUSE_EVENTS = [
    {"type": "turn_start", "user_message": "tier the model", "ts": "2026-01-01T00:00:00+00:00"},
    {"type": "tool", "role": "irina", "tool": "save_note", "args": {"text": "a"},
     "ts": "2026-01-01T00:00:01+00:00"},
    {"type": "tool", "role": "irina", "tool": "save_note", "args": {"text": "a"},
     "ts": "2026-01-01T00:00:02+00:00"},
    {"type": "turn_end", "reply": "done", "ts": "2026-01-01T00:00:03+00:00"},
    {"type": "turn_start", "user_message": "and again", "ts": "2026-01-01T00:01:00+00:00"},
    {"type": "tool", "role": "cfo-1-development", "tool": "manage_memory", "args": {},
     "ts": "2026-01-01T00:01:01+00:00"},
    {"type": "turn_end", "reply": "done", "ts": "2026-01-01T00:01:02+00:00"},
]

CAUSE_DEPT = {"seats": [
    {"role": "irina", "tools": ["save_note"]},
    {"role": "cfo-1-development", "tools": ["manage_memory"]},
]}


def test_the_cause_keeps_every_turn_when_there_is_no_upper_bound():
    """`_after(ts, None)` is True — "after nothing" — which is the right answer
    for a lower bound and the wrong one for an upper bound. Used as one, it
    skipped every turn and every cause came back empty, with no error anywhere
    and a panel that blamed a window that was never empty."""
    turns = metrics.contributions("step_repetition", "", None, None,
                                  CAUSE_EVENTS, CAUSE_DEPT)
    assert len(turns) == 2


def test_an_upper_bound_still_excludes_later_turns():
    """The fix must not have removed the bound it was guarding."""
    turns = metrics.contributions("step_repetition", "", None,
                                  "2026-01-01T00:00:30+00:00", CAUSE_EVENTS, CAUSE_DEPT)
    assert len(turns) == 1


def test_the_cause_only_lists_turns_that_involved_the_seat():
    """The panel opens on one seat. A seat that never acted in the window has no
    turns, and saying so is the honest answer — attributing the department's
    turns to whoever was clicked would blame the wrong seat."""
    assert metrics.contributions("step_repetition", "irina", None, None,
                                 CAUSE_EVENTS, CAUSE_DEPT)
    assert metrics.contributions("step_repetition", "cfo-2-operations", None, None,
                                 CAUSE_EVENTS, CAUSE_DEPT) == []


def test_a_metric_with_no_contribution_function_reports_no_value():
    """The turns are still listed — they ARE the window — but with no number
    rather than a made-up zero, which is the rule the registry follows
    everywhere else."""
    turns = metrics.contributions("success_rate", "", None, None,
                                  CAUSE_EVENTS, CAUSE_DEPT)
    assert turns
    assert all(t["value"] is None for t in turns)
