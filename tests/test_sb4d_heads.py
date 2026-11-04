"""SB4d guard 4 (canvas): the three view-marker heads draw their category's
resolved block, annotative and upright, and the bespoke arrows are built
tangent to the head outline's enclosing circle and sized from it (D1, Q3-Q5).
Expected radii: HEAD_R / SQ_HALF (tests/_sb4d_helpers.py) x k, k = the
drawing scale (ScaleManager default 100); cardinal wedge distance
D = R_k / sin 40 deg (section_marker), tip _CARDINAL_GAP = 25 mm outside the
crop edge."""
import math

import pytest
from PyQt6.QtCore import QPointF, QRectF

from tests._sb4d_helpers import HEAD_R, SQ_HALF, dispose, head_def, plan_scene

SIN40 = math.sin(math.radians(40))


def _dist(p, q):
    return math.hypot(p.x() - q.x(), p.y() - q.y())


def test_cardinal_owns_one_upright_elevation_head_at_its_centre(qapp):
    from firepro3d.view_marker_head import ViewMarkerHead
    ms, sec, det, tabs = plan_scene()
    try:
        d = head_def(ms, "Elevation", texts=(("Direction", -1.0),))
        sec.seed_cardinals()
        m = sec.marker("north")
        m.refresh_heads()
        h = m.head
        assert isinstance(h, ViewMarkerHead)
        assert h.parentItem() is m and h.host is m and h.category == "Elevation"
        assert h.rotation() == 0.0 and h.definition() is d
        assert h.pos() == m._cardinal_centre()
        assert h.host_values({"Direction"})["Direction"].text == "N"
        assert m.head_a is None and m.head_b is None
    finally:
        dispose(ms, sec, tabs)


@pytest.mark.parametrize("shape,r_mm", [("circle", HEAD_R), ("square", SQ_HALF * math.sqrt(2.0))])
def test_cardinal_wedge_is_tangent_to_the_heads_enclosing_circle(qapp, shape, r_mm):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Elevation", shape=shape)
        sec.seed_cardinals()
        m = sec.marker("north")
        m.refresh_heads()
        k = ms.scale_manager.drawing_scale
        rk = r_mm * k
        assert m.head.enclosing_radius() == pytest.approx(rk, rel=1e-3)
        c, t1, t2, tip, _a2, _sw = m._wedge_geometry()
        assert _dist(c, tip) == pytest.approx(rk / SIN40, rel=1e-3)
        for t in (t1, t2):
            assert _dist(c, t) == pytest.approx(rk, rel=1e-3)                     # on the circle
            dot = (t.x() - c.x()) * (tip.x() - t.x()) + (t.y() - c.y()) * (tip.y() - t.y())
            assert abs(dot) / (_dist(c, t) * _dist(t, tip)) < 1e-3                # tangent
        mid = m._mid()
        assert _dist(tip, mid) == pytest.approx(m._CARDINAL_GAP, abs=1e-6)        # 25 mm outside the edge
    finally:
        dispose(ms, sec, tabs)


def test_cardinal_head_and_wedge_follow_the_drawing_scale(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Elevation")
        sec.seed_cardinals()
        m = sec.marker("south")
        for ds in (50.0, 200.0):
            ms.scale_manager.drawing_scale = ds
            ms.refresh_annotation_tags()
            assert m.head.enclosing_radius() == pytest.approx(HEAD_R * ds, rel=1e-3)
            c, _t1, _t2, tip, _a2, _sw = m._wedge_geometry()
            assert _dist(c, tip) == pytest.approx(HEAD_R * ds / SIN40, rel=1e-3)
            assert m.head.pos() == m._cardinal_centre()
    finally:
        dispose(ms, sec, tabs)


def test_cardinal_never_plots(qapp):
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Elevation")
        sec.seed_cardinals()
        m = sec.marker("north")
        m.refresh_heads()
        rect = m.mapRectToScene(m.boundingRect()).adjusted(-5000, -5000, 5000, 5000)
        saved = apply_paper_overrides(ms, rect, 0.01)
        try:
            assert not m.isVisible() and not m.head.isVisible()
        finally:
            restore_model_display(saved)
        assert m.isVisible() and m.head.isVisible()
    finally:
        dispose(ms, sec, tabs)
