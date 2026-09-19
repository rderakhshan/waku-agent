# Laminar — per-trajectory tracing and evals

`concentric/` records the department in two places, and they answer different
questions. `metrics.db` is the aggregate: one reading per seat per snapshot,
computed over the whole corpus, which is what the Observation Lab draws its
trends from. Laminar is the other half — one trace per run, with every seat,
every hand-off and every model call inside it. Neither reduces to the other, and
the trajectory index is the join between them.

## On by default

Tracing is on. A run that happened should be recorded without anyone remembering
a switch, so `IRINA_LAMINAR=off` is the only thing that stops it — and even then
the run is still indexed locally (see below). The connection values live in
`.env`, which is git-ignored:

```sh
LMNR_PROJECT_API_KEY=<from your Laminar project settings>
LMNR_BASE_URL=http://localhost
LMNR_HTTP_PORT=8000
LMNR_GRPC_PORT=8001
```

The dependency is still optional in the package sense: it sits behind the
`[laminar]` extra, not in the core.

```sh
uv sync --extra laminar
```

If the SDK is missing, the key is absent, or `Laminar.initialize()` fails, every
helper is a no-op that cannot raise. A failed init is remembered for a minute
(`tracing.RETRY_SECONDS`) so a down server costs one check a minute rather than
one per turn.

## What maps to what

| Irina | Laminar |
|---|---|
| one trajectory (a run) | one trace |
| one seat's turn | one span, `seat.<role>`, with ring and parent |
| one `delegate` / `consult_peer` call | one `TOOL` span, `<tool>:<from>-><to>` |
| one model call | one `LLM` span — auto-instrumented, with tokens and cost |
| one conversation | one session (`session_id`) |
| a trajectory's scores | evaluator spans in the same trace |

## Where it hooks

Two boundaries, not many:

- `Seat.respond` — a seat turn is a span. A **ring-0** seat (Irina) is never
  reached from below, so it is where a trajectory begins.
- `Department.run` — the CLI's front door; it passes any explicit session id
  down.

The dashboard reaches Irina by calling the seat directly, so one boundary covers
both callers. `concentric.tracing.in_trajectory()` is what stops the CLI from
opening a second trace when it calls down into the seat; it is a contextvar, not
a global, because the dashboard is a threaded server.

## Sessions

A session is waku's own conversation id (`session.session_id`) — the same id
`chat_log` groups by, so a Laminar session is the conversation the dashboard
already lists under History, not a second notion of "session". A new chat, or
the idle timeout, starts a new one, and every trajectory of that conversation
lands in it.

## The trajectory index

`history.record_trajectory` writes one row per run — trace id, timestamp,
session, entry seat, seats seen, hand-offs, duration:

```sh
python -m concentric.history --trajectories
```

It is served at `/api/metrics/trajectories` and shown as **Recent runs** in the
Observation Lab. The row is deliberately thin: the run itself is in Laminar, and
the trace id is the handle this side keeps.

## When Laminar is down

The row is written either way. A run that Laminar never saw is still a run that
happened, and losing the store must cost the detail, never the fact.

Two things to know about the outage window:

- **The spans are lost.** OpenTelemetry retries in memory, so a brief restart is
  usually absorbed, but a long outage or a process exit drops them — nothing
  spools to disk. A local spool is the upgrade path if losses matter.
- **The trace id may be phantom.** If `Laminar.initialize()` succeeded but the
  export did not, the run still gets an id, and the row keeps it; it simply will
  not resolve in Laminar. A row with no trace id at all means init itself failed
  (no SDK, no key, or `IRINA_LAMINAR=off`).

## Evals

```sh
python -m concentric.laminar_evals            # every datapoint
python -m concentric.laminar_evals --limit 1  # one, for a smoke test
```

Laminar's evals are dataset -> executor -> evaluators, so the executor here is
the real department and each datapoint is a real run with its own trace. Every
run lands in the `irina-department` group, which is what makes two runs
comparable in the dashboard. Each datapoint is one model call; it is not free.

## The embedded page

The rail's **Laminar** entry (LLMOps) embeds Laminar's own UI. It cannot be
framed as shipped: Laminar sends `X-Frame-Options: DENY` and a CSP
`frame-ancestors 'none'`, and Next.js bakes its asset paths at build time. So:

- the frontend is built with `NEXT_PUBLIC_BASE_PATH=/laminar`, which is why
  `laminar/src/docker-compose.irina.yml` points at a locally-built image:

  ```sh
  docker build --build-arg NEXT_PUBLIC_BASE_PATH=/laminar \
    -t irina-laminar-frontend:latest ./frontend
  docker compose -f docker-compose.yml -f docker-compose.irina.yml up -d
  ```

  The `ghcr.io/lmnr-ai/frontend-ee-basepath` image exists, but it is the EE build
  and its ClickHouse migrations disagree with an OSS database — it exits.

- `concentric/dashboard.py` proxies `/laminar/*` to the frontend, drops
  `X-Frame-Options`, and removes only the `frame-ancestors` directive from the
  CSP, leaving the rest intact. The body is streamed so realtime responses keep
  flowing.

- `concentric/static/laminar.js` puts the frame in a fixed panel sized to
  `#view`, not inside it: `main.js` rebuilds `#view` every five seconds, which
  would reload the iframe and lose its state each tick.

## What it does not do

- It does not replace `concentric/metrics.py`. The structural metrics — hand-off
  latency, delegation depth, peer pairs, mandate breaches — stay there, computed
  over the corpus for free.
- It does not deep-link to a single trace. The SDK exposes no trace URL, so the
  index stores the trace id and you search for it in Laminar.
