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

from PyQt6.QtCore  import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui   import QPainterPath, QTransform
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsItem, QGraphicsItemGroup,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem,
)

from .annotations import DimensionAnnotation, NoteAnnotation
from .underlay_snap_index import UnderlaySnapIndex
from .construction_geometry import (
    LineItem, RectangleItem, CircleItem, ArcItem,
    PolylineItem, RegularPolygonItem,
)
from .geometry_intersect import _angle_in_arc
from .gridline import GridlineItem
from .pipe import Pipe
from .wall import WallSegment

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SNAP_TOLERANCE_PX = 40      # screen-pixel search radius
SNAP_MAX_SCENE_TOL = 200.0  # cap search radius in scene units (mm) at low zoom
SNAP_PRIORITY_BAND_PX = 12  # priority-override window (px); see find() / §6.1
_PHASE4_MAX_SEGMENTS = 256  # skip O(n²) pairing when segment count exceeds this

# Geometry primitive epsilons (used in snap math helpers)
_EPS_PARALLEL:   float = 1e-10  # line-line cross product denominator
_EPS_DEGENERATE: float = 1e-12  # zero-length segment / zero-radius guard
_EPS_COINCIDENT: float = 1e-6   # cursor-on-center / point-coincidence

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
                 "endpoint_candidates", "underlay_geoms")

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
        # Per-underlay-group UnderlaySnapIndex.query() results, keyed by
        # id(group). Phase 1 fills it; Phase 4 reuses it so each group
        # is queried once per find(), not twice per mousemove.
        self.underlay_geoms: dict[int, list[dict]] = {}

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

        # Convert tolerance from screen pixels to scene units, capped to
        # prevent huge search rects at low zoom (O(n²) phase-4 cost).
        scale = view_transform.m11()
        if scale <= 0:
            scale = 1.0
        tol = min(SNAP_TOLERANCE_PX / scale, SNAP_MAX_SCENE_TOL)

        search_rect = QRectF(
            cursor_scene.x() - tol, cursor_scene.y() - tol,
            tol * 2, tol * 2,
        )

        # Priority-override band — how much farther a higher-priority snap may
        # sit and still beat a closer lower-priority one. Historically this was
        # tol*0.3, which collapses when the user lowers the snap tolerance: at
        # 5px the band shrinks to ~1.5 units and an intersection (priority 0)
        # loses to the closer nearest/perpendicular foot near a crossing. Floor
        # it at a fixed pixel constant (capped at the tolerance) so it never
        # drops below ~12px, while keeping the original value wherever it is
        # already larger — i.e. behaviour only changes below the 40px default.
        # See docs/specs/snapping-engine.md §6.1 (and Pain #2, tolerance UX).
        priority_band = max(tol * 0.3, min(tol, SNAP_PRIORITY_BAND_PX / scale))

        # Mutable snap-tracking state shared across phases
        ctx = _SnapCtx(cursor=cursor_scene, tol=tol,
                        priority_band=priority_band)

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
        # (_PHASE4_MAX_SEGMENTS inside the method caps the O(n²) pairing)
        if self.snap_intersection:
            self._check_geometry_intersections(ctx, scene, search_rect, exclude, gl_items)

        return ctx.best_result

    # ── Phase methods ──────────────────────────────────────────────────────

    def _check_scene_items(self, ctx: "_SnapCtx", scene: QGraphicsScene,
                           search_rect: QRectF,
                           exclude: QGraphicsItem | None):
        """Phase 1: Check all scene items in the search rect for basic snaps."""
        _skip_types = (DimensionAnnotation, NoteAnnotation)

        _underlay_tags = ("DXF Underlay", "PDF Underlay")

        _bbox = Qt.ItemSelectionMode.IntersectsItemBoundingRect
        _items = scene.items(search_rect, _bbox)

        _queried_underlays: set[int] = set()

        for item in _items:
            if exclude is not None and item is exclude:
                continue

            parent = item.parentItem()
            if parent is not None:
                if (isinstance(parent, QGraphicsItemGroup)
                        and parent.data(0) in _underlay_tags):
                    if isinstance(parent.data(4), UnderlaySnapIndex):
                        # Lazy snap index — query once per group
                        gid = id(parent)
                        if gid not in _queried_underlays:
                            _queried_underlays.add(gid)
                            self._query_underlay_snaps(
                                ctx, parent, search_rect)
                    else:
                        # No snap index (import dialog) — process
                        # invisible child items directly
                        for snap_type, scene_pt, name in self._collect(
                                item):
                            ctx.check(snap_type, scene_pt, item, name)
                        for snap_type, pt in self._geometric_snaps(
                                ctx.cursor, item):
                            ctx.check(snap_type, pt, item)
                continue

            if item.zValue() > 150:
                continue
            if isinstance(item, _skip_types):
                continue
            if item.data(0) == "origin":
                continue
            if self.skip_pipes and isinstance(item, Pipe):
                continue

            # Underlay group itself — query its snap index
            if (isinstance(item, QGraphicsItemGroup)
                    and item.data(0) in _underlay_tags):
                gid = id(item)
                if gid not in _queried_underlays:
                    _queried_underlays.add(gid)
                    self._query_underlay_snaps(ctx, item, search_rect)
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
        # Each segment is (p1, p2, src_item, parent_key). ``src_item`` is the
        # QGraphicsItem traced for highlighting; ``parent_key`` drives
        # same-parent intersection suppression (two segments sharing a parent
        # never form an intersection candidate). For scene items the two are
        # the same item, so a wall's own faces / a polyline's own segments stay
        # suppressed. Underlay-index segments use ``parent_key = None``, which
        # is exempt from suppression: an underlay is "just lines on a drawing",
        # so every visible crossing is snappable regardless of how the DXF
        # grouped entities (e.g. two segments of one LWPOLYLINE that cross).
        # Polyline-vertex pseudo-intersections are handled by the endpoint
        # protection band (§6.3 Change B), not by suppression.
        _segments: list[tuple[QPointF, QPointF, QGraphicsItem, object]] = []
        _circles: list[tuple[QPointF, float, QGraphicsItem]] = []

        # Include all gridlines (shape is bubbles-only, missed by search_rect)
        for gl in gl_items:
            line = gl.line()
            _segments.append((gl.mapToScene(line.p1()),
                             gl.mapToScene(line.p2()), gl, gl))

        _underlay_tags = ("DXF Underlay", "PDF Underlay")

        def _phase4_items():
            """Yield items for segment extraction — skip underlay groups entirely."""
            _bbox = Qt.ItemSelectionMode.IntersectsItemBoundingRect
            for item in scene.items(search_rect, _bbox):
                if exclude is not None and item is exclude:
                    continue
                if item.zValue() > 150:
                    continue
                parent = item.parentItem()
                if parent is not None:
                    if (isinstance(parent, QGraphicsItemGroup)
                            and parent.data(0) in _underlay_tags):
                        if isinstance(parent.data(4), UnderlaySnapIndex):
                            continue  # segments from index below
                        yield item  # no index — process directly
                    continue
                if (isinstance(item, QGraphicsItemGroup)
                        and item.data(0) in _underlay_tags):
                    continue
                yield item

        for item in _phase4_items():
            if isinstance(item, QGraphicsLineItem):
                line = item.line()
                _segments.append((item.mapToScene(line.p1()),
                                 item.mapToScene(line.p2()), item, item))
            elif isinstance(item, PolylineItem):
                verts = item._points
                for j in range(len(verts) - 1):
                    _segments.append((item.mapToScene(verts[j]),
                                     item.mapToScene(verts[j + 1]), item, item))
            elif isinstance(item, RectangleItem):
                r = item.rect()
                corners = [
                    item.mapToScene(QPointF(r.left(),  r.top())),
                    item.mapToScene(QPointF(r.right(), r.top())),
                    item.mapToScene(QPointF(r.right(), r.bottom())),
                    item.mapToScene(QPointF(r.left(),  r.bottom())),
                ]
                for j in range(4):
                    _segments.append((corners[j], corners[(j + 1) % 4],
                                     item, item))
            elif isinstance(item, WallSegment):
                # Use mitered geometry so joined walls share clean corners
                # instead of crossing each other inside the joint — the
                # root cause of the §7.1 wall-corner false negative.
                try:
                    p1l, p1r, p2r, p2l = item.snap_quad_points()
                    _segments.append((p1l, p2l, item, item))
                    _segments.append((p1r, p2r, item, item))
                except (ValueError, AttributeError):
                    pass
            elif isinstance(item, CircleItem):
                _circles.append((item._center, item._radius, item))
            elif isinstance(item, RegularPolygonItem):
                verts = item.vertices()
                for j in range(len(verts)):
                    _segments.append((verts[j], verts[(j + 1) % len(verts)],
                                      item, item))
            elif isinstance(item, QGraphicsPathItem):
                # Generic path items (DXF imports). Filter each segment
                # against the search rect — polyline bounding rects are
                # large but only a few segments are actually near the cursor.
                path = item.path()
                n = path.elementCount()
                for j in range(min(n - 1, 511)):
                    e2 = path.elementAt(j + 1)
                    if e2.type == QPainterPath.ElementType.MoveToElement:
                        continue  # sub-path boundary, no segment
                    e1 = path.elementAt(j)
                    p1 = item.mapToScene(QPointF(e1.x, e1.y))
                    p2 = item.mapToScene(QPointF(e2.x, e2.y))
                    seg_r = QRectF(
                        min(p1.x(), p2.x()) - 0.5,
                        min(p1.y(), p2.y()) - 0.5,
                        abs(p2.x() - p1.x()) + 1.0,
                        abs(p2.y() - p1.y()) + 1.0,
                    )
                    if search_rect.intersects(seg_r):
                        _segments.append((p1, p2, item, item))
                # Abort during extraction — once over the cap the
                # phase bails anyway (see check below).
                if len(_segments) > _PHASE4_MAX_SEGMENTS:
                    return

        # Extract segments from underlay snap indices
        _queried_groups: set[int] = set()
        _bbox_mode = Qt.ItemSelectionMode.IntersectsItemBoundingRect
        for item in scene.items(search_rect, _bbox_mode):
            parent = item.parentItem()
            grp = None
            if parent is not None and isinstance(parent, QGraphicsItemGroup):
                if parent.data(0) in _underlay_tags:
                    grp = parent
            elif (isinstance(item, QGraphicsItemGroup)
                  and item.data(0) in _underlay_tags):
                grp = item
            if grp is None:
                continue
            gid = id(grp)
            if gid in _queried_groups:
                continue
            _queried_groups.add(gid)

            index = grp.data(4)
            if not isinstance(index, UnderlaySnapIndex):
                continue
            xf = grp.sceneTransform()
            inv_xf, ok = xf.inverted()
            if not ok:
                continue
            local_rect = inv_xf.mapRect(search_rect)
            lx1 = local_rect.x()
            ly1 = local_rect.y()
            lx2 = lx1 + local_rect.width()
            ly2 = ly1 + local_rect.height()

            # Reuse Phase 1's query result for this group (same
            # search_rect) instead of querying twice per mousemove.
            nearby = ctx.underlay_geoms.get(gid)
            if nearby is None:
                nearby = index.query(lx1, ly1, local_rect.width(),
                                     local_rect.height())
                ctx.underlay_geoms[gid] = nearby

            for g in nearby:
                kind = g.get("kind")
                if kind == "line":
                    ax = g["x1"]; ay = g["y1"]
                    bx = g["x2"]; by = g["y2"]
                    # Segment-bbox rejection in local space before any
                    # xf.map / QPointF construction.
                    if (max(ax, bx) < lx1 or min(ax, bx) > lx2
                            or max(ay, by) < ly1 or min(ay, by) > ly2):
                        continue
                    p1 = xf.map(QPointF(ax, ay))
                    p2 = xf.map(QPointF(bx, by))
                    seg_r = QRectF(
                        min(p1.x(), p2.x()) - 0.5,
                        min(p1.y(), p2.y()) - 0.5,
                        abs(p2.x() - p1.x()) + 1.0,
                        abs(p2.y() - p1.y()) + 1.0,
                    )
                    if search_rect.intersects(seg_r):
                        _segments.append((p1, p2, grp, None))
                elif kind == "path_points":
                    points = g.get("points", [])
                    for j in range(min(len(points) - 1, 511)):
                        a, b = points[j], points[j + 1]
                        if (max(a[0], b[0]) < lx1 or min(a[0], b[0]) > lx2
                                or max(a[1], b[1]) < ly1
                                or min(a[1], b[1]) > ly2):
                            continue
                        p1 = xf.map(QPointF(a[0], a[1]))
                        p2 = xf.map(QPointF(b[0], b[1]))
                        seg_r = QRectF(
                            min(p1.x(), p2.x()) - 0.5,
                            min(p1.y(), p2.y()) - 0.5,
                            abs(p2.x() - p1.x()) + 1.0,
                            abs(p2.y() - p1.y()) + 1.0,
                        )
                        if search_rect.intersects(seg_r):
                            _segments.append((p1, p2, grp, None))
                # Abort during extraction — once over the cap the phase
                # bails anyway, so don't keep extracting thousands more.
                if len(_segments) > _PHASE4_MAX_SEGMENTS:
                    return

        # Bail out if segment extraction exploded (batched DXF paths
        # have hundreds of segments per item; O(n²) pairing on 3000+
        # segments freezes the UI).
        if len(_segments) > _PHASE4_MAX_SEGMENTS:
            return

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

        # Segment–segment intersections. Suppress crossings whose two segments
        # share a parent entity (a wall's own two faces, one native polyline's
        # own segments). ``parent_key`` — not ``src_item`` — is the entity
        # identity. A ``None`` key (underlay-index segments) is exempt, so
        # crossings within or between imported underlay geometry are kept.
        for i, (sa1, sa2, src1, pk1) in enumerate(_segments):
            for sb1, sb2, src2, pk2 in _segments[i + 1:]:
                if pk1 is not None and pk1 is pk2:
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
            for sa1, sa2, src, _pk in _segments:
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

        # ── RegularPolygonItem (must come before generic QGraphicsPathItem) ─
        elif isinstance(item, RegularPolygonItem):
            verts = item.vertices()
            if self.snap_endpoint:
                for v in verts:
                    pts.append(("endpoint", v, None))
            if self.snap_midpoint:
                for i in range(len(verts)):
                    a, b = verts[i], verts[(i + 1) % len(verts)]
                    pts.append(("midpoint",
                                QPointF((a.x() + b.x()) / 2,
                                        (a.y() + b.y()) / 2), None))
            if self.snap_center:
                pts.append(("center", QPointF(item._center), None))

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
                    e2 = path.elementAt(i + 1)
                    if e2.type == QPainterPath.ElementType.MoveToElement:
                        continue  # sub-path boundary, no segment
                    e1 = path.elementAt(i)
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
        if abs(denom) < _EPS_PARALLEL:
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
        if disc < 0 or a < _EPS_DEGENERATE:
            return pts
        disc_sqrt = math.sqrt(disc)
        for sign in (-1, 1):
            t = (-b + sign * disc_sqrt) / (2.0 * a)
            if 0.0 <= t <= 1.0:
                pts.append(QPointF(seg_a.x() + t * dx, seg_a.y() + t * dy))
        return pts

    # ── Geometry-dict snap methods (underlay snap index) ───────────────────

    def _collect_from_geom(
        self, g: dict, xf: QTransform,
        local_bounds: tuple[float, float, float, float] | None = None,
    ) -> list[tuple[str, QPointF, str | None]]:
        """Return (snap_type, scene_pos, name) triples from a geometry dict.

        Like ``_collect`` but works on raw geometry dicts instead of
        QGraphicsItems.  *xf* is the underlay group's sceneTransform
        used to map local coordinates to scene space.  *local_bounds*
        is the search rect as (x1, y1, x2, y2) in group-local space —
        polyline points outside it are rejected with raw float compares
        before any ``xf.map``/``QPointF`` construction (a candidate
        outside the search rect can never be within snap tolerance).
        """
        pts: list[tuple[str, QPointF, str | None]] = []
        kind = g.get("kind")

        if kind == "line":
            p1 = xf.map(QPointF(g["x1"], g["y1"]))
            p2 = xf.map(QPointF(g["x2"], g["y2"]))
            if self.snap_endpoint:
                pts.append(("endpoint", p1, None))
                pts.append(("endpoint", p2, None))
            if self.snap_midpoint:
                pts.append(("midpoint", QPointF(
                    (p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2), None))

        elif kind == "circle":
            cx = g["x"] + g["w"] / 2
            cy = g["y"] + g["h"] / 2
            center = xf.map(QPointF(cx, cy))
            if self.snap_center:
                pts.append(("center", center, None))
            if self.snap_quadrant:
                rx, ry = g["w"] / 2, g["h"] / 2
                pts.append(("quadrant", xf.map(QPointF(cx + rx, cy)), None))
                pts.append(("quadrant", xf.map(QPointF(cx - rx, cy)), None))
                pts.append(("quadrant", xf.map(QPointF(cx, cy - ry)), None))
                pts.append(("quadrant", xf.map(QPointF(cx, cy + ry)), None))

        elif kind == "arc":
            cx = g["rx"] + g["rw"] / 2
            cy = g["ry"] + g["rh"] / 2
            rx = g["rw"] / 2
            start = g["start"]
            span = g["span"]
            if self.snap_center:
                pts.append(("center", xf.map(QPointF(cx, cy)), None))
            if self.snap_endpoint:
                sa = math.radians(start)
                ea = math.radians(start + span)
                pts.append(("endpoint", xf.map(QPointF(
                    cx + rx * math.cos(sa), cy - rx * math.sin(sa))), None))
                pts.append(("endpoint", xf.map(QPointF(
                    cx + rx * math.cos(ea), cy - rx * math.sin(ea))), None))
            if self.snap_midpoint:
                ma = math.radians(start + span / 2)
                pts.append(("midpoint", xf.map(QPointF(
                    cx + rx * math.cos(ma), cy - rx * math.sin(ma))), None))

        elif kind == "ellipse_full":
            cx = g["pos_cx"] + g["x"] + g["w"] / 2
            cy = g["pos_cy"] + g["y"] + g["h"] / 2
            if self.snap_center:
                pts.append(("center", xf.map(QPointF(cx, cy)), None))

        elif kind == "path_points":
            points = g.get("points", [])
            if local_bounds is not None:
                lx1, ly1, lx2, ly2 = local_bounds
            if self.snap_endpoint:
                for p in points[:512]:
                    if local_bounds is not None and not (
                            lx1 <= p[0] <= lx2 and ly1 <= p[1] <= ly2):
                        continue
                    pts.append(("endpoint", xf.map(QPointF(p[0], p[1])), None))
            if self.snap_midpoint:
                for i in range(min(len(points) - 1, 511)):
                    a, b = points[i], points[i + 1]
                    mx = (a[0] + b[0]) / 2
                    my = (a[1] + b[1]) / 2
                    if local_bounds is not None and not (
                            lx1 <= mx <= lx2 and ly1 <= my <= ly2):
                        continue
                    pts.append(("midpoint", xf.map(QPointF(mx, my)), None))

        # "text" — no snap targets
        return pts

    def _geometric_snaps_from_geom(
        self, cursor: QPointF, g: dict, xf: QTransform,
        local_bounds: tuple[float, float, float, float] | None = None,
    ) -> list[tuple[str, QPointF]]:
        """Perpendicular and nearest snap points from a geometry dict.

        Like ``_geometric_snaps`` but works on raw geometry dicts.
        *xf* is the underlay group's sceneTransform.  *local_bounds*
        is the search rect as (x1, y1, x2, y2) in group-local space —
        polyline segments whose bbox misses it are skipped (the foot
        of a perpendicular is clamped onto the segment, so a segment
        outside the search rect cannot yield an in-tolerance foot).
        """
        pts: list[tuple[str, QPointF]] = []
        kind = g.get("kind")

        def _seg_snap(p1: QPointF, p2: QPointF):
            foot = self._project_to_segment(cursor, p1, p2)
            if foot is not None:
                if self.snap_perpendicular:
                    pts.append(("perpendicular", foot))
                if self.snap_nearest:
                    pts.append(("nearest", foot))

        if kind == "line":
            _seg_snap(xf.map(QPointF(g["x1"], g["y1"])),
                      xf.map(QPointF(g["x2"], g["y2"])))

        elif kind == "circle":
            cx = g["x"] + g["w"] / 2
            cy = g["y"] + g["h"] / 2
            center = xf.map(QPointF(cx, cy))
            r = abs(xf.map(QPointF(cx + g["w"] / 2, cy)).x() - center.x())
            if r < _EPS_DEGENERATE:
                return pts
            d = math.hypot(cursor.x() - center.x(),
                           cursor.y() - center.y())
            if (self.snap_perpendicular or self.snap_nearest) and d > _EPS_COINCIDENT:
                foot = QPointF(
                    center.x() + r * (cursor.x() - center.x()) / d,
                    center.y() + r * (cursor.y() - center.y()) / d,
                )
                if self.snap_perpendicular:
                    pts.append(("perpendicular", foot))
                if self.snap_nearest:
                    pts.append(("nearest", foot))

        elif kind == "path_points":
            points = g.get("points", [])
            if local_bounds is not None:
                lx1, ly1, lx2, ly2 = local_bounds
            for i in range(min(len(points) - 1, 511)):
                a, b = points[i], points[i + 1]
                if local_bounds is not None and (
                        max(a[0], b[0]) < lx1 or min(a[0], b[0]) > lx2
                        or max(a[1], b[1]) < ly1 or min(a[1], b[1]) > ly2):
                    continue
                _seg_snap(xf.map(QPointF(a[0], a[1])),
                          xf.map(QPointF(b[0], b[1])))

        elif kind == "arc":
            cx = g["rx"] + g["rw"] / 2
            cy = g["ry"] + g["rh"] / 2
            center = xf.map(QPointF(cx, cy))
            r = abs(xf.map(QPointF(cx + g["rw"] / 2, cy)).x() - center.x())
            if r < _EPS_DEGENERATE:
                return pts
            d = math.hypot(cursor.x() - center.x(),
                           cursor.y() - center.y())
            if (self.snap_perpendicular or self.snap_nearest) and d > _EPS_COINCIDENT:
                foot = QPointF(
                    center.x() + r * (cursor.x() - center.x()) / d,
                    center.y() + r * (cursor.y() - center.y()) / d,
                )
                if self.snap_perpendicular:
                    pts.append(("perpendicular", foot))
                if self.snap_nearest:
                    pts.append(("nearest", foot))

        return pts

    def _query_underlay_snaps(self, ctx: "_SnapCtx",
                               group: QGraphicsItemGroup,
                               search_rect: QRectF):
        """Query an underlay's snap index for nearby geometry and compute snaps."""
        index = group.data(4)
        if not isinstance(index, UnderlaySnapIndex):
            return

        # Map search_rect from scene space to group-local space
        xf = group.sceneTransform()
        inv_xf, ok = xf.inverted()
        if not ok:
            return
        local_rect = inv_xf.mapRect(search_rect)
        local_bounds = (local_rect.x(), local_rect.y(),
                        local_rect.x() + local_rect.width(),
                        local_rect.y() + local_rect.height())

        gid = id(group)
        nearby = ctx.underlay_geoms.get(gid)
        if nearby is None:
            nearby = index.query(local_rect.x(), local_rect.y(),
                                 local_rect.width(), local_rect.height())
            ctx.underlay_geoms[gid] = nearby

        for g in nearby:
            for snap_type, scene_pt, name in self._collect_from_geom(
                    g, xf, local_bounds):
                ctx.check(snap_type, scene_pt, group, name)
            for snap_type, pt in self._geometric_snaps_from_geom(
                    ctx.cursor, g, xf, local_bounds):
                ctx.check(snap_type, pt, group)

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
            if d > _EPS_COINCIDENT:
                foot_angle_deg = math.degrees(math.atan2(-dy, dx))
                if _angle_in_arc(foot_angle_deg, item._start_deg, item._span_deg):
                    foot = QPointF(cx + r * dx / d, cy + r * dy / d)
                    if self.snap_perpendicular:
                        pts.append(("perpendicular", foot))
                    if self.snap_nearest:
                        pts.append(("nearest", foot))

                # Tangent — cursor must be outside the arc's radius
                if self.snap_tangent and d > r + _EPS_COINCIDENT:
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
                if (self.snap_perpendicular or self.snap_nearest) and d > _EPS_COINCIDENT:
                    foot = QPointF(
                        center.x() + r * (cursor.x() - center.x()) / d,
                        center.y() + r * (cursor.y() - center.y()) / d,
                    )
                    if self.snap_perpendicular:
                        pts.append(("perpendicular", foot))
                    if self.snap_nearest:
                        pts.append(("nearest", foot))

                # Tangent
                if self.snap_tangent and d > r + _EPS_COINCIDENT:
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
                        e2 = path.elementAt(i + 1)
                        if e2.type == QPainterPath.ElementType.MoveToElement:
                            continue  # sub-path boundary, no segment
                        e1 = path.elementAt(i)
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
        if len_sq < _EPS_DEGENERATE:
            return None
        t = ((pt.x() - seg_a.x()) * dx + (pt.y() - seg_a.y()) * dy) / len_sq
        t = max(0.0, min(1.0, t))
        return QPointF(seg_a.x() + t * dx, seg_a.y() + t * dy)
