"""The metric registry: every metric in the evaluation taxonomy, one slot each.

The taxonomy lives in `docs/llm-agent-evaluation-taxonomy.md`. That document is
a reference — it lists what the field measures. This module is the other half:
which of those this repository can actually say something about, and for the ones
it cannot, what would be needed.

Nothing here draws anything. Phase 0 is the registry and the catalogue, because
a metric's *shape* — is it a scalar or a series, does it change per turn or per
run, what does it cost — decides how it should ever be shown, and that shape is
only knowable once the value exists. Design after looking, not before.

Three rules hold this together:

  * Every slot has a value or an explicit None. There is no third thing.
  * `None` is never 0. A missing measurement and a measured zero are different
    facts, and conflating them silently deflates every aggregate that touches
    them. This is the failure mode `waku/memory/semantic/base.py` names.
  * A `None` carries a `filler`: the sentence that says what would fill it.

Everything here is a pure function of data already on disk. No model calls, no
network, no writes. The judge-dependent metrics report `state="ready"` and stay
None until a batch run fills them.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime
from typing import Any

# --- the slots ---------------------------------------------------------------
#
# state      computed    the value is here now
#            ready       the data or capability exists, nobody has wired it up
#            blocked     something this repository does not have is required
#            placeholder no work yet; arrives with a future capability
# kind       scalar      one number
#            series      a number per seat, per ring, or per bucket
# changes    per-turn / per-run / rarely / never
# direction  higher / lower / neutral  — which way is better, so a delta reads
# unit       what the number is
# source     trace / state / eval / judge / external / human

SLOTS: tuple[dict[str, Any], ...] = (
    # -- did it do the job? ---------------------------------------------------
    {"id": "success_rate", "label": "Success rate (SR / TSR)", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "higher",
     "source": "eval", "filler": "an eval run: make gate writes eval_report.json"},
    {"id": "tool_use_accuracy", "label": "Tool-use accuracy", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "higher",
     "source": "eval",
     "filler": "per-case tool and arg matching, exported from the deterministic suite"},
    {"id": "average_reward", "label": "Average reward", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "score", "direction": "higher",
     "source": "judge", "filler": "the judge suite's 0-1 scores, averaged"},
    {"id": "pass_at_k", "label": "Pass@k", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "probability", "direction": "higher",
     "source": "eval", "filler": "each dataset case run k times"},
    {"id": "hallucination_rate", "label": "Hallucination rate", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "lower",
     "source": "judge", "filler": "a groundedness judge over reply versus retrieved facts"},
    {"id": "factual_grounding", "label": "Factual grounding", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "higher",
     "source": "judge", "filler": "the same judge, scored the other way"},
    {"id": "context_retention", "label": "Context retention", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "higher",
     "source": "judge", "filler": "multi-turn scenarios probing a seat's own store"},

    # -- how fast, how much? --------------------------------------------------
    {"id": "latency_avg", "label": "Latency, mean", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "ms", "direction": "lower",
     "source": "trace", "filler": "a turn with an llm call in the trace"},
    {"id": "latency_p95", "label": "Latency, p95", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "ms", "direction": "lower",
     "source": "trace", "filler": "a turn with an llm call in the trace"},
    {"id": "throughput", "label": "Throughput", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "turns/min", "direction": "higher",
     "source": "trace", "filler": "a completed turn in the trace"},
    {"id": "tokens_in", "label": "Tokens in", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "tokens", "direction": "lower",
     "source": "trace", "filler": "an llm call in the trace"},
    {"id": "tokens_out", "label": "Tokens out", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "tokens", "direction": "lower",
     "source": "trace", "filler": "an llm call in the trace"},
    {"id": "cost", "label": "Spend", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "usd", "direction": "lower",
     "source": "trace", "filler": "an llm call whose model has a price"},
    {"id": "tool_errors", "label": "Tool errors", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "calls", "direction": "lower",
     "source": "trace", "filler": "a tool call in the trace"},
    {"id": "gate_retrieval_ratio", "label": "Gate retrieval ratio", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "ratio", "direction": "neutral",
     "source": "trace", "filler": "a gate decision in the trace"},
    {"id": "cost_per_ring", "label": "Spend per ring", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "usd", "direction": "lower",
     "source": "trace", "filler": "a seat with attributed spend"},
    {"id": "context_growth", "label": "Context growth per iteration", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "tokens", "direction": "lower",
     "source": "trace", "filler": "an llm call carrying token usage"},

    # -- how does it fail? ----------------------------------------------------
    {"id": "step_repetition", "label": "Step repetition", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "repeats", "direction": "lower",
     "source": "trace", "filler": "a tool call in the trace"},
    {"id": "unanswered_handoffs", "label": "Unanswered hand-offs", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "handoffs", "direction": "lower",
     "source": "trace", "filler": "a delegate call in the trace"},
    {"id": "premature_terminations", "label": "Premature terminations", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "turns", "direction": "lower",
     "source": "trace", "filler": "a turn in the trace"},
    {"id": "mandate_breaches", "label": "Mandate breaches", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "calls", "direction": "lower",
     "source": "trace", "filler": "a seat with a declared tool list"},
    {"id": "mast_reasoning_action_mismatch", "label": "MAST: reasoning-action mismatch",
     "state": "ready", "kind": "scalar", "changes": "per-run", "unit": "traces",
     "direction": "lower", "source": "judge",
     "filler": "a labeling judge over multi-agent traces"},
    {"id": "mast_information_withholding", "label": "MAST: information withholding",
     "state": "ready", "kind": "scalar", "changes": "per-run", "unit": "traces",
     "direction": "lower", "source": "judge",
     "filler": "the same judge, a different label"},
    {"id": "mast_annotator_agreement", "label": "Cohen's kappa (labeler agreement)",
     "state": "ready", "kind": "scalar", "changes": "per-run", "unit": "kappa",
     "direction": "higher", "source": "judge",
     "filler": "two labelers over the same traces"},

    # -- how does work move? --------------------------------------------------
    {"id": "delegation_depth", "label": "Delegation depth reached", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "ring", "direction": "neutral",
     "source": "trace", "filler": "an event carrying a ring"},
    {"id": "delegation_breadth", "label": "Distinct seats tasked", "state": "computed",
     "kind": "scalar", "changes": "rarely", "unit": "seats", "direction": "neutral",
     "source": "trace", "filler": "a delegate or consult call"},
    {"id": "handoff_latency", "label": "Hand-off latency", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "ms", "direction": "lower",
     "source": "trace", "filler": "a delegate call the target answered inside its turn"},
    {"id": "consultations", "label": "Peer consultations", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "calls", "direction": "neutral",
     "source": "trace", "filler": "a consult_peer call"},
    {"id": "peer_pairs_used", "label": "Peer pairs actually used", "state": "computed",
     "kind": "series", "changes": "rarely", "unit": "pairs", "direction": "neutral",
     "source": "trace", "filler": "a consult or delegate call with a known caller"},

    # -- what does it learn? --------------------------------------------------
    {"id": "memory_growth", "label": "Memory per seat", "state": "computed",
     "kind": "series", "changes": "rarely", "unit": "rows", "direction": "neutral",
     "source": "state", "filler": "a seat with a state.db"},
    {"id": "fact_writers", "label": "Seats that wrote facts", "state": "computed",
     "kind": "series", "changes": "rarely", "unit": "seats", "direction": "neutral",
     "source": "state", "filler": "a fact carrying a seat tag"},
    {"id": "seats_without_memory", "label": "Built seats with no memory", "state": "computed",
     "kind": "series", "changes": "rarely", "unit": "seats", "direction": "lower",
     "source": "state", "filler": "a built seat"},
    {"id": "idle_seats", "label": "Seats with state, never tasked", "state": "computed",
     "kind": "series", "changes": "rarely", "unit": "seats", "direction": "lower",
     "source": "state", "filler": "a built seat that has never been tasked"},
    {"id": "consolidation_backlog", "label": "Unconsolidated chats", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "chats", "direction": "lower",
     "source": "state", "filler": "a chat log with rows in it"},

    # -- psychometric (a judge can be asked; nobody has) ----------------------
    {"id": "argument_confidence", "label": "Argument confidence", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "scale", "direction": "neutral",
     "source": "judge", "filler": "a self-report elicitation over a debate protocol"},
    {"id": "cognitive_effort", "label": "Cognitive effort", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "scale", "direction": "neutral",
     "source": "judge", "filler": "the same elicitation, a different scale"},
    {"id": "cognitive_dissonance", "label": "Cognitive dissonance", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "scale", "direction": "lower",
     "source": "judge",
     "filler": "a seat's stated position compared with its own earlier output"},
    {"id": "empathy", "label": "Empathy", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "scale", "direction": "neutral",
     "source": "judge", "filler": "the same elicitation, meaningful once a seat is user-facing"},

    # -- preference and human factors -----------------------------------------
    {"id": "preference_rate", "label": "Preference rate", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "higher",
     "source": "judge", "filler": "the arena's pairwise races, scored by a judge"},
    {"id": "sus", "label": "SUS (dashboard usability)", "state": "ready",
     "kind": "scalar", "changes": "rarely", "unit": "score", "direction": "higher",
     "source": "human", "filler": "the ten-question System Usability Scale, answered by a person"},

    # -- semantic (needs vectors this repository does not produce) ------------
    {"id": "stance_convergence", "label": "Final stance convergence", "state": "blocked",
     "kind": "scalar", "changes": "per-run", "unit": "cosine", "direction": "higher",
     "source": "judge", "filler": "an embedding provider; no public embed(text) exists"},
    {"id": "stance_shift", "label": "Total stance shift", "state": "blocked",
     "kind": "scalar", "changes": "per-run", "unit": "cosine", "direction": "neutral",
     "source": "judge", "filler": "the same embedding provider"},
    {"id": "semantic_diversity", "label": "Semantic diversity", "state": "blocked",
     "kind": "scalar", "changes": "per-run", "unit": "cosine", "direction": "neutral",
     "source": "judge", "filler": "the same embedding provider"},
    {"id": "bertscore", "label": "BERTScore", "state": "blocked",
     "kind": "scalar", "changes": "per-run", "unit": "score", "direction": "higher",
     "source": "judge", "filler": "the same embedding provider"},
    {"id": "bleu_rouge_meteor", "label": "BLEU / ROUGE / METEOR", "state": "blocked",
     "kind": "scalar", "changes": "per-run", "unit": "score", "direction": "higher",
     "source": "external",
     "filler": "gold reference answers, which do not exist for an open-ended risk judgement"},

    # -- benchmarks -----------------------------------------------------------
    {"id": "bench_code", "label": "Benchmark: code and software engineering",
     "state": "ready", "kind": "scalar", "changes": "per-run", "unit": "ratio",
     "direction": "higher", "source": "external",
     "filler": "evals/coding.jsonl already is a SWE-bench analogue"},
    {"id": "bench_agentic", "label": "Benchmark: agentic and interactive",
     "state": "ready", "kind": "scalar", "changes": "per-run", "unit": "ratio",
     "direction": "higher", "source": "external",
     "filler": "a MultiAgentBench or tau-bench adapter; the department is the right shape"},
    {"id": "bench_general", "label": "Benchmark: academic and general reasoning",
     "state": "placeholder", "kind": "scalar", "changes": "per-run", "unit": "ratio",
     "direction": "higher", "source": "external",
     "filler": "an MMLU-shaped adapter, when seats take general duties"},
    {"id": "bench_math", "label": "Benchmark: mathematical problem solving",
     "state": "placeholder", "kind": "scalar", "changes": "per-run", "unit": "ratio",
     "direction": "higher", "source": "external",
     "filler": "a MATH-shaped adapter, when a seat holds a mathematical mandate"},
    {"id": "bench_domain", "label": "Benchmark: model risk management",
     "state": "placeholder", "kind": "scalar", "changes": "per-run", "unit": "ratio",
     "direction": "higher", "source": "external",
     "filler": "a domain benchmark; none exists yet, so this one would be authored"},
    {"id": "bench_multimodal", "label": "Benchmark: multimodal and embodied",
     "state": "placeholder", "kind": "scalar", "changes": "per-run", "unit": "ratio",
     "direction": "higher", "source": "external",
     "filler": "a GAIA-shaped adapter, when Irina accepts an image"},
    {"id": "bench_task_selection", "label": "Benchmark: task selection and quality",
     "state": "placeholder", "kind": "scalar", "changes": "per-run", "unit": "ratio",
     "direction": "higher", "source": "external",
     "filler": "FineTasks scores benchmarks, not agents; nothing here to measure"},
)


def registry() -> dict[str, dict]:
    """A fresh copy of the slots, keyed by id."""
    return {slot["id"]: {**slot, "value": None, "cost_ms": None} for slot in SLOTS}


# --- reading the trace -------------------------------------------------------

def _parse(ts: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _turns_of(events: list[dict]) -> list[list[dict]]:
    """Group events into turns the way `collect()` does: a turn opens at
    turn_start and closes at turn_end, and anything outside one belongs to no
    turn.

    Closing at turn_end is not cosmetic. Without it a group runs on into the next
    turn's events, the span balloons, and every metric built on turn boundaries
    reports the idle gap between sessions instead of the work."""
    out: list[list[dict]] = []
    current: list[dict] | None = None
    for ev in events:
        kind = ev.get("type")
        if kind == "turn_start":
            current = [ev]
            out.append(current)
        elif current is not None:
            current.append(ev)
            if kind == "turn_end":
                current = None
    return out


def _turn_spans(events: list[dict]) -> list[tuple[datetime, datetime]]:
    """(turn_start, last llm call) per turn — waku's own definition of a turn's
    duration (`dashboard.py`: start to the last llm call). Matching it keeps this
    module's numbers comparable with the dashboard's."""
    spans = []
    for turn in _turns_of(events):
        start = next((_parse(e.get("ts")) for e in turn
                      if e.get("type") == "turn_start"), None)
        llms = [t for t in (_parse(e.get("ts")) for e in turn
                            if e.get("type") == "llm") if t]
        if start and llms:
            spans.append((start, max(llms)))
    return spans


def _by_role(events: list[dict]) -> dict[str, list[datetime]]:
    acc: dict[str, list[datetime]] = {}
    for ev in events:
        role, ts = ev.get("role"), _parse(ev.get("ts"))
        if role and ts:
            acc.setdefault(role, []).append(ts)
    for stamps in acc.values():
        stamps.sort()
    return acc


def _delegations(events: list[dict]) -> list[tuple[str | None, str, datetime]]:
    """(caller, target, when) for every delegate and consult_peer call.

    The caller is None on the four oldest delegate events in this corpus: they
    predate the `role` stamp. They still count toward anything that only needs
    the target, and are skipped by anything that draws a graph."""
    out = []
    for ev in events:
        if ev.get("type") != "tool" or ev.get("tool") not in ("delegate", "consult_peer"):
            continue
        target = (ev.get("args") or {}).get("role")
        ts = _parse(ev.get("ts"))
        if target and ts:
            out.append((ev.get("role"), target, ts))
    return out


# --- the computations --------------------------------------------------------

def _success_rate(eval_report: dict | None) -> float | None:
    """The deterministic suite's pass ratio. It is the closest thing to SR that
    exists on disk: each case is a task, and passing is succeeding."""
    suites = (eval_report or {}).get("suites") or {}
    det = suites.get("deterministic") or {}
    passed, failed = det.get("passed") or 0, det.get("failed") or 0
    total = passed + failed
    return round(passed / total, 4) if total else None


def _throughput(events: list[dict]) -> float | None:
    """Turns per minute of ACTIVE time — the sum of the turns' own durations.

    Wall-clock span is useless here and the first catalogue run proved it: this
    corpus spans days of idle gaps, so turns-per-day read as 0.002 and said
    nothing. What a reader wants is how fast the thing works when it is working.
    """
    spans = _turn_spans(events)
    active = sum((end - start).total_seconds() for start, end in spans)
    if not spans or active <= 0:
        return None
    return round(len(spans) / (active / 60), 3)


def _gate_retrieval_ratio(stats: dict) -> float | None:
    skip, ret = stats.get("gate_skips") or 0, stats.get("gate_retrieves") or 0
    total = skip + ret
    return round(ret / total, 4) if total else None


def _step_repetition(events: list[dict]) -> int | None:
    """The same tool called with the same args twice inside one turn — MAST's
    step repetition, and a pure pattern match over the trace.

    None when nothing ran, not 0. A count of zero over an empty corpus reads as
    a clean bill of health, and the truth is that nobody looked.
    """
    if not any(e.get("type") == "tool" for e in events):
        return None
    repeats = 0
    for turn in _turns_of(events):
        seen = set()
        for ev in turn:
            if ev.get("type") != "tool":
                continue
            key = (ev.get("role"), ev.get("tool"),
                   json.dumps(ev.get("args") or {}, sort_keys=True, default=str))
            if key in seen:
                repeats += 1
            seen.add(key)
    return repeats


def _unanswered_handoffs(events: list[dict]) -> int | None:
    """A delegate whose target never emitted anything afterwards. The most
    expensive silent failure in a delegation graph: the work simply stopped."""
    delegations = _delegations(events)
    if not delegations:
        return None
    stamps = _by_role(events)
    count = 0
    for _, target, when in delegations:
        if not any(t > when for t in stamps.get(target, ())):
            count += 1
    return count


def _premature_terminations(events: list[dict]) -> int | None:
    """A turn that never ended, or ended with nothing to say."""
    turns = _turns_of(events)
    if not turns:
        return None
    count = 0
    for turn in turns:
        ends = [e for e in turn if e.get("type") == "turn_end"]
        if not ends or not (ends[-1].get("reply") or "").strip():
            count += 1
    return count


def _mandate_breaches(events: list[dict], department: dict) -> int | None:
    """A seat calling a tool it does not hold. The registry is the roster's own
    tool list, so this reads the rule rather than restating it."""
    calls = [e for e in events if e.get("type") == "tool"]
    if not calls:
        return None
    allowed = {s["role"]: set(s.get("tools") or [])
               for s in department.get("seats", [])}
    count = 0
    for ev in calls:
        role, tool = ev.get("role"), ev.get("tool")
        if role in allowed and tool and tool not in allowed[role]:
            count += 1
    return count


def _consultations(events: list[dict]) -> int | None:
    if not any(e.get("type") == "tool" for e in events):
        return None
    return sum(1 for e in events
               if e.get("type") == "tool" and e.get("tool") == "consult_peer")


def _handoff_latency(events: list[dict]) -> int | None:
    """Milliseconds from a delegate call to the target's first event IN THE SAME
    TURN.

    Scoping to the turn is the whole metric, and the first catalogue run showed
    why: across turns the gap is the idle time between sessions, which reported
    as 860 seconds and was not a hand-off at all.
    """
    gaps = []
    for turn in _turns_of(events):
        stamps = _by_role(turn)
        for _, target, when in _delegations(turn):
            nxt = next((t for t in stamps.get(target, ()) if t > when), None)
            if nxt:
                gaps.append((nxt - when).total_seconds() * 1000)
    return round(statistics.median(gaps)) if gaps else None


def _delegation_depth(events: list[dict]) -> int | None:
    rings = [e.get("ring") for e in events if isinstance(e.get("ring"), int)]
    return max(rings) if rings else None


def _peer_pairs(events: list[dict]) -> list[str] | None:
    """Who consults whom. Unattributed events are skipped rather than drawn as a
    "?" node — a graph edge with an unknown end is not an edge."""
    pairs = sorted({f"{src}>{dst}" for src, dst, _ in _delegations(events)
                    if src and src != dst})
    return pairs or None


def _cost_per_ring(usage: dict, department: dict) -> dict[str, float] | None:
    ring_of = {s["role"]: s.get("ring") for s in department.get("seats", [])}
    acc: dict[str, float] = {}
    for row in usage.get("by_seat") or []:
        ring = ring_of.get(row.get("seat"))
        if ring is None:
            continue
        key = str(ring)
        acc[key] = round(acc.get(key, 0.0) + (row.get("cost") or 0), 4)
    return acc or None


def _memory_growth(db: dict) -> dict[str, int] | None:
    rows = db.get("seats") or []
    out = {r["seat"]: (r.get("facts") or 0) + (r.get("episodes") or 0) for r in rows}
    return out or None


def _seats_without_memory(department: dict, db: dict) -> list[str] | None:
    rows = {r["seat"]: r for r in (db.get("seats") or [])}
    out = []
    for seat in department.get("seats", []):
        if not seat.get("built"):
            continue
        row = rows.get(seat["role"], {})
        if (row.get("facts") or 0) + (row.get("episodes") or 0) == 0:
            out.append(seat["role"])
    return out or None


def _idle_seats(department: dict) -> list[str] | None:
    built = {s["role"] for s in department.get("seats", []) if s.get("built")}
    active = {s["role"] for s in department.get("seats", []) if s.get("activity")}
    return sorted(built - active) or None


def _fact_writers(facts: list[dict]) -> list[str] | None:
    return sorted({f.get("seat") for f in facts if f.get("seat")}) or None


def _context_growth(events: list[dict]) -> dict[str, int] | None:
    """Mean prompt tokens per iteration index. A turn whose second iteration
    costs far more than its first is a turn filling its own context."""
    acc: dict[int, list[int]] = {}
    for ev in events:
        if ev.get("type") != "llm":
            continue
        iteration = ev.get("iteration")
        tokens = (ev.get("usage") or {}).get("in")
        if isinstance(iteration, int) and isinstance(tokens, int):
            acc.setdefault(iteration, []).append(tokens)
    if not acc:
        return None
    return {str(k): round(statistics.mean(v)) for k, v in sorted(acc.items())}


# --- the batch report --------------------------------------------------------
#
# The metrics that need a reader cannot run in the 5s poll, so they run when
# asked and land in a file. This is the same pattern as `eval_report.json`: the
# expensive thing writes once, the dashboard reads forever, and the page never
# calls a model.

# Which slots the report is allowed to fill. Listing them means a stray key in
# the file cannot quietly become a measurement.
JUDGE_METRICS = ("average_reward", "mast_reasoning_action_mismatch",
                 "mast_information_withholding")


def _home_env() -> None:
    """Point waku at Irina's home BEFORE anything imports waku.config.

    Every function here that touches waku calls this first. Without it the
    collector reads the default home while `_events()` reads Irina's, and the
    registry mixes two corpora — which is exactly what the first catalogue run
    did, and what made `latency_avg` disagree with `throughput` by a factor of
    twenty. `load_dotenv()` does not override an already-set variable, so a
    `setdefault` here wins over a developer's `.env`.
    """
    import os

    from concentric import ENTRY, MODEL, PROVIDER, SMALL_MODEL, seat_home

    os.environ.setdefault("WAKU_HOME", str(seat_home(ENTRY)))
    os.environ.setdefault("WAKU_PROVIDER", PROVIDER)
    os.environ.setdefault("WAKU_MODEL", MODEL)
    os.environ.setdefault("WAKU_SMALL_MODEL", SMALL_MODEL)


def report_path():
    """Where the batch run writes, beside the eval report it mirrors."""
    _home_env()
    from waku.config import load_settings

    settings = load_settings()
    settings.ensure_home()
    return settings.home / "metrics_report.json"


def load_report() -> dict:
    """The last batch run, or an empty dict. A missing or unreadable report is
    not an error: it means nobody has run one, and every judge slot stays None."""
    path = report_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _ask(prompt: str, max_tokens: int = 700) -> str:
    """One judge call, through the same client the agent uses. No new
    dependency: waku's provider adapter is already the only door to a model."""
    from waku.config import load_settings
    from waku.loop.models import get_client

    settings = load_settings()
    client = get_client(settings)
    response = client.messages.create(
        model=settings.small_model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def _digest(turn: list[dict]) -> str:
    """One turn as a few readable lines. The judge sees what a reader would:
    who was asked, what they called, and what came back."""
    lines = []
    for ev in turn:
        kind = ev.get("type")
        role = ev.get("role") or "entry"
        if kind == "turn_start":
            lines.append(f"ASK: {(ev.get('user_message') or '')[:220]}")
        elif kind == "tool":
            target = (ev.get("args") or {}).get("role") or ev.get("tool")
            lines.append(f"TOOL {role} -> {target}: {(ev.get('output') or '')[:120]}")
        elif kind == "turn_end":
            lines.append(f"REPLY: {(ev.get('reply') or '')[:400]}")
    return "\n".join(lines)


RUBRIC = """You are labelling one turn of a multi-agent system for two known
failure modes, and scoring the reply.

  reasoning_action_mismatch: the reply contradicts or ignores something a tool
    or a delegated agent actually returned.
  information_withholding: an agent held information another agent needed and
    did not pass it on.

Reply with ONLY this JSON, no prose:
{"reasoning_action_mismatch": 0 or 1, "information_withholding": 0 or 1,
 "reward": a number from 0.0 to 1.0 for how well the turn served the ask}

TURN:
"""


def run(limit: int = 20) -> dict:
    """Score the most recent turns and write the report. This is the only
    function here that spends money, and it never runs from the dashboard."""
    ctx = context()
    turns = [t for t in _turns_of(ctx.get("events") or []) if len(t) > 1]
    sample = turns[-limit:]
    hits = {"mast_reasoning_action_mismatch": 0, "mast_information_withholding": 0}
    rewards = []
    errors = []
    for turn in sample:
        try:
            raw = _ask(RUBRIC + _digest(turn))
            start, end = raw.index("{"), raw.rindex("}") + 1
            verdict = json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            errors.append(str(exc)[:120])
            continue
        for key in hits:
            hits[key] += 1 if verdict.get(key) else 0
        if isinstance(verdict.get("reward"), (int, float)):
            rewards.append(float(verdict["reward"]))

    values: dict[str, Any] = dict(hits)
    values["average_reward"] = round(sum(rewards) / len(rewards), 4) if rewards else None

    record = {
        "ran_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scored": len(rewards),
        "of_turns": len(sample),
        "values": values,
        "errors": errors[:5],
    }
    report_path().write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def apply_report(reg: dict[str, dict], report: dict) -> int:
    """Merge a report into the registry. Only ids in JUDGE_METRICS are accepted,
    and only when the value is present — a null in the report leaves the slot
    None rather than writing a zero."""
    values = (report or {}).get("values") or {}
    applied = 0
    for mid in JUDGE_METRICS:
        if mid in reg and isinstance(values.get(mid), (int, float)):
            reg[mid]["value"] = values[mid]
            applied += 1
    return applied


# --- the registry, filled ----------------------------------------------------

def compute(ctx: dict) -> dict[str, dict]:
    """Fill every slot the data on hand can fill. Pure: it reads `ctx` and
    returns a new registry. Anything it cannot fill stays None, with the
    `filler` sentence already saying what would fill it."""
    reg = registry()
    events = ctx.get("events") or []
    stats = ctx.get("stats") or {}
    department = ctx.get("department") or {}
    usage = ctx.get("usage") or {}
    db = ctx.get("db") or {}

    fills: dict[str, Any] = {
        "success_rate": _success_rate(ctx.get("eval_report")),
        "latency_avg": stats.get("latency_avg"),
        "latency_p95": stats.get("latency_p95"),
        "throughput": _throughput(events),
        "tokens_in": stats.get("tokens_in"),
        "tokens_out": stats.get("tokens_out"),
        "cost": stats.get("cost"),
        "tool_errors": stats.get("tool_errors"),
        "gate_retrieval_ratio": _gate_retrieval_ratio(stats),
        "cost_per_ring": _cost_per_ring(usage, department),
        "context_growth": _context_growth(events),
        "step_repetition": _step_repetition(events),
        "unanswered_handoffs": _unanswered_handoffs(events),
        "premature_terminations": _premature_terminations(events),
        "mandate_breaches": _mandate_breaches(events, department),
        "delegation_depth": _delegation_depth(events),
        "delegation_breadth": len({r for _, r, _ in _delegations(events)}) or None,
        "handoff_latency": _handoff_latency(events),
        "consultations": _consultations(events),
        "peer_pairs_used": _peer_pairs(events),
        "memory_growth": _memory_growth(db),
        "fact_writers": _fact_writers(ctx.get("facts") or []),
        "seats_without_memory": _seats_without_memory(department, db),
        "idle_seats": _idle_seats(department),
        "consolidation_backlog": ctx.get("chat_pending"),
    }

    started = time.perf_counter()
    for mid, value in fills.items():
        if mid in reg:
            reg[mid]["value"] = value
    # One timestamp for the whole pass: the individual computations are
    # microseconds, and a per-metric clock would cost more than it reports.
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    for mid in fills:
        reg[mid]["cost_ms"] = elapsed if reg[mid]["value"] is not None else None
    # The batch report last, so a judge number never overwrites a live one and
    # never lands in a slot the report is not allowed to fill.
    apply_report(reg, ctx.get("report") or {})
    return reg


# --- the catalogue -----------------------------------------------------------

def _render(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {v:g}" if isinstance(v, float) else f"{k}: {v}"
                               for k, v in value.items()) + "}"
    if isinstance(value, list):
        head = ", ".join(str(v) for v in value[:4])
        return f"[{head}{', …' if len(value) > 4 else ''}] ({len(value)})"
    return str(value)


def catalogue(reg: dict[str, dict]) -> str:
    """The whole registry, grouped by what can be said about it right now.

    The groups are facts about this run, not intentions: a metric that is wired
    up but has no data to report sits in its own group rather than padding the
    measured count. That distinction is the point of the catalogue."""
    groups = (
        ("MEASURED",
         [s for s in reg.values() if s["value"] is not None]),
        ("WIRED, NO DATA YET",
         [s for s in reg.values() if s["value"] is None and s["state"] == "computed"]),
        ("READY — the data or capability exists, nobody has wired it up",
         [s for s in reg.values() if s["value"] is None and s["state"] == "ready"]),
        ("BLOCKED — needs something this repository does not have",
         [s for s in reg.values() if s["value"] is None and s["state"] == "blocked"]),
        ("PLACEHOLDER — no work yet",
         [s for s in reg.values() if s["value"] is None and s["state"] == "placeholder"]),
    )
    lines = []
    for title, rows in groups:
        if not rows:
            continue
        lines.append(f"\n{title} ({len(rows)})")
        for slot in sorted(rows, key=lambda s: s["id"]):
            lines.append(f"  {slot['id']:<32} {_render(slot['value']):<24} "
                         f"{slot['kind']:<7} {slot['changes']:<9} {slot['unit']}")
            if slot["value"] is None and slot["filler"]:
                lines.append(f"  {'':<32} - {slot['filler']}")
    measured = sum(1 for s in reg.values() if s["value"] is not None)
    wired = sum(1 for s in reg.values() if s["state"] == "computed")
    lines.append(f"\n{measured} of {len(reg)} slots hold a value; "
                 f"{wired} are wired up.")
    return "\n".join(lines)


def context() -> dict:
    """The real payload, from the department's own collector. I/O lives here and
    nowhere else, so `compute()` stays testable without a filesystem.

    The environment has to be set BEFORE waku.config is imported, exactly as the
    launcher does it. Without this the collector reads the default home while
    `_events()` reads Irina's, and the registry mixes two different corpora —
    which is precisely what the first catalogue run did, and what made
    `latency_avg` disagree with `throughput` by a factor of twenty.
    """
    _home_env()
    from concentric.collect import _events, collect_department

    data = collect_department()
    return {
        "events": _events(),
        "stats": data.get("stats") or {},
        "usage": data.get("usage") or {},
        "department": data.get("department") or {},
        "db": data.get("db") or {},
        "facts": data.get("facts") or [],
        "episodes": data.get("episodes") or [],
        "chat_pending": data.get("chat_pending") or 0,
        "eval_report": data.get("eval_report"),
        "report": load_report(),
    }


def main() -> None:
    # The console on Windows defaults to cp1252 and cannot encode the em dash
    # this catalogue prints for an empty slot. The launcher reconfigures its own
    # stdout for the same reason; this module is also run on its own.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass
    if "--run" in sys.argv:
        record = run()
        print(f"scored {record['scored']} of {record['of_turns']} turns; "
              f"wrote {report_path()}")
        for key, value in record["values"].items():
            print(f"  {key:<32} {value}")
        if record["errors"]:
            print(f"  {len(record['errors'])} turn(s) could not be scored")
        return
    print(catalogue(compute(context())))


if __name__ == "__main__":
    main()
