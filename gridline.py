"""
gridline.py
===========
Revit-style gridline system for FirePro 3D.

Classes
-------
GridBubble     — circle + label at one end of a gridline (screen-fixed size)
GridlineItem   — finite gridline with two GridBubble children

Placement: 2-click (start → end).
Auto-numbering: vertical grids → A, B, C…  horizontal → 1, 2, 3…
"""

from __future__ import annotations

import math
from PyQt6.QtWidgets import (
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsTextItem,
    QGraphicsItem, QStyle,
)
from PyQt6.QtGui import QPen, QColor, QFont, QBrush, QPainterPath
from PyQt6.QtCore import Qt, QPointF


# ─────────────────────────────────────────────────────────────────────────────
# Auto-numbering counters (reset when a new document is created)
# ─────────────────────────────────────────────────────────────────────────────

_next_number: int = 1       # for horizontal grids: 1, 2, 3…
_next_letter_idx: int = 0   # for vertical grids:   A, B, C… AA, AB…


def reset_grid_counters():
    """Reset auto-numbering (call on new document / clear scene)."""
    global _next_number, _next_letter_idx
    _next_number = 1
    _next_letter_idx = 0


def _next_h_label() -> str:
    global _next_number
    label = str(_next_number)
    _next_number += 1
    return label


def _next_v_label() -> str:
    global _next_letter_idx
    idx = _next_letter_idx
    _next_letter_idx += 1
    # A–Z, then AA, AB, …
    if idx < 26:
        return chr(65 + idx)
    else:
        return chr(65 + (idx // 26) - 1) + chr(65 + (idx % 26))


def auto_label(p1: QPointF, p2: QPointF) -> str:
    """Choose H or V numbering based on the line's angle."""
    dx = abs(p2.x() - p1.x())
    dy = abs(p2.y() - p1.y())
    if dy >= dx:
        # More vertical → letter label (A, B, C)
        return _next_v_label()
    else:
        # More horizontal → number label (1, 2, 3)
        return _next_h_label()


# ─────────────────────────────────────────────────────────────────────────────
# GridBubble — circle + text, fixed screen size
# ─────────────────────────────────────────────────────────────────────────────

BUBBLE_RADIUS_MM = 8.0 * 25.4   # 8-inch radius in mm (zoom-dependent scene units)


class GridBubble(QGraphicsEllipseItem):
    """Zoom-dependent circle with a centred label (scales with scene geometry)."""

    def __init__(self, label: str, parent: QGraphicsItem | None = None):
        r = BUBBLE_RADIUS_MM
        super().__init__(-r, -r, 2 * r, 2 * r, parent)
        # No ItemIgnoresTransformations — bubble scales with zoom
        pen = QPen(QColor("#4488cc"), max(1, r * 0.04))
        self.setPen(pen)
        self.setBrush(QBrush(QColor("#1a1a2e")))
        self.setZValue(500)

        self._label = QGraphicsTextItem(label, self)
        self._label.setDefaultTextColor(QColor("#88ccff"))
        font = QFont("Consolas")
        font.setPixelSize(max(1, int(r * 1.0)))
        font.setBold(True)
        self._label.setFont(font)
        self._center_label()

    def set_label(self, text: str):
        self._label.setPlainText(text)
        self._center_label()

    def label(self) -> str:
        return self._label.toPlainText()

    def _center_label(self):
        br = self._label.boundingRect()
        self._label.setPos(-br.width() / 2, -br.height() / 2)

    # ── Selection: bubble click selects parent gridline ────────────────────

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        parent = self.parentItem()
        if parent is not None and parent.isSelected():
            r = BUBBLE_RADIUS_MM
            highlight = QPen(QColor("#ff8800"), max(1, r * 0.04))
            painter.setPen(highlight)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            from PyQt6.QtCore import QRectF
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def mousePressEvent(self, event):
        parent = self.parentItem()
        if parent is not None:
            scene = parent.scene()
            if scene is not None:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    parent.setSelected(not parent.isSelected())
                else:
                    scene.clearSelection()
                    parent.setSelected(True)
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# GridlineItem — finite line with two bubbles
# ─────────────────────────────────────────────────────────────────────────────

GRID_COLOR = "#4488cc"
GRID_WIDTH = 1.5


class GridlineItem(QGraphicsLineItem):
    """A finite gridline with auto-numbered bubble labels at each end."""

    def __init__(self, p1: QPointF, p2: QPointF, label: str | None = None):
        super().__init__(p1.x(), p1.y(), p2.x(), p2.y())

        # Cosmetic pen for the gridline itself
        pen = QPen(QColor(GRID_COLOR), GRID_WIDTH, Qt.PenStyle.DashDotLine)
        pen.setCosmetic(True)
        self.setPen(pen)

        # Flags
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(-10)  # below geometry and annotations

        # Auto-assign label
        if label is None:
            label = auto_label(p1, p2)
        self._label_text = label

        # Bubbles
        self.bubble1 = GridBubble(label, self)
        self.bubble2 = GridBubble(label, self)
        self._update_bubble_positions()

        # User layer
        self.user_layer: str = "Default"
        self.level: str = "Level 1"
        self._display_overrides: dict = {}  # per-instance display overrides
        self._display_scale: float = 1.0    # display scale for bubbles

    # ── Geometry overrides ────────────────────────────────────────────────

    def boundingRect(self):
        """Expand bounding rect so the cosmetic-pen line isn't culled by
        Qt's view frustum at high zoom.  Cosmetic pens have zero scene-unit
        width, giving the default rect no margin for viewport intersection."""
        br = super().boundingRect()
        m = BUBBLE_RADIUS_MM  # generous margin matching bubble size
        return br.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        """Return empty path so the line itself is not hit-testable.
        Selection is handled by GridBubble.mousePressEvent instead."""
        return QPainterPath()

    def itemChange(self, change, value):
        """Refresh bubble paint when selection state changes."""
        if change == self.GraphicsItemChange.ItemSelectedHasChanged:
            self.bubble1.update()
            self.bubble2.update()
        return super().itemChange(change, value)

    # ── Bubble positioning ────────────────────────────────────────────────

    def _update_bubble_positions(self):
        line = self.line()
        self.bubble1.setPos(line.p1())
        self.bubble2.setPos(line.p2())

    # ── Selection highlight (suppress dashed box) ─────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
        if self.isSelected():
            highlight = QPen(QColor(GRID_COLOR).lighter(150), GRID_WIDTH + 1.5)
            highlight.setCosmetic(True)
            highlight.setStyle(Qt.PenStyle.DashDotLine)
            painter.setPen(highlight)
            line = self.line()
            painter.drawLine(line)

    # ── Label management ──────────────────────────────────────────────────

    @property
    def grid_label(self) -> str:
        return self._label_text

    @grid_label.setter
    def grid_label(self, text: str):
        self._label_text = text
        self.bubble1.set_label(text)
        self.bubble2.set_label(text)

    def set_bubble_visible(self, end: int, visible: bool):
        """Toggle bubble visibility. end=1 for start, end=2 for end."""
        if end == 1:
            self.bubble1.setVisible(visible)
        else:
            self.bubble2.setVisible(visible)

    # ── Grip drag (constrained to gridline direction) ────────────────────

    def grip_points(self) -> list[QPointF]:
        """Return the two endpoint positions as scene-space grip handles."""
        line = self.line()
        return [line.p1(), line.p2()]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Move grip *index* to *new_pos*, constrained along the gridline
        direction so the line stays co-linear."""
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-12:
            return

        if index == 0:
            # Project new_pos onto the line direction relative to p2
            t = ((new_pos.x() - p2.x()) * dx + (new_pos.y() - p2.y()) * dy) / length_sq
            proj = QPointF(p2.x() + t * dx, p2.y() + t * dy)
            self.setLine(proj.x(), proj.y(), p2.x(), p2.y())
        elif index == 1:
            # Project new_pos onto the line direction relative to p1
            t = ((new_pos.x() - p1.x()) * dx + (new_pos.y() - p1.y()) * dy) / length_sq
            proj = QPointF(p1.x() + t * dx, p1.y() + t * dy)
            self.setLine(p1.x(), p1.y(), proj.x(), proj.y())

        self._update_bubble_positions()
        self.update()

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        line = self.line()
        d = {
            "p1": [line.p1().x(), line.p1().y()],
            "p2": [line.p2().x(), line.p2().y()],
            "label": self._label_text,
            "bubble1_vis": self.bubble1.isVisible(),
            "bubble2_vis": self.bubble2.isVisible(),
            "user_layer": self.user_layer,
            "level":      self.level,
        }
        if self._display_overrides:
            d["display_overrides"] = self._display_overrides
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GridlineItem":
        p1 = QPointF(d["p1"][0], d["p1"][1])
        p2 = QPointF(d["p2"][0], d["p2"][1])
        item = cls(p1, p2, label=d.get("label", "?"))
        item.bubble1.setVisible(d.get("bubble1_vis", True))
        item.bubble2.setVisible(d.get("bubble2_vis", True))
        item.user_layer = d.get("user_layer", "0")
        item.level = d.get("level", "Level 1")
        item._display_overrides = d.get("display_overrides", {})
        return item

    # ── Properties for property panel ─────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Label": {"type": "string", "value": self._label_text},
            "Bubble 1": {"type": "enum", "options": ["Visible", "Hidden"],
                         "value": "Visible" if self.bubble1.isVisible() else "Hidden"},
            "Bubble 2": {"type": "enum", "options": ["Visible", "Hidden"],
                         "value": "Visible" if self.bubble2.isVisible() else "Hidden"},
        }

    def set_property(self, key: str, value):
        if key == "Label":
            self.grid_label = str(value)
        elif key == "Bubble 1":
            self.bubble1.setVisible(value == "Visible")
        elif key == "Bubble 2":
            self.bubble2.setVisible(value == "Visible")
