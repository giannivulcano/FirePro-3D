"""
snap_engine.py
==============
Object Snap (OSNAP) engine for FirePro 3D.

Provides nearest-snap-point resolution for all geometry types in the scene,
returning a typed OsnapResult used by the view's foreground renderer to draw
a coloured snap marker.

Snap types supported
--------------------
endpoint    — line/polyline endpoints, rectangle corners
midpoint    — line/segment midpoints, rectangle edge centres, polyline vertex midpoints
center      — circle/ellipse centres, rectangle centres
quadrant    — circle 0°/90°/180°/270° points
nearest     — closest point on a line segment (fallback)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PyQt6.QtCore  import QPointF, QRectF
from PyQt6.QtGui   import QTransform
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsItem, QGraphicsItemGroup,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem,
)

from Annotations import DimensionAnnotation, NoteAnnotation
from construction_geometry import (
    LineItem, RectangleItem, CircleItem, ArcItem,
    PolylineItem, ConstructionLine,
)
from geometry_intersect import _angle_in_arc
from gridline import GridlineItem
from pipe import Pipe
from wall import WallSegment

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SNAP_TOLERANCE_PX = 40      # screen-pixel search radius

SNAP_COLORS: dict[str, str] = {
    "endpoint":      "#ffff00",   # yellow  – square marker
    "midpoint":      "#00ff88",   # green   – triangle marker
    "intersection":  "#ffff00",   # yellow  – X marker (gridline crossings)
    "center":        "#00eeee",   # cyan    – circle marker
    "quadrant":      "#ff8800",   # orange  – diamond marker
    "nearest":       "#aaaaaa",   # grey    – cross marker
    "perpendicular": "#ff00ff",   # magenta – right-angle marker
    "tangent":       "#88ff00",   # lime    – tangent marker
}

SNAP_MARKERS: dict[str, str] = {
    "endpoint":      "square",
    "midpoint":      "triangle",
    "intersection":  "x_cross",
    "center":        "circle",
    "quadrant":      "diamond",
    "nearest":       "cross",
    "perpendicular": "right_angle",
    "tangent":       "tangent_circle",
}

# Priority ordering — lower value = higher priority (endpoint wins over nearest)
SNAP_PRIORITY: dict[str, int] = {
    "intersection":  0,       # highest priority — always wins within band
    "endpoint":      1,
    "midpoint":      2,
    "center":        3,
    "perpendicular": 4,
    "quadrant":      5,
    "tangent":       6,
    "nearest":       7,
}


# ─────────────────────────────────────────────────────────────────────────────
# OsnapResult
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OsnapResult:
    """A single snap point found by the engine."""
    point:       QPointF
    snap_type:   str                               # key from SNAP_COLORS
    source_item:  QGraphicsItem | None = field(default=None, repr=False)
    source_item2: QGraphicsItem | None = field(default=None, repr=False)


class _SnapCtx:
    """Mutable snap-tracking context passed between find() phases."""
    __slots__ = ("cursor", "tol", "priority_band",
                 "best_dist", "best_prio", "best_result")

    def __init__(self, cursor: QPointF, tol: float, priority_band: float):
        self.cursor = cursor
        self.tol = tol
        self.priority_band = priority_band
        self.best_dist: float = tol
        self.best_prio: int = 999
        self.best_result: OsnapResult | None = None

    def check(self, snap_type: str, pt: QPointF, src_item: QGraphicsItem):
        """Compare a candidate snap against the current best."""
        d = math.hypot(pt.x() - self.cursor.x(), pt.y() - self.cursor.y())
        prio = SNAP_PRIORITY.get(snap_type, 6)
        if (d < self.best_dist - self.priority_band or
                (d < self.best_dist + self.priority_band and prio < self.best_prio)):
            self.best_dist = d
            self.best_prio = prio
            self.best_result = OsnapResult(point=pt, snap_type=snap_type,
                                            source_item=src_item)


# ─────────────────────────────────────────────────────────────────────────────
# SnapEngine
# ─────────────────────────────────────────────────────────────────────────────

class SnapEngine:
    """
    Nearest OSNAP resolver for a QGraphicsScene.

    Call :meth:`find` each time the cursor moves to get the best snap point.
    Store the result on the scene so :meth:`Model_View.drawForeground` can
    draw the coloured marker.
    """

    def __init__(self):
        self.enabled:        bool = True
        self.skip_pipes:     bool = False   # True in design_area mode
        # Per-type toggles (all on by default)
        self.snap_endpoint:      bool = True
        self.snap_midpoint:      bool = True
        self.snap_intersection:  bool = True
        self.snap_center:        bool = True
        self.snap_quadrant:      bool = True
        self.snap_nearest:       bool = True
        self.snap_perpendicular: bool = True
        self.snap_tangent:       bool = True

    # ── Public ───────────────────────────────────────────────────────────────

    def find(
        self,
        cursor_scene:   QPointF,
        scene:          QGraphicsScene,
        view_transform: QTransform,
        exclude:        QGraphicsItem | None = None,
    ) -> OsnapResult | None:
        """Return the nearest snappable point within tolerance, or *None*."""
        if not self.enabled:
            return None

        # Convert tolerance from screen pixels to scene units
        scale = view_transform.m11()
        if scale <= 0:
            scale = 1.0
        tol = SNAP_TOLERANCE_PX / scale

        search_rect = QRectF(
            cursor_scene.x() - tol, cursor_scene.y() - tol,
            tol * 2, tol * 2,
        )

        # Mutable snap-tracking state shared across phases
        ctx = _SnapCtx(cursor=cursor_scene, tol=tol,
                        priority_band=tol * 0.3)

        # Phase 1 — Scene items (endpoints, midpoints, perpendicular, etc.)
        self._check_scene_items(ctx, scene, search_rect, exclude)

        # Phase 2 — Gridline-to-gridline intersections
        gl_items = [gl for gl in getattr(scene, "_gridlines", [])
                     if gl.isVisible() and (exclude is None or gl is not exclude)]
        if self.snap_intersection:
            self._check_gridline_intersections(ctx, gl_items)

        # Phase 3 — Gridline point + edge snaps
        self._check_gridline_snaps(ctx, gl_items)

        # Phase 4 — Geometry-to-geometry intersections
        if self.snap_intersection:
            self._check_geometry_intersections(ctx, scene, search_rect, exclude, gl_items)

        return ctx.best_result

    # ── Phase methods ──────────────────────────────────────────────────────

    def _check_scene_items(self, ctx: "_SnapCtx", scene: QGraphicsScene,
                           search_rect: QRectF,
                           exclude: QGraphicsItem | None):
        """Phase 1: Check all scene items in the search rect for basic snaps."""
        from Annotations import HatchItem
        _skip_types = (DimensionAnnotation, NoteAnnotation, HatchItem)

        for item in scene.items(search_rect):
            if exclude is not None and item is exclude:
                continue
            if item.parentItem() is not None:
                continue
            if item.zValue() > 150:
                continue
            if isinstance(item, _skip_types):
                continue
            if item.data(0) == "origin":
                continue
            if self.skip_pipes and isinstance(item, Pipe):
                continue

            # DXF underlay groups — descend into children
            if isinstance(item, QGraphicsItemGroup) and item.data(0) == "DXF Underlay":
                for child in item.childItems():
                    for snap_type, scene_pt in self._collect(child):
                        ctx.check(snap_type, scene_pt, child)
                continue

            for snap_type, pt in self._collect(item):
                ctx.check(snap_type, pt, item)
            for snap_type, pt in self._geometric_snaps(ctx.cursor, item):
                ctx.check(snap_type, pt, item)

    def _check_gridline_intersections(self, ctx: "_SnapCtx",
                                       gl_items: list):
        """Phase 2: Pairwise gridline intersection snaps."""
        for i, g1 in enumerate(gl_items):
            l1 = g1.line()
            a1 = g1.mapToScene(l1.p1())
            a2 = g1.mapToScene(l1.p2())
            for g2 in gl_items[i + 1:]:
                l2 = g2.line()
                b1 = g2.mapToScene(l2.p1())
                b2 = g2.mapToScene(l2.p2())
                ix = self._line_line_intersect(a1, a2, b1, b2)
                if ix is not None:
                    d = math.hypot(ix.x() - ctx.cursor.x(),
                                   ix.y() - ctx.cursor.y())
                    if d <= ctx.tol:
                        # Force intersection to win over perpendicular/nearest
                        ctx.best_dist = d
                        ctx.best_prio = 0
                        ctx.best_result = OsnapResult(
                            point=ix, snap_type="intersection",
                            source_item=g1, source_item2=g2)

    def _check_gridline_snaps(self, ctx: "_SnapCtx", gl_items: list):
        """Phase 3: Gridline point + edge snaps (shape is bubbles-only)."""
        for gl in gl_items:
            for snap_type, pt in self._collect(gl):
                ctx.check(snap_type, pt, gl)
            for snap_type, pt in self._geometric_snaps(ctx.cursor, gl):
                ctx.check(snap_type, pt, gl)

    def _check_geometry_intersections(self, ctx: "_SnapCtx",
                                       scene: QGraphicsScene,
                                       search_rect: QRectF,
                                       exclude: QGraphicsItem | None,
                                       gl_items: list):
        """Phase 4: Line-line and line-circle intersection snaps."""
        _segments: list[tuple[QPointF, QPointF, QGraphicsItem]] = []
        _circles: list[tuple[QPointF, float, QGraphicsItem]] = []

        # Include all gridlines (shape is bubbles-only, missed by search_rect)
        for gl in gl_items:
            line = gl.line()
            _segments.append((gl.mapToScene(line.p1()),
                             gl.mapToScene(line.p2()), gl))

        for item in scene.items(search_rect):
            if exclude is not None and item is exclude:
                continue
            if item.parentItem() is not None:
                continue
            if isinstance(item, ConstructionLine):
                _segments.append((item.pt1, item.pt2, item))
            elif isinstance(item, QGraphicsLineItem):
                line = item.line()
                _segments.append((item.mapToScene(line.p1()),
                                 item.mapToScene(line.p2()), item))
            elif isinstance(item, PolylineItem):
                verts = item._points
                for j in range(len(verts) - 1):
                    _segments.append((item.mapToScene(verts[j]),
                                     item.mapToScene(verts[j + 1]), item))
            elif isinstance(item, RectangleItem):
                r = item.rect()
                corners = [
                    item.mapToScene(QPointF(r.left(),  r.top())),
                    item.mapToScene(QPointF(r.right(), r.top())),
                    item.mapToScene(QPointF(r.right(), r.bottom())),
                    item.mapToScene(QPointF(r.left(),  r.bottom())),
                ]
                for j in range(4):
                    _segments.append((corners[j], corners[(j + 1) % 4], item))
            elif isinstance(item, WallSegment):
                try:
                    p1l, p1r, p2r, p2l = item.quad_points()
                    _segments.append((p1l, p2l, item))
                    _segments.append((p1r, p2r, item))
                except (ValueError, AttributeError):
                    pass
            elif isinstance(item, CircleItem):
                _circles.append((item._center, item._radius, item))

        # Segment–segment intersections
        for i, (sa1, sa2, src1) in enumerate(_segments):
            for sb1, sb2, src2 in _segments[i + 1:]:
                if src1 is src2:
                    continue
                ix = self._line_line_intersect(sa1, sa2, sb1, sb2)
                if ix is not None:
                    d = math.hypot(ix.x() - ctx.cursor.x(),
                                   ix.y() - ctx.cursor.y())
                    if d <= ctx.tol:
                        ctx.check("intersection", ix, src1)

        # Segment–circle intersections
        for center, radius, c_item in _circles:
            for sa1, sa2, src in _segments:
                for ix in self._line_circle_intersect(sa1, sa2, center, radius):
                    d = math.hypot(ix.x() - ctx.cursor.x(),
                                   ix.y() - ctx.cursor.y())
                    if d <= ctx.tol:
                        ctx.check("intersection", ix, src)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _collect(self, item: QGraphicsItem) -> list[tuple[str, QPointF]]:
        """Return (snap_type, scene_pos) pairs for one item."""

        pts: list[tuple[str, QPointF]] = []

        # ── LineItem (finite draw line) ───────────────────────────────────
        if isinstance(item, LineItem):
            pts.extend(self._line_snaps(item))

        # ── ConstructionLine (extends to infinity) ────────────────────────
        elif isinstance(item, ConstructionLine):
            # Snap to the two anchor points only
            if self.snap_endpoint:
                pts.append(("endpoint", item.pt1))
                pts.append(("endpoint", item.pt2))
            if self.snap_midpoint:
                mid = QPointF(
                    (item.pt1.x() + item.pt2.x()) / 2,
                    (item.pt1.y() + item.pt2.y()) / 2,
                )
                pts.append(("midpoint", mid))

        # ── GridlineItem (endpoints, midpoint) ───────────────────────────
        elif isinstance(item, GridlineItem):
            pts.extend(self._line_snaps(item))

        # ── Generic QGraphicsLineItem (Pipe, origin axes) ─────────────────
        elif isinstance(item, QGraphicsLineItem):
            pts.extend(self._line_snaps(item))

        # ── RectangleItem ─────────────────────────────────────────────────
        elif isinstance(item, RectangleItem):
            r = item.rect()
            corners = [
                QPointF(r.left(),  r.top()),
                QPointF(r.right(), r.top()),
                QPointF(r.right(), r.bottom()),
                QPointF(r.left(),  r.bottom()),
            ]
            edges = [
                QPointF((r.left() + r.right()) / 2, r.top()),
                QPointF(r.right(), (r.top() + r.bottom()) / 2),
                QPointF((r.left() + r.right()) / 2, r.bottom()),
                QPointF(r.left(), (r.top() + r.bottom()) / 2),
            ]
            if self.snap_endpoint:
                for c in corners:
                    pts.append(("endpoint", item.mapToScene(c)))
            if self.snap_midpoint:
                for e in edges:
                    pts.append(("midpoint", item.mapToScene(e)))
            if self.snap_center:
                pts.append(("center", item.mapToScene(r.center())))

        # ── CircleItem / any QGraphicsEllipseItem (Node, sprinkler) ───────
        elif isinstance(item, QGraphicsEllipseItem):
            br  = item.boundingRect()
            cen = br.center()
            _is_node = hasattr(item, "pipes")  # Node has .pipes; circles don't
            if self.snap_center:
                pts.append(("center", item.mapToScene(cen)))
            # Quadrant snaps only for real circles, not Nodes
            if self.snap_quadrant and not _is_node:
                pts.append(("quadrant", item.mapToScene(QPointF(br.right(), cen.y()))))
                pts.append(("quadrant", item.mapToScene(QPointF(br.left(),  cen.y()))))
                pts.append(("quadrant", item.mapToScene(QPointF(cen.x(), br.top()))))
                pts.append(("quadrant", item.mapToScene(QPointF(cen.x(), br.bottom()))))

        # ── WallSegment (must come before generic QGraphicsPathItem) ─────
        elif isinstance(item, WallSegment):
            p1, p2 = item.pt1, item.pt2
            # Centerline endpoints
            if self.snap_endpoint:
                pts.append(("endpoint", p1))
                pts.append(("endpoint", p2))
            # Centerline midpoint
            if self.snap_midpoint:
                mid = QPointF((p1.x() + p2.x()) / 2,
                              (p1.y() + p2.y()) / 2)
                pts.append(("midpoint", mid))
            # Quad corner points (wall faces)
            if self.snap_endpoint:
                try:
                    p1l, p1r, p2r, p2l = item.quad_points()
                    pts.append(("endpoint", p1l))
                    pts.append(("endpoint", p1r))
                    pts.append(("endpoint", p2r))
                    pts.append(("endpoint", p2l))
                except Exception:
                    pass
            # Edge midpoints (face mid-lengths)
            if self.snap_midpoint:
                try:
                    p1l, p1r, p2r, p2l = item.quad_points()
                    pts.append(("midpoint", QPointF(
                        (p1l.x() + p2l.x()) / 2, (p1l.y() + p2l.y()) / 2)))
                    pts.append(("midpoint", QPointF(
                        (p1r.x() + p2r.x()) / 2, (p1r.y() + p2r.y()) / 2)))
                except Exception:
                    pass

        # ── PolylineItem (must come before generic QGraphicsPathItem) ────
        elif isinstance(item, PolylineItem):
            vertices = item._points
            # All vertices are real geometric endpoints
            if self.snap_endpoint:
                for v in vertices:
                    pts.append(("endpoint", item.mapToScene(v)))
            # True midpoints of each segment between consecutive vertices
            if self.snap_midpoint:
                for i in range(len(vertices) - 1):
                    a, b = vertices[i], vertices[i + 1]
                    mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
                    pts.append(("midpoint", item.mapToScene(mid)))

        # ── ArcItem ────────────────────────────────────────────────────────
        elif isinstance(item, ArcItem):
            cx, cy = item._center.x(), item._center.y()
            r = item._radius
            sa = math.radians(item._start_deg)
            ea = math.radians(item._start_deg + item._span_deg)

            # Arc start/end as endpoints
            if self.snap_endpoint:
                start_pt = QPointF(cx + r * math.cos(sa), cy - r * math.sin(sa))
                end_pt   = QPointF(cx + r * math.cos(ea), cy - r * math.sin(ea))
                pts.append(("endpoint", start_pt))
                pts.append(("endpoint", end_pt))

            # Center
            if self.snap_center:
                pts.append(("center", QPointF(cx, cy)))

            # Angular midpoint along the arc
            if self.snap_midpoint:
                mid_a = math.radians(item._start_deg + item._span_deg / 2)
                mid_pt = QPointF(cx + r * math.cos(mid_a),
                                 cy - r * math.sin(mid_a))
                pts.append(("midpoint", mid_pt))

            # Quadrant points that fall within the arc's angular range
            if self.snap_quadrant:
                for q_deg in (0.0, 90.0, 180.0, 270.0):
                    if _angle_in_arc(q_deg, item._start_deg, item._span_deg):
                        q_rad = math.radians(q_deg)
                        q_pt = QPointF(cx + r * math.cos(q_rad),
                                       cy - r * math.sin(q_rad))
                        pts.append(("quadrant", q_pt))

        # ── Generic QGraphicsPathItem (DXF imports, etc.) ────────────────
        elif isinstance(item, QGraphicsPathItem):
            path = item.path()
            n = path.elementCount()
            # All path vertices are endpoints
            if self.snap_endpoint:
                for i in range(min(n, 512)):
                    elem = path.elementAt(i)
                    pts.append(("endpoint",
                                item.mapToScene(QPointF(elem.x, elem.y))))
            # Segment midpoints between consecutive vertices
            if self.snap_midpoint:
                for i in range(min(n - 1, 511)):
                    e1 = path.elementAt(i)
                    e2 = path.elementAt(i + 1)
                    mid = QPointF((e1.x + e2.x) / 2, (e1.y + e2.y) / 2)
                    pts.append(("midpoint", item.mapToScene(mid)))

        return pts

    def _line_snaps(self, item: QGraphicsLineItem) -> list[tuple[str, QPointF]]:
        """Endpoint + midpoint snaps for a QGraphicsLineItem."""
        line = item.line()
        p1  = item.mapToScene(line.p1())
        p2  = item.mapToScene(line.p2())
        pts: list[tuple[str, QPointF]] = []
        if self.snap_endpoint:
            pts.append(("endpoint", p1))
            pts.append(("endpoint", p2))
        if self.snap_midpoint:
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            pts.append(("midpoint", mid))
        return pts

    # ── Line–line intersection ──────────────────────────────────────────

    @staticmethod
    def _line_line_intersect(
        a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF,
    ) -> QPointF | None:
        """Return intersection of two finite line segments, or None."""
        dx1 = a2.x() - a1.x();  dy1 = a2.y() - a1.y()
        dx2 = b2.x() - b1.x();  dy2 = b2.y() - b1.y()
        denom = dx1 * dy2 - dy1 * dx2
        if abs(denom) < 1e-10:
            return None  # parallel
        t = ((b1.x() - a1.x()) * dy2 - (b1.y() - a1.y()) * dx2) / denom
        s = ((b1.x() - a1.x()) * dy1 - (b1.y() - a1.y()) * dx1) / denom
        if 0.0 <= t <= 1.0 and 0.0 <= s <= 1.0:
            return QPointF(a1.x() + t * dx1, a1.y() + t * dy1)
        return None

    # ── Line–circle intersection ────────────────────────────────────────

    @staticmethod
    def _line_circle_intersect(
        seg_a: QPointF, seg_b: QPointF,
        center: QPointF, radius: float,
    ) -> list[QPointF]:
        """Return 0–2 intersection points of a line segment with a circle."""
        dx = seg_b.x() - seg_a.x()
        dy = seg_b.y() - seg_a.y()
        fx = seg_a.x() - center.x()
        fy = seg_a.y() - center.y()
        a = dx * dx + dy * dy
        b = 2.0 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - radius * radius
        disc = b * b - 4.0 * a * c
        pts: list[QPointF] = []
        if disc < 0 or a < 1e-12:
            return pts
        disc_sqrt = math.sqrt(disc)
        for sign in (-1, 1):
            t = (-b + sign * disc_sqrt) / (2.0 * a)
            if 0.0 <= t <= 1.0:
                pts.append(QPointF(seg_a.x() + t * dx, seg_a.y() + t * dy))
        return pts

    # ── Perpendicular / Tangent snaps ─────────────────────────────────────

    def _geometric_snaps(
        self, cursor: QPointF, item: QGraphicsItem,
    ) -> list[tuple[str, QPointF]]:
        """Perpendicular, nearest, and tangent snap points (cursor-dependent)."""

        pts: list[tuple[str, QPointF]] = []

        # Helper: project cursor onto a segment for perpendicular + nearest
        def _seg_snap(p1: QPointF, p2: QPointF):
            foot = self._project_to_segment(cursor, p1, p2)
            if foot is not None:
                if self.snap_perpendicular:
                    pts.append(("perpendicular", foot))
                elif self.snap_nearest:
                    pts.append(("nearest", foot))

        # ── Line-based items (QGraphicsLineItem: pipes, gridlines, etc.) ──
        if isinstance(item, QGraphicsLineItem):
            line = item.line()
            _seg_snap(item.mapToScene(line.p1()),
                      item.mapToScene(line.p2()))

        # ── WallSegment — project onto centerline and face edges ──────────
        elif isinstance(item, WallSegment):
            _seg_snap(item.pt1, item.pt2)  # centerline
            try:
                p1l, p1r, p2r, p2l = item.quad_points()
                _seg_snap(p1l, p2l)  # left face edge
                _seg_snap(p1r, p2r)  # right face edge
                _seg_snap(p1l, p1r)  # start cap
                _seg_snap(p2l, p2r)  # end cap
            except Exception:
                pass

        # ── RectangleItem — project onto each of the 4 edges ─────────────
        elif isinstance(item, RectangleItem):
            r = item.rect()
            corners = [
                item.mapToScene(QPointF(r.left(),  r.top())),
                item.mapToScene(QPointF(r.right(), r.top())),
                item.mapToScene(QPointF(r.right(), r.bottom())),
                item.mapToScene(QPointF(r.left(),  r.bottom())),
            ]
            for i in range(4):
                _seg_snap(corners[i], corners[(i + 1) % 4])

        # ── PolylineItem — project onto each segment ─────────────────────
        elif isinstance(item, PolylineItem):
            vertices = item._points
            for i in range(len(vertices) - 1):
                _seg_snap(item.mapToScene(vertices[i]),
                          item.mapToScene(vertices[i + 1]))

        # ── ArcItem — closest point on arc circumference ─────────────────
        if isinstance(item, ArcItem):
            cx, cy = item._center.x(), item._center.y()
            r = item._radius
            dx = cursor.x() - cx
            dy = cursor.y() - cy
            d = math.hypot(dx, dy)
            if d > 1e-6:
                foot_angle_deg = math.degrees(math.atan2(-dy, dx))
                if _angle_in_arc(foot_angle_deg, item._start_deg, item._span_deg):
                    foot = QPointF(cx + r * dx / d, cy + r * dy / d)
                    if self.snap_perpendicular:
                        pts.append(("perpendicular", foot))
                    elif self.snap_nearest:
                        pts.append(("nearest", foot))

        # ── Full circle (QGraphicsEllipseItem) — closest point on circle ─
        if isinstance(item, QGraphicsEllipseItem) and not hasattr(item, "pipes"):
            br = item.boundingRect()
            if abs(br.width() - br.height()) < 0.1:
                center = item.mapToScene(br.center())
                r = br.width() / 2.0
                d = math.hypot(cursor.x() - center.x(),
                               cursor.y() - center.y())
                # Perpendicular / nearest to circle circumference
                if (self.snap_perpendicular or self.snap_nearest) and d > 1e-6:
                    foot = QPointF(
                        center.x() + r * (cursor.x() - center.x()) / d,
                        center.y() + r * (cursor.y() - center.y()) / d,
                    )
                    snap_t = "perpendicular" if self.snap_perpendicular else "nearest"
                    pts.append((snap_t, foot))

                # Tangent
                if self.snap_tangent and d > r + 1e-6:
                    angle_to_cursor = math.atan2(
                        cursor.y() - center.y(),
                        cursor.x() - center.x(),
                    )
                    half_angle = math.acos(r / d)
                    for sign in (+1, -1):
                        a = angle_to_cursor + sign * half_angle
                        tp = QPointF(
                            center.x() + r * math.cos(a),
                            center.y() + r * math.sin(a),
                        )
                        pts.append(("tangent", tp))

        # ── Generic QGraphicsPathItem (DXF imports) — project onto segments
        elif isinstance(item, QGraphicsPathItem):
            # Skip if already handled as WallSegment or PolylineItem
            if not (isinstance(item, WallSegment)):
                if not (isinstance(item, PolylineItem)):
                    path = item.path()
                    n = path.elementCount()
                    for i in range(min(n - 1, 511)):
                        e1 = path.elementAt(i)
                        e2 = path.elementAt(i + 1)
                        _seg_snap(
                            item.mapToScene(QPointF(e1.x, e1.y)),
                            item.mapToScene(QPointF(e2.x, e2.y)),
                        )

        return pts

    @staticmethod
    def _project_to_segment(
        pt: QPointF, seg_a: QPointF, seg_b: QPointF,
    ) -> QPointF | None:
        """Return the foot-of-perpendicular from *pt* onto segment *seg_a*–*seg_b*.

        Returns None if the segment is degenerate (zero-length).
        """
        dx = seg_b.x() - seg_a.x()
        dy = seg_b.y() - seg_a.y()
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-12:
            return None
        t = ((pt.x() - seg_a.x()) * dx + (pt.y() - seg_a.y()) * dy) / len_sq
        t = max(0.0, min(1.0, t))
        return QPointF(seg_a.x() + t * dx, seg_a.y() + t * dy)
