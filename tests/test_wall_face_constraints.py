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
