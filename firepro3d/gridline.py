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
from functools import lru_cache
from PyQt6.QtWidgets import (
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsTextItem,
    QGraphicsRectItem, QGraphicsItem, QGraphicsPathItem, QStyle,
)
from PyQt6.QtGui import QPen, QColor, QFont, QBrush, QPainterPath, QPainterPathStroker, QFontMetricsF
from .constants import (
    Z_GRIDLINE_BUBBLE, Z_CONSTRUCTION, TEXT_METRIC_REF_PX,
    GRIDLINE_BUBBLE_LABEL_EM_FRAC, GRIDLINE_BUBBLE_OFFSET_MM,
)
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

# Model-unit (mm) proportioning base for elevation/detail markers and
# elevation-scene bubbles (they size off this constant).  NOT the plan-view
# bubble size (screen bubbles are RADIUS_PX ItemIgnoresTransformations) and
# NOT the paper size (paper bubbles derive from bubble_paper_geometry, §9.9.1).
BUBBLE_RADIUS_MM = 8.0 * 25.4


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
        self.setZValue(Z_GRIDLINE_BUBBLE)

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

    def enter_paper_mode(self, radius_scene: float, em_scene: float) -> dict:
        """Switch to scene-unit geometry for a paper render pass (§9.9.1)."""
        saved = {
            "rect": QRectF(self.rect()),
            "font": QFont(self._label.font()),
            "label_scale": self._label.scale(),
            "label_pos": QPointF(self._label.pos()),
        }
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)
        self.setRect(-radius_scene, -radius_scene, 2 * radius_scene, 2 * radius_scene)
        f = QFont(self._label.font())
        f.setPixelSize(TEXT_METRIC_REF_PX)          # §9.4: ref px + geometric scale
        self._label.setFont(f)
        self._label.setScale(em_scene / TEXT_METRIC_REF_PX)
        br = self._label.boundingRect()
        s = self._label.scale()
        self._label.setPos(-br.width() * s / 2, -br.height() * s / 2)
        return saved

    def exit_paper_mode(self, saved: dict):
        """Restore screen-pixel geometry after a paper render pass (§9.9.1)."""
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setRect(saved["rect"])
        self._label.setFont(saved["font"])
        self._label.setScale(saved["label_scale"])
        self._label.setPos(saved["label_pos"])

    # ── Selection: bubble click selects parent gridline ────────────────────

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        parent = self.parentItem()
        if parent is not None and parent.isSelected() and not getattr(parent, "_paper_render", False):
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
        self.setZValue(Z_CONSTRUCTION)
        self.setVisible(False)


# ─────────────────────────────────────────────────────────────────────────────
# _LockIndicator — small padlock icon at gridline midpoint
# ─────────────────────────────────────────────────────────────────────────────

_LOCK_SIZE = 10.0  # pixels (screen-fixed)


class _LockIndicator(QGraphicsPathItem):
    """Small padlock icon adjacent to the primary gridline bubble.

    Visible when the parent gridline is selected.  Click toggles the
    gridline's ``_locked`` state.  Orange = unlocked, green = locked.
    Drawn offset from the bubble centre so it sits beside it.
    """

    _OFFSET_PX = GridBubble.RADIUS_PX + 6  # bubble edge + gap

    def __init__(self, parent: "GridlineItem"):
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(Z_GRIDLINE_BUBBLE + 1)  # just above bubbles
        self.setVisible(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self._gridline = parent
        self._rebuild()

    def _rebuild(self):
        """Redraw the padlock shape offset from the bubble, colour reflects lock state."""
        s = _LOCK_SIZE
        # Compute offset direction: perpendicular to gridline, in screen pixels
        line = self._gridline.line()
        dx = line.p2().x() - line.p1().x()
        dy = line.p2().y() - line.p1().y()
        length = math.hypot(dx, dy)
        if length > 1e-9:
            # Perpendicular unit vector (screen space, since ITT)
            nx, ny = -dy / length, dx / length
        else:
            nx, ny = 1.0, 0.0
        # Pick the side where the dominant perpendicular component is positive
        dominant = nx if abs(nx) >= abs(ny) else ny
        if dominant < 0:
            nx, ny = -nx, -ny
        ox = nx * self._OFFSET_PX
        oy = ny * self._OFFSET_PX

        path = QPainterPath()
        # Body (rectangle) — offset by (ox, oy)
        path.addRect(ox - s / 2, oy - s * 0.35, s, s * 0.7)
        # Shackle (arc)
        path.moveTo(ox - s * 0.3, oy - s * 0.35)
        path.arcTo(ox - s * 0.3, oy - s * 0.85, s * 0.6, s * 0.6, 180, -180)
        self.setPath(path)
        locked = self._gridline._locked
        color = QColor("#44cc44") if locked else QColor("#ffaa00")
        self.setPen(QPen(color, 1.5))
        self.setBrush(QBrush(color.lighter(180)))

    def mousePressEvent(self, event):
        gl = self._gridline
        gl._locked = not gl._locked
        self._rebuild()
        # Update grip visibility — hide grips when locked
        gl._grip1.setVisible(not gl._locked and gl.isSelected())
        gl._grip2.setVisible(not gl._locked and gl.isSelected())
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# GridlineItem — finite line with two bubbles
# ─────────────────────────────────────────────────────────────────────────────

GRID_COLOR = "#4488cc"
GRID_WIDTH = 1.5

# Dash-dot geometry in screen pixels (screen path) — Task 12 may retune.
_DASH_PX = 14.0
_GAP_PX = 6.0
_DOT_PX = 2.0
# Paper path: fixed mm so a PDF reads as dash-dot regardless of DPI.
_DASH_MM = 6.35   # 1/4"
_GAP_MM = 3.18
_DOT_MM = 1.0


def _dash_pattern_px(sx: float) -> list[float]:
    """Dash pattern in scene units rendering a fixed on-screen pixel dash-dot
    at view scale ``sx``. Entries: dash, gap, dot, gap."""
    s = 1.0 / max(sx, 1e-9)
    return [_DASH_PX * s, _GAP_PX * s, _DOT_PX * s, _GAP_PX * s]


def _dash_pattern_mm(line_w: float) -> list[float]:
    """Dash pattern in scene-mm for the paper render path, normalised to the
    pen width (Qt expresses dash entries in pen-width multiples)."""
    w = max(line_w, 1e-6)
    return [_DASH_MM / w, _GAP_MM / w, _DOT_MM / w, _GAP_MM / w]


# Requires a live QApplication (QFontMetricsF); never call at module import time.
@lru_cache(maxsize=8)
def bubble_paper_geometry(cap_mm: float) -> tuple[float, float]:
    """Return (radius_mm, em_mm) of a bubble head on paper for a label cap height.

    em derives from cap via Consolas-bold metrics at TEXT_METRIC_REF_PX
    (paper-space spec §9.4 technique); the head radius keeps the historic
    screen proportion em = GRIDLINE_BUBBLE_LABEL_EM_FRAC × radius.

    Args:
        cap_mm: Desired cap height of the label text on paper, in mm.

    Returns:
        A tuple of (radius_mm, em_mm) where radius_mm is the bubble head
        radius and em_mm is the corresponding font em size, both in mm.
    """
    f = QFont("Consolas")
    f.setBold(True)
    f.setPixelSize(TEXT_METRIC_REF_PX)
    cap_ratio = QFontMetricsF(f).capHeight() / TEXT_METRIC_REF_PX
    em_mm = cap_mm / (cap_ratio if cap_ratio > 0 else 0.7)
    return em_mm / GRIDLINE_BUBBLE_LABEL_EM_FRAC, em_mm


class GridlineItem(QGraphicsLineItem):
    """A finite gridline with auto-numbered bubble labels at each end."""

    def __init__(self, p1: QPointF, p2: QPointF, label: str | None = None):
        super().__init__(p1.x(), p1.y(), p2.x(), p2.y())

        # Store the desired colour; drawing is handled entirely in paint()
        # using a non-cosmetic pen with width calculated from the view
        # transform.  This avoids Qt's cosmetic-pen rasteriser which
        # fails silently after a few zoom steps on some platforms.
        self._grid_color = QColor(GRID_COLOR)
        self.setPen(QPen(Qt.PenStyle.NoPen))       # suppress default drawing

        # Flags
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(-10)  # below geometry and annotations

        # Auto-assign label
        if label is None:
            label = auto_label(p1, p2)
        self._label_text = label

        # ── Parametric state (source of truth) ──────────────────────────
        self._origin = QPointF(p1)
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        self._length = math.hypot(dx, dy)
        self._angle_deg = math.degrees(math.atan2(-dy, dx)) % 360.0
        self._bubble1_offset = float(GRIDLINE_BUBBLE_OFFSET_MM)
        self._bubble2_offset = float(GRIDLINE_BUBBLE_OFFSET_MM)

        # Lock state (must be set before _LockIndicator creation)
        self._locked = False

        # Bubbles, grips, lock indicator
        self.bubble1 = GridBubble(label, self)
        self.bubble2 = GridBubble(label, self)
        self._grip1 = _PullTabGrip(self)
        self._grip2 = _PullTabGrip(self)
        self._lock_indicator = _LockIndicator(self)

        # Hover events for grip visibility
        self.setAcceptHoverEvents(True)

        self._display_overrides: dict = {}  # per-instance display overrides
        self._display_scale: float = 1.0    # display scale for bubbles
        # Write-together unit: the three _paper_* attributes are set only by
        # paper_display's override pass (_apply_gridline / restore) — never
        # mutate one without the others.
        self._paper_render = False        # True during a paper override pass
        self._paper_line_w = 0.0          # line/border width, scene units (paper pass)
        self._paper_bubble_r = 0.0        # bubble radius, scene units (paper pass)

        self._rebuild_geometry()

    # ── Geometry overrides ────────────────────────────────────────────────

    def boundingRect(self):
        """Expand bounding rect with a small margin for the pen.

        Bubbles and grips use ItemIgnoresTransformations and manage
        their own bounds independently.
        """
        br = super().boundingRect()
        # Account for bubbles positioned outboard of each endpoint plus pen.
        m = max(20.0, self._bubble1_offset, self._bubble2_offset) + 20.0
        return br.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        """Return the selectable hit area: the line body with a generous
        stroke width plus the bubble positions for marquee selection."""
        path = QPainterPath()
        line = self.line()
        # Add a stroked version of the line with generous hit width
        line_path = QPainterPath()
        line_path.moveTo(line.p1())
        line_path.lineTo(line.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(40.0)  # scene units — generous click target
        path = stroker.createStroke(line_path)
        # Also include bubble positions for marquee selection
        r = 50.0
        path.addEllipse(self.bubble1.pos(), r, r)
        path.addEllipse(self.bubble2.pos(), r, r)
        return path

    def itemChange(self, change, value):
        """Refresh bubble paint and show/hide grips + lock indicator on selection change."""
        if change == self.GraphicsItemChange.ItemSelectedChange:
            selected = bool(value)
            # Show grips only when selected AND unlocked
            self._grip1.setVisible(selected and not self._locked)
            self._grip2.setVisible(selected and not self._locked)
            # Show lock indicator when selected
            self._lock_indicator.setVisible(selected)
            if selected:
                self._lock_indicator._rebuild()
        if change == self.GraphicsItemChange.ItemSelectedHasChanged:
            self.bubble1.update()
            self.bubble2.update()
        return super().itemChange(change, value)

    # ── Parametric accessors ──────────────────────────────────────────────

    def origin(self) -> QPointF:
        return QPointF(self._origin)

    def length(self) -> float:
        return self._length

    def angle_deg(self) -> float:
        return self._angle_deg

    def bubble1_offset(self) -> float:
        return self._bubble1_offset

    def bubble2_offset(self) -> float:
        return self._bubble2_offset

    def _direction(self) -> tuple[float, float]:
        th = math.radians(self._angle_deg)
        return (math.cos(th), -math.sin(th))

    def _far_point(self) -> QPointF:
        dx, dy = self._direction()
        return QPointF(self._origin.x() + self._length * dx,
                       self._origin.y() + self._length * dy)

    def _rebuild_geometry(self):
        """Single writer: sync the underlying line() + bubbles/grips/lock
        from the parametric state (_origin/_length/_angle_deg/offsets)."""
        p1 = self._origin
        p2 = self._far_point()
        self.prepareGeometryChange()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())
        dx, dy = self._direction()
        self.bubble1.setPos(p1.x() - self._bubble1_offset * dx,
                            p1.y() - self._bubble1_offset * dy)
        self.bubble2.setPos(p2.x() + self._bubble2_offset * dx,
                            p2.y() + self._bubble2_offset * dy)
        self._update_grip_positions()
        if hasattr(self, "_lock_indicator"):
            self._lock_indicator.setPos(self.bubble1.pos())
        self.update()

    # ── Parametric mutators ───────────────────────────────────────────────

    def set_origin_x(self, x: float):
        if self._locked:
            return
        self._origin.setX(float(x))
        self._rebuild_geometry()

    def set_origin_y(self, y: float):
        if self._locked:
            return
        self._origin.setY(float(y))
        self._rebuild_geometry()

    def set_length(self, length: float):
        if self._locked:
            return
        self._length = max(1.0, float(length))
        self._rebuild_geometry()

    def set_angle_deg(self, angle: float):
        if self._locked:
            return
        self._angle_deg = float(angle) % 360.0
        self._rebuild_geometry()

    def set_bubble_offset(self, end: int, offset: float):
        val = max(0.0, float(offset))
        if end == 1:
            self._bubble1_offset = val
        else:
            self._bubble2_offset = val
        self._rebuild_geometry()

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
        if not self.isSelected() and not self._locked:
            self._grip1.setVisible(True)
            self._grip2.setVisible(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self._grip1.setVisible(False)
            self._grip2.setVisible(False)
        super().hoverLeaveEvent(event)

    # ── Selection highlight (suppress dashed box) ─────────────────────────

    def _build_line_pen(self, sx: float) -> QPen:
        """Build the screen-path dash-dot pen for view scale ``sx``.

        The pen is non-cosmetic (width in scene units), with an explicit
        dash pattern computed for a fixed on-screen pixel dash-dot so it
        stays legible at any zoom (Qt's ``DashDotLine`` pattern is in
        pen-width multiples and collapses when zoomed out).
        """
        pen_w = GRID_WIDTH / max(sx, 1e-9)
        pen = QPen(self._grid_color, pen_w)
        pen.setDashPattern(_dash_pattern_px(sx))
        return pen

    def paint(self, painter, option, widget=None):
        """Draw the gridline as a bubble-spanning dash-dot line.

        The pen width is derived from the current view transform (screen
        path) or the paper geometry (paper path); the dash pattern is set
        explicitly so it renders as a legible dash-dot at any zoom and in
        exported PDF.  The line is shortened at each end so it meets the
        visible bubble at its edge rather than its centre.
        """
        option.state &= ~QStyle.StateFlag.State_Selected

        if self._paper_render:
            pen_w = self._paper_line_w
            scene_r = self._paper_bubble_r
            pen = QPen(self._grid_color, pen_w)
            pen.setDashPattern(_dash_pattern_mm(pen_w))
            sx = None
        else:
            # Calculate pen width to maintain ~GRID_WIDTH screen pixels
            vt = painter.deviceTransform()
            sx = max(abs(vt.m11()), abs(vt.m22()), 1e-9)
            pen_w = GRID_WIDTH / sx
            scene_r = GridBubble.RADIUS_PX / sx  # pixel radius → scene units
            pen = self._build_line_pen(sx)

        # Shorten line to meet visible bubbles at their edge.
        # Bubbles use ItemIgnoresTransformations (screen mode) or scene-unit
        # geometry (paper mode); scene_r is set appropriately above.
        b1 = self.bubble1.pos()
        b2 = self.bubble2.pos()
        dx = b2.x() - b1.x()
        dy = b2.y() - b1.y()
        length = math.hypot(dx, dy)
        if length > 1e-9:
            ux, uy = dx / length, dy / length
            draw_p1 = QPointF(b1.x() + ux * scene_r, b1.y() + uy * scene_r) if self.bubble1.isVisible() else b1
            draw_p2 = QPointF(b2.x() - ux * scene_r, b2.y() - uy * scene_r) if self.bubble2.isVisible() else b2
        else:
            draw_p1, draw_p2 = b1, b2

        painter.setPen(pen)
        painter.drawLine(draw_p1, draw_p2)

        if self.isSelected() and not self._paper_render:
            sel_pen = QPen(self._grid_color.lighter(150), pen_w * 2)
            sel_pen.setDashPattern(_dash_pattern_px(sx))
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
        offset_x = nx * distance
        offset_y = ny * distance
        self._origin.setX(self._origin.x() + offset_x)
        self._origin.setY(self._origin.y() + offset_y)
        self._rebuild_geometry()

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
        """Translate the entire gridline by dragging a grip handle.

        Both grip indices move the whole gridline freely in 2D.
        Locked gridlines are not affected.
        """
        if self._locked:
            return
        line = self.line()
        p1, p2 = line.p1(), line.p2()

        # Current grip position
        current = p1 if index == 0 else p2

        # Delta from current to new
        dx = new_pos.x() - current.x()
        dy = new_pos.y() - current.y()

        # Translate the whole gridline (parametric: shift origin)
        self._origin.setX(self._origin.x() + dx)
        self._origin.setY(self._origin.y() + dy)
        self._rebuild_geometry()

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        line = self.line()
        d = {
            "p1": [line.p1().x(), line.p1().y()],
            "p2": [line.p2().x(), line.p2().y()],
            "label": self._label_text,
            "bubble1_vis": self.bubble1.isVisible(),
            "bubble2_vis": self.bubble2.isVisible(),
            "locked": self._locked,
        }
        if self._display_overrides:
            d["display_overrides"] = self._display_overrides
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GridlineItem":
        # Migration: old GridLine format used "start"/"end" instead of "p1"/"p2"
        if "p1" in d:
            p1 = QPointF(d["p1"][0], d["p1"][1])
            p2 = QPointF(d["p2"][0], d["p2"][1])
        else:
            p1 = QPointF(d["start"][0], d["start"][1])
            p2 = QPointF(d["end"][0], d["end"][1])
        item = cls(p1, p2, label=d.get("label", "?"))
        # Handle old-format key renames for bubble visibility
        b1_vis = d.get("bubble1_vis", d.get("bubble_start", True))
        b2_vis = d.get("bubble2_vis", d.get("bubble_end", True))
        item.bubble1.setVisible(b1_vis)
        item.bubble2.setVisible(b2_vis)
        item._locked = d.get("locked", False)
        item._display_overrides = d.get("display_overrides", {})
        # Silently ignore "level" and "axis" keys from old files
        return item

    # ── Properties for property panel ─────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Label": {"type": "string", "value": self._label_text},
            "Bubble 1": {"type": "enum", "options": ["Visible", "Hidden"],
                         "value": "Visible" if self.bubble1.isVisible() else "Hidden"},
            "Bubble 2": {"type": "enum", "options": ["Visible", "Hidden"],
                         "value": "Visible" if self.bubble2.isVisible() else "Hidden"},
            "Locked": {"type": "enum", "options": ["True", "False"], "value": str(self._locked)},
        }

    def set_property(self, key: str, value):
        if key == "Label":
            self.grid_label = str(value)
            sc = self.scene()
            if sc and hasattr(sc, '_gridlines'):
                apply_duplicate_warnings(sc._gridlines)
        elif key == "Bubble 1":
            self.bubble1.setVisible(value == "Visible")
        elif key == "Bubble 2":
            self.bubble2.setVisible(value == "Visible")
        elif key == "Locked":
            self._locked = value in ("True", True)

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
