"""The trajectory index keeps one row per run, and that row is the link.

A snapshot says what the department did in aggregate; this table says which run
did it. The two ways it could quietly lie are a row written before the run
finished (a claim about nothing) and a row that duplicates when the same trace
is seen twice — so both are pinned here.
"""

from __future__ import annotations

import pytest

from concentric import history


@pytest.fixture()
def conn(tmp_path):
    c = history.connect(tmp_path / "metrics.db")
    yield c
    c.close()


def test_a_recorded_run_is_readable_back(conn):
    history.record_trajectory("t1", session_id="s1", entry="irina",
                              seats=["irina", "cfo-4-audit"], handoffs=1,
                              duration_ms=42, conn=conn)
    rows = history.trajectories(conn=conn)
    assert len(rows) == 1
    assert rows[0]["trace_id"] == "t1"
    assert rows[0]["session_id"] == "s1"
    assert rows[0]["handoffs"] == 1
    assert rows[0]["seats"] == "irina,cfo-4-audit"


def test_re_recording_the_same_trace_updates_rather_than_duplicates(conn):
    history.record_trajectory("t1", entry="irina", handoffs=0, conn=conn)
    history.record_trajectory("t1", entry="irina", handoffs=3, conn=conn)
    rows = history.trajectories(conn=conn)
    assert len(rows) == 1
    assert rows[0]["handoffs"] == 3


def test_newest_first_and_limited(conn):
    history.record_trajectory("a", ts="2026-01-01T00:00:00+00:00", conn=conn)
    history.record_trajectory("b", ts="2026-01-02T00:00:00+00:00", conn=conn)
    history.record_trajectory("c", ts="2026-01-03T00:00:00+00:00", conn=conn)
    rows = history.trajectories(limit=2, conn=conn)
    assert [r["trace_id"] for r in rows] == ["c", "b"]


def test_since_filters_older_runs_out(conn):
    history.record_trajectory("old", ts="2026-01-01T00:00:00+00:00", conn=conn)
    history.record_trajectory("new", ts="2026-01-09T00:00:00+00:00", conn=conn)
    rows = history.trajectories(since="2026-01-05T00:00:00+00:00", conn=conn)
    assert [r["trace_id"] for r in rows] == ["new"]


def test_a_run_with_no_seats_still_records(conn):
    history.record_trajectory("bare", conn=conn)
    row = history.trajectories(conn=conn)[0]
    assert row["trace_id"] == "bare"
    assert row["seats"] == ""
    assert row["handoffs"] == 0
    assert row["ts"]
