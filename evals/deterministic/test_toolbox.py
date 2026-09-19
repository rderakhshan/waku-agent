"""Who may hold which tool, and the one rule that keeps generated code honest.

Two things are being pinned here.

The first is the default. A tool reaches a seat only because a file says so, so
"nobody" has to be the state of a fresh department — otherwise a new tool is
handed out by accident, and the design's claim that scope is the registry stops
being true.

The second is that reading a tool's card must not run it. A generated tool is
real code, and the page shows every tool in the market whether or not anyone has
it. If building that page executed the files, opening a tab would run whatever
was last generated. The test for it is blunt: the file raises on import, and the
card still appears.
"""

from __future__ import annotations

import pytest

from concentric import toolbox

RAISER = '''
NAME = "boom_tool"
DESCRIPTION = "a tool whose body must never run for a card to be drawn"
INPUT_SCHEMA = {"type": "object", "properties": {}}

raise RuntimeError("this file must not be executed to read its card")
'''


@pytest.fixture()
def box(tmp_path):
    return tmp_path / "toolbox.json"


# --- the file ----------------------------------------------------------------

def test_nobody_holds_anything_by_default(box):
    assert toolbox.load(box) == {}
    assert toolbox.tools_for("irina", box) == []
    assert toolbox.roles_for("search_web", box) == []


def test_assigning_grants_it_and_reads_back(box):
    toolbox.assign("search_web", ["cfo-4-audit", "irina"], box)
    assert toolbox.tools_for("irina", box) == ["search_web"]
    assert toolbox.roles_for("search_web", box) == ["cfo-4-audit", "irina"]


def test_an_unknown_role_is_refused_not_stored(box):
    """A typo that grants nothing would show on the page as granted."""
    with pytest.raises(ValueError):
        toolbox.assign("search_web", ["cfo-99-nope"], box)
    assert toolbox.load(box) == {}


def test_unassigning_removes_it(box):
    toolbox.assign("search_web", ["irina"], box)
    toolbox.unassign("search_web", box)
    assert toolbox.load(box) == {}


def test_a_tool_held_by_nobody_is_not_written(box):
    """An empty grant is the absence of a grant, not a line saying zero."""
    toolbox.assign("search_web", ["irina"], box)
    toolbox.assign("search_web", [], box)
    assert "search_web" not in toolbox.load(box)


# --- the market --------------------------------------------------------------

def test_the_market_lists_what_waku_builds():
    names = {card["name"] for card in toolbox.market()}
    assert {"search_web", "save_note", "manage_memory"} <= names


def test_every_builtin_card_says_which_switch_gates_it():
    for card in toolbox.market():
        if card["state"] == "builtin":
            assert "switch" in card


def test_a_generated_file_becomes_a_card_without_running_it(tmp_path, monkeypatch):
    """The load-bearing test: a card is read, not executed."""
    monkeypatch.setattr(toolbox, "TOOLS_DIR", tmp_path)
    (tmp_path / "boom_tool.py").write_text(RAISER, encoding="utf-8")
    cards = {card["name"]: card for card in toolbox.market()}
    assert "boom_tool" in cards
    assert cards["boom_tool"]["state"] == "generated"
    assert cards["boom_tool"]["description"].startswith("a tool whose body")


def test_a_file_with_no_name_is_not_a_card(tmp_path, monkeypatch):
    monkeypatch.setattr(toolbox, "TOOLS_DIR", tmp_path)
    (tmp_path / "nameless.py").write_text("X = 1\n", encoding="utf-8")
    assert "nameless" not in {card["name"] for card in toolbox.market()}


def test_a_private_file_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(toolbox, "TOOLS_DIR", tmp_path)
    (tmp_path / "_helper.py").write_text(RAISER, encoding="utf-8")
    assert "boom_tool" not in {card["name"] for card in toolbox.market()}


# --- the parts of generation that need no model ------------------------------

def test_a_fenced_reply_is_unwrapped():
    assert toolbox._strip_fence("```python\nX = 1\n```") == "X = 1\n"


def test_imports_are_reported_so_a_reader_can_see_them():
    src = "import json\nfrom pathlib import Path\ndef run(**k):\n    return ''\n"
    assert toolbox._imports(src) == ["json", "pathlib"]


def test_metadata_from_text_reads_the_three_names():
    meta = toolbox._metadata_from(RAISER)
    assert meta is not None
    assert meta["name"] == "boom_tool"
    assert meta["schema"] == {"type": "object", "properties": {}}


def test_metadata_from_text_gives_up_on_rubbish():
    assert toolbox._metadata_from("not python at all ((") is None
    assert toolbox._metadata_from("X = 1\n") is None
