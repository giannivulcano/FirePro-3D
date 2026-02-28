"""
construction_geometry.py
=========================
Reference-geometry items for FireFlow Pro.

ConstructionLine  — an "infinite" dashed cyan line placed by two clicks.
PolylineItem      — a multi-click open polyline on the active user layer.
"""

from __future__ import annotations

import math

from PyQt6.QtWidgets import (
    QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsEllipseItem,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor, QPainterPath, QBrush


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_CONSTRUCTION_COLOR = "#00aaff"     # cyan-blue
_CONSTRUCTION_EXTEND = 100_000      # px beyond the two anchor points (effectively infinite)


# ─────────────────────────────────────────────────────────────────────────────
# ConstructionLine
# ─────────────────────────────────────────────────────────────────────────────

class ConstructionLine(QGraphicsLineItem):
    """
    An infinite-looking dashed reference line.

    Parameters
    ----------
    pt1, pt2 : QPointF
        The two anchor points that define the direction of the line.
        The drawn line is extended far beyond both points so it appears
        to extend to the edge of the canvas.
    """

    def __init__(self, pt1: QPointF, pt2: QPointF):
        super().__init__()
        self._pt1 = pt1
        self._pt2 = pt2

        pen = QPen(QColor(_CONSTRUCTION_COLOR))
        pen.setWidth(1)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)       # stays 1 viewport pixel at any zoom
        self.setPen(pen)

        self.setZValue(-5)          # drawn behind all model items
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        self._recompute_line()

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def pt1(self) -> QPointF:
        return self._pt1

    @property
    def pt2(self) -> QPointF:
        return self._pt2

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return a plain dict for JSON serialisation."""
        return {
            "type": "construction_line",
            "pt1":  [self._pt1.x(), self._pt1.y()],
            "pt2":  [self._pt2.x(), self._pt2.y()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConstructionLine":
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        return cls(pt1, pt2)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _recompute_line(self):
        """Extend the line segment far beyond pt1 and pt2."""
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            # Degenerate: draw a tiny horizontal stub
            self.setLine(self._pt1.x() - 1, self._pt1.y(),
                         self._pt1.x() + 1, self._pt1.y())
            return
        # Unit vector
        ux, uy = dx / length, dy / length
        x1 = self._pt1.x() - ux * _CONSTRUCTION_EXTEND
        y1 = self._pt1.y() - uy * _CONSTRUCTION_EXTEND
        x2 = self._pt2.x() + ux * _CONSTRUCTION_EXTEND
        y2 = self._pt2.y() + uy * _CONSTRUCTION_EXTEND
        self.setLine(x1, y1, x2, y2)


# ─────────────────────────────────────────────────────────────────────────────
# PolylineItem
# ─────────────────────────────────────────────────────────────────────────────

class PolylineItem(QGraphicsPathItem):
    """
    A multi-segment open polyline drawn by successive mouse clicks.

    The path is rebuilt each time a new point is appended so the
    partial line is always visible in the scene.

    Parameters
    ----------
    color : str | QColor
        Stroke color, typically derived from the active user layer.
    """

    def __init__(self, start: QPointF, color: str | QColor = "#ffffff"):
        super().__init__()
        self._points: list[QPointF] = [start]

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidth(1)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setZValue(1)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        self._rebuild_path()

    # ── Public API ────────────────────────────────────────────────────────────

    def append_point(self, pt: QPointF):
        """Add the next vertex and rebuild the path."""
        self._points.append(pt)
        self._rebuild_path()

    def update_preview(self, pt: QPointF):
        """Temporarily extend path to *pt* for the cursor-follow preview."""
        # Rebuild with the tentative last point
        path = QPainterPath(self._points[0])
        for p in self._points[1:]:
            path.lineTo(p)
        path.lineTo(pt)
        self.setPath(path)

    def finalize(self):
        """Snap the path to the committed points and stop accepting input."""
        self._rebuild_path()

    # ── Grip protocol ─────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """Return all vertex positions as grip handles (one per vertex)."""
        return list(self._points)

    def apply_grip(self, index: int, pos: QPointF):
        """Move vertex *index* to *pos* and rebuild the path."""
        if 0 <= index < len(self._points):
            self._points[index] = pos
            self._rebuild_path()

    def translate(self, dx: float, dy: float):
        """Move all vertices by (dx, dy)."""
        self._points = [QPointF(p.x() + dx, p.y() + dy) for p in self._points]
        self._rebuild_path()

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        pen_color = self.pen().color().name()
        return {
            "type":   "polyline",
            "color":  pen_color,
            "points": [[p.x(), p.y()] for p in self._points],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PolylineItem":
        pts = [QPointF(p[0], p[1]) for p in data["points"]]
        color = data.get("color", "#ffffff")
        obj = cls(pts[0], color)
        for p in pts[1:]:
            obj.append_point(p)
        return obj

    # ── Internal ─────────────────────────────────────────────────────────────

    def _rebuild_path(self):
        if not self._points:
            return
        path = QPainterPath(self._points[0])
        for p in self._points[1:]:
            path.lineTo(p)
        self.setPath(path)


# ─────────────────────────────────────────────────────────────────────────────
# LineItem  — finite 2-point line (AutoCAD-style Line tool)
# ─────────────────────────────────────────────────────────────────────────────

class LineItem(QGraphicsLineItem):
    """
    A finite 2-point line with configurable colour and lineweight.

    Parameters
    ----------
    pt1, pt2    : QPointF  — start and end points
    color       : str | QColor — stroke colour (default white for dark theme)
    lineweight  : float — cosmetic pixel width (default 1.0)
    """

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._pt1 = pt1
        self._pt2 = pt2
        self.user_layer: str = "0"

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)

        self.setZValue(1)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        self.setLine(pt1.x(), pt1.y(), pt2.x(), pt2.y())

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":        "draw_line",
            "pt1":         [self._pt1.x(), self._pt1.y()],
            "pt2":         [self._pt2.x(), self._pt2.y()],
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
            "user_layer":  self.user_layer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LineItem":
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0))
        obj.user_layer = data.get("user_layer", "0")
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """Return [pt1, midpoint, pt2] as grip handles."""
        mid = QPointF((self._pt1.x() + self._pt2.x()) / 2,
                      (self._pt1.y() + self._pt2.y()) / 2)
        return [self._pt1, mid, self._pt2]

    def apply_grip(self, index: int, pos: QPointF):
        """Move a grip handle to *pos*.  index 0=pt1, 1=midpoint, 2=pt2."""
        if index == 0:
            self._pt1 = pos
        elif index == 1:
            # Mid-grip: translate entire line
            dx = pos.x() - (self._pt1.x() + self._pt2.x()) / 2
            dy = pos.y() - (self._pt1.y() + self._pt2.y()) / 2
            self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
            self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        elif index == 2:
            self._pt2 = pos
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    def translate(self, dx: float, dy: float):
        """Move the entire line by (dx, dy)."""
        self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
        self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())


# ─────────────────────────────────────────────────────────────────────────────
# RectangleItem  — axis-aligned rectangle (two corner clicks)
# ─────────────────────────────────────────────────────────────────────────────

class RectangleItem(QGraphicsRectItem):
    """
    An axis-aligned rectangle defined by two opposite corners.

    Parameters
    ----------
    pt1, pt2    : QPointF — opposite corners (order does not matter)
    color       : str | QColor
    lineweight  : float — cosmetic pixel width
    """

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        rect = QRectF(pt1, pt2).normalized()
        super().__init__(rect)
        self.user_layer: str = "0"

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setZValue(1)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        r = self.rect()
        return {
            "type":        "draw_rectangle",
            "x":           r.x(),
            "y":           r.y(),
            "w":           r.width(),
            "h":           r.height(),
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
            "user_layer":  self.user_layer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RectangleItem":
        pt1 = QPointF(data["x"], data["y"])
        pt2 = QPointF(data["x"] + data["w"], data["y"] + data["h"])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0))
        obj.user_layer = data.get("user_layer", "0")
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────
    # Grip indices (clockwise from top-left):
    #   0=TL  1=TM  2=TR  3=RM  4=BR  5=BM  6=BL  7=LM  8=Centre

    def grip_points(self) -> list[QPointF]:
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        return [
            QPointF(r.left(),  r.top()),                  # 0 TL
            QPointF(cx,        r.top()),                  # 1 TM
            QPointF(r.right(), r.top()),                  # 2 TR
            QPointF(r.right(), cy),                       # 3 RM
            QPointF(r.right(), r.bottom()),               # 4 BR
            QPointF(cx,        r.bottom()),               # 5 BM
            QPointF(r.left(),  r.bottom()),               # 6 BL
            QPointF(r.left(),  cy),                       # 7 LM
            QPointF(cx,        cy),                       # 8 Centre
        ]

    def apply_grip(self, index: int, pos: QPointF):
        """Resize or translate the rectangle by dragging one of its 9 grips."""
        r = self.rect()
        l, t, ri, b = r.left(), r.top(), r.right(), r.bottom()

        if   index == 0:  new_r = QRectF(QPointF(pos.x(), pos.y()), QPointF(ri,  b )).normalized()
        elif index == 1:  new_r = QRectF(QPointF(l,  pos.y()), QPointF(ri,  b )).normalized()
        elif index == 2:  new_r = QRectF(QPointF(l,  pos.y()), QPointF(pos.x(), b )).normalized()
        elif index == 3:  new_r = QRectF(QPointF(l,  t ), QPointF(pos.x(), b )).normalized()
        elif index == 4:  new_r = QRectF(QPointF(l,  t ), QPointF(pos.x(), pos.y())).normalized()
        elif index == 5:  new_r = QRectF(QPointF(l,  t ), QPointF(ri,  pos.y())).normalized()
        elif index == 6:  new_r = QRectF(QPointF(pos.x(), t ), QPointF(ri,  pos.y())).normalized()
        elif index == 7:  new_r = QRectF(QPointF(pos.x(), t ), QPointF(ri,  b )).normalized()
        elif index == 8:
            # Centre grip → translate
            dx, dy = pos.x() - r.center().x(), pos.y() - r.center().y()
            new_r = r.translated(dx, dy)
        else:
            return
        self.setRect(new_r)

    def translate(self, dx: float, dy: float):
        self.setRect(self.rect().translated(dx, dy))


# ─────────────────────────────────────────────────────────────────────────────
# CircleItem  — circle defined by centre + edge point
# ─────────────────────────────────────────────────────────────────────────────

class CircleItem(QGraphicsEllipseItem):
    """
    A circle defined by its centre and one point on the circumference.

    Parameters
    ----------
    center  : QPointF — circle centre in scene coordinates
    radius  : float   — radius in scene units
    color   : str | QColor
    lineweight : float — cosmetic pixel width
    """

    def __init__(self, center: QPointF, radius: float,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        self._center = center
        self._radius = radius
        r = radius
        super().__init__(center.x() - r, center.y() - r, 2 * r, 2 * r)
        self.user_layer: str = "0"

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setZValue(1)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":        "draw_circle",
            "cx":          self._center.x(),
            "cy":          self._center.y(),
            "radius":      self._radius,
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
            "user_layer":  self.user_layer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CircleItem":
        center = QPointF(data["cx"], data["cy"])
        obj = cls(center, data["radius"],
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
        obj.user_layer = data.get("user_layer", "0")
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────
    # Grip indices: 0=centre  1=right  2=top  3=left  4=bottom

    def grip_points(self) -> list[QPointF]:
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        return [
            QPointF(cx,     cy),      # 0 centre
            QPointF(cx + r, cy),      # 1 right  (0°)
            QPointF(cx,     cy - r),  # 2 top    (90°)
            QPointF(cx - r, cy),      # 3 left   (180°)
            QPointF(cx,     cy + r),  # 4 bottom (270°)
        ]

    def apply_grip(self, index: int, pos: QPointF):
        """Translate (index 0) or resize (index 1-4)."""
        import math as _math
        if index == 0:
            self._center = pos
        else:
            self._radius = _math.hypot(
                pos.x() - self._center.x(),
                pos.y() - self._center.y(),
            )
            if self._radius < 1:
                self._radius = 1
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)
