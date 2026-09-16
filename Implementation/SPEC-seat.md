# SPEC — the seat: data model and the three code mechanisms

`PLAN.md` Steps 2–4 build this. One **seat** = one configured waku agent.

---

## 1. The data model — `SeatSpec`

A frozen record per role. 24 of them. **Edges are derived, never stored.**

```python
@dataclass(frozen=True)
class SeatSpec:
    role: str          # slug, e.g. "cfo-2-validation"
    title: str         # display, e.g. "CFO-2 · Validation & monitoring"
    ring: int          # 0 = Irina, 1 = CFO, 2 = worker
    parent: str        # the role's manager ("" for Irina)
    arc_angle: float   # ring-2 placement; 0 for rings 0 and 1
    model_tier: str    # "strong" | "cheap"
    mandate: str       # one line, from the roster
```

**Source of truth.** Derive `role`, `title`, `parent` and `mandate` from the
existing `irina/department/roster.py` — **do not duplicate them**. The new module
adds only what the concentric graph needs: `ring`, `arc_angle`, `model_tier`.

### Derived functions (no stored edges)

```python
children(role)  -> tuple[str]   # direct reports
peers(role)     -> tuple[str]   # same ring, same table (CFOs: the other 3)
ring(role)      -> int
team(role)      -> str          # the CFO owning this role's arc
allowed(role)   -> tuple[str]   # children(role) + peers(role)
```

### Assertions (Step 2's tests)

- total is 24; `children("ceo")` is 4; ring 2 has 19.
- `peers("cfo-2-validation")` is the other three CFOs.
- a worker's `allowed` contains **only** its own team.
- `allowed("conceptual-soundness-validator")` does **not** contain
  `model-developer`.

---

## 2. Identity — `SeatIdentity`

waku has no identity concept. It is pushed into four seams waku already has.

```python
@dataclass(frozen=True)
class SeatIdentity:
    id: str        # stable, e.g. "cfo-2-validation" or a uuid
    role: str
    ring: int
    parent: str
```

**Where identity is materialised:**

| Purpose | Seam |
|---|---|
| which memory | `Settings.home = .irina/agents/<role>/` |
| which prompt | `<home>/SOUL.md` (read by waku's `load_soul`) |
| which tools | the filtered `ToolRegistry` |
| telemetry / graph rebuild | an observer wrapper that stamps `role`/`ring`/`parent` on every event |

The last one matters: because every event carries identity, the whole concentric
graph can be reconstructed from the event stream alone — which is also the
trajectory record the RL plan needs.

---

## 3. Mechanism A — the seat builder

```python
def build_seat(spec, *, client, ledger, extra_tools=()) -> Waku:
```

Does four things, all on waku's existing seams:

1. **Settings, constructed explicitly** — never from env (otherwise all 24 seats
   inherit the same environment and you get 24 identical agents):

   ```python
   Settings(provider=…, model=…,                 # per model_tier
            home=Path(".irina/agents") / spec.role,
            max_iterations=…, max_tokens=…)
   ```

2. **Prompt** — write `SOUL.md` into that home from
   `department.prompts.role_prompt(spec.role)`.

3. **Tools** — build waku's registry, then **filter** it to the role's toolset
   (`department.capabilities.tools_for_role` ∪ its team's tools). A tool the role
   does not own is never built, so a seat cannot exceed its remit by asking nicely.

4. **Mediation** — wrap each surviving tool's `fn` so every side effect still
   passes Irina's existing `Mediator` (path jail, secret refusal). waku's
   `ToolRegistry.execute` calls `tool.fn(**args)` unmediated, so this is the one
   place the security posture is preserved.

**Tests (scripted client, no API spend).** The home is created; the system prompt
contains the mandate; the registry contains **only** allowed tool names.

---

## 4. Mechanism B — the delegation edge

The single piece waku does not have. It is also where **edge + identity + scope
collapse into one mechanism: the tool a node receives.**

```python
def make_delegate(spec, *, build, ledger) -> Tool | None:
    allowed = allowed(spec.role)          # children ∪ peers
    ring    = spec.ring

    if ring >= MAX_RING:                  # 2
        return None                       # leaf: no tool is registered at all

    def fn(role, task):
        if role not in allowed:      return "ERROR: out of scope"
        if ring >= MAX_RING:         return "ERROR: ring limit"
        if not ledger.affordable():  return "ERROR: budget exhausted"
        return build(role, ring + 1).respond(task).reply

    tool = Tool(name="delegate", description=…, input_schema=…, fn=fn)
    tool.spec["…"]["properties"]["role"]["enum"] = list(allowed)
    return tool
```

### The three rules, in one factory

| Rule | How this factory enforces it |
|---|---|
| **Delegation edge** | the tool exists → the edge exists |
| **Scope** | `allowed` is baked in twice: as the `role` **enum** (the model cannot even name another role) and as a re-check inside `fn` |
| **Depth / ring limit** | `ring` is a counter incremented per level; at `MAX_RING` the factory returns `None` — the capability is **absent**, not refused |

### Peer edges

Same factory, different arguments: `allowed = peers(role)`, tool name
`consult_peer`, registered only on ring 1. Workers get their team peers through
the team's scope, never across arcs.

### Tests — the audit-grade ones

These are the tests that **cannot be written against prompt-only enforcement**:

- a CFO can delegate to its own team ✔
- `delegate("model-developer", …)` **from a validator** returns `"ERROR: out of scope"` ✔
- a worker's registry contains **no** delegate tool ✔
- a ring-2 node cannot obtain a grandchild ✔

---

## 5. Mechanism C — the budget ledger

waku caps one node (`max_iterations`, `max_tokens`) but has no accounting across a
tree, so a department run can multiply the ceiling.

```python
class Ledger:
    def observe(self, usage) -> None      # fed by the Step-3 observer
    def affordable(self, share=None) -> bool
    def grant(self, fanout) -> int        # remaining // (1 + fanout)
```

**Composition rule:** a child is granted `remaining // (1 + fanout)`, so a wide
tree cannot multiply the ceiling. The dollar side reuses
`irina/observability/pricing.py`.

**Tests.** An overspending scripted run is refused; a child's grant ≤ the parent's
remaining share; a 5-way fan-out stays within the parent's grant.

---

## 6. What the seat deliberately does **not** do

| Not built here | Where it belongs |
|---|---|
| the model inventory | orthogonal — `irina/store/` already exists |
| governance artefacts (approvals, waivers, findings) | orthogonal |
| the security envelope beyond the `Mediator` wrap | orthogonal |
| the service layer (RBAC, queue, Postgres) | orthogonal |
| RL trajectory export | later — the observer tags from §2 are the seam |
