# The toolbox — who may hold which tool

Scope in this department is the registry. A seat that does not hold a tool cannot
use it, because the tool is **absent**, not refused — that is the same rule that
makes a worker unable to delegate. A rule like that only means something if the
decision is written down somewhere a reader can find, so it lives in a file, not
in a prompt and never in a model's guess at run time.

## The default is nobody

A fresh department grants nothing. Every seat starts with the same two tools it
always had — `save_note` and `manage_memory` — plus the delegation tools its ring
allows. Everything else arrives because someone said so.

The file is `.waku-concentric/toolbox.json`, beside `metrics.db` and gitignored,
because an assignment is a choice about your own department rather than source:

```json
{
  "search_web": ["irina", "cfo-4-audit"]
}
```

An empty list is not written: the absence of a grant is not a grant of nothing.

## Two kinds of tool

- **What waku builds** — `search_web`, `create_event`, `list_events`,
  `send_message`, `manage_memory`, `update_soul`, `create_skill`, and the three
  behind switches (`github_read`, `delegate_task`, the Apple set). Granting one
  of these means *not deleting it* from the seat.
- **What is written here** — one file per tool under `concentric/tools/`, named
  after the tool. Each file defines four names and nothing else:

  ```python
  NAME = "lookup_rate"
  DESCRIPTION = "one sentence the model reads to decide when to call it"
  INPUT_SCHEMA = {"type": "object", "properties": {...}, "required": [...]}
  def run(**kwargs) -> str: ...
  ```

  A generated file is imported only when a seat that holds it is built. Reading
  its card does not run it: the name, description and shape are read out of the
  source with `ast`.

## The page

**Tools → Market.** A card per tool: what it does, who has it, and the ticks that
decide. Seats are grouped by ring, so "all four CFOs" is four clicks and one
Save. `Save` writes the file; the page reads it back, so what you see is what is
stored.

A card also says which switch gates its tool, because several are present and
inert — the department turns every waku switch off, so granting `github_read`
without turning `gh_tool` on gives a seat a tool that does nothing.

## Generated tools are code, and code runs

`Market → describe a tool` asks the model for a file, writes it under
`concentric/tools/`, and assigns it to **nobody**. The card then shows the source
and the modules it imports, and the ticks stay disabled until you have read it.

That gate is the whole safety story, and it is deliberately only that. A tool
runs in the same process as the agent, with the same reach: it can read files,
call the network, and delete things. This is not a sandbox, and the page does not
pretend otherwise — it makes you look before you hand it out.

## How a grant reaches a seat

`build_seat` keeps `BASE_TOOLS` plus `toolbox.tools_for(role)`, deletes the rest,
then registers the generated files that seat holds. One filter, reading a file
instead of a constant.

Tests: `evals/deterministic/test_toolbox.py`. The one that matters most writes a
tool file that raises on import and asserts its card still appears — reading a
market must never execute it.
