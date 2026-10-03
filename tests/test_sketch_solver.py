"""sketch_solver — residuals, Jacobians, substitution, DOF (spec §7, §11 #1)."""
import math

import numpy as np
import pytest

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


def _y_only(iy):
    """A point whose ONLY dependency is a y var (x pinned at 0) -> forces a ROW."""
    return ss.PointExpr(idx=(iy,), fn=lambda v: (np.array([0.0, v[0]]),
                                                 np.array([[0.0], [1.0]])))


def test_row_reading_a_fixed_group_touched_by_active_is_solved():
    """P6b: a fix written by this solve activates every row reading it."""
    x = np.array([0.0, 5.0, 10.0, 5.0])
    s = ss.System(x=x.copy())
    ss.BUILDERS["horizontal"]("o", (ss.raw_point(0, 1), ss.const_point(0, 0)), s)
    ss.BUILDERS["horizontal"]("r", (_y_only(1), _y_only(3)), s)
    res = ss.NumpySolver().solve(s, x.copy(), np.ones(4), active=[0, 1])
    assert res.converged
    assert abs(s.rows[0].fn(res.x)[0]) <= ss.LIN_TOL
    assert np.allclose(res.x, [0.0, 0.0, 10.0, 0.0], atol=1e-9)


def test_alias_chain_into_fixed_group_holds_the_fix():
    """y1 == y3 == y5 and y5 := 7: the whole group is fixed, even when the drag
    only touches an unrelated x var (a changed fix is a changed handle)."""
    s = ss.System(x=np.array([0.0, 1.0, 0.0, 2.0, 0.0, 3.0]))
    ss.BUILDERS["horizontal"]("ab", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    ss.BUILDERS["horizontal"]("bc", (ss.raw_point(2, 3), ss.raw_point(4, 5)), s)
    ss.BUILDERS["horizontal"]("co", (ss.raw_point(4, 5), ss.const_point(0, 7)), s)
    goals = np.array([4.0, 10.0, 0.0, 20.0, 0.0, 30.0])
    res = ss.NumpySolver().solve(s, goals, np.ones(6), active=[0])
    assert res.converged
    assert np.allclose(res.x, [4.0, 7.0, 0.0, 7.0, 0.0, 7.0])
    assert ss.NumpySolver().diagnose(s).dof == 3


def test_conflicting_fixes_through_alias_chain():
    s = ss.System(x=np.array([0.0, 1.0, 0.0, 2.0]))
    ss.BUILDERS["horizontal"]("ab", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    ss.BUILDERS["horizontal"]("ao", (ss.raw_point(0, 1), ss.const_point(0, 0)), s)
    ss.BUILDERS["horizontal"]("bo", (ss.const_point(0, 5), ss.raw_point(2, 3)), s)
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(4))
    assert not res.converged and np.array_equal(res.x, s.x)
    assert ss.NumpySolver().diagnose(s).conflicts == ["bo"]


def test_non_positive_weights_are_rejected():
    import pytest
    s = ss.System(x=np.array([0.0, 0.0]))
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            ss.NumpySolver().solve(s, s.x.copy(), np.array([1.0, bad]))


def test_structure_cache_tracks_added_constraints():
    """Solving caches the structure; adding a constraint afterwards is seen."""
    s = ss.System(x=np.array([0.0, 0.0, 100.0, 30.0]))
    first = ss.NumpySolver().solve(s, s.x.copy(), np.ones(4))
    assert np.allclose(first.x, s.x)
    ss.BUILDERS["horizontal"]("h", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(4))
    assert np.allclose(res.x, [0.0, 15.0, 100.0, 15.0])
    assert ss.NumpySolver().diagnose(s).dof == 3


def test_diagnose_sums_dof_over_components():
    s = ss.System(x=np.array([0.0, 0.0, 10.0, 3.0, 0.0, 50.0, 10.0, 60.0, 7.0, 8.0]))
    ss.BUILDERS["horizontal"]("r1", (_identity_derived(0), _identity_derived(2)), s)
    ss.BUILDERS["horizontal"]("r2", (_identity_derived(4), _identity_derived(6)), s)
    ss.BUILDERS["horizontal"]("r3", (_identity_derived(6), _identity_derived(4)), s)  # redundant
    d = ss.NumpySolver().diagnose(s)
    assert (d.nvars, d.rank, d.dof, d.conflicts) == (10, 2, 8, [])


def test_pinned_drag_off_manifold_meets_tolerance():
    """A W_PIN goal the constraints forbid: damping must not stall the residual."""
    s = ss.System(x=np.array([0.0, 0.0, 10.0, 0.0]))
    ss.BUILDERS["horizontal"]("o", (ss.raw_point(0, 1), ss.const_point(0, 0)), s)
    ss.BUILDERS["horizontal"]("r", (_y_only(1), _y_only(3)), s)
    goals = s.x.copy(); goals[3] = 9.0
    w = np.ones(4); w[3] = ss.W_PIN
    res = ss.NumpySolver().solve(s, goals, w, active=[3])
    assert res.converged and res.max_residual <= ss.LIN_TOL
    assert abs(res.x[3]) <= ss.LIN_TOL


def test_two_pinned_ends_fighting_a_row_meet_tolerance():
    s = ss.System(x=np.array([0.0, 0.0, 10.0, 0.0]))
    ss.BUILDERS["horizontal"]("r", (_y_only(1), _y_only(3)), s)
    goals = s.x.copy(); goals[3] = 9.0
    w = np.ones(4); w[1] = w[3] = ss.W_PIN
    res = ss.NumpySolver().solve(s, goals, w)
    assert res.converged and res.max_residual <= ss.LIN_TOL
    assert abs(res.x[1] - 4.5) < 1e-6 and abs(res.x[3] - 4.5) < 1e-6


def test_structure_cache_sees_in_place_fix_edit():
    s = ss.System(x=np.array([0.0, 3.0]))
    ss.BUILDERS["horizontal"]("o", (ss.raw_point(0, 1), ss.const_point(0, 0)), s)
    assert ss.NumpySolver().solve(s, s.x.copy(), np.ones(2)).x[1] == 0.0
    s.fixes[0] = (1, 5.0, "o")                 # same length, new value
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(2))
    assert res.converged and res.x[1] == 5.0


def test_structure_cache_sees_alias_swap_with_same_length():
    s = ss.System(x=np.array([0.0, 0.0, 10.0, 30.0, 20.0, 50.0]))
    ss.BUILDERS["horizontal"]("ab", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    first = ss.NumpySolver().solve(s, s.x.copy(), np.ones(6))
    assert np.allclose(first.x[[1, 3, 5]], [15.0, 15.0, 50.0])
    s.aliases.pop()
    ss.BUILDERS["horizontal"]("bc", (ss.raw_point(2, 3), ss.raw_point(4, 5)), s)
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(6))
    assert res.converged
    assert np.allclose(res.x[[1, 3, 5]], [0.0, 40.0, 40.0])


def _mixed_system(seed=5):
    """Rotation-derived rows + identity rows + aliases that put TWO entries of
    the same row into one reduced column (duplicate COO entries)."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(-20, 20, 16)
    s = ss.System(x=x)
    ss.BUILDERS["horizontal"]("a", (_derived_point(0), _derived_point(4)), s)
    ss.BUILDERS["horizontal"]("b", (_identity_derived(8), _identity_derived(10)), s)
    ss.BUILDERS["horizontal"]("c", (_identity_derived(10), _identity_derived(12)), s)
    s.aliases += [(11, 13, "al"), (2, 6, "ar")]      # rows c and a: 2 deps -> 1 col
    s.fixes.append((14, 1.0, "fx"))
    return s


def test_sparse_gram_matches_dense_jacobian_product():
    s = _mixed_system()
    st = ss._structure(s)
    x = s.x.copy(); x[st.fixed_vars] = st.fixed_vals
    rng = np.random.default_rng(1)
    dup = sum(len(c.ja) - len(set(zip(c.ja.tolist(), c.jc.tolist())))
              for c in st.comps if c.rows)
    assert dup >= 2                         # VC2: duplicate COO entries exercised
    for comp in st.comps:
        if not comp.rows:
            continue
        nr = len(comp.rows)
        winv = rng.uniform(1e-6, 2.0, comp.ncols)
        F, J = ss._eval_comp(comp, x)
        F2, v = ss._eval_vals(comp, x)
        A = np.bincount(comp.pidx, weights=v[comp.pe] * v[comp.pf] * winv[comp.pc],
                        minlength=nr * nr).reshape(nr, nr)
        assert np.allclose(A, (J * winv) @ J.T, rtol=1e-12, atol=1e-12)
        g = rng.normal(size=comp.ncols); lam = rng.normal(size=nr)
        assert np.allclose(np.bincount(comp.ja, weights=v * g[comp.jc], minlength=nr), J @ g)
        assert np.allclose(np.bincount(comp.jc, weights=v * lam[comp.ja],
                                       minlength=comp.ncols), J.T @ lam)
        assert np.array_equal(F, F2)


def test_residual_stop_reports_the_true_residual_at_the_returned_x():
    s = _row_sys([0, 0, 10, 0.3, 50, 20, 10, -0.2])
    w = np.ones(8); w[3] = w[7] = ss.ANG_SCALE ** 2; w[0] = w[1] = ss.W_PIN
    goals = s.x.copy(); goals[1] += 3.0
    res = ss.NumpySolver().solve(s, goals, w)
    true = max(abs(r.fn(res.x)[0]) for r in s.rows)
    assert res.converged and true <= ss.LIN_TOL
    assert res.max_residual == true


def test_divergent_step_reports_not_converged():
    s = ss.System(x=np.array([0.0, 0.0]))
    s.rows.append(ss.Row("nan", (0,), lambda x: (1.0, np.array([np.nan]))))
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(2))
    assert not res.converged


def test_nan_residual_with_finite_gradient_is_not_converged():
    s = ss.System(x=np.array([0.0, 0.0]))
    s.rows.append(ss.Row("nan", (0,), lambda x: (float("nan"), np.array([1.0]))))
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(2))
    assert not res.converged and np.isnan(res.max_residual)


def test_tight_component_plus_nan_component_is_not_converged():
    """A component that stops tight must not mask a NaN in another one."""
    s = ss.System(x=np.array([0.0, 0.0, 10.0, 0.0, 5.0, 5.0]))
    ss.BUILDERS["horizontal"]("ok", (_identity_derived(0), _identity_derived(2)), s)
    s.rows.append(ss.Row("nan", (4,), lambda x: (float("nan"), np.array([1.0]))))
    res = ss.NumpySolver().solve(s, s.x.copy(), np.ones(6))
    assert not res.converged and np.isnan(res.max_residual)


# ── CS2: Vertical (§7.3 pinned row, Session 2) ────────────────────────────


def _rot_point(cx_i, cy_i, t_i, r):
    """A derived point: (cx + r cos t, cy + r sin t) over vars (cx, cy, t)."""
    def fn(v):
        cx, cy, t = v
        p = np.array([cx + r * math.cos(t), cy + r * math.sin(t)])
        dp = np.array([[1.0, 0.0, -r * math.sin(t)], [0.0, 1.0, r * math.cos(t)]])
        return p, dp
    return ss.PointExpr(idx=(cx_i, cy_i, t_i), fn=fn)


def test_vertical_raw_points_alias_x():
    s = ss.System(x=np.array([0.0, 0.0, 10.0, 5.0]))
    ss.build_vertical("v", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    assert s.aliases == [(0, 2, "v")] and not s.rows and not s.fixes


def test_vertical_origin_fixes_x_to_zero():
    s = ss.System(x=np.array([7.0, 3.0]))
    ss.build_vertical("v", (ss.const_point(0.0, 0.0), ss.raw_point(0, 1)), s)
    assert s.fixes == [(0, 0.0, "v")]
    s2 = ss.System(x=np.array([7.0, 3.0]))
    ss.build_vertical("v", (ss.raw_point(0, 1), ss.const_point(0.0, 0.0)), s2)
    assert s2.fixes == [(0, 0.0, "v")]


def test_vertical_derived_row_residual_and_jacobian():
    s = ss.System(x=np.array([5.0, 2.0, 0.7, 1.0, 9.0]))
    a = _rot_point(0, 1, 2, 30.0)
    ss.build_vertical("v", (a, ss.raw_point(3, 4)), s)
    (row,) = s.rows
    r, g = row.fn(s.x)
    pa, _ = a.eval(s.x)
    assert r == pytest.approx(s.x[3] - pa[0])                    # x_b - x_a
    eps = 1e-6
    for k, d in enumerate(row.deps):                             # FD Jacobian
        xp = s.x.copy(); xp[d] += eps
        xm = s.x.copy(); xm[d] -= eps
        fd = (row.fn(xp)[0] - row.fn(xm)[0]) / (2 * eps)
        assert g[k] == pytest.approx(fd, rel=1e-6, abs=1e-6)
    s.x[3] = pa[0]                                                # satisfy it
    assert abs(row.fn(s.x)[0]) < 1e-12


def test_vertical_removes_one_dof():
    s = ss.System(x=np.array([5.0, 2.0, 0.7, 1.0, 9.0]))
    ss.build_vertical("v", (_rot_point(0, 1, 2, 30.0), ss.raw_point(3, 4)), s)
    assert ss.NumpySolver().diagnose(s).dof == 5 - 1


def test_horizontal_unchanged_after_refactor():
    s = ss.System(x=np.array([5.0, 2.0, 0.7, 1.0, 9.0]))
    ss.build_horizontal("h", (_rot_point(0, 1, 2, 30.0), ss.raw_point(3, 4)), s)
    (row,) = s.rows
    pa, _ = _rot_point(0, 1, 2, 30.0).eval(s.x)
    assert row.fn(s.x)[0] == pytest.approx(s.x[4] - pa[1])     # y_b - y_a


def test_registry_vertical_built():
    from firepro3d import sketch_model as sm
    assert sm.REGISTRY["vertical"].implemented
    assert "vertical" in ss.BUILDERS


# ── CS2 §7.4 diagnostics ────────────────────────────────────────────────────

def _diag(s):
    return ss.NumpySolver().diagnose(s)


def test_duplicate_alias_is_redundant_newer_attributed():
    s = ss.System(x=np.array([0.0, 5.0, 10.0, 5.0]))
    s.aliases += [(1, 3, "h1"), (1, 3, "h2")]
    s.cid_rank = {"h1": 0, "h2": 1}
    assert _diag(s).redundant == ["h2"]


def test_alias_order_follows_cid_rank_not_list_order():
    s = ss.System(x=np.array([0.0, 5.0, 10.0, 5.0]))
    s.aliases += [(1, 3, "late"), (3, 1, "early")]
    s.cid_rank = {"early": 0, "late": 1}
    assert _diag(s).redundant == ["late"]


def test_alias_joining_two_equal_fixes_is_redundant():
    s = ss.System(x=np.array([1.0, 0.0, 2.0, 0.0]))
    s.fixes += [(1, 0.0, "a0"), (3, 0.0, "b0")]
    s.aliases.append((1, 3, "ab"))
    s.cid_rank = {"a0": 0, "b0": 1, "ab": 2}
    assert _diag(s).redundant == ["ab"]


def test_dependent_row_is_redundant_and_rank_matches_svd():
    s = ss.System(x=np.array([5.0, 2.0, 0.0, 1.0, 2.0]))

    def row(cid, k):
        def fn(x):
            return k * x[2], np.array([k])
        return ss.Row(cid, (2,), fn)
    s.rows += [row("t1", 1.0), row("t2", 2.0)]        # same direction -> dependent
    s.cid_rank = {"t1": 0, "t2": 1}
    d = _diag(s)
    assert d.redundant == ["t2"]
    assert d.rank == 1


def test_dof_of_null_space_per_variable_group():
    # x0 free, x1 free, x2 tied to x0 by a row (x2 - x0 = 0); x3 fixed.
    s = ss.System(x=np.array([1.0, 2.0, 1.0, 0.0]))
    s.rows.append(ss.Row("r", (0, 2), lambda x: (x[2] - x[0], np.array([-1.0, 1.0]))))
    s.fixes.append((3, 0.0, "f"))
    d = _diag(s)
    assert d.dof == 2                       # (x0==x2) + x1
    assert d.dof_of([0, 2]) == 1            # the tied pair keeps one DOF
    assert d.dof_of([1]) == 1               # rowless free
    assert d.dof_of([3]) == 0               # fixed
    assert d.dof_of([0, 1, 2, 3]) == 2


def test_dof_of_rect_with_horizontal_top_keeps_four():
    def corner(su, sv):
        def fn(v):
            cx, cy, w, h, t = v
            u, vv = su * w / 2, sv * h / 2
            c, s_ = math.cos(t), math.sin(t)
            p = np.array([cx + u * c - vv * s_, cy + u * s_ + vv * c])
            dp = np.array([[1, 0, su / 2 * c, -sv / 2 * s_, -u * s_ - vv * c],
                           [0, 1, su / 2 * s_, sv / 2 * c, u * c - vv * s_]], float)
            return p, dp
        return ss.PointExpr(idx=(0, 1, 2, 3, 4), fn=fn)
    s = ss.System(x=np.array([0.0, 0.0, 100.0, 50.0, 0.0]))
    ss.build_horizontal("h", (corner(-1, -1), corner(1, -1)), s)
    d = _diag(s)
    assert d.dof == 4 and d.dof_of(range(5)) == 4


def test_non_redundant_constraints_are_not_flagged():
    s = ss.System(x=np.array([0.0, 5.0, 10.0, 5.0]))
    ss.build_horizontal("h", (ss.raw_point(0, 1), ss.raw_point(2, 3)), s)
    ss.build_vertical("v", (ss.raw_point(0, 1), ss.const_point(0.0, 0.0)), s)
    s.cid_rank = {"h": 0, "v": 1}
    assert _diag(s).redundant == []


def test_dependent_rows_count_reconciles_with_svd_rank():
    """CS2 review m2: a near-singular J whose relative GS test would flag a
    different count than the SVD rank defers to the rank."""
    J = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 5e-9, 0.0]])
    assert int(ss._dependent_rows(J, ndep=1).sum()) == 1
    assert ss._dependent_rows(J, ndep=1)[1]          # the exact duplicate


# ── D18 perf: scoped single-thread BLAS ────────────────────────────────────

def test_one_blas_thread_scopes_nests_and_restores():
    api = ss._blas_api()
    if not api:
        with ss.one_blas_thread():          # unavailable: a no-op, never raises
            pass
        pytest.skip("no OpenBLAS thread API in this numpy build")
    get, set_ = api
    before = get()
    set_(3)
    try:
        with ss.one_blas_thread():
            assert get() == 1
            with ss.one_blas_thread():      # nested: no early restore
                assert get() == 1
            assert get() == 1
        assert get() == 3
    finally:
        set_(before)


def test_solve_and_diagnose_run_single_threaded():
    api = ss._blas_api()
    if not api:
        pytest.skip("no OpenBLAS thread API in this numpy build")
    get, set_ = api
    seen = []

    def fn(x):
        seen.append(get())
        return float(x[1] - x[0]), np.array([-1.0, 1.0])
    s = ss.System(x=np.array([0.0, 2.0]))
    s.rows.append(ss.Row("r", (0, 1), fn))
    before = get()
    set_(4)
    try:
        ss.NumpySolver().solve(s, s.x.copy(), np.ones(2))
        ss.NumpySolver().diagnose(s)
        assert get() == 4
    finally:
        set_(before)
    assert seen and set(seen) == {1}


# ── D18 perf: batched rows == per-row fn ───────────────────────────────────

def _per_row(comp, x):
    F, gs = [], []
    for row in comp.rows:
        r, g = row.fn(x)
        F.append(r)
        gs.append(np.asarray(g, dtype=float))
    v = np.concatenate(gs)
    return np.array(F), (v if comp.jmask is None else v[comp.jmask])


def test_batched_rows_equal_per_row_fn_rect_heavy(qapp):
    from tests.test_d18_parity import _rect_heavy
    sc, n = _rect_heavy()
    try:
        sys_, _s, _w = sc.constraint_ctl._build(sc.constraint_ctl.active())
        st = ss._structure(sys_)
        rng = np.random.default_rng(7)
        x = sys_.x + rng.normal(0, 0.01, len(sys_.x))      # off the manifold, tilted rects
        x[st.fixed_vars] = st.fixed_vals
        for comp in st.comps:
            if not comp.rows:
                continue
            F0, v0 = _per_row(comp, x)
            F1, v1 = ss._eval_vals(comp, x)
            assert comp.batch is not None and comp.batch.groups      # really batched
            assert np.allclose(F1, F0, rtol=0, atol=1e-12)
            assert np.allclose(v1, v0, rtol=0, atol=1e-12)
    finally:
        sc.cleanup()


def test_batched_rows_equal_per_row_fn_mixed(qapp):
    """Generic fallback (arc / polygon rows), const ends (origin) and raw +
    rect batch rows in one component."""
    from tests.test_d18_parity import _mixed
    sc, n = _mixed()
    try:
        sys_, _s, _w = sc.constraint_ctl._build(sc.constraint_ctl.active())
        st = ss._structure(sys_)
        x = np.array(sys_.x)
        x[st.fixed_vars] = st.fixed_vals
        kinds = set()
        for comp in st.comps:
            if not comp.rows:
                continue
            F0, v0 = _per_row(comp, x)
            F1, v1 = ss._eval_vals(comp, x)
            kinds |= {"generic"} if comp.batch.generic else set()
            kinds |= {"batched"} if comp.batch.groups else set()
            assert np.allclose(F1, F0, rtol=0, atol=1e-12)
            assert np.allclose(v1, v0, rtol=0, atol=1e-12)
        assert kinds == {"generic", "batched"}                      # VC2: both paths ran
    finally:
        sc.cleanup()


def test_shared_deps_row_batches_like_fn():
    """A Horizontal on a rect EDGE: both ends read the same 5 vars (deduped deps)."""
    from firepro3d.sketch_adapters import _RECT_LOCAL, _rect_point_fn
    pa = ss.PointExpr(idx=(0, 1, 2, 3, 4), fn=_rect_point_fn(*_RECT_LOCAL["tl"]),
                      fam=("rect", _RECT_LOCAL["tl"]))
    pb = ss.PointExpr(idx=(0, 1, 2, 3, 4), fn=_rect_point_fn(*_RECT_LOCAL["tr"]),
                      fam=("rect", _RECT_LOCAL["tr"]))
    s = ss.System(x=np.array([10.0, 20.0, 50.0, 30.0, 0.3]))
    ss.build_horizontal("h", (pa, pb), s)
    st = ss._structure(s)
    comp = st.comps[0]
    F0, v0 = _per_row(comp, s.x)
    F1, v1 = ss._eval_vals(comp, s.x)
    assert comp.batch.groups and not comp.batch.generic
    assert np.allclose(F1, F0, atol=1e-12) and np.allclose(v1, v0, atol=1e-12)


# ── D18 perf: certified full-rank diagnostics == the SVD path ──────────────

def _diag_both(s):
    """(fast, svd) Diagnostics for *s* (svd forced via CERT_RATIO=inf)."""
    fast = ss.NumpySolver().diagnose(s)
    old = ss.CERT_RATIO
    ss.CERT_RATIO = float("inf")
    try:
        slow = ss.NumpySolver().diagnose(s)
    finally:
        ss.CERT_RATIO = old
    return fast, slow


def _same_diag(fast, slow, groups):
    assert (fast.rank, fast.dof, fast.conflicts, fast.redundant) == (
        slow.rank, slow.dof, slow.conflicts, slow.redundant)
    assert fast.dof_of_many(groups) == [slow.dof_of(g) for g in groups]


def test_fast_diagnostics_equal_svd_on_rect_heavy(qapp):
    from tests.test_d18_parity import _rect_heavy
    sc, n = _rect_heavy()
    try:
        ctl = sc.constraint_ctl
        sys_, slots, _w = ctl._build(ctl.active())
        sys_.cid_rank = {c.id: k for k, c in enumerate(ctl.active())}
        groups = [list(range(off, off + ad.nvars(it))) for _u, (it, ad, off) in slots.items()]
        fast, slow = _diag_both(sys_)
        big = max(range(len(fast._st.comps)), key=lambda c: len(fast._st.comps[c].rows))
        assert big in fast._fast                                # VC2: the certified path ran
        assert not slow._fast
        _same_diag(fast, slow, groups)
    finally:
        sc.cleanup()


def test_rank_deficient_component_falls_back_to_svd():
    """Two identical rows: no certificate -> SVD + Gram-Schmidt, same answer."""
    s = ss.System(x=np.array([0.0, 1.0, 2.0]))
    for cid in ("a", "b"):
        s.rows.append(ss.Row(cid, (0, 1), lambda x: (x[1] - x[0] - 1.0, np.array([-1.0, 1.0]))))
    s.cid_rank = {"a": 0, "b": 1}
    fast, slow = _diag_both(s)
    assert not fast._fast
    assert fast.redundant == ["b"]
    _same_diag(fast, slow, [[0, 1], [2], [0, 1, 2]])


def test_ill_conditioned_component_falls_back_to_svd():
    """cond(J) ~ 1e5 > the 1e3 certificate bound -> SVD path, same answer."""
    s = ss.System(x=np.array([0.0, 0.0, 0.0]))
    s.rows.append(ss.Row("a", (0, 1), lambda x: (x[0] + x[1], np.array([1.0, 1.0]))))
    s.rows.append(ss.Row("b", (0, 1), lambda x: (x[0] + (1 + 1e-5) * x[1],
                                                  np.array([1.0, 1.0 + 1e-5]))))
    fast, slow = _diag_both(s)
    assert not fast._fast and fast.rank == 2
    _same_diag(fast, slow, [[0], [1], [0, 1], [2]])
