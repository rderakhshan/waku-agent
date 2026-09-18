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

REQUIRED_AGG = {"sum", "mean"}


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


def test_counts_sum_and_ratios_average():
    """A spot check against the meaning, not the map. A week of repeats is the
    repeats in that week; a week of latencies is a mean."""
    for mid in ("step_repetition", "tool_errors", "cost", "tokens_in", "consultations"):
        assert metrics.AGG[mid] == "sum", mid
    for mid in ("latency_avg", "factual_grounding", "average_reward", "hallucination_rate"):
        assert metrics.AGG[mid] == "mean", mid


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
    result = history.series("cost", "a", "daily", agg="sum", conn=conn)
    assert [p["value"] for p in result["points"]] == [1.5]
    assert result["points"][0]["n"] == 3


def test_two_snapshots_make_a_series(conn):
    history.record(_registry(cost={"a": {"value": 1.0, "n": 1}}), metrics.AGG, conn=conn)
    history.record(_registry(cost={"a": {"value": 2.0, "n": 1}}), metrics.AGG, conn=conn)
    result = history.series("cost", "a", "daily", agg="sum", conn=conn)
    assert result["points"][0]["value"] == 3.0, "two readings in one day did not sum"
    assert result["points"][0]["n"] == 2


def test_sum_and_mean_give_different_answers_on_the_same_data(conn):
    """The whole reason the rule is declared rather than assumed."""
    history.record(_registry(latency_avg={"a": {"value": 10.0, "n": 1}}),
                   metrics.AGG, conn=conn)
    history.record(_registry(latency_avg={"a": {"value": 20.0, "n": 3}}),
                   metrics.AGG, conn=conn)
    summed = history.series("latency_avg", "a", "daily", agg="sum", conn=conn)
    averaged = history.series("latency_avg", "a", "daily", agg="mean", conn=conn)
    assert summed["points"][0]["value"] == 30.0
    # weighted by the samples: (10*1 + 20*3) / 4 = 17.5, not (10+20)/2 = 15
    assert averaged["points"][0]["value"] == 17.5


def test_a_metric_with_no_samples_falls_back_to_a_plain_mean(conn):
    """A value with no n is still worth recording; inventing a weight for it
    would not be."""
    history.record(_registry(consolidation_backlog=4), metrics.AGG, conn=conn)
    history.record(_registry(consolidation_backlog=8), metrics.AGG, conn=conn)
    result = history.series("consolidation_backlog", "", "daily", agg="mean", conn=conn)
    assert result["points"][0]["value"] == 6.0


# --- buckets -----------------------------------------------------------------

def test_every_granularity_produces_a_bucket(conn):
    history.record(_registry(cost={"a": {"value": 1.0, "n": 1}}), metrics.AGG, conn=conn)
    for granularity in history.BUCKETS:
        result = history.series("cost", "a", granularity, agg="sum", conn=conn)
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
    assert history.series("cost", "a", "daily", agg="sum", conn=conn)["baseline"] is None


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
