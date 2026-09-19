"""concentric — Irina's department, assembled on waku.

One seat = one configured waku agent (Waku + a filtered ToolRegistry). The graph
rules live in code, not prompts: the delegation edge exists because the tool
exists, scope is the tool's role enum, depth is a ring counter.

This directory is a working prototype. Nothing under waku/ imports it, and it is
not shipped (pyproject packages only waku). State lives in .waku-concentric/.
"""

from pathlib import Path

# One configuration for every seat, for now. Kept here — not in run.py — because
# the dashboard launcher must set the matching WAKU_* env vars BEFORE anything
# imports waku.config, and importing run.py would import waku.
PROVIDER = "deepseek"
MODEL = "deepseek-v4-pro"
SMALL_MODEL = "deepseek-v4-flash"

# The seat a run enters through. Its trace and its ledger already contain the
# whole subtree, so they are the department's source of truth for activity.
ENTRY = "irina"

# The tools every seat holds before anything is granted. Kept here rather than in
# seat.py so the toolbox can name them without importing waku: the Market has to
# be able to say "every seat" about these, instead of "nobody", which is what the
# grant file alone would report and what the department page contradicts.
BASE_TOOLS = ("save_note", "manage_memory")

# Where the seats keep their own memory, prompts, traces and ledgers. The
# `.waku-` prefix means .gitignore's `.waku-*/` rule already covers it.
STATE_ROOT = Path(".waku-concentric/agents")

# Home's billboard reads this as a directory rather than a list, so dropping an
# image in adds it to the rotation without touching code.
BILLBOARD_DIR = Path(__file__).resolve().parents[1] / "assets" / "images"


def seat_home(role: str, root: Path | None = None) -> Path:
    return (root or STATE_ROOT) / role
