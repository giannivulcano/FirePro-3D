"""
floor_slab.py
=============
FloorSlab entity for FirePro 3D.

Click-to-define boundary in 2D (like a polyline that closes),
rendered as a semi-transparent filled polygon in 2D and a flat
slab with thickness in 3D.
"""

from __future__ import annotations

import math

from .geometry_utils import triangulate_polygon

from PyQt6.QtWidgets import QGraphicsPathItem, QStyle, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QPen, QColor, QPainterPath, QBrush, QPainterPathStroker, QPolygonF,
)

from .constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_THICKNESS_MM = 152.4   # 6 inches
_FILL_ALPHA = 50               # semi-transparent fill in 2D
_SELECTION_COLOR = QColor("red")


def _scene_hit_width(item) -> float:
    sc = item.scene()
    if sc:
        views = sc.views()
        if views:
            scale = views[0].transform().m11()
            return max(4.0, 12.0 / max(scale, 1e-6))
    return 6.0


# ── FloorSlab ────────────────────────────────────────────────────────────────

from .displayable_item import DisplayableItemMixin


class FloorSlab(DisplayableItemMixin, QGraphicsPathItem):
    """A floor slab defined by a closed boundary polygon.

    2D rendering: semi-transparent filled polygon with outline.
    3D mesh: flat polygon extruded downward by ``thickness_mm``.
    """

    def __init__(self, points: list[QPointF] | None = None,
                 color: str | QColor = "#8888cc"):
        super().__init__()
        self._points: list[QPointF] = [QPointF(p) for p in (points or [])]
        self._color = QColor(color) if isinstance(color, str) else QColor(color)
        self._thickness_mm: float = DEFAULT_THICKNESS_MM
        self._level_offset_mm: float = 0.0  # vertical offset from level elevation

        self.init_displayable()
        self.name: str = ""

        self.setZValue(-80)      # behind walls and pipes
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        if len(self._points) >= 3:
            self._rebuild_path()

    def z_range_mm(self) -> tuple[float, float] | None:
        """Slab top is at level elevation, bottom is elevation - thickness."""
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return None
        lvl = lm.get(getattr(self, "level", None))
        if lvl is None:
            return None
        top_z = lvl.elevation + self._level_offset_mm
        bot_z = top_z - self._thickness_mm
        return (bot_z, top_z)

    # ── Point management ─────────────────────────────────────────────────────

    def add_point(self, pt: QPointF):
        self._points.append(QPointF(pt))
        self._rebuild_path()

    def close_polygon(self):
        """Call after the last point is added to finalise the polygon."""
        if len(self._points) >= 3:
            self._rebuild_path()

    @property
    def points(self) -> list[QPointF]:
        return self._points

    # ── Path rebuild (2D) ────────────────────────────────────────────────────

    def _rebuild_path(self):
        path = QPainterPath()
        if len(self._points) < 2:
            self.setPath(path)
            return
        path.moveTo(self._points[0])
        for p in self._points[1:]:
            path.lineTo(p)
        if len(self._points) >= 3:
            path.closeSubpath()
        self.setPath(path)

    # ── Paint ────────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected

        line_col = QColor(self._display_color) if self._display_color else self._color
        pen = QPen(line_col, 1)
        pen.setCosmetic(True)

        # When this slab is within the plan view range, draw an opaque
        # background fill first so it masks items below (walls on lower floors).
        if getattr(self, "_is_occluding", False) and len(self._points) >= 3:
            # Get scene background colour for the mask
            sc = self.scene()
            bg = QColor("#ffffff")  # fallback
            if sc:
                views = sc.views()
                if views:
                    vp_palette = views[0].viewport().palette()
                    bg = vp_palette.color(vp_palette.ColorRole.Base)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(bg))
            painter.drawPolygon(QPolygonF(self._points))

        painter.setPen(pen)

        if self._display_fill_color:
            fill_color = QColor(self._display_fill_color)
            fill_color.setAlpha(_FILL_ALPHA)
        else:
            fill_color = QColor(self._color)
            fill_color.setAlpha(_FILL_ALPHA)
        painter.setBrush(QBrush(fill_color))

        if len(self._points) >= 3:
            poly = QPolygonF(self._points)
            painter.drawPolygon(poly)
        elif len(self._points) == 2:
            painter.drawLine(self._points[0], self._points[1])

        # Section-cut hatch overlay
        if getattr(self, "_is_section_cut", False) and len(self._points) >= 3:
            from .displayable_item import draw_section_hatch
            clip = QPainterPath()
            clip.addPolygon(QPolygonF(self._points))
            clip.closeSubpath()
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

        if self.isSelected():
            sel_pen = QPen(_SELECTION_COLOR, 2)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if len(self._points) >= 3:
                painter.drawPolygon(QPolygonF(self._points))

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        path = self.path()
        if path.isEmpty():
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path) | path    # union stroke + fill area

    # ── Grip points ──────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        return [QPointF(p) for p in self._points]

    def apply_grip(self, index: int, new_pos: QPointF):
        if 0 <= index < len(self._points):
            self._points[index] = QPointF(new_pos)
            self._rebuild_path()

    def insert_point(self, idx: int, pt: QPointF):
        """Insert a vertex at position *idx* (shifts subsequent points)."""
        self._points.insert(idx, QPointF(pt))
        self._rebuild_path()

    def remove_point(self, idx: int):
        """Remove vertex at *idx* (no-op if would leave < 3 points)."""
        if len(self._points) <= 3:
            return
        if 0 <= idx < len(self._points):
            self._points.pop(idx)
            self._rebuild_path()

    def nearest_edge(self, pt: QPointF) -> tuple[int, float, QPointF]:
        """Return (edge_index, distance, projection_point) for the edge
        closest to *pt*.  Edge *i* runs from _points[i] → _points[(i+1)%n].
        """
        best_idx, best_dist, best_proj = 0, float("inf"), QPointF(pt)
        n = len(self._points)
        for i in range(n):
            a = self._points[i]
            b = self._points[(i + 1) % n]
            dx, dy = b.x() - a.x(), b.y() - a.y()
            len_sq = dx * dx + dy * dy
            if len_sq < 1e-12:
                t = 0.0
            else:
                t = max(0.0, min(1.0, ((pt.x() - a.x()) * dx + (pt.y() - a.y()) * dy) / len_sq))
            proj = QPointF(a.x() + t * dx, a.y() + t * dy)
            d = math.hypot(pt.x() - proj.x(), pt.y() - proj.y())
            if d < best_dist:
                best_idx, best_dist, best_proj = i, d, proj
        return best_idx, best_dist, best_proj

    def translate(self, dx: float, dy: float):
        self._points = [QPointF(p.x() + dx, p.y() + dy) for p in self._points]
        self._rebuild_path()

    # ── Properties API ───────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Type":          {"type": "label",     "value": "Floor Slab"},
            "Name":          {"type": "string",    "value": self.name},
            "Level":         {"type": "level_ref", "value": self.level},
            "Level Offset":  {"type": "dimension", "value": self._fmt(self._level_offset_mm),
                              "value_mm": self._level_offset_mm},
            "Colour":        {"type": "color",     "value": self._color.name()},
            "Thickness":     {"type": "dimension", "value": self._fmt(self._thickness_mm),
                              "value_mm": self._thickness_mm},
            "Points":        {"type": "label",     "value": str(len(self._points))},
        }

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
        elif key == "Level":
            self.level = str(value)
        elif key == "Level Offset":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._level_offset_mm = parsed
        elif key == "Colour":
            self._color = QColor(value)
            self.update()
        elif key == "Thickness":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._thickness_mm = parsed

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":              "floor_slab",
            "points":            [[p.x(), p.y()] for p in self._points],
            "color":             self._color.name(),
            "thickness_mm":      self._thickness_mm,
            "level":             self.level,
            "user_layer":        self.user_layer,
            "name":              self.name,
        }
        if self._level_offset_mm != 0.0:
            d["level_offset_mm"] = self._level_offset_mm
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FloorSlab":
        points = [QPointF(p[0], p[1]) for p in data.get("points", [])]
        slab = cls(points=points, color=data.get("color", "#8888cc"))
        # New mm key; fall back to old ft key with conversion
        if "thickness_mm" in data:
            slab._thickness_mm = data["thickness_mm"]
        else:
            slab._thickness_mm = data.get("thickness_ft", DEFAULT_THICKNESS_MM / 304.8) * 304.8
        slab.level = data.get("level", DEFAULT_LEVEL)
        slab.user_layer = data.get("user_layer", DEFAULT_USER_LAYER)
        slab.name = data.get("name", "")
        slab._level_offset_mm = data.get("level_offset_mm", 0.0)
        return slab

    # ── 3D mesh generation ───────────────────────────────────────────────────

    def get_3d_mesh(self, level_manager=None) -> dict | None:
        """Return vertices and faces for the flat slab.

        The slab sits at the level elevation and extends downward
        by ``thickness_ft``. Uses ear-clipping triangulation for the polygon.
        """
        if len(self._points) < 3:
            return None

        # Level elevation (mm) + offset
        top_z = 0.0
        if level_manager is not None:
            lvl = level_manager.get(self.level)
            if lvl:
                top_z = lvl.elevation + self._level_offset_mm
        bot_z = top_z - self._thickness_mm

        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None

        def to_mm(pt: QPointF) -> tuple[float, float]:
            if sm and sm.is_calibrated and sm.drawing_scale > 0:
                return (sm.scene_to_real(pt.x()), -sm.scene_to_real(pt.y()))
            return (pt.x(), -pt.y())

        pts_2d = [to_mm(p) for p in self._points]
        n = len(pts_2d)

        # Triangulate polygon (simple ear-clipping)
        tri_indices = triangulate_polygon(pts_2d)
        if not tri_indices:
            return None

        # Build vertices: top ring + bottom ring
        verts = []
        for x, y in pts_2d:
            verts.append([x, y, top_z])
        for x, y in pts_2d:
            verts.append([x, y, bot_z])

        faces = []
        # Top face
        for a, b, c in tri_indices:
            faces.append([a, b, c])
        # Bottom face (reversed winding)
        for a, b, c in tri_indices:
            faces.append([a + n, c + n, b + n])
        # Side faces
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, j + n])
            faces.append([i, j + n, i + n])

        return {
            "vertices": verts,
            "faces": faces,
            "color": (self._color.redF(), self._color.greenF(),
                      self._color.blueF(), 1.0),
        }

