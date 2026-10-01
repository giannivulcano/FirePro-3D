"""Slice 8 guards — periodic splines under snap and Offset (DD7).

Real Model_Space(scene_role="block_editor") + shown Model_View; real
SnapEngine.find and the real Offset tool (start -> move -> typed distance).
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import SplineItem
from tests._snap_polish_helpers import close_view, make_view, move

# A 1000 x 800 mm control loop inside the visible view (m11 = 0.25 shows
# about +-1600 x +-1200) and away from the origin (keeps the Slice-2 origin
# target out of the aperture). The periodic curve passes ~215 mm inside each
# corner control point.
SQ = [(400, 300), (1400, 300), (1400, 1100), (400, 1100)]


def _add(scene, closed=True, pts=SQ):
    s = SplineItem([QPointF(x, y) for x, y in pts], closed=closed)
    scene.addItem(s)
    scene._draw_splines.append(s)
    scene.push_undo_state()
    return s


def _type_distance(scene, text):
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Distance").setText(text)
    scene.dynamic_input._accept()


def _seam_turn_deg(path, eps=1e-4):
    p0, p1 = path.pointAtPercent(0.0), path.pointAtPercent(1.0)
    a, b = path.pointAtPercent(eps), path.pointAtPercent(1.0 - eps)
    t_out = (a.x() - p0.x(), a.y() - p0.y())
    t_in = (p1.x() - b.x(), p1.y() - b.y())
    c = ((t_out[0] * t_in[0] + t_out[1] * t_in[1])
         / (math.hypot(*t_out) * math.hypot(*t_in)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def test_periodic_spline_offers_no_endpoint_snap(qapp):
    view, scene = make_view(mode="select")              # m11 = 0.25
    try:
        s = _add(scene)
        eng = scene._snap_engine
        assert not any(k == "endpoint" for k, _p, _n in eng._collect(s))   # [RED]
        corner = QPointF(1400, 300)                      # control point 1, off-curve
        r = eng.find(QPointF(corner.x() + 4, corner.y() + 4), scene,
                     view.transform())
        assert r is None or r.snap_type != "endpoint"                       # [RED]
        # the curve itself still snaps (nearest/perp come from the path)
        on = s.path().pointAtPercent(0.1)
        r2 = eng.find(QPointF(on.x() + 2, on.y() + 2), scene, view.transform())
        assert r2 is not None and r2.source_item is s
        assert r2.snap_type != "endpoint"
    finally:
        close_view(view, scene)


def test_legacy_closed_spline_keeps_its_endpoint_snaps(qapp):
    """Coincident-end (kinked) splines are out of DD7's snap change."""
    view, scene = make_view(mode="select")
    try:
        s = _add(scene, closed=False, pts=SQ + [SQ[0]])
        kinds = [k for k, _p, _n in scene._snap_engine._collect(s)]
        assert kinds.count("endpoint") == 5
    finally:
        close_view(view, scene)


def test_offset_of_periodic_spline_stays_periodic(qapp):
    """Real Offset tool: preselected periodic square, cursor outside, typed 50."""
    pts = [(-200, -200), (200, -200), (200, 200), (-200, 200)]
    view, scene = make_view(scale=1.0)
    try:
        s = _add(scene, pts=pts)
        scene.clearSelection()
        s.setSelected(True)
        p0 = scene._undo_pos
        scene._modify_ctl.start("offset")
        assert scene.mode == "offset_side"
        move(view, QPointF(350, -280))                   # outside the loop
        _type_distance(scene, "50")
        assert len(scene._draw_splines) == 2
        new = scene._draw_splines[-1]
        assert new is not s and new.is_periodic()                           # [RED]
        assert len(new._control_points) == 4             # no seam duplicate
        # mitered control loop: each corner moved 50*sqrt(2) diagonally out
        for (x, y), q in zip(pts, new._control_points):
            assert (q.x(), q.y()) == pytest.approx((x * 1.25, y * 1.25), abs=1e-6)
        assert _seam_turn_deg(new.path()) < 0.5
        assert new.sceneBoundingRect().contains(s.sceneBoundingRect())
        assert scene._undo_pos == p0 + 1
        scene.undo()
        assert len(scene._draw_splines) == 1
    finally:
        close_view(view, scene)
