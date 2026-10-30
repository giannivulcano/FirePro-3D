"""Constraints between wall faces (design 2026-10-30) -- headless guards on
real plan ``Model_Space`` scenes: WF3 / WF4 / WF5 / WF6 units, AC1 (typed
value), AC2 (refusal), AC7 (persistence). E2e guards live in
tests/test_wall_face_placement_e2e.py and tests/test_wall_face_dims_e2e.py."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, Qt

from firepro3d import auto_constrain as ac
from firepro3d import constraint_dims as cd
from firepro3d import sketch_model as sm
from firepro3d.constraint_controller import DIM_WALL_THICKNESS_STATUS
from firepro3d.model_space import Model_Space
from firepro3d.snap_engine import OsnapResult
from firepro3d.wall import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, WallSegment


def _sc():
    sc = Model_Space()
    sc._msgs = []
    sc._show_status = lambda msg, timeout=5000: sc._msgs.append(msg)
    return sc


def _wall(sc, a, b, align=ALIGN_CENTER, thick=200.0):
    w = WallSegment(QPointF(*a), QPointF(*b), thickness_mm=thick)
    w._alignment = align
    sc.addItem(w)
    sc._walls.append(w)
    w.invalidate_geometry()
    return w


def R(it, h):
    return {"uid": it._uid, "h": h}


# -- WF4 / AC2: same-wall faces are its thickness, not a dimension ------------

def test_ac2_same_wall_faces_are_refused_as_thickness(qapp):
    sc = _sc()
    ctl = sc.constraint_ctl
    try:
        a = _wall(sc, (0, 0), (4000, 0))
        n0 = len(ctl.constraints)
        assert ctl.dim_precheck([R(a, "face_l"), R(a, "face_r")]) is None
        assert sc._msgs[-1] == DIM_WALL_THICKNESS_STATUS
        assert ctl.dim_precheck([R(a, "face_r"), R(a, "edge")]) is None     # own face vs own centerline
        assert sc._msgs[-1] == DIM_WALL_THICKNESS_STATUS
        assert ctl.add("dim_point_line", [R(a, "mid_r"), R(a, "face_l")]) is None   # the add path too
        assert sc._msgs[-1] == DIM_WALL_THICKNESS_STATUS
        assert len(ctl.constraints) == n0                                    # no record
        assert DIM_WALL_THICKNESS_STATUS == "Thickness is a wall property -- edit it in the panel"
    finally:
        sc.cleanup()


# -- WF3 / AC1: a typed face dim translates the second wall rigidly ----------

def test_wf3_translate_raws_hook():
    from firepro3d.sketch_adapters import adapter_for
    from firepro3d.geometry_2d import LineItem
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0))
    ad = adapter_for(w)
    for h in ("mid", "mid_l", "mid_r"):
        assert ad.translate_raws(w, h) == (0, 1, 2, 3), h
    assert ad.translate_raws(w, "p1") is None
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    assert adapter_for(ln).translate_raws(ln, "mid") is None     # base: least change (today)


# (B alignment, B face picked second). Center / 200 thick: face_l y = click + 100,
# face_r y = click - 100. Left: click line is face_r, face_l is 200 above it
# (derived ends). Right: click line is face_l, face_r 200 below (derived ends).
@pytest.mark.parametrize("b_align,b_face", [
    (ALIGN_CENTER, "face_r"), (ALIGN_CENTER, "face_l"),
    (ALIGN_LEFT, "face_l"), (ALIGN_RIGHT, "face_r"),
    # drawn line IS the picked face (raw ends): the _pl_apply raw path
    (ALIGN_LEFT, "face_r"), (ALIGN_RIGHT, "face_l")])
def test_ac1_typed_face_dim_moves_the_second_wall_by_the_full_delta(qapp, b_align, b_face):
    sc = _sc()
    ctl = sc.constraint_ctl
    try:
        a = _wall(sc, (0, 0), (4000, 0))                      # Center: face_l at y = +100
        b = _wall(sc, (0, 1500), (3000, 1500), align=b_align)
        qa, qb = a.quad_points(), b.quad_points()             # p1l, p1r, p2r, p2l
        y_face_b = {"face_l": qb[0].y(), "face_r": qb[1].y()}[b_face]
        clear = y_face_b - qa[0].y()                          # raw: quad corners of the two faces
        c = ctl.add(*ctl.dim_precheck([R(a, "face_l"), R(b, b_face)]))
        assert c is not None and c.type == "dim_point_line"
        assert c.refs == [R(b, cd.edge_mid_name(b_face)), R(a, "face_l")]
        assert c.value == pytest.approx(clear)
        assert ctl.set_value(c.id, clear + 250.0)
        # B translated +250 along +y (away from A), BOTH ends; length / direction kept
        assert (b._pt1.x(), b._pt1.y()) == pytest.approx((0.0, 1750.0), abs=1e-6)
        assert (b._pt2.x(), b._pt2.y()) == pytest.approx((3000.0, 1750.0), abs=1e-6)
        # A holds
        assert (a._pt1.x(), a._pt1.y(), a._pt2.x(), a._pt2.y()) == pytest.approx(
            (0.0, 0.0, 4000.0, 0.0), abs=1e-6)
        assert ctl.measure(c) == pytest.approx(clear + 250.0, abs=1e-6)
    finally:
        sc.cleanup()


def test_ac1_a_fixed_second_wall_never_moves_on_a_typed_face_dim(qapp):
    """WF3 last clause: a B held by Fix yields to today's conflict / least-change
    path -- whichever way the solve goes, the Fixed wall stays put."""
    sc = _sc()
    ctl = sc.constraint_ctl
    try:
        a = _wall(sc, (0, 0), (4000, 0))
        b = _wall(sc, (0, 1500), (3000, 1500))
        assert ctl.add("fix", [{"uid": b._uid, "h": sm.HANDLE_ITEM}]) is not None
        c = ctl.add(*ctl.dim_precheck([R(a, "face_l"), R(b, "face_r")]))
        assert c is not None and c.value == pytest.approx(1300.0)      # 1400 - 100
        ok = ctl.set_value(c.id, 1550.0)
        assert (b._pt1.x(), b._pt1.y(), b._pt2.x(), b._pt2.y()) == pytest.approx(
            (0.0, 1500.0, 3000.0, 1500.0), abs=1e-6)                 # Fixed: unmoved
        if ok:
            assert ctl.measure(c) == pytest.approx(1550.0, abs=1e-3)   # A yielded instead
        else:
            assert (a._pt1.y(), a._pt2.y()) == pytest.approx((0.0, 0.0), abs=1e-6)   # conflict: hold last good
    finally:
        sc.cleanup()
