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
    from wall_opening import WallOpening


# ── Constants ────────────────────────────────────────────────────────────────

THICKNESS_PRESETS_IN = [4, 6, 8, 12]           # inches
DEFAULT_THICKNESS_IN = 6

# Fill modes
FILL_NONE  = "None"
FILL_SOLID = "Solid"
FILL_HATCH = "Hatch"

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
    thickness_in: float,
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
    half_mm = (thickness_in * 25.4) / 2.0
    if (scale_manager is not None
            and scale_manager.drawing_scale > 0):
        paper_mm = half_mm / scale_manager.drawing_scale
        ht = scale_manager.paper_to_scene(paper_mm)
    else:
        ht = half_mm  # fallback: 1 px ≈ 1 mm

    if alignment == ALIGN_INTERIOR:
        off_left = QPointF(0, 0)
        off_right = QPointF(-nx * ht * 2, -ny * ht * 2)
    elif alignment == ALIGN_EXTERIOR:
        off_left = QPointF(nx * ht * 2, ny * ht * 2)
        off_right = QPointF(0, 0)
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

class WallSegment(QGraphicsPathItem):
    """A straight wall segment defined by two centerline endpoints.

    2D rendering: two parallel lines at +/- thickness/2 from the centerline,
    with optional solid fill or diagonal hatch between them.

    Properties exposed via ``get_properties()`` / ``set_property()``:
        Thickness (in), Colour, Fill Mode, Base Level, Top Level, Height (ft)
    """

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 thickness_in: float = DEFAULT_THICKNESS_IN,
                 color: str | QColor = "#cccccc"):
        super().__init__()
        self._pt1 = QPointF(pt1)
        self._pt2 = QPointF(pt2)
        self._thickness_in: float = float(thickness_in)
        self._color = QColor(color) if isinstance(color, str) else QColor(color)
        self._fill_mode: str = FILL_NONE

        # Level / height
        self.level: str = "Level 1"               # also the base level
        self._base_level: str = "Level 1"
        self._top_level: str = "Level 2"
        self._height_ft: float = 10.0              # fallback when top_level is "Custom"
        self._base_offset_ft: float = 0.0          # offset from base level elevation
        self._top_offset_ft: float = 0.0           # offset from top level elevation

        # Alignment mode (centerline / interior / exterior)
        self._alignment: str = ALIGN_CENTER

        # Wall openings (doors / windows)
        self.openings: list[WallOpening] = []

        # Cosmetic / user layer
        self.user_layer: str = "Default"
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
        return self._thickness_in

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
        """Half-thickness converted from inches to scene units.

        Uses the scene's ScaleManager (which always has valid defaults
        even before calibration: 1 px/mm, 1:100 scale).
        """
        # inches → mm: 1 in = 25.4 mm
        half_mm = (self._thickness_in * 25.4) / 2.0
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
            # Click line = left face; full thickness extends to the right
            off_left = QPointF(0, 0)
            off_right = QPointF(-nx * ht * 2, -ny * ht * 2)
        elif self._alignment == ALIGN_EXTERIOR:
            # Click line = right face; full thickness extends to the left
            off_left = QPointF(nx * ht * 2, ny * ht * 2)
            off_right = QPointF(0, 0)
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
        pen = QPen(self._color, 1)
        pen.setCosmetic(True)

        # Fill
        if self._fill_mode == FILL_SOLID:
            fill_color = QColor(self._color)
            fill_color.setAlpha(80)
            painter.setBrush(QBrush(fill_color))
        elif self._fill_mode == FILL_HATCH:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.setPen(pen)
        poly = QPolygonF([p1l, p2l, p2r, p1r])
        painter.drawPolygon(poly)

        # Hatch lines
        if self._fill_mode == FILL_HATCH:
            self._draw_hatch(painter, p1l, p1r, p2r, p2l)

        # Selection highlight
        if self.isSelected():
            sel_pen = QPen(_SELECTION_COLOR, 2)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(poly)

    def _draw_hatch(self, painter, p1l, p1r, p2r, p2l):
        """Draw diagonal hatch lines inside the wall quad."""
        pen = QPen(self._color, 0.5)
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

    def get_properties(self) -> dict:
        return {
            "Type":             {"type": "label",     "value": "Wall"},
            "Name":             {"type": "string",    "value": self.name},
            "Thickness (in)":   {"type": "string",    "value": str(self._thickness_in)},
            "Colour":           {"type": "color",     "value": self._color.name()},
            "Fill Mode":        {"type": "enum",      "value": self._fill_mode,
                                 "options": [FILL_NONE, FILL_SOLID, FILL_HATCH]},
            "Alignment":        {"type": "enum",      "value": self._alignment,
                                 "options": [ALIGN_CENTER, ALIGN_INTERIOR, ALIGN_EXTERIOR]},
            "Base Level":       {"type": "level_ref", "value": self._base_level},
            "Base Offset (ft)": {"type": "string",    "value": str(self._base_offset_ft)},
            "Top Level":        {"type": "level_ref", "value": self._top_level},
            "Top Offset (ft)":  {"type": "string",    "value": str(self._top_offset_ft)},
            "Height (ft)":      {"type": "string",    "value": str(self._height_ft)},
        }

    def set_property(self, key: str, value):
        if key == "Name":
            self.name = str(value)
        elif key == "Thickness (in)":
            try:
                self._thickness_in = float(value)
            except (ValueError, TypeError):
                return
            self._rebuild_path()
            self.update()
        elif key == "Colour":
            self._color = QColor(value)
            self.update()
        elif key == "Fill Mode":
            if value in (FILL_NONE, FILL_SOLID, FILL_HATCH):
                self._fill_mode = value
                self._rebuild_path()
                self.update()
        elif key == "Alignment":
            if value in (ALIGN_CENTER, ALIGN_INTERIOR, ALIGN_EXTERIOR):
                self._alignment = value
                self._rebuild_path()
                self.update()
        elif key == "Base Level":
            self._base_level = str(value)
        elif key == "Top Level":
            self._top_level = str(value)
        elif key == "Base Offset (ft)":
            try:
                self._base_offset_ft = float(value)
            except (ValueError, TypeError):
                pass
        elif key == "Top Offset (ft)":
            try:
                self._top_offset_ft = float(value)
            except (ValueError, TypeError):
                pass
        elif key == "Height (ft)":
            try:
                self._height_ft = float(value)
            except (ValueError, TypeError):
                pass

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        openings_data = []
        for op in self.openings:
            openings_data.append(op.to_dict())
        return {
            "type":          "wall",
            "pt1":           [self._pt1.x(), self._pt1.y()],
            "pt2":           [self._pt2.x(), self._pt2.y()],
            "thickness_in":  self._thickness_in,
            "color":         self._color.name(),
            "fill_mode":     self._fill_mode,
            "alignment":     self._alignment,
            "base_level":    self._base_level,
            "top_level":     self._top_level,
            "height_ft":     self._height_ft,
            "base_offset_ft": self._base_offset_ft,
            "top_offset_ft":  self._top_offset_ft,
            "level":         self.level,
            "user_layer":    self.user_layer,
            "name":          self.name,
            "openings":      openings_data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WallSegment":
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        wall = cls(pt1, pt2,
                   thickness_in=data.get("thickness_in", DEFAULT_THICKNESS_IN),
                   color=data.get("color", "#cccccc"))
        wall._fill_mode = data.get("fill_mode", FILL_NONE)
        wall._alignment = data.get("alignment", ALIGN_CENTER)
        wall._base_level = data.get("base_level", "Level 1")
        wall._top_level = data.get("top_level", "Level 2")
        wall._height_ft = data.get("height_ft", 10.0)
        wall._base_offset_ft = data.get("base_offset_ft", 0.0)
        wall._top_offset_ft = data.get("top_offset_ft", 0.0)
        wall.level = data.get("level", "Level 1")
        wall.user_layer = data.get("user_layer", "Default")
        wall.name = data.get("name", "")
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
        FT_TO_MM = 304.8

        # Determine base and top elevations in feet
        base_z_ft = 0.0
        top_z_ft = self._height_ft
        if level_manager is not None:
            base_lvl = level_manager.get(self._base_level)
            if base_lvl:
                base_z_ft = base_lvl.elevation + self._base_offset_ft
            top_lvl = level_manager.get(self._top_level)
            if top_lvl:
                top_z_ft = top_lvl.elevation + self._top_offset_ft
            else:
                top_z_ft = base_z_ft + self._height_ft

        base_z = base_z_ft * FT_TO_MM
        top_z = top_z_ft * FT_TO_MM
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

    def mitered_quad(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
        """Return quad_points adjusted for miter joins at connected endpoints.

        At each endpoint, if exactly one other wall shares the same point
        the left/right corner vertices are moved to the intersection of
        the two walls' corresponding side edges, producing a clean miter.
        """
        p1l, p1r, p2r, p2l = self.quad_points()

        sc = self.scene()
        if sc is None or not hasattr(sc, '_walls'):
            return (p1l, p1r, p2r, p2l)

        MITER_TOL = 1.0  # scene units — tight, walls are snapped exactly
        MAX_MITER = self.half_thickness_scene() * 4

        for my_idx in (0, 1):
            my_pt = self._pt1 if my_idx == 0 else self._pt2
            for other in sc._walls:
                if other is self:
                    continue
                other_ep = other.endpoint_near(my_pt, MITER_TOL)
                if other_ep is None:
                    continue

                o_p1l, o_p1r, o_p2r, o_p2l = other.quad_points()

                # Same endpoint index → cross pairing, different → parallel
                cross = (my_idx == other_ep)
                if cross:
                    left_target = (o_p1r, o_p2r)   # my left ∩ other right
                    right_target = (o_p1l, o_p2l)   # my right ∩ other left
                else:
                    left_target = (o_p1l, o_p2l)    # my left ∩ other left
                    right_target = (o_p1r, o_p2r)   # my right ∩ other right

                int_l = self._intersect_lines(p1l, p2l,
                                              left_target[0], left_target[1])
                int_r = self._intersect_lines(p1r, p2r,
                                              right_target[0], right_target[1])

                if int_l is not None and int_r is not None:
                    # Guard: skip if miter extends too far (very acute angle)
                    dist_l = math.hypot(int_l.x() - my_pt.x(),
                                        int_l.y() - my_pt.y())
                    dist_r = math.hypot(int_r.x() - my_pt.x(),
                                        int_r.y() - my_pt.y())
                    if dist_l < MAX_MITER and dist_r < MAX_MITER:
                        if my_idx == 0:
                            p1l, p1r = int_l, int_r
                        else:
                            p2l, p2r = int_l, int_r
                break  # one miter partner per endpoint

        return (p1l, p1r, p2r, p2l)

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
