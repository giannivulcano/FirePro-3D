"""
construction_geometry.py
=========================
Reference-geometry items for FirePro 3D.

ConstructionLine  — an "infinite" dashed cyan line placed by two clicks.
PolylineItem      — a multi-click open polyline on the active user layer.
"""

from __future__ import annotations

import math

from PyQt6.QtWidgets import (
    QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsEllipseItem,
    QStyle,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor, QPainterPath, QBrush, QPainterPathStroker, QPolygonF
from .constants import DEFAULT_USER_LAYER
from .constants import DEFAULT_LEVEL


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_CONSTRUCTION_COLOR = "#00aaff"     # cyan-blue
_CONSTRUCTION_EXTEND = 100_000      # px beyond the two anchor points (effectively infinite)


def _scene_hit_width(item) -> float:
    """Viewport-scale-aware hit width — always ~10 screen pixels regardless of zoom.

    Cosmetic pens have a fixed screen-pixel width but their shape() is in scene
    units.  At high zoom the two coincide; at low zoom a 1px cosmetic pen maps to
    a tiny fraction of a scene unit, making the item nearly impossible to click.
    This helper returns a scene-unit width that is always ~10 screen pixels.
    """
    sc = item.scene()
    if sc:
        views = sc.views()
        if views:
            scale = views[0].transform().m11()
            return max(2.0, 10.0 / max(scale, 1e-6))
    return 6.0


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
        self.level: str = DEFAULT_LEVEL

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
            "level": self.level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConstructionLine":
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        obj = cls(pt1, pt2)
        obj.level = data.get("level", DEFAULT_LEVEL)
        return obj

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Type":  {"type": "label",     "value": "Construction Line"},
            "pt1":   {"type": "label",     "value": f"({self._pt1.x():.1f}, {self._pt1.y():.1f})"},
            "pt2":   {"type": "label",     "value": f"({self._pt2.x():.1f}, {self._pt2.y():.1f})"},
            "Level": {"type": "level_ref", "value": self.level},
        }

    def set_property(self, key: str, value):
        if key == "Level":
            self.level = str(value)

    # ── Grips ─────────────────────────────────────────────────────────────

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
        self._recompute_line()

    # ── Move ──────────────────────────────────────────────────────────────

    def translate(self, dx: float, dy: float):
        """Move both anchor points by (dx, dy) and recompute."""
        self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
        self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        self._recompute_line()

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

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
        if self.isSelected():
            ln = self.line()
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawLine(ln.p1(), ln.p2())

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a viewport-scale-aware stroked path so the line is clickable."""
        ln = self.line()
        path = QPainterPath()
        path.moveTo(ln.p1())
        path.lineTo(ln.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path)


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
    lineweight : float
        Cosmetic pixel width (default 1.0).
    """

    def __init__(self, start: QPointF, color: str | QColor = "#ffffff",
                 lineweight: float = 1.0):
        super().__init__()
        self._points: list[QPointF] = [start]
        self.user_layer: str = DEFAULT_USER_LAYER
        self.level: str = DEFAULT_LEVEL

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setZValue(1)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        self._rebuild_path()

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Type": {"type": "label", "value": "Polyline"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
            "Vertices": {"type": "label", "value": str(len(self._points))},
            "Layer": {"type": "label", "value": self.user_layer},
        }

    def set_property(self, key: str, value):
        if key == "Layer":
            self.user_layer = value

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

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Return True if the first and last vertices coincide (within 1e-3)."""
        if len(self._points) < 3:
            return False
        first, last = self._points[0], self._points[-1]
        return (abs(first.x() - last.x()) < 1e-3 and
                abs(first.y() - last.y()) < 1e-3)

    def get_closed_path(self) -> QPainterPath | None:
        """Return a QPainterPath polygon if the polyline is closed, else None."""
        if not self.is_closed():
            return None
        poly = QPolygonF(self._points)
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        return path

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        pen_color = self.pen().color().name()
        return {
            "type":       "polyline",
            "color":      pen_color,
            "lineweight": self.pen().widthF(),
            "points":     [[p.x(), p.y()] for p in self._points],
            "user_layer": self.user_layer,
            "level":      self.level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PolylineItem":
        pts = [QPointF(p[0], p[1]) for p in data["points"]]
        color = data.get("color", "#ffffff")
        lw = data.get("lineweight", 1.0)
        obj = cls(pts[0], color, lw)
        for p in pts[1:]:
            obj.append_point(p)
        obj.user_layer = data.get("user_layer", "0")
        obj.level = data.get("level", DEFAULT_LEVEL)
        return obj

    # ── Internal ─────────────────────────────────────────────────────────────

    def _rebuild_path(self):
        if not self._points:
            return
        path = QPainterPath(self._points[0])
        for p in self._points[1:]:
            path.lineTo(p)
        self.setPath(path)

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
        if self.isSelected():
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawPath(self.path())

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a viewport-scale-aware stroked path so thin polylines are clickable."""
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(self.path())


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
        self.user_layer: str = DEFAULT_USER_LAYER
        self.level: str = DEFAULT_LEVEL

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)

        self.setZValue(1)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        self.setLine(pt1.x(), pt1.y(), pt2.x(), pt2.y())

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Type": {"type": "label", "value": "Line"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
            "Length": {"type": "label", "value": f"{self.line().length():.1f}"},
            "Layer": {"type": "label", "value": self.user_layer},
        }

    def set_property(self, key: str, value):
        if key == "Layer":
            self.user_layer = value

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":        "draw_line",
            "pt1":         [self._pt1.x(), self._pt1.y()],
            "pt2":         [self._pt2.x(), self._pt2.y()],
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
            "user_layer":  self.user_layer,
            "level":       self.level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LineItem":
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0))
        obj.user_layer = data.get("user_layer", "0")
        obj.level = data.get("level", DEFAULT_LEVEL)
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

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Lines are never closed shapes."""
        return False

    def get_closed_path(self) -> None:
        """Lines have no closed path."""
        return None

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
        if self.isSelected():
            ln = self.line()
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawLine(ln.p1(), ln.p2())

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a viewport-scale-aware stroked path so the line is easily clickable."""
        path = QPainterPath()
        path.moveTo(self._pt1)
        path.lineTo(self._pt2)
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path)


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
        self.user_layer: str = DEFAULT_USER_LAYER
        self.level: str = DEFAULT_LEVEL

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setZValue(1)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        r = self.rect()
        return {
            "Type": {"type": "label", "value": "Rectangle"},
            "Width": {"type": "label", "value": f"{r.width():.1f}"},
            "Height": {"type": "label", "value": f"{r.height():.1f}"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
            "Layer": {"type": "label", "value": self.user_layer},
        }

    def set_property(self, key: str, value):
        if key == "Layer":
            self.user_layer = value

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
            "level":       self.level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RectangleItem":
        pt1 = QPointF(data["x"], data["y"])
        pt2 = QPointF(data["x"] + data["w"], data["y"] + data["h"])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0))
        obj.user_layer = data.get("user_layer", "0")
        obj.level = data.get("level", DEFAULT_LEVEL)
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

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Rectangles are always closed shapes."""
        return True

    def get_closed_path(self) -> QPainterPath:
        """Return a QPainterPath rectangle for hatching / fill operations."""
        path = QPainterPath()
        path.addRect(self.rect())
        return path

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
        if self.isSelected():
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawRect(self.rect())

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a stroked outline path so the rectangle border is clickable."""
        path = QPainterPath()
        path.addRect(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path)


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
        self.user_layer: str = DEFAULT_USER_LAYER
        self.level: str = DEFAULT_LEVEL

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setZValue(1)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Type": {"type": "label", "value": "Circle"},
            "Centre": {"type": "label", "value": f"({self._center.x():.1f}, {self._center.y():.1f})"},
            "Radius": {"type": "label", "value": f"{self._radius:.1f}"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
            "Layer": {"type": "label", "value": self.user_layer},
        }

    def set_property(self, key: str, value):
        if key == "Layer":
            self.user_layer = value

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
            "level":       self.level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CircleItem":
        center = QPointF(data["cx"], data["cy"])
        obj = cls(center, data["radius"],
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
        obj.user_layer = data.get("user_layer", "0")
        obj.level = data.get("level", DEFAULT_LEVEL)
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

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Circles are always closed shapes."""
        return True

    def get_closed_path(self) -> QPainterPath:
        """Return a QPainterPath ellipse for hatching / fill operations."""
        path = QPainterPath()
        path.addEllipse(self.rect())
        return path

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
        if self.isSelected():
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawEllipse(self.rect())

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a stroked ellipse outline path so the circle border is clickable."""
        path = QPainterPath()
        path.addEllipse(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path)


# ─────────────────────────────────────────────────────────────────────────────
# ArcItem
# ─────────────────────────────────────────────────────────────────────────────

class ArcItem(QGraphicsPathItem):
    """
    A circular arc defined by centre, radius, start angle and span angle.
    Angles are in degrees, measured counter-clockwise from the +X axis
    (Qt convention: positive span = CCW, angles in 1/16ths internally but
    we use QPainterPath.arcTo which takes plain degrees).
    """

    def __init__(self, center: QPointF, radius: float,
                 start_deg: float, span_deg: float,
                 color: str = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._center = QPointF(center)
        self._radius = max(radius, 0.01)
        self._start_deg = start_deg
        self._span_deg = span_deg
        self.user_layer: str = DEFAULT_USER_LAYER
        self.level: str = DEFAULT_LEVEL
        pen = QPen(QColor(color), lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlags(
            self.GraphicsItemFlag.ItemIsSelectable |
            self.GraphicsItemFlag.ItemIsMovable
        )
        self._rebuild_path()

    def _rebuild_path(self):
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        path = QPainterPath()
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        path.arcMoveTo(rect, self._start_deg)
        path.arcTo(rect, self._start_deg, self._span_deg)
        self.setPath(path)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":       "arc",
            "cx":         self._center.x(),
            "cy":         self._center.y(),
            "radius":     self._radius,
            "start_deg":  self._start_deg,
            "span_deg":   self._span_deg,
            "color":      self.pen().color().name(),
            "lineweight": self.pen().widthF(),
            "user_layer": self.user_layer,
            "level":      self.level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArcItem":
        center = QPointF(data["cx"], data["cy"])
        obj = cls(center, data["radius"], data["start_deg"], data["span_deg"],
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
        obj.user_layer = data.get("user_layer", "0")
        obj.level = data.get("level", DEFAULT_LEVEL)
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        sa = math.radians(self._start_deg)
        ea = math.radians(self._start_deg + self._span_deg)
        return [
            QPointF(cx, cy),                                    # 0 centre
            QPointF(cx + r * math.cos(sa), cy - r * math.sin(sa)),  # 1 start
            QPointF(cx + r * math.cos(ea), cy - r * math.sin(ea)),  # 2 end
        ]

    def apply_grip(self, index: int, pos: QPointF):
        if index == 0:
            self._center = pos
        elif index == 1:
            # Move start point — change radius and start angle
            dx = pos.x() - self._center.x()
            dy = pos.y() - self._center.y()
            self._radius = max(math.hypot(dx, dy), 0.01)
            self._start_deg = math.degrees(math.atan2(-dy, dx))
        elif index == 2:
            # Move end point — change span angle
            dx = pos.x() - self._center.x()
            dy = pos.y() - self._center.y()
            end_deg = math.degrees(math.atan2(-dy, dx))
            self._span_deg = (end_deg - self._start_deg) % 360
            if self._span_deg == 0:
                self._span_deg = 360
        self._rebuild_path()

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self._rebuild_path()

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Return True if the arc spans a full 360 degrees (i.e. a full circle)."""
        return abs(self._span_deg) >= 360

    def get_closed_path(self) -> QPainterPath | None:
        """Return a QPainterPath ellipse if the arc is a full circle, else None."""
        if not self.is_closed():
            return None
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        path = QPainterPath()
        path.addEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        return path

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
        if self.isSelected():
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawPath(self.path())

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(self.path())


# ─────────────────────────────────────────────────────────────────────────────
# GeometryTemplate — pre-placement defaults for geometry tools
# ─────────────────────────────────────────────────────────────────────────────

class GeometryTemplate:
    """Pre-placement template for geometry tools (line, rectangle, circle, etc.).

    Provides ``get_properties()`` / ``set_property()`` so the PropertyManager
    can display and edit default values before placement.  Colour and
    line-weight are derived from the selected layer at placement time.
    """

    def __init__(self):
        self.level: str = DEFAULT_LEVEL
        self.user_layer: str = DEFAULT_USER_LAYER
        self.name: str = "(Template)"

    def get_properties(self) -> dict:
        return {
            "Type":  {"type": "label",     "value": "Geometry"},
            "Layer": {"type": "layer_ref", "value": self.user_layer},
            "Level": {"type": "level_ref", "value": self.level},
        }

    def set_property(self, key: str, value):
        if key == "Layer":
            self.user_layer = str(value)
        elif key == "Level":
            self.level = str(value)
