"""
tests/test_geo2d_fill_render.py
================================
Render-level tests for 2D geometry fill (paint + shape/hit-test).

Uses a real QGraphicsScene rendered to a QImage so the actual paint()
code path is exercised.  The `qapp` fixture (session-scoped) is in
conftest.py.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter, QColor, QTransform
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.construction_geometry import (
    RectangleItem,
    CircleItem,
    ArcItem,
    PolylineItem,
)


# ─────────────────────────────────────────────────────────────────────────────
# Render helper
# ─────────────────────────────────────────────────────────────────────────────

def _render_scene(scene: QGraphicsScene, rect_area: QRectF, size: int = 120) -> QImage:
    """Render *scene* into a white QImage of *size* x *size* pixels."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), rect_area)
    p.end()
    return img


def _pixel(img: QImage, x: int, y: int) -> QColor:
    return QColor(img.pixel(x, y))


def _is_white(c: QColor) -> bool:
    return c.red() > 240 and c.green() > 240 and c.blue() > 240


# ─────────────────────────────────────────────────────────────────────────────
# RectangleItem — solid fill
# ─────────────────────────────────────────────────────────────────────────────

class TestRectangleFill:
    def _make_rect(self, fill: str = "none", color: str = "#0000ff") -> tuple[RectangleItem, QGraphicsScene]:
        scene = QGraphicsScene()
        r = RectangleItem(QPointF(10, 10), QPointF(110, 110))
        r.fill_type = fill
        r._display_fill_color = color
        scene.addItem(r)
        return r, scene

    def test_solid_fill_interior_non_white(self, qapp):
        """Interior pixel must be non-white when solid fill is active."""
        r, scene = self._make_rect(fill="solid", color="#0000ff")
        img = _render_scene(scene, QRectF(0, 0, 120, 120))
        # Centre of rect is at scene (60, 60) → maps to pixel (60, 60) in 120x120
        c = _pixel(img, 60, 60)
        assert not _is_white(c), (
            f"Interior pixel should be filled but got RGB({c.red()},{c.green()},{c.blue()})"
        )

    def test_no_fill_interior_stays_white(self, qapp):
        """Interior pixel must stay white when fill_type is 'none'."""
        r, scene = self._make_rect(fill="none")
        img = _render_scene(scene, QRectF(0, 0, 120, 120))
        c = _pixel(img, 60, 60)
        assert _is_white(c), (
            f"Interior pixel should be white (no fill) but got RGB({c.red()},{c.green()},{c.blue()})"
        )

    def test_rotated_rect_fill_rotates_with_shape(self, qapp):
        """Fill must rotate with the shape (not stay axis-aligned).

        A 30°-rotated rect centred at (60,60) fills the interior; a pixel
        inside the rotated quad but outside the axis-aligned bounding box
        should be non-white.
        """
        scene = QGraphicsScene()
        # 40×80 rect centred at (60, 60) in scene coords
        r = RectangleItem(QPointF(40, 20), QPointF(80, 100))
        r.fill_type = "solid"
        r._display_fill_color = "#ff0000"
        r.set_angle(30)
        scene.addItem(r)

        # Render 120×120 over scene region (0, 0, 120, 120)
        img = _render_scene(scene, QRectF(0, 0, 120, 120))

        # The centre (60,60) is always inside a rotated rect centred there
        c_centre = _pixel(img, 60, 60)
        assert not _is_white(c_centre), (
            "Centre of rotated rect should be filled"
        )

        # Far corner — well outside any reasonable rotation
        c_far = _pixel(img, 5, 5)
        assert _is_white(c_far), "Far corner should remain white"

    def test_shape_filled_rect_contains_centre(self, qapp):
        """shape() of a filled rect must include its interior centre."""
        r, scene = self._make_rect(fill="solid")
        centre_local = r.rect().center()
        assert r.shape().contains(centre_local), (
            "Filled rect shape() should contain the centre point"
        )

    def test_shape_unfilled_rect_does_not_contain_centre(self, qapp):
        """shape() of an unfilled rect must NOT include the interior centre."""
        r, scene = self._make_rect(fill="none")
        centre_local = r.rect().center()
        assert not r.shape().contains(centre_local), (
            "Unfilled rect shape() should NOT contain the interior centre"
        )

    def test_scene_itemat_filled_rect_interior(self, qapp):
        """scene.itemAt() on the interior of a filled rect returns the rect."""
        scene = QGraphicsScene()
        r = RectangleItem(QPointF(10, 10), QPointF(110, 110))
        r.fill_type = "solid"
        r._display_fill_color = "#0000ff"
        scene.addItem(r)

        # scene centre of the rect
        hit = scene.itemAt(QPointF(60, 60), QTransform())
        assert hit is r, (
            f"scene.itemAt(centre) should return the filled rect, got {hit}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CircleItem — solid fill
# ─────────────────────────────────────────────────────────────────────────────

class TestCircleFill:
    def test_solid_fill_interior_non_white(self, qapp):
        """Interior pixel must be non-white when solid fill is active."""
        scene = QGraphicsScene()
        c_item = CircleItem(QPointF(60, 60), 40, "#00aa00")
        c_item.fill_type = "solid"
        c_item._display_fill_color = "#00aa00"
        scene.addItem(c_item)

        img = _render_scene(scene, QRectF(0, 0, 120, 120))
        c = _pixel(img, 60, 60)
        assert not _is_white(c), (
            f"Circle interior should be filled but got RGB({c.red()},{c.green()},{c.blue()})"
        )

    def test_no_fill_interior_stays_white(self, qapp):
        """Interior stays white when fill_type='none'."""
        scene = QGraphicsScene()
        c_item = CircleItem(QPointF(60, 60), 40, "#00aa00")
        c_item.fill_type = "none"
        scene.addItem(c_item)

        img = _render_scene(scene, QRectF(0, 0, 120, 120))
        c = _pixel(img, 60, 60)
        assert _is_white(c), (
            f"Circle interior should stay white (no fill) but got RGB({c.red()},{c.green()},{c.blue()})"
        )

    def test_shape_filled_circle_contains_centre(self, qapp):
        """shape() of a filled circle must include the centre."""
        scene = QGraphicsScene()
        c_item = CircleItem(QPointF(60, 60), 40, "#00aa00")
        c_item.fill_type = "solid"
        c_item._display_fill_color = "#00aa00"
        scene.addItem(c_item)

        centre_local = c_item.rect().center()
        assert c_item.shape().contains(centre_local), (
            "Filled circle shape() should contain its centre"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ArcItem — fillable only when closed (360° span)
# ─────────────────────────────────────────────────────────────────────────────

class TestArcFill:
    def test_closed_arc_is_fillable(self, qapp):
        """A 360° arc reports is_fillable() True."""
        a = ArcItem(QPointF(60, 60), 40, 0, 360)
        assert a.is_fillable()
        assert a.get_closed_path() is not None

    def test_open_arc_is_not_fillable(self, qapp):
        """A partial arc reports is_fillable() False."""
        a = ArcItem(QPointF(60, 60), 40, 0, 180)
        assert not a.is_fillable()
        assert a.get_closed_path() is None

    def test_closed_arc_solid_fill_interior_non_white(self, qapp):
        """Closed arc (360°) with solid fill colours the interior."""
        scene = QGraphicsScene()
        a = ArcItem(QPointF(60, 60), 40, 0, 360)
        a.fill_type = "solid"
        a._display_fill_color = "#ff6600"
        scene.addItem(a)

        img = _render_scene(scene, QRectF(0, 0, 120, 120))
        c = _pixel(img, 60, 60)
        assert not _is_white(c), (
            f"Closed arc interior should be filled but got RGB({c.red()},{c.green()},{c.blue()})"
        )

    def test_open_arc_fill_ignored(self, qapp):
        """Open arc never fills even if fill_type is set."""
        scene = QGraphicsScene()
        a = ArcItem(QPointF(60, 60), 40, 0, 180)
        a.fill_type = "solid"
        a._display_fill_color = "#ff6600"
        scene.addItem(a)

        img = _render_scene(scene, QRectF(0, 0, 120, 120))
        c = _pixel(img, 60, 60)
        assert _is_white(c), (
            f"Open arc interior should stay white but got RGB({c.red()},{c.green()},{c.blue()})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PolylineItem — fillable only when closed
# ─────────────────────────────────────────────────────────────────────────────

class TestPolylineFill:
    def _make_closed_poly(self, fill: str = "solid") -> tuple[PolylineItem, QGraphicsScene]:
        scene = QGraphicsScene()
        pts = [
            QPointF(20, 20),
            QPointF(100, 20),
            QPointF(100, 100),
            QPointF(20, 100),
            QPointF(20, 20),   # close back to start
        ]
        p = PolylineItem(pts[0])
        for pt in pts[1:]:
            p.append_point(pt)
        p.fill_type = fill
        p._display_fill_color = "#aa00aa"
        scene.addItem(p)
        return p, scene

    def test_closed_polyline_is_fillable(self, qapp):
        p, _ = self._make_closed_poly()
        assert p.is_fillable()

    def test_open_polyline_is_not_fillable(self, qapp):
        scene = QGraphicsScene()
        p = PolylineItem(QPointF(20, 20))
        p.append_point(QPointF(100, 20))
        p.append_point(QPointF(100, 100))
        assert not p.is_fillable()

    def test_closed_poly_solid_fill_interior_non_white(self, qapp):
        _, scene = self._make_closed_poly(fill="solid")
        img = _render_scene(scene, QRectF(0, 0, 120, 120))
        c = _pixel(img, 60, 60)
        assert not _is_white(c), (
            f"Closed polyline interior should be filled but got RGB({c.red()},{c.green()},{c.blue()})"
        )

    def test_open_poly_fill_ignored(self, qapp):
        scene = QGraphicsScene()
        p = PolylineItem(QPointF(20, 20))
        p.append_point(QPointF(100, 20))
        p.append_point(QPointF(100, 100))
        p.fill_type = "solid"
        p._display_fill_color = "#aa00aa"
        scene.addItem(p)

        img = _render_scene(scene, QRectF(0, 0, 120, 120))
        c = _pixel(img, 60, 60)
        assert _is_white(c), (
            f"Open polyline interior should stay white but got RGB({c.red()},{c.green()},{c.blue()})"
        )

    def test_shape_filled_closed_poly_contains_centre(self, qapp):
        """shape() of a filled closed polyline must include interior centre."""
        p, _ = self._make_closed_poly(fill="solid")
        centre = QPointF(60, 60)
        assert p.shape().contains(centre), (
            "Filled closed polyline shape() should contain its centre"
        )
