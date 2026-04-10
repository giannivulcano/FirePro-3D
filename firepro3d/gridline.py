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
    QGraphicsRectItem, QGraphicsItem, QStyle,
)
from PyQt6.QtGui import QPen, QColor, QFont, QBrush, QPainterPath
from .constants import DEFAULT_USER_LAYER
from PyQt6.QtCore import Qt, QPointF, QRectF


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


def _label_to_letter_idx(label: str) -> int | None:
    """Convert an alphabetic label to its sequential index (0-based).

    Args:
        label: A string label (e.g. "A", "Z", "AA", "AB").

    Returns:
        Integer index, or None if the label is not purely alphabetic or
        has more than two characters.
    """
    if not label.isalpha():
        return None
    label = label.upper()
    if len(label) == 1:
        return ord(label) - ord('A')
    elif len(label) == 2:
        return 26 + (ord(label[0]) - ord('A')) * 26 + (ord(label[1]) - ord('A'))
    return None


def sync_grid_counters(gridlines: list) -> None:
    """Advance auto-numbering counters past all existing gridline labels.

    Scans *gridlines* for pure-numeric and pure-alpha labels and sets
    ``_next_number`` / ``_next_letter_idx`` so the next auto-assigned
    label does not collide with any existing one.  Custom labels (e.g.
    "X-1") are silently ignored.

    Args:
        gridlines: Sequence of :class:`GridlineItem` objects to inspect.
    """
    global _next_number, _next_letter_idx
    max_num = 0
    max_letter = -1
    for gl in gridlines:
        label = gl.grid_label
        try:
            n = int(label)
            max_num = max(max_num, n)
            continue
        except ValueError:
            pass
        idx = _label_to_letter_idx(label)
        if idx is not None:
            max_letter = max(max_letter, idx)
    _next_number = max_num + 1
    _next_letter_idx = max_letter + 1


def check_duplicate_labels(gridlines: list) -> set:
    """Return the set of gridlines whose label appears more than once.

    Args:
        gridlines: Sequence of :class:`GridlineItem` objects to inspect.

    Returns:
        Set of :class:`GridlineItem` instances that share a label with at
        least one other item in *gridlines*.
    """
    from collections import Counter
    label_counts = Counter(gl.grid_label for gl in gridlines)
    return {gl for gl in gridlines if label_counts[gl.grid_label] > 1}


def apply_duplicate_warnings(gridlines: list) -> None:
    """Apply or clear duplicate-label warning colouring on every gridline.

    Args:
        gridlines: Sequence of :class:`GridlineItem` objects to update.
    """
    dupes = check_duplicate_labels(gridlines)
    for gl in gridlines:
        gl.update_duplicate_warning(gl in dupes)


# ─────────────────────────────────────────────────────────────────────────────
# GridBubble — circle + text, fixed screen size
# ─────────────────────────────────────────────────────────────────────────────

BUBBLE_RADIUS_MM = 8.0 * 25.4   # 8-inch radius in mm (zoom-dependent scene units)


class GridBubble(QGraphicsEllipseItem):
    """Fixed-size circle with a centred label (constant screen pixels)."""

    RADIUS_PX = 14.0  # screen pixels — constant regardless of zoom

    def __init__(self, label: str, parent: QGraphicsItem | None = None):
        r = self.RADIUS_PX
        super().__init__(-r, -r, 2 * r, 2 * r, parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        pen = QPen(QColor("#4488cc"), max(1.0, r * 0.08))
        self.setPen(pen)
        self.setBrush(QBrush(QColor("#1a1a2e")))
        self.setZValue(500)

        self._label = QGraphicsTextItem(label, self)
        self._label.setDefaultTextColor(QColor("#88ccff"))
        font = QFont("Consolas")
        font.setPixelSize(max(1, int(r * 0.9)))
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
            r = self.RADIUS_PX
            # Use the gridline's assigned colour for the highlight ring
            base_color = getattr(parent, "_grid_color", QColor(GRID_COLOR))
            highlight = QPen(base_color.lighter(150), max(1.0, r * 0.12))
            painter.setPen(highlight)
            painter.setBrush(Qt.BrushStyle.NoBrush)
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
# _PullTabGrip — small handle at gridline endpoints
# ─────────────────────────────────────────────────────────────────────────────

_GRIP_HALF = 5.0  # Half-width of pull-tab square (screen pixels)


class _PullTabGrip(QGraphicsRectItem):
    """Small square grip handle at a gridline endpoint.

    Uses ItemIgnoresTransformations for constant screen size.
    Visible only when parent gridline is selected or hovered.
    """

    def __init__(self, parent: QGraphicsItem):
        super().__init__(-_GRIP_HALF, -_GRIP_HALF, 2 * _GRIP_HALF, 2 * _GRIP_HALF, parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(QColor(68, 136, 204, 60)))
        self.setZValue(1)
        self.setVisible(False)


# ─────────────────────────────────────────────────────────────────────────────
# GridlineItem — finite line with two bubbles
# ─────────────────────────────────────────────────────────────────────────────

GRID_COLOR = "#4488cc"
GRID_WIDTH = 1.5


class GridlineItem(QGraphicsLineItem):
    """A finite gridline with auto-numbered bubble labels at each end."""

    def __init__(self, p1: QPointF, p2: QPointF, label: str | None = None):
        super().__init__(p1.x(), p1.y(), p2.x(), p2.y())

        # Store the desired colour; drawing is handled entirely in paint()
        # using a non-cosmetic pen with width calculated from the view
        # transform.  This avoids Qt's cosmetic-pen rasteriser which
        # fails silently after a few zoom steps on some platforms.
        self._grid_color = QColor(GRID_COLOR)
        pen = QPen(Qt.PenStyle.NoPen)       # suppress default drawing
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

        # Pull-tab grips
        self._grip1 = _PullTabGrip(self)
        self._grip2 = _PullTabGrip(self)
        self._update_grip_positions()

        # Hover events for grip visibility
        self.setAcceptHoverEvents(True)

        # User layer
        self.user_layer: str = DEFAULT_USER_LAYER
        self._locked: bool = False
        self.paper_height_mm: float = 3.0
        self._display_overrides: dict = {}  # per-instance display overrides
        self._display_scale: float = 1.0    # display scale for bubbles

    # ── Geometry overrides ────────────────────────────────────────────────

    def boundingRect(self):
        """Expand bounding rect with a small margin for the pen.

        Bubbles and grips use ItemIgnoresTransformations and manage
        their own bounds independently.
        """
        br = super().boundingRect()
        m = 20.0  # small scene-unit margin for the gridline pen
        return br.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        """Return bubble positions as the selectable shape.

        Uses a small scene-unit radius so marquee selection works
        near endpoints.  Direct clicks on ITT bubbles are handled
        by GridBubble.mousePressEvent.
        """
        path = QPainterPath()
        # Use a fixed scene-unit radius — enough for marquee selection
        r = 50.0
        path.addEllipse(self.bubble1.pos(), r, r)
        path.addEllipse(self.bubble2.pos(), r, r)
        return path

    def itemChange(self, change, value):
        """Refresh bubble paint and show/hide grips on selection change."""
        if change == self.GraphicsItemChange.ItemSelectedChange:
            selected = bool(value)
            self._grip1.setVisible(selected)
            self._grip2.setVisible(selected)
        if change == self.GraphicsItemChange.ItemSelectedHasChanged:
            self.bubble1.update()
            self.bubble2.update()
        return super().itemChange(change, value)

    # ── Bubble positioning ────────────────────────────────────────────────

    def _update_bubble_positions(self):
        line = self.line()
        self.bubble1.setPos(line.p1())
        self.bubble2.setPos(line.p2())
        if hasattr(self, '_grip1'):
            self._update_grip_positions()

    def _update_grip_positions(self):
        """Place grips slightly beyond each endpoint along the line direction."""
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 1e-12:
            self._grip1.setPos(p1)
            self._grip2.setPos(p2)
            return
        ux, uy = dx / length, dy / length
        self._grip1.setPos(p1.x() - ux * 10, p1.y() - uy * 10)
        self._grip2.setPos(p2.x() + ux * 10, p2.y() + uy * 10)

    # ── Hover events ─────────────────────────────────────────────────────

    def hoverEnterEvent(self, event):
        if not self.isSelected():
            self._grip1.setVisible(True)
            self._grip2.setVisible(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self._grip1.setVisible(False)
            self._grip2.setVisible(False)
        super().hoverLeaveEvent(event)

    # ── Selection highlight (suppress dashed box) ─────────────────────────

    def paint(self, painter, option, widget=None):
        """Draw the gridline with a non-cosmetic pen whose width is
        calculated from the current view transform so it appears as a
        constant-width screen line.  The line is shortened at each end
        so it meets the bubble at the closest edge rather than its centre."""
        option.state &= ~QStyle.StateFlag.State_Selected

        # Calculate pen width to maintain ~GRID_WIDTH screen pixels
        vt = painter.deviceTransform()
        sx = max(abs(vt.m11()), abs(vt.m22()), 1e-9)
        pen_w = GRID_WIDTH / sx

        # Shorten line to meet visible bubbles at their edge.
        # Bubbles use ItemIgnoresTransformations, so convert pixel radius
        # back to scene units using the current view scale.
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length > 1e-9:
            ux, uy = dx / length, dy / length
            scene_r = GridBubble.RADIUS_PX / sx  # pixel radius → scene units
            draw_p1 = QPointF(p1.x() + ux * scene_r, p1.y() + uy * scene_r) if self.bubble1.isVisible() else p1
            draw_p2 = QPointF(p2.x() - ux * scene_r, p2.y() - uy * scene_r) if self.bubble2.isVisible() else p2
        else:
            draw_p1, draw_p2 = p1, p2

        pen = QPen(self._grid_color, pen_w, Qt.PenStyle.DashDotLine)
        painter.setPen(pen)
        painter.drawLine(draw_p1, draw_p2)

        if self.isSelected():
            sel_pen = QPen(self._grid_color.lighter(150),
                           pen_w * 2, Qt.PenStyle.DashDotLine)
            painter.setPen(sel_pen)
            painter.drawLine(draw_p1, draw_p2)

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

    # ── Lock property ──────────────────────────────────────────────────

    @property
    def locked(self) -> bool:
        """Whether the gridline is locked against editing."""
        return self._locked

    @locked.setter
    def locked(self, value: bool):
        self._locked = value

    # ── Perpendicular move ───────────────────────────────────────────────

    def _perpendicular_vector(self) -> tuple[float, float]:
        """Return the unit perpendicular vector to the gridline direction.

        For a vertical line (dx=0, dy!=0), returns (1, 0).
        For a horizontal line (dy=0, dx!=0), returns (0, 1).
        For angled lines, returns the left-hand normal.
        """
        line = self.line()
        dx = line.p2().x() - line.p1().x()
        dy = line.p2().y() - line.p1().y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-12:
            return (1.0, 0.0)
        # Perpendicular normal: (-dy, dx) normalized, then flipped so
        # the dominant component is positive.  This ensures positive
        # distance always moves in the +X or +Y direction.
        nx, ny = -dy / length, dx / length
        # Flip so that the larger component is positive
        dominant = nx if abs(nx) >= abs(ny) else ny
        if dominant < 0:
            nx, ny = -nx, -ny
        return (nx, ny)

    def move_perpendicular(self, distance: float):
        """Translate the gridline by *distance* in the perpendicular direction.

        Positive distance moves in the perpendicular direction; negative
        moves opposite.  Locked gridlines are not affected.
        """
        if self._locked:
            return
        nx, ny = self._perpendicular_vector()
        line = self.line()
        p1 = line.p1()
        p2 = line.p2()
        offset_x = nx * distance
        offset_y = ny * distance
        self.setLine(
            p1.x() + offset_x, p1.y() + offset_y,
            p2.x() + offset_x, p2.y() + offset_y,
        )
        self._update_bubble_positions()
        self.update()

    def set_perpendicular_position(self, position: float):
        """Move the gridline so its perpendicular coordinate equals *position*.

        For a vertical gridline this sets the X coordinate of both endpoints.
        For a horizontal gridline this sets the Y coordinate.
        """
        if self._locked:
            return
        nx, ny = self._perpendicular_vector()
        line = self.line()
        p1 = line.p1()
        # Current perpendicular position = dot(p1, normal)
        current = p1.x() * nx + p1.y() * ny
        self.move_perpendicular(position - current)

    # ── Grip drag (constrained to gridline direction) ────────────────────

    def grip_points(self) -> list[QPointF]:
        """Return the two endpoint positions as scene-space grip handles."""
        line = self.line()
        return [line.p1(), line.p2()]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Move grip *index* to *new_pos*, constrained along the gridline
        direction so the line stays co-linear.  Locked gridlines are not
        affected."""
        if self._locked:
            return
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
            "locked": self._locked,
            "paper_height_mm": self.paper_height_mm,
        }
        if self._display_overrides:
            d["display_overrides"] = self._display_overrides
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GridlineItem":
        p1 = QPointF(d["p1"][0], d["p1"][1])
        p2 = QPointF(d["p2"][0], d["p2"][1])
        item = cls(p1, p2, label=d.get("label", "?"))
        # Handle old-format key renames
        b1_vis = d.get("bubble1_vis", d.get("bubble_start", True))
        b2_vis = d.get("bubble2_vis", d.get("bubble_end", True))
        item.bubble1.setVisible(b1_vis)
        item.bubble2.setVisible(b2_vis)
        item.user_layer = d.get("user_layer", "0")
        item._locked = d.get("locked", False)
        item.paper_height_mm = d.get("paper_height_mm", 3.0)
        item._display_overrides = d.get("display_overrides", {})
        # Silently ignore "level" key from old files
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

    # ── Duplicate warning ─────────────────────────────────────────────────

    def update_duplicate_warning(self, is_duplicate: bool):
        """Colour the bubble outlines orange when *is_duplicate* is True.

        Args:
            is_duplicate: Whether this gridline shares its label with
                another gridline in the scene.
        """
        color = QColor("#ff8800") if is_duplicate else self._grid_color
        pen = QPen(color, 2)
        self.bubble1.setPen(pen)
        self.bubble2.setPen(pen)
