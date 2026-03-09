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

from PyQt6.QtWidgets import QGraphicsPathItem, QStyle, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QPen, QColor, QPainterPath, QBrush, QPainterPathStroker, QPolygonF,
)


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_THICKNESS_FT = 0.5     # 6 inches
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

class FloorSlab(QGraphicsPathItem):
    """A floor slab defined by a closed boundary polygon.

    2D rendering: semi-transparent filled polygon with outline.
    3D mesh: flat polygon extruded downward by ``thickness_ft``.
    """

    def __init__(self, points: list[QPointF] | None = None,
                 color: str | QColor = "#8888cc"):
        super().__init__()
        self._points: list[QPointF] = [QPointF(p) for p in (points or [])]
        self._color = QColor(color) if isinstance(color, str) else QColor(color)
        self._thickness_ft: float = DEFAULT_THICKNESS_FT

        self.level: str = "Level 1"
        self.user_layer: str = "Default"
        self.name: str = ""

        self.setZValue(-80)      # behind walls and pipes
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        if len(self._points) >= 3:
            self._rebuild_path()

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

        pen = QPen(self._color, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)

        fill_color = QColor(self._color)
        fill_color.setAlpha(_FILL_ALPHA)
        painter.setBrush(QBrush(fill_color))

        if len(self._points) >= 3:
            poly = QPolygonF(self._points)
            painter.drawPolygon(poly)
        elif len(self._points) == 2:
            painter.drawLine(self._points[0], self._points[1])

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
            "Type":          {"type": "label",  "value": "Floor Slab"},
            "Name":          {"type": "string", "value": self.name},
            "Colour":        {"type": "color",  "value": self._color.name()},
            "Thickness (ft)":{"type": "string", "value": str(self._thickness_ft)},
            "Points":        {"type": "label",  "value": str(len(self._points))},
        }

    def set_property(self, key: str, value):
        if key == "Name":
            self.name = str(value)
        elif key == "Colour":
            self._color = QColor(value)
            self.update()
        elif key == "Thickness (ft)":
            try:
                self._thickness_ft = float(value)
            except (ValueError, TypeError):
                pass

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":         "floor_slab",
            "points":       [[p.x(), p.y()] for p in self._points],
            "color":        self._color.name(),
            "thickness_ft": self._thickness_ft,
            "level":        self.level,
            "user_layer":   self.user_layer,
            "name":         self.name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FloorSlab":
        points = [QPointF(p[0], p[1]) for p in data.get("points", [])]
        slab = cls(points=points, color=data.get("color", "#8888cc"))
        slab._thickness_ft = data.get("thickness_ft", DEFAULT_THICKNESS_FT)
        slab.level = data.get("level", "Level 1")
        slab.user_layer = data.get("user_layer", "Default")
        slab.name = data.get("name", "")
        return slab

    # ── 3D mesh generation ───────────────────────────────────────────────────

    def get_3d_mesh(self, level_manager=None) -> dict | None:
        """Return vertices and faces for the flat slab.

        The slab sits at the level elevation and extends downward
        by ``thickness_ft``. Uses ear-clipping triangulation for the polygon.
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
        top_z = elev_ft * FT_TO_MM
        bot_z = top_z - self._thickness_ft * FT_TO_MM

        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None

        def to_mm(pt: QPointF) -> tuple[float, float]:
            if sm and sm.is_calibrated and sm.drawing_scale > 0:
                return (sm.scene_to_real(pt.x()), -sm.scene_to_real(pt.y()))
            return (pt.x(), -pt.y())

        pts_2d = [to_mm(p) for p in self._points]
        n = len(pts_2d)

        # Triangulate polygon (simple ear-clipping)
        tri_indices = self._triangulate(pts_2d)
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
                      self._color.blueF(), 0.5),
        }

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
        area = sum(pts[i][0] * pts[(i+1) % n][1] - pts[(i+1) % n][0] * pts[i][1]
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
                    continue  # reflex vertex

                # Check no other vertex inside this triangle
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
