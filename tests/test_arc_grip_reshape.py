"""ArcItem grips re-shape the arc (user 2026-09-23 grill Q3/Q4)."""
import math
import pytest
from PyQt6.QtCore import QPointF, Qt

from firepro3d.geometry_2d import ArcItem
from firepro3d.manip_handle import ArcEndpointGripHandle


def _close(p, q, tol=1e-6):
    return abs(p.x() - q.x()) < tol and abs(p.y() - q.y()) < tol


def _arc():
    # centre (0,0), r 50, start 0°, span 90° → start (50,0), end (0,-50)
    return ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0)


class _Scene:
    _tools = None
    _grip_item = None
    _grip_dragging = False
    def get_effective_position(self, p): return QPointF(p)


class _M:
    _commit_hook = None
    _moved = True
    def __init__(self): self.sc = _Scene()
    def scene(self): return self.sc
    def _reflow_live(self): pass
    def _end_drag(self): pass


def test_centre_grip_keeps_both_endpoints():
    a = _arc()
    s0, e0 = a.grip_points()[1], a.grip_points()[2]
    a.apply_grip(0, QPointF(-40, 30))           # far off the bisector
    s1, e1 = a.grip_points()[1], a.grip_points()[2]
    assert _close(s0, s1) and _close(e0, e1)
    # the new centre lies on the bisector of start/end (equidistant)
    c = a.grip_points()[0]
    assert math.hypot(c.x() - s1.x(), c.y() - s1.y()) == pytest.approx(
        math.hypot(c.x() - e1.x(), c.y() - e1.y()))
    assert not _close(c, QPointF(0, 0))           # it actually moved


def test_centre_crossing_chord_turns_minor_into_major():
    a = _arc()
    a.apply_grip(0, QPointF(50, -50))            # past the chord midpoint (25,-25)
    assert a._span_deg > 180.0


def test_endpoint_grip_lands_under_cursor_other_end_and_mid_fixed():
    a = _arc()
    mid0 = a.arc_midpoint()
    e0 = a.grip_points()[2]
    h = [x for x in a.manip_handles() if x.index == 1][0]
    assert isinstance(h, ArcEndpointGripHandle)
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(60, 20), Qt.KeyboardModifier.NoModifier)
    assert _close(a.grip_points()[1], QPointF(60, 20))
    assert _close(a.grip_points()[2], e0)
    # the press-time midpoint is still ON the arc
    c, r = a._center, a._radius
    assert math.hypot(mid0.x() - c.x(), mid0.y() - c.y()) == pytest.approx(r)


def test_ctrl_endpoint_slides_along_press_circle():
    a = _arc()
    h = [x for x in a.manip_handles() if x.index == 1][0]
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(100, 20), Qt.KeyboardModifier.ControlModifier)
    assert a._radius == pytest.approx(50.0)
    assert _close(a._center, QPointF(0, 0))


def test_collinear_endpoint_drag_holds_last_valid_shape():
    a = _arc()
    h = [x for x in a.manip_handles() if x.index == 1][0]
    m = _M()
    h.on_press(m)
    before = a.to_dict()
    mid, end = a.arc_midpoint(), a.grip_points()[2]
    # a point on the line through end and mid (beyond mid) → collinear
    p = QPointF(mid.x() + (mid.x() - end.x()), mid.y() + (mid.y() - end.y()))
    h.on_drag(m, p, Qt.KeyboardModifier.NoModifier)
    assert a.to_dict() == before


def test_endpoint_esc_restores_exactly():
    a = _arc()
    before = a.to_dict()
    h = [x for x in a.manip_handles() if x.index == 2][0]
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(-20, -70), Qt.KeyboardModifier.NoModifier)
    h.on_cancel(m)
    after = a.to_dict()
    for k in ("cx", "cy", "radius", "start_deg", "span_deg"):
        assert after[k] == pytest.approx(before[k], abs=1e-6)
    assert a._arc_refit_ref is None
