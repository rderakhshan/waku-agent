"""Offline proof: the department runs end to end against a scripted model.

Run: python -m concentric.demo
No API key, no network, no spend. Prints the delegation path it took.

Each seat's script is the retrieval gate's answer, then the turn. A delegate
call costs two responses: the tool request, then the final text.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from concentric.run import build_department
from evals.helpers import ScriptedClient, response, text_block, tool_block

GATE_NO = '{"retrieve": false, "reason": "self-contained"}'


def _scripts() -> dict[str, list]:
    return {
        "irina": [
            response([text_block(GATE_NO)]),
            response([tool_block("delegate", {"role": "cfo-2-validation",
                                              "task": "Tier the IFRS 9 model."})],
                     "tool_use"),
            response([text_block("CFO-2 has tiered the IFRS 9 model.")]),
        ],
        "cfo-2-validation": [
            response([text_block(GATE_NO)]),
            response([tool_block("delegate", {"role": "challenger-modeler",
                                              "task": "Challenge the IFRS 9 tiering."})],
                     "tool_use"),
            response([text_block("The challenger reviewed it; the tiering stands.")]),
        ],
        "challenger-modeler": [
            response([text_block(GATE_NO)]),
            response([text_block("Challenger: the tiering is sound.")]),
        ],
    }


def main() -> int:
    scripts = _scripts()
    # A throwaway home per run: a demo must be repeatable, and reusing a home
    # would let the seats' own chat logs reach waku's consolidation threshold
    # and spend a scripted response. Nothing here is the user's data.
    root = Path(tempfile.mkdtemp(prefix="concentric-demo-"))
    department = build_department(
        client_factory=lambda role: ScriptedClient(scripts[role]), root=root)

    path: list[tuple[str, str]] = []

    def observer(kind: str, event: dict) -> None:
        if kind == "tool" and event.get("tool") in ("delegate", "consult_peer"):
            path.append((event["role"], event["args"]["role"]))

    reply = department.run("Tier the IFRS 9 model.", observer=observer)
    print("reply:", reply)

    # A child's events arrive while its parent's delegate call is still running,
    # so `path` is in emit order, not top-down order. Draw it as a tree.
    edges: dict[str, list[str]] = {}
    for src, dst in path:
        edges.setdefault(src, []).append(dst)

    def show(role: str, depth: int = 0) -> None:
        print("  " * depth + role)
        for child in edges.get(role, []):
            show(child, depth + 1)

    show("irina")
    print("seats built:", ", ".join(sorted(department._seats)))
    print("state:", root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
