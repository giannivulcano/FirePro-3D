"""
snap_engine.py
==============
Object Snap (SNAP) engine for FirePro 3D.

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
from typing import Callable

from PyQt6.QtCore  import QLineF, QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui   import (
    QBrush, QColor, QPainter, QPainterPath, QPen, QPolygon, QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsItem, QGraphicsItemGroup,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem,
    QGraphicsRectItem,
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
from .block_instance import BlockInstance

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SNAP_TOLERANCE_PX = 15        # screen-pixel aperture (grab radius); user-tuned default (was 40→20→15)
# Perf-only ceiling on the *search rect* in scene units. It must never shrink
# the effective aperture at a usable zoom — it only clamps below the zoom at
# which individual features are distinguishable (~0.002 px/mm). At 20px aperture
# this equals a 10 m search radius, reached only when a whole building fits in
# ~40 screen px. See docs/specs/snapping-engine.md §3.1 (cap is perf, not tolerance).
SNAP_MAX_SCENE_TOL = 10000.0  # mm
SNAP_PRIORITY_BAND_PX = 12  # priority-override window (px); see find() / §6.1
SNAP_HYSTERESIS_PX = 3       # hold the current snap until another beats it by this many px
_ENDPOINT_PROTECTION_PX = 6  # intersection candidates within this px of an in-aperture endpoint are suppressed (spec §6.3 Change B)
_PHASE4_MAX_SEGMENTS = 256  # skip O(n²) pairing when segment count exceeds this


def _safe_scale(scale: float) -> float:
    """A view m11() scale guarded against zero/negative (→ 1.0)."""
    return scale if scale > 0 else 1.0


def px_to_scene(px: float, scale: float) -> float:
    """Convert a screen-pixel distance to scene units at the given view scale.

    ``scale`` is ``QGraphicsView.transform().m11()`` (pixels per scene unit).
    The shared home for the px→scene math on the SNAP paths (the engine's
    aperture + the design-area / underlay routing) instead of open-coding
    ``px / scale``. (Inference and grip-pick keep their own local guards.)
    """
    return px / _safe_scale(scale)


def scene_to_px(scene_dist: float, scale: float) -> float:
    """Convert a scene-unit distance to screen pixels at the given view scale."""
    return scene_dist * _safe_scale(scale)


def _ray_line(ray) -> QLineF:
    """A long finite QLineF along *ray* for source-trace highlighting.

    ALIGN rays are conceptually infinite; the foreground pass draws a finite
    line, so we materialise a viewport-spanning segment centred on the ray
    origin. Carried on the ``OsnapResult.source_lines`` so ``drawForeground``
    lights the participating tracking vector(s).
    """
    ox, oy = ray.origin
    dx, dy = ray.direction
    L = 1e6
    return QLineF(QPointF(ox - L * dx, oy - L * dy),
                  QPointF(ox + L * dx, oy + L * dy))


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


# ─────────────────────────────────────────────────────────────────────────────
# Shared snap-indicator painter
# ─────────────────────────────────────────────────────────────────────────────

def paint_snap_indicator(painter: QPainter, view, snap_result) -> None:
    """Draw the snap trace and marker glyph for one snap result.

    This is the single source of truth for snap-indicator rendering, shared
    by ``Model_View.drawForeground`` (main plan view) and
    ``_PreviewView.drawForeground`` (import-dialog preview) so both draw
    identical indicators.  It renders, in order:

    1. **Source-item trace** — a dashed ghost (scene coords) of the item(s)
       being snapped to.  Draws ``source_lines`` if present, otherwise the
       ``source_item`` and optional ``source_item2``.  For path items, only
       segments adjacent to the snap point are highlighted (so a single
       corner snap does not light up an entire DXF rectangle).
    2. **Marker glyph** — a colour-coded shape (viewport/device coords) at the
       snap point.  ``face-`` named targets are drawn with a *filled* glyph;
       all others are outlined.

    All optional fields are guarded via ``getattr`` so a minimal result
    (``point`` + ``snap_type`` only) paints without raising.  The marker is
    drawn under ``resetTransform`` in device pixels via ``view.mapFromScene``,
    matching the screen-constant handle sizing the plan view has always used
    (so it stays constant across zoom).

    Args:
        painter: The active ``QPainter`` for the foreground pass.
        view: The ``QGraphicsView`` whose foreground is being painted;
            must provide ``mapFromScene``.
        snap_result: An :class:`OsnapResult` (or ``None``).  When ``None``,
            nothing is drawn.
    """
    if snap_result is None:
        return

    snap_type = snap_result.snap_type
    point = snap_result.point

    # ── 1. Source-item trace (scene coordinates — no resetTransform) ──────────
    src_item = getattr(snap_result, "source_item", None)
    src_lines = getattr(snap_result, "source_lines", None)
    if src_item is not None or src_lines:
        color = QColor(SNAP_COLORS.get(snap_type, "#aaaaaa"))
        trace_pen = QPen(color, 1)
        trace_pen.setStyle(Qt.PenStyle.DashLine)
        trace_pen.setCosmetic(True)
        painter.save()
        painter.setPen(trace_pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # If source_lines are provided (Phase 4 intersections),
        # draw only the participating segments instead of full items.
        if src_lines:
            for seg in src_lines:
                painter.drawLine(seg)
        else:
            # Draw all source items (source_item + optional source_item2)
            _sources = [src_item]
            _src2 = getattr(snap_result, "source_item2", None)
            if _src2 is not None:
                _sources.append(_src2)
            for src in _sources:
                if isinstance(src, QGraphicsLineItem):
                    ln = src.line()
                    p1 = src.mapToScene(ln.p1())
                    p2 = src.mapToScene(ln.p2())
                    painter.drawLine(QLineF(p1, p2))
                elif isinstance(src, QGraphicsEllipseItem):
                    painter.drawEllipse(src.mapRectToScene(src.rect()))
                elif isinstance(src, QGraphicsPathItem):
                    # Draw only segments adjacent to snap point,
                    # not the entire path (avoids lighting up a
                    # whole DXF rectangle for one corner snap).
                    sp = point
                    path = src.path()
                    n = path.elementCount()
                    best_segs = []
                    tol_sq = 1.0  # 1 mm² scene tolerance
                    for si in range(n - 1):
                        e1 = path.elementAt(si)
                        e2 = path.elementAt(si + 1)
                        p1 = src.mapToScene(QPointF(e1.x, e1.y))
                        p2 = src.mapToScene(QPointF(e2.x, e2.y))
                        d1 = (p1.x() - sp.x()) ** 2 + (p1.y() - sp.y()) ** 2
                        d2 = (p2.x() - sp.x()) ** 2 + (p2.y() - sp.y()) ** 2
                        mx = (p1.x() + p2.x()) * 0.5
                        my = (p1.y() + p2.y()) * 0.5
                        dm = (mx - sp.x()) ** 2 + (my - sp.y()) ** 2
                        if d1 < tol_sq or d2 < tol_sq or dm < tol_sq:
                            best_segs.append(QLineF(p1, p2))
                    if best_segs:
                        for seg in best_segs:
                            painter.drawLine(seg)
                    else:
                        painter.drawPath(src.mapToScene(src.path()))
                elif isinstance(src, QGraphicsRectItem):
                    painter.drawRect(src.mapRectToScene(src.rect()))

        painter.restore()

    # ── 2. Marker glyph (viewport/device coordinates) ─────────────────────────
    color  = QColor(SNAP_COLORS.get(snap_type, "#ffffff"))
    marker = SNAP_MARKERS.get(snap_type, "square")
    vp     = view.mapFromScene(point)
    x, y   = vp.x(), vp.y()
    s      = 6   # half-size in screen pixels

    painter.save()
    painter.resetTransform()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    pen = QPen(color, 2)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    painter.setPen(pen)

    # Filled glyph variant for WallSegment face-corner / face-mid targets
    # (§8.2 of the snap engine spec, amended: *filled* = face / secondary,
    # *outlined* = centerline / default).
    _name = getattr(snap_result, "name", None)
    if _name is not None and _name.startswith("face-"):
        painter.setBrush(QBrush(color))
    else:
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    if marker == "square":
        painter.drawRect(int(x) - s, int(y) - s, 2 * s, 2 * s)
    elif marker == "circle":
        painter.drawEllipse(int(x) - s, int(y) - s, 2 * s, 2 * s)
    elif marker == "triangle":
        poly = QPolygon([
            QPoint(int(x),     int(y) - s),
            QPoint(int(x) + s, int(y) + s),
            QPoint(int(x) - s, int(y) + s),
        ])
        painter.drawPolygon(poly)
    elif marker == "diamond":
        poly = QPolygon([
            QPoint(int(x),     int(y) - s),
            QPoint(int(x) + s, int(y)),
            QPoint(int(x),     int(y) + s),
            QPoint(int(x) - s, int(y)),
        ])
        painter.drawPolygon(poly)
    elif marker == "cross":
        painter.drawLine(int(x) - s, int(y) - s, int(x) + s, int(y) + s)
        painter.drawLine(int(x) + s, int(y) - s, int(x) - s, int(y) + s)
    elif marker == "right_angle":
        # ⊥ perpendicular symbol: right-angle corner
        painter.drawLine(int(x) - s, int(y), int(x), int(y))
        painter.drawLine(int(x), int(y), int(x), int(y) - s)
        painter.drawRect(int(x) - s, int(y) - s, 2 * s, 2 * s)
    elif marker == "tangent_circle":
        # Tangent: small circle with horizontal line through bottom
        painter.drawEllipse(int(x) - s, int(y) - s, 2 * s, 2 * s)
        painter.drawLine(int(x) - s - 2, int(y) + s, int(x) + s + 2, int(y) + s)
    elif marker == "x_cross":
        # Intersection: X inside a square
        painter.drawRect(int(x) - s, int(y) - s, 2 * s, 2 * s)
        painter.drawLine(int(x) - s, int(y) - s, int(x) + s, int(y) + s)
        painter.drawLine(int(x) + s, int(y) - s, int(x) - s, int(y) + s)

    painter.restore()


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
    # ── ALIGN transient tracking candidates — always BELOW every real snap ──
    # so a real endpoint/intersection/etc. in range always outranks a tracking
    # path. path×path / path×geometry crossings (align_intersection) win over a
    # single-path projection (align_path). See docs/specs/align-placement.md.
    "align_intersection": 20,
    "align_path":         30,
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
    __slots__ = ("cursor", "scale", "aperture_px", "priority_band_px",
                 "best_dist_px", "best_prio", "best_result",
                 "endpoint_candidates", "underlay_geoms", "only_types")

    def __init__(self, cursor: QPointF, scale: float,
                 aperture_px: float, priority_band_px: float,
                 only_types: "set[str] | None" = None):
        self.cursor = cursor
        self.scale = _safe_scale(scale)
        self.aperture_px = aperture_px
        self.priority_band_px = priority_band_px
        self.best_dist_px: float = aperture_px
        self.best_prio: int = 99
        self.best_result: OsnapResult | None = None
        # Scene-coord points of in-tolerance endpoint candidates seen so
        # far. Phase 4 uses this to suppress intersection candidates
        # that land inside the endpoint protection band (§6.3 Change B).
        self.endpoint_candidates: list[QPointF] = []
        # Per-underlay-group UnderlaySnapIndex.query() results, keyed by
        # id(group). Phase 1 fills it; Phase 4 reuses it so each group
        # is queried once per find(), not twice per mousemove.
        self.underlay_geoms: dict[int, list[dict]] = {}
        # Whitelist of snap types that may be returned (None = no restriction)
        self.only_types: "set[str] | None" = only_types

    def check(self, snap_type: str, pt: QPointF, src_item: QGraphicsItem | None,
              name: str | None = None, *,
              src_item2: QGraphicsItem | None = None,
              source_lines: list | None = None,
              aperture_px: float | None = None):
        """Compare a candidate snap against the current best, judged in PIXELS.

        ``aperture_px`` optionally overrides the hard grab-radius cutoff for
        THIS candidate only (ALIGN candidates ride their own wider
        ``ALIGN_PATH_TOL_PX`` band without widening the real-snap aperture).
        The priority-band picker arithmetic is unchanged — a closer real snap
        still wins by priority — so real-snap acceptance never regresses.
        """
        if self.only_types is not None and snap_type not in self.only_types:
            return
        d_scene = math.hypot(pt.x() - self.cursor.x(), pt.y() - self.cursor.y())
        d_px = d_scene * self.scale
        cutoff = self.aperture_px if aperture_px is None else aperture_px
        if d_px > cutoff:
            return  # hard pixel aperture — zoom-invariant grab radius
        if snap_type == "endpoint":
            self.endpoint_candidates.append(pt)
        prio = SNAP_PRIORITY.get(snap_type, 6)
        band = self.priority_band_px
        # Acceptance rules (all judged in px):
        #  1. strictly closer beyond the band  → always win;
        #  2. within the band + higher priority → win (priority-override,
        #     "recall-first": e.g. an intersection beats a closer perpendicular);
        #  3. within the band + EQUAL priority + strictly closer → win.
        # Rule 3 is load-bearing for ALIGN: the acquired point's H/V rays and its
        # extension ray are all ``align_path`` (equal priority) and the H/V rays
        # are always checked first, so without a same-priority closest-wins rule
        # a closer extension foot (2 px) could never displace a farther H/V foot
        # (10 px) once it was the incumbent — extension tracking then silently
        # failed for every non-axis-aligned source (BUG B) while H/V "worked"
        # only because its ray coincides with the extension for axis-aligned
        # geometry.  ``< best_dist_px`` (strict) means a farther equal-priority
        # candidate checked later can never displace a closer incumbent.
        if (d_px < self.best_dist_px - band or
                (d_px < self.best_dist_px + band and prio < self.best_prio) or
                (d_px < self.best_dist_px and prio == self.best_prio)):
            self.best_dist_px = d_px
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
    Nearest SNAP resolver for a QGraphicsScene.

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
        only_types:     "set[str] | None" = None,
        item_filter:    "Callable[[QGraphicsItem], bool] | None" = None,
        held:           "OsnapResult | None" = None,
        align_paths:    "list | None" = None,
        align_aperture_px: float | None = None,
    ) -> OsnapResult | None:
        """Return the nearest snappable point within tolerance, or *None*.

        Args:
            cursor_scene: Cursor position in scene coordinates.
            scene: The QGraphicsScene to search.
            view_transform: Current view transform (m11() gives px/scene scale).
            exclude: Optional single item to skip entirely.
            only_types: Optional whitelist of snap type strings (e.g. ``{"center"}``).
                If provided, only candidates whose snap_type is in this set are
                returned.  ``None`` (default) imposes no restriction.
            item_filter: Optional predicate — ``item_filter(item)`` must return
                True for an item to contribute snap candidates.  ``None``
                (default) allows all items.
            held: Previously-committed snap result (hysteresis anchor).  When
                provided, the engine holds this point unless another candidate
                beats it by ``SNAP_HYSTERESIS_PX`` OR the cursor leaves the
                aperture OR a strictly-higher-priority candidate appears.
                ``None`` (default) means no hysteresis — existing callers are
                unaffected.
            align_paths: Optional list of ALIGN :class:`~firepro3d.align_engine.Ray`
                transient tracking vectors. When provided, ALIGN candidates are
                added INTO the same priority-band picker (not a second pass):
                path×path and path×geometry crossings as ``align_intersection``
                (priority 20) and single-path projections as ``align_path``
                (priority 30) — both well below every real snap (0–7), so a real
                snap in range always wins. Candidates ride the identical pixel
                aperture + hysteresis arithmetic (zoom-invariant). ``None``
                (default) skips the pass entirely — existing callers unaffected.
            align_aperture_px: Optional px grab-radius for ALIGN candidates only.
                ALIGN paths soft-snap at their OWN wider band
                (``ALIGN_PATH_TOL_PX``), separate from the 15px real-snap
                aperture, so a cursor can reach a tracking path from farther away
                without loosening real snaps. ``None`` (default) falls back to
                ``ALIGN_PATH_TOL_PX``. Real-snap acceptance is never affected.
        """
        if not self.enabled:
            return None

        from .constants import ALIGN_PATH_TOL_PX
        align_aperture = (float(ALIGN_PATH_TOL_PX) if align_aperture_px is None
                          else float(align_aperture_px))

        # Aperture is a screen-pixel constant (zoom-invariant). Convert to a
        # scene-unit SEARCH radius, clamped to a perf-only ceiling that never
        # bites at a usable zoom. Acceptance is judged in pixels (see _SnapCtx).
        scale = view_transform.m11()
        aperture_px = float(SNAP_TOLERANCE_PX)
        # ALIGN candidates search a wider rect (their own aperture) — but the
        # real-snap search rect stays at the 15px aperture below.
        search_tol = min(px_to_scene(aperture_px, scale), SNAP_MAX_SCENE_TOL)

        search_rect = QRectF(
            cursor_scene.x() - search_tol, cursor_scene.y() - search_tol,
            search_tol * 2, search_tol * 2,
        )

        priority_band_px = float(SNAP_PRIORITY_BAND_PX)

        # Mutable snap-tracking state shared across phases
        ctx = _SnapCtx(cursor=cursor_scene, scale=scale,
                       aperture_px=aperture_px, priority_band_px=priority_band_px,
                       only_types=only_types)

        # Phase 1 — Scene items (endpoints, midpoints, perpendicular, etc.)
        self._check_scene_items(ctx, scene, search_rect, exclude, item_filter)

        # Phase 2 — Gridline-to-gridline intersections
        gl_items = [gl for gl in getattr(scene, "_gridlines", [])
                     if gl.isVisible() and (exclude is None or gl is not exclude)
                     and (item_filter is None or item_filter(gl))]
        if self.snap_intersection:
            self._check_gridline_intersections(ctx, gl_items)

        # Phase 3 — Gridline point + edge snaps
        self._check_gridline_snaps(ctx, gl_items)

        # Phase 4 — Geometry-to-geometry intersections
        # (_PHASE4_MAX_SEGMENTS inside the method caps the O(n²) pairing)
        if self.snap_intersection:
            self._check_geometry_intersections(ctx, scene, search_rect, exclude,
                                               gl_items, item_filter)

        # Phase 5 — ALIGN transient tracking candidates (into the same picker).
        # Priced below every real snap (see SNAP_PRIORITY), so any real snap in
        # range outranks these; they ride ctx.check's px aperture unchanged, so
        # the acquire/path grab radius is zoom-invariant like all other snaps.
        if align_paths:
            from .align_engine import path_x_path, path_x_segment, project_to_ray
            cur = (cursor_scene.x(), cursor_scene.y())
            # path × path (priority align_intersection = 20)
            for i in range(len(align_paths)):
                for j in range(i + 1, len(align_paths)):
                    p = path_x_path(align_paths[i], align_paths[j])
                    if p is not None:
                        ctx.check("align_intersection", QPointF(*p), None,
                                  source_lines=[_ray_line(align_paths[i]),
                                                _ray_line(align_paths[j])],
                                  aperture_px=align_aperture)
            # path × nearby geometry (priority align_intersection = 20)
            for seg in self._align_geometry_segments(scene, cursor_scene,
                                                     view_transform, item_filter,
                                                     ctx, align_aperture):
                for ray in align_paths:
                    p = path_x_segment(ray, seg[0], seg[1])
                    if p is not None:
                        ctx.check("align_intersection", QPointF(*p), None,
                                  source_lines=[_ray_line(ray)],
                                  aperture_px=align_aperture)
            # single-path projection (priority align_path = 30)
            for ray in align_paths:
                foot, _ = project_to_ray(cur, ray)
                ctx.check("align_path", QPointF(*foot), None,
                          source_lines=[_ray_line(ray)],
                          aperture_px=align_aperture)

        best = ctx.best_result
        if held is None:
            return best
        held_d_px = scene_to_px(
            math.hypot(held.point.x() - cursor_scene.x(),
                       held.point.y() - cursor_scene.y()), scale)
        # A held ALIGN result is released at the ALIGN aperture, not the tighter
        # real-snap aperture, so an on-path hold isn't dropped prematurely.
        held_aperture = (align_aperture
                         if held.snap_type in ("align_intersection", "align_path")
                         else aperture_px)
        if held_d_px > held_aperture:
            return best  # cursor left the held aperture → release the hold
        if best is None:
            return held
        best_prio = SNAP_PRIORITY.get(best.snap_type, 6)
        held_prio = SNAP_PRIORITY.get(held.snap_type, 6)
        if best_prio < held_prio:
            return best  # strictly higher priority always breaks the hold (recall-first)
        # Margin release only fires when best has equal or better priority than held.
        # A lower-priority candidate (worse number) never displaces a held higher-priority
        # snap, regardless of distance — "recall-first: never hide an endpoint that just
        # came into range."
        if best_prio <= held_prio and ctx.best_dist_px < held_d_px - SNAP_HYSTERESIS_PX:
            return best  # beat the hold by the margin (same or better priority tier)
        return held

    # ── Phase methods ──────────────────────────────────────────────────────

    def _check_scene_items(self, ctx: "_SnapCtx", scene: QGraphicsScene,
                           search_rect: QRectF,
                           exclude: QGraphicsItem | None,
                           item_filter: "Callable[[QGraphicsItem], bool] | None" = None):
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
                        if item_filter is not None and not item_filter(item):
                            continue
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

            if item_filter is not None and not item_filter(item):
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
                                       gl_items: list,
                                       item_filter: "Callable[[QGraphicsItem], bool] | None" = None):
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

        # Shared extraction — the same generator ALIGN's path×geometry pass
        # consumes (single home for the search-rect + per-type segment math,
        # respecting _PHASE4_MAX_SEGMENTS). It yields ("seg", …) / ("circle", …)
        # records; here we split them into the two collections phase-4 pairs.
        _overflow = False
        for rec in self._iter_geometry_segments(scene, search_rect, exclude,
                                                gl_items, item_filter, ctx):
            if rec[0] == "seg":
                _segments.append(rec[1])
            else:  # "circle"
                _circles.append(rec[1])
            if len(_segments) > _PHASE4_MAX_SEGMENTS:
                _overflow = True
                break

        # Bail out if segment extraction exploded (batched DXF paths
        # have hundreds of segments per item; O(n²) pairing on 3000+
        # segments freezes the UI).
        if _overflow:
            return

        # Endpoint protection band — §6.3 Change B. Intersection
        # candidates within this radius of any in-tolerance endpoint
        # candidate are suppressed before reaching the picker, so a
        # high-priority intersection can never silently displace an
        # endpoint at (for example) a mitered wall corner.
        # Fixed 6px, independent of the user-tunable aperture (spec §6.3 Change B).
        protection_r = px_to_scene(_ENDPOINT_PROTECTION_PX, ctx.scale)
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
                if ix is not None and not _protected(ix):
                    ctx.check("intersection", ix, src1,
                              src_item2=src2,
                              source_lines=[QLineF(sa1, sa2),
                                            QLineF(sb1, sb2)])

        # Segment–circle intersections
        for center, radius, c_item in _circles:
            for sa1, sa2, src, _pk in _segments:
                for ix in self._line_circle_intersect(sa1, sa2, center, radius):
                    if not _protected(ix):
                        ctx.check("intersection", ix, src,
                                  src_item2=c_item,
                                  source_lines=[QLineF(sa1, sa2)])

    # ── Shared geometry-segment extraction (phase 4 + ALIGN) ─────────────────

    def _iter_geometry_segments(self, scene: QGraphicsScene,
                                search_rect: QRectF,
                                exclude: QGraphicsItem | None,
                                gl_items: list,
                                item_filter: "Callable[[QGraphicsItem], bool] | None",
                                ctx: "_SnapCtx"):
        """Yield near-cursor scene geometry as tagged records.

        The single home for the search-rect + per-entity-type segment/circle
        extraction used by BOTH phase-4 geometry intersections and ALIGN's
        path×geometry crossings. Yields:

            ("seg", (p1, p2, src_item, parent_key))   — a scene-space segment
            ("circle", (center, radius, src_item))    — a circle for line×circle

        ``src_item`` is the QGraphicsItem traced for highlighting; ``parent_key``
        drives same-parent intersection suppression in phase 4 (underlay-index
        segments use ``None``, which is exempt). Callers must honour
        ``_PHASE4_MAX_SEGMENTS`` themselves and stop consuming past the cap; this
        generator does not count for them (it is lazy), but it does apply the
        same per-item early-out the original inline extractor used so a single
        pathological path/underlay can't spew unbounded work before the caller
        breaks. See docs/specs/snapping-engine.md §7.1 and align-placement.md.
        """
        _underlay_tags = ("DXF Underlay", "PDF Underlay")
        _emitted = 0  # running segment count, for the per-item early-out only

        # Include all gridlines (shape is bubbles-only, missed by search_rect)
        for gl in gl_items:
            line = gl.line()
            yield ("seg", (gl.mapToScene(line.p1()),
                           gl.mapToScene(line.p2()), gl, gl))
            _emitted += 1

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
                        if item_filter is not None and not item_filter(item):
                            continue
                        yield item  # no index — process directly
                    continue
                if (isinstance(item, QGraphicsItemGroup)
                        and item.data(0) in _underlay_tags):
                    continue
                if item_filter is not None and not item_filter(item):
                    continue
                yield item

        for item in _phase4_items():
            if isinstance(item, QGraphicsLineItem):
                line = item.line()
                yield ("seg", (item.mapToScene(line.p1()),
                               item.mapToScene(line.p2()), item, item))
                _emitted += 1
            elif isinstance(item, PolylineItem):
                verts = item._points
                for j in range(len(verts) - 1):
                    yield ("seg", (item.mapToScene(verts[j]),
                                   item.mapToScene(verts[j + 1]), item, item))
                    _emitted += 1
            elif isinstance(item, RectangleItem):
                r = item.rect()
                corners = [
                    item.mapToScene(QPointF(r.left(),  r.top())),
                    item.mapToScene(QPointF(r.right(), r.top())),
                    item.mapToScene(QPointF(r.right(), r.bottom())),
                    item.mapToScene(QPointF(r.left(),  r.bottom())),
                ]
                for j in range(4):
                    yield ("seg", (corners[j], corners[(j + 1) % 4],
                                   item, item))
                    _emitted += 1
            elif isinstance(item, WallSegment):
                # Use mitered geometry so joined walls share clean corners
                # instead of crossing each other inside the joint — the
                # root cause of the §7.1 wall-corner false negative.
                try:
                    p1l, p1r, p2r, p2l = item.snap_quad_points()
                    yield ("seg", (p1l, p2l, item, item))
                    yield ("seg", (p1r, p2r, item, item))
                    _emitted += 2
                except (ValueError, AttributeError):
                    pass
            elif isinstance(item, CircleItem):
                yield ("circle", (item._center, item._radius, item))
            elif isinstance(item, RegularPolygonItem):
                verts = item.vertices()
                for j in range(len(verts)):
                    yield ("seg", (verts[j], verts[(j + 1) % len(verts)],
                                   item, item))
                    _emitted += 1
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
                        yield ("seg", (p1, p2, item, item))
                        _emitted += 1
                # Abort during extraction — once over the cap the
                # consumer bails anyway, so stop spending work here.
                if _emitted > _PHASE4_MAX_SEGMENTS:
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
            #
            # ACCEPTED v1 NARROWING (ALIGN path×underlay): this per-group cache
            # is keyed on gid alone and populated by phase-1/4 with the 15px
            # SNAP_TOLERANCE_PX search rect.  When ALIGN reuses it (via
            # _align_geometry_segments, which passes the wider ~20px ALIGN
            # aperture), an underlay group already cached at 15px is NOT
            # re-queried at 20px — so ALIGN path×UNDERLAY crossings only see
            # underlay segments within the 15px rect, a ≤5px sliver short of the
            # full ALIGN band.  Native scene items are re-queried fresh here each
            # frame (not cached this way) and are unaffected.  Deliberately NOT
            # widening the key: keying on (gid, aperture) would re-introduce the
            # double underlay query per mousemove that this cache just removed.
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
                        yield ("seg", (p1, p2, grp, None))
                        _emitted += 1
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
                            yield ("seg", (p1, p2, grp, None))
                            _emitted += 1
                # Abort during extraction — once over the cap the consumer
                # bails anyway, so don't keep extracting thousands more.
                if _emitted > _PHASE4_MAX_SEGMENTS:
                    return

    def _align_geometry_segments(self, scene: QGraphicsScene,
                                 cursor_scene: QPointF,
                                 view_transform: QTransform,
                                 item_filter: "Callable[[QGraphicsItem], bool] | None",
                                 ctx: "_SnapCtx",
                                 aperture_px: float | None = None):
        """Yield (p1, p2) scene-space segments near the cursor for ALIGN.

        Path×geometry crossings project ALIGN rays against nearby real geometry.
        This reuses the exact phase-4 search rect + segment extraction (via the
        shared ``_iter_geometry_segments`` generator) so ALIGN sees the same
        geometry phase-4 does. Respects ``_PHASE4_MAX_SEGMENTS`` (stops past the
        cap). No gridlines are threaded in (ALIGN passes an empty ``gl_items``);
        gridline crossings already surface as real ``intersection`` snaps.

        The MAIN ``find()`` ctx is threaded in so its ``underlay_geoms`` cache —
        already populated by phase 1/4 this same call — is reused here instead of
        re-querying the underlay snap indices (spec: no redundant underlay
        iteration; matters on DXF-heavy scenes when ALIGN is active).
        """
        scale = view_transform.m11()
        # ALIGN path×geometry crossings use the ALIGN aperture for the search
        # rect (wider than the 15px real-snap aperture) so a ray can cross real
        # geometry that lies just outside the real-snap grab radius.
        if aperture_px is None:
            from .constants import ALIGN_PATH_TOL_PX
            aperture_px = float(ALIGN_PATH_TOL_PX)
        search_tol = min(px_to_scene(aperture_px, scale), SNAP_MAX_SCENE_TOL)
        search_rect = QRectF(
            cursor_scene.x() - search_tol, cursor_scene.y() - search_tol,
            search_tol * 2, search_tol * 2,
        )
        _count = 0
        for rec in self._iter_geometry_segments(scene, search_rect, None,
                                               [], item_filter, ctx):
            if rec[0] != "seg":
                continue  # circles have no path×segment crossing here
            p1, p2, _src, _pk = rec[1]
            yield (p1.x(), p1.y()), (p2.x(), p2.y())
            _count += 1
            if _count > _PHASE4_MAX_SEGMENTS:
                return

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

        # ── BlockInstance (insertion origin + transformed geometry vertices) ─
        elif isinstance(item, BlockInstance):
            if self.snap_center:
                # definition origin is local (0,0) — the instance's insertion point
                pts.append(("center", item.mapToScene(QPointF(0.0, 0.0)), None))
            if self.snap_endpoint:
                # ON-CURVE vertices only. addEllipse/addPath emit cubic-bezier
                # CONTROL points (CurveTo/CurveToData) that sit OFF the visible
                # outline — emitting those snapped the cursor to empty space.
                from PyQt6.QtGui import QPainterPath as _QPP
                _on_curve = (_QPP.ElementType.MoveToElement,
                             _QPP.ElementType.LineToElement)
                for _pen, path in item.render_ops():
                    for i in range(path.elementCount()):
                        el = path.elementAt(i)
                        if el.type in _on_curve:
                            pts.append(("endpoint",
                                        item.mapToScene(QPointF(el.x, el.y)), None))

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

        # ── RegularPolygonItem — project onto each polygon edge (must come
        #    before generic QGraphicsPathItem) ──────────────────────────────
        elif isinstance(item, RegularPolygonItem):
            verts = item.vertices()
            for i in range(len(verts)):
                _seg_snap(verts[i], verts[(i + 1) % len(verts)])

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
