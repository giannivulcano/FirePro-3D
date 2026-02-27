"""
construction_geometry.py
=========================
Reference-geometry items for FireFlow Pro.

ConstructionLine  — an "infinite" dashed cyan line placed by two clicks.
PolylineItem      — a multi-click open polyline on the active user layer.
"""

from __future__ import annotations

import math

from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPathItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QColor, QPainterPath


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
        self.setBrush(Qt.BrushStyle.NoBrush)

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
