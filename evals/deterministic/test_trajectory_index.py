"""The trajectory index keeps one row per run, and that row is the link.

A snapshot says what the department did in aggregate; this table says which run
did it. The two ways it could quietly lie are a row written before the run
finished (a claim about nothing) and a row that duplicates when the same trace
is seen twice — so both are pinned here.
"""

from __future__ import annotations

import sqlite3

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


# --- a run Laminar never saw ------------------------------------------------
#
# The row is the local fact; the trace is the detail. An unreachable store must
# cost the detail and never the fact, so an absent trace id has to be storable.

def test_an_untraced_run_is_still_recorded(conn):
    history.record_trajectory(None, entry="irina", handoffs=2, conn=conn)
    rows = history.trajectories(conn=conn)
    assert len(rows) == 1
    assert rows[0]["trace_id"] is None
    assert rows[0]["entry"] == "irina"
    assert rows[0]["handoffs"] == 2


def test_two_untraced_runs_are_two_rows(conn):
    """NULL is not a key, so these must not collapse into one another."""
    history.record_trajectory(None, conn=conn)
    history.record_trajectory(None, conn=conn)
    assert len(history.trajectories(conn=conn)) == 2


def test_the_ask_the_answer_and_the_broken_rules_round_trip(conn):
    history.record_trajectory("t1", task="the ask", reply="the answer",
                              violations=["in_scope", "repeated"], conn=conn)
    row = history.trajectories(conn=conn)[0]
    assert row["task"] == "the ask"
    assert row["reply"] == "the answer"
    assert row["violations"] == "in_scope,repeated"


def test_failures_returns_only_the_runs_that_broke_a_rule(conn):
    history.record_trajectory("ok", violations=[], conn=conn)
    history.record_trajectory("bad", violations=["unanswered"], conn=conn)
    assert [r["trace_id"] for r in history.failures(conn=conn)] == ["bad"]


def test_an_older_table_gains_the_new_columns_in_place(tmp_path):
    """task/reply/violations arrive by ALTER, not by rebuilding the table."""
    path = tmp_path / "older.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE trajectories ("
        " id INTEGER PRIMARY KEY, trace_id TEXT UNIQUE, ts TEXT NOT NULL,"
        " session_id TEXT, entry TEXT, seats TEXT, handoffs INTEGER,"
        " duration_ms INTEGER);"
        "INSERT INTO trajectories (trace_id, ts, entry)"
        " VALUES ('t','2026-01-01T00:00:00+00:00','irina');")
    raw.commit()
    raw.close()

    conn = history.connect(path)
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(trajectories)")}
        assert {"task", "reply", "violations"} <= columns
        assert history.trajectories(conn=conn)[0]["trace_id"] == "t"
    finally:
        conn.close()


def test_an_old_table_is_migrated_and_keeps_its_rows(tmp_path):
    """The first cut keyed on trace_id. An existing file must survive that."""
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE trajectories ("
        " trace_id TEXT PRIMARY KEY, ts TEXT NOT NULL, session_id TEXT,"
        " entry TEXT, seats TEXT, handoffs INTEGER, duration_ms INTEGER);"
        "INSERT INTO trajectories VALUES"
        " ('t-old','2026-01-01T00:00:00+00:00','s','irina','irina',1,10);")
    raw.commit()
    raw.close()

    conn = history.connect(path)
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(trajectories)")}
        assert "id" in columns
        rows = history.trajectories(conn=conn)
        assert [r["trace_id"] for r in rows] == ["t-old"]
        assert rows[0]["handoffs"] == 1
        # and the new shape works on the migrated file
        history.record_trajectory(None, conn=conn)
        assert len(history.trajectories(conn=conn)) == 2
    finally:
        conn.close()
