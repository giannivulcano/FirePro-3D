"""Slice 8 guards — editing a periodic spline keeps it periodic (DD7).

Grip drag runs through the real Model_View -> SelectionManipulator path;
undo through Model_Space.undo(); transforms through the per-item protocol
(manip_rotate / translate, and Slice 3's manip_reflect / manip_scale_about).
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import SplineItem
from tests._snap_polish_helpers import close_view, drag, make_view

SQ = [(-400, -400), (400, -400), (400, 400), (-400, 400)]


def _seam_ok(path):
    p0, p1 = path.pointAtPercent(0.0), path.pointAtPercent(1.0)
    a, b = path.pointAtPercent(1e-4), path.pointAtPercent(1.0 - 1e-4)
    t_out = (a.x() - p0.x(), a.y() - p0.y())
    t_in = (p1.x() - b.x(), p1.y() - b.y())
    c = ((t_out[0] * t_in[0] + t_out[1] * t_in[1])
         / (math.hypot(*t_out) * math.hypot(*t_in)))
    turn = math.degrees(math.acos(max(-1.0, min(1.0, c))))
    return math.hypot(p1.x() - p0.x(), p1.y() - p0.y()) < 1e-6 and turn < 0.5


def test_grip_drag_keeps_it_closed_and_undo_restores(qapp):
    view, scene = make_view()                       # block_editor, m11 = 0.25
    try:
        s = SplineItem([QPointF(x, y) for x, y in SQ], closed=True)
        scene.addItem(s)
        scene._draw_splines.append(s)
        scene.push_undo_state()
        scene.clearSelection()
        s.setSelected(True)
        p0 = scene._undo_pos
        drag(view, QPointF(400, -400), QPointF(700, -600))   # control point 1
        cps = s.grip_points()
        assert len(cps) == 4                          # one grip per CP, no seam pair
        assert math.hypot(cps[1].x() - 700, cps[1].y() + 600) < 1.0
        assert cps[0] == QPointF(-400, -400)          # the seam neighbour stayed put
        assert s.is_periodic() and _seam_ok(s.path())
        assert scene._undo_pos == p0 + 1              # one undo step
        scene.undo()
        r = scene._draw_splines[0]                    # restore rebuilds items
        assert r.is_periodic()
        assert r.grip_points()[1] == QPointF(400, -400)
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("op", ["rotate", "translate", "reflect", "scale"])
def test_transforms_keep_the_periodic_flag(qapp, op):
    s = SplineItem([QPointF(x, y) for x, y in SQ], closed=True)
    before = [QPointF(p) for p in s.grip_points()]
    if op == "rotate":
        s.manip_rotate(30.0, QPointF(0, 0))
    elif op == "translate":
        s.translate(100.0, -50.0)
    elif op == "reflect":                    # Slice 3 (Part B) — named, not defined here
        s.manip_reflect(QPointF(1000, 0), QPointF(1000, 100))   # axis x = 1000
        got = [c for p in s.grip_points() for c in (p.x(), p.y())]
        want = [c for p in before for c in (2000 - p.x(), p.y())]
        assert got == pytest.approx(want)    # flat list: approx rejects nesting
    else:                                    # Slice 3 (Part B)
        s.manip_scale_about(QPointF(0, 0), 2.0)
        got = [c for p in s.grip_points() for c in (p.x(), p.y())]
        want = [c for p in before for c in (2 * p.x(), 2 * p.y())]
        assert got == pytest.approx(want)
    assert s.is_periodic() and len(s.grip_points()) == 4
    assert _seam_ok(s.path())
    assert SplineItem.from_dict(s.to_dict()).is_periodic()
