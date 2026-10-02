"""sketch_solver — residuals, Jacobians, substitution, DOF (spec §7, §11 #1)."""
import math

import numpy as np

from firepro3d import sketch_solver as ss


def _derived_point(i0):
    """A point derived through a rotation var — forces the ROW path."""
    def fn(v):                     # v = [cx, cy, r, th]
        cx, cy, r, th = v
        p = np.array([cx + r * math.cos(th), cy - r * math.sin(th)])
        dp = np.array([[1, 0, math.cos(th), -r * math.sin(th)],
                       [0, 1, -math.sin(th), -r * math.cos(th)]], float)
        return p, dp
    return ss.PointExpr(idx=(i0, i0 + 1, i0 + 2, i0 + 3), fn=fn)


def _row_sys(x):
    s = ss.System(x=np.array(x, float))
    ss.BUILDERS["horizontal"]("h", (_derived_point(0), _derived_point(4)), s)
    return s


def test_horizontal_residual_zero_when_level_nonzero_otherwise():
    s = _row_sys([0, 0, 10, 0, 50, 0, 10, 0])
    r, _ = s.rows[0].fn(s.x)
    assert abs(r) < 1e-12
    s2 = _row_sys([0, 0, 10, 0, 50, 7, 10, 0])
    assert abs(s2.rows[0].fn(s2.x)[0] - 7.0) < 1e-12


def test_horizontal_jacobian_matches_finite_differences():
    rng = np.random.default_rng(3)
    for _ in range(20):
        x = rng.uniform(-50, 50, 8)
        s = _row_sys(x)
        row = s.rows[0]
        _, g = row.fn(s.x)
        for k, d in enumerate(row.deps):
            e = np.zeros(8); e[d] = 1e-6
            fd = (row.fn(s.x + e)[0] - row.fn(s.x - e)[0]) / 2e-6
            assert abs(fd - g[k]) < 1e-5


def test_raw_points_substitute_instead_of_adding_a_row():
    s = ss.System(x=np.array([0.0, 0.0, 100.0, 30.0]))
    ss.BUILDERS["horizontal"]("h", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    assert s.rows == [] and s.aliases == [(1, 3, "h")]


def test_point_to_origin_fixes_y():
    s = ss.System(x=np.array([5.0, 9.0]))
    ss.BUILDERS["horizontal"]("h", (ss.raw_point(0, 1), ss.const_point(0, 0)), s)
    assert s.fixes == [(1, 0.0, "h")]


def test_least_change_apply_moves_both_ends_to_mean_y():
    """D22: a tilted line made Horizontal -> both ends at the mean Y."""
    s = ss.System(x=np.array([0.0, 0.0, 100.0, 30.0]))
    ss.BUILDERS["horizontal"]("h", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(4))
    assert res.converged
    assert np.allclose(res.x, [0.0, 15.0, 100.0, 15.0])


def test_pinned_drag_moves_the_other_end():
    s = ss.System(x=np.array([0.0, 0.0, 100.0, 0.0]))
    ss.BUILDERS["horizontal"]("h", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    goals = s.x.copy(); goals[3] = 40.0
    w = np.ones(4); w[2] = w[3] = ss.W_PIN
    res = ss.NumpySolver().solve(s, goals, w)
    assert res.converged and abs(res.x[1] - 40.0) < 1e-4 and abs(res.x[3] - 40.0) < 1e-4


def _identity_derived(ix):
    """Mathematically the raw point, but routed through idx/fn -> forces a ROW."""
    return ss.PointExpr(idx=(ix, ix + 1), fn=lambda v: (np.array(v, float), np.eye(2)))


def test_row_and_substituted_forms_agree():
    """Same geometry: row form (derived identity) == alias form (raw) -> both at mean Y."""
    x = np.array([0.0, 0.0, 100.0, 6.0])
    row = ss.System(x=x.copy())
    ss.BUILDERS["horizontal"]("h", (_identity_derived(0), _identity_derived(2)), row)
    alias = ss.System(x=x.copy())
    ss.BUILDERS["horizontal"]("h", (ss.raw_point(0, 1), ss.raw_point(2, 3)), alias)
    assert len(row.rows) == 1 and alias.aliases
    r1 = ss.NumpySolver().solve(row, x.copy(), np.ones(4))
    r2 = ss.NumpySolver().solve(alias, x.copy(), np.ones(4))
    assert r1.converged and r2.converged
    assert np.allclose(r1.x, r2.x, atol=1e-6) and np.allclose(r1.x[[1, 3]], [3.0, 3.0])


def test_dof_removed_equals_catalogue():
    s = ss.System(x=np.array([0.0, 0.0, 100.0, 30.0]))
    assert ss.NumpySolver().diagnose(s).dof == 4
    ss.BUILDERS["horizontal"]("h", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    assert ss.NumpySolver().diagnose(s).dof == 3       # removes exactly 1
    s2 = _row_sys([0, 0, 10, 0, 50, 0, 10, 0])
    assert ss.NumpySolver().diagnose(s2).dof == 7       # row form removes 1 too


def test_conflicting_fixes_do_not_converge():
    s = ss.System(x=np.array([0.0, 1.0]))
    s.fixes += [(1, 0.0, "a"), (1, 5.0, "b")]
    assert not ss.NumpySolver().solve(s, s.x.copy(), np.ones(2)).converged


def test_reduced_space_uses_summed_group_weights():
    """An aliased group's goal weight is the SUM of its members' weights.

    P(0,1)-Q(2,3) via a ROW (identity-derived), Q-R via an ALIAS (y3 == y5).
    Goals y1=0 (w 1), y3=10 (w 1), y5=10 (w 3): minimise 1*a^2 + 4*(z-10)^2
    with a == z  ->  a = z = 40/5 = 8.
    """
    x = np.array([0.0, 0.0, 50.0, 10.0, 100.0, 10.0])
    s = ss.System(x=x.copy())
    ss.BUILDERS["horizontal"]("r", (_identity_derived(0), _identity_derived(2)), s)
    ss.BUILDERS["horizontal"]("a", (ss.raw_point(2, 3), ss.raw_point(4, 5)), s)
    assert len(s.rows) == 1 and s.aliases == [(3, 5, "a")]
    w = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 3.0])
    res = ss.NumpySolver().solve(s, x.copy(), w)
    assert res.converged
    assert np.allclose(res.x, [0.0, 8.0, 50.0, 8.0, 100.0, 8.0], atol=1e-9)


def test_rowless_component_lands_on_weighted_mean_goal():
    s = ss.System(x=np.array([0.0, 0.0, 100.0, 0.0]))
    ss.BUILDERS["horizontal"]("h", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    goals = np.array([1.0, 10.0, 99.0, 20.0])
    w = np.array([1.0, 1.0, 1.0, 4.0])
    res = ss.NumpySolver().solve(s, goals, w)
    assert res.converged
    assert np.allclose(res.x, [1.0, 18.0, 99.0, 18.0], atol=1e-12)


def test_inactive_component_keeps_current_values_exactly():
    """Only components holding an active variable are solved; others are untouched
    (even an unsatisfied alias) and do not affect ``converged``."""
    x = np.array([0.0, 0.0, 100.0, 30.0, 0.0, 50.0, 100.0, 50.0])
    s = ss.System(x=x.copy())
    ss.BUILDERS["horizontal"]("a", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    ss.BUILDERS["horizontal"]("b", (_identity_derived(4), _identity_derived(6)), s)
    goals = x.copy(); goals[7] = 70.0
    w = np.ones(8); w[6] = w[7] = ss.W_PIN
    res = ss.NumpySolver().solve(s, goals, w, active=[6, 7])
    assert res.converged
    assert np.array_equal(res.x[:4], x[:4])            # inactive: bit-identical
    assert abs(res.x[5] - 70.0) < 1e-4 and abs(res.x[7] - 70.0) < 1e-4


def test_failed_solve_reports_not_converged_for_unsatisfiable_row():
    """A row whose every dep is fixed cannot be satisfied -> hold-last-good signal."""
    s = ss.System(x=np.array([0.0, 0.0, 0.0, 0.0]))
    s.fixes += [(1, 0.0, "f1"), (3, 5.0, "f2")]
    ss.BUILDERS["horizontal"]("h", (_identity_derived(0), _identity_derived(2)), s)
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(4))
    assert not res.converged and abs(res.max_residual - 5.0) < 1e-12


def test_active_row_reads_fixed_value_not_stale_current():
    """A solved row that depends on a fixed (eliminated) var sees the fixed value."""
    s = ss.System(x=np.array([0.0, 5.0, 100.0, 5.0]))
    ss.BUILDERS["horizontal"]("o", (ss.raw_point(0, 1), ss.const_point(0, 0)), s)
    ss.BUILDERS["horizontal"]("r", (_identity_derived(0), _identity_derived(2)), s)
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(4), active=[2, 3])
    assert res.converged
    assert np.allclose(res.x, [0.0, 0.0, 100.0, 0.0], atol=1e-9)


def test_nonlinear_row_pinned_drag_converges_with_w_pin():
    """Rotation-derived ends (ROW path) under a W_PIN drag.

    Angle vars carry ANG_SCALE**2 goal weight (1 rad ~ 1000 mm, mirroring the
    angular row scaling of spec 7.2); with weight-1 angles the min-change
    problem is mixed-unit and the iteration can stall (see Task 3 report).
    """
    s = _row_sys([0, 0, 10, 0.3, 50, 20, 10, -0.2])
    w = np.ones(8); w[3] = w[7] = ss.ANG_SCALE ** 2
    applied = ss.NumpySolver().solve(s, s.x.copy(), w)
    assert applied.converged
    s.x = applied.x
    goals = s.x.copy(); goals[1] += 35.0
    w[0] = w[1] = ss.W_PIN
    res = ss.NumpySolver().solve(s, goals, w)
    assert res.converged and res.max_residual <= ss.LIN_TOL
    assert abs(res.x[1] - goals[1]) < 1e-3
    assert abs(res.x[3] - 0.3) < 0.01 and abs(res.x[7] + 0.2) < 0.01
