# SPEC — the concentric graph

The topology being assembled. This is the specification `PLAN.md` builds to; the
rendered target is `assets/irina-concentric.png`.

---

## 1. Rings and placement

Three concentric circles around a common centre.

| Ring | Holds | Count | Placement |
|---|---|---|---|
| 0 | Irina (CEO) | 1 | at the centre |
| 1 | the four CFOs | 4 | `centre + polar(R1, cfo.angle)` |
| 2 | the workers | 19 | `centre + polar(R2, cfo.angle − arc/2 + step·(i + 0.5))` |

**Constants used in the sketch**

```
centre   = (820, 900)
R1       = 330          # the CFO ring
R2       = 640          # the worker ring
arc      = 88°          # the slice of ring 2 owned by one team
step     = arc / count(team)
angles   = CFO-1: −90°  CFO-2: 0°  CFO-3: 90°  CFO-4: 180°
```

Each CFO owns a contiguous **arc** of ring 2. That contiguity is what makes "same
team only" a property of the geometry rather than a runtime check.

## 2. Nodes

Every node — Irina, each CFO, each worker — is **one configured waku agent**
(`Waku(Settings(...))` + a filtered `ToolRegistry`). See `SPEC-seat.md`.

| Node | Prompt | Tools | Model | Memory |
|---|---|---|---|---|
| Irina | CEO mandate | `delegate` (4 CFOs) | strong | `.irina/agents/ceo/` |
| CFO-n | pillar mandate | `delegate` (its 5 workers) + `consult_peer` (the other 3 CFOs) | strong | `.irina/agents/cfo-n/` |
| worker | role mandate | its role tool + team tools — **no delegate tool** | cheap | `.irina/agents/<role>/` |

## 3. Edge rules

| Edge | Kind | Direction | Where enforced |
|---|---|---|---|
| Irina ↔ CFO | vertical, one level | both | `delegate` tool on Irina |
| worker ↔ its CFO | vertical, one level | both | `delegate` tool on the CFO |
| CFO ↔ CFO | lateral, ring 1 | both | `consult_peer` tool, `allowed = peers()` |
| worker ↔ worker | lateral, ring 2, **same arc only** | both | the team's `delegate`/peer scope |
| worker ↔ other team's worker | **forbidden** | — | absent from every toolset |
| worker ↔ other CFO | **forbidden** | — | absent from every toolset |
| worker ↔ Irina | **forbidden** (no skip-level) | — | absent from every toolset |

**The rule in one line:** vertical edges go exactly one level; lateral edges exist
only inside a round table — ring 1 for the CFOs, and one per team on ring 2.

## 4. The three prohibitions, made concrete

1. **No skip-level** — a worker cannot message Irina. Its registry has no tool
   whose `allowed` list contains `ceo`.
2. **No cross-team** — a validation worker cannot reach a development worker. Its
   `allowed` list is its own team only; the call returns `ERROR: out of scope`.
3. **No worker-to-worker across CFOs** — the relay path is
   `worker → its CFO → the other CFO → that team's worker`, drawn in red on the
   sketch.

## 5. Depiction (ASCII)

```
                         ┌───────────────────────────────┐
        ring 2  ───────► │   workers, one arc per team   │
                         │   ┌───────────────────────┐   │
        ring 1  ───────► │   │   the four CFOs       │   │
                         │   │   ┌───────────────┐   │   │
        ring 0  ───────► │   │   │    Irina      │   │   │
                         │   │   └───────────────┘   │   │
                         │   └───────────────────────┘   │
                         └───────────────────────────────┘

  radial line   = vertical, one level   (worker→its CFO, CFO→Irina)
  ring 1 dashed = the CFO round table   (peer ↔ peer)
  ring 2 arc    = a team's round table  (peer ↔ peer, inside the arc)
  red dashed    = a relayed cross-team message (worker → CFO → CFO → worker)
```

## 6. The prompt (pseudo-code)

This is the spec in generative form — usable to re-render the figure with any
tool, or as the design brief for the assembler.

```text
PROMPT — "Irina's Department as three concentric round tables"
──────────────────────────────────────────────────────────────
CANVAS  2240 x 1810, light background, navy header
STYLE   flat vector, corporate
        navy #0A1B3A · blue #1E4E8C · edge #2E6DB4
        peer amber #B36B00 · relay red #B02A2A

DATA
  CEO   = { name: "Irina", title: "Chief Model Risk Officer", depth: 0 }
  CFOs  = [ {id, title, angle}, ... ]        # 4 roles, depth 1
  TEAM  = { cfo_id: [worker, ...] }          # 19 workers, depth 2

LAYOUT   (concentric — no rectangles, no tree)
  centre = canvas_centre
  place CEO at centre
  for cfo in CFOs:
      cfo.pos = centre + polar(R1, cfo.angle)          # R1 = inner ring
  for cfo in CFOs:
      arc  = 88°  centred on cfo.angle
      step = arc / count(TEAM[cfo])
      for i, w in enumerate(TEAM[cfo]):
          w.pos   = centre + polar(R2, cfo.angle - arc/2 + step*(i + 0.5))
          w.owner = cfo                                 # R2 = outer ring

DRAW RINGS
  circle(R2, light solid)                          # outer boundary
  circle(R1, amber dashed)                         # the CFO round table
  for cfo in CFOs: arc(R2, cfo.arc, amber dashed)  # each team's own table

DRAW EDGES
  for cfo in CFOs: two_way(CEO, cfo)                    # ↓ assign  ↑ report
  for cfo in CFOs: for w in TEAM[cfo]: line(w, cfo)     # one level, worker→its CFO
  for cfo in CFOs: peer_tick(R1, between_adjacent_cfos) # CFO ↔ CFO

FORBIDDEN   (assert: never emitted as edges)
  worker ↔ worker   when  worker.owner != other.owner
  worker ↔ other cfo
  worker ↔ CEO

HIGHLIGHT   (one example, so the rule is visible)
  path = worker(cfo-2) → cfo-2 → arc(R1) → cfo-1 → worker(cfo-1)
  draw red dashed, label "cross-team"

NODE LABELS
  CEO    : "Irina · CEO · depth 0"
  CFO    : "<title> · depth 1 · peers with the other 3 CFOs"
  worker : "<role name>"
  ring   : "ROUND TABLE · DEPTH 1"
  arc    : "ROUND TABLE · DEPTH 2 · N workers"

SIDE PANEL
  print this same pseudo-code as text, so the figure documents itself
LEGEND
  blue two-way  = vertical, one level (assign ↓ / report ↑)
  soft line     = worker ↔ its own CFO
  amber dashed  = peer — inside one round table only
  red dashed    = a relayed cross-team message (worker → CFO → CFO → worker)
```

## 7. Counts

```
ring 0   1
ring 1   4          (Development · Validation · Governance · Audit)
ring 2   5 + 5 + 5 + 4 = 19
total    24

vertical edges   4 (Irina↔CFO) + 19 (worker↔CFO) = 23
lateral edges    4 (CFO ring, adjacent) + within-arc worker peers
```
