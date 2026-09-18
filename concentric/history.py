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
           since: str | None = None, agg: str = "mean",
           conn: sqlite3.Connection | None = None) -> dict:
    """One metric, one subject, bucketed.

    `agg` decides how a bucket is computed, and it comes from the registry rather
    than from a guess here: counts sum, ratios and times take a weighted mean over
    their own samples. Getting this wrong is the quietest way a trend chart lies.
    """
    if granularity not in BUCKETS:
        raise ValueError(f"granularity must be one of {', '.join(BUCKETS)}")
    own = conn is None
    conn = conn or connect()
    try:
        bucket = BUCKETS[granularity]
        where = "WHERE r.metric = ? AND r.subject = ?"
        params: list = [metric, subject]
        if since:
            where += " AND s.ts >= ?"
            params.append(since)
        if agg == "sum":
            expr = "SUM(r.value)"
        else:
            # A weighted mean over the samples behind each reading. Falls back to
            # a plain mean when a metric has no n, which is the only honest thing
            # left to do rather than inventing a weight.
            expr = ("CASE WHEN SUM(COALESCE(r.n, 0)) > 0 "
                    "THEN SUM(r.value * r.n) / SUM(r.n) ELSE AVG(r.value) END")
        rows = conn.execute(
            f"SELECT {bucket} AS bucket, {expr} AS value, SUM(COALESCE(r.n,0)) AS n "
            f"FROM readings r JOIN snapshots s ON s.id = r.snapshot "
            f"{where} GROUP BY bucket ORDER BY bucket", params).fetchall()
        points = [{"bucket": r["bucket"], "value": round(r["value"], 6) if r["value"] is not None else None,
                   "n": r["n"]} for r in rows]
        values = [p["value"] for p in points if p["value"] is not None]
        baseline = None
        if len(values) >= 3:
            values.sort()
            baseline = {"lo": values[len(values) // 10], "hi": values[-max(1, len(values) // 10)]}
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
                    metrics.AGG.get(args.metric, "mean"), conn)
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
