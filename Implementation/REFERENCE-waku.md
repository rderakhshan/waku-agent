# REFERENCE — waku's seams, with the evidence

What was actually read in waku (`ShenSeanChen/waku-agent`, `main`) during the
session, and what each fact buys the plan. Read this so you do not have to re-read
the upstream repo.

---

## 1. The base class — `waku/app.py`

```python
class Waku:
    def __init__(self, settings: Settings | None = None, client=None, conn=None):
        # `client` and `conn` are injectable: evals swap in a scripted model,
        # the dashboard injects a cross-thread connection. Same seam either way.
        self.settings = settings or load_settings()
        self.settings.ensure_home()
        self.conn = conn or connect(self.settings.home)
        self.client = client or get_client(self.settings)

        self.memory  = Memory(self.conn, self.settings, self.client)
        self.tools   = build_registry(self.conn, self.settings, self.memory)
        self.session = Session(self.settings, memory=self.memory)
        self.tracer  = Tracer(self.settings)

    def respond(self, user_message, observer=None, source="cli", stream=False) -> LoopResult:
        ...
```

`app.py`'s own docstring: *"the assembly diagram in code: config → db → tools →
memory → session → loop."* That is the definition of a base harness.

**Two facts this gives the plan:**

1. **`client` is injectable** → every test in `PLAN.md` runs against a scripted
   model. No API spend, ever.
2. **`settings.home` is the state root** → per-seat memory is a path change, not a
   new subsystem. This is what makes parallel fan-out safe (each seat owns its
   connection).

## 2. Per-node configuration — `waku/config.py`

`Settings` is a plain dataclass, every field read from an env var. The fields that
matter per seat:

| Field | Default | Per-seat use |
|---|---|---|
| `provider` | `anthropic` | route by role |
| `model` | provider default | strong for CFOs, cheap for workers |
| `small_model` | provider default | the retrieval gate + consolidation |
| `home` | `.waku` | **the seat's memory root** |
| `max_iterations` | `10` | turn ceiling per node |
| `max_tokens` | `8192` | output ceiling per node |
| `history_turns` | `12` | **the context bound** |
| `experimental` | off | gates `delegate_task` |
| `graph_workflows` | off | the triage graph |

**Two consequences:**

- `Settings` fields are `default_factory=lambda: os.getenv(...)`, so a seat's
  settings **must be constructed explicitly** — otherwise 24 seats inherit one env.
- **waku does bound context**: `history_turns` is a sliding window, with older
  turns living in `state.db` and returning via the retrieval gate. That is a
  different mechanism from Irina's summarising compaction, and for a department it
  is arguably better — per-turn cost stays flat.

## 3. The tool contract — `waku/tools/registry.py`

```python
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., str]
    wants_notify: bool = False        # long tools can stream progress

class ToolRegistry:
    def register(self, tool): ...
    def schemas(self): ...
    def execute(self, name, args, notify=None) -> str:
        tool = self._tools.get(name)
        if tool is None: return f"Error: unknown tool '{name}'"
        try:
            if tool.wants_notify: return tool.fn(**args, _notify=notify or (lambda k, e: None))
            return tool.fn(**args)
        except Exception as exc: return f"Error running {name}: {exc}"
```

**Three facts:**

1. The shape is **near-identical to Irina's** `Tool(name, spec, run)` — an adapter
   is ~15 lines.
2. `self._tools` is a dict → **filtering a seat's toolset is trivial**.
3. `execute` calls `fn(**args)` **unmediated** → the `Mediator` wrap in
   `SPEC-seat.md` §3 is required, and it is the only place security is preserved.

## 4. The loop — `waku/loop/agent.py`

```python
def run_loop(client, model, system, messages, tools: ToolRegistry,
             max_iterations=10, max_tokens=2048, observer=None, stream=False) -> LoopResult
```

- ~100 lines; two guardrails (model stops, or `max_iterations`).
- **`observer(kind, event)`** — the same signature as Irina's `on_event`. Telemetry
  bridging is nearly free.
- **No `before_tool` and no `before_turn`** — no policy hook, no compaction hook.
  Policy is therefore enforced by *which tools exist* (which is exactly the
  `SPEC-seat.md` approach), and context is bounded by `history_turns`.
- `LoopResult(reply, tool_calls, iterations)` — returns **more** than Irina's loop
  (which returns a bare string).

## 5. Providers — `waku/loop/models.py`

11 providers over two wire formats, one ~60-line OpenAI-compat bridge:
`anthropic · openai · openrouter · gemini · deepseek · minimax · kimi · glm · xai ·
opencode_zen · opencode_go`.

**This is waku's biggest single win over Irina**, whose provider layer wires three
and leaves Anthropic as a placeholder. It also means `anthropic` + `openai` become
dependencies → hence the `irina[waku]` extra.

## 6. What waku already provides vs what the plan adds

| The graph needs | Native to waku | Where it goes |
|---|---|---|
| 24 independent agents | ✅ `Waku(Settings(...))` | — |
| per-node prompt / tools / model / memory | ✅ `Settings` + registry filter | `SPEC-seat.md` §3 |
| one turn per node | ✅ `respond()` | — |
| context bound | ✅ `history_turns` + retrieval gate | — |
| tracing | ✅ `Tracer` per home | — |
| **delegation edge** | ❌ | `SPEC-seat.md` §4 (~50 lines) |
| **identity** | ❌ | `SPEC-seat.md` §2 (~40 lines) |
| **scope** | ❌ | the `allowed` list on the delegate tool |
| **depth / ring limit** | ❌ | the `ring` counter; leaf = no tool |
| **roster** | ❌ | `SPEC-graph.md` (pure data) |
| **budget** | ◐ caps yes, spend no | `SPEC-seat.md` §5 (~40 lines) |
| **orchestrator** | ❌ | `PLAN.md` Step 6 (~150 lines) |

**Total new code ≈ 400 lines, none of it inside waku.**

## 7. Caveats to hold on to

| Caveat | Consequence |
|---|---|
| `respond()` is chat-turn shaped — it calls `session.add_exchange`, `maybe_consolidate`, `export_markdown` | For a worker running a one-shot task you may prefer a lean `task()` that calls `_run_full_turn` without the chat layer. **Decision D2.** |
| waku is unversioned and self-described as *"not production"* | Pin an exact version. **Decision D1.** |
| `build_registry(conn, settings, memory)` also adds MCP + memory-admin tools | Filter by name after building. |
| `Waku.__init__` calls `ensure_home()` + `connect()` | Eager construction of 24 seats creates 24 SQLite files. Build lazily. |
| waku's graph engine is deterministic, no peer messaging | Do **not** use it for this graph — it cannot express runtime selection. Build the orchestrator. |
| `ToolRegistry.execute` has no mediation | Wrap `fn` (the `Mediator`). |
