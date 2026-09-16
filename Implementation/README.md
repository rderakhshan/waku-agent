# Implementation — assembling Irina's department on waku

Everything needed to build the **concentric department** designed in this session.
Read `PLAN.md` first — it is the executable artifact. The rest are the specs and
references its steps point at.

## Objective

Assemble Irina's department — Irina (ring 0), 4 CFOs (ring 1), 19 workers
(ring 2) — using **waku's `Waku` class as the base harness**, with the graph's
rules enforced **in code, not in prompts**.

## Reading order

| # | File | What it is |
|---|---|---|
| 1 | [`PLAN.md`](PLAN.md) | the 7-step construction plan; each step is one PR and self-contained |
| 2 | [`SPEC-graph.md`](SPEC-graph.md) | the topology: rings, arcs, edge rules, and the pseudo-code prompt |
| 3 | [`SPEC-seat.md`](SPEC-seat.md) | the data model and the three code mechanisms (seat, delegation, scope) |
| 4 | [`REFERENCE-waku.md`](REFERENCE-waku.md) | waku's actual seams, with the evidence |
| 5 | [`DECISIONS.md`](DECISIONS.md) | the four decisions to settle first, the invariants, the risks |

## Status

**Nothing implemented.** `PLAN.md` sits at **Step 0 (spike)**. The four decisions
in `DECISIONS.md` are unanswered.

## Assets

| File | What |
|---|---|
| `assets/irina-concentric.png` | the target graph (2240×1810, 2× scale) |
| `assets/make_concentric.py` | regenerates it — hand-built SVG → headless Chrome screenshot |
| `assets/irina-concentric.html` | the generated SVG/HTML source |

To regenerate: `python assets/make_concentric.py`, then screenshot the HTML with
`chrome --headless=new --window-size=2240,1810 --screenshot=…`.

## Ground rules carried over from the session

1. **Prompts govern behaviour; code governs possibility.** The delegation edge,
   the identity values and the scope boundary must be code. Prompts carry the
   mandate, the delegation etiquette and the regulatory anchors.
2. **waku is never edited.** All coupling lives in `irina/backends/`.
3. **Everything is testable offline.** waku's `client` injection seam means every
   test runs against a scripted model — no API spend.
