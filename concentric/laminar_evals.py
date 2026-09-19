"""Run the department over a small task set and score each trajectory.

Laminar's evals are dataset -> executor -> evaluators. Here the executor is the
real department, so each datapoint is a real trajectory with its own trace and
its own scores attached to it. `group_name` is what makes runs comparable: the
dashboard only puts runs side by side when they share one, so every run of this
module lands in the same group and the averages become a time series.

The structural metrics stay in concentric/metrics.py, where they are computed
over the whole corpus for free. These evaluators are the other half: they only
exist per trajectory, and they need the run itself, not a database of them.

    python -m concentric.laminar_evals              # every datapoint
    python -m concentric.laminar_evals --limit 1    # one, for a smoke test

Every datapoint is one real department turn. This is not free.
"""

from __future__ import annotations

import os
import sys
from typing import Any

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
    """The executor: one real turn, with the edges it used recorded.

    The handoffs are the interesting part and they are not in the reply, so the
    observer captures them — this is the same event stream the CLI prints.

    `build_department` is imported here, not at module level, so this module
    stays importable without pulling waku in — the evaluators below are pure and
    that is what the deterministic eval exercises.
    """
    from concentric.run import build_department

    handoffs: list[dict[str, str]] = []

    def observer(kind: str, event: dict) -> None:
        if kind == "tool" and event.get("tool") in ("delegate", "consult_peer"):
            handoffs.append({
                "tool": event["tool"],
                "from": event.get("role", ""),
                "to": event.get("args", {}).get("role", ""),
            })

    reply = build_department().run(
        datapoint["task"], entry=datapoint.get("entry", "irina"),
        observer=observer)
    return {
        "reply": reply,
        "handoffs": handoffs,
        "targets": [h["to"] for h in handoffs if h["to"]],
    }


def delegated(output: dict, target: Any) -> float:
    """Did the department use an edge at all?"""
    return 1.0 if output.get("handoffs") else 0.0


def delegated_to_expected(output: dict, target: Any) -> float:
    """Did it reach the seat the task actually needed?"""
    expect = (target or {}).get("expect_seat")
    if not expect:
        return 1.0  # nothing was required, so nothing was missed
    return 1.0 if expect in output.get("targets", []) else 0.0


def reply_non_empty(output: dict, target: Any) -> float:
    return 1.0 if (output.get("reply") or "").strip() else 0.0


EVALUATORS = {
    "delegated": delegated,
    "delegated_to_expected": delegated_to_expected,
    "reply_non_empty": reply_non_empty,
}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    limit: int | None = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    key = (os.environ.get("LMNR_PROJECT_API_KEY") or "").strip()
    if not key:
        print("Set LMNR_PROJECT_API_KEY (see laminar/.env) before running evals.")
        return 2

    from lmnr import evaluate

    data = DATASET if limit is None else DATASET[:limit]
    result = evaluate(
        data=data,
        executor=run_department,
        evaluators=EVALUATORS,
        name="department-smoke",
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
