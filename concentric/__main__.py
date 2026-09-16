"""python -m concentric            -> chat with Irina
   python -m concentric "task"    -> one-shot

The chat path needs DEEPSEEK_API_KEY in .env; every turn is a real model call.
"""

from __future__ import annotations

import sys

from concentric import roster
from concentric.run import build_department


def one_shot(task: str) -> int:
    def observer(kind: str, event: dict) -> None:
        if kind == "tool" and event.get("tool") in ("delegate", "consult_peer"):
            print(f"  [ring {event.get('ring')}] {event.get('role')} "
                  f"--{event['tool']}--> {event['args'].get('role')}")

    print(f'Department: {len(roster.SEATS)} seats on deepseek. Task: "{task}"')
    reply = build_department().run(task, observer=observer)
    print("\n" + reply)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        from concentric.chat import chat

        return chat()
    return one_shot(" ".join(args))


if __name__ == "__main__":
    raise SystemExit(main())
