"""Pure 3-click rectangle solver + side/depth HUD schemas (plan Task 5).

Also pins fold D: ``rotated_rect_corners`` reimplemented via
``CAD_Math.rotate_point`` must keep matching ``RectangleItem.set_angle``.
"""
import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import (rect_side_frame, rect_signed_depth,
                                   rect_from_side_and_depth, rect_side_ghost,
                                   rotated_rect_corners, RectangleItem)
from firepro3d.dynamic_input import SCHEMAS


def _close(p, q, tol=1e-6):
    return abs(p.x() - q.x()) < tol and abs(p.y() - q.y()) < tol


def _corners(sol):
    return rotated_rect_corners(*sol)


def test_corner_rect_rotated_first_side_and_depth_side():
    base, side = QPointF(0, 0), QPointF(30 * math.cos(math.radians(30)),
                                        -30 * math.sin(math.radians(30)))
    n = rect_side_frame(base, side)[2]
    cursor = QPointF(side.x() + 10 * n[0], side.y() + 10 * n[1])   # 10 to the left
    d = rect_signed_depth(base, side, cursor)
    assert d == pytest.approx(10.0)
    sol = rect_from_side_and_depth(base, side, d, from_center=False)
    cs = _corners(sol)
    assert any(_close(c, base) for c in cs)
    assert any(_close(c, side) for c in cs)
    assert any(_close(c, cursor) for c in cs)
    assert sol[2] == pytest.approx(30.0)


def test_negative_depth_flips_side():
    base, side = QPointF(0, 0), QPointF(40, 0)
    up = _corners(rect_from_side_and_depth(base, side, 10, False))
    dn = _corners(rect_from_side_and_depth(base, side, -10, False))
    assert min(c.y() for c in up) == pytest.approx(-10)
    assert max(c.y() for c in dn) == pytest.approx(10)


def test_centre_rect_full_extents():
    c, side = QPointF(0, 0), QPointF(0, -20)          # side midpoint 20 up → W = 40
    sol = rect_from_side_and_depth(c, side, 5, from_center=True)   # H = 10
    cs = _corners(sol)
    xs = sorted(round(p.x(), 6) for p in cs)
    ys = sorted(round(p.y(), 6) for p in cs)
    assert xs[0] == -5 and xs[-1] == 5 and ys[0] == -20 and ys[-1] == 20


def test_too_small_rejected():
    assert rect_from_side_and_depth(QPointF(0, 0), QPointF(0.3, 0), 10, False) is None
    assert rect_from_side_and_depth(QPointF(0, 0), QPointF(10, 0), 0.2, False) is None


def test_matches_rectangle_item_footprint_and_roundtrip(qapp):
    sol = rect_from_side_and_depth(QPointF(5, 5), QPointF(35, -12), 9, False)
    pt1, pt2, ang, piv = sol
    it = RectangleItem(pt1, pt2)
    it.set_angle(ang, piv)
    grips = it.grip_points()
    for c in _corners(sol):
        assert any(_close(c, g, 1e-6) for g in grips)
    back = RectangleItem.from_dict(it.to_dict())
    for a, b in zip(back.grip_points(), grips):
        assert _close(a, b)


def test_rotated_rect_corners_unchanged_by_fold_d():
    cs = rotated_rect_corners(QPointF(0, 0), QPointF(10, 5), 90.0, QPointF(0, 0))
    assert _close(cs[1], QPointF(0, -10))     # TR (10,0) rotated Y-up 90° → screen up


@pytest.mark.parametrize("angle", [0.0, 17.5, 90.0, -133.0, 271.0])
def test_rotated_rect_corners_match_item_map_to_scene(qapp, angle):
    """Fold D keeps the helper identical to the item's own Qt transform."""
    pt1, pt2, piv = QPointF(-3, 2), QPointF(14, 9), QPointF(1.5, -4)
    it = RectangleItem(pt1, pt2)
    it.set_angle(angle, piv)
    local = [QPointF(pt1.x(), pt1.y()), QPointF(pt2.x(), pt1.y()),
             QPointF(pt2.x(), pt2.y()), QPointF(pt1.x(), pt2.y())]
    for got, loc in zip(rotated_rect_corners(pt1, pt2, angle, piv), local):
        assert _close(got, it.mapToScene(loc), 1e-9)


def test_side_ghost():
    a, b = rect_side_ghost(QPointF(0, 0), QPointF(10, 0), from_center=True)
    assert _close(a, QPointF(-10, 0)) and _close(b, QPointF(10, 0))
    a, b = rect_side_ghost(QPointF(0, 0), QPointF(10, 0), from_center=False)
    assert _close(a, QPointF(0, 0)) and _close(b, QPointF(10, 0))


def test_rect_depth_schema_resolves_along_injected_normal():
    p = SCHEMAS["rect_depth"].resolve(QPointF(1, 1), {"H": 4.0, "__dir__": (0.0, -1.0)})
    assert _close(p, QPointF(1, -3))
    p = SCHEMAS["rect_depth_center"].resolve(QPointF(1, 1), {"H": 4.0, "__dir__": (0.0, -1.0)})
    assert _close(p, QPointF(1, -1))
    p = SCHEMAS["rect_side_center"].resolve(QPointF(0, 0), {"Length": 20.0, "Angle": 0.0})
    assert _close(p, QPointF(10, 0))


def test_rect_side_center_seed_roundtrips():
    s = SCHEMAS["rect_side_center"]
    v = s.seed(QPointF(2, 3), QPointF(12, -7))
    assert _close(s.resolve(QPointF(2, 3), v), QPointF(12, -7))


def test_hud_injects_direction_for_rect_depth(qapp):
    """``values()``/``current_values()`` inject ``__dir__`` for rect_depth*."""
    from firepro3d.dynamic_input import DynamicInputHud
    for name in ("rect_depth", "rect_depth_center"):
        hud = DynamicInputHud(SCHEMAS[name])
        hud.set_track_direction((0.6, -0.8))
        assert hud.current_values()["__dir__"] == (0.6, -0.8)
        assert hud.values()["__dir__"] == (0.6, -0.8)
