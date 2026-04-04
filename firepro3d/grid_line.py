"""
grid_line.py
============
Revit-style grid line with labelled bubbles at each end, pull-tab grips,
draggable perpendicular reposition, and lockable position.
"""

from __future__ import annotations

import math
from PyQt6.QtWidgets import (
    QGraphicsItemGroup, QGraphicsLineItem, QGraphicsEllipseItem,
    QGraphicsTextItem, QGraphicsRectItem, QGraphicsItem,
)
from PyQt6.QtGui import QPen, QColor, QBrush, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF


_GRID_COLOR = QColor("#00aaff")
_BUBBLE_RADIUS = 14.0       # screen pixels (ItemIgnoresTransformations)
_GRIP_SIZE = 6.0            # half-width of the pull-tab grip square (screen pixels)
_Z_GRID = -5                # behind model items


class GridLine(QGraphicsItemGroup):
    """
    A finite-length grid line with circle bubbles and pull-tab grips.

    Parameters
    ----------
    start, end : QPointF
        Scene-coordinate endpoints of the line.
    label : str
        Label shown inside the bubble (e.g. "1", "A").
    axis : str
        "x" for vertical lines (numbered 1,2,3...),
        "y" for horizontal lines (lettered A,B,C...).
    """

    def __init__(self, start: QPointF, end: QPointF, label: str = "",
                 axis: str = "x", parent=None):
        super().__init__(parent)
        self._start = QPointF(start)
        self._end = QPointF(end)
        self._label = label
        self._axis = axis
        self._locked = False
        self._bubble_start_visible = True
        self._bubble_end_visible = True

        self.setZValue(_Z_GRID)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        self._line_item: QGraphicsLineItem | None = None
        self._bubble_start: QGraphicsItemGroup | None = None
        self._bubble_end: QGraphicsItemGroup | None = None
        self._grip_start: QGraphicsRectItem | None = None
        self._grip_end: QGraphicsRectItem | None = None

        self._rebuild()

    # ── Rebuild visual items ─────────────────────────────────────────────────

    def _rebuild(self):
        """Reconstruct all child graphics items from current state."""
        # Remove old children
        for child in list(self.childItems()):
            self.removeFromGroup(child)
            if child.scene():
                child.scene().removeItem(child)

        pen = QPen(_GRID_COLOR, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)

        # Main line
        self._line_item = QGraphicsLineItem(
            self._start.x(), self._start.y(),
            self._end.x(), self._end.y()
        )
        self._line_item.setPen(pen)
        self.addToGroup(self._line_item)

        # Bubbles
        if self._bubble_start_visible:
            self._bubble_start = self._create_bubble(self._start, self._label)
            self.addToGroup(self._bubble_start)
        else:
            self._bubble_start = None

        if self._bubble_end_visible:
            self._bubble_end = self._create_bubble(self._end, self._label)
            self.addToGroup(self._bubble_end)
        else:
            self._bubble_end = None

        # Grip handles (pull tabs) — small squares at each end
        self._grip_start = self._create_grip(self._start)
        self.addToGroup(self._grip_start)
        self._grip_end = self._create_grip(self._end)
        self.addToGroup(self._grip_end)

    def _create_bubble(self, pos: QPointF, label: str) -> QGraphicsItemGroup:
        """Circle bubble with centred label text.

        Uses ItemIgnoresTransformations so the bubble stays a constant
        screen size regardless of zoom — matching Revit behaviour.
        """
        grp = QGraphicsItemGroup()
        grp.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        r = _BUBBLE_RADIUS

        circle = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
        pen = QPen(_GRID_COLOR, 1.5)
        circle.setPen(pen)
        circle.setBrush(QBrush(QColor(0, 0, 0, 200)))  # dark fill for contrast
        grp.addToGroup(circle)

        text = QGraphicsTextItem(label)
        text.setDefaultTextColor(_GRID_COLOR)
        font = QFont("Arial")
        font.setPointSizeF(9)
        font.setBold(True)
        text.setFont(font)
        br = text.boundingRect()
        text.setPos(-br.width() / 2, -br.height() / 2)
        grp.addToGroup(text)

        grp.setPos(pos)
        return grp

    def _create_grip(self, pos: QPointF) -> QGraphicsRectItem:
        """Small square grip handle for pull-tab length adjustment.

        Uses ItemIgnoresTransformations for constant screen size.
        """
        s = _GRIP_SIZE
        grip = QGraphicsRectItem(-s, -s, 2 * s, 2 * s)
        grip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        grip.setPen(QPen(Qt.PenStyle.NoPen))
        grip.setBrush(QBrush(QColor(0, 170, 255, 60)))
        grip.setPos(pos)
        grip.setZValue(1)
        return grip

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str):
        self._label = value
        self._rebuild()

    @property
    def axis(self) -> str:
        return self._axis

    @property
    def start(self) -> QPointF:
        return QPointF(self._start)

    @property
    def end(self) -> QPointF:
        return QPointF(self._end)

    @property
    def locked(self) -> bool:
        return self._locked

    @locked.setter
    def locked(self, value: bool):
        self._locked = value

    def grip_points(self) -> list[QPointF]:
        """Return [start, end] positions for drag-handle interaction."""
        return [QPointF(self._start), QPointF(self._end)]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Move start (0) or end (1) grip to adjust line length."""
        if self._locked:
            return
        if index == 0:
            # Constrain to the line's direction
            if self._axis == "x":
                self._start = QPointF(self._start.x(), new_pos.y())
            else:
                self._start = QPointF(new_pos.x(), self._start.y())
        elif index == 1:
            if self._axis == "x":
                self._end = QPointF(self._end.x(), new_pos.y())
            else:
                self._end = QPointF(new_pos.x(), self._end.y())
        self._rebuild()

    def move_perpendicular(self, offset: float):
        """Shift the entire line perpendicular to its axis by *offset* units."""
        if self._locked:
            return
        if self._axis == "x":
            # Vertical line — move in X direction
            delta = QPointF(offset, 0)
        else:
            # Horizontal line — move in Y direction
            delta = QPointF(0, offset)
        self._start += delta
        self._end += delta
        self._rebuild()

    def set_position_value(self, value: float):
        """Set the perpendicular position to an absolute value."""
        if self._locked:
            return
        if self._axis == "x":
            dx = value - self._start.x()
            self._start = QPointF(value, self._start.y())
            self._end = QPointF(value, self._end.y())
        else:
            dy = value - self._start.y()
            self._start = QPointF(self._start.x(), value)
            self._end = QPointF(self._end.x(), value)
        self._rebuild()

    def position_value(self) -> float:
        """Return the perpendicular coordinate (X for vertical, Y for horizontal)."""
        if self._axis == "x":
            return self._start.x()
        else:
            return self._start.y()

    def toggle_bubble(self, end: str, visible: bool):
        """Toggle bubble visibility. end = 'start' or 'end'."""
        if end == "start":
            self._bubble_start_visible = visible
        elif end == "end":
            self._bubble_end_visible = visible
        self._rebuild()

    # ── Hit testing for grips ────────────────────────────────────────────────

    def grip_at(self, scene_pos: QPointF, tolerance: float = 10.0) -> int | None:
        """Return 0 (start grip) or 1 (end grip) if near, else None."""
        d0 = math.hypot(scene_pos.x() - self._start.x(),
                        scene_pos.y() - self._start.y())
        d1 = math.hypot(scene_pos.x() - self._end.x(),
                        scene_pos.y() - self._end.y())
        if d0 <= tolerance:
            return 0
        if d1 <= tolerance:
            return 1
        return None

    # ── Serialization ────────────────────────────────────────────────────────

    # ── Property panel ────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Label":  {"type": "string", "value": self._label},
            "Axis":   {"type": "enum", "options": ["x", "y"], "value": self._axis},
            "Locked": {"type": "enum", "options": ["True", "False"],
                       "value": str(self._locked)},
        }

    def set_property(self, key, value):
        if key == "Label":
            self._label = value
            self._rebuild()
        elif key == "Axis":
            self._axis = value
        elif key == "Locked":
            self._locked = value in ("True", True)

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type": "grid_line",
            "label": self._label,
            "axis": self._axis,
            "start": [self._start.x(), self._start.y()],
            "end": [self._end.x(), self._end.y()],
            "locked": self._locked,
            "bubble_start": self._bubble_start_visible,
            "bubble_end": self._bubble_end_visible,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GridLine:
        gl = cls(
            QPointF(data["start"][0], data["start"][1]),
            QPointF(data["end"][0], data["end"][1]),
            label=data.get("label", ""),
            axis=data.get("axis", "x"),
        )
        gl._locked = data.get("locked", False)
        gl._bubble_start_visible = data.get("bubble_start", True)
        gl._bubble_end_visible = data.get("bubble_end", True)
        gl._rebuild()
        return gl
