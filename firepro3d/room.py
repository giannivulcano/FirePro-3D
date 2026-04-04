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
    QGraphicsPolygonItem, QGraphicsTextItem, QGraphicsRectItem,
    QGraphicsItem, QStyle,
)
from PyQt6.QtGui import QPen, QColor, QBrush, QPolygonF, QFont, QPainterPath, QPainter
from PyQt6.QtCore import Qt, QPointF

from .constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER

if TYPE_CHECKING:
    from .scale_manager import ScaleManager

# ── NFPA 13 coverage limits — imported from constants.py ─────────────────
from .constants import HAZARD_CLASSES, NFPA_MAX_COVERAGE_SQFT as _NFPA_MAX_COVERAGE_SQFT


# NFPA 13 ceiling construction types — determines max spacing and
# protection area per Table 10.2.4.2.1(a)/(b).
CEILING_TYPES = [
    "Noncombustible unobstructed",
    "Noncombustible obstructed",
    "Combustible unobstructed - no exposed members",
    "Combustible unobstructed - exposed members >= 3ft (910 mm) O/C",
    "Combustible unobstructed - exposed members < 3ft (910 mm) O/C",
    "Combustible obstructed - exposed members >= 3ft (910 mm) O/C",
    "Combustible obstructed - exposed members < 3ft (910 mm) O/C",
    "Combustible concealed space per 10.2.6.1.4",
]

COMPARTMENT_TYPES = [
    "Room", "Corridor", "Stairwell", "Shaft",
    "Attic", "Concealed Space",
]

# ── Room label background with rounded corners ─────────────────────────


class _RoundedRectBgItem(QGraphicsRectItem):
    """Label background: no fill, border with filleted (rounded) corners."""

    _CORNER_RADIUS = 40.0  # scene units (mm) — adjust for visual fillet

    def paint(self, painter: QPainter, option, widget=None):
        r = self.rect()
        if r.isEmpty():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRoundedRect(r, self._CORNER_RADIUS, self._CORNER_RADIUS)


# ── Room class ──────────────────────────────────────────────────────────


from .displayable_item import DisplayableItemMixin


class Room(DisplayableItemMixin, QGraphicsPolygonItem):
    """A closed polygonal room/space region derived from wall boundaries."""

    def __init__(self, boundary: list[QPointF] | None = None,
                 color: str | QColor = "#4488cc"):
        super().__init__()
        self._boundary: list[QPointF] = list(boundary) if boundary else []
        self._color = QColor(color) if isinstance(color, str) else QColor(color)

        # Shared display-manager attributes
        self.init_displayable()

        # Identity
        self.name: str = ""
        self._tag: str = ""
        self._show_label: bool = True
        self._ceiling_level: str = "Level 2"
        self._ceiling_offset: float = 0.0   # mm offset from ceiling level

        # NFPA / fire protection
        self._hazard_class: str = "Light Hazard"
        self._compartment_type: str = "Room"
        self._ceiling_type: str = "Noncombustible unobstructed"

        # Room-specific display extras (beyond mixin)
        self._display_scale: float = 1.0
        self._display_opacity: float = 100
        self._display_visible: bool = True

        # Label in scene units (scales with zoom like pipe labels)
        self._label_bg = None  # background rect, created in _update_label
        self._label = QGraphicsTextItem(self)
        self._label.setDefaultTextColor(QColor("#000000"))
        self._label.setZValue(200)  # above everything including walls
        self._label_font_color: str = "#000000"
        self._label_font_size: float = 150.0  # mm in scene units
        self._label_offset: QPointF = QPointF(0, 0)  # user drag offset from centroid

        # Rendering
        self.setZValue(-60)  # below walls (-50), above floors (-80)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        if self._boundary:
            self._rebuild()

    # ── Z-range for view-depth filtering ────────────────────────────────

    def z_range_mm(self) -> tuple[float, float] | None:
        """Room spans from floor level to underside of ceiling slab."""
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return None
        floor_lvl = lm.get(getattr(self, "level", None))
        if floor_lvl is None:
            return None
        bot_z = floor_lvl.elevation
        ceil_lvl = lm.get(getattr(self, "_ceiling_level", None))
        if ceil_lvl is None:
            top_z = bot_z + 3048.0  # 10ft default
        else:
            # Subtract ceiling slab thickness
            slab_thickness = 0.0
            for slab in getattr(sc, "_floor_slabs", []):
                if getattr(slab, "level", None) == self._ceiling_level:
                    slab_thickness = max(slab_thickness, slab._thickness_mm)
            top_z = ceil_lvl.elevation - slab_thickness + self._ceiling_offset
        return (bot_z, top_z)

    # ── Grip protocol (drawn by Model_View like all other geometry) ────

    def grip_points(self) -> list[QPointF]:
        """Return a single grip at the label centre for dragging.

        Only shown when the label is visible — this is a label-only grip,
        not a room-polygon grip.
        """
        text = self._tag or self.name or ""
        if not self._show_label or not text:
            return []
        if self._label_bg is not None and not self._label_bg.rect().isEmpty():
            return [self._label_bg.rect().center()]
        if self._boundary:
            cx = sum(p.x() for p in self._boundary) / len(self._boundary)
            cy = sum(p.y() for p in self._boundary) / len(self._boundary)
            return [QPointF(cx, cy)]
        return []

    def apply_grip(self, index: int, pos: QPointF):
        """Move the label so its centre lands at *pos*."""
        if index != 0 or not self._boundary:
            return
        cx = sum(p.x() for p in self._boundary) / len(self._boundary)
        cy = sum(p.y() for p in self._boundary) / len(self._boundary)
        br = self._label.boundingRect()
        # pos is the desired centre of the label bg
        lx = pos.x() - br.width() / 2
        ly = pos.y() - br.height() / 2
        self._label_offset = QPointF(
            lx - (cx - br.width() / 2),
            ly - (cy - br.height() / 2),
        )
        self._label.setPos(lx, ly)
        if self._label_bg is not None:
            pad = self._label_font_size * 0.2
            self._label_bg.setRect(
                lx - pad, ly - pad,
                br.width() + 2 * pad, br.height() + 2 * pad,
            )

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
        lx = cx - br.width() / 2 + self._label_offset.x()
        ly = cy - br.height() / 2 + self._label_offset.y()
        self._label.setPos(lx, ly)

        # Background box — no fill, border with rounded corners
        pad = fs * 0.2
        if self._label_bg is None:
            self._label_bg = _RoundedRectBgItem(self)
            self._label_bg.setZValue(199)
        border_color = QColor(self._display_color or self._color.name())
        pen = QPen(border_color, 2)
        pen.setCosmetic(True)
        self._label_bg.setPen(pen)
        self._label_bg.setBrush(QBrush(Qt.BrushStyle.NoBrush))
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
        """Compute ceiling height from level elevations, accounting for
        the floor slab thickness at the ceiling level."""
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return 0.0
        floor_lvl = lm.get(self.level)
        ceil_lvl = lm.get(self._ceiling_level)
        if floor_lvl is None or ceil_lvl is None:
            return 0.0
        # Find the thickest floor slab on the ceiling level
        slab_thickness = 0.0
        for slab in getattr(sc, "_floor_slabs", []):
            if getattr(slab, "level", None) == self._ceiling_level:
                slab_thickness = max(slab_thickness, slab._thickness_mm)
        return ceil_lvl.elevation - floor_lvl.elevation - slab_thickness + self._ceiling_offset

    # ── Sprinkler detection ──────────────────────────────────────────────

    def _detect_sprinklers(self) -> list:
        """Return sprinklers assigned to this room.

        First checks for nodes explicitly tagged with this room's name
        (set by auto-populate).  Falls back to XY + Z-range detection
        for manually placed sprinklers.
        """
        sc = self.scene()
        if sc is None or not hasattr(sc, "sprinkler_system"):
            return []

        my_name = self.name
        tagged = []
        untagged_nodes = []

        for node in sc.sprinkler_system.nodes:
            if not node.has_sprinkler():
                continue
            room_tag = getattr(node, "_room_name", "")
            if room_tag and room_tag == my_name:
                tagged.append(node.sprinkler)
            elif not room_tag:
                untagged_nodes.append(node)

        # For untagged nodes, fall back to XY polygon + Z range check
        if untagged_nodes and len(self._boundary) >= 3:
            path = QPainterPath()
            path.addPolygon(QPolygonF(self._boundary))
            path.closeSubpath()

            zr = self.z_range_mm()
            if zr is not None:
                z_bot, z_top = min(zr), max(zr)
            else:
                z_bot, z_top = None, None

            for node in untagged_nodes:
                if not path.contains(node.scenePos()):
                    continue
                if z_bot is not None:
                    z = getattr(node, "z_pos", None)
                    if z is not None and (z < z_bot or z > z_top):
                        continue
                tagged.append(node.sprinkler)

        return tagged
        return result
        return result

    def _nfpa_max_coverage_sqft(self) -> float:
        """Max coverage per sprinkler (sq ft) for the current hazard class."""
        return _NFPA_MAX_COVERAGE_SQFT.get(self._hazard_class, 130.0)

    # ── Formatting helpers ───────────────────────────────────────────────

    def _fmt_area(self, mm2: float) -> str:
        """Format area in display units (sq ft or sq m)."""
        sm = self._get_scale_manager()
        if sm is None:
            return f"{mm2:.0f} mm²"
        from .scale_manager import DisplayUnit
        if sm._display_unit == DisplayUnit.IMPERIAL:
            sqft = mm2 / (304.8 ** 2)
            return f"{sqft:.1f} sq ft"
        elif sm._display_unit == DisplayUnit.METRIC_M:
            sqm = mm2 / 1_000_000.0
            return f"{sqm:.2f} m²"
        return f"{mm2:.0f} mm²"

    def _fmt_volume(self, mm3: float) -> str:
        sm = self._get_scale_manager()
        if sm is None:
            return f"{mm3:.0f} mm³"
        from .scale_manager import DisplayUnit
        if sm._display_unit == DisplayUnit.IMPERIAL:
            cuft = mm3 / (304.8 ** 3)
            return f"{cuft:.0f} cu ft"
        elif sm._display_unit == DisplayUnit.METRIC_M:
            cum = mm3 / 1e9
            return f"{cum:.1f} m³"
        return f"{mm3:.0f} mm³"

    # ── Geometry ──────────────────────────────────────────────────────────

    def boundingRect(self):
        """Include the polygon AND all child items (label, background).

        Without this override, the inherited QGraphicsPolygonItem bounding
        rect only covers the polygon.  When the label child extends beyond
        the polygon, Qt's BSP can incorrectly cull the polygon fill once
        the label scrolls off screen.
        """
        br = super().boundingRect()
        return br.united(self.childrenBoundingRect())

    def shape(self) -> QPainterPath:
        """Only the room tag label area is selectable, not the full polygon."""
        path = QPainterPath()
        if self._label_bg is not None and self._label_bg.isVisible():
            path.addRect(self._label_bg.rect())
        elif self._label.isVisible():
            path.addRect(self._label.mapRectToParent(
                self._label.boundingRect()))
        return path

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
            "Ceiling Offset":    {"type": "dimension", "value_mm": self._ceiling_offset},
            "Ceiling Height":    {"type": "label",     "value": self._fmt(ceil_h)},
            "Volume":            {"type": "label",     "value": self._fmt_volume(vol_mm3)},
            "Hazard Class":      {"type": "enum",      "value": self._hazard_class,
                                  "options": HAZARD_CLASSES},
            "Compartment Type":  {"type": "enum",      "value": self._compartment_type,
                                  "options": COMPARTMENT_TYPES},
            "Ceiling Type":      {"type": "enum",      "value": self._ceiling_type,
                                  "options": CEILING_TYPES},
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
        elif key == "Ceiling Offset":
            try:
                self._ceiling_offset = float(value)
            except (ValueError, TypeError):
                pass
        elif key == "Hazard Class":
            if str(value) in HAZARD_CLASSES:
                self._hazard_class = str(value)
        elif key == "Compartment Type":
            if str(value) in COMPARTMENT_TYPES:
                self._compartment_type = str(value)
        elif key == "Ceiling Type":
            if str(value) in CEILING_TYPES:
                self._ceiling_type = str(value)
        elif key == "Fill Color":
            self._color = QColor(value)
            self.update()

    # ── Grip points (label-only) ─────────────────────────────────────────
    # NOTE: grip_points / apply_grip defined earlier handle label dragging.
    # Room boundary vertices are NOT exposed as grips.

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
            "ceiling_offset":   self._ceiling_offset,
            "user_layer":       self.user_layer,
            "hazard_class":     self._hazard_class,
            "compartment_type": self._compartment_type,
            "ceiling_type":     self._ceiling_type,
            "label_offset":     [self._label_offset.x(), self._label_offset.y()],
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
        room._ceiling_offset = float(data.get("ceiling_offset", 0.0))
        room.user_layer = data.get("user_layer", DEFAULT_USER_LAYER)
        room._hazard_class = data.get("hazard_class", "Light Hazard")
        room._compartment_type = data.get("compartment_type", "Room")
        room._ceiling_type = data.get("ceiling_type", "Noncombustible unobstructed")
        lo = data.get("label_offset", [0, 0])
        room._label_offset = QPointF(lo[0], lo[1])
        room._rebuild()  # rebuild polygon + label now that name/tag are set
        return room
