"""
wall_opening.py
===============
Door and Window opening entities for FirePro 3D.

Openings belong to a parent WallSegment and are defined by their
position along the wall centerline, width, height, and (for windows)
sill height.  They produce standard 2D plan-view symbols and cut
rectangular holes from the wall's 3D mesh.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsPathItem, QStyle, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QPen, QColor, QPainterPath, QBrush, QPainterPathStroker,
)

if TYPE_CHECKING:
    from .wall import WallSegment

from .constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER


# ── Preset libraries ─────────────────────────────────────────────────────────

# Width × Height in mm
DOOR_PRESETS = {
    "820×2040":  (820,  2040),
    "920×2040":  (920,  2040),
    "1200×2040": (1200, 2040),
    "1800×2040": (1800, 2040),   # double door
}
DOOR_DEFAULT = "920×2040"

WINDOW_PRESETS = {
    "600×600":   (600,  600),
    "900×1200":  (900,  1200),
    "1200×1500": (1200, 1500),
    "1800×1200": (1800, 1200),
}
WINDOW_DEFAULT = "900×1200"

_SELECTION_COLOR = QColor("red")
_DOOR_COLOR = QColor("#aa6633")
_WINDOW_COLOR = QColor("#3399cc")


def _scene_hit_width(item) -> float:
    sc = item.scene()
    if sc:
        views = sc.views()
        if views:
            scale = views[0].transform().m11()
            return max(4.0, 12.0 / max(scale, 1e-6))
    return 6.0


# ── Base class ───────────────────────────────────────────────────────────────

class WallOpening(QGraphicsPathItem):
    """Base class for openings in a wall segment.

    An opening is positioned along the wall by ``offset_along``, which is
    the distance from pt1 of the parent wall to the center of the opening
    (in scene units).
    """

    KIND = "opening"   # overridden by subclasses

    def __init__(self, wall: WallSegment | None = None,
                 width_mm: float = 920.0,
                 height_mm: float = 2040.0,
                 sill_mm: float = 0.0,
                 offset_along: float = 0.0):
        super().__init__()
        self._wall = wall
        self._width_mm: float = width_mm
        self._height_mm: float = height_mm
        self._sill_mm: float = sill_mm         # distance from floor (windows)
        self._offset_along: float = offset_along  # scene units from wall pt1

        self.level: str = DEFAULT_LEVEL
        self.user_layer: str = DEFAULT_USER_LAYER

        self.setZValue(-45)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        if wall is not None:
            self._reposition()

    # ── Geometry ─────────────────────────────────────────────────────────────

    @property
    def wall(self) -> WallSegment | None:
        return self._wall

    @wall.setter
    def wall(self, w: WallSegment | None):
        self._wall = w
        if w is not None:
            self._reposition()

    def width_scene(self) -> float:
        """Opening width in scene units."""
        sc = self.scene() if self._wall is None else self._wall.scene()
        if sc and hasattr(sc, "scale_manager"):
            sm = sc.scale_manager
            if sm.is_calibrated and sm.drawing_scale > 0:
                paper_mm = self._width_mm / sm.drawing_scale
                return sm.paper_to_scene(paper_mm)
        return self._width_mm * 0.15   # fallback

    def center_on_wall(self) -> QPointF:
        """World position of the opening center on the wall centerline."""
        if self._wall is None:
            return QPointF(0, 0)
        a = self._wall.centerline_angle_rad()
        return QPointF(
            self._wall.pt1.x() + self._offset_along * math.cos(a),
            self._wall.pt1.y() + self._offset_along * math.sin(a),
        )

    def _reposition(self):
        """Recompute path and position based on parent wall."""
        if self._wall is None:
            return
        center = self.center_on_wall()
        self.setPos(center)
        self._rebuild_path()

    def _rebuild_path(self):
        """Override in subclasses for door/window specific symbols."""
        pass

    # ── Paint ────────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Subclasses implement drawing
        self._paint_symbol(painter)
        if self.isSelected():
            sel_pen = QPen(_SELECTION_COLOR, 2)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())

    def _paint_symbol(self, painter):
        """Override in subclasses."""
        pass

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        path = self.path()
        if path.isEmpty():
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path) | path

    # ── Properties ───────────────────────────────────────────────────────────

    def _fmt(self, mm: float) -> str:
        from .format_utils import fmt_length
        return fmt_length(self, mm)

    def get_properties(self) -> dict:
        return {
            "Type":       {"type": "label", "value": self.KIND.title()},
            "Width":      {"type": "string", "value": self._fmt(self._width_mm)},
            "Height":     {"type": "string", "value": self._fmt(self._height_mm)},
        }

    def set_property(self, key: str, value):
        if key in ("Width", "Width (mm)"):
            try:
                self._width_mm = float(value)
            except (ValueError, TypeError):
                return
            self._reposition()
        elif key in ("Height", "Height (mm)"):
            try:
                self._height_mm = float(value)
            except (ValueError, TypeError):
                return

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "kind":          self.KIND,
            "width_mm":      self._width_mm,
            "height_mm":     self._height_mm,
            "sill_mm":       self._sill_mm,
            "offset_along":  self._offset_along,
            "level":         self.level,
            "user_layer":    self.user_layer,
        }

    @classmethod
    def from_dict(cls, data: dict, wall: WallSegment | None = None) -> "WallOpening":
        kind = data.get("kind", "door")
        if kind == "window":
            obj = WindowOpening(
                wall=wall,
                width_mm=data.get("width_mm", 900),
                height_mm=data.get("height_mm", 1200),
                sill_mm=data.get("sill_mm", 900),
                offset_along=data.get("offset_along", 0),
            )
        else:
            obj = DoorOpening(
                wall=wall,
                width_mm=data.get("width_mm", 920),
                height_mm=data.get("height_mm", 2040),
                offset_along=data.get("offset_along", 0),
            )
        obj.level = data.get("level", DEFAULT_LEVEL)
        obj.user_layer = data.get("user_layer", DEFAULT_USER_LAYER)
        return obj

    # ── Translate ────────────────────────────────────────────────────────────

    def translate(self, dx: float, dy: float):
        """Move along wall — adjust offset_along by projected distance."""
        if self._wall is None:
            return
        a = self._wall.centerline_angle_rad()
        proj = dx * math.cos(a) + dy * math.sin(a)
        self._offset_along += proj
        self._reposition()


# ── DoorOpening ──────────────────────────────────────────────────────────────

class DoorOpening(WallOpening):
    """Door opening — 2D symbol: rectangle with arc swing indicator."""

    KIND = "door"

    def __init__(self, wall=None, width_mm=920, height_mm=2040,
                 offset_along=0, preset: str | None = None):
        if preset and preset in DOOR_PRESETS:
            width_mm, height_mm = DOOR_PRESETS[preset]
        super().__init__(wall=wall, width_mm=width_mm, height_mm=height_mm,
                         sill_mm=0, offset_along=offset_along)
        self._preset: str = preset or DOOR_DEFAULT

    def _rebuild_path(self):
        if self._wall is None:
            self.setPath(QPainterPath())
            return

        half_w = self.width_scene() / 2.0
        ht = self._wall.half_thickness_scene()
        a = self._wall.centerline_angle_rad()

        # Local coords: wall runs along X, normal along Y
        path = QPainterPath()
        # Gap rectangle (clear wall lines)
        path.addRect(-half_w, -ht, half_w * 2, ht * 2)
        # Door swing arc (90-degree arc from hinge side)
        arc_rect = QPainterPath()
        arc_rect.moveTo(-half_w, -ht)
        arc_rect.arcTo(-half_w - half_w, -ht - half_w * 2,
                       half_w * 2, half_w * 2, 0, -90)
        path.addPath(arc_rect)

        self.setPath(path)
        # Rotate to match wall angle
        self.setRotation(math.degrees(a))

    def _paint_symbol(self, painter):
        if self._wall is None:
            return
        half_w = self.width_scene() / 2.0
        ht = self._wall.half_thickness_scene()

        pen = QPen(_DOOR_COLOR, 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)

        # Clear fill for gap
        painter.setBrush(QBrush(QColor(30, 30, 30)))
        painter.drawRect(QPointF(-half_w, -ht).x(), QPointF(-half_w, -ht).y(),
                         half_w * 2, ht * 2)

        # Door leaf line
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(-half_w, ht), QPointF(half_w, ht))

        # Swing arc
        from PyQt6.QtCore import QRectF
        arc_rect = QRectF(-half_w, ht - half_w * 2, half_w * 2, half_w * 2)
        painter.drawArc(arc_rect, 0, 90 * 16)

    def get_properties(self) -> dict:
        props = super().get_properties()
        props["Preset"] = {
            "type": "enum",
            "value": self._preset,
            "options": list(DOOR_PRESETS.keys()) + ["Custom"],
        }
        return props

    def set_property(self, key: str, value):
        if key == "Preset" and value in DOOR_PRESETS:
            self._preset = value
            self._width_mm, self._height_mm = DOOR_PRESETS[value]
            self._reposition()
        else:
            super().set_property(key, value)


# ── WindowOpening ────────────────────────────────────────────────────────────

class WindowOpening(WallOpening):
    """Window opening — 2D symbol: rectangle with crossing diagonal lines."""

    KIND = "window"

    def __init__(self, wall=None, width_mm=900, height_mm=1200,
                 sill_mm=900, offset_along=0, preset: str | None = None):
        if preset and preset in WINDOW_PRESETS:
            width_mm, height_mm = WINDOW_PRESETS[preset]
        super().__init__(wall=wall, width_mm=width_mm, height_mm=height_mm,
                         sill_mm=sill_mm, offset_along=offset_along)
        self._preset: str = preset or WINDOW_DEFAULT

    def _rebuild_path(self):
        if self._wall is None:
            self.setPath(QPainterPath())
            return

        half_w = self.width_scene() / 2.0
        ht = self._wall.half_thickness_scene()
        a = self._wall.centerline_angle_rad()

        path = QPainterPath()
        # Rectangle
        path.addRect(-half_w, -ht, half_w * 2, ht * 2)
        # Crossing lines
        path.moveTo(-half_w, -ht)
        path.lineTo(half_w, ht)
        path.moveTo(-half_w, ht)
        path.lineTo(half_w, -ht)

        self.setPath(path)
        self.setRotation(math.degrees(a))

    def _paint_symbol(self, painter):
        if self._wall is None:
            return
        half_w = self.width_scene() / 2.0
        ht = self._wall.half_thickness_scene()

        pen = QPen(_WINDOW_COLOR, 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)

        # Fill for gap
        painter.setBrush(QBrush(QColor(40, 60, 80, 100)))
        from PyQt6.QtCore import QRectF
        rect = QRectF(-half_w, -ht, half_w * 2, ht * 2)
        painter.drawRect(rect)

        # Crossing diagonals
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(-half_w, -ht), QPointF(half_w, ht))
        painter.drawLine(QPointF(-half_w, ht), QPointF(half_w, -ht))

        # Center horizontal line (glass pane indicator)
        painter.drawLine(QPointF(-half_w, 0), QPointF(half_w, 0))

    def get_properties(self) -> dict:
        props = super().get_properties()
        props["Sill Height"] = {
            "type": "string", "value": self._fmt(self._sill_mm),
        }
        props["Preset"] = {
            "type": "enum",
            "value": self._preset,
            "options": list(WINDOW_PRESETS.keys()) + ["Custom"],
        }
        return props

    def set_property(self, key: str, value):
        if key in ("Sill Height", "Sill Height (mm)"):
            try:
                self._sill_mm = float(value)
            except (ValueError, TypeError):
                pass
        elif key == "Preset" and value in WINDOW_PRESETS:
            self._preset = value
            self._width_mm, self._height_mm = WINDOW_PRESETS[value]
            self._reposition()
        else:
            super().set_property(key, value)
