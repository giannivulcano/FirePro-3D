"""
roof.py
=======
RoofItem entity for FirePro 3D.

Click-to-define boundary in 2D (like a polyline that closes),
rendered as a semi-transparent filled polygon with ridge/hip lines
in 2D, and a 3D mesh with optional pitch in the 3D view.
"""

from __future__ import annotations

import math

from .geometry_utils import triangulate_polygon

from PyQt6.QtWidgets import QGraphicsPathItem, QStyle, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QPen, QColor, QPainterPath, QBrush, QPainterPathStroker, QPolygonF,
)

from .constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER, Z_ROOF

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_THICKNESS_MM = 152.4     # 6 inches (0.5 ft × 304.8)
DEFAULT_PITCH_DEG = 20.0        # default slope for gable/hip
DEFAULT_EAVE_HEIGHT_MM = 0.0    # offset above level datum (mm)
DEFAULT_OVERHANG_MM = 0.0       # no overhang by default
_FILL_ALPHA = 40                # semi-transparent fill in 2D
_SELECTION_COLOR = QColor("red")

ROOF_TYPES = ("flat", "gable", "hip", "shed")


def _offset_polygon(points: list[QPointF], dist: float) -> list[QPointF]:
    """Expand a closed polygon outward by *dist* scene units.

    Uses the perpendicular-offset-of-each-edge approach and finds
    intersections of adjacent offset edges.  Falls back to the original
    polygon on degenerate cases.
    """
    n = len(points)
    if n < 3 or dist <= 0:
        return list(points)

    # Ensure CCW winding (positive area = CCW in screen coords where Y↓)
    area = sum(
        points[i].x() * points[(i + 1) % n].y()
        - points[(i + 1) % n].x() * points[i].y()
        for i in range(n)
    )
    # In Qt screen coords (Y down), the perpendicular (-dy, dx) points
    # to the *left* of the edge direction.  For a visually-CW polygon
    # (negative signed area) that is outward; for visually-CCW (positive
    # signed area) we must negate to keep the offset outward.
    sign = -1.0 if area > 0 else 1.0

    # Compute offset edges (each edge moved outward by dist)
    offset_edges = []
    for i in range(n):
        j = (i + 1) % n
        dx = points[j].x() - points[i].x()
        dy = points[j].y() - points[i].y()
        length = math.hypot(dx, dy)
        if length < 1e-9:
            offset_edges.append((points[i], points[j]))
            continue
        # Outward normal
        nx = -dy / length * dist * sign
        ny = dx / length * dist * sign
        p1 = QPointF(points[i].x() + nx, points[i].y() + ny)
        p2 = QPointF(points[j].x() + nx, points[j].y() + ny)
        offset_edges.append((p1, p2))

    # Intersect consecutive offset edges
    result = []
    for i in range(n):
        j = (i + 1) % n
        a1, a2 = offset_edges[i]
        b1, b2 = offset_edges[j]
        pt = _line_intersect(a1, a2, b1, b2)
        if pt is not None:
            result.append(pt)
        else:
            result.append(offset_edges[j][0])

    return result if len(result) >= 3 else list(points)


from .geometry_intersect import line_line_intersection_unbounded as _line_intersect


def _scene_hit_width(item) -> float:
    sc = item.scene()
    if sc:
        views = sc.views()
        if views:
            scale = views[0].transform().m11()
            return max(4.0, 12.0 / max(scale, 1e-6))
    return 6.0


# ── RoofItem ─────────────────────────────────────────────────────────────────

from .displayable_item import DisplayableItemMixin


class RoofItem(DisplayableItemMixin, QGraphicsPathItem):
    """A roof defined by a closed boundary polygon.

    2D rendering: semi-transparent filled polygon with ridge lines.
    3D mesh: pitched or flat polygon at eave height.
    """

    def __init__(self, points: list[QPointF] | None = None,
                 color: str | QColor = "#D2B48C"):
        super().__init__()
        self._points: list[QPointF] = [QPointF(p) for p in (points or [])]
        self._color = QColor(color) if isinstance(color, str) else QColor(color)
        self._thickness_mm: float = DEFAULT_THICKNESS_MM
        self._roof_type: str = "flat"
        self._pitch_deg: float = DEFAULT_PITCH_DEG
        self._eave_height_mm: float = DEFAULT_EAVE_HEIGHT_MM
        self._overhang_mm: float = DEFAULT_OVERHANG_MM
        self._ridge_direction: str = "auto"   # "auto", "horizontal", "vertical"
        self._ridge_position: float = 0.5     # reserved for future offset

        self.init_displayable()
        self.name: str = ""

        self.setZValue(Z_ROOF)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        if len(self._points) >= 3:
            self._rebuild_path()

    # ── Point management ─────────────────────────────────────────────────

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

    def _overhang_points(self) -> list[QPointF]:
        """Return boundary expanded outward by overhang distance (scene units).

        The overhang is stored in mm; we convert to scene units using the
        scene's scale_manager if available, falling back to a stored reference.
        """
        if self._overhang_mm <= 0 or len(self._points) < 3:
            return self._points
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
        if sm is None:
            sm = self._scale_manager_ref
        if sm and sm.is_calibrated and sm.drawing_scale > 0:
            dist = sm.real_to_scene(self._overhang_mm)  # mm → scene
        else:
            dist = self._overhang_mm  # fallback: treat as scene units
        return _offset_polygon(self._points, dist)

    # ── Path rebuild (2D) ────────────────────────────────────────────────

    def _rebuild_path(self):
        path = QPainterPath()
        if len(self._points) < 2:
            self.setPath(path)
            return
        # Use overhang-expanded boundary as the actual path so the
        # bounding rect and hit-testing automatically include the overhang.
        pts = self._overhang_points()
        path.moveTo(pts[0])
        for p in pts[1:]:
            path.lineTo(p)
        if len(pts) >= 3:
            path.closeSubpath()
        self.setPath(path)

    # ── Ridge line helpers (for 2D rendering) ────────────────────────────

    def _compute_ridge_lines(self) -> list[tuple[QPointF, QPointF]]:
        """Compute ridge/hip lines for pitched roof types."""
        if len(self._points) < 3 or self._roof_type == "flat":
            return []

        # Compute centroid
        cx = sum(p.x() for p in self._points) / len(self._points)
        cy = sum(p.y() for p in self._points) / len(self._points)
        centroid = QPointF(cx, cy)

        if self._roof_type == "gable":
            return self._gable_ridge()
        elif self._roof_type == "hip":
            # Hip: lines from each vertex to centroid
            lines = []
            for p in self._points:
                lines.append((p, centroid))
            return lines
        elif self._roof_type == "shed":
            # Shed: single line along the highest edge (first edge)
            if len(self._points) >= 2:
                mid0 = QPointF(
                    (self._points[0].x() + self._points[1].x()) / 2,
                    (self._points[0].y() + self._points[1].y()) / 2,
                )
                return [(mid0, centroid)]
            return []
        return []

    def _gable_ridge_endpoints(self, pts=None):
        """Compute gable ridge endpoints based on ridge direction setting.

        Returns ((x1, y1), (x2, y2)) in the coordinate system of *pts*.
        If *pts* is None, uses self._points (QPointF).
        Also returns (eave_edge_indices, gable_edge_indices) for mesh building.
        """
        if pts is None:
            pts = self._points
            get_xy = lambda p: (p.x(), p.y())
        else:
            get_xy = lambda p: (p[0], p[1])

        n = len(pts)
        if n < 3:
            return None

        # Compute bounding box
        xs = [get_xy(p)[0] for p in pts]
        ys = [get_xy(p)[1] for p in pts]
        cx = sum(xs) / n
        cy = sum(ys) / n

        direction = self._ridge_direction

        if direction == "auto":
            # Find two longest edges; ridge runs between their midpoints
            edges = []
            for i in range(n):
                j = (i + 1) % n
                x1, y1 = get_xy(pts[i])
                x2, y2 = get_xy(pts[j])
                length = math.hypot(x2 - x1, y2 - y1)
                mx = (x1 + x2) / 2
                my = (y1 + y2) / 2
                edges.append((length, mx, my, i))
            edges.sort(key=lambda e: e[0], reverse=True)
            if len(edges) < 2:
                return None
            ridge_p1 = (edges[0][1], edges[0][2])
            ridge_p2 = (edges[1][1], edges[1][2])
            eave_indices = {edges[0][3], edges[1][3]}
        elif direction == "horizontal":
            # Ridge runs left-right (along X axis)
            # Find edges that are most horizontal (eave edges)
            ridge_p1 = (min(xs), cy)
            ridge_p2 = (max(xs), cy)
            eave_indices = set()
            for i in range(n):
                j = (i + 1) % n
                x1, y1 = get_xy(pts[i])
                x2, y2 = get_xy(pts[j])
                dx = abs(x2 - x1)
                dy = abs(y2 - y1)
                if dx > dy:  # more horizontal than vertical = eave
                    eave_indices.add(i)
        elif direction == "vertical":
            # Ridge runs top-bottom (along Y axis)
            ridge_p1 = (cx, min(ys))
            ridge_p2 = (cx, max(ys))
            eave_indices = set()
            for i in range(n):
                j = (i + 1) % n
                x1, y1 = get_xy(pts[i])
                x2, y2 = get_xy(pts[j])
                dx = abs(x2 - x1)
                dy = abs(y2 - y1)
                if dy > dx:  # more vertical than horizontal = eave
                    eave_indices.add(i)
        else:
            return None

        gable_indices = set(range(n)) - eave_indices
        return ridge_p1, ridge_p2, eave_indices, gable_indices

    def _gable_ridge(self) -> list[tuple[QPointF, QPointF]]:
        """Compute gable ridge line for 2D rendering."""
        result = self._gable_ridge_endpoints()
        if result is None:
            return []
        ridge_p1, ridge_p2, _, _ = result
        return [(QPointF(ridge_p1[0], ridge_p1[1]),
                 QPointF(ridge_p2[0], ridge_p2[1]))]

    # ── Paint ────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected

        line_col = QColor(self._display_color) if self._display_color else self._color
        pen = QPen(line_col, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)

        if self._display_fill_color:
            fill_color = QColor(self._display_fill_color)
            fill_color.setAlpha(_FILL_ALPHA)
        else:
            fill_color = QColor(self._color)
            fill_color.setAlpha(_FILL_ALPHA)
        painter.setBrush(QBrush(fill_color))

        if len(self._points) >= 3:
            # Draw the full roof boundary (includes overhang if any)
            oh_pts = self._overhang_points()
            painter.drawPolygon(QPolygonF(oh_pts))
            # If overhang is active, draw inner wall boundary as dotted line
            if oh_pts is not self._points:
                inner_pen = QPen(line_col, 1, Qt.PenStyle.DotLine)
                inner_pen.setCosmetic(True)
                painter.setPen(inner_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(QPolygonF(self._points))
                painter.setPen(pen)
        elif len(self._points) == 2:
            painter.drawLine(self._points[0], self._points[1])

        # Draw ridge/hip lines
        ridge_lines = self._compute_ridge_lines()
        if ridge_lines:
            ridge_pen = QPen(line_col, 1, Qt.PenStyle.DashDotLine)
            ridge_pen.setCosmetic(True)
            painter.setPen(ridge_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for p1, p2 in ridge_lines:
                painter.drawLine(p1, p2)

        # Selection highlight
        if self.isSelected():
            sel_pen = QPen(_SELECTION_COLOR, 2)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())

    # ── Shape / hit-test ─────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        path = self.path()
        if path.isEmpty():
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path) | path

    # ── Grip points ──────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        return [QPointF(p) for p in self._points]

    def apply_grip(self, index: int, new_pos: QPointF):
        if 0 <= index < len(self._points):
            self._points[index] = QPointF(new_pos)
            self._rebuild_path()

    def insert_point(self, idx: int, pt: QPointF):
        """Insert a vertex at position *idx*."""
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
        """Return (edge_index, distance, projection_point) for closest edge."""
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

    # ── Properties API ───────────────────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Type":         {"type": "label",     "value": "Roof"},
            "Name":         {"type": "string",    "value": self.name},
            "Colour":       {"type": "color",     "value": self._color.name()},
            "Roof Type":    {"type": "enum",      "value": self._roof_type.capitalize(),
                             "options": [t.capitalize() for t in ROOF_TYPES]},
            "Pitch":        {"type": "string",    "value": f"{self._pitch_deg}°"},
            "Eave Level":   {"type": "level_ref", "value": self.level},
            "Eave Height":  {"type": "dimension", "value": self._fmt(self._eave_height_mm),
                             "value_mm": self._eave_height_mm},
            "Overhang":     {"type": "dimension", "value": self._fmt(self._overhang_mm),
                             "value_mm": self._overhang_mm},
            "Thickness":    {"type": "dimension", "value": self._fmt(self._thickness_mm),
                             "value_mm": self._thickness_mm},
            "Points":       {"type": "label",     "value": str(len(self._points))},
            "":             {"type": "button",    "value": "Edit Roof…",
                             "callback": self._open_edit_dialog},
        }

    def _open_edit_dialog(self):
        """Open the RoofDialog to edit this roof's properties in-place."""
        from .roof_dialog import RoofDialog
        sc = self.scene()
        if sc is None:
            return

        lm = getattr(sc, "_level_manager", None)

        parent = sc.views()[0] if sc.views() else None
        dlg = RoofDialog(
            parent,
            defaults={
                "name":            self.name,
                "roof_type":       self._roof_type,
                "pitch_deg":       self._pitch_deg,
                "eave_height_mm":  self._eave_height_mm,
                "level":           self.level,
                "overhang_mm":     self._overhang_mm,
                "color":           self._color.name(),
                "ridge_direction": self._ridge_direction,
                "half_span_mm":    self.half_span_mm(),
            },
            level_manager=lm,
            scale_manager=getattr(sc, "scale_manager", None),
        )
        from PyQt6.QtWidgets import QDialog
        if dlg.exec() == QDialog.DialogCode.Accepted:
            p = dlg.get_params()
            self.name            = p["name"] or self.name
            self._roof_type      = p["roof_type"]
            self._pitch_deg      = p["pitch_deg"]
            self._eave_height_mm = p["eave_height_mm"]
            self._overhang_mm    = p["overhang_mm"]
            self._ridge_direction = p.get("ridge_direction", "auto")
            self._color          = QColor(p["color"])
            if p.get("eave_level"):
                self.level = p["eave_level"]
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
        elif key == "Roof Type":
            v = str(value).lower()
            if v in ROOF_TYPES:
                self._roof_type = v
                self._rebuild_path()
                self.update()
        elif key == "Pitch":
            try:
                self._pitch_deg = float(str(value).replace("°", ""))
                self._rebuild_path()
                self.update()
            except (ValueError, TypeError):
                pass
        elif key == "Eave Level":
            self.level = str(value)
        elif key == "Eave Height":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._eave_height_mm = parsed
        elif key == "Overhang":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._overhang_mm = max(0.0, parsed)
                self._rebuild_path()
                self.update()
        elif key == "Thickness":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._thickness_mm = parsed

    # ── Serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":            "roof",
            "points":          [[p.x(), p.y()] for p in self._points],
            "color":           self._color.name(),
            "roof_type":       self._roof_type,
            "pitch_deg":       self._pitch_deg,
            "eave_height_mm":  self._eave_height_mm,
            "overhang_mm":     self._overhang_mm,
            "thickness_mm":    self._thickness_mm,
            "ridge_direction": self._ridge_direction,
            "ridge_position":  self._ridge_position,
            "level":           self.level,
            "user_layer":      self.user_layer,
            "name":            self.name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoofItem":
        FT = 304.8
        points = [QPointF(p[0], p[1]) for p in data.get("points", [])]
        roof = cls(points=points, color=data.get("color", "#D2B48C"))
        roof._roof_type = data.get("roof_type", "flat")
        roof._pitch_deg = data.get("pitch_deg", DEFAULT_PITCH_DEG)
        # Accept new mm keys; fall back to old ft keys with conversion
        if "eave_height_mm" in data:
            roof._eave_height_mm = data["eave_height_mm"]
        elif "eave_height_ft" in data:
            roof._eave_height_mm = data["eave_height_ft"] * FT
        else:
            roof._eave_height_mm = DEFAULT_EAVE_HEIGHT_MM
        if "overhang_mm" in data:
            roof._overhang_mm = data["overhang_mm"]
        elif "overhang_ft" in data:
            roof._overhang_mm = data["overhang_ft"] * FT
        else:
            roof._overhang_mm = DEFAULT_OVERHANG_MM
        if "thickness_mm" in data:
            roof._thickness_mm = data["thickness_mm"]
        elif "thickness_ft" in data:
            roof._thickness_mm = data["thickness_ft"] * FT
        else:
            roof._thickness_mm = DEFAULT_THICKNESS_MM
        roof._ridge_direction = data.get("ridge_direction", "auto")
        roof._ridge_position = data.get("ridge_position", 0.5)
        roof.level = data.get("level", DEFAULT_LEVEL)
        roof.user_layer = data.get("user_layer", DEFAULT_USER_LAYER)
        roof.name = data.get("name", "")
        return roof

    # ── 3D mesh generation ───────────────────────────────────────────────

    def get_3d_mesh(self, level_manager=None) -> dict | None:
        """Return vertices and faces for the roof.

        Flat roofs use the same approach as FloorSlab.
        Pitched roofs raise the ridge above the eave height.
        """
        if len(self._points) < 3:
            return None

        # Level elevation (mm)
        elev_mm = 0.0
        if level_manager is not None:
            lvl = level_manager.get(self.level)
            if lvl:
                elev_mm = lvl.elevation
        eave_z = elev_mm + self._eave_height_mm
        bot_z = eave_z - self._thickness_mm

        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None

        def to_mm(pt: QPointF) -> tuple[float, float]:
            if sm and sm.is_calibrated and sm.drawing_scale > 0:
                return (sm.scene_to_real(pt.x()), -sm.scene_to_real(pt.y()))
            return (pt.x(), -pt.y())

        # Use overhang-expanded polygon for 3D eave edges
        eave_pts = self._overhang_points()
        pts_2d = [to_mm(p) for p in eave_pts]
        n = len(pts_2d)

        if self._roof_type == "flat" or self._pitch_deg == 0:
            return self._mesh_flat(pts_2d, n, eave_z, bot_z)
        elif self._roof_type == "gable":
            return self._mesh_gable(pts_2d, n, eave_z, bot_z)
        elif self._roof_type == "hip":
            return self._mesh_hip(pts_2d, n, eave_z, bot_z)
        elif self._roof_type == "shed":
            return self._mesh_shed(pts_2d, n, eave_z, bot_z)
        return self._mesh_flat(pts_2d, n, eave_z, bot_z)

    def _mesh_flat(self, pts_2d, n, top_z, bot_z) -> dict | None:
        """Flat roof — same as FloorSlab mesh."""
        tri_indices = triangulate_polygon(pts_2d)
        if not tri_indices:
            return None

        verts = []
        for x, y in pts_2d:
            verts.append([x, y, top_z])
        for x, y in pts_2d:
            verts.append([x, y, bot_z])

        faces = []
        for a, b, c in tri_indices:
            faces.append([a, b, c])
        for a, b, c in tri_indices:
            faces.append([a + n, c + n, b + n])
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

    def _mesh_gable(self, pts_2d, n, eave_z, bot_z) -> dict | None:
        """Gable roof — two sloped planes + vertical gable-end walls."""
        ridge_rise = self._ridge_rise_mm()
        result = self._gable_ridge_endpoints(pts_2d)
        if result is None:
            return self._mesh_flat(pts_2d, n, eave_z, bot_z)

        ridge_p1, ridge_p2, eave_indices, gable_indices = result
        ridge_z = eave_z + ridge_rise

        # Vertices: eave pts at eave_z, then 2 ridge pts at ridge_z
        verts = []
        for x, y in pts_2d:
            verts.append([x, y, eave_z])
        r1_idx = n      # ridge point 1
        r2_idx = n + 1  # ridge point 2
        verts.append([ridge_p1[0], ridge_p1[1], ridge_z])
        verts.append([ridge_p2[0], ridge_p2[1], ridge_z])

        faces = []

        # For each edge, determine which ridge point it's closest to
        for i in range(n):
            j = (i + 1) % n
            mx = (pts_2d[i][0] + pts_2d[j][0]) / 2
            my = (pts_2d[i][1] + pts_2d[j][1]) / 2
            d1 = math.hypot(mx - ridge_p1[0], my - ridge_p1[1])
            d2 = math.hypot(mx - ridge_p2[0], my - ridge_p2[1])

            if i in eave_indices:
                # Eave edge: sloped face from edge to ridge line
                # Triangle 1: eave_i, eave_j, nearest_ridge
                # Triangle 2: eave_i, nearest_ridge, far_ridge
                # This creates a quad from eave edge to ridge line
                near_r = r1_idx if d1 < d2 else r2_idx
                far_r = r2_idx if d1 < d2 else r1_idx
                faces.append([i, j, near_r])
                faces.append([i, near_r, far_r])
            else:
                # Gable-end edge: triangular face from edge up to
                # the nearest ridge point (vertical gable wall)
                near_r = r1_idx if d1 < d2 else r2_idx
                faces.append([i, j, near_r])

        # Bottom face
        bot_start = n + 2
        for x, y in pts_2d:
            verts.append([x, y, bot_z])
        tri_indices = triangulate_polygon(pts_2d)
        for a, b, c in tri_indices:
            faces.append([a + bot_start, c + bot_start, b + bot_start])

        # Side walls (eave to bottom)
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, j + bot_start])
            faces.append([i, j + bot_start, i + bot_start])

        return {
            "vertices": verts,
            "faces": faces,
            "color": (self._color.redF(), self._color.greenF(),
                      self._color.blueF(), 1.0),
        }

    def _mesh_hip(self, pts_2d, n, eave_z, bot_z) -> dict | None:
        """Hip roof — all edges slope up to a central peak."""
        ridge_rise = self._ridge_rise_mm()

        cx = sum(x for x, y in pts_2d) / n
        cy = sum(y for x, y in pts_2d) / n
        peak_z = eave_z + ridge_rise

        verts = []
        for x, y in pts_2d:
            verts.append([x, y, eave_z])
        # Peak vertex at index n
        verts.append([cx, cy, peak_z])

        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, n])

        # Bottom face
        bot_start = n + 1
        for x, y in pts_2d:
            verts.append([x, y, bot_z])
        tri_indices = triangulate_polygon(pts_2d)
        for a, b, c in tri_indices:
            faces.append([a + bot_start, c + bot_start, b + bot_start])

        return {
            "vertices": verts,
            "faces": faces,
            "color": (self._color.redF(), self._color.greenF(),
                      self._color.blueF(), 1.0),
        }

    def _mesh_shed(self, pts_2d, n, eave_z, bot_z) -> dict | None:
        """Shed roof — first edge is high, opposite side is at eave."""
        ridge_rise = self._ridge_rise_mm()
        high_z = eave_z + ridge_rise

        # First two vertices are high, rest are at eave
        verts = []
        for i, (x, y) in enumerate(pts_2d):
            z = high_z if i < 2 else eave_z
            verts.append([x, y, z])

        tri_indices = triangulate_polygon(pts_2d)
        if not tri_indices:
            return None

        faces = []
        for a, b, c in tri_indices:
            faces.append([a, b, c])

        # Bottom face
        bot_start = n
        for x, y in pts_2d:
            verts.append([x, y, bot_z])
        for a, b, c in tri_indices:
            faces.append([a + bot_start, c + bot_start, b + bot_start])

        # Side faces
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, j + bot_start])
            faces.append([i, j + bot_start, i + bot_start])

        return {
            "vertices": verts,
            "faces": faces,
            "color": (self._color.redF(), self._color.greenF(),
                      self._color.blueF(), 1.0),
        }

    def _ridge_rise_mm(self) -> float:
        """Compute ridge rise in mm from pitch angle.

        For gable roofs, the half-span is perpendicular to the ridge.
        """
        if self._pitch_deg <= 0 or not self._points:
            return 0.0
        xs = [p.x() for p in self._points]
        ys = [p.y() for p in self._points]
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        # Half-span is perpendicular to ridge direction
        if self._ridge_direction == "horizontal":
            half_span = h / 2  # perpendicular to horizontal ridge = vertical span
        elif self._ridge_direction == "vertical":
            half_span = w / 2  # perpendicular to vertical ridge = horizontal span
        else:
            # "auto" — use the shorter dimension as the span
            half_span = min(w, h) / 2
        # Convert scene units to mm if scale is available
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
        if sm is None:
            sm = self._scale_manager_ref
        if sm and sm.is_calibrated and sm.drawing_scale > 0:
            half_span_mm = sm.scene_to_real(half_span)
        else:
            half_span_mm = half_span
        return half_span_mm * math.tan(math.radians(self._pitch_deg))

    def half_span_mm(self) -> float:
        """Return the half-span in mm (for dialog peak height display)."""
        if not self._points:
            return 0.0
        xs = [p.x() for p in self._points]
        ys = [p.y() for p in self._points]
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        if self._ridge_direction == "horizontal":
            half_span = h / 2
        elif self._ridge_direction == "vertical":
            half_span = w / 2
        else:
            half_span = min(w, h) / 2
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
        if sm is None:
            sm = self._scale_manager_ref
        if sm and sm.is_calibrated and sm.drawing_scale > 0:
            return sm.scene_to_real(half_span)  # scene → mm
        return half_span  # fallback

