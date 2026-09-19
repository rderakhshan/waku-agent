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


def test_the_floor_tools_report_every_seat_not_nobody():
    """`save_note` is held by every seat before anything is granted, and the
    department page says so — reporting the grant file alone would have the two
    halves of the dashboard disagreeing about the same tool."""
    cards = {c["name"]: c for c in toolbox.market()}
    floor = cards["save_note"]
    assert floor["state"] == "floor"
    assert len(floor["roles"]) == 24
    assert toolbox.load() == {}          # and yet nothing is in the file


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

def test_imports_are_reported_so_a_reader_can_see_them():
    src = "import json\nfrom pathlib import Path\ndef run(**k):\n    return ''\n"
    assert toolbox._imports(src) == ["json", "pathlib"]


def test_a_card_reads_from_text_as_well_as_a_file():
    meta = toolbox._card_from(RAISER)
    assert meta is not None
    assert meta["name"] == "boom_tool"
    assert meta["schema"] == {"type": "object", "properties": {}}
    assert meta["origin"] == toolbox.LAB_ORIGIN   # no ORIGIN line means a person wrote it


def test_a_card_gives_up_on_rubbish():
    assert toolbox._card_from("not python at all ((") is None
    assert toolbox._card_from("X = 1\n") is None


# --- the lab -----------------------------------------------------------------
#
# The lab is an assembler, not a generator: it writes the parts a person typed.
# That is why a tool built there needs no review gate, and why every way of
# getting those parts wrong has to come back as a sentence rather than a file.

def _lab(tmp_path, monkeypatch, **over):
    monkeypatch.setattr(toolbox, "TOOLS_DIR", tmp_path)
    parts = {"name": "ok_tool", "description": "does a thing",
             "schema": {"type": "object", "properties": {}}, "icon": "tools",
             "body": "def run(**kwargs) -> str:\n    return ''\n"}
    parts.update(over)
    return toolbox.assemble(parts.pop("name"), parts.pop("description"),
                            parts.pop("schema"), parts.pop("icon"),
                            parts.pop("body"))


def test_the_lab_assembles_a_tool_from_its_parts(tmp_path, monkeypatch):
    assert _lab(tmp_path, monkeypatch, name="lookup_rate", icon="chart").get("name") \
        == "lookup_rate"
    card = {c["name"]: c for c in toolbox.market()}["lookup_rate"]
    assert card["icon"] == "chart"
    assert card["origin"] == toolbox.LAB_ORIGIN
    assert card["state"] == "generated"
    assert card["description"] == "does a thing"


def test_a_tool_built_in_the_lab_is_still_assigned_to_nobody(tmp_path, monkeypatch):
    _lab(tmp_path, monkeypatch)
    assert toolbox.load(tmp_path / "box.json") == {}


def test_a_model_written_tool_is_stamped_so_the_gate_can_find_it(tmp_path, monkeypatch):
    monkeypatch.setattr(toolbox, "TOOLS_DIR", tmp_path)
    (tmp_path / "made_up.py").write_text(
        'ORIGIN = "model"\n' + RAISER.replace("boom_tool", "made_up"), encoding="utf-8")
    card = {c["name"]: c for c in toolbox.market()}["made_up"]
    assert card["origin"] == "model"


def test_an_id_that_is_not_snake_case_is_refused(tmp_path, monkeypatch):
    assert "snake_case" in _lab(tmp_path, monkeypatch, name="Not A Name")["error"]


def test_a_missing_description_is_refused(tmp_path, monkeypatch):
    assert "description" in _lab(tmp_path, monkeypatch, description="   ")["error"]


def test_a_body_without_run_is_refused(tmp_path, monkeypatch):
    assert "run(" in _lab(tmp_path, monkeypatch, body="x = 1\n")["error"]


def test_a_shape_that_is_not_an_object_is_refused(tmp_path, monkeypatch):
    assert "JSON object" in _lab(tmp_path, monkeypatch, schema=None)["error"]


def test_an_id_already_in_use_is_refused(tmp_path, monkeypatch):
    _lab(tmp_path, monkeypatch)
    assert "already exists" in _lab(tmp_path, monkeypatch)["error"]


def test_the_assembled_file_is_the_contract_and_nothing_else(tmp_path, monkeypatch):
    _lab(tmp_path, monkeypatch, name="tiny", icon="check")
    source = (tmp_path / "tiny.py").read_text(encoding="utf-8")
    for line in ('NAME = "tiny"', 'ICON = "check"', 'ORIGIN = "lab"', "INPUT_SCHEMA"):
        assert line in source
    assert "def run(" in source
