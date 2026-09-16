"""The department as data — 24 seats, and every edge derived from them.

Edges are never stored. `children`/`peers` compute them from `parent` and
`ring`, so the topology cannot drift from the roster, and scope is a lookup
rather than a rule someone has to remember.

There is deliberately no geometry here. A `ring` is a fact about the graph
(0 = Irina, 1 = CFO, 2 = worker); how a view chooses to draw it is the view's
business. An `arc_angle` used to live on SeatSpec for a concentric picture, and
keeping it made a cosmetic change look structural — nothing that enforces scope
or depth ever read it.

The 24 roles come from Implementation/assets/make_concentric.py.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_RING = 2


@dataclass(frozen=True)
class SeatSpec:
    """One role. Identity and mandate — no behaviour, no placement."""

    role: str        # slug, e.g. "cfo-2-validation"
    title: str       # display, e.g. "CFO-2 - Validation & monitoring"
    ring: int        # 0 = Irina, 1 = CFO, 2 = worker
    parent: str      # the role's manager ("" for Irina)
    mandate: str     # one line, the seat's remit


_IRINA = (
    "irina",
    "Irina - Chief Model Risk Officer",
    ("Own the department's mandate, decide what work is done, and answer for "
     "every model-risk judgement the department makes."),
)

_TEAMS = (
    ("cfo-1-development", "CFO-1 - Development & ownership",
     ("Run model development: build, own and document the models, and keep the "
      "data feeding them fit for purpose."),
     (
         ("model-owner", "Model Owner",
          "Own each model end to end and answer for its behaviour."),
         ("model-developer", "Model Developer",
          "Implement and change models to specification."),
         ("data-steward", "Data Steward",
          "Keep the data feeding models accurate, complete and permitted."),
         ("documentation-analyst", "Documentation Analyst",
          "Write and maintain the model documentation."),
         ("mlops-engineer", "MLOps Engineer",
          "Keep models running, monitored and reproducible in production."),
     )),
    ("cfo-2-validation", "CFO-2 - Validation & monitoring",
     "Validate the models independently and watch them once they are live.",
     (
         ("conceptual-soundness-validator", "Conceptual-Soundness Validator",
          "Challenge whether a model's design is sound for its purpose."),
         ("outcomes-analyst", "Outcomes Analyst",
          "Test whether models behave as intended on real outcomes."),
         ("ongoing-monitoring-analyst", "Ongoing-Monitoring Analyst",
          "Watch live models for drift, degradation and breaches."),
         ("challenger-modeler", "Challenger Modeler",
          "Build an independent challenger and compare it with the incumbent."),
         ("data-quality-reviewer", "Data-Quality Reviewer",
          "Review the data a model depends on and report what is unfit."),
     )),
    ("cfo-3-governance", "CFO-3 - Governance & reporting",
     ("Keep the model inventory, the policy and the reporting that governance "
      "depends on."),
     (
         ("inventory-tiering-analyst", "Inventory & Tiering Analyst",
          "Keep the model inventory complete and every model correctly tiered."),
         ("policy-analyst", "Policy Analyst",
          "Maintain the model-risk policy and interpret it for the department."),
         ("model-risk-reporting-analyst", "Model-Risk Reporting Analyst",
          "Produce the model-risk reporting the committees rely on."),
         ("findings-remediation-manager", "Findings & Remediation Manager",
          "Track every finding to a closed, evidenced remediation."),
         ("committee-secretary", "Committee Secretary",
          "Run the committee papers, decisions and minutes."),
     )),
    ("cfo-4-audit", "CFO-4 - Model audit",
     "Audit the department's controls and report independently on them.",
     (
         ("audit-planner", "Audit Planner",
          "Plan the audit: scope, risk and the controls to test."),
         ("control-tester", "Control Tester",
          "Test whether a control actually operates as described."),
         ("evidence-analyst", "Evidence Analyst",
          "Gather and assess the evidence behind a control's result."),
         ("audit-report-writer", "Audit Report Writer",
          "Write the audit report, its findings and its conclusions."),
     )),
)


def _build() -> tuple[SeatSpec, ...]:
    seats = [SeatSpec(_IRINA[0], _IRINA[1], 0, "", _IRINA[2])]
    for cfo_role, cfo_title, cfo_mandate, members in _TEAMS:
        seats.append(SeatSpec(cfo_role, cfo_title, 1, "irina", cfo_mandate))
        for role, title, mandate in members:
            seats.append(SeatSpec(role, title, 2, cfo_role, mandate))
    return tuple(seats)


SEATS: tuple[SeatSpec, ...] = _build()
BY_ROLE: dict[str, SeatSpec] = {s.role: s for s in SEATS}


def spec(role: str) -> SeatSpec:
    return BY_ROLE[role]


def ring(role: str) -> int:
    return BY_ROLE[role].ring


def team(role: str) -> str:
    """The CFO owning this role's arc ("" for Irina)."""
    seat = BY_ROLE[role]
    if seat.ring == 1:
        return role
    if seat.ring == 2:
        return seat.parent
    return ""


def children(role: str) -> tuple[str, ...]:
    """Direct reports — the vertical edge, one level down."""
    return tuple(s.role for s in SEATS if s.parent == role)


def peers(role: str) -> tuple[str, ...]:
    """The other seats at the same round table — the lateral edge."""
    seat = BY_ROLE[role]
    if seat.ring == 1:
        return tuple(s.role for s in SEATS if s.ring == 1 and s.role != role)
    if seat.ring == 2:
        return tuple(s.role for s in SEATS
                     if s.ring == 2 and s.parent == seat.parent and s.role != role)
    return ()


def allowed(role: str) -> tuple[str, ...]:
    """Everything this role may reach: its own team and its own ring only."""
    return children(role) + peers(role)
