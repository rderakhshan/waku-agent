# Plan — Irina's department as a graph of waku blocks

> **Status:** implemented as a prototype in `concentric/`. Nothing under `waku/`
> changed; nothing ships (`pyproject.toml` packages only `waku`).

**Goal.** Establish the concentric department — Irina (ring 0), 4 CFOs (ring 1),
19 workers (ring 2) — by composing existing waku building blocks. The graph's
rules are enforced in code, not in prompts.

## Decisions

1. One new directory, `concentric/`, at the repo root. Repo-only.
2. **No changes to `waku/`.** Every node is an existing waku block.
3. All 24 seats share one configuration: `provider="deepseek"`,
   `model="deepseek-v4-pro"`, `small_model="deepseek-v4-flash"`. Per-seat
   configuration stays possible later because the config is a parameter.
4. Each seat is a **complete, independent `Waku`** — its own `home`, `state.db`,
   `SOUL.md`, `traces/`, `usage.jsonl` and filtered `ToolRegistry`.
5. One delegation factory serves every edge: vertical = `children(role)`,
   lateral = `peers(role)`.
6. Scope is the tool's `role` enum, re-checked in `fn`. Depth is the ring
   counter; at ring 2 the factory returns `None`, so a worker has no delegate
   tool at all — the capability is absent, not refused.
7. Serial first. Threaded fan-out and a budget ledger are deferred.

## The graph

```
ring 0   Irina
ring 1   4 CFOs        peer with each other
ring 2   19 workers    peer within their own team only

Irina <-> CFO        delegate      one level
CFO   <-> its team   delegate      one level
CFO   <-> CFO        consult_peer  ring 1
worker<-> worker     consult_peer  own team only
forbidden            cross-team, worker->other CFO, worker->Irina, skip-level
```

The upward direction is free: a delegate call returns
`child.respond(task).reply`, which becomes the tool result.

## Files

| File | What |
|---|---|
| `concentric/roster.py` | 24 `SeatSpec`s + `children`/`peers`/`ring`/`team`/`allowed` |
| `concentric/delegate.py` | `make_delegate` + `make_peer` (the one new mechanism) |
| `concentric/seat.py` | `build_seat()` → `Seat` (Settings, `SOUL.md`, filtered registry, identity) |
| `concentric/run.py` | `build_department()` + `run()` (lazy seat construction) |
| `concentric/__main__.py` | `python -m concentric "task"` |
| `concentric/demo.py` | offline end-to-end proof against a scripted client |
| `evals/deterministic/test_concentric_*.py` | 0/1 evals, no API key |

## Commands

```
python -m concentric.spike                       # prove the seams, offline
python -m pytest -q evals/deterministic/test_concentric_*.py
python -m ruff check concentric
python -m concentric "tier the IFRS 9 model"     # live, needs DEEPSEEK_API_KEY
```

## Deferred

Threaded `fan_out`, the whole-tree budget `ledger.py`, and docs. Add them once
the serial graph is green.
