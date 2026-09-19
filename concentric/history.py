"""The department's metric history: every reading, with the time it was taken.

The Observation Lab shows what the department is doing now and forgets it a second
later. This remembers — so a number has a baseline, a change has a date, and a
regression can be traced to the turns that caused it.

Two writers, one store, one reader:

    every 15 min   --+
                     +-->  metrics.db  -->  series()  -->  the Lab
    run the batch  --+

Both write the SAME row shape, so nothing downstream has to know which produced a
number. A judged metric and a free one sit side by side in one series.

Three rules hold it together:

  * A reading carries `n`, always. A value without its sample draws the same line
    as a value with forty times the evidence, and a chart cannot tell you which.
  * Aggregation is declared per metric, not assumed. Counts SUM across a bucket;
    ratios and times take a weighted mean. Averaging a week of counts, or summing
    a week of latencies, produces a number that looks fine and is not.
  * The store is bounded. Retention drops the detail and downsamples the rest, on
    write, so the file cannot grow without end.

What it does NOT store is the cause. The traces already hold every turn; a
snapshot only says WHEN to look. Copying the turns in here would be storing the
same thing twice, and the copy would rot.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

# How long a raw reading lives before it is downsampled away, and how long any
# reading lives at all. Both are enforced on write.
DETAIL_DAYS = 7
KEEP_DAYS = 30

# The bucket for each granularity, as a SQLite expression over the ISO timestamp.
# SQLite's `/` on integers is integer division, which is what makes the
# bi-weekly and quarterly buckets work without arithmetic in Python.
BUCKETS = {
    "hourly": "strftime('%Y-%m-%dT%H', ts)",
    "daily": "date(ts)",
    "weekly": "strftime('%Y-W%W', ts)",
    "biweekly": "strftime('%Y', ts) || '-B' || (CAST(strftime('%W', ts) AS INTEGER) / 2)",
    "monthly": "strftime('%Y-%m', ts)",
    "quarterly": "strftime('%Y', ts) || '-Q' || ((CAST(strftime('%m', ts) AS INTEGER) + 2) / 3)",
    "yearly": "strftime('%Y', ts)",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  id     INTEGER PRIMARY KEY,
  ts     TEXT NOT NULL,
  reason TEXT NOT NULL,
  turns  INTEGER
);
CREATE TABLE IF NOT EXISTS readings (
  snapshot INTEGER NOT NULL,
  metric   TEXT NOT NULL,
  level    TEXT NOT NULL,
  subject  TEXT NOT NULL,
  value    REAL,
  n        INTEGER,
  PRIMARY KEY (snapshot, metric, subject)
);
CREATE INDEX IF NOT EXISTS ix_series ON readings(metric, subject, snapshot);
CREATE TABLE IF NOT EXISTS marks (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS trajectories (
  id          INTEGER PRIMARY KEY,
  trace_id    TEXT UNIQUE,
  ts          TEXT NOT NULL,
  session_id  TEXT,
  entry       TEXT,
  seats       TEXT,
  handoffs    INTEGER,
  duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS ix_trajectories_ts ON trajectories(ts);
"""

# The first cut keyed the row on `trace_id`, which made a run without one
# unrepresentable — and a run without one is exactly what a Laminar outage
# produces. The row is the local fact; the trace is the detail.
_MIGRATE_TRAJECTORIES = """
DROP INDEX IF EXISTS ix_trajectories_ts;
ALTER TABLE trajectories RENAME TO trajectories_old;
CREATE TABLE trajectories (
  id          INTEGER PRIMARY KEY,
  trace_id    TEXT UNIQUE,
  ts          TEXT NOT NULL,
  session_id  TEXT,
  entry       TEXT,
  seats       TEXT,
  handoffs    INTEGER,
  duration_ms INTEGER
);
CREATE INDEX ix_trajectories_ts ON trajectories(ts);
INSERT INTO trajectories (trace_id, ts, session_id, entry, seats, handoffs, duration_ms)
  SELECT trace_id, ts, session_id, entry, seats, handoffs, duration_ms
  FROM trajectories_old;
DROP TABLE trajectories_old;
"""


def _home_env() -> None:
    """Point waku at Irina's home before anything imports waku.config — the same
    rule every other module here follows, and the one whose absence once made the
    registry read two different corpora at once."""
    import os

    from concentric import ENTRY, MODEL, PROVIDER, SMALL_MODEL, seat_home

    os.environ.setdefault("WAKU_HOME", str(seat_home(ENTRY)))
    os.environ.setdefault("WAKU_PROVIDER", PROVIDER)
    os.environ.setdefault("WAKU_MODEL", MODEL)
    os.environ.setdefault("WAKU_SMALL_MODEL", SMALL_MODEL)


def db_path() -> Path:
    """Beside the seats, not among them.

    STATE_ROOT holds one directory per seat; a metrics.db inside it would read as
    another agent's home. It belongs to the department's observation, so it sits
    one level up — still inside .waku-concentric/, and still covered by the
    .waku-*/ gitignore rule.
    """
    from concentric import STATE_ROOT

    return STATE_ROOT.parent / "metrics.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(trajectories)")}
    if "id" not in columns:  # written before a trace_id could be absent
        conn.executescript(_MIGRATE_TRAJECTORIES)
    return conn


# --- marks -------------------------------------------------------------------
#
# Small named values: the bookmark the batch reads so it never scores a turn
# twice, and the time of the last snapshot so the timer knows when it is due.

def get_mark(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM marks WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_mark(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO marks(key, value) VALUES(?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


# --- trajectories ------------------------------------------------------------
#
# A snapshot is the department in aggregate; a trajectory is one run. The two do
# not reduce to each other, so this store keeps both: the readings answer "which
# seat is worst", and this table answers "which run was that". It is deliberately
# thin — the run itself lives in Laminar, and the trace_id is the way there.

def record_trajectory(trace_id: str | None, *, ts: str | None = None,
                      session_id: str | None = None, entry: str | None = None,
                      seats: list[str] | None = None, handoffs: int = 0,
                      duration_ms: int | None = None,
                      conn: sqlite3.Connection | None = None) -> None:
    """Index one run. Called after a trajectory finishes, not before — a row for
    a run that never completed would be a claim about nothing.

    `trace_id` is None when Laminar could not be reached. The row is written
    anyway: the run happened, and an unreachable store must not erase the fact
    of it, only the detail.
    """
    own = conn is None
    conn = conn or connect()
    try:
        columns = ("(trace_id, ts, session_id, entry, seats, handoffs, duration_ms)")
        values = (trace_id, ts or datetime.now(UTC).isoformat(), session_id,
                  entry, ",".join(seats or []), handoffs, duration_ms)
        sql = f"INSERT INTO trajectories {columns} VALUES(?, ?, ?, ?, ?, ?, ?)"
        if trace_id is not None:
            # A trace seen twice is the same run, not two.
            sql += (" ON CONFLICT(trace_id) DO UPDATE SET ts = excluded.ts,"
                    " session_id = excluded.session_id, entry = excluded.entry,"
                    " seats = excluded.seats, handoffs = excluded.handoffs,"
                    " duration_ms = excluded.duration_ms")
        conn.execute(sql, values)
        conn.commit()
    finally:
        if own:
            conn.close()


def trajectories(limit: int = 50, since: str | None = None,
                 conn: sqlite3.Connection | None = None) -> list[dict]:
    """The most recent runs, newest first — the index behind a trend point."""
    own = conn is None
    conn = conn or connect()
    try:
        sql = "SELECT * FROM trajectories"
        params: list = []
        if since:
            sql += " WHERE ts >= ?"
            params.append(since)
        sql += " ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        if own:
            conn.close()


# --- writing -----------------------------------------------------------------

def readings_of(registry: dict, agg: dict[str, str]) -> list[tuple]:
    """Flatten the registry into (metric, level, subject, value, n) rows.

    A slot with a per-seat or per-pair breakdown becomes one row per subject; a
    scalar becomes one row with an empty subject. Lists of seat names are stored
    as their COUNT — the membership is a view of the traces, and what a series
    wants from it is how many.
    """
    rows = []
    for slot in registry.values():
        value = slot.get("value")
        if value is None:
            continue
        metric, level = slot["id"], slot.get("level", "system")
        if isinstance(value, dict):
            for subject, cell in value.items():
                if isinstance(cell, dict):
                    rows.append((metric, level, str(subject), cell.get("value"), cell.get("n")))
                elif isinstance(cell, (int, float)):
                    rows.append((metric, level, str(subject), float(cell), None))
        elif isinstance(value, list):
            rows.append((metric, level, "", float(len(value)), len(value)))
        elif isinstance(value, (int, float)):
            rows.append((metric, level, "", float(value), None))
    return [r for r in rows if r[3] is not None]


def record(registry: dict, agg: dict[str, str], reason: str = "timer",
           turns: int = 0, conn: sqlite3.Connection | None = None) -> int:
    """Write one snapshot. Returns its id.

    One transaction: a half-written snapshot would read as a change that never
    happened.
    """
    own = conn is None
    conn = conn or connect()
    try:
        ts = datetime.now(UTC).isoformat(timespec="seconds")
        cur = conn.execute("INSERT INTO snapshots(ts, reason, turns) VALUES(?,?,?)",
                           (ts, reason, turns))
        snapshot = cur.lastrowid
        rows = [(snapshot, m, lv, sub, v, n) for m, lv, sub, v, n in readings_of(registry, agg)]
        conn.executemany("INSERT OR REPLACE INTO readings"
                         "(snapshot, metric, level, subject, value, n) VALUES(?,?,?,?,?,?)",
                         rows)
        conn.commit()
        set_mark(conn, "last_snapshot_ts", ts)
        return snapshot
    finally:
        if own:
            conn.close()


def prune(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Drop what is past retention, and downsample the rest.

    Two steps, because they answer different questions. The detail older than a
    week is dropped: an hourly reading from three weeks ago says nothing a daily
    one does not. Anything older than the retention window goes entirely. Both
    run on write, so the file cannot grow without end.
    """
    now = now or datetime.now(UTC)
    detail_before = (now - timedelta(days=DETAIL_DAYS)).isoformat(timespec="seconds")
    keep_before = (now - timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")

    # Keep one reading per series per HOUR once the detail window has passed.
    # `MAX(id)` per bucket is the last reading in it, which is the honest choice
    # for a snapshot series — the value at the end of the hour, not a mean of the
    # readings inside it.
    dropped_detail = conn.execute(
        "DELETE FROM readings WHERE snapshot IN ("
        "  SELECT s.id FROM snapshots s WHERE s.ts < ? AND s.id NOT IN ("
        "    SELECT MAX(s2.id) FROM snapshots s2 WHERE s2.ts >= ?"
        "    GROUP BY strftime('%Y-%m-%dT%H', s2.ts)))",
        (detail_before, keep_before)).rowcount
    dropped_old = conn.execute(
        "DELETE FROM snapshots WHERE ts < ?", (keep_before,)).rowcount
    conn.commit()
    return {"dropped_detail": dropped_detail, "dropped_snapshots": dropped_old}


# --- reading -----------------------------------------------------------------

def series(metric: str, subject: str = "", granularity: str = "daily",
           since: str | None = None, agg: str = "last",
           conn: sqlite3.Connection | None = None) -> dict:
    """One metric, one subject, bucketed.

    `agg` decides how a bucket is computed, and it comes from the registry rather
    than from a guess here:

      delta  the metric only grows, so its reading is a running total over the
             whole corpus and the bucket's answer is how much it moved. Summing
             three readings of "15 repeats" gives 45, which describes nothing.
      last   the metric is a level or a running mean, so its reading already is
             the answer and the bucket takes the most recent one.

    Both are computed from the readings inside the bucket, never across buckets.
    """
    if granularity not in BUCKETS:
        raise ValueError(f"granularity must be one of {', '.join(BUCKETS)}")
    if agg not in ("delta", "last"):
        raise ValueError("agg must be 'delta' or 'last'")
    own = conn is None
    conn = conn or connect()
    try:
        bucket = BUCKETS[granularity]
        where = "WHERE r.metric = ? AND r.subject = ?"
        params: list = [metric, subject]
        if since:
            where += " AND s.ts >= ?"
            params.append(since)

        if agg == "delta":
            # MAX - MIN, which for a monotonic counter is last - first. NULL when
            # the bucket holds a single reading: a change needs two, and reporting
            # zero would say "nothing happened" about a period nobody watched.
            # The first bucket therefore covers only what was recorded inside it,
            # which is the honest answer — nothing was watching before that.
            rows = conn.execute(
                f"SELECT {bucket} AS bucket, "
                f"  CASE WHEN COUNT(*) > 1 THEN MAX(r.value) - MIN(r.value) END AS value, "
                f"  COUNT(*) - 1 AS n "
                f"FROM readings r JOIN snapshots s ON s.id = r.snapshot "
                f"{where} GROUP BY bucket ORDER BY bucket", params).fetchall()
        else:
            # The most recent reading in each bucket. A window function rather
            # than a correlated subquery, because snapshots are ordered by id and
            # id order is time order.
            rows = conn.execute(
                f"SELECT bucket, value, n FROM ("
                f"  SELECT {bucket} AS bucket, r.value AS value, r.n AS n,"
                f"         ROW_NUMBER() OVER (PARTITION BY {bucket} ORDER BY s.id DESC) AS rn"
                f"  FROM readings r JOIN snapshots s ON s.id = r.snapshot"
                f"  {where}) WHERE rn = 1 ORDER BY bucket", params).fetchall()

        points = [{"bucket": r["bucket"],
                   "value": round(r["value"], 6) if r["value"] is not None else None,
                   "n": r["n"]} for r in rows]
        values = [p["value"] for p in points if p["value"] is not None]
        baseline = None
        if len(values) >= 3:
            ordered = sorted(values)
            baseline = {"lo": ordered[len(ordered) // 10],
                        "hi": ordered[-max(1, len(ordered) // 10)]}
        return {"metric": metric, "subject": subject, "granularity": granularity,
                "agg": agg, "points": points, "baseline": baseline}
    finally:
        if own:
            conn.close()


def subjects(metric: str, conn: sqlite3.Connection | None = None) -> list[str]:
    own = conn is None
    conn = conn or connect()
    try:
        rows = conn.execute("SELECT DISTINCT subject FROM readings WHERE metric = ? "
                            "ORDER BY subject", (metric,)).fetchall()
        return [r["subject"] for r in rows]
    finally:
        if own:
            conn.close()


# --- the eval loop -----------------------------------------------------------
#
# A chart can say a number moved. It cannot say that moving was bad, which is
# what the registry's `direction` is for, and a change against it is the only
# thing here worth calling a regression.
#
# This is where the store stops being a record and becomes a loop. A regression
# is a claim about the department, and a claim is worth nothing until something
# fails when it stops being true. So the fix for one is a deterministic eval:
# the case goes in `evals/deterministic/`, and it stays red until the department
# stops doing the thing. Both bugs this module has already shipped were that
# shape — silent, wrong, and caught by nothing — which is why the cases pinning
# them live beside this function rather than in a changelog.

def regressions(granularity: str = "daily", since: str | None = None,
                min_n: int = 1, conn: sqlite3.Connection | None = None) -> list[dict]:
    """The series that moved the wrong way in their last bucket, worst first.

    A metric that has not declared which way is better cannot regress. `neutral`
    is not a missing opinion to be guessed at; it is a refusal to have one, and
    inventing one turns noise into a finding with a colour.

    Ranked by relative change, because that is the only thing comparable across
    metrics — a cent and a millisecond do not share a scale. A series that moved
    off zero has no baseline to be relative to, so it sorts first: a metric
    leaving zero is unambiguously something new.
    """
    from concentric import metrics

    own = conn is None
    conn = conn or connect()
    try:
        direction = {slot["id"]: slot.get("direction", "neutral")
                     for slot in metrics.SLOTS}
        pairs = conn.execute("SELECT DISTINCT metric, subject FROM readings "
                             "ORDER BY metric, subject").fetchall()
        found: list[dict] = []
        for row in pairs:
            metric, subject = row["metric"], row["subject"]
            way = direction.get(metric, "neutral")
            if way not in ("higher", "lower"):
                continue
            points = [p for p in series(metric, subject, granularity, since,
                                        metrics.AGG.get(metric, "last"),
                                        conn)["points"] if p["value"] is not None]
            # Two buckets, because a change needs two. One reading is a fact
            # about the present, not a move away from anything.
            if len(points) < 2:
                continue
            was, now = points[-2], points[-1]
            if now["n"] < min_n:
                continue
            change = now["value"] - was["value"]
            if change == 0:
                continue
            if (change < 0) if way == "higher" else (change > 0):
                slot = metrics.registry()[metric]
                found.append({
                    "metric": metric,
                    "label": slot.get("label", metric),
                    "subject": subject,
                    "direction": way,
                    "unit": slot.get("unit", ""),
                    "was": was["value"],
                    "now": now["value"],
                    "change": change,
                    "relative": (abs(change) / abs(was["value"])
                                 if was["value"] else None),
                    "bucket": now["bucket"],
                    "n": now["n"],
                })
        # `is not None` first, so a move off zero (no baseline) sorts above every
        # measurable one, then the largest relative move.
        found.sort(key=lambda r: (r["relative"] is not None,
                                  -(r["relative"] or 0.0),
                                  r["metric"], r["subject"]))
        return found
    finally:
        if own:
            conn.close()


def main() -> None:
    import argparse
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass

    from concentric import metrics

    parser = argparse.ArgumentParser(prog="concentric.history")
    parser.add_argument("--metric")
    parser.add_argument("--subject", default="")
    parser.add_argument("--granularity", default="daily", choices=sorted(BUCKETS))
    parser.add_argument("--since")
    parser.add_argument("--record", action="store_true",
                        help="take a snapshot now, without calling a model")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--regressions", action="store_true",
                        help="the series that moved the wrong way, worst first")
    parser.add_argument("--trajectories", action="store_true",
                        help="the most recent traced runs, newest first")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    conn = connect()
    if args.record:
        reg = metrics.compute(metrics.context())
        snapshot = record(reg, metrics.AGG, reason="manual", conn=conn)
        print(f"snapshot {snapshot} written to {db_path()}")
        return
    if args.prune:
        print(json.dumps(prune(conn), indent=2))
        return
    if args.regressions:
        rows = regressions(args.granularity, args.since, conn=conn)
        if args.json:
            print(json.dumps(rows, indent=2))
            return
        if not rows:
            print(f"nothing moved the wrong way ({args.granularity})")
            return
        print(f"regressions - {args.granularity}")
        for r in rows:
            moved = (f"{r['relative'] * 100:+.0f}%"
                     if r["relative"] is not None else "off zero")
            print(f"  {r['metric']:<24} {r['subject'] or '(all)':<18} "
                  f"{r['was']} -> {r['now']}  {moved}  ({r['bucket']})")
        return
    if args.trajectories:
        rows = trajectories(conn=conn)
        if args.json:
            print(json.dumps(rows, indent=2))
            return
        if not rows:
            print("no trajectories recorded (tracing must be on for a run to land here)")
            return
        print(f"trajectories - {len(rows)} most recent")
        for r in rows:
            print(f"  {r['ts']}  {r['entry'] or '?':<8} "
                  f"{r['handoffs'] or 0} handoffs  {r['trace_id'] or '(untraced)'}")
        return
    if not args.metric:
        rows = conn.execute(
            "SELECT s.ts, s.reason, COUNT(r.metric) AS readings FROM snapshots s "
            "LEFT JOIN readings r ON r.snapshot = s.id GROUP BY s.id "
            "ORDER BY s.id DESC LIMIT 20").fetchall()
        for r in rows:
            print(f"  {r['ts']}  {r['reason']:<8} {r['readings']} readings")
        print(f"\n{db_path()}")
        return

    result = series(args.metric, args.subject, args.granularity, args.since,
                    metrics.AGG.get(args.metric, "last"), conn)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"{args.metric} · {args.subject or '(all)'} · {args.granularity} · {result['agg']}")
    print(f"  {'bucket':<16} {'value':>12} {'n':>8}")
    for p in result["points"]:
        print(f"  {p['bucket']:<16} {p['value']:>12} {p['n']:>8}")
    if result["baseline"]:
        print(f"  usual range: {result['baseline']['lo']} .. {result['baseline']['hi']}")


if __name__ == "__main__":
    main()
