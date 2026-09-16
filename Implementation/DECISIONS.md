# DECISIONS — settle these before Step 1

Four decisions gate the plan. Until they are answered, Step 0 (the spike) is the
only work that can safely proceed.

---

## D1 — How is waku pinned?

| Option | Trade |
|---|---|
| **A. Pin an exact PyPI version** (recommended) | reproducible; but upstream moves fast and the pin ages |
| B. Pin a git commit | same, plus access to unreleased fixes |
| C. Track `main` | always current; breaks silently |
| D. Vendor `loop/agent.py` + `loop/models.py` into `irina/backends/vendor/` | full control, MIT-licensed; you own drift |

**Recommendation: A**, with D as the escape hatch if drift bites. Whichever is
chosen, **all imports stay inside `irina/backends/`** (invariant 3).

---

## D2 — `respond()` or a lean `task()` for delegated nodes?

waku's `respond()` is a **chat turn**: it appends to the session, runs
`maybe_consolidate()` and `export_markdown()`.

| Option | Trade |
|---|---|
| **A. `respond()` everywhere** (recommended for CFOs) | each seat keeps a transcript — which *is* the audit record, and the RL trajectory |
| B. `task()` — a thin wrapper over `_run_full_turn` with no chat bookkeeping | cleaner for workers; you lose the per-seat transcript |
| C. Split: `respond()` for Irina + CFOs, `task()` for workers | best of both, one extra method |

**Recommendation: C**, decided in Step 0. The question to answer there: does the
transcript noise from 19 one-shot workers hurt, or does it help?

---

## D3 — Opt-in or default?

| Option | Trade |
|---|---|
| **A. Opt-in** — `IRINA_BACKEND=waku` (recommended) | the existing harness keeps working; coupling contained; safe to land incrementally |
| B. Default once Step 6 passes | simpler for the user; risks regressions in the shipped path |

**Recommendation: A.** Invariant 1 (all existing tests pass) is only meaningful if
the default path is untouched.

---

## D4 — Memory layout

| Option | Trade |
|---|---|
| **A. Per-seat home** — `.irina/agents/<role>/` (recommended) | each seat has its own `state.db`, traces, outbox. **This is what makes parallel fan-out safe** — each seat owns its connection |
| B. One shared home | one DB; but concurrent writes from a thread pool become a locking problem |

**Recommendation: A.** It is also the better model for the department: each seat
accumulates its own domain knowledge. Shared state belongs in the **model
inventory**, not in a shared memory file.

---

## Invariants — asserted after every step

1. `python -m pytest tests/` — all 24 existing test files pass.
2. `python -c "import irina"` works with **no optional dependency installed** (the
   stdlib-only core is preserved).
3. **No module outside `irina/backends/` imports waku.**

## Risks

| Risk | Mitigation |
|---|---|
| waku's internals drift | D1; all imports inside `irina/backends/` |
| `respond()` semantics wrong for workers | D2, settled in Step 0 |
| Live API spend during development | scripted-client injection in **every** test (waku's own eval pattern) |
| `Settings` silently reading env → 24 identical agents | construct `Settings` explicitly per seat |
| 24 SQLite files at start-up | lazy seat construction |
| Thread-safety of SQLite under fan-out | **verify** in Step 6 — waku's dashboard needed a cross-thread injection, so do not assume |
| Scope enforced only by prompt | Step 4's tests: cross-team delegation must return `"out of scope"` |
| The `Mediator` wrap is skipped | assert it in Step 3's tests |

## Out of scope

The security envelope beyond the `Mediator` wrap, the model inventory, governance
artefacts, the service layer, and the RL trajectory export. Steps 3–4 only
*preserve the seams* they will need. See `docs/improvement-directions.md` for the
long-term RL roadmap these feed.

## Open questions for the owner

1. **D1–D4** above.
2. Should the concentric sketch become the shipped figure (added to `images/` and
   referenced from the README), or stay a working artifact here?
3. Which provider/model pair is the default for a **CFO** (strong) and a **worker**
   (cheap)? The plan assumes a two-tier split but does not name the models.
4. Is the department's **existing** `irina/department/` implementation frozen while
   this backend is built, or should the two converge later?
