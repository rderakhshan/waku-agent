# Laminar — per-trajectory tracing and evals

`concentric/` records the department in two places, and they answer different
questions. `metrics.db` is the aggregate: one reading per seat per snapshot,
computed over the whole corpus, which is what the Observation Lab draws its
trends from. Laminar is the other half — one trace per run, with every seat,
every hand-off and every model call inside it. Neither reduces to the other, and
the trajectory index is the join between them.

**It is optional and off by default.** With `IRINA_LAMINAR` unset, or the `lmnr`
SDK missing, or no project key, every tracing call is a no-op that cannot raise —
a tracing failure must never take the seat loop down with it. The dependency
lives behind an extra, not in the core.

## Turning it on

```sh
uv sync --extra laminar
```

Then, with a Laminar instance reachable (self-hosting is a `docker compose up`;
see its own docs):

```sh
IRINA_LAMINAR=1
LMNR_PROJECT_API_KEY=<from your Laminar project settings>
LMNR_BASE_URL=http://localhost
LMNR_HTTP_PORT=8000
LMNR_GRPC_PORT=8001
```

## What maps to what

| Irina | Laminar |
|---|---|
| one trajectory (a run) | one trace |
| one seat's turn | one span, `seat.<role>`, with ring and parent |
| one `delegate` / `consult_peer` call | one `TOOL` span, `<tool>:<from>-><to>` |
| one model call | one `LLM` span — auto-instrumented, with tokens and cost |
| one chat thread | one session (`session_id`) |
| a trajectory's scores | evaluator spans in the same trace |

## Where it hooks

Two boundaries, not many:

- `Seat.respond` — a seat turn is a span. A **ring-0** seat (Irina) is never
  reached from below, so it is where a trajectory begins.
- `Department.run` — the CLI's front door; it mints the session id and passes it
  down.

The dashboard reaches Irina by calling the seat directly, so one boundary covers
both callers. `concentric.tracing.in_trajectory()` is what stops the CLI from
opening a second trace when it calls down into the seat; it is a contextvar, not
a global, because the dashboard is a threaded server.

## The trajectory index

`history.record_trajectory` writes one row per run — trace id, timestamp,
session, entry seat, seats seen, hand-offs, duration — so a run can be found from
this side without reading Laminar:

```sh
python -m concentric.history --trajectories
```

It is served at `/api/metrics/trajectories` and shown as **Recent runs** in the
Observation Lab. The row is deliberately thin: the run itself is in Laminar, and
the trace id is the only handle this side keeps.

## Evals

```sh
python -m concentric.laminar_evals            # every datapoint
python -m concentric.laminar_evals --limit 1  # one, for a smoke test
```

Laminar's evals are dataset -> executor -> evaluators, so the executor here is
the real department and each datapoint is a real run with its own trace. Every
run lands in the `irina-department` group, which is what makes two runs
comparable in the dashboard. Each datapoint is one model call; it is not free.

## What it does not do

- It does not replace `concentric/metrics.py`. The structural metrics — hand-off
  latency, delegation depth, peer pairs, mandate breaches — stay there, computed
  over the corpus for free.
- It does not deep-link to a single trace. The SDK exposes no trace URL, so the
  index stores the trace id and you search for it in Laminar.
