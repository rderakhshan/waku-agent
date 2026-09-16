# Plan — assembling Irina's concentric department on waku

> **Status:** ○ **Proposed** — nothing implemented. This is the construction plan
> for the sketch *"Irina's Department — Concentric Round Tables"* and its
> pseudo-code prompt.

**Objective.** Assemble Irina's department — Irina (ring 0), 4 CFOs (ring 1), 19
workers (ring 2) — using waku's `Waku` class as the base harness, with the
graph's rules enforced **in code**, not in prompts.

**The shape being built** (from the sketch):

```
ring 0  Irina
ring 1  4 CFOs on one round table  (they peer)
ring 2  4 team arcs                (workers peer inside their own arc only)

edges:  Irina ↔ CFO        vertical, one level
        worker ↔ its CFO   vertical, one level
        CFO ↔ CFO          lateral, ring 1
        worker ↔ worker    lateral, ring 2, SAME arc only
forbid: worker ↔ other team's worker · worker ↔ other CFO · worker ↔ Irina
```

**Why waku works as the base.** `Waku.__init__(settings, client, conn)` is an
assembly root (config → db → tools → memory → session → loop) whose every
per-node attribute is a `Settings` field — `home` (memory), `model`/`provider`,
`max_iterations`, `max_tokens`. One node = `Waku(Settings(...))` plus a filtered
`ToolRegistry`. `client` is injectable, which is what makes every test below
runnable **without API spend**.

---

## Pre-flight (verified)

| Check | State |
|---|---|
| Branch | `main` |
| waku installed | **no** — the extra does not exist yet |
| Python | 3.13.9 |
| Repo plan convention | `docs/*-plan.md` |
| Test suite | 24 files under `tests/`, no `conftest.py`, helper is `tests/support.py` |
| Existing roster to derive from | `irina/department/roster.py` (24 roles, `parent` per role) |

**Invariants asserted after every step:**

1. `python -m pytest tests/` — all existing tests pass.
2. `python -c "import irina"` works with **no optional dependency installed** (the
   stdlib-only core is preserved).
3. **No module outside `irina/backends/` imports waku.** This is what keeps the
   coupling contained and the default path untouched.

---

## Steps

Seven steps. Serial order with two parallelisable pairs. Each step is one PR.

```
0  spike ──────────► 1  extra ──┐
                                ├─► 3  seat ──► 4  delegate ──► 5  ledger ──► 6  graph ──► 7  wiring
                    2  roster ──┘
```

| # | Step | Depends on | Tier | Parallel with |
|---|---|---|---|---|
| 0 | Spike — prove the seam | — | strongest | — |
| 1 | `irina[waku]` extra + guarded import | 0 | default | 2 |
| 2 | Roster (graph as data) | 0 | default | 1 |
| 3 | Identity + seat builder | 1, 2 | strongest | — |
| 4 | Delegation edge + scope + depth | 3 | strongest | 5 (module only) |
| 5 | Budget ledger | 3 | default | 4 (module only) |
| 6 | Orchestrator (build + run + fan-out) | 4, 5 | strongest | — |
| 7 | Opt-in wiring + docs | 6 | default | — |

---

### Step 0 — Spike: prove the seam *(throwaway, do this first)*

**Context brief.** The whole plan rests on four assumptions about waku that have
been read but not run. Prove them before writing anything durable. waku is not
installed; install it into a scratch venv, not the repo's.

**Tasks**

1. Scratch venv; `pip install waku-agent`.
2. Build one agent with **explicit** settings:
   `Waku(Settings(provider="anthropic", model="claude-sonnet-5", home=Path(tmp)))`.
3. Inject a **scripted client** (the seam `Waku(settings, client=...)` documents)
   that returns a canned Anthropic-shaped reply — no network.
4. Confirm: (a) explicit `Settings` is honoured, not the env; (b) `agent.tools`
   can be filtered to a subset and `respond()` still runs; (c) `respond()` returns
   `LoopResult` with `.reply`; (d) a tool's `fn` can be replaced, so a *delegation*
   tool can call another `Waku`.
5. Write down everything that broke or surprised.

**Verification.** The script runs offline and prints a `LoopResult`.

**Exit criteria.** All four facts confirmed, **or** a documented blocker that
changes the plan. If (d) fails, the delegation edge needs a different hook and
Step 4 is redesigned before anything else is built.

**Rollback.** Delete the scratch venv and the script.

---

### Step 1 — The dependency seam

**Context brief.** waku requires `anthropic` and `openai`; Irina's core is
stdlib-only and must stay that way. Add waku as an **optional extra** behind a
guarded import, so `import irina` is unchanged for anyone who does not want it.

**Tasks**

1. `pyproject.toml`: add `waku = ["waku-agent==<pinned>"]` to
   `[project.optional-dependencies]`. **Pin exactly** (waku's internals are
   unversioned; 341 commits and no stability promise).
2. `irina/backends/__init__.py` — a lazy accessor that raises a clear
   `RuntimeError` naming the install command when waku is absent.
3. Do **not** touch `irina/provider/`, `irina/loop/`, or `irina/harness/`.

**Verification**

```bash
python -m pytest tests/                       # all pass, waku not installed
python -c "import irina; print(irina.__version__)"
python -c "import irina.backends"             # raises the helpful error
```

**Exit criteria.** Core imports clean without waku; the extra installs and the
accessor resolves. Invariant 3 holds.

**Rollback.** Revert `pyproject.toml`; delete `irina/backends/`.

---

### Step 2 — Roster: the graph as data

**Context brief.** The graph must be describable as data before it can be built.
The 24 roles already exist in `irina/department/roster.py` with a `parent` field —
**derive from it, do not duplicate it**, so the two can never disagree. What is
new is the *concentric* geometry: which ring, which arc angle.

**Tasks**

1. `irina/backends/roster.py`:
   - `SeatSpec(role, title, ring, parent, arc_angle, model_tier, mandate)` — frozen.
   - Build the 24 `SeatSpec`s by reading `department.roster` for role/title/parent/
     mandate, and adding `ring` (0/1/2) and `arc_angle` (CFO-1 = −90°, CFO-2 = 0°,
     CFO-3 = 90°, CFO-4 = 180°; workers spread across their CFO's 88° arc).
2. Derived functions — no stored edges:
   `children(role)`, `peers(role)`, `ring(role)`, `team(role)`,
   `allowed(role) = children(role) ∪ peers(role)`.
3. Assert the counts in a test: 1 + 4 + 19 = 24; `children("ceo")` is 4;
   `peers("cfo-2")` is the other 3 CFOs; a worker's `allowed` is its own team only.

**Verification.** `python -m pytest tests/test_backends_roster.py`

**Exit criteria.** The whole graph is described by data with zero logic; the
counts and the scope rule are asserted.

**Rollback.** Delete the module and its test.

---

### Step 3 — Identity + the seat builder

**Context brief.** A "seat" is one configured waku agent. This step turns a
`SeatSpec` into a live `Waku` whose prompt, tools, model and memory are all
role-correct. Identity is not stored *inside* waku — it is pushed into four seams
waku already has.

**Tasks**

1. `irina/backends/identity.py` — `SeatIdentity(id, role, ring, parent)`, and an
   observer wrapper that stamps every event with `role`/`ring`/`parent` (so the
   graph can be rebuilt from the stream alone).
2. `irina/backends/seat.py` — `build_seat(spec, *, client, ledger, extra_tools)`:
   - `Settings(provider=…, model=…, home=Path(".irina/agents/<role>"),
     max_iterations=…, max_tokens=…)` — **constructed explicitly**, never from env;
   - write `SOUL.md` into that home from `department.prompts.role_prompt(role)`;
   - build the registry, then **filter** it to the role's toolset
     (`department.capabilities.tools_for_role` ∪ team tools), reusing the
     existing `toolsets` logic where possible;
   - wrap the surviving tools' `fn` so every side effect still passes the
     existing `Mediator` (this is the one place security survives).
3. Tests (scripted client, no spend): the home is created; the system prompt
   contains the role's mandate; the registry contains **only** allowed tool names.

**Verification.** `python -m pytest tests/test_backends_seat.py`

**Exit criteria.** `build_seat` returns a `Waku` that is provably role-correct on
all four axes — prompt, tools, model, memory — with no API call.

**Rollback.** Delete the two modules and their test.

---

### Step 4 — The delegation edge + scope + depth *(the only new mechanism)*

**Context brief.** This is the single piece waku does not have. It is also where
the user's three rules — edge, identity, scope — collapse into one mechanism:
**the tool each node receives.** Scope is a parameter of the factory; depth is a
counter; the edge exists because the tool exists.

**Tasks**

1. `irina/backends/delegate.py`:

```python
def make_delegate(parent, spec, *, build, ledger):
    allowed = roster.allowed(spec.role)              # children ∪ peers
    ring    = spec.ring
    def fn(role, task):
        if role not in allowed:  return "ERROR: out of scope"
        if ring >= MAX_RING:     return "ERROR: ring limit"
        if not ledger.affordable(): return "ERROR: budget exhausted"
        return build(role, ring + 1).respond(task).reply
    tool = Tool(name="delegate", description=…, input_schema=…, fn=fn)
    tool.spec["…"]["properties"]["role"]["enum"] = list(allowed)
    return tool
```

2. **Leaf rule:** at `ring == MAX_RING` (2) the builder **does not register the
   tool at all** — a worker has no way to recurse. Capability absent, not refused.
3. Two-way peer edges use the same factory with `allowed = peers(role)` and a
   distinct name (`consult_peer`), present only on ring 1.

**Tests — the ones that matter, and that would fail under prompt-only scope:**

- a CFO can delegate to its own team;
- a validator delegating to `model-developer` returns `"ERROR: out of scope"`;
- a worker's registry contains **no** delegate tool;
- a ring-2 node attempting a grandchild is impossible by construction.

**Verification.** `python -m pytest tests/test_backends_delegate.py`

**Exit criteria.** Scope and depth are enforced by construction, with a test that
proves a cross-team delegation is refused. This is the audit-grade property.

**Rollback.** Delete the module and its test.

---

### Step 5 — Budget ledger

**Context brief.** waku caps one node (`max_iterations`, `max_tokens`) but has no
accounting across a tree, so a department run can multiply the ceiling. This step
adds the missing whole-run bound.

**Tasks**

1. `irina/backends/ledger.py` — `Ledger(cap_tokens, cap_usd)`:
   - `observe(usage)` called from the Step-3 observer for every `assistant` event;
   - `affordable(share=None)` → whether another child may be built;
   - **composition:** a child is granted `remaining // (1 + fanout)` so a wide
     tree cannot multiply the ceiling;
   - reuses `irina/observability/pricing.py` for the dollar side.
2. Wire the one-line check into the Step-4 factory.

**Tests.** A scripted run that overspends is refused; a child's grant is ≤ the
parent's remaining share; a 5-way fan-out does not exceed the parent's grant.

**Verification.** `python -m pytest tests/test_backends_ledger.py`

**Exit criteria.** A whole-tree ceiling that actually binds under fan-out.

**Rollback.** Delete the module and its test; remove the one-line check.

---

### Step 6 — Orchestrator: build, run, parallel fan-out

**Context brief.** Join the pieces. Build the graph lazily, run the entry node,
and run siblings in parallel — which is safe **precisely because each seat owns
its own `home` and SQLite connection**. That property is the reason the per-seat
home design pays off.

**Tasks**

1. `irina/backends/graph.py`:
   - `build_department(entry="ceo", *, client, ledger) -> Seat` — construct seats
     **lazily** (24 eager `Waku`s means 24 SQLite files at start-up);
   - `run(task) -> str` — `entry.respond(task).reply`;
   - `fan_out(tasks)` — `ThreadPoolExecutor` for nodes that need several children
     at once (the five validation checks); assert it is actually parallel;
   - one observer that stamps identity, feeds the ledger, then forwards to waku's
     `Tracer`.
2. **Thread-safety check:** confirm each seat's connection is created in the
   thread that uses it (waku's dashboard needed a cross-thread injection, so this
   is the one thing to verify rather than assume).

**Tests.** Build all 24 seats offline; a scripted task flows Irina → CFO-2 →
Challenger Modeler and returns the reply; a fan-out of 5 is faster than serial
(the same wall-clock assertion waku uses in its own graph eval).

**Verification.** `python -m pytest tests/test_backends_graph.py`

**Exit criteria.** The concentric graph runs end to end against a scripted model,
with scope, depth and budget all in force.

**Rollback.** Delete the module and its test.

---

### Step 7 — Opt-in wiring + docs

**Context brief.** Ship it without changing the default. Irina's existing
`Harness` and `department` stay the default path; the waku backend is opt-in.

**Tasks**

1. A flag: `IRINA_BACKEND=waku` (env) and/or `--backend waku` (CLI), defaulting to
   the existing harness.
2. `docs/waku-backend.md` — what the backend is, the concentric graph, the four
   rules, how to install the extra, and the honest limitations (no mediation
   inside waku's tools, waku's internals unpinned, no compaction-by-summary).
3. A row in the `docs/status.md` matrix and the README Documentation table.
4. Run the full suite; confirm the default path is byte-for-byte unaffected.

**Verification**

```bash
python -m pytest tests/
IRINA_BACKEND=waku python -m irina.cli -p "tier the IFRS 9 model"   # smoke
```

**Exit criteria.** Opt-in works, default unchanged, docs shipped, all invariants
hold.

**Rollback.** Revert the flag and the docs; the backend is inert without it.

---

## Decisions needed before Step 1

| # | Decision | Recommendation |
|---|---|---|
| D1 | Pin waku by commit, or depend on PyPI `waku-agent`? | **Pin an exact version**; vendor `loop/agent.py` + `loop/models.py` if drift bites |
| D2 | Do delegated nodes use `respond()` (chat transcript) or a lean `task()`? | `respond()` for CFOs (conversational, and the transcript is the audit record); consider `task()` for workers if transcript noise hurts |
| D3 | Is the waku backend opt-in or the default? | **Opt-in** — the existing harness keeps working, and the coupling stays contained |
| D4 | Per-seat memory home, or one shared home? | **Per-seat** (`.irina/agents/<role>/`) — it is what makes parallel fan-out safe |

## Risks

| Risk | Mitigation |
|---|---|
| waku's internals drift (unversioned, "not production") | Pin exactly; keep all imports inside `irina/backends/` |
| `respond()` chat semantics wrong for workers | Decided in Step 0; add a lean `task()` if needed |
| Live API spend during development | Scripted-client injection in **every** test (waku's own eval pattern) |
| `Settings` silently reading env, giving 24 identical agents | Always construct `Settings` explicitly per seat (Step 3) |
| 24 SQLite files at start-up | Lazy seat construction (Step 6) |
| Thread-safety of SQLite under fan-out | Verify in Step 6, not assume |
| Scope enforced only by prompt | Step 4's tests: cross-team delegation must return `"out of scope"` |

## Out of scope for this plan

The security envelope, the model inventory, governance artefacts, the service
layer and the RL trajectory export are **orthogonal** to assembling the graph and
are not built here. Steps 3 and 4 only preserve the seams they will need.
