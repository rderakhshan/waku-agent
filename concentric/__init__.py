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

# Where the seats keep their own memory, prompts, traces and ledgers. The
# `.waku-` prefix means .gitignore's `.waku-*/` rule already covers it.
STATE_ROOT = Path(".waku-concentric/agents")


def seat_home(role: str, root: Path | None = None) -> Path:
    return (root or STATE_ROOT) / role
