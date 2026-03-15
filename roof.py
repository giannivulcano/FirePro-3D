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

from PyQt6.QtWidgets import QGraphicsPathItem, QStyle, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QPen, QColor, QPainterPath, QBrush, QPainterPathStroker, QPolygonF,
)

from constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER, Z_ROOF

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_THICKNESS_FT = 0.5      # 6 inches
DEFAULT_PITCH_DEG = 0.0         # flat by default
DEFAULT_EAVE_HEIGHT_FT = 10.0   # eave above level datum
DEFAULT_OVERHANG_FT = 0.0       # no overhang by default
_FILL_ALPHA = 40                # semi-transparent fill in 2D
_SELECTION_COLOR = QColor("red")

ROOF_TYPES = ("flat", "gable", "hip", "shed")


def _scene_hit_width(item) -> float:
    sc = item.scene()
    if sc:
        views = sc.views()
        if views:
            scale = views[0].transform().m11()
            return max(4.0, 12.0 / max(scale, 1e-6))
    return 6.0


# ── RoofItem ─────────────────────────────────────────────────────────────────

class RoofItem(QGraphicsPathItem):
    """A roof defined by a closed boundary polygon.

    2D rendering: semi-transparent filled polygon with ridge lines.
    3D mesh: pitched or flat polygon at eave height.
    """

    def __init__(self, points: list[QPointF] | None = None,
                 color: str | QColor = "#D2B48C"):
        super().__init__()
        self._points: list[QPointF] = [QPointF(p) for p in (points or [])]
        self._color = QColor(color) if isinstance(color, str) else QColor(color)
        self._thickness_ft: float = DEFAULT_THICKNESS_FT
        self._roof_type: str = "flat"
        self._pitch_deg: float = DEFAULT_PITCH_DEG
        self._eave_height_ft: float = DEFAULT_EAVE_HEIGHT_FT
        self._overhang_ft: float = DEFAULT_OVERHANG_FT

        self.level: str = DEFAULT_LEVEL
        self.user_layer: str = DEFAULT_USER_LAYER
        self.name: str = ""

        # Display Manager overrides
        self._display_color: str | None = None
        self._display_fill_color: str | None = None
        self._display_overrides: dict = {}

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

    # ── Path rebuild (2D) ────────────────────────────────────────────────

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

    def _gable_ridge(self) -> list[tuple[QPointF, QPointF]]:
        """Compute gable ridge line along the longest axis."""
        if len(self._points) < 4:
            # For triangles, draw from midpoint of longest edge to opposite vertex
            cx = sum(p.x() for p in self._points) / len(self._points)
            cy = sum(p.y() for p in self._points) / len(self._points)
            return [(QPointF(cx, cy), QPointF(cx, cy))]

        # Find the two longest parallel-ish edges and draw ridge between midpoints
        n = len(self._points)
        edges = []
        for i in range(n):
            j = (i + 1) % n
            dx = self._points[j].x() - self._points[i].x()
            dy = self._points[j].y() - self._points[i].y()
            length = math.hypot(dx, dy)
            mid = QPointF(
                (self._points[i].x() + self._points[j].x()) / 2,
                (self._points[i].y() + self._points[j].y()) / 2,
            )
            edges.append((length, mid, i))

        # Sort by length descending, take midpoints of two longest edges
        edges.sort(key=lambda e: e[0], reverse=True)
        if len(edges) >= 2:
            return [(edges[0][1], edges[1][1])]
        return []

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
            poly = QPolygonF(self._points)
            painter.drawPolygon(poly)
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
            if len(self._points) >= 3:
                painter.drawPolygon(QPolygonF(self._points))

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
            "Type":             {"type": "label",  "value": "Roof"},
            "Name":             {"type": "string", "value": self.name},
            "Colour":           {"type": "color",  "value": self._color.name()},
            "Roof Type":        {"type": "combo",  "value": self._roof_type,
                                 "options": list(ROOF_TYPES)},
            "Pitch (deg)":      {"type": "string", "value": str(self._pitch_deg)},
            "Eave Height (ft)": {"type": "string", "value": str(self._eave_height_ft)},
            "Overhang (ft)":    {"type": "string", "value": str(self._overhang_ft)},
            "Thickness (ft)":   {"type": "string", "value": str(self._thickness_ft)},
            "Points":           {"type": "label",  "value": str(len(self._points))},
        }

    def set_property(self, key: str, value):
        if key == "Name":
            self.name = str(value)
        elif key == "Colour":
            self._color = QColor(value)
            self.update()
        elif key == "Roof Type":
            if value in ROOF_TYPES:
                self._roof_type = value
                self.update()
        elif key == "Pitch (deg)":
            try:
                self._pitch_deg = float(value)
            except (ValueError, TypeError):
                pass
        elif key == "Eave Height (ft)":
            try:
                self._eave_height_ft = float(value)
            except (ValueError, TypeError):
                pass
        elif key == "Overhang (ft)":
            try:
                self._overhang_ft = max(0.0, float(value))
            except (ValueError, TypeError):
                pass
        elif key == "Thickness (ft)":
            try:
                self._thickness_ft = float(value)
            except (ValueError, TypeError):
                pass

    # ── Serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":            "roof",
            "points":          [[p.x(), p.y()] for p in self._points],
            "color":           self._color.name(),
            "roof_type":       self._roof_type,
            "pitch_deg":       self._pitch_deg,
            "eave_height_ft":  self._eave_height_ft,
            "overhang_ft":     self._overhang_ft,
            "thickness_ft":    self._thickness_ft,
            "level":           self.level,
            "user_layer":      self.user_layer,
            "name":            self.name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoofItem":
        points = [QPointF(p[0], p[1]) for p in data.get("points", [])]
        roof = cls(points=points, color=data.get("color", "#D2B48C"))
        roof._roof_type = data.get("roof_type", "flat")
        roof._pitch_deg = data.get("pitch_deg", DEFAULT_PITCH_DEG)
        roof._eave_height_ft = data.get("eave_height_ft", DEFAULT_EAVE_HEIGHT_FT)
        roof._overhang_ft = data.get("overhang_ft", DEFAULT_OVERHANG_FT)
        roof._thickness_ft = data.get("thickness_ft", DEFAULT_THICKNESS_FT)
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

        FT_TO_MM = 304.8

        # Level elevation
        elev_ft = 0.0
        if level_manager is not None:
            lvl = level_manager.get(self.level)
            if lvl:
                elev_ft = lvl.elevation
        eave_z = (elev_ft + self._eave_height_ft) * FT_TO_MM
        bot_z = eave_z - self._thickness_ft * FT_TO_MM

        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None

        def to_mm(pt: QPointF) -> tuple[float, float]:
            if sm and sm.is_calibrated and sm.drawing_scale > 0:
                return (sm.scene_to_real(pt.x()), -sm.scene_to_real(pt.y()))
            return (pt.x(), -pt.y())

        pts_2d = [to_mm(p) for p in self._points]
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
        tri_indices = self._triangulate(pts_2d)
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
                      self._color.blueF(), 0.5),
        }

    def _mesh_gable(self, pts_2d, n, eave_z, bot_z) -> dict | None:
        """Gable roof — raised ridge along longest axis."""
        ridge_rise = self._ridge_rise_mm()

        # Find two longest edges and their midpoints
        edges = []
        for i in range(n):
            j = (i + 1) % n
            dx = pts_2d[j][0] - pts_2d[i][0]
            dy = pts_2d[j][1] - pts_2d[i][1]
            length = math.hypot(dx, dy)
            mx = (pts_2d[i][0] + pts_2d[j][0]) / 2
            my = (pts_2d[i][1] + pts_2d[j][1]) / 2
            edges.append((length, mx, my, i))
        edges.sort(key=lambda e: e[0], reverse=True)

        if len(edges) < 2:
            return self._mesh_flat(pts_2d, n, eave_z, bot_z)

        # Ridge endpoints at midpoints of two longest edges
        ridge_p1 = (edges[0][1], edges[0][2])
        ridge_p2 = (edges[1][1], edges[1][2])
        ridge_z = eave_z + ridge_rise

        # Build mesh: eave vertices + 2 ridge vertices
        verts = []
        for x, y in pts_2d:
            verts.append([x, y, eave_z])
        # Ridge vertices at indices n and n+1
        verts.append([ridge_p1[0], ridge_p1[1], ridge_z])
        verts.append([ridge_p2[0], ridge_p2[1], ridge_z])

        # Triangulate each face from eave edge to ridge
        faces = []
        for i in range(n):
            j = (i + 1) % n
            # Connect each eave edge to nearest ridge point
            faces.append([i, j, n])      # to ridge point 1
            faces.append([i, j, n + 1])  # to ridge point 2

        # Bottom face (flat)
        bot_start = n + 2
        for x, y in pts_2d:
            verts.append([x, y, bot_z])
        tri_indices = self._triangulate(pts_2d)
        for a, b, c in tri_indices:
            faces.append([a + bot_start, c + bot_start, b + bot_start])

        return {
            "vertices": verts,
            "faces": faces,
            "color": (self._color.redF(), self._color.greenF(),
                      self._color.blueF(), 0.5),
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
        tri_indices = self._triangulate(pts_2d)
        for a, b, c in tri_indices:
            faces.append([a + bot_start, c + bot_start, b + bot_start])

        return {
            "vertices": verts,
            "faces": faces,
            "color": (self._color.redF(), self._color.greenF(),
                      self._color.blueF(), 0.5),
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

        tri_indices = self._triangulate(pts_2d)
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
                      self._color.blueF(), 0.5),
        }

    def _ridge_rise_mm(self) -> float:
        """Compute ridge rise in mm from pitch angle."""
        FT_TO_MM = 304.8
        if self._pitch_deg <= 0:
            return 0.0
        # Estimate half-span from polygon bounding box
        if not self._points:
            return 0.0
        xs = [p.x() for p in self._points]
        ys = [p.y() for p in self._points]
        half_span = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
        # Convert scene units to mm if scale is available
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
        if sm and sm.is_calibrated and sm.drawing_scale > 0:
            half_span_mm = sm.scene_to_real(half_span)
        else:
            half_span_mm = half_span
        return half_span_mm * math.tan(math.radians(self._pitch_deg))

    @staticmethod
    def _triangulate(pts: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
        """Simple ear-clipping triangulation for a simple polygon."""
        n = len(pts)
        if n < 3:
            return []

        indices = list(range(n))
        triangles = []

        def cross(o, a, b):
            return (pts[a][0] - pts[o][0]) * (pts[b][1] - pts[o][1]) - \
                   (pts[a][1] - pts[o][1]) * (pts[b][0] - pts[o][0])

        def point_in_triangle(px, py, ax, ay, bx, by, cx, cy):
            d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
            d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
            d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
            has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
            has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
            return not (has_neg and has_pos)

        # Ensure CCW winding
        area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                   for i in range(n))
        if area < 0:
            indices = indices[::-1]

        attempts = 0
        max_attempts = n * n
        while len(indices) > 2 and attempts < max_attempts:
            attempts += 1
            found_ear = False
            m = len(indices)
            for i in range(m):
                prev_idx = indices[(i - 1) % m]
                curr_idx = indices[i]
                next_idx = indices[(i + 1) % m]

                if cross(prev_idx, curr_idx, next_idx) <= 0:
                    continue

                is_ear = True
                ax, ay = pts[prev_idx]
                bx, by = pts[curr_idx]
                cx, cy = pts[next_idx]
                for j in range(m):
                    if j in (i, (i - 1) % m, (i + 1) % m):
                        continue
                    px, py = pts[indices[j]]
                    if point_in_triangle(px, py, ax, ay, bx, by, cx, cy):
                        is_ear = False
                        break

                if is_ear:
                    triangles.append((prev_idx, curr_idx, next_idx))
                    indices.pop(i)
                    found_ear = True
                    break

            if not found_ear:
                break

        return triangles
