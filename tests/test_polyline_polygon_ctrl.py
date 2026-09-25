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
    """Undirected segment angle a→b in degrees, folded into [0, 180).

    Args:
        a: Segment start (scene coords, Y-down).
        b: Segment end.

    Returns:
        The angle modulo 180°, so the on-increment check is direction-free.
    """
    return math.degrees(math.atan2(-(b.y() - a.y()), b.x() - a.x())) % 180.0


def _on_increment(a_deg, step=45.0):
    """Whether *a_deg* lies on a multiple of *step* (within 0.01°).

    Args:
        a_deg: Angle in degrees.
        step: Angle increment in degrees.

    Returns:
        True if the angle is on an increment.
    """
    r = a_deg % step
    return min(r, step - r) < 0.01


def _poly(scene, pts, closed=False):
    """Add a finalized, selected PolylineItem to *scene*.

    Args:
        scene: The real ``Model_Space``.
        pts: Vertex ``(x, y)`` tuples in order.
        closed: Flag the polyline closed (needs >= 3 vertices).

    Returns:
        The registered ``PolylineItem``.
    """
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
    """Ctrl-drag vertex 0 of a closed 4-vertex polygon item; assert the edge
    from vertex n−1 lands on a 45° increment.

    Args:
        cls: ``FloorSlab`` or ``RoofItem``.
        bucket: The scene collection attribute the item registers in.
    """
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


# ── Fold D: floor / roof polygon placement ───────────────────────────────────

_ORIGIN = QPointF(0, 0)
_RAW = QPointF(600, 400)          # 33.69° off the first vertex


def _near(a, b, tol=0.01):
    """Whether two points coincide within *tol* mm.

    Args:
        a: First point.
        b: Second point.
        tol: Distance tolerance in mm.

    Returns:
        True if ``|a − b| <= tol``.
    """
    return math.hypot(a.x() - b.x(), a.y() - b.y()) <= tol


def _preview_tip(scene):
    """Return the rubber-band preview's tip (asserting it is anchored at the
    first vertex and visible).

    Args:
        scene: The real ``Model_Space`` mid-placement.

    Returns:
        The preview line's end point.
    """
    ln = scene.preview_pipe.line()
    assert scene.preview_pipe.isVisible()
    assert ln.p1() == _ORIGIN, ln
    return ln.p2()


def test_floor_polygon_placement_ctrl_constrains_preview_and_commit(qapp):
    view, scene = make_view(role="plan", mode="floor")
    try:
        scene._set_floor_primitive("polygon")
        click(view, _ORIGIN)
        assert scene._floor_active is not None
        move(view, _RAW, mods=CTRL)
        r = scene.get_resolved_point()
        assert r is not None and r != _RAW
        assert _on_increment(_angle(_ORIGIN, r)), _angle(_ORIGIN, r)
        tip = _preview_tip(scene)
        assert _on_increment(_angle(_ORIGIN, tip)), _angle(_ORIGIN, tip)
        click(view, _RAW, mods=CTRL)
        pts = scene._floor_active._points
        assert len(pts) == 2 and pts[0] == _ORIGIN, pts
        assert _on_increment(_angle(pts[0], pts[1])), _angle(pts[0], pts[1])
        # preview tip == published point == committed vertex (one anchor)
        assert _near(tip, r) and _near(r, pts[1]), (tip, r, pts[1])
    finally:
        close_view(view, scene)


def test_roof_polygon_placement_ctrl_constrains_preview_and_commit(qapp):
    """Real clicks; never closes the polygon (closing opens the modal RoofDialog)."""
    view, scene = make_view(role="plan", mode="roof")
    try:
        click(view, _ORIGIN)
        assert scene._roof_active is not None
        move(view, _RAW, mods=CTRL)
        tip = _preview_tip(scene)
        assert tip != _RAW
        assert _on_increment(_angle(_ORIGIN, tip)), _angle(_ORIGIN, tip)
        click(view, _RAW, mods=CTRL)
        pts = scene._roof_active._points
        assert len(pts) == 2 and pts[0] == _ORIGIN, pts
        assert _on_increment(_angle(pts[0], pts[1])), _angle(pts[0], pts[1])
        assert _near(tip, pts[1]), (tip, pts[1])      # preview == committed
    finally:
        close_view(view, scene)
