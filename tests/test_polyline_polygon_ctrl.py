"""S3a / Fold D guards — Ctrl angle-constrains polyline/polygon vertices.

Real ``Model_Space`` + shown ``Model_View``, posted mouse events with Ctrl on
EVERY event. Every angle assertion is the convention-free on-increment
property (the committed segment lies on a 45° multiple), measured from the
committed geometry. The raw drag target is 33.69° off the anchor.
"""
import math

from PyQt6.QtCore import QPointF, Qt

from firepro3d.floor_slab import FloorSlab
from firepro3d.geometry_2d import PolylineItem
from firepro3d.roof import RoofItem
from tests._snap_polish_helpers import click, close_view, drag, make_view, move

CTRL = Qt.KeyboardModifier.ControlModifier


def _angle(a, b):
    return math.degrees(math.atan2(-(b.y() - a.y()), b.x() - a.x())) % 180.0


def _on_increment(a_deg, step=45.0):
    r = a_deg % step
    return min(r, step - r) < 0.01


def _poly(scene, pts, closed=False):
    pl = PolylineItem(QPointF(*pts[0]))
    for p in pts[1:]:
        pl.append_point(QPointF(*p))
    if closed:
        pl.close()
    pl.finalize()
    scene.addItem(pl)
    scene._polylines.append(pl)
    scene.clearSelection()
    pl.setSelected(True)
    return pl


# ── S3a: vertex grips ────────────────────────────────────────────────────────

def test_open_polyline_end_grip_ctrl_constrains_against_neighbour(qapp):
    view, scene = make_view()
    try:
        pl = _poly(scene, [(0, 0), (1000, 0)])
        drag(view, pl.grip_points()[1], QPointF(600, 400), mods=CTRL)   # raw 33.69°
        g = pl.grip_points()
        assert g[1] != QPointF(1000, 0)
        assert _on_increment(_angle(g[0], g[1])), _angle(g[0], g[1])
    finally:
        close_view(view, scene)


def test_open_polyline_start_grip_ctrl_constrains_against_next(qapp):
    view, scene = make_view()
    try:
        pl = _poly(scene, [(0, 0), (1000, 0), (1000, -1000)])
        drag(view, pl.grip_points()[0], QPointF(400, 300), mods=CTRL)
        g = pl.grip_points()
        assert g[0] != QPointF(0, 0)
        assert _on_increment(_angle(g[1], g[0])), _angle(g[1], g[0])
    finally:
        close_view(view, scene)


def test_interior_vertex_ctrl_constrains_against_previous(qapp):
    view, scene = make_view()
    try:
        pl = _poly(scene, [(0, 0), (1000, 0), (1000, -1000)])
        drag(view, pl.grip_points()[1], QPointF(600, 400), mods=CTRL)
        g = pl.grip_points()
        assert g[1] != QPointF(1000, 0)
        assert _on_increment(_angle(g[0], g[1])), _angle(g[0], g[1])
    finally:
        close_view(view, scene)


def test_closed_polyline_vertex0_ctrl_wraps_to_last(qapp):
    view, scene = make_view()
    try:
        pl = _poly(scene, [(0, 0), (1000, 0), (1000, 1000), (0, 1000)], closed=True)
        assert pl.is_closed()
        drag(view, pl.grip_points()[0], QPointF(600, 600), mods=CTRL)  # 33.69° from v3
        g = pl.grip_points()
        assert g[0] != QPointF(0, 0)
        assert _on_increment(_angle(g[3], g[0])), _angle(g[3], g[0])
    finally:
        close_view(view, scene)


def _polygon_vertex0_ctrl(cls, bucket):
    view, scene = make_view(role="plan")
    try:
        item = cls([QPointF(0, 0), QPointF(1000, 0),
                    QPointF(1000, 1000), QPointF(0, 1000)])
        item.close_polygon()
        scene.addItem(item)
        getattr(scene, bucket).append(item)
        scene.clearSelection()
        item.setSelected(True)
        drag(view, item.grip_points()[0], QPointF(600, 600), mods=CTRL)  # 33.69° from v3
        g = item.grip_points()
        assert g[0] != QPointF(0, 0)
        assert _on_increment(_angle(g[3], g[0])), _angle(g[3], g[0])
    finally:
        close_view(view, scene)


def test_floor_vertex_grip_ctrl_constrains_against_previous(qapp):
    _polygon_vertex0_ctrl(FloorSlab, "_floor_slabs")


def test_roof_vertex_grip_ctrl_constrains_against_previous(qapp):
    _polygon_vertex0_ctrl(RoofItem, "_roofs")
