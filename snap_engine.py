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

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SNAP_TOLERANCE_PX = 15      # screen-pixel search radius

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
    "endpoint":      0,
    "intersection":  0,       # same priority as endpoint
    "midpoint":      1,
    "center":        2,
    "perpendicular": 3,
    "quadrant":      4,
    "tangent":       5,
    "nearest":       6,
}


# ─────────────────────────────────────────────────────────────────────────────
# OsnapResult
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OsnapResult:
    """A single snap point found by the engine."""
    point:       QPointF
    snap_type:   str                               # key from SNAP_COLORS
    source_item: QGraphicsItem | None = field(default=None, repr=False)


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
    ) -> OsnapResult | None:
        """
        Return the nearest snappable point within tolerance, or *None*.

        Parameters
        ----------
        cursor_scene :
            Cursor in scene (world) coordinates.
        scene :
            Active QGraphicsScene.
        view_transform :
            View's current QTransform (used to convert screen-px → scene units).
        """
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

        # Lazy-import annotation types so snap engine never snaps to them
        try:
            from Annotations import DimensionAnnotation, NoteAnnotation
            _anno_types = (DimensionAnnotation, NoteAnnotation)
        except ImportError:
            _anno_types = ()

        best_dist   = tol
        best_prio   = 999
        best_result: OsnapResult | None = None

        def _check(snap_type: str, pt: QPointF, src_item: QGraphicsItem):
            nonlocal best_dist, best_prio, best_result
            d = math.hypot(pt.x() - cursor_scene.x(), pt.y() - cursor_scene.y())
            prio = SNAP_PRIORITY.get(snap_type, 6)
            # Strictly closer always wins; within tolerance, prefer higher priority
            if d < best_dist - 1e-3 or (d < best_dist + 1e-3 and prio < best_prio):
                best_dist   = d
                best_prio   = prio
                best_result = OsnapResult(point=pt, snap_type=snap_type, source_item=src_item)

        for item in scene.items(search_rect):
            # Skip child items (parts of groups) — underlay children handled below
            if item.parentItem() is not None:
                continue
            # Skip pure preview/overlay items (very high z)
            z = item.zValue()
            if z > 150:
                continue
            # Skip annotations (dimensions, notes) and origin markers
            if _anno_types and isinstance(item, _anno_types):
                continue
            if item.data(0) == "origin":
                continue
            # In design_area mode, skip pipe items
            if self.skip_pipes:
                try:
                    from pipe import Pipe
                    if isinstance(item, Pipe):
                        continue
                except ImportError:
                    pass

            # DXF underlay groups — descend into children for snap
            if isinstance(item, QGraphicsItemGroup) and item.data(0) == "DXF Underlay":
                for child in item.childItems():
                    for snap_type, scene_pt in self._collect(child):
                        # _collect already returns scene-mapped points
                        _check(snap_type, scene_pt, child)
                continue

            for snap_type, pt in self._collect(item):
                _check(snap_type, pt, item)

            # Perpendicular and tangent snaps (computed from cursor position)
            for snap_type, pt in self._geometric_snaps(cursor_scene, item):
                _check(snap_type, pt, item)

        # ── Gridline-to-gridline intersection snaps ─────────────────────
        # Use ALL gridlines in the scene (not just those in search_rect)
        # because gridline shapes may be too thin for the small search rect.
        # Intersection snaps override perpendicular/nearest when within tol.
        if self.snap_endpoint:
            try:
                from gridline import GridlineItem as _GL
            except ImportError:
                _GL = None
            if _GL is not None:
                gl_items = list(getattr(scene, "_gridlines", []))
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
                            d = math.hypot(ix.x() - cursor_scene.x(),
                                           ix.y() - cursor_scene.y())
                            if d <= tol:
                                # Force intersection to win over
                                # perpendicular/nearest that may be closer
                                best_dist = d
                                best_prio = 0
                                best_result = OsnapResult(
                                    point=ix,
                                    snap_type="intersection",
                                    source_item=g1,
                                )

        return best_result

    # ── Internal ─────────────────────────────────────────────────────────────

    def _collect(self, item: QGraphicsItem) -> list[tuple[str, QPointF]]:
        """Return (snap_type, scene_pos) pairs for one item."""

        # Lazy imports to avoid circular dependencies
        try:
            from construction_geometry import (
                LineItem, RectangleItem, CircleItem, ArcItem,
                PolylineItem, ConstructionLine,
            )
        except ImportError:
            LineItem = RectangleItem = CircleItem = ArcItem = PolylineItem = ConstructionLine = None  # type: ignore
        try:
            from gridline import GridlineItem
        except ImportError:
            GridlineItem = None  # type: ignore
        try:
            from wall import WallSegment as _WallSeg
        except ImportError:
            _WallSeg = None  # type: ignore

        pts: list[tuple[str, QPointF]] = []

        # ── LineItem (finite draw line) ───────────────────────────────────
        if LineItem and isinstance(item, LineItem):
            pts.extend(self._line_snaps(item))

        # ── ConstructionLine (extends to infinity) ────────────────────────
        elif ConstructionLine and isinstance(item, ConstructionLine):
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
        elif GridlineItem and isinstance(item, GridlineItem):
            pts.extend(self._line_snaps(item))

        # ── Generic QGraphicsLineItem (Pipe, origin axes) ─────────────────
        elif isinstance(item, QGraphicsLineItem):
            pts.extend(self._line_snaps(item))

        # ── RectangleItem ─────────────────────────────────────────────────
        elif RectangleItem and isinstance(item, RectangleItem):
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
        elif _WallSeg and isinstance(item, _WallSeg):
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
        elif PolylineItem and isinstance(item, PolylineItem):
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
        elif ArcItem and isinstance(item, ArcItem):
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
                from geometry_intersect import _angle_in_arc
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

    # ── Perpendicular / Tangent snaps ─────────────────────────────────────

    def _geometric_snaps(
        self, cursor: QPointF, item: QGraphicsItem,
    ) -> list[tuple[str, QPointF]]:
        """Perpendicular, nearest, and tangent snap points (cursor-dependent)."""
        # Lazy imports
        try:
            from construction_geometry import (
                LineItem, CircleItem, ArcItem, ConstructionLine,
                RectangleItem, PolylineItem,
            )
        except ImportError:
            LineItem = CircleItem = ArcItem = ConstructionLine = None  # type: ignore
            RectangleItem = PolylineItem = None  # type: ignore
        try:
            from wall import WallSegment as _WallSeg
        except ImportError:
            _WallSeg = None  # type: ignore

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

        # ── WallSegment — project onto centerline ─────────────────────────
        elif _WallSeg and isinstance(item, _WallSeg):
            _seg_snap(item.pt1, item.pt2)

        # ── RectangleItem — project onto each of the 4 edges ─────────────
        elif RectangleItem and isinstance(item, RectangleItem):
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
        elif PolylineItem and isinstance(item, PolylineItem):
            vertices = item._points
            for i in range(len(vertices) - 1):
                _seg_snap(item.mapToScene(vertices[i]),
                          item.mapToScene(vertices[i + 1]))

        # ── ArcItem — closest point on arc circumference ─────────────────
        if ArcItem and isinstance(item, ArcItem):
            cx, cy = item._center.x(), item._center.y()
            r = item._radius
            dx = cursor.x() - cx
            dy = cursor.y() - cy
            d = math.hypot(dx, dy)
            if d > 1e-6:
                foot_angle_deg = math.degrees(math.atan2(-dy, dx))
                from geometry_intersect import _angle_in_arc
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
            if not (_WallSeg and isinstance(item, _WallSeg)):
                if not (PolylineItem and isinstance(item, PolylineItem)):
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
