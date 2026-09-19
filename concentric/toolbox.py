"""Which seat may use which tool, and the tools that are not in waku yet.

Scope in this department is the registry: a seat that does not hold a tool cannot
use it, because the tool is *absent* rather than refused. That rule only means
something if the decision is written down where a reader can find it — so this
module owns it. A file, not a prompt, and never a model's guess at run time.

Default is nobody. A tool reaches a seat only when the file says so.

Two kinds of tool live here:

  * the ones waku already builds — `search_web`, `create_event` and the rest —
    granted by name, which simply means not deleting them from the seat;
  * the ones written later, one file each under `concentric/tools/`, imported
    only for a seat that has been given them.

Reading a generated file's card does NOT run it. The name, description and input
shape are read out of the source with `ast`, and the module is imported only at
the moment a seat is built with it. Generated code is real code, and the moment
it runs is worth keeping to one place.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from concentric import roster

# Where the generated tools live. One file per tool, named after it.
TOOLS_DIR = Path(__file__).resolve().parent / "tools"

# The tools waku builds, and the switch that has to be on for each one to exist
# at all. Mirrors `waku/tools/__init__.py`; the department turns every switch off,
# so a tool listed here with a switch is present-but-inert until that changes.
BUILTIN_TOOLS: tuple[dict[str, str], ...] = (
    {"name": "search_web", "switch": "", "description": "Read-only web search."},
    {"name": "save_note", "switch": "", "description": "Write a note."},
    {"name": "list_events", "switch": "", "description": "Read the calendar."},
    {"name": "send_message", "switch": "",
     "description": "Send a message through a connected gateway."},
    {"name": "manage_memory", "switch": "", "description": "Correct or forget a memory."},
    {"name": "update_soul", "switch": "", "description": "Learn a standing rule."},
    {"name": "create_skill", "switch": "", "description": "Author a new skill."},
    {"name": "create_event", "switch": "apple_calendar / google_calendar",
     "description": "Add a calendar event. With neither calendar on, it writes to "
                    "waku's own store."},
    {"name": "github_read", "switch": "gh_tool",
     "description": "Read a GitHub repo through the gh CLI."},
    {"name": "delegate_task", "switch": "experimental",
     "description": "Hand a coding task to a sub-agent."},
)


# --- the file ----------------------------------------------------------------

def box_path() -> Path:
    """Beside the seats, not among them — the same reasoning as metrics.db.

    Deliberately NOT inside `concentric/`: an assignment is a choice this reader
    made about their own department, not source, and `.waku-concentric/` is
    already the gitignored home for exactly that.
    """
    from concentric import STATE_ROOT

    return STATE_ROOT.parent / "toolbox.json"


def load(path: Path | None = None) -> dict[str, list[str]]:
    target = path or box_path()
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, list[str]] = {}
    for tool, roles in (data or {}).items():
        if isinstance(roles, list):
            out[str(tool)] = [str(r) for r in roles]
    return out


def save(box: dict[str, list[str]], path: Path | None = None) -> None:
    target = path or box_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    kept = {tool: sorted(set(roles)) for tool, roles in box.items() if roles}
    target.write_text(json.dumps(kept, indent=2, sort_keys=True), encoding="utf-8")


def roles_for(tool: str, path: Path | None = None) -> list[str]:
    return load(path).get(tool, [])


def tools_for(role: str, path: Path | None = None) -> list[str]:
    """Every tool this seat has been given, generated or built in."""
    return sorted(tool for tool, roles in load(path).items() if role in roles)


def assign(tool: str, roles: list[str], path: Path | None = None) -> dict[str, list[str]]:
    """Give a tool to these seats.

    An unknown role is refused rather than stored: a typo that quietly grants
    nothing is worse than an error, because the page would show it as assigned.
    """
    unknown = sorted(r for r in roles if r not in roster.BY_ROLE)
    if unknown:
        raise ValueError(f"unknown role(s): {', '.join(unknown)}")
    box = load(path)
    box[tool] = sorted(set(roles))
    save(box, path)
    return box


def unassign(tool: str, path: Path | None = None) -> dict[str, list[str]]:
    box = load(path)
    box.pop(tool, None)
    save(box, path)
    return box


# --- the market --------------------------------------------------------------

def _metadata(path: Path) -> dict[str, Any] | None:
    """A card, read out of the source without running any of it."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    wanted = {"NAME", "DESCRIPTION", "INPUT_SCHEMA"}
    found: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in wanted:
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except Exception:
                    pass
    if "NAME" not in found:
        return None
    return {"name": str(found["NAME"]),
            "description": str(found.get("DESCRIPTION", "")),
            "schema": found.get("INPUT_SCHEMA") or {},
            "source": path.read_text(encoding="utf-8")}


def _planned() -> list[dict[str, Any]]:
    """waku's own wish list — three tools written down and not built."""
    try:
        from waku.tools.experimental import PLANNED
    except Exception:
        return []
    return [dict(item) for item in PLANNED]


def market() -> list[dict[str, Any]]:
    """Every tool this page can show: what waku builds, what is written here, and
    what is only planned."""
    box = load()
    cards: list[dict[str, Any]] = []

    for item in BUILTIN_TOOLS:
        cards.append({"name": item["name"], "description": item["description"],
                      "schema": {}, "switch": item["switch"], "state": "builtin",
                      "source": "", "roles": box.get(item["name"], [])})

    if TOOLS_DIR.is_dir():
        for path in sorted(TOOLS_DIR.glob("*.py")):
            if path.name.startswith("_"):
                continue
            meta = _metadata(path)
            if meta is None:
                continue
            meta.update({"switch": "", "state": "generated",
                         "roles": box.get(meta["name"], [])})
            cards.append(meta)

    for item in _planned():
        cards.append({"name": item.get("name", ""),
                      "description": item.get("description", ""),
                      "schema": {}, "switch": "", "state": "planned",
                      "source": "", "roles": box.get(item.get("name", ""), []),
                      "box": item.get("box", "")})
    return cards


GENERATE_PROMPT = """Write one Python tool for an agent.

Reply with ONLY the file's source. No markdown fence, no explanation, no text
before or after. The file must define exactly these four names:

NAME = "snake_case_name"
DESCRIPTION = "one sentence the model reads to decide when to call it"
INPUT_SCHEMA = {{"type": "object", "properties": {{...}}, "required": [...]}}
def run(**kwargs) -> str:
    ...

Rules:
- standard library only, imported inside `run` where you can;
- `run` returns a string, and never raises: return an error sentence instead;
- keep it short enough to read in one screen.

The tool to write: {ask}
"""


def _imports(source: str) -> list[str]:
    """The modules a tool's source imports, so the card can show them.

    Not a sandbox and not a verdict — a reader deciding whether to hand this to a
    seat should see what it reaches for, and that is all this claims to be.
    """
    try:
        tree = ast.parse(source)
    except Exception:
        return []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return sorted(found)


def _strip_fence(text: str) -> str:
    """A model often wraps source in a fence however plainly it was asked not to."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
    return body.strip() + "\n"


def generate(ask: str) -> dict[str, Any]:
    """Draft one tool from a description and write it, assigned to nobody.

    Written, not handed out: a generated tool is real code that will run inside
    the agent, so the page makes it be read before it can be given to a seat.
    This writes a file and nothing else.
    """
    import re

    from concentric import metrics

    source = _strip_fence(metrics.ask(GENERATE_PROMPT.format(ask=ask), max_tokens=1200))
    meta = _metadata_from(source)
    if meta is None:
        return {"error": "the model did not return a file with NAME, DESCRIPTION "
                         "and INPUT_SCHEMA"}
    name = meta["name"]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        return {"error": f"unusable tool name: {name!r}"}
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    target = TOOLS_DIR / f"{name}.py"
    if target.exists():
        return {"error": f"{name} already exists — pick a different name"}
    target.write_text(source, encoding="utf-8")
    return {"name": name, "imports": _imports(source)}


def _metadata_from(source: str) -> dict[str, Any] | None:
    """The same read as `_metadata`, on text rather than a file."""
    try:
        tree = ast.parse(source)
    except Exception:
        return None
    wanted = {"NAME", "DESCRIPTION", "INPUT_SCHEMA"}
    found: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in wanted:
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except Exception:
                    pass
    if "NAME" not in found:
        return None
    return {"name": str(found["NAME"]),
            "description": str(found.get("DESCRIPTION", "")),
            "schema": found.get("INPUT_SCHEMA") or {}}


def make_tool(name: str):
    """Wrap one generated file as a waku Tool, or None if there is no such file.

    Imported here and nowhere else: this is the one moment a generated tool's
    code runs, and it happens because a seat was built with it.
    """
    import importlib.util

    path = TOOLS_DIR / f"{name}.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"concentric_tool_{name}", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from waku.tools.registry import Tool

    return Tool(name=module.NAME, description=module.DESCRIPTION,
                input_schema=module.INPUT_SCHEMA, fn=module.run)
