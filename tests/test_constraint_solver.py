"""Tests for constraints.solve_constraints — the pure solver extracted from
Model_Space._solve_constraints (decomposition slice C).

The solver mutates constrained items via each constraint's solve(), does no
rendering, and returns the conflict list only when it stalls.
"""

from __future__ import annotations

from firepro3d.constraints import solve_constraints


class _FakeConstraint:
    """Minimal stand-in for a Constraint: records solve() calls."""

    def __init__(self, result, enabled=True):
        # result: bool constant, or a list of per-call bools
        self.result = result
        self.enabled = enabled
        self.calls = []

    def solve(self, moved_item=None):
        self.calls.append(moved_item)
        if isinstance(self.result, (list, tuple)):
            idx = min(len(self.calls) - 1, len(self.result) - 1)
            return self.result[idx]
        return self.result


def test_empty_returns_empty():
    assert solve_constraints([]) == []


def test_all_satisfied_returns_empty():
    cs = [_FakeConstraint(True), _FakeConstraint(True)]
    assert solve_constraints(cs) == []
    # Solved exactly once each (converged on first iteration).
    assert all(len(c.calls) == 1 for c in cs)


def test_disabled_constraint_skipped():
    disabled = _FakeConstraint(False, enabled=False)
    assert solve_constraints([disabled]) == []
    assert disabled.calls == []  # never solved


def test_conflict_returns_unsatisfied_on_stall():
    stuck = _FakeConstraint(False)  # never satisfies, never improves
    result = solve_constraints([stuck])
    assert result == [stuck]
    # Stall detection breaks after 3 non-improving iterations (4 solve calls).
    assert len(stuck.calls) == 4


def test_convergence_after_progress_returns_empty():
    # Unsatisfied for the first two iterations, satisfied on the third.
    c = _FakeConstraint([False, False, True])
    assert solve_constraints([c]) == []
    assert len(c.calls) == 3


def test_moved_item_is_passed_through():
    sentinel = object()
    c = _FakeConstraint(True)
    solve_constraints([c], moved_item=sentinel)
    assert c.calls == [sentinel]


def test_partial_progress_then_stall_reports_only_the_stuck_one():
    # `stuck` never satisfies; `flips` satisfies once it has been solved 3×.
    # The system ends up stalled on `stuck` alone and reports it.
    stuck = _FakeConstraint(False)
    flips = _FakeConstraint([False, False, True, True, True, True, True, True])
    result = solve_constraints([stuck, flips])
    assert stuck in result
    assert flips not in result
