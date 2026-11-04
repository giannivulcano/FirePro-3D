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

from tests._sb4d_helpers import (HEAD_R, SQ_HALF, dispose, head_def, pixel_at,
                                 plan_scene, wall)

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


def _placed(ms, sec, a=(0.0, 0.0), b=(6000.0, 0.0)):
    m = sec.place_section(QPointF(*a), QPointF(*b))
    m.refresh_heads()
    return m


def test_placed_section_owns_two_upright_heads_on_the_cut_ends(qapp):
    from firepro3d import marks
    from firepro3d.view_marker_head import ViewMarkerHead
    ms, sec, det, tabs = plan_scene()
    try:
        d = head_def(ms, "Section", texts=(("Mark", -2.0), ("Sheet", 2.0)))
        a, b = (0.0, 0.0), (5196.152, -3000.0)                 # a 30 deg cut
        m = _placed(ms, sec, a, b)
        assert m.head is None
        for h, end in ((m.head_a, QPointF(*a)), (m.head_b, QPointF(*b))):
            assert isinstance(h, ViewMarkerHead) and h.parentItem() is m
            assert h.category == "Section" and h.definition() is d
            assert h.pos() == end
            t = h.sceneTransform()
            assert h.rotation() == 0.0 and t.m12() == 0.0 and t.m21() == 0.0   # upright on a 30 deg cut (Q3)
        marks.set_mark(m, "7")
        assert m.head_a.host_values({"Mark"})["Mark"].text == "7"
    finally:
        dispose(ms, sec, tabs)


@pytest.mark.parametrize("shape,r_mm", [("circle", HEAD_R), ("square", SQ_HALF * math.sqrt(2.0))])
def test_section_triangle_is_tangent_to_the_heads_enclosing_circle(qapp, shape, r_mm):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Section", shape=shape)
        m = _placed(ms, sec)
        rk = r_mm * ms.scale_manager.drawing_scale
        for end in (m.cut_a, m.cut_b):
            p0, apex, p1 = list(m._triangle(end))
            for s, e in ((p0, apex), (apex, p1)):
                dx, dy = e.x() - s.x(), e.y() - s.y()
                dist = abs(dy * (end.x() - s.x()) - dx * (end.y() - s.y())) / math.hypot(dx, dy)
                assert dist == pytest.approx(rk, rel=1e-3)                        # sides tangent
            assert _dist(apex, end) == pytest.approx(rk * math.sqrt(2.0), rel=1e-3)
    finally:
        dispose(ms, sec, tabs)


def test_cut_line_is_trimmed_at_each_head_outline(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Section")
        m = _placed(ms, sec)                                     # A (0, 0) -> B (6000, 0)
        rk = HEAD_R * ms.scale_manager.drawing_scale             # 500
        a, b = m._trimmed_cut()
        assert a.x() == pytest.approx(rk, rel=1e-3) and b.x() == pytest.approx(6000.0 - rk, rel=1e-3)
    finally:
        dispose(ms, sec, tabs)


def test_section_head_follows_the_drawing_scale(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Section")
        m = _placed(ms, sec)
        for ds in (50.0, 200.0):
            ms.scale_manager.drawing_scale = ds
            ms.refresh_annotation_tags()
            assert m.head_a.enclosing_radius() == pytest.approx(HEAD_R * ds, rel=1e-3)
            assert _dist(list(m._triangle(m.cut_a))[1], m.cut_a) == pytest.approx(
                HEAD_R * ds * math.sqrt(2.0), rel=1e-3)
    finally:
        dispose(ms, sec, tabs)


def _detail(ms, det, rect=QRectF(0.0, 0.0, 4000.0, 3000.0)):
    m = det.create_detail("Detail 1", rect)
    m.refresh_heads()
    return m


def test_detail_owns_one_upright_callout_head_at_its_bubble(qapp):
    from firepro3d.view_marker_head import ViewMarkerHead
    ms, sec, det, tabs = plan_scene()
    try:
        d = head_def(ms, "Detail", texts=(("Mark", -2.0), ("Sheet", 2.0)))
        m = _detail(ms, det)
        b = m.bubble
        assert isinstance(b, ViewMarkerHead) and b.parentItem() is m and b.host is m
        assert b.category == "Detail" and b.definition() is d and b.rotation() == 0.0
        assert b.pos() == m._bubble_pos
        assert b.enclosing_radius() == pytest.approx(HEAD_R * ms.scale_manager.drawing_scale, rel=1e-3)
    finally:
        dispose(ms, sec, tabs)


def test_detail_head_follows_grip_resize_translate_and_load(qapp):
    from firepro3d.detail_view import DetailMarker
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Detail")
        m = _detail(ms, det)
        m.apply_grip(8, QPointF(9000.0, 9000.0))                   # bubble drag
        assert m.bubble.pos() == QPointF(9000.0, 9000.0)
        m.apply_grip(2, QPointF(5000.0, 4000.0))                   # resize: bubble follows the centre delta
        assert m.bubble.pos() == m._bubble_pos
        m.manip_translate(100.0, 50.0)
        assert m.bubble.pos() == m._bubble_pos
        back = DetailMarker.from_dict(m.to_dict())
        ms.addItem(back)
        assert back.bubble.pos() == m._bubble_pos
    finally:
        dispose(ms, sec, tabs)


def test_detail_leader_is_trimmed_at_the_head_outline(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Detail")
        m = _detail(ms, det)                                        # bubble straight below the crop rect
        start, end = m._leader()
        rk = HEAD_R * ms.scale_manager.drawing_scale
        assert _dist(end, m._bubble_pos) == pytest.approx(rk, rel=1e-3)
        assert start == m._closest_rect_point(m.crop_rect, m._bubble_pos)
    finally:
        dispose(ms, sec, tabs)


def test_detail_head_follows_the_drawing_scale(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Detail")
        m = _detail(ms, det)
        for ds in (50.0, 200.0):
            ms.scale_manager.drawing_scale = ds
            ms.refresh_annotation_tags()
            assert m.bubble.enclosing_radius() == pytest.approx(HEAD_R * ds, rel=1e-3)
    finally:
        dispose(ms, sec, tabs)


# -- heads re-anchor, the wedge stops at the head, the head is hittable -----------

def test_heads_follow_set_geometry_flip_and_auto_fit(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Section")
        head_def(ms, "Elevation")
        placed = _placed(ms, sec)
        placed.set_geometry(QPointF(100.0, 200.0), QPointF(4100.0, 1200.0), 3000.0)
        assert placed.head_a.pos() == QPointF(100.0, 200.0)
        assert placed.head_b.pos() == QPointF(4100.0, 1200.0)
        sec.seed_cardinals()
        north = sec.marker("north")
        north.refresh_heads()
        before = QPointF(north.head.pos())
        north.flip()                                      # the look side (and so the centre) swaps
        assert north.head.pos() == north._cardinal_centre() and north.head.pos() != before
        north.flip()
        assert north.head.pos() == before
        north.set_geometry(QPointF(-3000.0, -9000.0), QPointF(3000.0, -9000.0), 2500.0)
        assert north.head.pos() == north._cardinal_centre() and north.head.pos() != before
        south = sec.marker("south")
        south.refresh_heads()
        old = QPointF(south.head.pos())
        wall(ms)                                          # the building grows: an auto-extent cardinal re-fits
        assert south.auto_fit(ms) and south.head.pos() == south._cardinal_centre()
        assert south.head.pos() != old
    finally:
        dispose(ms, sec, tabs)


def test_section_arrow_stops_at_the_head_outline_and_paints_beyond_it(qapp):
    """The triangle's base is on the cut line through the head centre, so it
    covers the head's interior; _outside_head keeps it out (the cardinal wedge
    only grazes the enclosing circle, so there the subtraction is invisible)."""
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Section")
        head_def(ms, "Elevation")
        m = _placed(ms, sec)
        nx, ny = m.normal_scene()
        r, end = m._rk(), m.cut_a
        arrow = m._marker_color.name()
        inside = QPointF(end.x() + nx * 0.5 * r, end.y() + ny * 0.5 * r)    # in the triangle, inside the head
        beyond = QPointF(end.x() + nx * 1.2 * r, end.y() + ny * 1.2 * r)    # in the triangle, past the head
        background = pixel_at(ms, QPointF(end.x() - nx * 0.5 * r, end.y() - ny * 0.5 * r + 3000.0))
        assert pixel_at(ms, beyond) == arrow
        assert pixel_at(ms, inside) == background != arrow
        sec.seed_cardinals()
        north = sec.marker("north")
        north.refresh_heads()
        c, rc = north._cardinal_centre(), north._rk()
        nx, ny = north.normal_scene()
        assert pixel_at(ms, QPointF(c.x() + nx * 1.3 * rc, c.y() + ny * 1.3 * rc)) == north._marker_color.name()
    finally:
        dispose(ms, sec, tabs)


def test_shape_covers_each_head_outline(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Section")
        head_def(ms, "Elevation")
        placed = _placed(ms, sec)                                       # A (0, 0) -> B (6000, 0), look +y
        r = placed._rk()
        nx, ny = placed.normal_scene()
        for end in (placed.cut_a, placed.cut_b):
            behind = QPointF(end.x() - nx * 0.8 * r, end.y() - ny * 0.8 * r)   # off the line, off the arrow
            assert placed.shape().contains(behind)
        sec.seed_cardinals()
        north = sec.marker("north")
        north.refresh_heads()
        assert north.shape().contains(north._cardinal_centre())          # the head itself, not just the wedge
    finally:
        dispose(ms, sec, tabs)
