"""
section_marker.py
=================
Section view geometry and the plan marker (spec ``section-view-subsystem.md``).

``SectionBasis`` is the pure projection / classification math of one section
(world mm).  ``SectionMarker`` is the single plan-scene item per section: a cut
line A->B with a bubble and look-side arrow head at each end, plus a crop box
(``depth`` beyond the line) that is drawn only while the marker is selected.
The four cardinal elevations are permanent cardinal ``SectionMarker`` s.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsItem, QStyle
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QPolygonF, QFont, QPainter, QPainterPath,
    QPainterPathStroker,
)

from .constants import DEFAULT_LEVEL, Z_OVERLAY
from .gridline import BUBBLE_RADIUS_MM, GRID_COLOR

if TYPE_CHECKING:
    from .model_space import Model_Space


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CROP_MARGIN = 2000.0                   # plan-scene units (mm at ppm 1) — default crop box padding

MIN_CUT_LEN = 100.0          # plan-scene units (mm at ppm 1) -- shorter cuts are refused at placement (spec s9)
FALLBACK_HALF = 10000.0      # plan-scene units (mm at ppm 1) -- auto-extent box when the project is empty (spec s13)
DEFAULT_DEPTH = 10000.0      # plan-scene units (mm at ppm 1) -- depth when nothing lies on the look side / field absent (spec s9)

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
    ``SectionScene`` converts to world through ``_scene_to_world``. Carries the
    fields, the dict round-trip, the cardinal auto-extent fit, the paint, the
    grips, the context menu and the property panel.
    """

    HALO_AREA = True

    def __init__(self, name: str, cut_a: QPointF, cut_b: QPointF,
                 look_sign: int = 1, depth: float = DEFAULT_DEPTH,
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

    # -- geometry helpers ------------------------------------------------------
    _R = BUBBLE_RADIUS_MM * 3.0                              # bubble radius (old marker circle)
    _HEAD = BUBBLE_RADIUS_MM * 3.0 / math.sin(math.radians(40))   # arrow-head reach (old _POINT_DIST)

    def _unit(self):
        dx, dy = self._b.x() - self._a.x(), self._b.y() - self._a.y()
        L = math.hypot(dx, dy) or 1.0
        return dx / L, dy / L, L

    def _head_polygon(self, tip: QPointF, direction: tuple[float, float]) -> QPolygonF:
        """The old ViewMarkerArrow wedge: tangent points at +/-40 deg around *direction*."""
        R, D = self._R, self._HEAD
        base = math.atan2(direction[1], direction[0])
        alpha = math.acos(min(R / D, 1.0))
        t1 = QPointF(tip.x() - D * math.cos(base) + R * math.cos(base + alpha),
                     tip.y() - D * math.sin(base) + R * math.sin(base + alpha))
        t2 = QPointF(tip.x() - D * math.cos(base) + R * math.cos(base - alpha),
                     tip.y() - D * math.sin(base) + R * math.sin(base - alpha))
        return QPolygonF([t1, tip, t2])

    def _bubble_centres(self):
        ux, uy, _L = self._unit()
        off = self._R * 1.5
        return (QPointF(self._a.x() - ux * off, self._a.y() - uy * off),
                QPointF(self._b.x() + ux * off, self._b.y() + uy * off))

    def boundingRect(self) -> QRectF:
        r = self.box_polygon().boundingRect()
        for c in self._bubble_centres():
            r = r.united(QRectF(c.x() - self._R, c.y() - self._R, 2 * self._R, 2 * self._R))
        m = self._HEAD + self._R
        return r.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        """Hittable: cut line (stroked), the two bubbles, the arrow heads; the
        box edges only while selected (the interior is never hittable)."""
        path = QPainterPath()
        line = QPainterPath(self._a); line.lineTo(self._b)
        stroker = QPainterPathStroker(); stroker.setWidth(max(20.0, self._R * 0.5))
        path.addPath(stroker.createStroke(line))
        for c in self._bubble_centres():
            path.addEllipse(c, self._R, self._R)
        nx, ny = self.normal_scene()
        for end in (self._a, self._b):
            path.addPolygon(self._head_polygon(QPointF(end.x() + nx * self._HEAD, end.y() + ny * self._HEAD), (nx, ny)))
        if self.isSelected():
            box = QPainterPath(); box.addPolygon(self.box_polygon()); box.closeSubpath()
            edge = QPainterPathStroker(); edge.setWidth(max(20.0, self._R * 0.5))
            path.addPath(edge.createStroke(box))
        return path

    def paint(self, painter: QPainter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        col, fill = self._marker_color, self._fill_color
        pen_w = max(1.0, self._R * 0.04)
        # Cut line: solid, cosmetic.
        line_pen = QPen(col, 1); line_pen.setCosmetic(True)
        painter.setPen(line_pen)
        painter.drawLine(self._a, self._b)
        # Arrow heads at A and B pointing to the look side (D6: carried over).
        nx, ny = self.normal_scene()
        painter.setPen(QPen(col, pen_w)); painter.setBrush(QBrush(col))
        for end in (self._a, self._b):
            tip = QPointF(end.x() + nx * self._HEAD, end.y() + ny * self._HEAD)
            painter.drawPolygon(self._head_polygon(tip, (nx, ny)))
        # Bubbles with the name (cardinal letter for cardinals) at both ends.
        label = self._cardinal[0].upper() if self._cardinal else (self._name.split()[-1] if self._name.split() else "?")
        font = QFont("Consolas"); font.setBold(True)
        fs = self._display_font_size if self._display_font_size else 10
        font.setPixelSize(max(1, int(self._R * (fs / 10.0) * (1.0 if len(label) <= 1 else 0.7))))
        painter.setFont(font)
        for c in self._bubble_centres():
            painter.setPen(QPen(col, pen_w)); painter.setBrush(QBrush(fill))
            painter.drawEllipse(c, self._R, self._R)
            painter.setPen(QPen(col.lighter(150)))
            painter.drawText(QRectF(c.x() - self._R, c.y() - self._R, 2 * self._R, 2 * self._R),
                             Qt.AlignmentFlag.AlignCenter, label)
        from . import paper_display as _pd
        if self.isSelected() and not _pd.paper_pass_active():
            # Crop box: the retired SharedCropBox's dashed look, only while selected (s6)
            # and never on a sheet / PDF -- the paper pass does not clear selection (VC9 M4).
            box_pen = QPen(col, 1, Qt.PenStyle.DashLine); box_pen.setCosmetic(True)
            painter.setPen(box_pen)
            faint = QColor(col); faint.setAlpha(15)
            painter.setBrush(QBrush(faint))
            painter.drawPolygon(self.box_polygon())
            hl = QPen(col.lighter(150), max(1.0, self._R * 0.08)); hl.setCosmetic(False)
            painter.setPen(hl); painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(self._a, self._b)

    # -- grip protocol (DetailMarker pattern) ---------------------------------------
    def grip_points(self) -> list[QPointF]:
        nx, ny = self.normal_scene()
        mid = QPointF((self._a.x() + self._b.x()) / 2.0, (self._a.y() + self._b.y()) / 2.0)
        far_mid = QPointF(mid.x() + nx * self._depth, mid.y() + ny * self._depth)
        off = min(self._R * 1.5, self._depth * 0.5)       # stay clear of the depth grip
        flip = QPointF(mid.x() + nx * off, mid.y() + ny * off)
        return [QPointF(self._a), QPointF(self._b), far_mid, flip]

    def apply_grip(self, index: int, new_pos: QPointF):
        if index == 0:
            if math.hypot(new_pos.x() - self._b.x(), new_pos.y() - self._b.y()) < MIN_CUT_LEN:
                return
            self.set_geometry(new_pos, self._b, self._depth)
        elif index == 1:
            if math.hypot(new_pos.x() - self._a.x(), new_pos.y() - self._a.y()) < MIN_CUT_LEN:
                return
            self.set_geometry(self._a, new_pos, self._depth)
        elif index == 2:
            nx, ny = self.normal_scene()
            depth = (new_pos.x() - self._a.x()) * nx + (new_pos.y() - self._a.y()) * ny
            self.set_geometry(self._a, self._b, max(MIN_CUT_LEN, depth))
        # index 3 (flip) is click-only: FlipGripHandle.on_release calls flip().

    def manip_bounds(self) -> QRectF:
        return self.box_polygon().boundingRect()

    def manip_handles(self):
        from .manip_handle import EndpointGripHandle, GripHandle, FlipGripHandle
        return [EndpointGripHandle(self, 0, opposite_index=1),
                EndpointGripHandle(self, 1, opposite_index=0),
                GripHandle(self, 2, circular=False),
                FlipGripHandle(self, 3)]

    def manip_translate(self, dx: float, dy: float):
        self.set_geometry(QPointF(self._a.x() + dx, self._a.y() + dy),
                          QPointF(self._b.x() + dx, self._b.y() + dy), self._depth)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.prepareGeometryChange()          # shape() grows / shrinks with selection
            self.update()
        return super().itemChange(change, value)

    # -- interaction -----------------------------------------------------------------
    def mouseDoubleClickEvent(self, event):
        sc = self.scene()
        if sc is not None and hasattr(sc, "openViewRequested"):
            sc.openViewRequested.emit(self.view_type, self.view_name)
        event.accept()

    def build_context_menu(self):
        """Open - Rename - Flip - Delete (s6); Rename / Delete disabled on cardinals (D5b, D8)."""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu()
        mgr = self._manager
        act_open = menu.addAction("Open")
        act_open.triggered.connect(lambda: mgr is not None and mgr.open_section(self.view_name))
        act_rename = menu.addAction("Rename")
        act_rename.triggered.connect(self._prompt_rename)
        act_flip = menu.addAction("Flip")
        act_flip.triggered.connect(self._flip_with_undo)
        act_delete = menu.addAction("Delete")
        act_delete.triggered.connect(self._delete_with_undo)
        if self._cardinal:
            act_rename.setEnabled(False)
            act_delete.setEnabled(False)
        return menu

    def contextMenuEvent(self, event):
        self.build_context_menu().exec(event.screenPos())
        event.accept()

    def _push_undo(self, sc=None):
        sc = sc if sc is not None else self.scene()
        push = getattr(sc, "push_undo_state", None)
        if push is not None:
            push()

    def _delete_with_undo(self):
        """Menu Delete: mutate first, then snapshot (post-action convention)."""
        sc = self.scene()                         # the marker leaves the scene on delete
        if self._manager is not None:
            self._manager.delete_section(self._name)
            self._push_undo(sc)

    def _rename_with_undo(self, new: str):
        """Rename through the manager; one undo step when the name actually changed."""
        if self._manager is None or not new or new == self._name:
            return
        old = self._name
        self._manager.rename_section(old, new)
        if self._name != old:
            self._push_undo()

    def _flip_with_undo(self):
        self.flip()
        self._push_undo()                         # s8: menu Flip is one undo step

    def _prompt_rename(self):
        from PyQt6.QtWidgets import QInputDialog
        new, ok = QInputDialog.getText(None, "Rename Section", "Name:", text=self._name)
        if ok:
            self._rename_with_undo(new)

    # -- property panel (DetailMarker pattern) -------------------------------------------
    def _fmt(self, mm: float) -> str:
        sc = self.scene()
        sm = getattr(sc, "scale_manager", None) if sc else None
        return sm.scene_to_display(mm) if sm else f"{mm:.1f} mm"

    def get_properties(self) -> dict:
        return {
            "Name": {"value": self._name, "type": "string", "readonly": bool(self._cardinal)},
            "Depth": {"value": self._fmt(self._depth), "type": "string"},
            "Flip": {"value": self._look < 0, "type": "bool"},
            "Cardinal": {"value": self._cardinal.title() if self._cardinal else "-",
                         "type": "string", "readonly": True},
        }

    def set_property(self, key: str, value):
        if key == "Name" and not self._cardinal:
            self._rename_with_undo(str(value))
        elif key == "Depth":
            from .scale_manager import ScaleManager
            mm = ScaleManager.parse_dimension(str(value))
            if mm is not None:
                sc = self.scene()
                sm = getattr(sc, "scale_manager", None) if sc else None
                depth = sm.mm_to_scene(mm) if sm else mm
                if depth >= MIN_CUT_LEN:
                    self.set_geometry(self._a, self._b, float(depth))
                    self._push_undo()
        elif key == "Flip":
            if bool(value) != (self._look < 0):
                self._flip_with_undo()

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
                int(d.get("look_sign", 1)), float(d.get("depth", DEFAULT_DEPTH)),
                cardinal=d.get("cardinal"), auto_extent=bool(d.get("auto_extent", False)))
        m.gridline_z_overrides = dict(d.get("gridline_z_overrides", {}))
        return m
