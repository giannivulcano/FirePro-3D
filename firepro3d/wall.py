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

from .constants import (DEFAULT_LEVEL,
                       MITER_TOL, MAX_MITER_FACTOR)

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
ALIGN_LEFT     = "Left"
ALIGN_RIGHT    = "Right"

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

    if alignment == ALIGN_LEFT:
        # Left: axis is on the left face — wall extends rightward
        off_left = QPointF(nx * ht * 2, ny * ht * 2)
        off_right = QPointF(0, 0)
    elif alignment == ALIGN_RIGHT:
        # Right: axis is on the right face — wall extends leftward
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

        # Alignment mode (centerline / left / right)
        self._alignment: str = ALIGN_CENTER

        # Per-endpoint join mode
        # Auto: solid at 2-wall corners, butt at T/cross intersections
        # Solid: continuous fill, no visible miter line
        # Butt: no miter extension
        self._join_mode_pt1: str = "Auto"
        self._join_mode_pt2: str = "Auto"
        self._solid_pt1: bool = False   # set by mitered_quad()
        self._solid_pt2: bool = False
        # Extra end vertices covering the junction wedge at 3-wall full
        # miters (between p1r→p1l / p2l→p2r in the fill polygon)
        self._end_wedge_pts1: list[QPointF] = []
        self._end_wedge_pts2: list[QPointF] = []

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
          Center — click line is the wall centerline (default)
          Left   — click line is the left (normal-side) face
          Right  — click line is the right face
        """
        nx, ny = self.normal()
        ht = self.half_thickness_scene()
        if self._alignment == ALIGN_LEFT:
            # Left: axis is on the left face — wall extends rightward
            off_left = QPointF(nx * ht * 2, ny * ht * 2)
            off_right = QPointF(0, 0)
        elif self._alignment == ALIGN_RIGHT:
            # Right: axis is on the right face — wall extends leftward
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
        # Outer rectangle (possibly mitered; wedge vertices cover the
        # junction triangle at 3-wall full miters)
        path.moveTo(p1l)
        path.lineTo(p2l)
        for pt in self._end_wedge_pts2:
            path.lineTo(pt)
        path.lineTo(p2r)
        path.lineTo(p1r)
        for pt in self._end_wedge_pts1:
            path.lineTo(pt)
        path.closeSubpath()
        self.setPath(path)
        # Reposition owned openings to reflect updated wall geometry
        for op in self.openings:
            op._reposition()

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
            else:
                fill_color = QColor(self._color)
            if not getattr(self, "_paper_fill_opaque", False):
                fill_color.setAlpha(80)
            fill_brush = QBrush(fill_color)

        solid_pt1 = getattr(self, "_solid_pt1", False)
        solid_pt2 = getattr(self, "_solid_pt2", False)
        # Fill polygon includes junction-wedge vertices (3-wall miters)
        fill_poly = QPolygonF([p1l, p2l, *self._end_wedge_pts2,
                               p2r, p1r, *self._end_wedge_pts1])

        if not solid_pt1 and not solid_pt2:
            # No solid joins — draw full polygon as before
            painter.setPen(pen)
            painter.setBrush(fill_brush)
            painter.drawPolygon(fill_poly)
        else:
            # Fill the quad without outline, then draw only non-solid edges
            if fill_brush != Qt.BrushStyle.NoBrush:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill_brush)
                painter.drawPolygon(fill_poly)

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
            clip.addPolygon(fill_poly)
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
                painter.drawPolygon(fill_poly)
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
        # Width grip on the far face midpoint
        p1l, p1r, p2r, p2l = self.quad_points()
        if self._alignment == ALIGN_RIGHT:
            # Right-aligned: far face is the right (negative-normal) side
            width_grip = QPointF((p2r.x() + p1r.x()) / 2,
                                 (p2r.y() + p1r.y()) / 2)
        else:
            # Center/Left: far face is the left (positive-normal) side
            width_grip = QPointF((p1l.x() + p2l.x()) / 2,
                                 (p1l.y() + p2l.y()) / 2)
        return [QPointF(self._pt1), QPointF(self._pt2), mid, width_grip]

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
        elif index == 3:
            # Width grip — drag perpendicular to wall to adjust thickness
            nx, ny = self.normal()
            mid_x = (self._pt1.x() + self._pt2.x()) / 2
            mid_y = (self._pt1.y() + self._pt2.y()) / 2
            d = abs((new_pos.x() - mid_x) * nx + (new_pos.y() - mid_y) * ny)
            ht_scene = self.half_thickness_scene()
            if ht_scene > 0 and d > 0:
                if self._alignment == ALIGN_CENTER:
                    new_thickness = self._thickness_mm * (d / ht_scene)
                else:
                    new_thickness = self._thickness_mm * (d / (2 * ht_scene))
                self._thickness_mm = max(new_thickness, 25.4)  # min ~1 inch
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
                             "options": ["Center", "Left", "Right"]},
            "Base Level":   {"type": "level_ref", "value": self._base_level},
            "Base Offset":  {"type": "dimension", "value": self._fmt(self._base_offset_mm),
                             "value_mm": self._base_offset_mm},
            "Top Level":    {"type": "level_ref", "value": self._top_level},
            "Top Offset":   {"type": "dimension", "value": self._fmt(self._top_offset_mm),
                             "value_mm": self._top_offset_mm},
            "Height":       {"type": "label",     "value": self._fmt(height_mm)},
            "Join Start":   {"type": "enum",      "value": self._join_mode_pt1,
                             "options": ["Auto", "Butt", "Solid"]},
            "Join End":     {"type": "enum",      "value": self._join_mode_pt2,
                             "options": ["Auto", "Butt", "Solid"]},
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
                self._thickness_mm = max(parsed, 1.0)
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
            if str(value) in ("Auto", "Butt", "Solid"):
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
        thick_mm = max(thick_mm, 1.0)
        wall = cls(pt1, pt2, thickness_mm=thick_mm,
                   color=data.get("color", "#cccccc"))
        wall._fill_mode = data.get("fill_mode", FILL_NONE)
        wall._alignment = data.get("alignment", ALIGN_CENTER)
        # Migration: rename Interior/Exterior → Left/Right
        if wall._alignment == "Interior":
            wall._alignment = "Left"
        elif wall._alignment == "Exterior":
            wall._alignment = "Right"
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
        wall.name = data.get("name", "")
        # Per-endpoint join modes (backward compat: old "join_mode" applies to both)
        legacy = data.get("join_mode", "Auto")
        wall._join_mode_pt1 = data.get("join_mode_pt1", legacy)
        wall._join_mode_pt2 = data.get("join_mode_pt2", legacy)
        # Migration: Miter removed — map to Solid (preserves corner geometry)
        if wall._join_mode_pt1 == "Miter":
            wall._join_mode_pt1 = "Solid"
        if wall._join_mode_pt2 == "Miter":
            wall._join_mode_pt2 = "Solid"
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
        _vert_cache: dict[tuple, int] = {}

        def V(x, y, z):
            # Round to sub-micron precision so geometrically identical points
            # share a vertex index, enabling edge-sharing for watertightness.
            key = (round(x, 4), round(y, 4), round(z, 4))
            if key in _vert_cache:
                return _vert_cache[key]
            idx = len(verts)
            verts.append([x, y, z])
            _vert_cache[key] = idx
            return idx

        def quad(a, b, c, d):
            faces.append([a, b, c])
            faces.append([a, c, d])

        # ── Structured mesh: t-columns × z-rows ──────────────────────────────
        # Build t-breakpoints and z-breakpoints from all openings so that every
        # cell boundary is shared correctly between adjacent faces.
        #
        # t-columns: [0..t0, t0..t1, t1..1] for each opening
        # z-rows:    [base_z..ob, ob..ot, ot..top_z] for each opening
        #
        # The centre cell (t0..t1, ob..ot) is the aperture void — no face.
        # All other cells emit one quad on each of the two long faces,
        # plus the end caps and floor/ceiling close the box.

        # Collect unique t-breakpoints and z-breakpoints
        t_pts = sorted({0.0, 1.0} | {t for (t0, t1, _, __) in openings_sorted
                                      for t in (t0, t1)})
        z_pts = sorted({base_z, top_z} | {z for (_, __, ob, ot) in openings_sorted
                                           for z in (ob, ot)})

        # Build set of (t-col, z-row) cells that are void (aperture)
        void_cells = set()
        for (t0, t1, ob, ot) in openings_sorted:
            ti = t_pts.index(t0)
            zi = z_pts.index(ob)
            void_cells.add((ti, zi))  # col=ti (t0→t1 segment), row=zi (ob→ot segment)

        # End caps (side 1 at pt1-end t=0, side 3 at pt2-end t=1) — always solid.
        # Side 1: c0(left)–c1(right) end cap
        for zi in range(len(z_pts) - 1):
            za, zb = z_pts[zi], z_pts[zi + 1]
            quad(V(*c0, za), V(*c1, za), V(*c1, zb), V(*c0, zb))
        # Side 3: c3(left)–c2(right) end cap
        for zi in range(len(z_pts) - 1):
            za, zb = z_pts[zi], z_pts[zi + 1]
            quad(V(*c3, za), V(*c2, za), V(*c2, zb), V(*c3, zb))

        # The bottom-face row index and top-face row index in z_pts.
        bottom_zi = z_pts.index(base_z)   # always 0
        top_zi = len(z_pts) - 2           # always the last row (z_pts[-2]→top_z)

        # Bottom face (z = base_z): skip any t-column where the aperture goes
        # all the way to the floor (ob == base_z), since there is no wall
        # material on the floor at the opening position — the jamb provides the
        # only face there, and including a bottom quad would share the edge with
        # 3 faces instead of 2, creating a non-manifold mesh.
        # Winding → normal DOWN (−Z).
        for ti in range(len(t_pts) - 1):
            if (ti, bottom_zi) in void_cells:
                continue    # opening at floor level — no bottom face here
            ta, tb = t_pts[ti], t_pts[ti + 1]
            lA = lerp_2d(c0, c3, ta);  rA = lerp_2d(c1, c2, ta)
            lB = lerp_2d(c0, c3, tb);  rB = lerp_2d(c1, c2, tb)
            quad(V(*lA, base_z), V(*rA, base_z), V(*rB, base_z), V(*lB, base_z))

        # Top face (z = top_z): skip any t-column where the aperture goes all
        # the way to the ceiling (ot == top_z) — same reasoning as bottom face.
        # Winding → normal UP (+Z).
        for ti in range(len(t_pts) - 1):
            if (ti, top_zi) in void_cells:
                continue    # opening at ceiling level — no top face here
            ta, tb = t_pts[ti], t_pts[ti + 1]
            lA = lerp_2d(c0, c3, ta);  rA = lerp_2d(c1, c2, ta)
            lB = lerp_2d(c0, c3, tb);  rB = lerp_2d(c1, c2, tb)
            quad(V(*lB, top_z), V(*rB, top_z), V(*rA, top_z), V(*lA, top_z))

        # ── Long faces (left c0→c3 and right c1→c2) with aperture voids ──────
        # Each (t-col, z-row) cell that is NOT void gets a quad on EACH long face.
        # Left face normal: outward (away from wall depth centre).
        # Right face normal: outward (away from wall depth centre).
        #
        # Left face quad winding: (near-bot, far-bot, far-top, near-top) → outward −Y
        # Right face quad winding: (near-bot, far-bot, far-top, near-top) but
        #   for right face c1→c2 "near" = smaller t → same winding pattern.

        for ti in range(len(t_pts) - 1):
            ta, tb = t_pts[ti], t_pts[ti + 1]
            for zi in range(len(z_pts) - 1):
                if (ti, zi) in void_cells:
                    continue        # aperture void — no face
                za, zb = z_pts[zi], z_pts[zi + 1]

                # Left long face (c0→c3 edge)
                lA = lerp_2d(c0, c3, ta)
                lB = lerp_2d(c0, c3, tb)
                quad(V(*lA, za), V(*lB, za), V(*lB, zb), V(*lA, zb))

                # Right long face (c1→c2 edge)
                rA = lerp_2d(c1, c2, ta)
                rB = lerp_2d(c1, c2, tb)
                quad(V(*rA, za), V(*rB, za), V(*rB, zb), V(*rA, zb))

        # ── Reveal caps: close the tunnel at each aperture depth-face ─────────
        # At each aperture void cell (ti, zi), four faces close the tunnel:
        #   sill cap (bottom of void), head cap (top of void),
        #   near jamb (t=t0 face), far jamb (t=t1 face).
        # Each cap face connects the left-face side to the right-face side.
        for (ti, zi) in void_cells:
            ta, tb = t_pts[ti], t_pts[ti + 1]    # t0, t1
            za, zb = z_pts[zi], z_pts[zi + 1]    # ob, ot

            oL0 = lerp_2d(c0, c3, ta)    # left face at t=t0
            oL1 = lerp_2d(c0, c3, tb)    # left face at t=t1
            oR0 = lerp_2d(c1, c2, ta)    # right face at t=t0
            oR1 = lerp_2d(c1, c2, tb)    # right face at t=t1

            # Sill cap (z = za = ob): quad facing UP into aperture.
            # Only needed when ob > base_z; if ob == base_z the bottom face
            # (emitted above) already covers this horizontal surface.
            if za > base_z:
                quad(V(*oL0, za), V(*oR0, za), V(*oR1, za), V(*oL1, za))

            # Head cap (z = zb = ot): quad facing DOWN into aperture.
            # Only needed when ot < top_z; if ot == top_z the top face
            # (emitted above) already covers this horizontal surface.
            if zb < top_z:
                quad(V(*oL1, zb), V(*oR1, zb), V(*oR0, zb), V(*oL0, zb))

            # Near jamb (t = ta = t0): quad facing toward t<t0.
            quad(V(*oL0, za), V(*oL0, zb), V(*oR0, zb), V(*oR0, za))

            # Far jamb (t = tb = t1): quad facing toward t>t1.
            quad(V(*oR1, za), V(*oL1, za), V(*oL1, zb), V(*oR1, zb))

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
        quad, solid_pt1, solid_pt2, wedge1, wedge2 = self._compute_mitered_quad()
        self._solid_pt1 = solid_pt1
        self._solid_pt2 = solid_pt2
        self._end_wedge_pts1 = wedge1
        self._end_wedge_pts2 = wedge2
        return quad

    def snap_quad_points(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
        """Return the mitered/joined wall quad without any state mutation.

        Identical geometry to ``mitered_quad()`` but safe to call from the
        snap engine (which must not touch paint coordination state).
        """
        quad, _solid_pt1, _solid_pt2, _w1, _w2 = self._compute_mitered_quad()
        return quad

    def _compute_mitered_quad(
        self,
    ) -> tuple[tuple[QPointF, QPointF, QPointF, QPointF], bool, bool,
               list[QPointF], list[QPointF]]:
        """Pure computation shared by mitered_quad() and snap_quad_points().

        Returns ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2, wedge_pts1,
        wedge_pts2) where the wedge lists hold extra end vertices that
        make the fill polygon cover the junction wedge at 3-wall full
        miters.  Does NOT read or write ``self._solid_pt1`` /
        ``self._solid_pt2``.
        """
        p1l, p1r, p2r, p2l = self.quad_points()
        solid_pt1 = False
        solid_pt2 = False
        wedge1: list[QPointF] = []
        wedge2: list[QPointF] = []

        sc = self.scene()
        if sc is None or not hasattr(sc, '_walls'):
            return ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2,
                    wedge1, wedge2)

        MAX_MITER = self.half_thickness_scene() * MAX_MITER_FACTOR

        for my_idx in (0, 1):
            my_pt = self._pt1 if my_idx == 0 else self._pt2

            partners = []
            for other in sc._walls:
                if other is self:
                    continue
                other_ep = other.endpoint_near(my_pt, MITER_TOL)
                if other_ep is not None:
                    partners.append((other, other_ep))

            raw_mode = (self._join_mode_pt1 if my_idx == 0
                        else self._join_mode_pt2)
            if raw_mode == "Auto" and len(partners) == 2:
                # 3-wall junction: full miter cleanup (pie join) — each
                # face miters to its angular neighbour; falls back to
                # Butt when the geometry degenerates.
                pie = self._pie_miter_corners(
                    my_idx, my_pt, partners, (p1l, p1r, p2r, p2l),
                    MAX_MITER)
                if pie is not None:
                    int_l, int_r, wpts = pie
                    if my_idx == 0:
                        p1l, p1r = int_l, int_r
                        solid_pt1 = True
                        wedge1 = wpts
                    else:
                        p2l, p2r = int_l, int_r
                        solid_pt2 = True
                        wedge2 = wpts
                continue

            if raw_mode == "Auto" and not partners:
                # Tee join: endpoint on a host wall mid-span — cope the
                # end to the host's near face (any angle; also cleans up
                # legacy face-snapped endpoints).
                tee = self._tee_cope_corners(
                    my_idx, my_pt, sc._walls, (p1l, p1r, p2r, p2l),
                    MAX_MITER)
                if tee is not None:
                    int_l, int_r = tee
                    if my_idx == 0:
                        p1l, p1r = int_l, int_r
                        solid_pt1 = True
                    else:
                        p2l, p2r = int_l, int_r
                        solid_pt2 = True
                continue

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

        return ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2, wedge1, wedge2)

    def _pie_miter_corners(self, my_idx: int, my_pt: QPointF, partners,
                           quad, max_miter: float):
        """Full-miter corners for one endpoint of a 3-wall junction.

        Sorts the two partners angularly around the junction, miters
        this wall's left/right face against the wedge-facing face of the
        angularly adjacent partner, and computes the third junction
        corner (the partners' far-face intersection) so the fill polygon
        can cover the junction wedge.

        Returns ``(int_left, int_right, wedge_pts)`` or ``None`` when
        the geometry degenerates (zero-length walls, parallel faces,
        miter beyond *max_miter*) — the caller then falls back to Butt.
        """
        p1l, p1r, p2r, p2l = quad
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return None
        if my_idx == 0:
            ux, uy = dx / length, dy / length
        else:
            ux, uy = -dx / length, -dy / length
        # Which rotation direction from the outward vector reaches my
        # LEFT face: +rot90 at pt1, −rot90 at pt2 (quad_points puts the
        # left face on the +rot90(pt1→pt2) side).
        left_sign = 1.0 if my_idx == 0 else -1.0

        infos = []
        for other, other_ep in partners:
            odx = other._pt2.x() - other._pt1.x()
            ody = other._pt2.y() - other._pt1.y()
            olen = math.hypot(odx, ody)
            if olen < 1e-9:
                return None
            if other_ep == 0:
                oux, ouy = odx / olen, ody / olen
            else:
                oux, ouy = -odx / olen, -ody / olen
            cross = ux * ouy - uy * oux
            dot = ux * oux + uy * ouy
            theta = math.atan2(cross, dot)
            phi = theta if theta > 1e-9 else theta + 2.0 * math.pi
            infos.append((phi, other, oux, ouy))

        infos.sort(key=lambda e: e[0])
        ccw, cw = infos[0], infos[-1]
        left_info = ccw if left_sign > 0 else cw
        right_info = cw if left_sign > 0 else ccw

        def faces(info, s):
            """(wedge-facing face line, far face line) of a partner."""
            _phi, other, oux, ouy = info
            o_p1l, o_p1r, o_p2r, o_p2l = other.quad_points()
            left_line = (o_p1l, o_p2l)
            right_line = (o_p1r, o_p2r)
            odx2 = other._pt2.x() - other._pt1.x()
            ody2 = other._pt2.y() - other._pt1.y()
            olen2 = math.hypot(odx2, ody2)
            lnx, lny = -ody2 / olen2, odx2 / olen2   # left-face offset dir
            wnx, wny = s * ouy, -s * oux             # −s·rot90(u_partner)
            if lnx * wnx + lny * wny > 0:
                return left_line, right_line
            return right_line, left_line

        wedge_l, far_l = faces(left_info, left_sign)
        wedge_r, far_r = faces(right_info, -left_sign)

        int_l = self._intersect_lines(p1l, p2l, wedge_l[0], wedge_l[1])
        int_r = self._intersect_lines(p1r, p2r, wedge_r[0], wedge_r[1])
        if int_l is None or int_r is None:
            return None
        if (math.hypot(int_l.x() - my_pt.x(), int_l.y() - my_pt.y())
                >= max_miter
                or math.hypot(int_r.x() - my_pt.x(), int_r.y() - my_pt.y())
                >= max_miter):
            return None

        wedge_pts: list[QPointF] = []
        extra = self._intersect_lines(far_l[0], far_l[1], far_r[0], far_r[1])
        if extra is not None and math.hypot(
                extra.x() - my_pt.x(), extra.y() - my_pt.y()) < max_miter:
            wedge_pts.append(extra)
        return int_l, int_r, wedge_pts

    def _tee_cope_corners(self, my_idx: int, my_pt: QPointF, walls,
                          quad, max_miter: float):
        """Cope an endpoint that tees into a host wall mid-span.

        Host = the nearest wall whose centerline passes within its half
        thickness (+ ``MITER_TOL``) of the endpoint, away from the
        host's own endpoints.  Both of this wall's face lines are
        intersected with the host's *near* face (the face on this wall's
        body side), so the end hugs the host face at any angle.  Works
        for endpoints on the host centerline (tee snap) and for legacy
        endpoints snapped to the face.

        Returns ``(int_left, int_right)`` or ``None`` (no host, ref on
        the host centerline, parallel faces, or miter beyond the clamp).
        """
        p1l, p1r, p2r, p2l = quad
        host = None
        host_dist = float("inf")
        for other in walls:
            if other is self:
                continue
            band = other.half_thickness_scene() + MITER_TOL
            proj = other.nearest_centerline_point(my_pt, band)
            if proj is None:
                continue
            d = math.hypot(my_pt.x() - proj.x(), my_pt.y() - proj.y())
            if d < host_dist:
                host_dist = d
                host = other
        if host is None:
            return None

        # Near face = host face on my body's side of the host centerline
        ref = self._pt2 if my_idx == 0 else self._pt1
        hax, hay = host._pt1.x(), host._pt1.y()
        hdx = host._pt2.x() - hax
        hdy = host._pt2.y() - hay
        s_ref = hdx * (ref.y() - hay) - hdy * (ref.x() - hax)
        if abs(s_ref) < 1e-9:
            return None    # running along the host — no usable cope
        sign = 1.0 if s_ref > 0 else -1.0
        o_p1l, o_p1r, o_p2r, o_p2l = host.quad_points()
        s_l = hdx * (o_p1l.y() - hay) - hdy * (o_p1l.x() - hax)
        s_r = hdx * (o_p1r.y() - hay) - hdy * (o_p1r.x() - hax)
        if s_l * sign >= s_r * sign:
            face = (o_p1l, o_p2l)
        else:
            face = (o_p1r, o_p2r)

        int_l = self._intersect_lines(p1l, p2l, face[0], face[1])
        int_r = self._intersect_lines(p1r, p2r, face[0], face[1])
        if int_l is None or int_r is None:
            return None
        if (math.hypot(int_l.x() - my_pt.x(), int_l.y() - my_pt.y())
                >= max_miter
                or math.hypot(int_r.x() - my_pt.x(), int_r.y() - my_pt.y())
                >= max_miter):
            return None
        return int_l, int_r

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

    def nearest_centerline_point(self, pos: QPointF,
                                 tolerance: float) -> QPointF | None:
        """Return the projection of *pos* onto this wall's centerline if
        *pos* is near the mid-section (tee-join target).

        Returns ``None`` if *pos* projects near an endpoint (5% margin,
        matching ``nearest_face_point``) or lies farther than
        *tolerance* from the centerline.
        """
        ax, ay = self._pt1.x(), self._pt1.y()
        bx, by = self._pt2.x(), self._pt2.y()
        dx, dy = bx - ax, by - ay
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-12:
            return None
        t = ((pos.x() - ax) * dx + (pos.y() - ay) * dy) / len_sq
        margin = 0.05
        if t < margin or t > 1.0 - margin:
            return None
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        if math.hypot(pos.x() - proj_x, pos.y() - proj_y) > tolerance:
            return None
        return QPointF(proj_x, proj_y)

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
