"""
section_marker.py
=================
Elevation (and future section) view markers for the 2D Model plan view.

All four elevation markers (N/S/E/W) share a **single bounding rectangle**.
Each triangle sits at the midpoint of one side of that rectangle.
When any marker is selected, the shared crop box appears with grip handles
for resizing.  The crop box defines the visible extent for all elevation views.

Designed to be reusable for section views (view_type="section" + angle).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsItem,
    QStyle,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QPolygonF, QFont, QPainter, QPainterPath,
)

from .constants import DEFAULT_LEVEL, Z_OVERLAY
from .gridline import BUBBLE_RADIUS_MM, GRID_COLOR

if TYPE_CHECKING:
    from .model_space import Model_Space


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Triangle size = 3× the gridline bubble diameter
MARKER_SIZE = BUBBLE_RADIUS_MM * 6.0   # ~1219mm — matches 3× bubble size
CROP_MARGIN = 2000.0                   # plan-scene units (mm at ppm 1) — default crop box padding

MIN_CUT_LEN = 100.0          # plan-scene units (mm at ppm 1) -- shorter cuts are refused at placement (spec s9)
FALLBACK_HALF = 10000.0      # plan-scene units (mm at ppm 1) -- auto-extent box when the project is empty (spec s13)

ZONE_CUT = "cut"
ZONE_BEHIND = "behind"
ZONE_HIDDEN = "hidden"


@dataclass(frozen=True)
class SectionBasis:
    """Origin-free oblique basis of one section (spec s4.1), world mm.

    ``h(p) = p . D`` (along the cut, no origin term so cardinals match the
    retired ``_world_to_elev`` bit for bit), ``d(p) = (p - A) . N`` (signed
    distance from the cut line, + on the look side), ``v = -z``.
    """

    ax: float
    ay: float
    dx: float
    dy: float
    nx: float
    ny: float
    length: float
    depth: float

    @classmethod
    def from_cut(cls, a, b, look_sign: int, depth_mm: float) -> "SectionBasis":
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        length = math.hypot(bx - ax, by - ay)
        if length <= 0.0 or depth_mm <= 0.0:
            raise ValueError("degenerate section: zero cut length or depth")
        dx, dy = (bx - ax) / length, (by - ay) / length
        s = 1 if look_sign >= 0 else -1
        return cls(ax, ay, dx, dy, s * -dy, s * dx, length, float(depth_mm))

    # -- projection --------------------------------------------------------
    def h(self, x: float, y: float) -> float:
        return x * self.dx + y * self.dy

    def d(self, x: float, y: float) -> float:
        return (x - self.ax) * self.nx + (y - self.ay) * self.ny

    def project(self, x: float, y: float, z: float) -> tuple[float, float]:
        return self.h(x, y), -z

    def sort_key(self, x: float, y: float) -> float:
        """Ascending sort = farthest first (today's ``_assign_depth_z_values``)."""
        return -self.d(x, y)

    @property
    def h_a(self) -> float:
        return self.h(self.ax, self.ay)

    @property
    def h_b(self) -> float:
        return self.h(self.ax + self.dx * self.length, self.ay + self.dy * self.length)

    @property
    def h_min(self) -> float:
        return min(self.h_a, self.h_b)

    @property
    def h_max(self) -> float:
        return max(self.h_a, self.h_b)

    # -- classification (spec s4.2) ------------------------------------------
    def _in_box(self, h: float, d: float, eps: float = 1e-9) -> bool:
        return (self.h_min - eps <= h <= self.h_max + eps
                and -eps <= d <= self.depth + eps)

    def _cut_params(self, p, q) -> list[float]:
        """Params t in [0, 1] along p->q where the segment meets the cut
        segment A->B; a collinear overlap returns its two end params."""
        d1, d2 = self.d(*p), self.d(*q)
        h1, h2 = self.h(*p), self.h(*q)
        eps = 1e-9
        if abs(d1) <= eps and abs(d2) <= eps:                 # collinear
            lo, hi = sorted((h1, h2))
            ov_lo, ov_hi = max(lo, self.h_min), min(hi, self.h_max)
            if ov_lo > ov_hi + eps:
                return []
            if abs(h2 - h1) <= eps:
                return [0.0] if self._in_box(h1, 0.0) else []
            return sorted(((ov_lo - h1) / (h2 - h1), (ov_hi - h1) / (h2 - h1)))
        if (d1 > eps and d2 > eps) or (d1 < -eps and d2 < -eps):
            return []
        t = d1 / (d1 - d2)
        h = h1 + t * (h2 - h1)
        return [t] if self.h_min - eps <= h <= self.h_max + eps else []

    def classify_segment(self, p, q):
        """``(zone, h_at_cut, t_at_cut)`` for a segment footprint (pipe)."""
        ts = self._cut_params(p, q)
        if ts:
            t = sum(ts) / len(ts)                      # overlap midpoint when collinear
            x = p[0] + t * (q[0] - p[0])
            y = p[1] + t * (q[1] - p[1])
            return ZONE_CUT, self.h(x, y), t
        if self._segment_meets_box(p, q):
            return ZONE_BEHIND, None, None
        return ZONE_HIDDEN, None, None

    def _segment_meets_box(self, p, q) -> bool:
        """Liang-Barsky clip of p->q against the (h, d) box."""
        h1, d1, h2, d2 = self.h(*p), self.d(*p), self.h(*q), self.d(*q)
        t0, t1 = 0.0, 1.0
        for dp, lo, hi in ((h2 - h1, self.h_min - h1, self.h_max - h1),
                           (d2 - d1, 0.0 - d1, self.depth - d1)):
            if abs(dp) < 1e-12:
                if lo > 0.0 or hi < 0.0:
                    return False
                continue
            ta, tb = lo / dp, hi / dp
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
            if t0 > t1:
                return False
        return True

    def classify_polygon(self, pts):
        """``(zone, h_lo, h_hi)`` for a closed footprint (wall quad, slab)."""
        n = len(pts)
        if n < 3:
            return ZONE_HIDDEN, None, None
        poly = QPolygonF([QPointF(x, y) for x, y in pts])
        hs = []
        for i in range(n):
            p, q = pts[i], pts[(i + 1) % n]
            for t in self._cut_params(p, q):
                hs.append(self.h(p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        a = QPointF(self.ax, self.ay)
        b = QPointF(self.ax + self.dx * self.length, self.ay + self.dy * self.length)
        for end, h_end in ((a, self.h_a), (b, self.h_b)):
            if poly.containsPoint(end, Qt.FillRule.OddEvenFill):
                hs.append(h_end)
        if hs:
            return ZONE_CUT, min(hs), max(hs)
        # Behind: footprint meets the box. Vertex in box, box corner in
        # footprint, or an edge crossing a box edge.
        if any(self._in_box(self.h(x, y), self.d(x, y)) for x, y in pts):
            return ZONE_BEHIND, None, None
        corners = self._box_corners()
        if any(poly.containsPoint(QPointF(cx, cy), Qt.FillRule.OddEvenFill) for cx, cy in corners):
            return ZONE_BEHIND, None, None
        for i in range(n):
            if self._segment_meets_box(pts[i], pts[(i + 1) % n]):
                return ZONE_BEHIND, None, None
        return ZONE_HIDDEN, None, None

    def _box_corners(self):
        a = (self.ax, self.ay)
        b = (self.ax + self.dx * self.length, self.ay + self.dy * self.length)
        far = (self.nx * self.depth, self.ny * self.depth)
        return [a, b, (b[0] + far[0], b[1] + far[1]), (a[0] + far[0], a[1] + far[1])]

    def classify_point(self, p) -> str:
        """Points (nodes) are never cut (spec s4.2)."""
        return ZONE_BEHIND if self._in_box(self.h(*p), self.d(*p)) else ZONE_HIDDEN


def building_bbox(model_space) -> QRectF:
    """Plan-scene bbox of gridlines and every displayable item, plus
    ``CROP_MARGIN`` (spec s4.3). Empty project -> the +/-FALLBACK_HALF box."""
    rect = QRectF()
    lists = (getattr(model_space, "_gridlines", []), getattr(model_space, "_walls", []),
             getattr(model_space, "_floor_slabs", []), getattr(model_space, "_roofs", []),
             getattr(model_space, "_rooms", []), getattr(model_space, "_block_instances", []))
    ss = getattr(model_space, "sprinkler_system", None)
    if ss is not None:
        lists = lists + (list(ss.nodes), list(ss.pipes))
    for items in lists:
        for it in items:
            try:
                r = it.sceneBoundingRect()
            except RuntimeError:          # deleted C++ object
                continue
            if r.isNull():
                continue
            rect = r if rect.isNull() else rect.united(r)
    if rect.isNull():
        rect = QRectF(-FALLBACK_HALF, -FALLBACK_HALF, 2 * FALLBACK_HALF, 2 * FALLBACK_HALF)
    return rect.adjusted(-CROP_MARGIN, -CROP_MARGIN, CROP_MARGIN, CROP_MARGIN)


def cardinal_cut(direction: str, box: QRectF):
    """``((ax, ay), (bx, by), depth)`` in plan-scene coords for a cardinal
    whose crop box is *box*: the cut line is the box edge on the camera side
    (scene top = world north), the look side is the box interior."""
    l, t, r, b = box.left(), box.top(), box.right(), box.bottom()
    if direction == "north":
        return (r, t), (l, t), box.height()
    if direction == "south":
        return (l, b), (r, b), box.height()
    if direction == "east":
        return (r, b), (r, t), box.width()
    if direction == "west":
        return (l, t), (l, b), box.width()
    raise ValueError(direction)


CARDINALS = ("north", "south", "east", "west")


class SectionMarker(QGraphicsItem):
    """A section's cut line + crop box on the plan (spec s6).

    Geometry (``cut_a``, ``cut_b``, ``depth``) is in plan-scene units -- mm at
    ppm 1 (``DetailMarker.crop_rect`` convention);
    ``SectionScene`` converts to world through ``_scene_to_world``. Paint,
    grips, menu and properties are added in a later task; this core carries
    the fields, the dict round-trip and the cardinal auto-extent fit.
    """

    HALO_AREA = True

    def __init__(self, name: str, cut_a: QPointF, cut_b: QPointF,
                 look_sign: int = 1, depth: float = 10000.0,
                 cardinal: "str | None" = None, auto_extent: bool = False,
                 parent: QGraphicsItem | None = None):
        super().__init__(parent)
        self._name = name
        self._a = QPointF(cut_a)
        self._b = QPointF(cut_b)
        self._look = 1 if look_sign >= 0 else -1
        self._depth = float(depth)
        self._cardinal = cardinal
        self._auto_extent = bool(auto_extent) if cardinal else False
        self.gridline_z_overrides: dict[str, dict] = {}
        self._manager = None                     # set by SectionManager
        self.PAPER_EXCLUDED = cardinal is not None    # s6.4: cardinals never plot
        self._exclude_from_bulk_select = True
        self.level = DEFAULT_LEVEL               # display-manager categorization
        self._display_overrides: dict = {}
        self._marker_color = QColor(GRID_COLOR)
        self._fill_color = QColor("#1a1a2e")
        self._display_font_size: int | None = None
        self.setZValue(Z_OVERLAY)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    @classmethod
    def for_cardinal(cls, direction: str, box: QRectF) -> "SectionMarker":
        a, b, depth = cardinal_cut(direction, box)
        return cls(direction.title(), QPointF(*a), QPointF(*b), 1, depth,
                   cardinal=direction, auto_extent=True)

    # -- fields -----------------------------------------------------------
    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, v: str):
        self._name = str(v)
        self.update()

    @property
    def cut_a(self) -> QPointF:
        return QPointF(self._a)

    @property
    def cut_b(self) -> QPointF:
        return QPointF(self._b)

    @property
    def look_sign(self) -> int:
        return self._look

    @property
    def depth(self) -> float:
        return self._depth

    @property
    def cardinal(self) -> "str | None":
        return self._cardinal

    @property
    def auto_extent(self) -> bool:
        return self._auto_extent

    @property
    def view_type(self) -> str:
        return "elevation" if self._cardinal else "section"

    @property
    def view_name(self) -> str:
        """The name consumers key on: the direction for a cardinal (s7.2)."""
        return self._cardinal if self._cardinal else self._name

    def normal_scene(self) -> tuple[float, float]:
        """Unit look normal in plan-scene coords (y-down): ``look * (D.y, -D.x)``."""
        dx, dy = self._b.x() - self._a.x(), self._b.y() - self._a.y()
        L = math.hypot(dx, dy) or 1.0
        return self._look * dy / L, -self._look * dx / L

    def box_polygon(self) -> QPolygonF:
        nx, ny = self.normal_scene()
        far = QPointF(nx * self._depth, ny * self._depth)
        return QPolygonF([self._a, self._b, self._b + far, self._a + far])

    # -- mutation (grips / menu / manager call these) -----------------------
    def set_geometry(self, a: QPointF, b: QPointF, depth: float, *, user: bool = True):
        self.prepareGeometryChange()
        self._a, self._b, self._depth = QPointF(a), QPointF(b), float(depth)
        if user and self._cardinal:
            self._auto_extent = False            # first user edit owns the box (s4.3)
        self.update()
        self._notify()

    def flip(self):
        self._look = -self._look
        self.update()
        self._notify()

    def _notify(self):
        mgr = self._manager
        if mgr is not None:
            mgr.on_marker_geometry_changed(self)

    def auto_fit(self, model_space) -> bool:
        """Re-seed a cardinal's box from the building; True when geometry moved."""
        if not self._auto_extent or not self._cardinal:
            return False
        a, b, depth = cardinal_cut(self._cardinal, building_bbox(model_space))
        a, b = QPointF(*a), QPointF(*b)
        if a == self._a and b == self._b and depth == self._depth:
            return False
        self.prepareGeometryChange()
        self._a, self._b, self._depth = a, b, depth
        self.update()
        return True

    # -- geometry stubs (Task 8 replaces) --------------------------------------
    def boundingRect(self) -> QRectF:
        return self.box_polygon().boundingRect().adjusted(-MARKER_SIZE, -MARKER_SIZE,
                                                          MARKER_SIZE, MARKER_SIZE)

    def paint(self, painter, option, widget=None):
        pass

    # -- serialization (spec s8) ------------------------------------------------
    def to_dict(self) -> dict:
        return {"name": self._name,
                "cut_a": [self._a.x(), self._a.y()],
                "cut_b": [self._b.x(), self._b.y()],
                "look_sign": self._look, "depth": self._depth,
                "cardinal": self._cardinal, "auto_extent": self._auto_extent,
                "gridline_z_overrides": dict(self.gridline_z_overrides)}

    @classmethod
    def from_dict(cls, d: dict) -> "SectionMarker":
        m = cls(d["name"], QPointF(*d["cut_a"]), QPointF(*d["cut_b"]),
                int(d.get("look_sign", 1)), float(d.get("depth", 10000.0)),
                cardinal=d.get("cardinal"), auto_extent=bool(d.get("auto_extent", False)))
        m.gridline_z_overrides = dict(d.get("gridline_z_overrides", {}))
        return m


# ─────────────────────────────────────────────────────────────────────────────
# SharedCropBox — single dashed rectangle for all elevation markers
# ─────────────────────────────────────────────────────────────────────────────

class SharedCropBox(QGraphicsRectItem):
    """A single dashed rectangle shared by all elevation markers.

    Visible only when any marker is selected.  Resizable via grip handles.
    The rect is in scene coordinates and defines the building extent
    for all elevation views.
    """

    PAPER_EXCLUDED = True   # authoring furniture — never plots (hard rule)

    def __init__(self, rect: QRectF, parent: QGraphicsItem | None = None):
        super().__init__(rect, parent)

        # No own outline — the SelectionManipulator's dashed frame is the crop
        # outline when a marker is selected (U3 unified chrome). Keep the faint
        # fill so the building-extent region still reads. (DetailMarker precedent.)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        fill = QColor(GRID_COLOR)
        fill.setAlpha(15)
        self.setBrush(QBrush(fill))
        self.setZValue(-200)
        self.setVisible(False)

        # Not selectable itself
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    # ── Grip protocol ────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """8 grips: 4 corners + 4 edge midpoints (scene coords)."""
        r = self.rect()
        pts = [
            r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft(),
            QPointF(r.center().x(), r.top()),
            QPointF(r.right(), r.center().y()),
            QPointF(r.center().x(), r.bottom()),
            QPointF(r.left(), r.center().y()),
        ]
        return [self.mapToScene(p) for p in pts]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Resize the shared rect from a grip drag."""
        local = self.mapFromScene(new_pos)
        r = self.rect()

        if index == 0:
            r.setTopLeft(local)
        elif index == 1:
            r.setTopRight(local)
        elif index == 2:
            r.setBottomRight(local)
        elif index == 3:
            r.setBottomLeft(local)
        elif index == 4:
            r.setTop(local.y())
        elif index == 5:
            r.setRight(local.x())
        elif index == 6:
            r.setBottom(local.y())
        elif index == 7:
            r.setLeft(local.x())

        r = r.normalized()
        self.setRect(r)

        # Reposition markers to midpoints of the resized rect
        mgr = getattr(self, "_manager", None)
        if mgr is not None:
            mgr._reposition_markers_to_rect(r)


# ─────────────────────────────────────────────────────────────────────────────
# ViewMarkerArrow — filled triangle with cardinal letter
# ─────────────────────────────────────────────────────────────────────────────

class ViewMarkerArrow(QGraphicsPolygonItem):
    """Elevation marker: circle with cardinal letter + two tangent lines
    meeting at a point toward the building.

    Shares a single crop box managed by ViewMarkerManager.
    """

    PAPER_EXCLUDED = True   # elevation tags are authoring furniture — never plot
    HALO_AREA = True         # HALO: filled selectable polygon — cursor inside = direct hit

    _CIRCLE_R = BUBBLE_RADIUS_MM * 3.0          # circle radius (3× default)
    # Tip distance chosen so the two tangent lines meet at ~80°:
    # half-angle = 40°, D = R / sin(40°) ≈ R * 1.556
    _POINT_DIST = BUBBLE_RADIUS_MM * 3.0 / math.sin(math.radians(40))

    def __init__(self, direction: str, view_type: str = "elevation",
                 parent: QGraphicsItem | None = None):
        super().__init__(parent)
        self._direction = direction.lower()
        self._view_type = view_type
        self._manager = None  # set by ViewMarkerManager

        # Build bounding polygon (used for hit-testing footprint)
        self._size = MARKER_SIZE
        self.setPolygon(self._build_outline_polygon())

        # Appearance: use gridline color scheme
        self._marker_color = QColor(GRID_COLOR)
        self._fill_color = QColor("#1a1a2e")
        pen_w = max(1.0, BUBBLE_RADIUS_MM * 0.04)
        pen = QPen(self._marker_color, pen_w)
        self.setPen(pen)
        self.setBrush(QBrush(self._fill_color))
        self.setZValue(Z_OVERLAY)

        # Selectable (NOT movable — position pinned to shared box midlines)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self._exclude_from_bulk_select = True  # skip Ctrl+A / rubber-band

        # Ensure this level attribute exists for display manager categorization
        self.level = DEFAULT_LEVEL

    @property
    def direction(self) -> str:
        return self._direction

    @property
    def view_type(self) -> str:
        return self._view_type

    @property
    def crop_box(self):
        """Return the shared crop box from the manager."""
        if self._manager is not None:
            return self._manager._crop_box
        return None

    # ── Geometry ──────────────────────────────────────────────────────────

    def _tip_direction(self) -> tuple[float, float]:
        """Unit vector from circle center toward the building (tip direction)."""
        if self._direction == "north":
            return (0, 1)     # tip points down (+Y = toward building in plan)
        elif self._direction == "south":
            return (0, -1)
        elif self._direction == "east":
            return (-1, 0)    # east looks left (−X toward building)
        elif self._direction == "west":
            return (1, 0)     # west looks right (+X toward building)
        return (0, 1)

    def _tangent_points_and_tip(self):
        """Return (tangent_left, tangent_right, tip) in local coords."""
        R = self._CIRCLE_R
        D = self._POINT_DIST
        dx, dy = self._tip_direction()

        # Tip point
        tip = QPointF(dx * D, dy * D)

        # Angle of tangent lines from center-to-tip axis
        # For a circle of radius R and external point at distance D:
        # tangent touches at angle ±arccos(R/D) from the axis
        alpha = math.acos(min(R / D, 1.0))

        # Base angle of the direction vector
        base_angle = math.atan2(dy, dx)

        # Tangent points on the circle
        a1 = base_angle + alpha
        a2 = base_angle - alpha
        t1 = QPointF(R * math.cos(a1), R * math.sin(a1))
        t2 = QPointF(R * math.cos(a2), R * math.sin(a2))

        return t1, t2, tip

    def _build_outline_polygon(self) -> QPolygonF:
        """Build a polygon that encloses the circle + tangent lines for hit-testing."""
        t1, t2, tip = self._tangent_points_and_tip()
        R = self._CIRCLE_R
        # Approximate: polygon = circle bounding box corners + tip
        return QPolygonF([
            QPointF(-R, -R), QPointF(R, -R),
            QPointF(R, R), QPointF(-R, R),
            tip,
        ])

    # ── Drawing ──────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None):
        """Draw circle with cardinal letter + two tangent lines to a point."""
        option.state &= ~QStyle.StateFlag.State_Selected

        R = self._CIRCLE_R
        pen_w = max(1.0, R * 0.04)
        t1, t2, tip = self._tangent_points_and_tip()

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Filled wedge (area enclosed by tangent lines + arc) ───────
        # Build path: t1 → tip → t2 → arc back to t1
        dx, dy = self._tip_direction()
        base_angle = math.atan2(dy, dx)
        alpha = math.acos(min(R / self._POINT_DIST, 1.0))
        # Qt arc angles in degrees × 16, measured counter-clockwise from 3-o'clock
        a1_deg = -math.degrees(base_angle + alpha)   # tangent point 1 angle
        a2_deg = -math.degrees(base_angle - alpha)   # tangent point 2 angle
        sweep = a1_deg - a2_deg
        # Normalise sweep to go the short way around (through the side away from tip)
        while sweep > 180:
            sweep -= 360
        while sweep < -180:
            sweep += 360

        wedge = QPainterPath()
        wedge.moveTo(t1)
        wedge.lineTo(tip)
        wedge.lineTo(t2)
        arc_rect = QRectF(-R, -R, 2 * R, 2 * R)
        wedge.arcTo(arc_rect, a2_deg, sweep)
        wedge.closeSubpath()

        painter.setPen(QPen(self._marker_color, pen_w))
        painter.setBrush(QBrush(self._marker_color))
        painter.drawPath(wedge)

        # ── Filled circle ────────────────────────────────────────────
        painter.setBrush(QBrush(self._fill_color))
        painter.drawEllipse(QPointF(0, 0), R, R)

        # ── Selection highlight ──────────────────────────────────────
        if self.isSelected():
            highlight_pen = QPen(self._marker_color.lighter(150),
                                 max(1, R * 0.08))
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), R, R)
            painter.drawLine(t1, tip)
            painter.drawLine(t2, tip)

        # ── Cardinal letter centered in circle ───────────────────────
        letter = self._direction[0].upper()
        font = QFont("Consolas")
        font_pt = getattr(self, "_display_font_size", None)
        if font_pt is not None:
            font.setPixelSize(max(1, int(R * (font_pt / 10.0))))
        else:
            font.setPixelSize(max(1, int(R * 1.0)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(self._marker_color.lighter(150)))
        # Draw letter centered in the circle, not the full bounding rect
        circle_rect = QRectF(-R, -R, 2 * R, 2 * R)
        painter.drawText(circle_rect, Qt.AlignmentFlag.AlignCenter, letter)

    def boundingRect(self) -> QRectF:
        R = self._CIRCLE_R
        D = self._POINT_DIST
        m = max(R, D) + R * 0.1  # small margin
        return QRectF(-m, -m, 2 * m, 2 * m)

    def shape(self) -> QPainterPath:
        """Selectable area = circle + tangent-line region."""
        path = QPainterPath()
        R = self._CIRCLE_R
        path.addEllipse(QPointF(0, 0), R, R)
        t1, t2, tip = self._tangent_points_and_tip()
        path.moveTo(t1)
        path.lineTo(tip)
        path.lineTo(t2)
        path.closeSubpath()
        return path

    # ── Selection → show/hide shared crop box ─────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if self._manager is not None:
                self._manager._on_marker_selection_changed()
            self.update()
        return super().itemChange(change, value)

    # ── Double-click → open view ──────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        sc = self.scene()
        if sc is not None and hasattr(sc, "openViewRequested"):
            sc.openViewRequested.emit(self._view_type, self._direction)
        event.accept()

    # ── Grip protocol (forward to shared crop box) ────────────────────────

    def grip_points(self) -> list[QPointF]:
        # Gated on isSelected() + box existence only — NOT box.isVisible().
        # The box's visibility is set by this marker's own itemChange
        # (_on_marker_selection_changed) during the SAME selection event that
        # triggers the manipulator's rebake; keying on isVisible() races that
        # ordering (rebake read [] -> built zero grip hosts -> no handles shown).
        # Selection alone is the correct predicate: the box is visible iff a
        # marker is selected, and the manipulator only wraps selected items.
        if self.isSelected() and self._manager is not None:
            box = self._manager._crop_box
            if box is not None:
                return box.grip_points()
        return []

    def apply_grip(self, index: int, new_pos: QPointF):
        if self._manager is not None:
            box = self._manager._crop_box
            if box is not None:
                box.apply_grip(index, new_pos)

    # ── Selection-manipulator adapter (U3) — PARAMETRIC crop (resize + move) ──
    # Governing spec: selection-manipulator.md (U3). Mirrors DetailMarker
    # (detail_view.py): the 8 crop grips (corners + edge midpoints) live-mutate
    # the SHARED SharedCropBox via apply_grip; interior-drag moves the whole box.
    # The manipulator EXCLUDES items with no "translate" capability
    # (selection_manipulator.py) so manip_translate is mandatory to be wrapped.
    # Grips render SQUARE (resize handles); caps = {translate} (no manip_scale ->
    # not box-native -> the manipulator's dashed FRAME is the crop outline; the
    # box's own outline is dropped, its faint fill kept). Axis-aligned (no rotate).
    # State-dependent: grip_points() is empty unless selected + box visible, so
    # manip_handles() is empty then and the coexistence gate reads "not migrated"
    # (benign — nothing renders on either path; same as Room/DesignArea).

    def manip_bounds(self) -> QRectF:
        box = None if self._manager is None else self._manager._crop_box
        if box is not None:
            return box.mapRectToScene(box.rect())
        return self.sceneBoundingRect()

    def manip_handles(self):
        from .manip_handle import default_grip_handles
        return default_grip_handles(self)      # 8 crop grips, all square (resize)

    def manip_translate(self, dx: float, dy: float):
        """Move the whole shared crop box + reposition all markers to its edges."""
        box = None if self._manager is None else self._manager._crop_box
        if box is None:
            return
        r = box.rect().translated(dx, dy)
        box.setRect(r)
        self._manager._reposition_markers_to_rect(r)

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "direction": self._direction,
            "view_type": self._view_type,
            "pos_x": self.pos().x(),
            "pos_y": self.pos().y(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ViewMarkerArrow":
        marker = cls(
            direction=data["direction"],
            view_type=data.get("view_type", "elevation"),
        )
        marker.setPos(data.get("pos_x", 0), data.get("pos_y", 0))
        return marker


# ─────────────────────────────────────────────────────────────────────────────
# ViewMarkerManager — creates and manages all markers + shared crop box
# ─────────────────────────────────────────────────────────────────────────────

class ViewMarkerManager:
    """Creates and manages elevation markers with a shared crop rectangle.

    All four markers (N/S/E/W) are pinned to the midpoints of the shared
    bounding box edges.  Selecting any marker shows the shared crop box.
    """

    def __init__(self, scene: "Model_Space"):
        self._scene = scene
        self._markers: dict[str, ViewMarkerArrow] = {}
        self._crop_box: SharedCropBox | None = None

    def create_elevation_markers(self):
        """Create N/S/E/W markers around the gridline bbox with a shared crop box."""
        bbox = self._gridline_bbox()
        crop_rect = QRectF(
            bbox.left() - CROP_MARGIN,
            bbox.top() - CROP_MARGIN,
            bbox.width() + CROP_MARGIN * 2,
            bbox.height() + CROP_MARGIN * 2,
        )

        # Create shared crop box
        self._crop_box = SharedCropBox(crop_rect)
        self._crop_box._manager = self
        self._scene.addItem(self._crop_box)

        # Create 4 markers pinned to midpoints of the crop rect edges
        for direction in ("north", "south", "east", "west"):
            if direction in self._markers:
                continue
            marker = ViewMarkerArrow(direction, "elevation")
            marker._manager = self
            self._scene.addItem(marker)
            self._markers[direction] = marker

        self._reposition_markers_to_rect(crop_rect)

    def _reposition_markers_to_rect(self, rect: QRectF):
        """Pin all markers so the arrow tip meets the midpoint of each edge."""
        cx = rect.center().x()
        cy = rect.center().y()
        # The circle center is _POINT_DIST away from the tip, so offset
        # the center by that amount + a 25 mm gap outward from the rect edge.
        gap = 25.0  # mm offset between tip and bounding box edge
        d = ViewMarkerArrow._POINT_DIST + gap

        positions = {
            "north": QPointF(cx, rect.top() - d),
            "south": QPointF(cx, rect.bottom() + d),
            "east":  QPointF(rect.right() + d, cy),
            "west":  QPointF(rect.left() - d, cy),
        }

        for direction, pos in positions.items():
            marker = self._markers.get(direction)
            if marker is not None:
                marker.setPos(pos)

    def _on_marker_selection_changed(self):
        """Show crop box if ANY marker is selected, hide if none are."""
        any_selected = any(m.isSelected() for m in self._markers.values())
        if self._crop_box is not None:
            self._crop_box.setVisible(any_selected)

    def remove_all(self):
        """Remove all markers and the crop box from the scene."""
        for marker in self._markers.values():
            if marker.scene() is self._scene:
                self._scene.removeItem(marker)
        self._markers.clear()
        if self._crop_box is not None and self._crop_box.scene() is self._scene:
            self._scene.removeItem(self._crop_box)
            self._crop_box = None

    def get_marker(self, direction: str) -> ViewMarkerArrow | None:
        return self._markers.get(direction.lower())

    def get_crop_rect(self) -> QRectF | None:
        """Get the shared crop rect in scene coordinates."""
        if self._crop_box is None:
            return None
        return self._crop_box.mapRectToScene(self._crop_box.rect())

    def _gridline_bbox(self) -> QRectF:
        """Compute bounding box of all gridline endpoints in scene coords."""
        gridlines = getattr(self._scene, "_gridlines", [])
        if not gridlines:
            return QRectF(-10000, -10000, 20000, 20000)

        xs, ys = [], []
        for gl in gridlines:
            line = gl.line()
            p1 = gl.mapToScene(line.p1())
            p2 = gl.mapToScene(line.p2())
            xs.extend([p1.x(), p2.x()])
            ys.extend([p1.y(), p2.y()])

        return QRectF(
            min(xs), min(ys),
            max(xs) - min(xs), max(ys) - min(ys),
        )

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        result: dict = {}
        if self._crop_box is not None:
            r = self._crop_box.rect()
            result["crop_rect"] = {
                "x": r.x(), "y": r.y(),
                "w": r.width(), "h": r.height(),
            }
        result["markers"] = [m.to_dict() for m in self._markers.values()]
        return result

    def from_dict(self, data: dict):
        self.remove_all()
        cr = data.get("crop_rect")
        if cr:
            rect = QRectF(cr["x"], cr["y"], cr["w"], cr["h"])
        else:
            bbox = self._gridline_bbox()
            rect = QRectF(
                bbox.left() - CROP_MARGIN, bbox.top() - CROP_MARGIN,
                bbox.width() + CROP_MARGIN * 2, bbox.height() + CROP_MARGIN * 2,
            )

        self._crop_box = SharedCropBox(rect)
        self._crop_box._manager = self
        self._scene.addItem(self._crop_box)

        for item in data.get("markers", []):
            marker = ViewMarkerArrow.from_dict(item)
            marker._manager = self
            self._scene.addItem(marker)
            self._markers[marker.direction] = marker

        self._reposition_markers_to_rect(rect)
