"""Talk to Irina in the console — the interactive front door.

    python -m concentric            # chat (this file)
    python -m concentric "task"     # one-shot

One Department instance lives for the whole session, so Irina keeps her
conversation history in memory and her memory on disk. Delegated seats stream
their text too, each line prefixed with the seat that is speaking, so you can
watch the department work.

Needs DEEPSEEK_API_KEY in .env. Every turn is a real model call.
"""

from __future__ import annotations

import sys

from concentric import roster
from concentric.run import build_department

BANNER = """\
Irina's department - {n} seats on deepseek.
Ask Irina for work. She delegates down and reports back.
  /seats   list every seat
  /exit    leave (Ctrl-C or Ctrl-D also work)"""


class _Printer:
    """Renders the event stream as readable, role-prefixed output."""

    def __init__(self) -> None:
        self._speaker: str | None = None
        self._line_open = False
        self._streamed = False

    def _close_line(self) -> None:
        if self._line_open:
            print()
            self._line_open = False

    def __call__(self, kind: str, event: dict) -> None:
        role = event.get("role", "?")
        if kind == "text":
            delta = event.get("delta", "")
            if not delta:
                return
            if self._speaker != role:
                self._close_line()
                print(f"\n[{role}] ", end="", flush=True)
                self._speaker = role
            print(delta, end="", flush=True)
            self._line_open = True
            self._streamed = True
        elif kind == "tool" and event.get("tool") in ("delegate", "consult_peer"):
            self._close_line()
            self._speaker = None
            target = event.get("args", {}).get("role", "?")
            print(f"    .. {role} --{event['tool']}--> {target}", flush=True)

    def finish(self, reply: str) -> None:
        """After a turn: close any open line, and print the reply if it never
        streamed (a client without streaming, or a purely delegated answer)."""
        if not self._streamed:
            print(f"\n[irina] {reply}")
        self._close_line()
        self._speaker = None
        self._streamed = False


def _print_seats() -> None:
    for ring in (0, 1, 2):
        seats = [s for s in roster.SEATS if s.ring == ring]
        print(f"  ring {ring}: " + ", ".join(s.role for s in seats))


def chat() -> int:
    department = build_department()
    print(BANNER.format(n=len(roster.SEATS)))
    while True:
        try:
            line = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/exit", "/quit"):
            return 0
        if line == "/seats":
            _print_seats()
            continue
        printer = _Printer()
        try:
            reply = department.run(line, observer=printer, stream=True)
        except Exception as exc:  # a bad key or a provider error, not a crash
            print(f"\n[error] {exc}")
            print("Check DEEPSEEK_API_KEY in your .env.")
            continue
        printer.finish(reply)


def main() -> int:
    return chat()


if __name__ == "__main__":
    sys.exit(chat())
