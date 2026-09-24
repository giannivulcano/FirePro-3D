"""Rotated-RectangleItem consumers must honour the data rotation.

RectangleItem stores rotation as DATA (``_angle``/``_pivot``) with ``rect()``
axis-aligned in local coords.  Consumers that read ``rect()`` alone (block
compile, mirror/scale/rotate/explode, offset) silently produced an axis-aligned
result for an angled rect.  Every test here asserts observable scene geometry
(corner sets) of a real 30/45 degree rectangle.
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath

from firepro3d.block_definition import BlockDefinition
from firepro3d.cad_math import CAD_Math
from firepro3d.geometry_2d import LineItem, PolylineItem, RectangleItem
from firepro3d import tool_geometry as tg
from tests.test_scene_tools import _StubScene, scene  # noqa: F401  (fixture)


TOL = 1e-6


def _corners(r: RectangleItem) -> list[QPointF]:
    g = r.grip_points()
    return [g[0], g[2], g[4], g[6]]


def _same_point_set(a, b, tol=1e-4) -> bool:
    if len(a) != len(b):
        return False
    rest = list(b)
    for p in a:
        hit = next((q for q in rest
                    if abs(p.x() - q.x()) < tol and abs(p.y() - q.y()) < tol), None)
        if hit is None:
            return False
        rest.remove(hit)
    return True


def _rect30(pivot=None) -> RectangleItem:
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    r.set_angle(30.0, pivot)
    return r


def _path_vertices(path: QPainterPath) -> list[QPointF]:
    pts = []
    for i in range(path.elementCount()):
        e = path.elementAt(i)
        p = QPointF(e.x, e.y)
        if not any(abs(p.x() - q.x()) < 1e-6 and abs(p.y() - q.y()) < 1e-6
                   for q in pts):
            pts.append(p)
    return pts


# ── 1. mapToParent + block compile ───────────────────────────────────────────

def test_map_to_parent_honours_data_rotation(qapp):
    r = _rect30()
    local = QPointF(0, 0)
    assert abs(r.mapToParent(local).x() - r.mapToScene(local).x()) < TOL
    assert abs(r.mapToParent(local).y() - r.mapToScene(local).y()) < TOL
    path = QPainterPath()
    path.addRect(r.rect())
    assert _same_point_set(_path_vertices(r.mapToParent(path)), _corners(r))


@pytest.mark.parametrize("pivot", [None, QPointF(0, 0)])
def test_block_compile_keeps_rotated_rect_footprint(qapp, pivot):
    r = _rect30(pivot)
    expected = _corners(r)
    d = BlockDefinition.new(name="R", library="L", series="S",
                            primitives=[r.to_dict()], origin=(0.0, 0.0))
    # Round-trip the definition (save/load) before compiling.
    d = BlockDefinition.from_dict(d.to_dict())
    ops = d.render_ops()
    assert len(ops) == 1
    assert _same_point_set(_path_vertices(ops[0][2]), expected)


# ── 2. scene_tools transforms ────────────────────────────────────────────────

def test_mirror_rotated_rect(scene):
    r = _rect30()
    scene.addItem(r)
    scene._draw_rects.append(r)
    scene._selected_items = [r]
    a1, a2 = QPointF(300, -50), QPointF(320, 400)
    expected = [CAD_Math.mirror_point(c, a1, a2) for c in _corners(r)]
    new = scene._tools._apply_mirror(a1, a2)
    assert len(new) == 1
    assert _same_point_set(_corners(new[0]), expected)


def test_scale_rotated_rect(scene):
    r = _rect30(QPointF(0, 0))
    scene.addItem(r)
    base = QPointF(50, 80)
    expected = [CAD_Math.scale_point(c, base, 1.5) for c in _corners(r)]
    scene._tools._apply_scale(base, 1.5, items=[r])
    assert _same_point_set(_corners(r), expected)


def test_scale_rotated_rect_centre_pivot(scene):
    r = _rect30()
    scene.addItem(r)
    base = QPointF(-40, 10)
    expected = [CAD_Math.scale_point(c, base, 0.5) for c in _corners(r)]
    scene._tools._apply_scale(base, 0.5, items=[r])
    assert _same_point_set(_corners(r), expected)


def test_rotate_rotated_rect_to_polyline(scene):
    r = _rect30()
    scene.addItem(r)
    scene._draw_rects.append(r)
    pivot = QPointF(10, 20)
    expected = [CAD_Math.rotate_point(c, pivot, 45.0) for c in _corners(r)]
    scene._tools._apply_rotate(pivot, 45.0, items=[r])
    assert len(scene._polylines) == 1
    pts = scene._polylines[0]._points
    uniq = [p for i, p in enumerate(pts)
            if not any(abs(p.x() - q.x()) < 1e-6 and abs(p.y() - q.y()) < 1e-6
                       for q in pts[:i])]
    assert _same_point_set(uniq, expected)


def test_explode_rotated_rect(scene):
    r = _rect30()
    scene.addItem(r)
    scene._draw_rects.append(r)
    r.setSelected(True)
    expected = _corners(r)
    scene._tools.explode_selected_items()
    assert len(scene._draw_lines) == 4
    ends = []
    for ln in scene._draw_lines:
        ends.extend([ln._pt1, ln._pt2])
    uniq = [p for i, p in enumerate(ends)
            if not any(abs(p.x() - q.x()) < 1e-6 and abs(p.y() - q.y()) < 1e-6
                       for q in ends[:i])]
    assert _same_point_set(uniq, expected)


# ── 3. offset ────────────────────────────────────────────────────────────────

def _expected_offset_corners(r: RectangleItem, d: float) -> list[QPointF]:
    lr = r.rect().adjusted(-d, -d, d, d)
    local = [lr.topLeft(), lr.topRight(), lr.bottomRight(), lr.bottomLeft()]
    return [r.mapToScene(p) for p in local]


@pytest.mark.parametrize("pivot", [None, QPointF(0, 0)])
def test_offset_rotated_rect_grow(qapp, pivot):
    r = _rect30(pivot)
    new = tg.make_offset_item(r, 10.0)
    assert new is not None
    assert _same_point_set(_corners(new), _expected_offset_corners(r, 10.0))


def test_offset_rotated_rect_side_and_distance(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    r.set_angle(45.0)
    # A point just outside a rotated edge but INSIDE the axis-aligned bounds.
    tl, tr = _corners(r)[0], _corners(r)[1]
    mid = QPointF((tl.x() + tr.x()) / 2, (tl.y() + tr.y()) / 2)
    # outward normal of the TL->TR edge in local is -y; map that direction
    n = r.mapToScene(QPointF(100, -1)) - r.mapToScene(QPointF(100, 0))
    probe = QPointF(mid.x() + 5 * n.x(), mid.y() + 5 * n.y())
    assert r.mapRectToScene(r.rect()).contains(probe)
    assert tg.offset_signed_dist(r, 7.0, probe) == 7.0
    assert abs(tg.perpendicular_distance(r, probe) - 5.0) < 1e-6


def test_highlight_rotated_rect_follows_footprint(scene):
    r = _rect30()
    scene.addItem(r)
    h = scene._tools._highlight_item(r)
    path = h.mapToScene(h.shape()) if not hasattr(h, "path") else h.path()
    assert _same_point_set(_path_vertices(path), _corners(r))
