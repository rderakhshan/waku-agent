"""DETERMINISTIC EVAL — the cause panel compares a role, not an object.

The bug this pins was silent in the way that matters. `detailRow()` is handed the
seat OBJECT — it reads `seat.role`, `seat.activity` and so on throughout — but the
cause check was written as:

    if (cause && cause.subject === seat)

`cause.subject` is a role string. A string never equals an object, so the branch
was false every time, the panel never rendered, and nothing threw. The row simply
showed the readings instead, which looks exactly like a feature that was never
built. It cost a full browser session to find, because the only symptom was a
panel that did not appear.

Python cannot test this: it is one comparison inside a browser script. So the
check is over the source, which is the same thing `test_design_system.py` does
for colour literals and `test_rulebook.py` does for emoji. A grep is a blunt
instrument, and for a bug whose whole signature is one missing `.role`, blunt is
enough.

The second half guards the wiring the click needs: a trend cell has to carry the
metric AND the seat, because the handler reads both and a cell missing one would
open a cause for the wrong thing.
"""

from __future__ import annotations

import pathlib
import re

OBSERVATION = (pathlib.Path(__file__).resolve().parents[2]
               / "concentric" / "static" / "observation.js")


def _source() -> str:
    return OBSERVATION.read_text(encoding="utf-8")


def test_the_cause_is_matched_against_a_role():
    """`cause.subject === seat` is false for every seat. It has to be seat.role."""
    source = _source()
    assert "cause.subject === seat.role" in source, (
        "the cause panel no longer compares the cause's subject against the "
        "seat's ROLE — if this was renamed, check the comparison is still "
        "string-to-string")


def test_the_cause_is_never_matched_against_the_seat_object():
    """The exact shape of the bug, so it cannot come back by a different route.

    `seat.role`, `seat.title` and the rest are fine; a bare `seat` is not, because
    it is an object and the subject is a role.
    """
    source = _source()
    offenders = re.findall(r"cause\.subject\s*===?\s*seat\b(?!\.)", source)
    assert not offenders, (
        f"{len(offenders)} comparison(s) of a role string against the seat "
        f"OBJECT — this is always false: {offenders}")


def test_a_trend_cell_carries_the_metric_and_the_seat():
    """The click handler reads both. A cell carrying only the metric would open
    the cause for whichever seat happened to be first."""
    source = _source()
    assert 'class="lab-trend"' in source, "the trend cell lost its class"
    assert "data-metric=" in source and "data-seat=" in source, (
        "a trend cell must carry both data-metric and data-seat for the click "
        "to know what to open")


def test_the_detail_row_delegates_to_the_cause_when_one_matches():
    """The panel is only reachable through detailRow. If that call is removed the
    comparison above becomes dead code and the panel silently stops appearing —
    the same failure, one layer up."""
    source = _source()
    assert "return causeRow(" in source, (
        "detailRow no longer renders causeRow — the cause panel is unreachable")
