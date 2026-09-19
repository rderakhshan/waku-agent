"""The rail's order and its names belong to this launcher, not to waku.

The shell ships its own order and labels, and the launcher rearranges three rows
and renames one on the way through. Both are string surgery on markup this repo
does not own, which is the kind of change that stops working quietly when the
markup moves — so the intent is pinned here instead of living in a comment.

Source-level, like `test_cause_panel.py`: importing the launcher would pull waku
in and set the environment for every other test in the run.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "concentric" / "dashboard.py").read_text(encoding="utf-8")


def test_tools_is_renamed_to_say_it_covers_mcps():
    assert '"tools": "Tools &amp; MCPs"' in SOURCE


def test_the_three_rows_move_together():
    assert '_RAIL_ORDER = ("tools", "memory", "graph")' in SOURCE


def test_the_reorder_and_the_rename_are_both_applied():
    assert "_reorder(html, _RAIL_ORDER)" in SOURCE
    assert "_rename(html, _RAIL_NAMES)" in SOURCE
