"""
room.py
=======
Room / Space element for FirePro 3D.

A Room is a closed polygonal region derived from wall boundaries.
It tracks sprinklers inside its boundary and computes NFPA 13
coverage metrics.

Created by clicking inside a closed wall loop — the boundary is
auto-detected from connected walls on the active level.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsPolygonItem, QGraphicsTextItem, QGraphicsItem, QStyle,
)
from PyQt6.QtGui import QPen, QColor, QBrush, QPolygonF, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF

from constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER

if TYPE_CHECKING:
    from scale_manager import ScaleManager

# ── NFPA 13 coverage limits (sq ft per sprinkler) ──────────────────────

HAZARD_CLASSES = [
    "Light Hazard",
    "Ordinary Hazard Group 1",
    "Ordinary Hazard Group 2",
    "Extra Hazard Group 1",
    "Extra Hazard Group 2",
    "Miscellaneous Storage",
]

_NFPA_MAX_COVERAGE_SQFT: dict[str, float] = {
    "Light Hazard":             225.0,
    "Ordinary Hazard Group 1":  130.0,
    "Ordinary Hazard Group 2":  130.0,
    "Extra Hazard Group 1":     100.0,
    "Extra Hazard Group 2":     100.0,
    "Miscellaneous Storage":    100.0,
}

COMPARTMENT_TYPES = [
    "Room", "Corridor", "Stairwell", "Shaft",
    "Attic", "Concealed Space",
]

# ── Room class ──────────────────────────────────────────────────────────


class Room(QGraphicsPolygonItem):
    """A closed polygonal room/space region derived from wall boundaries."""

    def __init__(self, boundary: list[QPointF] | None = None,
                 color: str | QColor = "#4488cc"):
        super().__init__()
        self._boundary: list[QPointF] = list(boundary) if boundary else []
        self._color = QColor(color) if isinstance(color, str) else QColor(color)

        # Identity
        self.name: str = ""
        self._tag: str = ""
        self._show_label: bool = True
        self.level: str = DEFAULT_LEVEL
        self._ceiling_level: str = "Level 2"
        self.user_layer: str = DEFAULT_USER_LAYER

        # NFPA / fire protection
        self._hazard_class: str = "Light Hazard"
        self._compartment_type: str = "Room"
        self._construction: str = "Non-combustible"
        self._obstructed: str = "Unobstructed"

        # Display
        self._display_color: str | None = None
        self._display_fill_color: str | None = None
        self._display_overrides: dict = {}
        self._display_scale: float = 1.0
        self._display_opacity: float = 100
        self._display_visible: bool = True

        # Scale manager fallback for templates
        self._scale_manager_ref: ScaleManager | None = None

        # Label in scene units (scales with zoom like pipe labels)
        self._label_bg = None  # background rect, created in _update_label
        self._label = QGraphicsTextItem(self)
        self._label.setDefaultTextColor(QColor("#000000"))
        self._label.setZValue(200)  # above everything including walls
        self._label_font_color: str = "#000000"
        self._label_font_size: float = 150.0  # mm in scene units

        # Rendering
        self.setZValue(-60)  # below walls (-50), above floors (-80)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        if self._boundary:
            self._rebuild()

    # ── Geometry ─────────────────────────────────────────────────────────

    def _rebuild(self):
        """Rebuild polygon and label from boundary points."""
        if len(self._boundary) < 3:
            self.setPolygon(QPolygonF())
            return
        poly = QPolygonF(self._boundary)
        self.setPolygon(poly)
        self._update_label()

    def _update_label(self):
        """Position the room tag label at the polygon centroid with background."""
        from PyQt6.QtWidgets import QGraphicsRectItem

        text = self._tag or self.name or ""
        self._label.setVisible(self._show_label and bool(text))
        if self._label_bg is not None:
            self._label_bg.setVisible(self._show_label and bool(text))
        if not text or not self._boundary:
            return

        fc = self._label_font_color
        fs = self._label_font_size
        html = (f"<div style='text-align:center; font-size:{fs:.0f}px; "
                f"font-family:Segoe UI; font-weight:bold; "
                f"color:{fc};'>{text}</div>")
        self._label.setHtml(html)
        self._label.setTextWidth(-1)
        ideal = self._label.document().idealWidth()
        self._label.setTextWidth(ideal)

        cx = sum(p.x() for p in self._boundary) / len(self._boundary)
        cy = sum(p.y() for p in self._boundary) / len(self._boundary)
        br = self._label.boundingRect()
        lx = cx - br.width() / 2
        ly = cy - br.height() / 2
        self._label.setPos(lx, ly)

        # Background box
        pad = fs * 0.2
        if self._label_bg is None:
            self._label_bg = QGraphicsRectItem(self)
            self._label_bg.setZValue(199)
            self._label_bg.setPen(QPen(Qt.PenStyle.NoPen))
        bg_color = QColor("#ffffff")
        bg_color.setAlpha(200)
        self._label_bg.setBrush(QBrush(bg_color))
        self._label_bg.setRect(
            lx - pad, ly - pad,
            br.width() + 2 * pad, br.height() + 2 * pad
        )

    @property
    def boundary(self) -> list[QPointF]:
        return list(self._boundary)

    # ── Area / perimeter calculations ────────────────────────────────────

    def _compute_area_mm2(self) -> float:
        """Polygon area via shoelace formula (scene units = mm²)."""
        pts = self._boundary
        n = len(pts)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += pts[i].x() * pts[j].y()
            area -= pts[j].x() * pts[i].y()
        return abs(area) / 2.0

    def _compute_perimeter_mm(self) -> float:
        """Sum of edge lengths (scene units = mm)."""
        pts = self._boundary
        n = len(pts)
        if n < 2:
            return 0.0
        total = 0.0
        for i in range(n):
            j = (i + 1) % n
            dx = pts[j].x() - pts[i].x()
            dy = pts[j].y() - pts[i].y()
            total += math.hypot(dx, dy)
        return total

    def _ceiling_height_mm(self) -> float:
        """Compute ceiling height from level elevations."""
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return 0.0
        floor_lvl = lm.get(self.level)
        ceil_lvl = lm.get(self._ceiling_level)
        if floor_lvl is None or ceil_lvl is None:
            return 0.0
        return ceil_lvl.elevation - floor_lvl.elevation

    # ── Sprinkler detection ──────────────────────────────────────────────

    def _detect_sprinklers(self) -> list:
        """Return sprinklers whose nodes are inside the boundary polygon."""
        sc = self.scene()
        if sc is None or not hasattr(sc, "sprinkler_system"):
            return []
        if len(self._boundary) < 3:
            return []

        path = QPainterPath()
        path.addPolygon(QPolygonF(self._boundary))
        path.closeSubpath()

        result = []
        for node in sc.sprinkler_system.nodes:
            if not node.has_sprinkler():
                continue
            if node.level != self.level:
                continue
            if path.contains(node.scenePos()):
                result.append(node.sprinkler)
        return result

    def _nfpa_max_coverage_sqft(self) -> float:
        """Max coverage per sprinkler (sq ft) for the current hazard class."""
        return _NFPA_MAX_COVERAGE_SQFT.get(self._hazard_class, 130.0)

    # ── Formatting helpers ───────────────────────────────────────────────

    def _get_sm(self):
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
        if sm is None:
            sm = self._scale_manager_ref
        return sm

    def _fmt(self, mm: float) -> str:
        sm = self._get_sm()
        return sm.format_length(mm) if sm else f"{mm:.1f} mm"

    def _fmt_area(self, mm2: float) -> str:
        """Format area in display units (sq ft or sq m)."""
        sm = self._get_sm()
        if sm is None:
            return f"{mm2:.0f} mm²"
        from scale_manager import DisplayUnit
        if sm._display_unit == DisplayUnit.IMPERIAL:
            sqft = mm2 / (304.8 ** 2)
            return f"{sqft:.1f} sq ft"
        elif sm._display_unit == DisplayUnit.METRIC_M:
            sqm = mm2 / 1_000_000.0
            return f"{sqm:.2f} m²"
        return f"{mm2:.0f} mm²"

    def _fmt_volume(self, mm3: float) -> str:
        sm = self._get_sm()
        if sm is None:
            return f"{mm3:.0f} mm³"
        from scale_manager import DisplayUnit
        if sm._display_unit == DisplayUnit.IMPERIAL:
            cuft = mm3 / (304.8 ** 3)
            return f"{cuft:.0f} cu ft"
        elif sm._display_unit == DisplayUnit.METRIC_M:
            cum = mm3 / 1e9
            return f"{cum:.1f} m³"
        return f"{mm3:.0f} mm³"

    # ── Paint ────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected

        fill_col = QColor(self._display_fill_color or self._color.name())
        fill_col.setAlpha(50)
        line_col = QColor(self._display_color or self._color.name())

        pen = QPen(line_col, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill_col))
        painter.drawPolygon(self.polygon())

        # Selection highlight
        if self.isSelected():
            sel_pen = QPen(QColor("red"), 2)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(self.polygon())

    # ── Properties API ───────────────────────────────────────────────────

    def get_properties(self) -> dict:
        area_mm2 = self._compute_area_mm2()
        perim_mm = self._compute_perimeter_mm()
        ceil_h = self._ceiling_height_mm()
        vol_mm3 = area_mm2 * ceil_h if ceil_h > 0 else 0.0

        sprinklers = self._detect_sprinklers()
        spr_count = len(sprinklers)

        # Coverage per sprinkler in sq ft
        area_sqft = area_mm2 / (304.8 ** 2)
        cov_per_spr = area_sqft / spr_count if spr_count > 0 else 0.0
        max_cov = self._nfpa_max_coverage_sqft()
        status = "Pass" if (spr_count > 0 and cov_per_spr <= max_cov) else "Fail"

        return {
            "Type":              {"type": "label",     "value": "Room"},
            "Room Name":         {"type": "string",    "value": self.name},
            "Room Tag":          {"type": "string",    "value": self._tag},
            "Show Label":        {"type": "enum",      "value": "True" if self._show_label else "False",
                                  "options": ["True", "False"]},
            "Area":              {"type": "label",     "value": self._fmt_area(area_mm2)},
            "Perimeter":         {"type": "label",     "value": self._fmt(perim_mm)},
            "Floor Level":       {"type": "level_ref", "value": self.level},
            "Ceiling Level":     {"type": "level_ref", "value": self._ceiling_level},
            "Ceiling Height":    {"type": "label",     "value": self._fmt(ceil_h)},
            "Volume":            {"type": "label",     "value": self._fmt_volume(vol_mm3)},
            "Hazard Class":      {"type": "enum",      "value": self._hazard_class,
                                  "options": HAZARD_CLASSES},
            "Compartment Type":  {"type": "enum",      "value": self._compartment_type,
                                  "options": COMPARTMENT_TYPES},
            "Construction":      {"type": "enum",      "value": self._construction,
                                  "options": ["Combustible", "Non-combustible"]},
            "Obstructed":        {"type": "enum",      "value": self._obstructed,
                                  "options": ["Obstructed", "Unobstructed"]},
            "Sprinkler Count":   {"type": "label",     "value": str(spr_count)},
            "Coverage/Sprinkler": {"type": "label",    "value": f"{cov_per_spr:.1f} sq ft"},
            "Max Coverage":      {"type": "label",     "value": f"{max_cov:.0f} sq ft"},
            "Coverage Status":   {"type": "label",     "value": status},
            "Fill Color":        {"type": "color",     "value": self._color.name()},
        }

    def set_property(self, key: str, value):
        if key == "Room Name":
            self.name = str(value)
            self._update_label()
        elif key == "Room Tag":
            self._tag = str(value)
            self._update_label()
        elif key == "Show Label":
            self._show_label = (str(value) == "True")
            self._update_label()
        elif key == "Floor Level":
            self.level = str(value)
        elif key == "Ceiling Level":
            self._ceiling_level = str(value)
        elif key == "Hazard Class":
            if str(value) in HAZARD_CLASSES:
                self._hazard_class = str(value)
        elif key == "Compartment Type":
            if str(value) in COMPARTMENT_TYPES:
                self._compartment_type = str(value)
        elif key == "Construction":
            self._construction = str(value)
        elif key == "Obstructed":
            self._obstructed = str(value)
        elif key == "Fill Color":
            self._color = QColor(value)
            self.update()

    # ── Grip points ──────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        return [QPointF(p) for p in self._boundary]

    def apply_grip(self, index: int, new_pos: QPointF):
        if 0 <= index < len(self._boundary):
            self._boundary[index] = QPointF(new_pos)
            self._rebuild()

    def translate(self, dx: float, dy: float):
        self._boundary = [QPointF(p.x() + dx, p.y() + dy) for p in self._boundary]
        self._rebuild()

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":             "room",
            "boundary":         [[p.x(), p.y()] for p in self._boundary],
            "color":            self._color.name(),
            "name":             self.name,
            "tag":              self._tag,
            "show_label":       self._show_label,
            "level":            self.level,
            "ceiling_level":    self._ceiling_level,
            "user_layer":       self.user_layer,
            "hazard_class":     self._hazard_class,
            "compartment_type": self._compartment_type,
            "construction":     self._construction,
            "obstructed":       self._obstructed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Room":
        pts = [QPointF(p[0], p[1]) for p in data.get("boundary", [])]
        room = cls(boundary=pts, color=data.get("color", "#4488cc"))
        room.name = data.get("name", "")
        room._tag = data.get("tag", "")
        room._show_label = data.get("show_label", True)
        room.level = data.get("level", DEFAULT_LEVEL)
        room._ceiling_level = data.get("ceiling_level", "Level 2")
        room.user_layer = data.get("user_layer", DEFAULT_USER_LAYER)
        room._hazard_class = data.get("hazard_class", "Light Hazard")
        room._compartment_type = data.get("compartment_type", "Room")
        room._construction = data.get("construction", "Non-combustible")
        room._obstructed = data.get("obstructed", "Unobstructed")
        return room
