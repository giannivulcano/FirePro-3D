"""AC2 pure planner: exactness test + handle refs (auto_constrain.plan_hv /
item_hv / rect_drawn_edge)."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

from firepro3d import auto_constrain as ac
from firepro3d.geometry_2d import EllipseItem, LineItem, RectangleItem, RegularPolygonItem

REFS = [{"uid": "u", "h": "edge"}]


def test_plan_hv_exact_axes():
    assert ac.plan_hv((0, 5), (100, 5), REFS) == [("horizontal", REFS)]
    assert ac.plan_hv((7, 0), (7, -40), REFS) == [("vertical", REFS)]


def test_plan_hv_within_lin_tol_counts_as_exact():
    # 6e-17 * 100 = cos(pi/2) residue of a Ctrl-locked 90 deg tip (raw: math.cos)
    assert ac.plan_hv((0, 0), (100 * math.cos(math.pi / 2), 100), REFS) == [("vertical", REFS)]


def test_plan_hv_near_miss_and_degenerate_are_none():
    # 1 deg off over 100 mm: dy = 100*sin(1deg) = 1.745 mm >> 1e-6
    a, b = (0, 0), (100 * math.cos(math.radians(1)), 100 * math.sin(math.radians(1)))
    assert ac.plan_hv(a, b, REFS) == []
    assert ac.plan_hv((3, 3), (3, 3), REFS) == []          # zero length: no direction
    assert ac.plan_hv((0, 0), (0, 5e-7), REFS) == []        # both under LIN_TOL


def test_item_hv_line_edge():
    ln = LineItem(QPointF(0, 10), QPointF(200, 10))
    assert ac.item_hv(ln, ("edge",)) == [("horizontal", [{"uid": ln._uid, "h": "edge"}])]


def test_item_hv_two_points_ellipse_axis():
    el = EllipseItem(QPointF(0, 0), 80.0, 30.0, 90.0)        # rot 90: a-axis vertical
    assert ac.item_hv(el, ("a0", "a1")) == [
        ("vertical", [{"uid": el._uid, "h": "a0"}, {"uid": el._uid, "h": "a1"}])]


def test_item_hv_unknown_handle_is_none():
    ln = LineItem(QPointF(0, 10), QPointF(200, 10))
    assert ac.item_hv(ln, ("s9",)) == []


def test_polygon_circumscribed_facing_side_is_last():
    pg = RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=50.0, rotation_deg=0.0,
                            inscribed=False)
    # heading 0 = east apothem -> the facing side is vertical
    assert ac.item_hv(pg, ("s5",)) == [("vertical", [{"uid": pg._uid, "h": "s5"}])]


def test_rect_drawn_edge_corner_and_centre():
    r = RectangleItem(QPointF(0, -50), QPointF(100, 0))       # axis-aligned, y-down scene
    # raw: _RECT_LOCAL bottom = local v = +1 -> scene y = cy + h/2 = -25 + 25 = 0
    assert ac.rect_drawn_edge(r, QPointF(0, 0), QPointF(100, 0), from_center=False) == "bottom"
    # centre variant: side point = the right-edge midpoint (100, -25)
    assert ac.rect_drawn_edge(r, QPointF(50, -25), QPointF(100, -25), from_center=True) == "right"
