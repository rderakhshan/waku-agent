"""The roster as data — counts, rings, and the scope rule.

These are the assertions that make the topology provable rather than described.
If someone edits the roster and opens a cross-team edge, this goes red.
"""

from __future__ import annotations

from concentric import roster


def test_there_are_twenty_four_seats():
    assert len(roster.SEATS) == 24


def test_the_rings_are_1_4_19():
    rings = [s.ring for s in roster.SEATS]
    assert rings.count(0) == 1
    assert rings.count(1) == 4
    assert rings.count(2) == 19


def test_every_role_slug_is_unique():
    assert len(roster.BY_ROLE) == 24


def test_irina_owns_the_four_cfos():
    cfo_children = roster.children("irina")
    assert len(cfo_children) == 4
    assert all(roster.ring(r) == 1 for r in cfo_children)


def test_every_worker_reports_to_a_cfo():
    for seat in roster.SEATS:
        if seat.ring == 2:
            assert roster.ring(seat.parent) == 1


def test_cfo_peers_are_the_other_three():
    assert set(roster.peers("cfo-2-validation")) == {
        "cfo-1-development", "cfo-3-governance", "cfo-4-audit"}


def test_worker_peers_stay_inside_the_team():
    peers = roster.peers("challenger-modeler")
    assert "challenger-modeler" not in peers
    assert peers
    assert all(roster.team(p) == "cfo-2-validation" for p in peers)


def test_a_worker_can_never_reach_irina_or_another_team():
    for seat in roster.SEATS:
        if seat.ring == 2:
            reach = roster.allowed(seat.role)
            assert "irina" not in reach
            assert all(roster.team(r) == roster.team(seat.role) for r in reach)


def test_the_audit_grade_case():
    """A validator must not be able to name a development worker."""
    reach = roster.allowed("conceptual-soundness-validator")
    assert "model-developer" not in reach
    assert "cfo-1-development" not in reach


def test_irina_has_no_peers_and_no_parent():
    assert roster.peers("irina") == ()
    assert roster.BY_ROLE["irina"].parent == ""


def test_arc_angles_are_distinct_within_a_team():
    for cfo in roster.children("irina"):
        angles = [s.arc_angle for s in roster.SEATS if s.parent == cfo]
        assert len(set(angles)) == len(angles)


def test_max_ring_matches_the_deepest_seat():
    assert roster.MAX_RING == 2
    assert max(s.ring for s in roster.SEATS) == roster.MAX_RING
