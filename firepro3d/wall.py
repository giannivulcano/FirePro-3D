"""
wall.py
=======
WallSegment entity for FirePro 3D.

Drawn as a double-line (centerline +/- half thickness) in 2D plan view.
Extruded to a 3D mesh between base_level and top_level (or base + height).
Supports thickness presets, colour, fill mode, and wall openings.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsPathItem, QStyle, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPen, QColor, QPainterPath, QBrush, QPainterPathStroker, QPolygonF,
)

if TYPE_CHECKING:
    from .wall_opening import WallOpening

from .constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER

# ── Constants ────────────────────────────────────────────────────────────────

THICKNESS_PRESETS_IN = [4, 6, 8, 12]           # inches (used by dialog combo)
DEFAULT_THICKNESS_IN = 6                        # inches (used by dialog combo)
DEFAULT_THICKNESS_MM = DEFAULT_THICKNESS_IN * 25.4  # 152.4 mm

# Fill modes
FILL_NONE  = "None"
FILL_SOLID = "Solid"
FILL_HATCH = "Hatch"      # legacy alias
FILL_SECTION = "Section"

# Alignment modes (Revit-style wall placement line)
ALIGN_CENTER   = "Center"
ALIGN_INTERIOR = "Interior"
ALIGN_EXTERIOR = "Exterior"

_HATCH_SPACING = 6.0      # cosmetic pixel spacing for 2D hatch lines
_SELECTION_COLOR = QColor("red")


def _scene_hit_width(item) -> float:
    sc = item.scene()
    if sc:
        views = sc.views()
        if views:
            scale = views[0].transform().m11()
            return max(4.0, 14.0 / max(scale, 1e-6))
    return 8.0


def compute_wall_quad(
    pt1: QPointF, pt2: QPointF,
    thickness_mm: float,
    alignment: str,
    scale_manager=None,
) -> tuple[QPointF, QPointF, QPointF, QPointF]:
    """Compute the 4 corner points of a wall rectangle without a QGraphicsItem.

    Returns (p1_left, p1_right, p2_right, p2_left) — same order as
    ``WallSegment.quad_points()``.
    """
    dx = pt2.x() - pt1.x()
    dy = pt2.y() - pt1.y()
    angle = math.atan2(dy, dx)
    nx, ny = -math.sin(angle), math.cos(angle)

    # Half-thickness in scene units
    half_mm = thickness_mm / 2.0
    if (scale_manager is not None
            and scale_manager.drawing_scale > 0):
        paper_mm = half_mm / scale_manager.drawing_scale
        ht = scale_manager.paper_to_scene(paper_mm)
    else:
        ht = half_mm  # fallback: 1 px ≈ 1 mm

    if alignment == ALIGN_INTERIOR:
        # Interior: axis is on interior face — wall extends outward (right side)
        off_left = QPointF(nx * ht * 2, ny * ht * 2)
        off_right = QPointF(0, 0)
    elif alignment == ALIGN_EXTERIOR:
        # Exterior: axis is on exterior face — wall extends inward (left side)
        off_left = QPointF(0, 0)
        off_right = QPointF(-nx * ht * 2, -ny * ht * 2)
    else:  # Center
        off_left = QPointF(nx * ht, ny * ht)
        off_right = QPointF(-nx * ht, -ny * ht)
    return (
        pt1 + off_left,
        pt1 + off_right,
        pt2 + off_right,
        pt2 + off_left,
    )


# ── WallSegment ──────────────────────────────────────────────────────────────

from .displayable_item import DisplayableItemMixin


class WallSegment(DisplayableItemMixin, QGraphicsPathItem):
    """A straight wall segment defined by two centerline endpoints.

    2D rendering: two parallel lines at +/- thickness/2 from the centerline,
    with optional solid fill or diagonal hatch between them.

    Properties exposed via ``get_properties()`` / ``set_property()``:
        Thickness, Colour, Fill Mode, Base Level, Top Level, Height
    """

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 thickness_mm: float = DEFAULT_THICKNESS_MM,
                 color: str | QColor = "#cccccc"):
        super().__init__()
        self._pt1 = QPointF(pt1)
        self._pt2 = QPointF(pt2)
        self._thickness_mm: float = float(thickness_mm)
        self._color = QColor(color) if isinstance(color, str) else QColor(color)
        self._fill_mode: str = FILL_NONE

        # Shared display-manager attributes
        self.init_displayable()

        # Level / height (all in mm)
        self._base_level: str = DEFAULT_LEVEL
        self._top_level: str = "Level 2"
        self._height_mm: float = 3048.0            # 10 ft fallback
        self._base_offset_mm: float = 0.0          # offset from base level elevation
        self._top_offset_mm: float = 0.0           # offset from top level elevation

        # Alignment mode (centerline / interior / exterior)
        self._alignment: str = ALIGN_CENTER

        # Per-endpoint join mode
        # Auto: solid at 2-wall corners, butt at T/cross intersections
        # Solid: miter without visible miter line (continuous fill)
        # Butt: no miter extension
        # Miter: classic miter with visible joint line
        self._join_mode_pt1: str = "Auto"
        self._join_mode_pt2: str = "Auto"
        self._solid_pt1: bool = False   # set by mitered_quad()
        self._solid_pt2: bool = False

        # Wall openings (doors / windows)
        self.openings: list[WallOpening] = []

        self.name: str = ""

        self.setZValue(-50)                         # behind pipes, above underlays
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        self._rebuild_path()

    # ── Geometry helpers ─────────────────────────────────────────────────────

    @property
    def pt1(self) -> QPointF:
        return self._pt1

    @property
    def pt2(self) -> QPointF:
        return self._pt2

    @property
    def thickness_in(self) -> float:
        """Backward compat — returns thickness in inches."""
        return self._thickness_mm / 25.4

    @property
    def thickness_mm(self) -> float:
        return self._thickness_mm

    def centerline_length(self) -> float:
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        return math.hypot(dx, dy)

    def centerline_angle_rad(self) -> float:
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        return math.atan2(dy, dx)

    def normal(self) -> tuple[float, float]:
        """Unit normal perpendicular to centerline (rotated +90 deg)."""
        a = self.centerline_angle_rad()
        return (-math.sin(a), math.cos(a))

    def half_thickness_scene(self) -> float:
        """Half-thickness converted from mm to scene units.

        Uses the scene's ScaleManager (which always has valid defaults
        even before calibration: 1 px/mm, 1:100 scale).
        """
        half_mm = self._thickness_mm / 2.0
        sc = self.scene()
        if sc and hasattr(sc, "scale_manager"):
            sm = sc.scale_manager
            if sm.drawing_scale > 0:
                paper_mm = half_mm / sm.drawing_scale
                return sm.paper_to_scene(paper_mm)
        # Fallback when not attached to a scene
        return half_mm

    def quad_points(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
        """Return the four corner points of the wall rectangle (2D).

        Order: p1_left, p1_right, p2_right, p2_left  (CCW winding).

        Alignment controls how the wall rectangle relates to the click line
        (defined by _pt1 / _pt2):
          Center   — click line is the wall centerline (default)
          Interior — click line is the left (normal-side) face
          Exterior — click line is the right face
        """
        nx, ny = self.normal()
        ht = self.half_thickness_scene()
        if self._alignment == ALIGN_INTERIOR:
            # Interior: axis is on interior face — wall extends outward (right side)
            off_left = QPointF(nx * ht * 2, ny * ht * 2)
            off_right = QPointF(0, 0)
        elif self._alignment == ALIGN_EXTERIOR:
            # Exterior: axis is on exterior face — wall extends inward (left side)
            off_left = QPointF(0, 0)
            off_right = QPointF(-nx * ht * 2, -ny * ht * 2)
        else:  # ALIGN_CENTER
            off_left = QPointF(nx * ht, ny * ht)
            off_right = QPointF(-nx * ht, -ny * ht)
        return (
            self._pt1 + off_left,    # p1 left
            self._pt1 + off_right,   # p1 right
            self._pt2 + off_right,   # p2 right
            self._pt2 + off_left,    # p2 left
        )

    # ── Path rebuild (2D) ────────────────────────────────────────────────────

    def _rebuild_path(self):
        """Reconstruct the QPainterPath from current geometry (mitered)."""
        p1l, p1r, p2r, p2l = self.mitered_quad()

        path = QPainterPath()
        # Outer rectangle (possibly mitered)
        path.moveTo(p1l)
        path.lineTo(p2l)
        path.lineTo(p2r)
        path.lineTo(p1r)
        path.closeSubpath()
        self.setPath(path)

    # ── Paint ────────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected

        p1l, p1r, p2r, p2l = self.mitered_quad()
        line_col = QColor(self._display_color) if self._display_color else self._color
        pen = QPen(line_col, 1)
        pen.setCosmetic(True)

        # Fill (always fill the full quad area)
        fill_brush = Qt.BrushStyle.NoBrush
        if self._fill_mode == FILL_SOLID:
            if self._display_fill_color:
                fill_color = QColor(self._display_fill_color)
                fill_color.setAlpha(80)
            else:
                fill_color = QColor(self._color)
                fill_color.setAlpha(80)
            fill_brush = QBrush(fill_color)

        solid_pt1 = getattr(self, "_solid_pt1", False)
        solid_pt2 = getattr(self, "_solid_pt2", False)

        if not solid_pt1 and not solid_pt2:
            # No solid joins — draw full polygon as before
            painter.setPen(pen)
            painter.setBrush(fill_brush)
            poly = QPolygonF([p1l, p2l, p2r, p1r])
            painter.drawPolygon(poly)
        else:
            # Fill the quad without outline, then draw only non-solid edges
            if fill_brush != Qt.BrushStyle.NoBrush:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill_brush)
                painter.drawPolygon(QPolygonF([p1l, p2l, p2r, p1r]))

            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Left side edge (always drawn)
            painter.drawLine(p1l, p2l)
            # Right side edge (always drawn)
            painter.drawLine(p1r, p2r)
            # End edges: only draw if NOT solid at that endpoint
            if not solid_pt1:
                painter.drawLine(p1l, p1r)
            if not solid_pt2:
                painter.drawLine(p2l, p2r)

        # Section hatching — shown when fill mode is Section/Hatch, OR when
        # the view-range cut plane intersects this wall.
        _show_section = (self._fill_mode in (FILL_HATCH, FILL_SECTION)
                         or getattr(self, "_is_section_cut", False))
        if _show_section:
            from .displayable_item import draw_section_hatch
            clip = QPainterPath()
            clip.addPolygon(QPolygonF([p1l, p2l, p2r, p1r]))
            clip.closeSubpath()
            # Section fill colour replaces element fill; hatch lines
            # use the element's normal line colour and weight.
            sec_fill_hex = getattr(self, "_display_section_color", None) or ""
            sec_fill = QColor(sec_fill_hex) if sec_fill_hex.startswith("#") else None
            pattern = getattr(self, "_display_section_pattern", None) or "diagonal"
            h_scale = getattr(self, "_display_section_scale", 1.0) or 1.0
            draw_section_hatch(painter, clip, self.scene(),
                               color=line_col,
                               pattern=pattern,
                               line_width=pen.widthF() or 1.0,
                               section_fill=sec_fill,
                               hatch_scale=h_scale)

        # Selection highlight
        if self.isSelected():
            sel_pen = QPen(_SELECTION_COLOR, 2)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if not solid_pt1 and not solid_pt2:
                painter.drawPolygon(QPolygonF([p1l, p2l, p2r, p1r]))
            else:
                painter.drawLine(p1l, p2l)
                painter.drawLine(p1r, p2r)
                if not solid_pt1:
                    painter.drawLine(p1l, p1r)
                if not solid_pt2:
                    painter.drawLine(p2l, p2r)

    def _draw_hatch(self, painter, p1l, p1r, p2r, p2l):
        """Draw diagonal hatch lines inside the wall quad."""
        hatch_col = QColor(self._display_fill_color) if self._display_fill_color else self._color
        pen = QPen(hatch_col, 0.5)
        pen.setCosmetic(True)
        painter.setPen(pen)

        # Use bounding rect for hatch coverage
        xs = [p.x() for p in (p1l, p1r, p2r, p2l)]
        ys = [p.y() for p in (p1l, p1r, p2r, p2l)]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        # Hatch spacing in scene units — scale with zoom
        sc = self.scene()
        views = sc.views() if sc else []
        scale = abs(views[0].transform().m11()) if views else 1.0
        spacing = _HATCH_SPACING / max(scale, 1e-6)

        # Build clip polygon
        clip = QPainterPath()
        clip.addPolygon(QPolygonF([p1l, p2l, p2r, p1r]))
        clip.closeSubpath()

        # Draw 45-degree lines
        diag = math.hypot(x_max - x_min, y_max - y_min)
        n_lines = int(diag * 2 / spacing) + 1
        start = x_min + y_min - diag
        for i in range(n_lines):
            c = start + i * spacing
            # Line: x + y = c  → y = c - x
            lp1 = QPointF(x_min, c - x_min)
            lp2 = QPointF(x_max, c - x_max)
            line_path = QPainterPath()
            line_path.moveTo(lp1)
            line_path.lineTo(lp2)
            clipped = clip.intersected(line_path)
            painter.drawPath(clipped)

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        path = self.path()
        stroker = QPainterPathStroker()
        stroker.setWidth(max(_scene_hit_width(self), self.half_thickness_scene() * 2))
        return stroker.createStroke(path)

    # ── Grip points for interactive editing ───────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        mid = QPointF(
            (self._pt1.x() + self._pt2.x()) / 2,
            (self._pt1.y() + self._pt2.y()) / 2,
        )
        return [QPointF(self._pt1), QPointF(self._pt2), mid]

    def apply_grip(self, index: int, new_pos: QPointF):
        if index == 0:
            self._pt1 = QPointF(new_pos)
        elif index == 1:
            self._pt2 = QPointF(new_pos)
        elif index == 2:
            # Move whole wall
            old_mid = QPointF(
                (self._pt1.x() + self._pt2.x()) / 2,
                (self._pt1.y() + self._pt2.y()) / 2,
            )
            dx = new_pos.x() - old_mid.x()
            dy = new_pos.y() - old_mid.y()
            self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
            self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        self._rebuild_path()

    def translate(self, dx: float, dy: float):
        self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
        self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        self._rebuild_path()

    # ── Properties API ───────────────────────────────────────────────────────

    def z_range_mm(self) -> tuple[float, float] | None:
        """Return (z_bottom, z_top) of this wall in absolute mm."""
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return None
        base_lvl = lm.get(self._base_level)
        top_lvl = lm.get(self._top_level)
        z_bot = (base_lvl.elevation if base_lvl else 0.0) + self._base_offset_mm
        z_top = (top_lvl.elevation if top_lvl else 0.0) + self._top_offset_mm
        return (z_bot, z_top)

    def _computed_height_mm(self) -> float:
        """Auto-calculate wall height in mm from level elevations and offsets."""
        zr = self.z_range_mm()
        if zr is not None:
            return zr[1] - zr[0]
        return self._height_mm  # fallback

    def get_properties(self) -> dict:
        height_mm = self._computed_height_mm()
        return {
            "Type":         {"type": "label",     "value": "Wall"},
            "Name":         {"type": "string",    "value": self.name},
            "Colour":       {"type": "color",     "value": self._color.name()},
            "Thickness":    {"type": "dimension", "value": self._fmt(self._thickness_mm),
                             "value_mm": self._thickness_mm},
            "Fill Mode":    {"type": "enum",      "value": self._fill_mode,
                             "options": ["None", "Solid", "Section"]},
            "Alignment":    {"type": "enum",      "value": self._alignment,
                             "options": ["Center", "Interior", "Exterior"]},
            "Base Level":   {"type": "level_ref", "value": self._base_level},
            "Base Offset":  {"type": "dimension", "value": self._fmt(self._base_offset_mm),
                             "value_mm": self._base_offset_mm},
            "Top Level":    {"type": "level_ref", "value": self._top_level},
            "Top Offset":   {"type": "dimension", "value": self._fmt(self._top_offset_mm),
                             "value_mm": self._top_offset_mm},
            "Height":       {"type": "label",     "value": self._fmt(height_mm)},
            "Join Start":   {"type": "enum",      "value": self._join_mode_pt1,
                             "options": ["Auto", "Butt", "Miter", "Solid"]},
            "Join End":     {"type": "enum",      "value": self._join_mode_pt2,
                             "options": ["Auto", "Butt", "Miter", "Solid"]},
        }

    def _open_edit_dialog(self):
        """Open the WallDialog to edit this wall's properties in-place."""
        from .wall_dialog import WallDialog
        sc = self.scene()
        if sc is None:
            return

        lm = getattr(sc, "_level_manager", None)

        parent = sc.views()[0] if sc.views() else None
        sm = getattr(sc, "scale_manager", None)
        dlg = WallDialog(
            parent,
            defaults={
                "name":           self.name,
                "thickness_mm":   self._thickness_mm,
                "color":          self._color.name(),
                "fill_mode":      self._fill_mode,
                "alignment":      self._alignment,
                "base_level":     self._base_level,
                "base_offset_mm": self._base_offset_mm,
                "top_level":      self._top_level,
                "top_offset_mm":  self._top_offset_mm,
            },
            level_manager=lm,
            scale_manager=sm,
        )
        from PyQt6.QtWidgets import QDialog
        if dlg.exec() == QDialog.DialogCode.Accepted:
            p = dlg.get_params()
            self.name            = p["name"] or self.name
            self._thickness_mm   = p["thickness_mm"]
            self._color          = QColor(p["color"])
            self._fill_mode      = p["fill_mode"]
            self._alignment      = p["alignment"]
            self._base_level     = p["base_level"]
            self._base_offset_mm = p["base_offset_mm"]
            self._top_level      = p["top_level"]
            self._top_offset_mm  = p["top_offset_mm"]
            self._height_mm      = p["height_mm"]
            self.level           = p["base_level"]
            self._rebuild_path()
            self.update()
            if sc and hasattr(sc, "sceneModified"):
                sc.sceneModified.emit()
            if sc and hasattr(sc, "push_undo_state"):
                sc.push_undo_state()

    def _parse_dim(self, value) -> float | None:
        """Parse a dimension value (display-formatted or raw) to mm.

        If *value* is already a numeric type (float/int), it is treated as
        mm and returned directly.  String values are parsed through the
        ScaleManager (supports feet-inches, mm, m, etc.).
        """
        if isinstance(value, (int, float)):
            return float(value)
        from .scale_manager import ScaleManager
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else self._scale_manager_ref
        if sm:
            parsed = ScaleManager.parse_dimension(str(value), sm.bare_number_unit())
            if parsed is not None:
                return parsed
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def set_property(self, key: str, value):
        if key == "Name":
            self.name = str(value)
        elif key == "Colour":
            self._color = QColor(value)
            self.update()
        elif key == "Thickness":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._thickness_mm = parsed
                self._rebuild_path()
                self.update()
        elif key == "Fill Mode":
            self._fill_mode = str(value)
            self.update()
        elif key == "Alignment":
            self._alignment = str(value)
            self._rebuild_path()
            self.update()
        elif key == "Base Level":
            self._base_level = str(value)
            self.level = str(value)
            self._height_mm = self._computed_height_mm()
            self._rebuild_path()
            self.update()
        elif key == "Base Offset":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._base_offset_mm = parsed
                self._height_mm = self._computed_height_mm()
                self._rebuild_path()
                self.update()
        elif key == "Top Level":
            self._top_level = str(value)
            self._height_mm = self._computed_height_mm()
            self._rebuild_path()
            self.update()
        elif key == "Top Offset":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._top_offset_mm = parsed
                self._height_mm = self._computed_height_mm()
                self._rebuild_path()
                self.update()
        elif key in ("Join Start", "Join End"):
            if str(value) in ("Auto", "Butt", "Miter", "Solid"):
                if key == "Join Start":
                    self._join_mode_pt1 = str(value)
                else:
                    self._join_mode_pt2 = str(value)
                self._rebuild_path()
                self.update()
                # Rebuild connected walls so they reflect the change
                sc = self.scene()
                if sc and hasattr(sc, "_walls"):
                    for w in sc._walls:
                        if w is not self:
                            w._rebuild_path()
                            w.update()

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        openings_data = []
        for op in self.openings:
            openings_data.append(op.to_dict())
        return {
            "type":          "wall",
            "pt1":           [self._pt1.x(), self._pt1.y()],
            "pt2":           [self._pt2.x(), self._pt2.y()],
            "thickness_mm":  self._thickness_mm,
            "color":         self._color.name(),
            "fill_mode":     self._fill_mode,
            "alignment":     self._alignment,
            "base_level":    self._base_level,
            "top_level":     self._top_level,
            "height_mm":     self._height_mm,
            "base_offset_mm": self._base_offset_mm,
            "top_offset_mm":  self._top_offset_mm,
            "level":         self.level,
            "user_layer":    self.user_layer,
            "name":          self.name,
            "join_mode_pt1": self._join_mode_pt1,
            "join_mode_pt2": self._join_mode_pt2,
            "openings":      openings_data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WallSegment":
        FT = 304.8
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        # Accept new mm key; fall back to old in key with conversion
        if "thickness_mm" in data:
            thick_mm = data["thickness_mm"]
        elif "thickness_in" in data:
            thick_mm = data["thickness_in"] * 25.4
        else:
            thick_mm = DEFAULT_THICKNESS_MM
        wall = cls(pt1, pt2, thickness_mm=thick_mm,
                   color=data.get("color", "#cccccc"))
        wall._fill_mode = data.get("fill_mode", FILL_NONE)
        wall._alignment = data.get("alignment", ALIGN_CENTER)
        wall._base_level = data.get("base_level", DEFAULT_LEVEL)
        wall._top_level = data.get("top_level", "Level 2")
        if "height_mm" in data:
            wall._height_mm = data["height_mm"]
        elif "height_ft" in data:
            wall._height_mm = data["height_ft"] * FT
        else:
            wall._height_mm = 3048.0
        if "base_offset_mm" in data:
            wall._base_offset_mm = data["base_offset_mm"]
        elif "base_offset_ft" in data:
            wall._base_offset_mm = data["base_offset_ft"] * FT
        else:
            wall._base_offset_mm = 0.0
        if "top_offset_mm" in data:
            wall._top_offset_mm = data["top_offset_mm"]
        elif "top_offset_ft" in data:
            wall._top_offset_mm = data["top_offset_ft"] * FT
        else:
            wall._top_offset_mm = 0.0
        wall.level = data.get("level", DEFAULT_LEVEL)
        wall.user_layer = data.get("user_layer", DEFAULT_USER_LAYER)
        wall.name = data.get("name", "")
        # Per-endpoint join modes (backward compat: old "join_mode" applies to both)
        legacy = data.get("join_mode", "Auto")
        wall._join_mode_pt1 = data.get("join_mode_pt1", legacy)
        wall._join_mode_pt2 = data.get("join_mode_pt2", legacy)
        # Openings restored by caller after wall_opening module is available
        return wall

    # ── 3D mesh generation ───────────────────────────────────────────────────

    def get_3d_mesh(self, level_manager=None) -> dict | None:
        """Return vertices and faces for the extruded wall box.

        Returns dict with 'vertices' (Nx3 float list) and 'faces' (Mx3 int list),
        or None if geometry is degenerate.

        The wall is extruded from base_z to top_z (in mm, for vispy).
        Openings are subtracted as rectangular holes.
        """
        # Determine base and top elevations in mm
        base_z = 0.0
        top_z = self._height_mm
        if level_manager is not None:
            base_lvl = level_manager.get(self._base_level)
            if base_lvl:
                base_z = base_lvl.elevation + self._base_offset_mm
            top_lvl = level_manager.get(self._top_level)
            if top_lvl:
                top_z = top_lvl.elevation + self._top_offset_mm
            else:
                top_z = base_z + self._height_mm
        if abs(top_z - base_z) < 1.0:
            return None

        # 2D quad corners (scene coords → mm via scale manager), mitered
        p1l, p1r, p2r, p2l = self.mitered_quad()
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None

        def to_mm(pt: QPointF) -> tuple[float, float]:
            if sm and sm.is_calibrated and sm.drawing_scale > 0:
                x_mm = sm.scene_to_real(pt.x())
                y_mm = sm.scene_to_real(pt.y())
            else:
                x_mm = pt.x()
                y_mm = pt.y()
            return (x_mm, -y_mm)   # negate Y for 3D convention

        corners_2d = [to_mm(p) for p in (p1l, p1r, p2r, p2l)]

        color = (self._color.redF(), self._color.greenF(),
                 self._color.blueF(), 0.9)

        if not self.openings:
            # Simple box: 8 vertices, 12 triangles (6 faces × 2 tris)
            verts = []
            for x, y in corners_2d:
                verts.append([x, y, base_z])
            for x, y in corners_2d:
                verts.append([x, y, top_z])
            faces = [
                [0, 1, 2], [0, 2, 3],       # bottom
                [4, 6, 5], [4, 7, 6],       # top
                [0, 1, 5], [0, 5, 4],       # side 1
                [1, 2, 6], [1, 6, 5],       # side 2
                [2, 3, 7], [2, 7, 6],       # side 3
                [3, 0, 4], [3, 4, 7],       # side 4
            ]
            return {"vertices": verts, "faces": faces, "color": color}

        # ── Wall with openings ────────────────────────────────────────────
        # Front face: corners_2d[0]→corners_2d[1] (p1l→p1r)
        # Back  face: corners_2d[3]→corners_2d[2] (p2l→p2r)
        # Wall axis runs from pt1 to pt2 (along the "left" and "right" edges).
        # "side 1" (idx 0→1) is at pt1-end, "side 3" (idx 2→3) is at pt2-end.
        # The two long faces are "side 2" (idx 1→2, right) and "side 4" (idx 3→0, left).

        # Wall length in scene units (used to normalise offset_along → 0..1)
        import math as _m
        wall_len = _m.hypot(self._pt2.x() - self._pt1.x(),
                            self._pt2.y() - self._pt1.y())
        if wall_len < 1e-6:
            wall_len = 1.0

        # Collect normalised opening intervals along wall axis
        openings_sorted = []
        for op in self.openings:
            # offset_along is scene-units from pt1 centre;  width is in mm.
            # Convert width to scene units for fractional position.
            if sm and sm.is_calibrated:
                w_scene = op._width_mm / (sm._pixels_per_mm * sm._drawing_scale) if sm._pixels_per_mm else op._width_mm
            else:
                w_scene = op._width_mm   # assume 1 px = 1 mm
            t_center = op._offset_along / wall_len
            t_half = (w_scene / 2.0) / wall_len
            t0 = max(0.0, t_center - t_half)
            t1 = min(1.0, t_center + t_half)
            if t1 <= t0:
                continue
            ob = base_z + op._sill_mm
            ot = ob + op._height_mm
            ob = max(ob, base_z)
            ot = min(ot, top_z)
            if ot <= ob:
                continue
            openings_sorted.append((t0, t1, ob, ot))
        openings_sorted.sort(key=lambda x: x[0])

        if not openings_sorted:
            # All openings were degenerate — fall back to solid box
            verts = []
            for x, y in corners_2d:
                verts.append([x, y, base_z])
            for x, y in corners_2d:
                verts.append([x, y, top_z])
            faces = [
                [0, 1, 2], [0, 2, 3],
                [4, 6, 5], [4, 7, 6],
                [0, 1, 5], [0, 5, 4],
                [1, 2, 6], [1, 6, 5],
                [2, 3, 7], [2, 7, 6],
                [3, 0, 4], [3, 4, 7],
            ]
            return {"vertices": verts, "faces": faces, "color": color}

        # Helper: interpolate between two 2D corners at parameter t
        def lerp_2d(a, b, t):
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

        # Left edge: corners_2d[0]→corners_2d[3]  (p1l → p2l)
        # Right edge: corners_2d[1]→corners_2d[2] (p1r → p2r)
        c0, c1, c2, c3 = corners_2d  # p1l, p1r, p2r, p2l

        verts = []
        faces = []

        def V(x, y, z):
            idx = len(verts)
            verts.append([x, y, z])
            return idx

        def quad(a, b, c, d):
            faces.append([a, b, c])
            faces.append([a, c, d])

        # Bottom face (solid, no openings cut from floor)
        i0 = V(*c0, base_z); i1 = V(*c1, base_z)
        i2 = V(*c2, base_z); i3 = V(*c3, base_z)
        quad(i0, i1, i2, i3)

        # Top face (solid)
        i4 = V(*c0, top_z); i5 = V(*c1, top_z)
        i6 = V(*c2, top_z); i7 = V(*c3, top_z)
        quad(i4, i6, i5, i4)  # note winding
        quad(i4, i7, i6, i4)

        # End caps (side 1 at pt1, side 3 at pt2)
        # Side 1: c0 base→c1 base→c1 top→c0 top
        quad(V(*c0, base_z), V(*c1, base_z), V(*c1, top_z), V(*c0, top_z))
        # Side 3: c2 base→c3 base→c3 top→c2 top
        quad(V(*c2, base_z), V(*c3, base_z), V(*c3, top_z), V(*c2, top_z))

        # Now build the two long faces (left and right) with openings cut out.
        # Left face runs c3→c0 (p2l→p1l) — but for consistent t=0→1,
        # left edge goes c0→c3 (t=0 at pt1, t=1 at pt2).
        # Right edge goes c1→c2 (t=0 at pt1, t=1 at pt2).

        for edge_start, edge_end in [(c0, c3), (c1, c2)]:
            # Build wall-face strips around each opening
            t_cursor = 0.0
            for (t0, t1, ob, ot) in openings_sorted:
                # Solid strip before this opening (full height)
                if t0 > t_cursor:
                    bl = lerp_2d(edge_start, edge_end, t_cursor)
                    br = lerp_2d(edge_start, edge_end, t0)
                    quad(V(*bl, base_z), V(*br, base_z), V(*br, top_z), V(*bl, top_z))

                ol = lerp_2d(edge_start, edge_end, t0)
                orr = lerp_2d(edge_start, edge_end, t1)

                # Below opening (sill region)
                if ob > base_z:
                    quad(V(*ol, base_z), V(*orr, base_z), V(*orr, ob), V(*ol, ob))
                # Above opening (head region)
                if ot < top_z:
                    quad(V(*ol, ot), V(*orr, ot), V(*orr, top_z), V(*ol, top_z))

                t_cursor = t1

            # Solid strip after last opening
            if t_cursor < 1.0:
                bl = lerp_2d(edge_start, edge_end, t_cursor)
                br = lerp_2d(edge_start, edge_end, 1.0)
                quad(V(*bl, base_z), V(*br, base_z), V(*br, top_z), V(*bl, top_z))

        return {"vertices": verts, "faces": faces, "color": color}

    # ── Miter join ────────────────────────────────────────────────────────────

    @staticmethod
    def _intersect_lines(p1: QPointF, p2: QPointF,
                         p3: QPointF, p4: QPointF) -> QPointF | None:
        """Intersect infinite lines (p1→p2) and (p3→p4). None if parallel."""
        dx1 = p2.x() - p1.x()
        dy1 = p2.y() - p1.y()
        dx2 = p4.x() - p3.x()
        dy2 = p4.y() - p3.y()
        denom = dx1 * dy2 - dy1 * dx2
        if abs(denom) < 1e-10:
            return None  # parallel
        t = ((p3.x() - p1.x()) * dy2 - (p3.y() - p1.y()) * dx2) / denom
        return QPointF(p1.x() + t * dx1, p1.y() + t * dy1)

    def _resolve_join_mode(self, endpoint_idx: int, num_walls_at_point: int) -> str:
        """Resolve the effective join mode for an endpoint.

        Auto defaults:
          - 2 walls at corner → Solid (continuous fill, no miter line)
          - 3+ walls (T or cross) → Butt (clean termination)
          - 1 wall (free end) → Butt
        """
        mode = self._join_mode_pt1 if endpoint_idx == 0 else self._join_mode_pt2
        if mode != "Auto":
            return mode
        # Auto logic
        if num_walls_at_point == 2:
            return "Solid"
        return "Butt"

    def mitered_quad(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
        """Return quad_points adjusted for per-endpoint join modes.

        Also sets ``_solid_pt1`` / ``_solid_pt2`` flags indicating which
        endpoints use Solid mode (so paint() can skip drawing the end edge).
        """
        quad, solid_pt1, solid_pt2 = self._compute_mitered_quad()
        self._solid_pt1 = solid_pt1
        self._solid_pt2 = solid_pt2
        return quad

    def snap_quad_points(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
        """Return the mitered/joined wall quad without any state mutation.

        Identical geometry to ``mitered_quad()`` but safe to call from the
        snap engine (which must not touch paint coordination state).
        """
        quad, _solid_pt1, _solid_pt2 = self._compute_mitered_quad()
        return quad

    def _compute_mitered_quad(
        self,
    ) -> tuple[tuple[QPointF, QPointF, QPointF, QPointF], bool, bool]:
        """Pure computation shared by mitered_quad() and snap_quad_points().

        Returns ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2). Does NOT
        read or write ``self._solid_pt1`` / ``self._solid_pt2``.
        """
        p1l, p1r, p2r, p2l = self.quad_points()
        solid_pt1 = False
        solid_pt2 = False

        sc = self.scene()
        if sc is None or not hasattr(sc, '_walls'):
            return ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2)

        MITER_TOL = 1.0
        MAX_MITER = self.half_thickness_scene() * 4

        for my_idx in (0, 1):
            my_pt = self._pt1 if my_idx == 0 else self._pt2

            partners = []
            for other in sc._walls:
                if other is self:
                    continue
                other_ep = other.endpoint_near(my_pt, MITER_TOL)
                if other_ep is not None:
                    partners.append((other, other_ep))

            mode = self._resolve_join_mode(my_idx, 1 + len(partners))

            if mode == "Butt" or not partners:
                continue

            other, other_ep = partners[0]
            o_p1l, o_p1r, o_p2r, o_p2l = other.quad_points()

            cross = (my_idx == other_ep)
            if cross:
                left_target = (o_p1r, o_p2r)
                right_target = (o_p1l, o_p2l)
            else:
                left_target = (o_p1l, o_p2l)
                right_target = (o_p1r, o_p2r)

            int_l = self._intersect_lines(p1l, p2l,
                                          left_target[0], left_target[1])
            int_r = self._intersect_lines(p1r, p2r,
                                          right_target[0], right_target[1])

            if int_l is not None and int_r is not None:
                dist_l = math.hypot(int_l.x() - my_pt.x(),
                                    int_l.y() - my_pt.y())
                dist_r = math.hypot(int_r.x() - my_pt.x(),
                                    int_r.y() - my_pt.y())
                if dist_l < MAX_MITER and dist_r < MAX_MITER:
                    if my_idx == 0:
                        p1l, p1r = int_l, int_r
                        if mode == "Solid":
                            solid_pt1 = True
                    else:
                        p2l, p2r = int_l, int_r
                        if mode == "Solid":
                            solid_pt2 = True

        return ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2)

    # ── Wall joining helper ──────────────────────────────────────────────────

    def endpoint_near(self, pos: QPointF, tolerance: float) -> int | None:
        """Return 0 if pos is near pt1, 1 if near pt2, else None."""
        if math.hypot(pos.x() - self._pt1.x(), pos.y() - self._pt1.y()) <= tolerance:
            return 0
        if math.hypot(pos.x() - self._pt2.x(), pos.y() - self._pt2.y()) <= tolerance:
            return 1
        return None

    def snap_endpoint_to(self, idx: int, target: QPointF):
        """Snap endpoint idx (0 or 1) exactly to target and rebuild."""
        if idx == 0:
            self._pt1 = QPointF(target)
        else:
            self._pt2 = QPointF(target)
        self._rebuild_path()

    def nearest_face_point(self, pos: QPointF, tolerance: float,
                           scale_manager=None,
                           reference_point: QPointF | None = None) -> QPointF | None:
        """Return the point on the wall face nearest to *reference_point*
        if *pos* is near the mid-section of this wall's centerline.

        Used for tee-intersection snapping: the joining wall's endpoint
        is trimmed to the face of the existing wall that is closest to the
        new wall's *other* endpoint (``reference_point``).  If no
        ``reference_point`` is given, the face closest to *pos* is returned
        (legacy behaviour).

        Returns ``None`` if *pos* is near an endpoint or too far from the
        centerline.
        """
        # Project pos onto the centerline parametrically
        ax, ay = self._pt1.x(), self._pt1.y()
        bx, by = self._pt2.x(), self._pt2.y()
        dx, dy = bx - ax, by - ay
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-12:
            return None
        t = ((pos.x() - ax) * dx + (pos.y() - ay) * dy) / len_sq

        # Must be in the mid-section (not near endpoints)
        margin = 0.05
        if t < margin or t > 1.0 - margin:
            return None

        # Perpendicular distance to centerline
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        perp_dist = math.hypot(pos.x() - proj_x, pos.y() - proj_y)
        if perp_dist > tolerance:
            return None

        # Get the wall quad to determine face positions
        p1l, p1r, p2r, p2l = compute_wall_quad(
            self._pt1, self._pt2, self._thickness_mm,
            self._alignment, scale_manager)

        # Interpolate left and right face at parameter t
        face_l = QPointF(p1l.x() + t * (p2l.x() - p1l.x()),
                         p1l.y() + t * (p2l.y() - p1l.y()))
        face_r = QPointF(p1r.x() + t * (p2r.x() - p1r.x()),
                         p1r.y() + t * (p2r.y() - p1r.y()))

        # Choose the face nearest to reference_point (the new wall's
        # other endpoint) so the new wall terminates on the correct side.
        ref = reference_point if reference_point is not None else pos
        d_l = math.hypot(ref.x() - face_l.x(), ref.y() - face_l.y())
        d_r = math.hypot(ref.x() - face_r.x(), ref.y() - face_r.y())
        return face_l if d_l <= d_r else face_r
