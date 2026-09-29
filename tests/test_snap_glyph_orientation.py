"""Snap marker glyphs lie along the snapped geometry (snapping-engine.md §9.2).

Real ``OsnapResult`` with real source items, painted into a real ``QImage``;
the orientation guards assert on PIXELS (a 45° endpoint square renders as a
diamond), never on the painter's own angle.
"""
import math

import pytest
from PyQt6.QtCore import QLineF, QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QTransform
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsSimpleTextItem,
)

from firepro3d.snap_engine import (
    OsnapResult, SNAP_COLORS, paint_snap_indicator, snap_tangent_deg,
)

C = 100          # glyph centre in the image (viewport px)
S = 6            # glyph half-size (paint_snap_indicator's ``s``)


def _same_line(deg, want, tol=1e-6):
    """Headings are defined mod 180 (a→b vs b→a)."""
    d = (deg - want) % 180.0
    return min(d, 180.0 - d) < tol


# ── snap_tangent_deg ──────────────────────────────────────────────────────
def test_line_item_tangent(qapp):
    ln = QGraphicsLineItem(0, 0, 100, 100)
    r = OsnapResult(point=QPointF(100, 100), snap_type="endpoint", source_item=ln)
    assert _same_line(snap_tangent_deg(r), 45.0)


def test_line_item_tangent_honours_item_transform(qapp):
    ln = QGraphicsLineItem(0, 0, 100, 0)
    ln.setRotation(30)
    end = ln.mapToScene(QPointF(100, 0))
    r = OsnapResult(point=end, snap_type="endpoint", source_item=ln)
    assert _same_line(snap_tangent_deg(r), 30.0)


def test_path_corner_first_leg_wins(qapp):
    p = QPainterPath(QPointF(0, 0))
    p.lineTo(100, 0)
    p.lineTo(100, 100)
    it = QGraphicsPathItem(p)
    corner = OsnapResult(point=QPointF(100, 0), snap_type="endpoint", source_item=it)
    assert _same_line(snap_tangent_deg(corner), 0.0)
    mid2 = OsnapResult(point=QPointF(100, 50), snap_type="midpoint", source_item=it)
    assert _same_line(snap_tangent_deg(mid2), 90.0)


def test_ellipse_quadrant_is_tangent(qapp):
    e = QGraphicsEllipseItem(QRectF(-50, -50, 100, 100))
    top = OsnapResult(point=QPointF(0, -50), snap_type="quadrant", source_item=e)
    right = OsnapResult(point=QPointF(50, 0), snap_type="quadrant", source_item=e)
    # flattened curve: within a few degrees of the true tangent
    assert _same_line(snap_tangent_deg(top), 0.0, tol=3.0)
    assert _same_line(snap_tangent_deg(right), 90.0, tol=3.0)


def test_source_lines_take_precedence(qapp):
    ln = QGraphicsLineItem(0, 0, 100, 0)
    r = OsnapResult(point=QPointF(0, 0), snap_type="intersection",
                    source_item=ln,
                    source_lines=[QLineF(-10, -10, 10, 10), QLineF(-10, 10, 10, -10)])
    assert _same_line(snap_tangent_deg(r), 45.0)          # first line wins the tie


def test_fallback_is_item_scene_rotation(qapp):
    t = QGraphicsSimpleTextItem("A")
    t.setRotation(25)
    r = OsnapResult(point=QPointF(0, 0), snap_type="endpoint", source_item=t)
    assert snap_tangent_deg(r) == pytest.approx(25.0)


def test_no_source_is_none(qapp):
    assert snap_tangent_deg(OsnapResult(point=QPointF(), snap_type="nearest")) is None


# ── rendered orientation (pixels) ─────────────────────────────────────────
class _View:
    """Scene origin at image (C, C); float + int mappers like a real view."""

    def viewportTransform(self):  # noqa: N802 — Qt casing
        return QTransform().translate(C, C)

    def mapFromScene(self, pt):  # noqa: N802
        return QPointF(pt.x() + C, pt.y() + C)


def _render(result):
    img = QImage(2 * C, 2 * C, QImage.Format.Format_ARGB32)
    img.fill(QColor("black"))
    p = QPainter(img)
    paint_snap_indicator(p, _View(), result)
    p.end()
    return img


def _lit(img, x, y, color, r=1):
    """Any pixel within *r* of (x, y) close to *color*."""
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            c = QColor(img.pixel(int(x) + dx, int(y) + dy))
            if (abs(c.red() - color.red()) < 70 and abs(c.green() - color.green()) < 70
                    and abs(c.blue() - color.blue()) < 70):
                return True
    return False


def _endpoint_on(deg):
    """Endpoint snap at the scene origin on a long line at *deg*."""
    r = math.radians(deg)
    ln = QGraphicsLineItem(0, 0, 400 * math.cos(r), 400 * math.sin(r))
    # no trace clutter near the glyph corners: trace goes one way only
    return OsnapResult(point=QPointF(0, 0), snap_type="endpoint", source_item=ln)


def test_endpoint_square_on_45deg_line_renders_as_diamond(qapp):
    img = _render(_endpoint_on(-135))           # line runs up-left, away from probes
    col = QColor(SNAP_COLORS["endpoint"])
    d = S * math.sqrt(2)
    assert _lit(img, C + d - 1, C, col), "diamond vertex on +x axis"
    assert _lit(img, C, C + d - 1, col), "diamond vertex on +y axis"
    assert not _lit(img, C + S, C + S, col, r=0), "no axis-aligned square corner"


def test_endpoint_square_on_horizontal_line_stays_axis_aligned(qapp):
    img = _render(_endpoint_on(180))            # trace runs left only
    col = QColor(SNAP_COLORS["endpoint"])
    assert _lit(img, C + S, C + S, col), "axis-aligned corner"
    assert not _lit(img, C + S * math.sqrt(2) + 1, C, col, r=0)


def test_perpendicular_glyph_leg_follows_line(qapp):
    """⊥ legs lie along the line and its normal: on a 30° line the corner's
    outer square edges are rotated, so the axis-aligned corner is dark."""
    r = math.radians(-150)
    ln = QGraphicsLineItem(0, 0, 400 * math.cos(r), 400 * math.sin(r))
    res = OsnapResult(point=QPointF(0, 0), snap_type="perpendicular", source_item=ln)
    img = _render(res)
    col = QColor(SNAP_COLORS["perpendicular"])
    assert not _lit(img, C + S, C + S, col, r=0)
    assert any(_lit(img, C + S * math.cos(math.radians(a)) * 1.2,
                    C + S * math.sin(math.radians(a)) * 1.2, col)
               for a in range(0, 360, 15))


@pytest.mark.parametrize("zoom", [1.0, 0.05])
def test_real_model_view_rotates_glyph_at_zoom(shown_model_view, zoom):
    """Real ``Model_View`` foreground pass (float viewportTransform), near and
    far zoomed out: a 45° endpoint still renders as a diamond."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    view, scene = shown_model_view
    view.resetTransform()
    view.scale(zoom, zoom)
    view.centerOn(0, 0)
    ln = QGraphicsLineItem(0, 0, -4000, -4000)        # up-left, away from probes
    scene._snap_result = OsnapResult(point=QPointF(0, 0), snap_type="endpoint",
                                     source_item=ln)
    view.viewport().update()
    QApplication.processEvents()
    img = QImage(view.viewport().size(), QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.black)
    p = QPainter(img)
    view.render(p)
    p.end()
    c = view.mapFromScene(QPointF(0, 0))
    col = QColor(SNAP_COLORS["endpoint"])
    d = S * math.sqrt(2)
    assert _lit(img, c.x() + d - 1, c.y(), col)
    assert not _lit(img, c.x() + S, c.y() + S, col, r=0)
