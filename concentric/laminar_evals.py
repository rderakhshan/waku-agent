"""Run the department over a task set and score each trajectory.

Laminar's evals are dataset -> executor -> evaluators. Here the executor is the
real department, so each datapoint is a real run with its own trace and its own
scores. `group_name` is what makes runs comparable: the dashboard only puts runs
side by side when they share one.

There are two kinds of score here, and they are not the same kind of thing:

  * **The graph rules** — in scope, depth respected, hand-offs answered, no
    repeated step. Exact, free, and computed from the roster and the run's own
    events. This is the half a judge cannot do, because a judge does not know
    the org chart.
  * **Irina's judge numbers**, reported rather than recomputed. The registry is
    the calculator; this is a delivery slot, and it exists only because Laminar's
    Evals tab shows nothing that did not come out of an evaluator.

    python -m concentric.laminar_evals                  # every datapoint
    python -m concentric.laminar_evals --limit 1        # one, as a smoke test
    python -m concentric.laminar_evals --from-failures  # the runs that broke a rule

Every datapoint is one real department turn. This is not free.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from concentric import graph_rules

GROUP = "irina-department"

# A task, and the seat the answer depends on. Kept tiny on purpose: this is a
# check that the loop is wired, not a benchmark of the department.
DATASET: list[dict[str, Any]] = [
    {
        "data": {
            "task": "Delegate to the audit team, then repeat their answer: "
                    "name one control they test.",
            "entry": "irina",
        },
        "target": {"expect_seat": "cfo-4-audit"},
    },
    {
        "data": {
            "task": "Ask the development team for one risk they own, then repeat it.",
            "entry": "irina",
        },
        "target": {"expect_seat": "cfo-1-development"},
    },
    {
        "data": {"task": "Say hello in one line.", "entry": "irina"},
        "target": {"expect_seat": None},
    },
]


def run_department(datapoint: dict[str, Any]) -> dict[str, Any]:
    """The executor: one real turn, with every tool call it made kept.

    The events are the interesting part and they are not in the reply, so the
    observer captures them — this is the same stream the CLI prints.
    """
    from concentric.run import build_department

    events: list[dict] = []

    def observer(kind: str, event: dict) -> None:
        if kind == "tool":
            events.append({"tool": event.get("tool"),
                           "args": event.get("args") or {},
                           "output": event.get("output"),
                           "role": event.get("role")})

    reply = build_department().run(
        datapoint["task"], entry=datapoint.get("entry", "irina"),
        observer=observer)
    return {"reply": reply, "events": events}


# --- the graph rules, as scores ---------------------------------------------

def _rule(check):
    """1.0 when the rule held, 0.0 when the run broke it."""
    def score(output: dict, target: Any) -> float:
        return 0.0 if check(output.get("events") or []) else 1.0
    return score


def delegated(output: dict, target: Any) -> float:
    return 1.0 if graph_rules.handoffs(output.get("events") or []) else 0.0


def reached_expected(output: dict, target: Any) -> float:
    """Did it reach the seat the task actually needed?"""
    expect = (target or {}).get("expect_seat")
    if not expect:
        return 1.0  # nothing was required, so nothing was missed
    reached = [(e.get("args") or {}).get("role")
               for e in graph_rules.handoffs(output.get("events") or [])]
    return 1.0 if expect in reached else 0.0


def reply_non_empty(output: dict, target: Any) -> float:
    return 1.0 if (output.get("reply") or "").strip() else 0.0


# Every rule the graph checks, and the name its score is reported under. A score
# of 1 means the rule held, so the names say what went right rather than what
# went wrong — "in_scope", not "out_of_scope". The mapping is explicit because
# the coverage test compares it to `graph_rules.violations` by name: a rule added
# there and not scored here has to fail, not go quiet.
RULE_CHECKS = {
    "out_of_scope": graph_rules.out_of_scope,
    "over_depth": graph_rules.over_depth,
    "unanswered": graph_rules.unanswered,
    "repeated": graph_rules.repeated,
}
RULE_NAMES = {
    "out_of_scope": "in_scope",
    "over_depth": "depth_respected",
    "unanswered": "handoffs_answered",
    "repeated": "no_repeated_step",
}

RULES = {RULE_NAMES[rule]: _rule(check) for rule, check in RULE_CHECKS.items()}
RULES.update({
    "delegated": delegated,
    "reached_expected": reached_expected,
    "reply_non_empty": reply_non_empty,
})


# --- Irina's own numbers, delivered -----------------------------------------

def judge_ids(registry: dict) -> list[str]:
    """The slots this eval reports as scores: the judge-dependent ones.

    Kept separate from the snapshot so a test can assert the coverage without a
    corpus — a pass-through that silently selects nothing is worse than none.
    """
    return sorted(slot["id"] for slot in registry.values()
                  if slot.get("source") == "judge")


def judge_snapshot() -> dict[str, float]:
    """The judge-dependent metrics Irina has already computed, once per run.

    The registry computes over the corpus, so every datapoint in one eval gets
    the same snapshot — recomputing it per datapoint would be the same answer
    twenty times. Empty when no batch has ever run, which is why the evaluator
    is only added when there is something to report.
    """
    from concentric import metrics

    try:
        registry = metrics.compute(metrics.context())
    except Exception:
        return {}
    wanted = set(judge_ids(registry))
    out: dict[str, float] = {}
    for slot in registry.values():
        if slot["id"] not in wanted:
            continue
        value = slot.get("value")
        if isinstance(value, (int, float)):
            out[slot["id"]] = float(value)
    return out


# --- the runs worth re-running ----------------------------------------------

def failure_datapoints(limit: int | None = None) -> list[dict[str, Any]]:
    """The recorded runs that broke a rule, as datapoints to run again.

    A fix is only proven by the run that used to fail, so the case is the ask
    and the answer it produced then. Runs recorded before the ask was kept are
    skipped: there is nothing to re-run.
    """
    from concentric import history

    out: list[dict[str, Any]] = []
    for row in history.failures(limit=limit or 50):
        task = (row.get("task") or "").strip()
        if not task:
            continue
        out.append({
            "data": {"task": task, "entry": row.get("entry") or "irina"},
            "target": {"broke": row.get("violations") or ""},
        })
    return out


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    limit: int | None = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    from_failures = "--from-failures" in args

    key = (os.environ.get("LMNR_PROJECT_API_KEY") or "").strip()
    if not key:
        print("Set LMNR_PROJECT_API_KEY (see docs/laminar.md) before running evals.")
        return 2

    if from_failures:
        data = failure_datapoints(limit)
        if not data:
            print("No failing runs recorded — nothing to re-run.")
            return 0
    else:
        data = DATASET if limit is None else DATASET[:limit]

    evaluators = dict(RULES)
    snapshot = judge_snapshot()
    if snapshot:
        evaluators["irina_metrics"] = lambda output, target: snapshot

    from lmnr import evaluate

    from concentric import MODEL, PROVIDER

    result = evaluate(
        data=data,
        executor=run_department,
        evaluators=evaluators,
        # The model is in the name, not the group: two models must land in the
        # same group or the dashboard will not compare them.
        name=f"department-{PROVIDER}-{MODEL}",
        group_name=GROUP,
        project_api_key=key,
        base_url=os.environ.get("LMNR_BASE_URL", "http://localhost"),
        http_port=int(os.environ.get("LMNR_HTTP_PORT", "8000")),
        grpc_port=int(os.environ.get("LMNR_GRPC_PORT", "8001")),
    )
    if result is None:
        print("evaluate() returned no result.")
        return 1

    print("Average scores:")
    for name, score in result["average_scores"].items():
        print(f"  {name}: {score}")
    print(f"Results: {result['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
