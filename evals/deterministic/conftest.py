"""Record which dataset cases passed, so tool-use accuracy has a numerator.

The suite already asserts every case against its expected tool and arguments.
This only writes the outcome down, in the shape `concentric/metrics.py` reads —
and the path comes from that module rather than being rebuilt here, so the
writer and the reader cannot drift apart.

It writes only when the home already exists. Running the tests in a fresh
checkout must not create one, and CI is a fresh checkout.
"""

from __future__ import annotations

import json

_OUTCOMES: dict[str, bool] = {}


def pytest_runtest_logreport(report) -> None:
    # "::test_dataset_case" and not "dataset_case": the looser match also caught
    # this repository's own unit test for the metric, which is named
    # test_tool_accuracy_is_the_share_of_dataset_cases_that_passed. That recorded
    # a pass against the wrong thing and reported tool-use accuracy as 1.0 — a
    # number that looked like a measurement and was a substring match.
    if report.when != "call" or "::test_dataset_case" not in report.nodeid:
        return
    _OUTCOMES[report.nodeid] = report.passed


def pytest_sessionfinish(session, exitstatus) -> None:
    if not _OUTCOMES:
        return
    try:
        from concentric.metrics import tool_report_path

        path = tool_report_path(ensure=False)
        if not path.parent.exists():
            return
        path.write_text(json.dumps({
            "cases": _OUTCOMES,
            "passed": sum(_OUTCOMES.values()),
            "total": len(_OUTCOMES),
        }, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 — a reporting hook must never fail a run
        pass
