"""
view_cube.py
============
Interactive ViewCube widget for FireFlow Pro's 3D viewport.

Renders a small wireframe cube (Revit / AutoCAD / SolidWorks style) that
rotates to match the current camera orientation.  Clicking a face, edge,
or corner snaps the camera to the corresponding standard engineering view.

The cube is drawn with QPainter on a transparent overlay widget that sits
in the top-right corner of the 3D canvas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPolygonF,
    QPainterPath, QMouseEvent, QFontMetrics,
)


# ─────────────────────────────────────────────────────────────────────────────
# 3×3 rotation helpers (no numpy dependency for the overlay widget)
# ─────────────────────────────────────────────────────────────────────────────

def _rot_x(deg: float) -> list[list[float]]:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]

def _rot_y(deg: float) -> list[list[float]]:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]

def _rot_z(deg: float) -> list[list[float]]:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]

def _mat_mul(a, b):
    """Multiply two 3×3 matrices."""
    return [
        [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]

def _mat_vec(m, v):
    """Multiply 3×3 matrix × 3-vector."""
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


# ─────────────────────────────────────────────────────────────────────────────
# Cube geometry
# ─────────────────────────────────────────────────────────────────────────────

# Unit cube vertices (±1) — indices 0-7
_CUBE_VERTS = [
    (-1, -1, -1),  # 0  back-bottom-left
    ( 1, -1, -1),  # 1  back-bottom-right
    ( 1,  1, -1),  # 2  back-top-right
    (-1,  1, -1),  # 3  back-top-left
    (-1, -1,  1),  # 4  front-bottom-left
    ( 1, -1,  1),  # 5  front-bottom-right
    ( 1,  1,  1),  # 6  front-top-right
    (-1,  1,  1),  # 7  front-top-left
]

# Faces: (vertex_indices, label, normal, elevation, azimuth)
# The normal is used for back-face culling; elev/azim are the camera preset.
_CUBE_FACES = [
    # face verts        label     normal        elev  azim
    ([4, 5, 6, 7],     "FRONT",  ( 0,  0,  1),   0,    0),
    ([1, 0, 3, 2],     "BACK",   ( 0,  0, -1),   0,  180),
    ([5, 1, 2, 6],     "RIGHT",  ( 1,  0,  0),   0,   90),
    ([0, 4, 7, 3],     "LEFT",   (-1,  0,  0),   0,  -90),
    ([7, 6, 2, 3],     "TOP",    ( 0,  1,  0),  90,    0),
    ([0, 1, 5, 4],     "BOTTOM", ( 0, -1,  0), -90,    0),
]

# Edges: pairs of vertex indices + (elevation, azimuth) for the diagonal view
# Only named edges that correspond to useful views
_CUBE_EDGES = [
    # Top edges
    ([7, 6], "top-front",   45,   0),
    ([3, 2], "top-back",    45, 180),
    ([6, 2], "top-right",   45,  90),
    ([7, 3], "top-left",    45, -90),
    # Bottom edges
    ([4, 5], "bot-front",  -45,   0),
    ([0, 1], "bot-back",   -45, 180),
    ([5, 1], "bot-right",  -45,  90),
    ([0, 4], "bot-left",   -45, -90),
    # Vertical edges
    ([4, 7], "front-left",   0, -45),
    ([5, 6], "front-right",  0,  45),
    ([0, 3], "back-left",    0,-135),
    ([1, 2], "back-right",   0, 135),
]

# Corners: vertex index + (elevation, azimuth)
_CUBE_CORNERS = [
    (7, "top-front-left",    35, -45),
    (6, "top-front-right",   35,  45),
    (3, "top-back-left",     35,-135),
    (2, "top-back-right",    35, 135),
    (4, "bot-front-left",   -35, -45),
    (5, "bot-front-right",  -35,  45),
    (0, "bot-back-left",    -35,-135),
    (1, "bot-back-right",   -35, 135),
]

# Colors
_COL_FACE        = QColor(60, 63, 70, 180)
_COL_FACE_HOVER  = QColor(80, 130, 200, 200)
_COL_EDGE        = QColor(140, 145, 155, 220)
_COL_EDGE_HOVER  = QColor(100, 170, 255, 255)
_COL_LABEL       = QColor(220, 225, 230)
_COL_OUTLINE     = QColor(90, 95, 105, 200)
_COL_COMPASS     = QColor(180, 185, 195, 160)


# ─────────────────────────────────────────────────────────────────────────────
# Hit zone data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _HitZone:
    kind: str        # "face" | "edge" | "corner"
    index: int       # into _CUBE_FACES / _CUBE_EDGES / _CUBE_CORNERS
    polygon: QPolygonF
    elev: float
    azim: float
    label: str


# ─────────────────────────────────────────────────────────────────────────────
# ViewCube widget
# ─────────────────────────────────────────────────────────────────────────────

class ViewCube(QWidget):
    """Small interactive orientation cube drawn as a QPainter overlay."""

    viewRequested = pyqtSignal(float, float)  # (elevation, azimuth)

    CUBE_SIZE = 100   # widget extent in pixels (cube drawn inside this)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.CUBE_SIZE + 30, self.CUBE_SIZE + 30)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._elevation = 30.0
        self._azimuth = 45.0
        self._hover_zone: _HitZone | None = None
        self._hit_zones: list[_HitZone] = []

    # ── Public API ──────────────────────────────────────────────────────────

    def set_camera_angles(self, elevation: float, azimuth: float):
        """Update the cube orientation to match the camera."""
        if abs(self._elevation - elevation) > 0.1 or abs(self._azimuth - azimuth) > 0.1:
            self._elevation = elevation
            self._azimuth = azimuth
            self.update()

    # ── Projection ──────────────────────────────────────────────────────────

    def _build_rotation(self):
        """Build the view rotation matrix from elevation and azimuth.

        Convention (matching vispy TurntableCamera):
        - Azimuth rotates around Y (vertical world axis)
        - Elevation tilts up/down
        """
        # Rotate around Y by -azimuth, then around X by -elevation
        ry = _rot_y(-self._azimuth)
        rx = _rot_x(-self._elevation)
        return _mat_mul(rx, ry)

    def _project(self, v, rot, cx, cy, scale):
        """Project a 3D point to 2D screen coords using orthographic projection."""
        rv = _mat_vec(rot, v)
        # Orthographic: just take x, y (Z is depth for sorting)
        return QPointF(cx + rv[0] * scale, cy - rv[1] * scale), rv[2]

    # ── Paint ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        scale = self.CUBE_SIZE * 0.34

        rot = self._build_rotation()
        self._hit_zones.clear()

        # ── Project all cube vertices ────────────────────────────────────
        proj_pts: list[tuple[QPointF, float]] = []
        for v in _CUBE_VERTS:
            pt, depth = self._project(v, rot, cx, cy, scale)
            proj_pts.append((pt, depth))

        # ── Draw faces (sorted back-to-front by average depth) ───────────
        face_order: list[tuple[float, int]] = []
        for fi, (verts, label, normal, elev, azim) in enumerate(_CUBE_FACES):
            avg_z = sum(proj_pts[vi][1] for vi in verts) / len(verts)
            face_order.append((avg_z, fi))
        face_order.sort(key=lambda x: x[0])  # back-to-front (lowest Z first)

        for _, fi in face_order:
            verts, label, normal, elev, azim = _CUBE_FACES[fi]

            # Back-face cull: dot(normal, view_direction)
            rn = _mat_vec(rot, normal)
            if rn[2] < -0.05:
                continue  # facing away

            poly = QPolygonF([proj_pts[vi][0] for vi in verts])

            is_hover = (self._hover_zone is not None
                        and self._hover_zone.kind == "face"
                        and self._hover_zone.index == fi)

            # Fill face
            fill = _COL_FACE_HOVER if is_hover else _COL_FACE
            p.setBrush(QBrush(fill))
            p.setPen(QPen(_COL_OUTLINE, 1.2))
            p.drawPolygon(poly)

            # Label on front-facing faces
            if rn[2] > 0.3:
                center = QPointF(
                    sum(proj_pts[vi][0].x() for vi in verts) / 4,
                    sum(proj_pts[vi][0].y() for vi in verts) / 4,
                )
                font = QFont()
                font_size = 8 if len(label) <= 5 else 7
                font.setPointSize(font_size)
                font.setBold(True)
                p.setFont(font)
                col = QColor(255, 255, 255) if is_hover else _COL_LABEL
                p.setPen(col)
                fm = QFontMetrics(font)
                tw = fm.horizontalAdvance(label)
                th = fm.height()
                p.drawText(QPointF(center.x() - tw / 2, center.y() + th / 4), label)

            # Store hit zone
            hz = _HitZone("face", fi, poly, elev, azim, label)
            self._hit_zones.append(hz)

        # ── Draw edges as thick hover-able lines ─────────────────────────
        for ei, (v_pair, name, elev, azim) in enumerate(_CUBE_EDGES):
            p0 = proj_pts[v_pair[0]][0]
            p1 = proj_pts[v_pair[1]][0]
            mid_z = (proj_pts[v_pair[0]][1] + proj_pts[v_pair[1]][1]) / 2

            # Only draw if edge is somewhat visible (facing us)
            # Check midpoint normal (average of adjacent face normals)
            if mid_z < -0.5:
                continue

            is_hover = (self._hover_zone is not None
                        and self._hover_zone.kind == "edge"
                        and self._hover_zone.index == ei)

            pen_col = _COL_EDGE_HOVER if is_hover else _COL_EDGE
            pen_w = 4.0 if is_hover else 1.5
            p.setPen(QPen(pen_col, pen_w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(p0, p1)

            # Build a thin polygon around the edge for hit testing
            dx = p1.x() - p0.x()
            dy = p1.y() - p0.y()
            ln = math.sqrt(dx * dx + dy * dy)
            if ln > 1:
                nx, ny = -dy / ln * 5, dx / ln * 5
                edge_poly = QPolygonF([
                    QPointF(p0.x() + nx, p0.y() + ny),
                    QPointF(p1.x() + nx, p1.y() + ny),
                    QPointF(p1.x() - nx, p1.y() - ny),
                    QPointF(p0.x() - nx, p0.y() - ny),
                ])
                self._hit_zones.append(
                    _HitZone("edge", ei, edge_poly, elev, azim, name)
                )

        # ── Draw corner dots ─────────────────────────────────────────────
        for ci, (vi, name, elev, azim) in enumerate(_CUBE_CORNERS):
            pt = proj_pts[vi][0]
            depth = proj_pts[vi][1]
            if depth < -0.3:
                continue  # behind

            is_hover = (self._hover_zone is not None
                        and self._hover_zone.kind == "corner"
                        and self._hover_zone.index == ci)

            r = 5.0 if is_hover else 3.0
            col = _COL_EDGE_HOVER if is_hover else _COL_EDGE
            p.setBrush(QBrush(col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(pt, r, r)

            # Hit zone (circle approximated as 8-sided polygon)
            hit_r = 8.0
            corner_poly = QPolygonF()
            for k in range(8):
                a = 2 * math.pi * k / 8
                corner_poly.append(QPointF(
                    pt.x() + hit_r * math.cos(a),
                    pt.y() + hit_r * math.sin(a),
                ))
            self._hit_zones.append(
                _HitZone("corner", ci, corner_poly, elev, azim, name)
            )

        # ── Compass directions ───────────────────────────────────────────
        compass_r = self.CUBE_SIZE * 0.46
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)

        # N/S/E/W mapped through azimuth rotation
        for lbl, angle_deg in [("N", 0), ("E", 90), ("S", 180), ("W", 270)]:
            a = math.radians(angle_deg - self._azimuth)
            tx = cx + compass_r * math.sin(a)
            ty = cy + compass_r * math.cos(a)  # Y inverted for screen
            tw = fm.horizontalAdvance(lbl)
            th = fm.height()
            p.setPen(_COL_COMPASS)
            p.drawText(QPointF(tx - tw / 2, ty + th / 4), lbl)

        p.end()

    # ── Mouse handling ──────────────────────────────────────────────────────

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        old = self._hover_zone
        self._hover_zone = self._hit_test(pos)
        if self._hover_zone != old:
            if self._hover_zone is not None:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            hz = self._hit_test(pos)
            if hz is not None:
                self.viewRequested.emit(hz.elev, hz.azim)

    def leaveEvent(self, event):
        if self._hover_zone is not None:
            self._hover_zone = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def _hit_test(self, pos: QPointF) -> _HitZone | None:
        """Find the topmost hit zone under *pos*.

        Iterate in reverse (last painted = on top) and prioritise
        corners > edges > faces so small targets are easily clickable.
        """
        corners = []
        edges = []
        faces = []
        for hz in reversed(self._hit_zones):
            if hz.polygon.containsPoint(pos, Qt.FillRule.WindingFill):
                if hz.kind == "corner":
                    corners.append(hz)
                elif hz.kind == "edge":
                    edges.append(hz)
                else:
                    faces.append(hz)

        # Priority: corner > edge > face
        if corners:
            return corners[0]
        if edges:
            return edges[0]
        if faces:
            return faces[0]
        return None
