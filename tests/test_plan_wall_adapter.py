"""Editor/Build slice 2 Task 3: the wall adapter (ruling W1).

Handle positions are checked against the wall's OWN geometry
(quad_points / centerline_pt*), never the adapter's output; solves run
through the controller seams the grip handle uses (manip_handle.py
on_press / on_drag / on_release: begin_drag, apply_grip, drag, end_drag).
"""
from __future__ import annotations

import gc
import math

import numpy as np
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.sketch_adapters import adapter_for
from firepro3d.wall import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, WallSegment


@pytest.fixture
def plan(qapp):
    sc = Model_Space()
    yield sc
    sc.cleanup()
    gc.collect()      # finalise the scene (and its walls) now, not inside a later test


def _wall(sc, a, b, align=ALIGN_CENTER, thick=200.0):
    w = WallSegment(QPointF(*a), QPointF(*b), thickness_mm=thick)
    w._alignment = align
    sc.addItem(w)
    sc._walls.append(w)
    w.invalidate_geometry()
    return w


def _xy(p):
    return (p.x(), p.y())


def _eval(e, x):
    return tuple(float(c) for c in e.eval(np.asarray(x, dtype=float))[0])


@pytest.mark.parametrize("align", [ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT])
def test_handles_match_the_wall_geometry(plan, align):
    w = _wall(plan, (0, 0), (3000, 1000), align)
    ad = adapter_for(w)
    x = ad.read(w)
    assert x == [w._pt1.x(), w._pt1.y(), w._pt2.x(), w._pt2.y()]
    pts = ad.points(w, 0)
    q = w.quad_points()                        # p1l, p1r, p2r, p2l
    want = {"p1": _xy(w.centerline_pt1), "p2": _xy(w.centerline_pt2),
            "mid": _xy(w.centerline_midpoint()),
            "p1l": _xy(q[0]), "p1r": _xy(q[1]), "p2r": _xy(q[2]), "p2l": _xy(q[3])}
    assert set(pts) == set(want)
    for name, xy in want.items():
        assert _eval(pts[name], x) == pytest.approx(xy, abs=1e-9), name
    assert set(ad.edges(w, 0)) == {"edge", "face_l", "face_r", "end1", "end2"}


@pytest.mark.parametrize("align", [ALIGN_LEFT, ALIGN_RIGHT])
def test_derived_handle_jacobians_match_finite_differences(plan, align):
    w = _wall(plan, (100, -50), (2500, 1300), align)
    ad = adapter_for(w)
    x = np.array(ad.read(w), dtype=float)
    h = 1e-6
    for name, e in ad.points(w, 0).items():
        if e.raw is not None:
            continue
        sub = x[list(e.deps)]
        _p, dp = e.fn(sub)
        for j in range(len(sub)):
            a, b = sub.copy(), sub.copy()
            a[j] -= h
            b[j] += h
            num = (e.fn(b)[0] - e.fn(a)[0]) / (2 * h)
            assert np.allclose(dp[:, j], num, atol=1e-5), (name, j)


def _grip_drag(sc, w, index, to):
    """The grip handle's controller seam (manip_handle.py 272 / 287 / 349)."""
    ctl = sc.constraint_ctl
    ctl.begin_drag(w)
    w.apply_grip(index, QPointF(*to))
    ctl.drag(w, index)
    ctl.end_drag()


def _len(w):
    return math.hypot(w._pt2.x() - w._pt1.x(), w._pt2.y() - w._pt1.y())


@pytest.mark.parametrize("align", [ALIGN_CENTER, ALIGN_LEFT])
def test_smart_dim_wall_length_holds_on_an_end_drag(plan, align):
    """T4 (wall half, unit level; the shown-view e2e is Task 6). The grabbed
    drawn-line end is honoured (pinned at W_PIN) and the far end moves to
    hold the length -- for a Left wall too, whose ``p2`` handle is derived
    (pin_vars maps grip 1 to the raw vars 2, 3)."""
    w = _wall(plan, (0, 0), (3000, 0), align)
    c = plan.constraint_ctl.add("dim_distance", [{"uid": w._uid, "h": "edge"}])
    assert c is not None and c.value == pytest.approx(3000.0)
    _grip_drag(plan, w, 1, (3000, 2000))             # unconstrained: length 3606
    assert _len(w) == pytest.approx(3000.0, abs=1e-6)
    # soft pin at W_PIN = 1e6 (sketch_solver.py:25): residual ~ correction / W_PIN = ~606 mm / 1e6 = ~6e-4 mm
    assert _xy(w._pt2) == pytest.approx((3000.0, 2000.0), abs=1e-2)


def test_left_wall_drawn_face_stays_on_a_thickness_change(plan):
    """W1 preview: a Left wall's drawn line is its right face (quad p1r /
    p2r, wall.quad_points docstring); thickening it moves the left face only,
    and the adapter's p1l handle follows the new body corner."""
    w = _wall(plan, (0, 0), (3000, 0), ALIGN_LEFT)
    q0 = w.quad_points()
    before = [_xy(q0[0]), _xy(q0[3])]           # left face ends (+normal side)
    w.apply_grip(3, QPointF(1500, 400))         # width grip: thickness only
    q1 = w.quad_points()
    assert [_xy(q1[1]), _xy(q1[2])] == pytest.approx([(0, 0), (3000, 0)])
    assert [_xy(q1[0]), _xy(q1[3])] != pytest.approx(before)
    pts = adapter_for(w).points(w, 0)
    x = adapter_for(w).read(w)
    assert _eval(pts["p1l"], x) == pytest.approx(_xy(q1[0]), abs=1e-9)


def test_zero_length_solve_is_refused(plan):
    """D29: a dim edit that would shrink the wall to zero length collapses."""
    w = _wall(plan, (0, 0), (3000, 0))
    c = plan.constraint_ctl.add("dim_distance", [{"uid": w._uid, "h": "edge"}])
    before = (_xy(w._pt1), _xy(w._pt2))
    assert plan.constraint_ctl.set_value(c.id, 0.0) is False
    assert (_xy(w._pt1), _xy(w._pt2)) == before


def test_solver_write_rebuilds_the_outline(plan):
    """design s2: write-back sets both ends then invalidate_geometry() (the
    cached outline the paint path reads follows the solved centerline)."""
    w = _wall(plan, (0, 0), (3000, 0))
    c = plan.constraint_ctl.add("dim_distance", [{"uid": w._uid, "h": "edge"}])
    assert plan.constraint_ctl.set_value(c.id, 4000.0) is True
    assert _len(w) == pytest.approx(4000.0, abs=1e-6)
    # the painted path is set by the rebuild; outline_geometry() would self-heal, so read it first
    assert w.path().boundingRect().width() == pytest.approx(4000.0, abs=1.0)
    body = w.outline_geometry().body          # WallOutline.body: the paint fill polygon
    xs = [body.at(i).x() for i in range(body.count())]
    assert xs and max(xs) - min(xs) == pytest.approx(4000.0, abs=1.0)
