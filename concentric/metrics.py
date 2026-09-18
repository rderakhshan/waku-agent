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

import itertools
import json
import math
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from typing import Any

# How many turns a batch run scores. The limit bounds every pass, so this is also
# what the button's cost estimate is built from. It sits up here because `run()`
# uses it as a default, and a default is evaluated when the function is defined.
BATCH_LIMIT = 20

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
    {"id": "tool_use_accuracy", "label": "Tool-use accuracy", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "higher",
     "source": "eval",
     "filler": "a deterministic run: the suite records which dataset cases passed"},
    {"id": "average_reward", "label": "Average reward", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "score", "direction": "higher",
     "source": "judge", "filler": "a batch run: python -m concentric.metrics --run"},
    {"id": "pass_at_k", "label": "Pass@k", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "probability", "direction": "higher",
     "source": "eval",
     "filler": "an arena race that has run the same case twice; one pass in k is "
               "the point, so a single run cannot answer it"},
    {"id": "hallucination_rate", "label": "Hallucination rate", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "lower",
     "source": "judge",
     "filler": "a batch run: a groundedness judge reads each reply against what "
               "its tools actually returned"},
    {"id": "factual_grounding", "label": "Factual grounding", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "higher",
     "source": "judge",
     "filler": "the same batch run and the same judge, scored the other way"},
    {"id": "context_retention", "label": "Context retention", "state": "ready",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "higher",
     "source": "judge", "filler": "multi-turn scenarios probing a seat's own store"},

    # -- how fast, how much? --------------------------------------------------
    {"id": "latency_avg", "label": "Latency, mean", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "ms", "direction": "lower",
     "source": "trace", "filler": "a turn with an llm call in the trace"},
    {"id": "latency_p95", "label": "Latency, p95", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "ms", "direction": "lower",
     "source": "trace", "filler": "a turn with an llm call in the trace"},
    {"id": "throughput", "label": "Throughput", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "turns/min", "direction": "higher",
     "source": "trace", "filler": "a completed turn in the trace"},
    {"id": "tokens_in", "label": "Tokens in", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "tokens", "direction": "lower",
     "source": "trace", "filler": "an llm call in the trace"},
    {"id": "tokens_out", "label": "Tokens out", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "tokens", "direction": "lower",
     "source": "trace", "filler": "an llm call in the trace"},
    {"id": "cost", "label": "Spend", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "usd", "direction": "lower",
     "source": "trace", "filler": "an llm call whose model has a price"},
    {"id": "tool_errors", "label": "Tool errors", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "calls", "direction": "lower",
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
     "kind": "series", "changes": "per-turn", "unit": "repeats", "direction": "lower",
     "source": "trace", "filler": "a tool call in the trace"},
    {"id": "unanswered_handoffs", "label": "Unanswered hand-offs", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "handoffs", "direction": "lower",
     "source": "trace", "filler": "a delegate call in the trace"},
    {"id": "premature_terminations", "label": "Premature terminations", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "turns", "direction": "lower",
     "source": "trace", "filler": "a turn in the trace"},
    {"id": "mandate_breaches", "label": "Mandate breaches", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "calls", "direction": "lower",
     "source": "trace", "filler": "a seat with a declared tool list"},
    {"id": "mast_reasoning_action_mismatch", "label": "MAST: reasoning-action mismatch",
     "state": "computed", "kind": "scalar", "changes": "per-run", "unit": "traces",
     "direction": "lower", "source": "judge",
     "filler": "a batch run: python -m concentric.metrics --run"},
    {"id": "mast_information_withholding", "label": "MAST: information withholding",
     "state": "computed", "kind": "scalar", "changes": "per-run", "unit": "turns",
     "direction": "lower", "source": "judge",
     "filler": "a batch run — and note it stays a department count: the trace "
               "shows what a seat said, not what it chose not to say, so there is "
               "no honest way to put a name on it"},
    {"id": "mast_annotator_agreement", "label": "Cohen's kappa (labeler agreement)",
     "state": "computed", "kind": "scalar", "changes": "per-run", "unit": "kappa",
     "direction": "higher", "source": "judge",
     "filler": "a batch run: the same traces labelled twice, and kappa between them"},

    # -- how does work move? --------------------------------------------------
    {"id": "delegation_depth", "label": "Delegation depth reached", "state": "computed",
     "kind": "scalar", "changes": "per-turn", "unit": "ring", "direction": "neutral",
     "source": "trace", "filler": "an event carrying a ring"},
    {"id": "delegation_breadth", "label": "Distinct seats tasked", "state": "computed",
     "kind": "scalar", "changes": "rarely", "unit": "seats", "direction": "neutral",
     "source": "trace", "filler": "a delegate or consult call"},
    {"id": "handoff_latency", "label": "Hand-off latency", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "ms", "direction": "lower",
     "source": "trace", "filler": "a delegate call the target answered inside its turn"},
    {"id": "consultations", "label": "Peer consultations", "state": "computed",
     "kind": "series", "changes": "per-turn", "unit": "calls", "direction": "neutral",
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
    {"id": "preference_rate", "label": "Preference rate", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "ratio", "direction": "higher",
     "source": "judge",
     "filler": "an arena race with at least two quality-judged models; a "
               "preference needs a field to prefer against"},
    {"id": "sus", "label": "SUS (dashboard usability)", "state": "ready",
     "kind": "scalar", "changes": "rarely", "unit": "score", "direction": "higher",
     "source": "human", "filler": "the ten-question System Usability Scale, answered by a person"},

    # -- semantic: wired, waiting on an embedding key and a batch run --------
    #
    # The openai client is already a core dependency, so nothing is installed
    # here. What is missing is OPENAI_API_KEY — the same variable the Supabase
    # and LangMem memory backends already use for their embeddings.
    {"id": "stance_convergence", "label": "Final stance convergence", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "cosine", "direction": "higher",
     "source": "judge",
     "filler": "OPENAI_API_KEY, then a batch run: the seats' answers are embedded "
               "and compared pairwise"},
    {"id": "stance_shift", "label": "Total stance shift", "state": "computed",
     "kind": "series", "changes": "per-run", "unit": "cosine", "direction": "neutral",
     "source": "judge",
     "filler": "OPENAI_API_KEY, then a batch run: one seat's first answer against "
               "its last"},
    {"id": "semantic_diversity", "label": "Semantic diversity", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "cosine", "direction": "neutral",
     "source": "judge",
     "filler": "OPENAI_API_KEY, then a batch run: the same cosines as convergence, "
               "read the other way"},
    {"id": "bertscore", "label": "BERTScore", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "score", "direction": "higher",
     "source": "judge",
     "filler": "gold references in references.jsonl, plus an embedding key"},
    {"id": "bleu_rouge_meteor", "label": "BLEU / ROUGE / METEOR", "state": "computed",
     "kind": "scalar", "changes": "per-run", "unit": "score", "direction": "higher",
     "source": "external",
     "filler": "gold references in references.jsonl; BLEU and ROUGE are implemented "
               "and waiting, METEOR needs a synonym table and is not"},

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


# What each metric is a property of. This is the taxonomy's own indexing: a
# formula that carries an agent index (Delta^i, a^i_r) is `agent`, one that
# compares two agents (s^1 . s^2, avg_{i<j}) is `pair`, and one that belongs to
# the harness, the department as a whole, or a labeler is `system`.
#
# It is a separate map rather than a field on each slot because the slot list is
# long and this is the one thing worth reading in one place — the shape of the
# whole registry at a glance.
LEVELS: dict[str, str] = {
    # the taxonomy's Performance and Task Completion
    "success_rate": "agent",
    "tool_use_accuracy": "agent",
    "average_reward": "agent",
    "pass_at_k": "agent",
    # grounding and retention
    "hallucination_rate": "agent",
    "factual_grounding": "agent",
    "context_retention": "agent",
    # System and Human-Centric, indexed by agent
    "latency_avg": "agent",
    "latency_p95": "agent",
    "throughput": "agent",
    "tokens_in": "agent",
    "tokens_out": "agent",
    "cost": "agent",
    "tool_errors": "agent",
    # harness-level
    "gate_retrieval_ratio": "system",
    "cost_per_ring": "system",
    "context_growth": "system",
    # MAST, split by which layer owns the failure
    "step_repetition": "agent",
    "premature_terminations": "agent",
    "mandate_breaches": "agent",
    "unanswered_handoffs": "pair",
    "mast_reasoning_action_mismatch": "pair",
    "mast_information_withholding": "system",
    "mast_annotator_agreement": "system",
    # structure and interaction
    "delegation_depth": "system",
    "delegation_breadth": "system",
    "handoff_latency": "pair",
    "consultations": "pair",
    "peer_pairs_used": "pair",
    # memory
    "memory_growth": "agent",
    "fact_writers": "agent",
    "seats_without_memory": "agent",
    "idle_seats": "agent",
    "consolidation_backlog": "system",
    # psychometric
    "argument_confidence": "agent",
    "cognitive_effort": "agent",
    "cognitive_dissonance": "agent",
    "empathy": "agent",
    # preference
    "preference_rate": "pair",
    "sus": "system",
    # semantic
    "stance_convergence": "pair",
    "stance_shift": "agent",
    "semantic_diversity": "pair",
    "bertscore": "agent",
    "bleu_rouge_meteor": "agent",
    # benchmarks score one agent on a task
    "bench_code": "agent",
    "bench_agentic": "agent",
    "bench_general": "agent",
    "bench_math": "agent",
    "bench_domain": "agent",
    "bench_multimodal": "agent",
    "bench_task_selection": "system",
}


# How a metric behaves when it is summed over a time bucket.
#
#   sum    a count or a total. A week of repeats is the repeats in that week.
#   mean   a ratio, a time or a score. A week of latencies is the mean latency of
#          the turns in it, weighted by how many there were.
#
# Getting this wrong is the quietest way a trend chart lies. Summing latencies
# gives a number with no unit; averaging a week of counts gives one with no
# meaning. There is no universal rule — it depends on the metric — so it is
# declared here, once, and an eval checks that every slot is covered.
AGG: dict[str, str] = {
    # counts and totals
    "tokens_in": "sum",
    "tokens_out": "sum",
    "cost": "sum",
    "cost_per_ring": "sum",
    "tool_errors": "sum",
    "step_repetition": "sum",
    "premature_terminations": "sum",
    "mandate_breaches": "sum",
    "unanswered_handoffs": "sum",
    "consultations": "sum",
    "peer_pairs_used": "sum",
    "mast_reasoning_action_mismatch": "sum",
    "mast_information_withholding": "sum",
    "memory_growth": "sum",
    "fact_writers": "sum",
    "seats_without_memory": "sum",
    "idle_seats": "sum",
    "consolidation_backlog": "sum",
    # ratios, times and scores
    "success_rate": "mean",
    "tool_use_accuracy": "mean",
    "average_reward": "mean",
    "pass_at_k": "mean",
    "hallucination_rate": "mean",
    "factual_grounding": "mean",
    "context_retention": "mean",
    "latency_avg": "mean",
    "latency_p95": "mean",
    "throughput": "mean",
    "gate_retrieval_ratio": "mean",
    "context_growth": "mean",
    "handoff_latency": "mean",
    "delegation_depth": "mean",
    "delegation_breadth": "mean",
    "mast_annotator_agreement": "mean",
    "argument_confidence": "mean",
    "cognitive_effort": "mean",
    "cognitive_dissonance": "mean",
    "empathy": "mean",
    "preference_rate": "mean",
    "sus": "mean",
    "stance_convergence": "mean",
    "stance_shift": "mean",
    "semantic_diversity": "mean",
    "bertscore": "mean",
    "bleu_rouge_meteor": "mean",
    "bench_code": "mean",
    "bench_agentic": "mean",
    "bench_general": "mean",
    "bench_math": "mean",
    "bench_domain": "mean",
    "bench_multimodal": "mean",
    "bench_task_selection": "mean",
}


def registry() -> dict[str, dict]:
    """A fresh copy of the slots, keyed by id."""
    return {slot["id"]: {**slot, "level": LEVELS.get(slot["id"], "system"),
                         "value": None, "cost_ms": None, "as_of": None}
            for slot in SLOTS}


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



def _gate_retrieval_ratio(stats: dict) -> float | None:
    skip, ret = stats.get("gate_skips") or 0, stats.get("gate_retrieves") or 0
    total = skip + ret
    return round(ret / total, 4) if total else None








def _delegation_depth(events: list[dict]) -> int | None:
    rings = [e.get("ring") for e in events if isinstance(e.get("ring"), int)]
    return max(rings) if rings else None



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


# --- the seats' own answers --------------------------------------------------
#
# A delegate call's output IS the child's reply — it is what came back to the
# parent — so the trace already holds every seat's position. The children's own
# turns are not in it, and for these metrics they do not need to be.

def _turn_answers(events: list[dict]) -> list[list[str]]:
    """The seats' answers, one list per turn, for turns where two seats spoke.
    Convergence and diversity are questions about a group, so a turn with one
    answer is not one."""
    out = []
    for turn in _turns_of(events):
        answers = [(ev.get("output") or "").strip() for ev in turn
                   if ev.get("type") == "tool" and ev.get("tool") == "delegate"]
        answers = [a for a in answers if len(a) > 40]
        if len(answers) >= 2:
            out.append(answers)
    return out


def _seat_answers(events: list[dict]) -> dict[str, list[str]]:
    """Each seat's answers in order, across the whole corpus. Stance shift is a
    question about one seat over time, so it needs this shape rather than the
    per-turn one."""
    out: dict[str, list[str]] = {}
    for turn in _turns_of(events):
        for ev in turn:
            if ev.get("type") != "tool" or ev.get("tool") != "delegate":
                continue
            target = (ev.get("args") or {}).get("role")
            text = (ev.get("output") or "").strip()
            if target and len(text) > 40:
                out.setdefault(target, []).append(text)
    return out


def _replies(events: list[dict]) -> dict[str, str]:
    """What the department was asked and what it finally said, per turn — the
    only shape a reference answer can be matched against."""
    out: dict[str, str] = {}
    for turn in _turns_of(events):
        ask = next((e.get("user_message") for e in turn
                    if e.get("type") == "turn_start"), None)
        reply = next((e.get("reply") for e in reversed(turn)
                      if e.get("type") == "turn_end"), None)
        if ask and reply:
            out[ask] = reply
    return out


# --- reference-scored text metrics -------------------------------------------
#
# BLEU and ROUGE are n-gram overlap against a gold answer. They need no package:
# the whole of BLEU-4 is a precision, a brevity penalty and a geometric mean.

def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _ngrams(tokens: list[str], n: int) -> Counter:
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def bleu(hypothesis: str, reference: str, max_n: int = 4) -> float | None:
    """Brevity-penalised n-gram precision, add-one smoothed above unigrams so a
    single sentence still scores."""
    hyp, ref = _tokens(hypothesis), _tokens(reference)
    if not hyp or not ref:
        return None
    log_sum = 0.0
    for n in range(1, max_n + 1):
        hg, rg = _ngrams(hyp, n), _ngrams(ref, n)
        overlap = sum(min(count, rg[gram]) for gram, count in hg.items())
        total = sum(hg.values())
        precision = ((overlap + 1) / (total + 1)) if n > 1 else (overlap / total)
        if precision <= 0:
            return 0.0
        log_sum += math.log(precision) / max_n
    penalty = min(1.0, math.exp(1 - len(ref) / len(hyp))) if len(hyp) < len(ref) else 1.0
    return round(penalty * math.exp(log_sum), 4)


def rouge(hypothesis: str, reference: str, max_n: int = 2) -> float | None:
    """ROUGE-N recall, averaged over unigrams and bigrams."""
    hyp, ref = _tokens(hypothesis), _tokens(reference)
    if not hyp or not ref:
        return None
    scores = []
    for n in range(1, max_n + 1):
        hg, rg = _ngrams(hyp, n), _ngrams(ref, n)
        overlap = sum(min(count, rg[gram]) for gram, count in hg.items())
        total = sum(rg.values())
        scores.append(overlap / total if total else 0.0)
    return round(sum(scores) / len(scores), 4)


def references_path():
    """One JSON object per line: {"input": "...", "reference": "..."}.

    Nothing writes this yet. It is the shape a gold answer set would take, and
    the metric stays None until one exists — for an open-ended risk judgement
    there may never be one right answer, which is why this is a file a person
    authors rather than something the harness can generate.
    """
    _home_env()
    from waku.config import load_settings

    settings = load_settings()
    settings.ensure_home()
    return settings.home / "references.jsonl"


def _bertscores(replies: dict[str, str], gold: dict[str, str]) -> list[float]:
    """BERTScore, reduced to what it is: the cosine similarity between a reply's
    embedding and its reference's."""
    from concentric import embeddings

    if not embeddings.available():
        return []
    asks = [a for a in replies if gold.get(a.strip())]
    if not asks:
        return []
    vectors = embeddings.embed([replies[a] for a in asks]
                               + [gold[a.strip()] for a in asks])
    if not vectors:
        return []
    half = len(asks)
    return [embeddings.cosine(vectors[i], vectors[half + i]) for i in range(half)]


def _reference_values(events: list[dict]) -> dict:
    """BLEU, ROUGE and BERTScore against gold answers, if any have been authored.

    All three need the same missing input, so they are computed together and
    left out together. A metric scored against whatever text happened to be
    nearby would be worse than no metric.
    """
    path = references_path()
    if not path.exists():
        return {}
    try:
        pairs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    except (OSError, json.JSONDecodeError):
        return {}
    gold = {p.get("input", "").strip(): p.get("reference", "") for p in pairs}
    if not gold:
        return {}
    replies = _replies(events)
    bleus, rouges = [], []
    for ask, reply in replies.items():
        ref = gold.get(ask.strip())
        if not ref:
            continue
        b, r = bleu(reply, ref), rouge(reply, ref)
        if b is not None:
            bleus.append(b)
        if r is not None:
            rouges.append(r)
    out = {}
    if bleus and rouges:
        out["bleu_rouge_meteor"] = round(
            (sum(bleus) + sum(rouges)) / (len(bleus) + len(rouges)), 4)
    berts = _bertscores(replies, gold)
    if berts:
        out["bertscore"] = round(sum(berts) / len(berts), 4)
    return out


def _semantic_values(events: list[dict]) -> dict:
    """Convergence, shift and diversity, over the seats' own answers.

    Convergence and diversity are the same pairwise cosines read two ways: how
    much a group agreed, and how much it did not. Shift is one seat's first
    answer against its last, which is the closest this corpus gets to the
    taxonomy's before-and-after — a seat here answers a task, not a debate, so
    its position moves between turns rather than inside one.
    """
    from concentric import embeddings

    if not embeddings.available():
        return {}
    turns = _turn_answers(events)
    seats = _seat_answers(events)
    texts = sorted({t for group in turns for t in group}
                   | {t for group in seats.values() for t in group})
    if len(texts) < 2:
        return {}
    vectors = embeddings.embed(texts)
    if not vectors:
        return {}
    vec = dict(zip(texts, vectors))

    agreement, spread = [], []
    for group in turns:
        pairs = [embeddings.cosine(vec[a], vec[b]) for i, a in enumerate(group)
                 for b in group[i + 1:]]
        if pairs:
            agreement.append(sum(pairs) / len(pairs))
            spread.append(1 - sum(pairs) / len(pairs))

    shifts = {}
    for seat, answers in seats.items():
        first, last = answers[0], answers[-1]
        if len(answers) >= 2 and first in vec and last in vec:
            shifts[seat] = {
                "value": round(1 - embeddings.cosine(vec[first], vec[last]), 4),
                "n": len(answers),
            }

    out = {}
    if agreement:
        out["stance_convergence"] = round(sum(agreement) / len(agreement), 4)
    if spread:
        out["semantic_diversity"] = round(sum(spread) / len(spread), 4)
    if shifts:
        out["stance_shift"] = shifts
    return out


# --- the batch report --------------------------------------------------------
#
# The metrics that need a reader cannot run in the 5s poll, so they run when
# asked and land in a file. This is the same pattern as `eval_report.json`: the
# expensive thing writes once, the dashboard reads forever, and the page never
# calls a model.

# Which slots the report is allowed to fill. Listing them means a stray key in
# the file cannot quietly become a measurement.
JUDGE_METRICS = ("average_reward", "mast_reasoning_action_mismatch",
                 "mast_information_withholding", "mast_annotator_agreement",
                 "hallucination_rate", "factual_grounding",
                 "stance_convergence", "stance_shift", "semantic_diversity",
                 "bertscore", "bleu_rouge_meteor")


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
    dependency: waku's provider adapter is already the only door to a model.

    The model is read BEFORE get_client, which is not the obvious order and is
    deliberate. get_client drops a model id it believes belongs to another
    provider, and its owner map is a dict comprehension over PROVIDERS — so when
    three providers ship a "deepseek" family, the last one wins the name and
    "deepseek" itself is judged to be someone else's. The effect was that
    WAKU_SMALL_MODEL=deepseek-v4-flash was silently replaced by deepseek-v4-pro,
    and the judge ran on the expensive model while the cheap one sat configured
    and unused. Reading it first keeps the choice the reader made.
    """
    from waku.config import load_settings
    from waku.loop.models import get_client

    settings = load_settings()
    model = settings.small_model or settings.model
    client = get_client(settings)
    response = client.messages.create(
        model=model, max_tokens=max_tokens,
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


GROUNDING = """You are checking one turn of an agent for grounding.

The TOOLS block is everything the agent actually saw: what its tools and its
delegated seats returned. The REPLY block is what it told the user.

  grounded: every factual claim in the reply is supported by the tools block.
    A reply that says it could not confirm something is grounded. A reply that
    states a fact the tools never returned is not.

Reply with ONLY this JSON, no prose:
{"grounded": 0 or 1}

"""



AGREEMENT_A = """Label this turn for one failure mode.
reasoning_action_mismatch: the reply contradicts or ignores what a tool returned.
Reply with ONLY {"reasoning_action_mismatch": 0 or 1}.

TURN:
"""
AGREEMENT_B = """A colleague labelled this turn. Give your own independent
judgement, from the evidence only.
Does the reply contradict or ignore anything a tool returned?
Reply with ONLY {"reasoning_action_mismatch": 0 or 1}.

TURN:
"""


def kappa(a: list[int], b: list[int]) -> float | None:
    """Cohen's kappa between two labelers.

    Plain agreement is not enough: two labelers who both say "no failure" every
    time agree perfectly and have measured nothing. Kappa subtracts the
    agreement that chance alone would produce, which is why the taxonomy names
    it rather than a percentage.
    """
    n = len(a)
    if n == 0 or n != len(b):
        return None
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected >= 1:
        return None          # both labelers constant and identical: undefined
    return round((observed - expected) / (1 - expected), 4)


def _agreement_values(events: list[dict], sample: list[list[dict]], tick=None) -> dict:
    """How much two labelings of the same traces agree.

    The two prompts differ in framing, not in question, so what kappa measures
    here is the labeler's own stability — a low value means the failure mode is
    being guessed at rather than read.
    """
    first, second = [], []
    for turn in sample:
        digest = _digest(turn)
        va = _judge_json(AGREEMENT_A + digest)
        vb = _judge_json(AGREEMENT_B + digest)
        if tick:
            tick()
            tick()
        if va is None or vb is None:
            continue
        if "reasoning_action_mismatch" not in va or "reasoning_action_mismatch" not in vb:
            continue
        first.append(1 if va["reasoning_action_mismatch"] else 0)
        second.append(1 if vb["reasoning_action_mismatch"] else 0)
    value = kappa(first, second)
    return {"mast_annotator_agreement": value} if value is not None else {}


def _judge_json(prompt: str, max_tokens: int = 400) -> dict | None:
    """One judge call, parsed. None on any failure — a metric that cannot be
    computed is None, and a bad judge reply must not take the run down."""
    try:
        raw = _ask(prompt, max_tokens=max_tokens)
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError, OSError):
        return None




WITHHOLDING = """You are reading one turn of a multi-agent system.

  information_withholding: an agent held information another agent needed and
    did not pass it on.

Reply with ONLY {"information_withholding": 0 or 1}.

TURN:
"""


def _withholding(turns: list[list[dict]], tick=None) -> int | None:
    """A count of turns where an agent held something back.

    Stays department-level, and its `level` says so. The trace shows what each
    seat said but not what it knew and chose not to say, so there is no honest
    way to put a name on it — and inventing one would be worse than the gap.
    """
    hits = scored = 0
    for turn in turns:
        digest = _digest(turn)
        if not digest:
            continue
        verdict = _judge_json(WITHHOLDING + digest)
        if tick:
            tick()
        if verdict is None:
            continue
        scored += 1
        if verdict.get("information_withholding"):
            hits += 1
    return hits if scored else None


def run(limit: int = BATCH_LIMIT, on_progress=None) -> dict:
    """Score the most recent `limit` turns and write the report.

    The limit bounds every pass. This is the only function here that spends
    money, and it never runs on its own — the launcher's button is the only
    caller, and `estimate_calls` tells the reader what it will cost before
    anybody presses it.

    Everything it produces is keyed by the seat or the pair it is about. The
    turn-level versions asked "was the department's reply good", which is a
    question about nobody in particular.
    """
    ctx = context()
    events = ctx.get("events") or []
    turns = [t for t in _turns_of(events) if len(t) > 1]
    sample = turns[-limit:]
    total = estimate_calls(events, limit)
    done = 0

    def tick():
        nonlocal done
        done += 1
        if on_progress:
            on_progress(done, total)

    values: dict[str, Any] = {}
    scored_answers = 0

    scored = _scored_answers(sample, tick)
    if scored["average_reward"]:
        values["average_reward"] = scored["average_reward"]
        scored_answers = sum(cell["n"] for cell in scored["average_reward"].values())
    if scored["mast_reasoning_action_mismatch"]:
        values["mast_reasoning_action_mismatch"] = scored["mast_reasoning_action_mismatch"]
    values.update(_grounding_by_seat(sample, tick))

    withholding = _withholding(sample, tick)
    if withholding is not None:
        values["mast_information_withholding"] = withholding

    values.update(_agreement_values(events, sample, tick))
    values.update(_semantic_values(events))
    values.update(_reference_values(events))

    record = {
        "ran_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scored": scored_answers,
        "of_turns": len(sample),
        "values": values,
        "errors": [],
    }
    report_path().write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def apply_report(reg: dict[str, dict], report: dict) -> int:
    """Merge a report into the registry. Only ids in JUDGE_METRICS are accepted,
    and only when the value is present — a null in the report leaves the slot
    None rather than writing a zero.

    A judge number also carries the moment it was produced. Without it a reading
    from three hours ago and a counter computed on this poll look identical, and
    they are not the same kind of fact.
    """
    values = (report or {}).get("values") or {}
    ran_at = (report or {}).get("ran_at")
    applied = 0
    for mid in JUDGE_METRICS:
        if mid in reg and isinstance(values.get(mid), (int, float)):
            reg[mid]["value"] = values[mid]
            reg[mid]["as_of"] = ran_at
            applied += 1
    return applied


def _by_seat(events: list[dict], fn, unit=None) -> dict | None:
    """Run `fn` once per seat instead of once for the department.

    This is the whole per-agent mechanism. Every metric helper already takes a
    list of events; grouping first turns it into 24 answers instead of one, and
    a department mean is where the answer to "which seat?" goes to die.

    `unit` counts the sample the number is drawn from — the llm calls behind a
    latency, the tool calls behind a repeat. It travels with the value because a
    mean over two turns and a mean over forty are not the same claim, and a page
    that shows them side by side without saying so invites a wrong conclusion.
    """
    groups: dict[str, list[dict]] = {}
    for ev in events:
        role = ev.get("role")
        if role:
            groups.setdefault(role, []).append(ev)
    out: dict[str, dict] = {}
    for seat, group in groups.items():
        value = fn(group)
        if value is None:
            continue
        out[seat] = {"value": value,
                     "n": sum(1 for e in group if unit(e)) if unit else len(group)}
    return out or None


def _by_pair(events: list[dict], fn) -> dict | None:
    """Run `fn(events, caller, target)` once per interacting pair.

    Pairs are siblings of seats, not children: a hand-off's latency cannot be
    recovered from either seat's own mean, so this reads the same event list
    rather than the per-seat results.
    """
    out: dict[str, Any] = {}
    for src, dst, _ in _delegations(events):
        if not src or not dst or src == dst:
            continue
        key = f"{src}>{dst}"
        if key not in out:
            value = fn(events, src, dst)
            if value is not None:
                out[key] = value
    return out or None


def _seat_turns(events: list[dict]) -> dict[str, list[list[dict]]]:
    """{seat: [its events, one list per turn it took part in]}.

    A seat does not own a turn — only the entry seat opens and closes one — so
    the seat's own work has to be lifted out of the turn it sits inside. Several
    of the per-agent metrics are only meaningful within a turn: two events a day
    apart are not a latency.
    """
    out: dict[str, list[list[dict]]] = {}
    for turn in _turns_of(events):
        by_seat: dict[str, list[dict]] = {}
        for ev in turn:
            role = ev.get("role")
            if role:
                by_seat.setdefault(role, []).append(ev)
        for seat, group in by_seat.items():
            out.setdefault(seat, []).append(group)
    return out


def _sum_by_seat(events: list[dict], predicate, measure, unit=None) -> dict | None:
    """Sum `measure(event)` over a seat's events that satisfy `predicate`."""
    out = {}
    for seat, turns in _seat_turns(events).items():
        total = 0
        n = 0
        for group in turns:
            for ev in group:
                if predicate(ev):
                    total += measure(ev)
                    n += 1
        if n:
            out[seat] = {"value": round(total, 4), "n": n}
    return out or None


def _latency_by_seat(events: list[dict], pct: float | None = None) -> dict | None:
    """Per seat: the gap between its own consecutive events inside a turn — how
    long it spends between acting.

    Deliberately not the department's latency_avg. That one is turn_start to the
    last llm call, and no single seat owns a turn. This measures the seat, and
    the two are not comparable — which is why they are two different rows.
    """
    out = {}
    for seat, turns in _seat_turns(events).items():
        gaps = []
        for group in turns:
            stamps = [t for t in (_parse(e.get("ts")) for e in group) if t]
            gaps += [(b - a).total_seconds() * 1000
                     for a, b in itertools.pairwise(stamps)]
        if not gaps:
            continue
        gaps.sort()
        value = (gaps[min(len(gaps) - 1, int(len(gaps) * pct))] if pct
                 else statistics.mean(gaps))
        out[seat] = {"value": round(value), "n": len(gaps)}
    return out or None


def _throughput_by_seat(events: list[dict]) -> dict | None:
    """Per seat: turns it took part in, per minute of its own active time."""
    out = {}
    for seat, turns in _seat_turns(events).items():
        active = 0.0
        for group in turns:
            stamps = [t for t in (_parse(e.get("ts")) for e in group) if t]
            if len(stamps) >= 2:
                active += (max(stamps) - min(stamps)).total_seconds()
        if active <= 0:
            continue
        out[seat] = {"value": round(len(turns) / (active / 60), 4), "n": len(turns)}
    return out or None


def _repeats_by_seat(events: list[dict]) -> dict | None:
    """The same tool with the same args twice inside one turn, per seat."""
    out = {}
    for seat, turns in _seat_turns(events).items():
        repeats = 0
        calls = 0
        for group in turns:
            seen = set()
            for ev in group:
                if ev.get("type") != "tool":
                    continue
                calls += 1
                key = (ev.get("tool"),
                       json.dumps(ev.get("args") or {}, sort_keys=True, default=str))
                if key in seen:
                    repeats += 1
                seen.add(key)
        if calls:
            out[seat] = {"value": repeats, "n": calls}
    return out or None


def _breaches_by_seat(events: list[dict], department: dict) -> dict | None:
    """Tool calls a seat made that its role does not hold."""
    allowed = {s["role"]: set(s.get("tools") or [])
               for s in department.get("seats", [])}
    out = {}
    for seat, turns in _seat_turns(events).items():
        if seat not in allowed:
            continue
        calls = breaches = 0
        for group in turns:
            for ev in group:
                if ev.get("type") != "tool" or not ev.get("tool"):
                    continue
                calls += 1
                if ev["tool"] not in allowed[seat]:
                    breaches += 1
        if calls:
            out[seat] = {"value": breaches, "n": calls}
    return out or None


def _early_stops_by_seat(events: list[dict]) -> dict | None:
    """Turns that ended with nothing to say, attributed to the last seat to act.

    This is an INFERENCE and the filler says so. turn_end carries no role —
    only the entry seat owns a turn — so the seat cannot be read off the trace.
    Blaming the last seat to act is a guess, and a guess labelled as one is
    still worth more than a department count that blames nobody.
    """
    out: dict[str, dict] = {}
    for turn in _turns_of(events):
        ends = [e for e in turn if e.get("type") == "turn_end"]
        if ends and (ends[-1].get("reply") or "").strip():
            continue
        acted = [e.get("role") for e in turn if e.get("role")]
        if not acted:
            continue
        seat = acted[-1]
        cell = out.setdefault(seat, {"value": 0, "n": 0})
        cell["value"] += 1
        cell["n"] += 1
    return out or None


def _cost_by_seat(usage: dict) -> dict | None:
    """Spend per seat — already per-seat in the payload, so this only reshapes."""
    rows = usage.get("by_seat") or []
    out = {r["seat"]: {"value": round(r.get("cost") or 0, 4), "n": r.get("calls") or 0}
           for r in rows if r.get("seat")}
    return out or None


def _tool_errors_by_seat(events: list[dict]) -> dict | None:
    """Tool results that came back as errors, per seat. The classifier is waku's
    own `_tool_status`, so the per-seat number and the department number cannot
    disagree about what an error is."""
    from waku.ops.dashboard import _tool_status

    out = {}
    for seat, turns in _seat_turns(events).items():
        calls = errors = 0
        for group in turns:
            for ev in group:
                if ev.get("type") != "tool":
                    continue
                calls += 1
                if _tool_status(ev.get("output") or "") == "error":
                    errors += 1
        if calls:
            out[seat] = {"value": errors, "n": calls}
    return out or None


def _is_llm(ev: dict) -> bool:
    return ev.get("type") == "llm"


def _handoff_for(events: list[dict], src: str, dst: str) -> dict | None:
    """Milliseconds from a caller's delegate to that target's first answer,
    inside the turn it happened in — the same rule as the department median, and
    scoped to the turn for the same reason: across turns the gap is the idle time
    between sessions, which is not a hand-off at all."""
    gaps = []
    for turn in _turns_of(events):
        stamps = _by_role(turn)
        for caller, target, when in _delegations(turn):
            if caller != src or target != dst:
                continue
            nxt = next((t for t in stamps.get(dst, ()) if t > when), None)
            if nxt:
                gaps.append((nxt - when).total_seconds() * 1000)
    if not gaps:
        return None
    return {"value": round(statistics.median(gaps)), "n": len(gaps)}


def _consultations_for(events: list[dict], src: str, dst: str) -> dict | None:
    """How often one seat asked another at its own round table."""
    count = sum(1 for ev in events
                if ev.get("type") == "tool" and ev.get("tool") == "consult_peer"
                and ev.get("role") == src
                and (ev.get("args") or {}).get("role") == dst)
    return {"value": count, "n": count} if count else None


def _unanswered_for(events: list[dict], src: str, dst: str) -> dict | None:
    """Delegates this pair made where the target never emitted anything after.
    The most expensive silent failure in the graph, and it belongs to the pair —
    not to the caller, who did hand the work over, and not to the target, which
    may never have received it."""
    stamps = _by_role(events)
    total = unanswered = 0
    for caller, target, when in _delegations(events):
        if caller != src or target != dst:
            continue
        total += 1
        if not any(t > when for t in stamps.get(dst, ())):
            unanswered += 1
    if not total:
        return None
    return {"value": unanswered, "n": total}


def _peer_pairs(events: list[dict]) -> dict | None:
    """Who consults and delegates to whom, and how often — a weighted mesh
    instead of a flat list of names."""
    counts: dict[str, int] = {}
    for src, dst, _ in _delegations(events):
        if src and dst and src != dst:
            key = f"{src}>{dst}"
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    return {key: {"value": n, "n": n} for key, n in sorted(counts.items())}


# --- the eval and arena inputs -----------------------------------------------
#
# Two metrics need a file rather than a trace, because their numerator is
# produced by something that runs on purpose: the deterministic suite, and the
# arena. Both files are read here and turned into numbers by pure functions, so
# `compute()` still never touches a disk.

# pass@k's k. Two is the smallest repeat that can distinguish "it worked" from
# "it worked once" — the taxonomy's whole point in asking for k at all.
PASS_K = 2


def _answers(turns: list[list[dict]]) -> dict[str, list[dict]]:
    """{seat: [{task, answer, tools, caller}]} — each seat's answers.

    A delegate call carries the task it was given and returns the target's reply
    as its output, so the trace already holds what a judge needs to score one
    SEAT rather than one turn. The seat's own tool calls sit beside it in the
    same turn, which is what grounding gets checked against.

    This is what makes the judged metrics per-agent: the turn-level versions
    asked "was the department's reply good", which is a question about nobody.
    """
    out: dict[str, list[dict]] = {}
    for turn in turns:
        by_seat: dict[str, list[dict]] = {}
        for ev in turn:
            role = ev.get("role")
            if role:
                by_seat.setdefault(role, []).append(ev)
        for ev in turn:
            if ev.get("type") != "tool" or ev.get("tool") != "delegate":
                continue
            args = ev.get("args") or {}
            target, task = args.get("role"), (args.get("task") or "").strip()
            answer = (ev.get("output") or "").strip()
            if not target or not task or len(answer) < 40:
                continue
            tools = [(e.get("output") or "").strip()
                     for e in by_seat.get(target, [])
                     if e.get("type") == "tool" and e.get("output")]
            out.setdefault(target, []).append({
                "task": task, "answer": answer, "tools": tools,
                "caller": ev.get("role"),
            })
    return out


REWARD_ANSWER = """Read one agent's answer and the reply its caller finally gave.

  reward: how well the agent answered the task. 1.0 is complete, correct and
    useful; 0.0 is useless.
  reasoning_action_mismatch: the caller's reply contradicts or ignores the
    answer it was handed.

Reply with ONLY {{"reward": a number from 0.0 to 1.0,
                  "reasoning_action_mismatch": 0 or 1}}.

TASK: {task}
ANSWER: {answer}

THE CALLER'S REPLY:
{reply}
"""


def _scored_answers(turns: list[list[dict]], tick=None) -> dict:
    """One call per answer, returning the reward and the mismatch together.

    They are two questions about the same answer, so asking them separately cost
    two hundred and sixty calls where one hundred and thirty will do. Reward is a
    property of the seat; the mismatch is a property of the pair — the caller
    owns the reply, the target owns the answer, and the failure is in neither
    alone.
    """
    reward_by_seat: dict[str, dict] = {}
    mismatch_by_pair: dict[str, dict] = {}
    for turn in turns:
        reply = next((e.get("reply") for e in reversed(turn)
                      if e.get("type") == "turn_end"), "") or ""
        for ev in turn:
            if ev.get("type") != "tool" or ev.get("tool") != "delegate":
                continue
            caller = ev.get("role")
            args = ev.get("args") or {}
            target, task = args.get("role"), (args.get("task") or "").strip()
            answer = (ev.get("output") or "").strip()
            if not caller or not target or not task or len(answer) < 40:
                continue
            verdict = _judge_json(REWARD_ANSWER.format(
                task=task[:600], answer=answer[:1500], reply=reply[:1500]))
            if tick:
                tick()
            if verdict is None:
                continue
            score = verdict.get("reward")
            if isinstance(score, (int, float)):
                cell = reward_by_seat.setdefault(target, {"total": 0.0, "n": 0})
                cell["total"] += float(score)
                cell["n"] += 1
            if reply:
                pair = mismatch_by_pair.setdefault(
                    f"{caller}>{target}", {"value": 0, "n": 0})
                pair["n"] += 1
                if verdict.get("reasoning_action_mismatch"):
                    pair["value"] += 1
    return {
        "average_reward": ({seat: {"value": round(c["total"] / c["n"], 4), "n": c["n"]}
                            for seat, c in reward_by_seat.items()} or None),
        "mast_reasoning_action_mismatch": mismatch_by_pair or None,
    }


def _grounding_by_seat(turns: list[list[dict]], tick=None) -> dict:
    """Grounding and hallucination, per seat.

    One judgement per answer, checked against the tools THAT SEAT called. A
    department ratio cannot say which seat made something up, and a claim is made
    by one seat, not by a department.
    """
    grounded_by_seat = {}
    for seat, answers in _answers(turns).items():
        scored = grounded = 0
        for a in answers:
            if not a["tools"]:
                continue
            verdict = _judge_json(GROUNDING + "TOOLS:\n" + "\n".join(a["tools"])[:4000]
                                  + "\n\nREPLY:\n" + a["answer"][:2000])
            if tick:
                tick()
            if verdict is None or "grounded" not in verdict:
                continue
            scored += 1
            grounded += 1 if verdict.get("grounded") else 0
        if scored:
            grounded_by_seat[seat] = {"value": round(grounded / scored, 4), "n": scored}
    if not grounded_by_seat:
        return {}
    return {
        "factual_grounding": grounded_by_seat,
        "hallucination_rate": {
            seat: {"value": round(1 - cell["value"], 4), "n": cell["n"]}
            for seat, cell in grounded_by_seat.items()},
    }





def estimate_calls(events: list[dict], limit: int = BATCH_LIMIT) -> int:
    """How many model calls a run of this size will make.

    The button says this before anyone presses it. Spending money is a decision,
    and a decision needs a number — the alternative is finding out from the bill.
    """
    turns = [t for t in _turns_of(events) if len(t) > 1][-limit:]
    answers = _answers(turns)
    per_answer = sum(len(v) for v in answers.values())
    with_tools = sum(1 for v in answers.values() for a in v if a["tools"])
    # reward and mismatch share one call per answer, grounding one more for the
    # answers that used a tool, one withholding per turn, two labels per turn
    return per_answer + with_tools + len(turns) + 2 * len(turns)


def tool_report_path(ensure: bool = True):
    """Where the deterministic suite records which dataset cases passed.

    A separate file from eval_report.json, which is written by release_gate.py
    inside waku/ and cannot be extended from here.

    `ensure=False` is for the writer, which must not create a home just by
    running the test suite: a checkout that has never been used should stay
    untouched, and CI is a checkout that has never been used.
    """
    _home_env()
    from waku.config import load_settings

    settings = load_settings()
    if ensure:
        settings.ensure_home()
    return settings.home / "tool_report.json"


def _read_json(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _report_from(name: str) -> dict:
    """A report, from Irina's home or from the default one.

    The gate and the test hook resolve their own home from WAKU_HOME. The
    launcher sets that in-process, but a plain `make gate` in a terminal does
    not, so a report written by hand lands in `.waku/` while this module reads
    Irina's. Both are looked at rather than making the reader remember to export
    a variable before running a command.
    """
    from pathlib import Path

    for folder in (tool_report_path(ensure=False).parent, Path(".waku")):
        path = folder / name
        if path.exists():
            return _read_json(path)
    return {}


def _tool_accuracy(report: dict) -> float | None:
    """The share of dataset cases where the expected tool fired with the
    expected arguments. The suite already asserts this per case; the file is
    only the outcome written down."""
    total = report.get("total") or 0
    return round((report.get("passed") or 0) / total, 4) if total else None


def _preference_rate(runs: list[dict], spec: str) -> float | None:
    """Over races that were quality-judged, how often the department's own model
    scored highest.

    A preference needs a field to prefer against, so a race where fewer than two
    models returned a score is not one — and with no arena runs at all there is
    no preference to measure, which is None rather than zero.
    """
    judged = wins = 0
    for race in runs:
        scores = [(r.get("spec"), (r.get("quality") or {}).get("score"))
                  for r in race.get("results", [])]
        scores = [(s, q) for s, q in scores if q is not None]
        if len(scores) < 2:
            continue
        judged += 1
        best = max(q for _, q in scores)
        if spec in {s for s, q in scores if q == best}:
            wins += 1
    return round(wins / judged, 4) if judged else None


def _pass_at_k(runs: list[dict], k: int = PASS_K) -> float | None:
    """Over cases run at least k times, the share where at least one run passed.

    This is a different number from a pass rate, and deliberately so: a case that
    fails nine times and passes once still counts here, because the question is
    whether the capability is reachable at all.
    """
    by_case: dict[str, list[bool]] = {}
    for race in runs:
        for r in race.get("results", []):
            completion = r.get("completion") or {}
            case = completion.get("case")
            if case is None:
                continue
            by_case.setdefault(str(case), []).append(bool(completion.get("passed")))
    repeated = [outcomes for outcomes in by_case.values() if len(outcomes) >= k]
    if not repeated:
        return None
    return round(sum(1 for o in repeated if any(o)) / len(repeated), 4)


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
        "tool_use_accuracy": _tool_accuracy(ctx.get("tool_report") or {}),
        "preference_rate": _preference_rate(ctx.get("arena_runs") or [],
                                            ctx.get("arena_spec") or ""),
        "pass_at_k": _pass_at_k(ctx.get("arena_runs") or []),
        "latency_avg": _latency_by_seat(events),
        "latency_p95": _latency_by_seat(events, pct=0.95),
        "throughput": _throughput_by_seat(events),
        "tokens_in": _sum_by_seat(events, _is_llm,
                                  lambda e: (e.get("usage") or {}).get("in", 0)),
        "tokens_out": _sum_by_seat(events, _is_llm,
                                   lambda e: (e.get("usage") or {}).get("out", 0)),
        "cost": _cost_by_seat(usage),
        "tool_errors": _tool_errors_by_seat(events),
        "gate_retrieval_ratio": _gate_retrieval_ratio(stats),
        "cost_per_ring": _cost_per_ring(usage, department),
        "context_growth": _context_growth(events),
        "step_repetition": _repeats_by_seat(events),
        "unanswered_handoffs": _by_pair(events, _unanswered_for),
        "premature_terminations": _early_stops_by_seat(events),
        "mandate_breaches": _breaches_by_seat(events, department),
        "delegation_depth": _delegation_depth(events),
        "delegation_breadth": len({r for _, r, _ in _delegations(events)}) or None,
        "handoff_latency": _by_pair(events, _handoff_for),
        "consultations": _by_pair(events, _consultations_for),
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

    # The two inputs that come from a file rather than a trace: the suite's
    # per-case outcomes, and the arena's races.
    from waku.config import load_settings
    from waku.ops.compare_history import load_runs

    settings = load_settings()
    return {
        "events": _events(),
        "stats": data.get("stats") or {},
        "usage": data.get("usage") or {},
        "department": data.get("department") or {},
        "db": data.get("db") or {},
        "facts": data.get("facts") or [],
        "episodes": data.get("episodes") or [],
        "chat_pending": data.get("chat_pending") or 0,
        "eval_report": data.get("eval_report") or _report_from("eval_report.json"),
        "report": load_report(),
        "tool_report": _report_from("tool_report.json"),
        "arena_runs": load_runs(settings.home),
        "arena_spec": f"{settings.provider}:{settings.model}",
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
