# The toolbox — who may hold which tool

Scope in this department is the registry. A seat that does not hold a tool cannot
use it, because the tool is **absent**, not refused — the same rule that stops a
worker delegating. A rule like that only means something if the decision is
written down somewhere a reader can find, so it lives in a file, not in a prompt
and never in a model's guess at run time.

## The page

Five tabs: **Available** — what the agent can call this turn, drawn as the same
cards the Market uses; **Results** — what it called; **Market** — what a seat may
hold; **LAB** — build a tool; **MCP** — external servers.

## The default is nobody

A fresh department grants nothing. Every seat starts with the two tools it always
had — `save_note` and `manage_memory` — plus the delegation tools its ring allows.
Everything else arrives because someone said so.

Those two are shown as **every seat** rather than *nobody*, and carry no Assign
button: they are the floor, held before anything is granted. Reporting the grant
file alone would have the Market say "nobody" about a tool the department page
says is held by all twenty-four seats.

The file is `.waku-concentric/toolbox.json`, beside `metrics.db` and gitignored,
because an assignment is a choice about your own department rather than source:

```json
{
  "search_web": ["cfo-4-audit"]
}
```

An empty list is not written: the absence of a grant is not a grant of nothing.

## Two kinds of tool

- **What waku builds** — `search_web`, `create_event`, `list_events`,
  `send_message`, `manage_memory`, `update_soul`, `create_skill`, and the three
  behind switches (`github_read`, `delegate_task`, the Apple set). Granting one of
  these means *not deleting it* from the seat.
- **What is built here** — one file per tool under `concentric/tools/`, named
  after the tool, written by the LAB.

## The Market

**Tools → Market.** A card per tool, built on the same anatomy as the Connections
page: a tile, a state pill, a line of description, an action.

The pill is the whole state at a glance — **assigned**, **nobody**,
**needs setup** (present, but its switch is off), or **planned** (on waku's wish
list). Cards are grouped into sections by that state, so the tools you have given
out are not mixed in with the ones you have not.

A specialised tool has one owner, so the card shows its holders as **chips** and
an **Assign** button — not a wall of twenty-four checkboxes, which would imply the
normal case is picking many. Beyond two holders the rest are counted as `+N`, with
the full list in the tooltip. The Assign menu is grouped by ring — Irina, CFOs,
Workers, with workers showing their team — so you pick a seat by where it sits,
and it offers "Remove from everyone" once anyone holds the tool.

## The LAB

**Tools → LAB.** A form, not a prompt. You supply:

- an **id** — snake case, which is both the file name and the name the model calls;
- a **description** — the one field that decides whether the tool is ever called,
  because the model never reads your code;
- an **icon** from the vendored set;
- the **arguments**, added a row at a time: name, type, description, required;
- the **code body**, pasted in.

The page assembles the argument rows into the schema itself. A schema is something
a page can build, and a typo in one is a tool that never gets called — so nobody
writes one by hand. The file that lands is the one you wrote, which is why a tool
built here can be handed to a seat at once.

## What a tool file is

```python
NAME = "lookup_rate"
DESCRIPTION = "one sentence the model reads to decide when to call it"
ICON = "chart"
ORIGIN = "lab"
INPUT_SCHEMA = {"type": "object", "properties": {...}, "required": [...]}

def run(**kwargs) -> str: ...
```

Standard library only. `run` returns a string and never raises — return an error
sentence instead, the way every waku tool does. `ORIGIN` records who wrote the
file; the LAB writes `"lab"`.

Reading this folder for the Market does **not** import these files: the name,
description, icon and shape are read out of the source with `ast`. That is not a
nicety — the page lists every file in the folder, so if drawing a card executed
the file, opening the tab would run whatever was last put there. A file is
imported at exactly one moment: when a seat that holds it is built.

A tool runs inside the agent's own process with the agent's own reach — files,
network, deletions. There is no sandbox. The card shows a built tool's source
under "What it actually does", so you can read it before you hand it out.

## How a grant reaches a seat

`build_seat` keeps `BASE_TOOLS` plus `toolbox.tools_for(role)`, deletes the rest,
then registers the built files that seat holds. One filter, reading a file instead
of a constant.

Tests: `evals/deterministic/test_toolbox.py`. Two of them carry the weight: a tool
file that raises on import still gets a card, and every way of getting the LAB's
parts wrong comes back as a sentence rather than a file.
