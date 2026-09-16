"""A0 — the spike. Prove the four seams before anything durable is written.

Run: python -m concentric.spike
Offline: a scripted client, no API key, no spend.

Four facts to confirm, in order:
  (a) an explicit Settings is honoured, not the environment
  (b) a seat's ToolRegistry can be filtered to a subset
  (c) respond() returns a LoopResult with .reply
  (d) a tool's fn can build and call another Waku -> the delegation edge
"""

from __future__ import annotations

from pathlib import Path

from evals.helpers import ScriptedClient, make_waku, response, text_block
from waku.tools.registry import Tool

STATE = Path(".waku-concentric/agents")

# respond() spends one small-model call on the retrieval gate BEFORE the loop
# (runtime/session.py:81 -> memory/retrieval_gate.py:36). So a scripted turn
# needs two responses: the gate's JSON, then the answer. No off-switch exists.
GATE_NO = '{"retrieve": false, "reason": "self-contained"}'


def _seat(role: str, model: str, script: list) -> object:
    return make_waku(STATE / role, client=ScriptedClient(script),
                     provider="anthropic", model=model, max_iterations=3)


def main() -> None:
    # (a) + (b) + (c) ------------------------------------------------------
    irina = _seat("irina", "claude-sonnet-5", [
        response([text_block(GATE_NO)]),
        response([text_block("seam ok")]),
    ])
    print("(a) provider :", irina.settings.provider)
    print("(a) model    :", irina.settings.model)
    print("(a) home     :", irina.settings.home)

    keep = {"create_event", "list_events"}
    for name in list(irina.tools._tools):
        if name not in keep:
            del irina.tools._tools[name]
    print("(b) tools    :", sorted(irina.tools._tools))

    result = irina.respond("hello from the spike")
    print("(c) reply    :", result.reply)
    print("(c) iters    :", result.iterations)

    # (d) the delegation edge: a tool whose fn builds and calls another Waku --
    child = _seat("cfo-2-validation", "claude-haiku-4-5-20251001", [
        response([text_block(GATE_NO)]),
        response([text_block("child replied")]),
    ])

    def delegate(role: str, task: str) -> str:
        if role != "cfo-2-validation":
            return "ERROR: out of scope"
        return child.respond(task).reply

    irina.tools.register(Tool(
        name="delegate",
        description="delegate a task to a seat you own",
        input_schema={
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["cfo-2-validation"]},
                "task": {"type": "string"},
            },
            "required": ["role", "task"],
        },
        fn=delegate,
    ))
    print("(d) delegate :", delegate("cfo-2-validation", "tier the IFRS 9 model"))


if __name__ == "__main__":
    main()
