"""
view_marker.py
==============
Elevation (and future section) view markers for the 2D Model plan view.

All four elevation markers (N/S/E/W) share a **single bounding rectangle**.
Each triangle sits at the midpoint of one side of that rectangle.
When any marker is selected, the shared crop box appears with grip handles
for resizing.  The crop box defines the visible extent for all elevation views.

Designed to be reusable for section views (view_type="section" + angle).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsItem,
    QStyle,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QPolygonF, QFont, QPainter, QPainterPath,
)

from .constants import DEFAULT_LEVEL
from .gridline import BUBBLE_RADIUS_MM, GRID_COLOR

if TYPE_CHECKING:
    from .model_space import Model_Space


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Triangle size = 3× the gridline bubble diameter
MARKER_SIZE = BUBBLE_RADIUS_MM * 6.0   # ~1219mm — matches 3× bubble size
CROP_MARGIN = 2000.0                   # mm — default crop box padding


# ─────────────────────────────────────────────────────────────────────────────
# SharedCropBox — single dashed rectangle for all elevation markers
# ─────────────────────────────────────────────────────────────────────────────

class SharedCropBox(QGraphicsRectItem):
    """A single dashed rectangle shared by all elevation markers.

    Visible only when any marker is selected.  Resizable via grip handles.
    The rect is in scene coordinates and defines the building extent
    for all elevation views.
    """

    def __init__(self, rect: QRectF, parent: QGraphicsItem | None = None):
        super().__init__(rect, parent)

        pen = QPen(QColor(GRID_COLOR), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        fill = QColor(GRID_COLOR)
        fill.setAlpha(15)
        self.setBrush(QBrush(fill))
        self.setZValue(-200)
        self.setVisible(False)

        # Not selectable itself
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    # ── Grip protocol ────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """8 grips: 4 corners + 4 edge midpoints (scene coords)."""
        r = self.rect()
        pts = [
            r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft(),
            QPointF(r.center().x(), r.top()),
            QPointF(r.right(), r.center().y()),
            QPointF(r.center().x(), r.bottom()),
            QPointF(r.left(), r.center().y()),
        ]
        return [self.mapToScene(p) for p in pts]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Resize the shared rect from a grip drag."""
        local = self.mapFromScene(new_pos)
        r = self.rect()

        if index == 0:
            r.setTopLeft(local)
        elif index == 1:
            r.setTopRight(local)
        elif index == 2:
            r.setBottomRight(local)
        elif index == 3:
            r.setBottomLeft(local)
        elif index == 4:
            r.setTop(local.y())
        elif index == 5:
            r.setRight(local.x())
        elif index == 6:
            r.setBottom(local.y())
        elif index == 7:
            r.setLeft(local.x())

        r = r.normalized()
        self.setRect(r)

        # Reposition markers to midpoints of the resized rect
        mgr = getattr(self, "_manager", None)
        if mgr is not None:
            mgr._reposition_markers_to_rect(r)


# ─────────────────────────────────────────────────────────────────────────────
# ViewMarkerArrow — filled triangle with cardinal letter
# ─────────────────────────────────────────────────────────────────────────────

class ViewMarkerArrow(QGraphicsPolygonItem):
    """Elevation marker: circle with cardinal letter + two tangent lines
    meeting at a point toward the building.

    Shares a single crop box managed by ViewMarkerManager.
    """

    _CIRCLE_R = BUBBLE_RADIUS_MM * 3.0          # circle radius (3× default)
    # Tip distance chosen so the two tangent lines meet at ~80°:
    # half-angle = 40°, D = R / sin(40°) ≈ R * 1.556
    _POINT_DIST = BUBBLE_RADIUS_MM * 3.0 / math.sin(math.radians(40))

    def __init__(self, direction: str, view_type: str = "elevation",
                 parent: QGraphicsItem | None = None):
        super().__init__(parent)
        self._direction = direction.lower()
        self._view_type = view_type
        self._manager = None  # set by ViewMarkerManager

        # Build bounding polygon (used for hit-testing footprint)
        self._size = MARKER_SIZE
        self.setPolygon(self._build_outline_polygon())

        # Appearance: use gridline color scheme
        self._marker_color = QColor(GRID_COLOR)
        self._fill_color = QColor("#1a1a2e")
        pen_w = max(1.0, BUBBLE_RADIUS_MM * 0.04)
        pen = QPen(self._marker_color, pen_w)
        self.setPen(pen)
        self.setBrush(QBrush(self._fill_color))
        self.setZValue(200)

        # Selectable (NOT movable — position pinned to shared box midlines)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self._exclude_from_bulk_select = True  # skip Ctrl+A / rubber-band

        # Ensure this level attribute exists for display manager categorization
        self.level = DEFAULT_LEVEL
        self.user_layer: str = "Default"

    @property
    def direction(self) -> str:
        return self._direction

    @property
    def view_type(self) -> str:
        return self._view_type

    @property
    def crop_box(self):
        """Return the shared crop box from the manager."""
        if self._manager is not None:
            return self._manager._crop_box
        return None

    # ── Geometry ──────────────────────────────────────────────────────────

    def _tip_direction(self) -> tuple[float, float]:
        """Unit vector from circle center toward the building (tip direction)."""
        if self._direction == "north":
            return (0, 1)     # tip points down (+Y = toward building in plan)
        elif self._direction == "south":
            return (0, -1)
        elif self._direction == "east":
            return (-1, 0)    # east looks left (−X toward building)
        elif self._direction == "west":
            return (1, 0)     # west looks right (+X toward building)
        return (0, 1)

    def _tangent_points_and_tip(self):
        """Return (tangent_left, tangent_right, tip) in local coords."""
        R = self._CIRCLE_R
        D = self._POINT_DIST
        dx, dy = self._tip_direction()

        # Tip point
        tip = QPointF(dx * D, dy * D)

        # Angle of tangent lines from center-to-tip axis
        # For a circle of radius R and external point at distance D:
        # tangent touches at angle ±arccos(R/D) from the axis
        alpha = math.acos(min(R / D, 1.0))

        # Base angle of the direction vector
        base_angle = math.atan2(dy, dx)

        # Tangent points on the circle
        a1 = base_angle + alpha
        a2 = base_angle - alpha
        t1 = QPointF(R * math.cos(a1), R * math.sin(a1))
        t2 = QPointF(R * math.cos(a2), R * math.sin(a2))

        return t1, t2, tip

    def _build_outline_polygon(self) -> QPolygonF:
        """Build a polygon that encloses the circle + tangent lines for hit-testing."""
        t1, t2, tip = self._tangent_points_and_tip()
        R = self._CIRCLE_R
        # Approximate: polygon = circle bounding box corners + tip
        return QPolygonF([
            QPointF(-R, -R), QPointF(R, -R),
            QPointF(R, R), QPointF(-R, R),
            tip,
        ])

    # ── Drawing ──────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None):
        """Draw circle with cardinal letter + two tangent lines to a point."""
        option.state &= ~QStyle.StateFlag.State_Selected

        R = self._CIRCLE_R
        pen_w = max(1.0, R * 0.04)
        t1, t2, tip = self._tangent_points_and_tip()

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Filled wedge (area enclosed by tangent lines + arc) ───────
        # Build path: t1 → tip → t2 → arc back to t1
        dx, dy = self._tip_direction()
        base_angle = math.atan2(dy, dx)
        alpha = math.acos(min(R / self._POINT_DIST, 1.0))
        # Qt arc angles in degrees × 16, measured counter-clockwise from 3-o'clock
        a1_deg = -math.degrees(base_angle + alpha)   # tangent point 1 angle
        a2_deg = -math.degrees(base_angle - alpha)   # tangent point 2 angle
        sweep = a1_deg - a2_deg
        # Normalise sweep to go the short way around (through the side away from tip)
        while sweep > 180:
            sweep -= 360
        while sweep < -180:
            sweep += 360

        wedge = QPainterPath()
        wedge.moveTo(t1)
        wedge.lineTo(tip)
        wedge.lineTo(t2)
        arc_rect = QRectF(-R, -R, 2 * R, 2 * R)
        wedge.arcTo(arc_rect, a2_deg, sweep)
        wedge.closeSubpath()

        painter.setPen(QPen(self._marker_color, pen_w))
        painter.setBrush(QBrush(self._marker_color))
        painter.drawPath(wedge)

        # ── Filled circle ────────────────────────────────────────────
        painter.setBrush(QBrush(self._fill_color))
        painter.drawEllipse(QPointF(0, 0), R, R)

        # ── Selection highlight ──────────────────────────────────────
        if self.isSelected():
            highlight_pen = QPen(self._marker_color.lighter(150),
                                 max(1, R * 0.08))
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), R, R)
            painter.drawLine(t1, tip)
            painter.drawLine(t2, tip)

        # ── Cardinal letter centered in circle ───────────────────────
        letter = self._direction[0].upper()
        font = QFont("Consolas")
        font_pt = getattr(self, "_display_font_size", None)
        if font_pt is not None:
            font.setPixelSize(max(1, int(R * (font_pt / 10.0))))
        else:
            font.setPixelSize(max(1, int(R * 1.0)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(self._marker_color.lighter(150)))
        # Draw letter centered in the circle, not the full bounding rect
        circle_rect = QRectF(-R, -R, 2 * R, 2 * R)
        painter.drawText(circle_rect, Qt.AlignmentFlag.AlignCenter, letter)

    def boundingRect(self) -> QRectF:
        R = self._CIRCLE_R
        D = self._POINT_DIST
        m = max(R, D) + R * 0.1  # small margin
        return QRectF(-m, -m, 2 * m, 2 * m)

    def shape(self) -> QPainterPath:
        """Selectable area = circle + tangent-line region."""
        path = QPainterPath()
        R = self._CIRCLE_R
        path.addEllipse(QPointF(0, 0), R, R)
        t1, t2, tip = self._tangent_points_and_tip()
        path.moveTo(t1)
        path.lineTo(tip)
        path.lineTo(t2)
        path.closeSubpath()
        return path

    # ── Selection → show/hide shared crop box ─────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if self._manager is not None:
                self._manager._on_marker_selection_changed()
            self.update()
        return super().itemChange(change, value)

    # ── Double-click → open view ──────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        sc = self.scene()
        if sc is not None and hasattr(sc, "openViewRequested"):
            sc.openViewRequested.emit(self._view_type, self._direction)
        event.accept()

    # ── Grip protocol (forward to shared crop box) ────────────────────────

    def grip_points(self) -> list[QPointF]:
        if self.isSelected() and self._manager is not None:
            box = self._manager._crop_box
            if box is not None and box.isVisible():
                return box.grip_points()
        return []

    def apply_grip(self, index: int, new_pos: QPointF):
        if self._manager is not None:
            box = self._manager._crop_box
            if box is not None:
                box.apply_grip(index, new_pos)

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "direction": self._direction,
            "view_type": self._view_type,
            "pos_x": self.pos().x(),
            "pos_y": self.pos().y(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ViewMarkerArrow":
        marker = cls(
            direction=data["direction"],
            view_type=data.get("view_type", "elevation"),
        )
        marker.setPos(data.get("pos_x", 0), data.get("pos_y", 0))
        return marker


# ─────────────────────────────────────────────────────────────────────────────
# ViewMarkerManager — creates and manages all markers + shared crop box
# ─────────────────────────────────────────────────────────────────────────────

class ViewMarkerManager:
    """Creates and manages elevation markers with a shared crop rectangle.

    All four markers (N/S/E/W) are pinned to the midpoints of the shared
    bounding box edges.  Selecting any marker shows the shared crop box.
    """

    def __init__(self, scene: "Model_Space"):
        self._scene = scene
        self._markers: dict[str, ViewMarkerArrow] = {}
        self._crop_box: SharedCropBox | None = None

    def create_elevation_markers(self):
        """Create N/S/E/W markers around the gridline bbox with a shared crop box."""
        bbox = self._gridline_bbox()
        crop_rect = QRectF(
            bbox.left() - CROP_MARGIN,
            bbox.top() - CROP_MARGIN,
            bbox.width() + CROP_MARGIN * 2,
            bbox.height() + CROP_MARGIN * 2,
        )

        # Create shared crop box
        self._crop_box = SharedCropBox(crop_rect)
        self._crop_box._manager = self
        self._scene.addItem(self._crop_box)

        # Create 4 markers pinned to midpoints of the crop rect edges
        for direction in ("north", "south", "east", "west"):
            if direction in self._markers:
                continue
            marker = ViewMarkerArrow(direction, "elevation")
            marker._manager = self
            self._scene.addItem(marker)
            self._markers[direction] = marker

        self._reposition_markers_to_rect(crop_rect)

    def _reposition_markers_to_rect(self, rect: QRectF):
        """Pin all markers so the arrow tip meets the midpoint of each edge."""
        cx = rect.center().x()
        cy = rect.center().y()
        # The circle center is _POINT_DIST away from the tip, so offset
        # the center by that amount + a 25 mm gap outward from the rect edge.
        gap = 25.0  # mm offset between tip and bounding box edge
        d = ViewMarkerArrow._POINT_DIST + gap

        positions = {
            "north": QPointF(cx, rect.top() - d),
            "south": QPointF(cx, rect.bottom() + d),
            "east":  QPointF(rect.right() + d, cy),
            "west":  QPointF(rect.left() - d, cy),
        }

        for direction, pos in positions.items():
            marker = self._markers.get(direction)
            if marker is not None:
                marker.setPos(pos)

    def _on_marker_selection_changed(self):
        """Show crop box if ANY marker is selected, hide if none are."""
        any_selected = any(m.isSelected() for m in self._markers.values())
        if self._crop_box is not None:
            self._crop_box.setVisible(any_selected)

    def remove_all(self):
        """Remove all markers and the crop box from the scene."""
        for marker in self._markers.values():
            if marker.scene() is self._scene:
                self._scene.removeItem(marker)
        self._markers.clear()
        if self._crop_box is not None and self._crop_box.scene() is self._scene:
            self._scene.removeItem(self._crop_box)
            self._crop_box = None

    def get_marker(self, direction: str) -> ViewMarkerArrow | None:
        return self._markers.get(direction.lower())

    def get_crop_rect(self) -> QRectF | None:
        """Get the shared crop rect in scene coordinates."""
        if self._crop_box is None:
            return None
        return self._crop_box.mapRectToScene(self._crop_box.rect())

    def _gridline_bbox(self) -> QRectF:
        """Compute bounding box of all gridline endpoints in scene coords."""
        gridlines = getattr(self._scene, "_gridlines", [])
        if not gridlines:
            return QRectF(-10000, -10000, 20000, 20000)

        xs, ys = [], []
        for gl in gridlines:
            line = gl.line()
            p1 = gl.mapToScene(line.p1())
            p2 = gl.mapToScene(line.p2())
            xs.extend([p1.x(), p2.x()])
            ys.extend([p1.y(), p2.y()])

        return QRectF(
            min(xs), min(ys),
            max(xs) - min(xs), max(ys) - min(ys),
        )

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        result: dict = {}
        if self._crop_box is not None:
            r = self._crop_box.rect()
            result["crop_rect"] = {
                "x": r.x(), "y": r.y(),
                "w": r.width(), "h": r.height(),
            }
        result["markers"] = [m.to_dict() for m in self._markers.values()]
        return result

    def from_dict(self, data: dict):
        self.remove_all()
        cr = data.get("crop_rect")
        if cr:
            rect = QRectF(cr["x"], cr["y"], cr["w"], cr["h"])
        else:
            bbox = self._gridline_bbox()
            rect = QRectF(
                bbox.left() - CROP_MARGIN, bbox.top() - CROP_MARGIN,
                bbox.width() + CROP_MARGIN * 2, bbox.height() + CROP_MARGIN * 2,
            )

        self._crop_box = SharedCropBox(rect)
        self._crop_box._manager = self
        self._scene.addItem(self._crop_box)

        for item in data.get("markers", []):
            marker = ViewMarkerArrow.from_dict(item)
            marker._manager = self
            self._scene.addItem(marker)
            self._markers[marker.direction] = marker

        self._reposition_markers_to_rect(rect)
