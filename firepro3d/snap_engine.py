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

from PyQt6.QtCore  import QLineF, QPointF, QRectF
from PyQt6.QtGui   import QTransform
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsItem, QGraphicsItemGroup,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem,
)

from .annotations import DimensionAnnotation, NoteAnnotation
from .construction_geometry import (
    LineItem, RectangleItem, CircleItem, ArcItem,
    PolylineItem, ConstructionLine,
)
from .geometry_intersect import _angle_in_arc
from .gridline import GridlineItem
from .pipe import Pipe
from .wall import WallSegment

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SNAP_TOLERANCE_PX = 40      # screen-pixel search radius

# Below this half-thickness (in scene units) a WallSegment is too thin
# for the user to visually distinguish its face corners from the
# centerline endpoint. We suppress named face-corner / face-mid
# candidates in that regime so the marker glyph doesn't flicker.
# The value matches half of a physical 6 mm wall in the default scale
# (practical floor for real FirePro3D drawings); drawings that use a
# finer scale will almost always have thicker walls.
_FACE_COLLAPSE_SCENE_EPS: float = 3.0

# ─────────────────────────────────────────────────────────────────────────────
# Snap marker legend
# ─────────────────────────────────────────────────────────────────────────────
#
# Eight base glyphs, all rendered *outlined* (no fill) by the foreground
# pass in model_view.drawForeground. Color is carried by SNAP_COLORS;
# shape is carried by SNAP_MARKERS; priority (picker tie-break) is
# carried by SNAP_PRIORITY below.
#
#   endpoint        yellow     outlined square          END  (priority 1)
#   midpoint        green      outlined triangle        MID  (priority 2)
#   intersection    yellow     x inside square          INT  (priority 0)
#   center          cyan       circle                   CEN  (priority 3)
#   quadrant        orange     diamond                  QUA  (priority 5)
#   perpendicular   magenta    right-angle symbol       PER  (priority 4)
#   tangent         lime       tangent circle           TAN  (priority 6)
#   nearest         grey       cross                    NEA  (priority 7)
#
# Two *filled* named-target variants (added 2026-04 per snap engine
# spec §8.2, amended). These are triggered by the ``name`` field on
# OsnapResult: targets whose name starts with ``face-`` are rendered
# with the base glyph's fill color instead of the outlined default.
#
#   face-*-corner-* filled yellow square    WallSegment face corners
#   face-*-mid      filled green triangle   WallSegment face midpoints
#
# See docs/specs/snapping-engine.md §4, §8.
# ─────────────────────────────────────────────────────────────────────────────
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
    source_lines: list | None = field(default=None, repr=False)
    """Optional list of QLineF segments to highlight instead of full items."""
    name:         str | None = None
    """Optional semantic name for this candidate.

    Used for named/semantic targets on complex objects (e.g. a
    WallSegment emits ``centerline-end-A``, ``face-left-corner-A``,
    ``face-right-mid`` etc.).  Targets whose name starts with ``face-``
    are rendered with a *filled* marker glyph by the foreground pass
    in ``model_view.drawForeground``; all other targets (including
    ``name=None``) keep today's outlined rendering.
    """


class _SnapCtx:
    """Mutable snap-tracking context passed between find() phases."""
    __slots__ = ("cursor", "tol", "priority_band",
                 "best_dist", "best_prio", "best_result",
                 "endpoint_candidates")

    def __init__(self, cursor: QPointF, tol: float, priority_band: float):
        self.cursor = cursor
        self.tol = tol
        self.priority_band = priority_band
        self.best_dist: float = tol
        self.best_prio: int = 999
        self.best_result: OsnapResult | None = None
        # Scene-coord points of in-tolerance endpoint candidates seen so
        # far. Phase 4 uses this to suppress intersection candidates
        # that land inside the endpoint protection band (§6.3 Change B).
        self.endpoint_candidates: list[QPointF] = []

    def check(self, snap_type: str, pt: QPointF, src_item: QGraphicsItem,
              name: str | None = None, *,
              src_item2: QGraphicsItem | None = None,
              source_lines: list | None = None):
        """Compare a candidate snap against the current best."""
        d = math.hypot(pt.x() - self.cursor.x(), pt.y() - self.cursor.y())
        if snap_type == "endpoint" and d <= self.tol:
            self.endpoint_candidates.append(pt)
        prio = SNAP_PRIORITY.get(snap_type, 6)
        if (d < self.best_dist - self.priority_band or
                (d < self.best_dist + self.priority_band and prio < self.best_prio)):
            self.best_dist = d
            self.best_prio = prio
            self.best_result = OsnapResult(
                point=pt, snap_type=snap_type,
                source_item=src_item, source_item2=src_item2,
                source_lines=source_lines, name=name,
            )


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
        from .annotations import HatchItem
        _skip_types = (DimensionAnnotation, NoteAnnotation, HatchItem)

        _underlay_tags = ("DXF Underlay", "PDF Underlay")

        for item in scene.items(search_rect):
            if exclude is not None and item is exclude:
                continue

            parent = item.parentItem()
            if parent is not None:
                # Children of underlay groups — collect snaps
                if (isinstance(parent, QGraphicsItemGroup)
                        and parent.data(0) in _underlay_tags):
                    for snap_type, scene_pt, name in self._collect(item):
                        ctx.check(snap_type, scene_pt, item, name)
                continue

            if item.zValue() > 150:
                continue
            if isinstance(item, _skip_types):
                continue
            if item.data(0) == "origin":
                continue
            if self.skip_pipes and isinstance(item, Pipe):
                continue

            # DXF/PDF underlay groups — skip the group itself;
            # children are yielded directly by scene.items() above.
            if (isinstance(item, QGraphicsItemGroup)
                    and item.data(0) in _underlay_tags):
                continue

            for snap_type, pt, name in self._collect(item):
                ctx.check(snap_type, pt, item, name)
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
                        ctx.check("intersection", ix, g1,
                                  src_item2=g2)

    def _check_gridline_snaps(self, ctx: "_SnapCtx", gl_items: list):
        """Phase 3: Gridline point + edge snaps (shape is bubbles-only)."""
        for gl in gl_items:
            for snap_type, pt, name in self._collect(gl):
                ctx.check(snap_type, pt, gl, name)
            for snap_type, pt in self._geometric_snaps(ctx.cursor, gl):
                ctx.check(snap_type, pt, gl)

    def _check_geometry_intersections(self, ctx: "_SnapCtx",
                                       scene: QGraphicsScene,
                                       search_rect: QRectF,
                                       exclude: QGraphicsItem | None,
                                       gl_items: list):
        """Phase 4: Line-line and line-circle intersection snaps."""
        from .annotations import HatchItem as _hatch_type
        _segments: list[tuple[QPointF, QPointF, QGraphicsItem]] = []
        _circles: list[tuple[QPointF, float, QGraphicsItem]] = []

        # Include all gridlines (shape is bubbles-only, missed by search_rect)
        for gl in gl_items:
            line = gl.line()
            _segments.append((gl.mapToScene(line.p1()),
                             gl.mapToScene(line.p2()), gl))

        _underlay_tags = ("DXF Underlay", "PDF Underlay")

        def _phase4_items():
            """Yield items for segment extraction, descending into DXF groups.

            Uses Qt's scene.items() spatial index instead of manual
            sceneBoundingRect checks — Qt correctly handles cosmetic
            pens and group transforms that boundingRect misses.
            """
            for item in scene.items(search_rect):
                if exclude is not None and item is exclude:
                    continue
                if item.zValue() > 150:
                    continue
                parent = item.parentItem()
                if parent is not None:
                    # Yield children of underlay groups directly
                    if (isinstance(parent, QGraphicsItemGroup)
                            and parent.data(0) in _underlay_tags):
                        yield item
                    continue
                # Skip the group itself (children already yielded above)
                if (isinstance(item, QGraphicsItemGroup)
                        and item.data(0) in _underlay_tags):
                    continue
                yield item

        for item in _phase4_items():
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
                # Use mitered geometry so joined walls share clean corners
                # instead of crossing each other inside the joint — the
                # root cause of the §7.1 wall-corner false negative.
                try:
                    p1l, p1r, p2r, p2l = item.snap_quad_points()
                    _segments.append((p1l, p2l, item))
                    _segments.append((p1r, p2r, item))
                except (ValueError, AttributeError):
                    pass
            elif isinstance(item, CircleItem):
                _circles.append((item._center, item._radius, item))
            elif isinstance(item, QGraphicsPathItem):
                # Generic path items (DXF imports). Skip HatchItem —
                # intentionally all-N/A per snap spec §5.
                if not isinstance(item, _hatch_type):
                    path = item.path()
                    n = path.elementCount()
                    for j in range(min(n - 1, 511)):
                        e1 = path.elementAt(j)
                        e2 = path.elementAt(j + 1)
                        _segments.append((
                            item.mapToScene(QPointF(e1.x, e1.y)),
                            item.mapToScene(QPointF(e2.x, e2.y)),
                            item,
                        ))

        # Endpoint protection band — §6.3 Change B. Intersection
        # candidates within this radius of any in-tolerance endpoint
        # candidate are suppressed before reaching the picker, so a
        # high-priority intersection can never silently displace an
        # endpoint at (for example) a mitered wall corner.
        protection_r = ctx.tol * 0.15
        protection_r_sq = protection_r * protection_r
        endpoints = list(ctx.endpoint_candidates)

        def _protected(ix: QPointF) -> bool:
            for ep in endpoints:
                ex = ix.x() - ep.x()
                ey = ix.y() - ep.y()
                if ex * ex + ey * ey <= protection_r_sq:
                    return True
            return False

        # Segment–segment intersections
        for i, (sa1, sa2, src1) in enumerate(_segments):
            for sb1, sb2, src2 in _segments[i + 1:]:
                if src1 is src2:
                    # Same-parent intersection filter — §6.3 Change A,
                    # already present in the original implementation.
                    # Dropped candidates are wall-internal face×face
                    # crossings, rectangle edge self-crossings, etc.
                    continue
                ix = self._line_line_intersect(sa1, sa2, sb1, sb2)
                if ix is not None:
                    d = math.hypot(ix.x() - ctx.cursor.x(),
                                   ix.y() - ctx.cursor.y())
                    if d <= ctx.tol and not _protected(ix):
                        ctx.check("intersection", ix, src1,
                                  src_item2=src2,
                                  source_lines=[QLineF(sa1, sa2),
                                                QLineF(sb1, sb2)])

        # Segment–circle intersections
        for center, radius, c_item in _circles:
            for sa1, sa2, src in _segments:
                for ix in self._line_circle_intersect(sa1, sa2, center, radius):
                    d = math.hypot(ix.x() - ctx.cursor.x(),
                                   ix.y() - ctx.cursor.y())
                    if d <= ctx.tol and not _protected(ix):
                        ctx.check("intersection", ix, src,
                                  src_item2=c_item,
                                  source_lines=[QLineF(sa1, sa2)])

    # ── Internal ─────────────────────────────────────────────────────────────

    def _collect(
        self, item: QGraphicsItem,
    ) -> list[tuple[str, QPointF, str | None]]:
        """Return (snap_type, scene_pos, name) triples for one item.

        ``name`` is ``None`` for all item types except ``WallSegment``,
        which emits semantic names (centerline-end-A, face-left-corner-A,
        face-right-mid, etc.) so the foreground renderer can pick filled
        vs outlined glyph variants.
        """
        pts: list[tuple[str, QPointF, str | None]] = []

        # ── LineItem (finite draw line) ───────────────────────────────────
        if isinstance(item, LineItem):
            pts.extend(self._line_snaps(item))

        # ── ConstructionLine (extends to infinity) ────────────────────────
        elif isinstance(item, ConstructionLine):
            # Snap to the two anchor points only
            if self.snap_endpoint:
                pts.append(("endpoint", item.pt1, None))
                pts.append(("endpoint", item.pt2, None))
            if self.snap_midpoint:
                mid = QPointF(
                    (item.pt1.x() + item.pt2.x()) / 2,
                    (item.pt1.y() + item.pt2.y()) / 2,
                )
                pts.append(("midpoint", mid, None))

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
                    pts.append(("endpoint", item.mapToScene(c), None))
            if self.snap_midpoint:
                for e in edges:
                    pts.append(("midpoint", item.mapToScene(e), None))
            if self.snap_center:
                pts.append(("center", item.mapToScene(r.center()), None))

        # ── CircleItem / any QGraphicsEllipseItem (Node, sprinkler) ───────
        elif isinstance(item, QGraphicsEllipseItem):
            br  = item.boundingRect()
            cen = br.center()
            _is_node = hasattr(item, "pipes")  # Node has .pipes; circles don't
            if self.snap_center:
                pts.append(("center", item.mapToScene(cen), None))
            # Quadrant snaps only for real circles, not Nodes
            if self.snap_quadrant and not _is_node:
                pts.append(("quadrant", item.mapToScene(QPointF(br.right(), cen.y())), None))
                pts.append(("quadrant", item.mapToScene(QPointF(br.left(),  cen.y())), None))
                pts.append(("quadrant", item.mapToScene(QPointF(cen.x(), br.top())), None))
                pts.append(("quadrant", item.mapToScene(QPointF(cen.x(), br.bottom())), None))

        # ── WallSegment (must come before generic QGraphicsPathItem) ─────
        elif isinstance(item, WallSegment):
            p1, p2 = item.pt1, item.pt2

            # Centerline endpoints (named, but rendered OUTLINED — default glyph)
            if self.snap_endpoint:
                pts.append(("endpoint", p1, "centerline-end-A"))
                pts.append(("endpoint", p2, "centerline-end-B"))

            # Centerline midpoint
            if self.snap_midpoint:
                mid_c = QPointF((p1.x() + p2.x()) / 2,
                                (p1.y() + p2.y()) / 2)
                pts.append(("midpoint", mid_c, "centerline-mid"))

            # Face targets use mitered geometry so they land on the
            # visible wall corners, not the raw unmitered quad. Use the
            # side-effect-free snap_quad_points() (wall.py) — NOT
            # mitered_quad(), which writes paint coordination state.
            try:
                p1l, p1r, p2r, p2l = item.snap_quad_points()
            except Exception:
                p1l = p1r = p2r = p2l = None

            # Defensive rail: if the wall half-thickness in scene units
            # is below _FACE_COLLAPSE_SCENE_EPS, the face corners and
            # face midpoints collapse visually onto the centerline at
            # any reasonable zoom — drop them so the marker doesn't
            # flicker between filled (face) and outlined (centerline).
            try:
                _ht = item.half_thickness_scene()
            except Exception:
                _ht = 0.0

            if (p1l is not None and self.snap_endpoint
                    and _ht >= _FACE_COLLAPSE_SCENE_EPS):
                pts.append(("endpoint", p1l, "face-left-corner-A"))
                pts.append(("endpoint", p1r, "face-right-corner-A"))
                pts.append(("endpoint", p2l, "face-left-corner-B"))
                pts.append(("endpoint", p2r, "face-right-corner-B"))

            if (p1l is not None and self.snap_midpoint
                    and _ht >= _FACE_COLLAPSE_SCENE_EPS):
                left_mid = QPointF(
                    (p1l.x() + p2l.x()) / 2, (p1l.y() + p2l.y()) / 2)
                right_mid = QPointF(
                    (p1r.x() + p2r.x()) / 2, (p1r.y() + p2r.y()) / 2)
                pts.append(("midpoint", left_mid,  "face-left-mid"))
                pts.append(("midpoint", right_mid, "face-right-mid"))

        # ── PolylineItem (must come before generic QGraphicsPathItem) ────
        elif isinstance(item, PolylineItem):
            vertices = item._points
            # All vertices are real geometric endpoints
            if self.snap_endpoint:
                for v in vertices:
                    pts.append(("endpoint", item.mapToScene(v), None))
            # True midpoints of each segment between consecutive vertices
            if self.snap_midpoint:
                for i in range(len(vertices) - 1):
                    a, b = vertices[i], vertices[i + 1]
                    mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
                    pts.append(("midpoint", item.mapToScene(mid), None))

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
                pts.append(("endpoint", start_pt, None))
                pts.append(("endpoint", end_pt, None))

            # Center
            if self.snap_center:
                pts.append(("center", QPointF(cx, cy), None))

            # Angular midpoint along the arc
            if self.snap_midpoint:
                mid_a = math.radians(item._start_deg + item._span_deg / 2)
                mid_pt = QPointF(cx + r * math.cos(mid_a),
                                 cy - r * math.sin(mid_a))
                pts.append(("midpoint", mid_pt, None))

            # Quadrant points that fall within the arc's angular range
            if self.snap_quadrant:
                for q_deg in (0.0, 90.0, 180.0, 270.0):
                    if _angle_in_arc(q_deg, item._start_deg, item._span_deg):
                        q_rad = math.radians(q_deg)
                        q_pt = QPointF(cx + r * math.cos(q_rad),
                                       cy - r * math.sin(q_rad))
                        pts.append(("quadrant", q_pt, None))

        # ── Generic QGraphicsPathItem (DXF imports, etc.) ────────────────
        elif isinstance(item, QGraphicsPathItem):
            path = item.path()
            n = path.elementCount()
            # All path vertices are endpoints
            if self.snap_endpoint:
                for i in range(min(n, 512)):
                    elem = path.elementAt(i)
                    pts.append(("endpoint",
                                item.mapToScene(QPointF(elem.x, elem.y)), None))
            # Segment midpoints between consecutive vertices
            if self.snap_midpoint:
                for i in range(min(n - 1, 511)):
                    e1 = path.elementAt(i)
                    e2 = path.elementAt(i + 1)
                    mid = QPointF((e1.x + e2.x) / 2, (e1.y + e2.y) / 2)
                    pts.append(("midpoint", item.mapToScene(mid), None))

        return pts

    def _line_snaps(
        self, item: QGraphicsLineItem,
    ) -> list[tuple[str, QPointF, str | None]]:
        """Endpoint + midpoint snaps for a QGraphicsLineItem."""
        line = item.line()
        p1  = item.mapToScene(line.p1())
        p2  = item.mapToScene(line.p2())
        pts: list[tuple[str, QPointF, str | None]] = []
        if self.snap_endpoint:
            pts.append(("endpoint", p1, None))
            pts.append(("endpoint", p2, None))
        if self.snap_midpoint:
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            pts.append(("midpoint", mid, None))
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
                if self.snap_nearest:
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
                p1l, p1r, p2r, p2l = item.snap_quad_points()
                _seg_snap(p1l, p2l)  # left face edge (mitered)
                _seg_snap(p1r, p2r)  # right face edge (mitered)
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

        # ── ArcItem — closest point on arc circumference + tangent ───────
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
                    if self.snap_nearest:
                        pts.append(("nearest", foot))

                # Tangent — cursor must be outside the arc's radius
                if self.snap_tangent and d > r + 1e-6:
                    angle_to_cursor = math.atan2(
                        cursor.y() - cy, cursor.x() - cx,
                    )
                    half_angle = math.acos(r / d)
                    for sign in (+1, -1):
                        a = angle_to_cursor + sign * half_angle
                        tp = QPointF(cx + r * math.cos(a),
                                     cy + r * math.sin(a))
                        # Only emit if tangent point falls on the visible arc
                        tp_deg = math.degrees(math.atan2(-(tp.y() - cy),
                                                          tp.x() - cx))
                        if _angle_in_arc(tp_deg, item._start_deg,
                                         item._span_deg):
                            pts.append(("tangent", tp))

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
                    if self.snap_perpendicular:
                        pts.append(("perpendicular", foot))
                    if self.snap_nearest:
                        pts.append(("nearest", foot))

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
