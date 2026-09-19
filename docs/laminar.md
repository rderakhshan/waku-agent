# Laminar — per-trajectory tracing and evals

`concentric/` records the department in two places, and they answer different
questions. `metrics.db` is the aggregate: one reading per seat per snapshot,
computed over the whole corpus, which is what the Observation Lab draws its
trends from. Laminar is the other half — one trace per run, with every seat,
every hand-off and every model call inside it. Neither reduces to the other, and
the trajectory index is the join between them.

## Setup

Tracing is on. A run that happened should be recorded without anyone remembering
a switch, so `IRINA_LAMINAR=off` is the only thing that stops it — and even then
the run is still indexed locally (see below).

**1. Run Laminar locally.** Five containers — frontend, app-server, Postgres,
ClickHouse, Quickwit:

```bash
git clone https://github.com/lmnr-ai/lmnr && cd lmnr
docker compose up -d          # the UI lands at http://localhost:5667
```

**2. Serve it under `/laminar`.** Irina embeds the UI in a rail page, and
Laminar refuses to be framed (`X-Frame-Options: DENY`), so the launcher proxies
it and strips exactly those headers. Next bakes its asset paths in at build
time, so the frontend has to be built with a base path:

```bash
docker build --build-arg NEXT_PUBLIC_BASE_PATH=/laminar \
  -t irina-laminar-frontend:latest ./frontend

cat > docker-compose.irina.yml <<'YAML'
services:
  frontend:
    image: irina-laminar-frontend:latest
    pull_policy: never
YAML

docker compose -f docker-compose.yml -f docker-compose.irina.yml up -d
```

The published `ghcr.io/lmnr-ai/frontend-ee-basepath` image is the same idea, but
it is the EE build and its ClickHouse migrations disagree with an OSS database,
so it exits on startup. Building the OSS frontend keeps one schema.

**3. Create a project, then give Irina its key.** Open
<http://localhost:5667/laminar> and sign in with any email — self-hosted Laminar
lets anyone in by default. Create a project, copy the API key from **Project
settings**, then:

```sh
uv sync --extra laminar
```

and put the key in `.env` (git-ignored):

```sh
LMNR_PROJECT_API_KEY=<the key you copied>
LMNR_BASE_URL=http://localhost
LMNR_HTTP_PORT=8000
LMNR_GRPC_PORT=8001
```

That is the whole setup. From then on every run is traced, and each conversation
becomes one Laminar **session** — `session.session_id`, the same id the chat log
already groups by.

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
session, entry seat, seats seen, hand-offs, duration, and now the ask, the answer
and any rules the run broke:

```sh
python -m concentric.history --trajectories
```

It is served at `/api/metrics/trajectories` and shown as **Recent runs** in the
Observation Lab.

The ask and the answer are kept because a run that went wrong has to be
re-runnable — a verdict without the case is not much use. The violations are
computed as the run finishes, from the same events, so a bad run is flagged
locally and immediately, with Laminar up or down. `history.failures()` reads them
back, which is what `--from-failures` runs on.

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
python -m concentric.laminar_evals                  # every datapoint
python -m concentric.laminar_evals --limit 1        # one, as a smoke test
python -m concentric.laminar_evals --from-failures  # the runs that broke a rule
```

Laminar's evals are dataset -> executor -> evaluators, so the executor here is
the real department and each datapoint is a real run with its own trace. Every
run lands in the `irina-department` group. The model goes in the run's *name*,
not the group, so two models still land side by side where they can be compared.

There are two kinds of score here, and they are not the same kind of thing:

- **The graph rules** — `in_scope`, `depth_respected`, `handoffs_answered`,
  `no_repeated_step`. Exact and free: the roster says who may task whom and how
  deep, and the run's own events say what it did. This is the half a judge cannot
  do, because a judge does not know the org chart. The rules themselves live in
  `concentric/graph_rules.py`, and a test fails if one is added there without a
  score here.
- **Irina's judge numbers**, reported rather than recomputed. The registry is the
  calculator; the evaluator is only a delivery slot, because Laminar's Evals tab
  shows nothing that did not come out of an evaluator. `judge_ids()` selects them
  and a test fails if that selection ever comes back empty.

`--from-failures` re-runs the runs whose recorded violations are non-empty: a fix
is only proven by the run that used to fail.

Each datapoint is one model call, so it is not free; `--from-failures` costs
whatever its recorded tasks cost to run again.

## The embedded page

The rail's **Trace and Eval** entry (LLMOps) embeds Laminar's own UI. It cannot be
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
