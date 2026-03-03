"""
snap_engine.py
==============
Object Snap (OSNAP) engine for FireFlow Pro.

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
    "endpoint":  "#ffff00",   # yellow  – square marker
    "midpoint":  "#00ff88",   # green   – triangle marker
    "center":    "#00eeee",   # cyan    – circle marker
    "quadrant":  "#ff8800",   # orange  – diamond marker
    "nearest":   "#aaaaaa",   # grey    – cross marker
}

SNAP_MARKERS: dict[str, str] = {
    "endpoint":  "square",
    "midpoint":  "triangle",
    "center":    "circle",
    "quadrant":  "diamond",
    "nearest":   "cross",
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
        # Per-type toggles (all on by default)
        self.snap_endpoint:  bool = True
        self.snap_midpoint:  bool = True
        self.snap_center:    bool = True
        self.snap_quadrant:  bool = True
        self.snap_nearest:   bool = False

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
        best_result: OsnapResult | None = None

        def _check(snap_type: str, pt: QPointF, src_item: QGraphicsItem):
            nonlocal best_dist, best_result
            d = math.hypot(pt.x() - cursor_scene.x(), pt.y() - cursor_scene.y())
            if d < best_dist:
                best_dist   = d
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

            # DXF underlay groups — descend into children for snap
            if isinstance(item, QGraphicsItemGroup) and item.data(0) == "DXF Underlay":
                for child in item.childItems():
                    for snap_type, scene_pt in self._collect(child):
                        # _collect already returns scene-mapped points
                        _check(snap_type, scene_pt, child)
                continue

            for snap_type, pt in self._collect(item):
                _check(snap_type, pt, item)

        return best_result

    # ── Internal ─────────────────────────────────────────────────────────────

    def _collect(self, item: QGraphicsItem) -> list[tuple[str, QPointF]]:
        """Return (snap_type, scene_pos) pairs for one item."""

        # Lazy imports to avoid circular dependencies
        try:
            from construction_geometry import (
                LineItem, RectangleItem, CircleItem,
                PolylineItem, ConstructionLine,
            )
        except ImportError:
            LineItem = RectangleItem = CircleItem = PolylineItem = ConstructionLine = None  # type: ignore

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
            if self.snap_center:
                pts.append(("center", item.mapToScene(cen)))
            if self.snap_quadrant:
                pts.append(("quadrant", item.mapToScene(QPointF(br.right(), cen.y()))))
                pts.append(("quadrant", item.mapToScene(QPointF(br.left(),  cen.y()))))
                pts.append(("quadrant", item.mapToScene(QPointF(cen.x(), br.top()))))
                pts.append(("quadrant", item.mapToScene(QPointF(cen.x(), br.bottom()))))

        # ── PolylineItem / any QGraphicsPathItem ──────────────────────────
        elif isinstance(item, QGraphicsPathItem):
            path = item.path()
            n = path.elementCount()
            for i in range(min(n, 512)):
                elem = path.elementAt(i)
                pt   = item.mapToScene(QPointF(elem.x, elem.y))
                if self.snap_endpoint and (i == 0 or i == n - 1):
                    pts.append(("endpoint", pt))
                elif self.snap_midpoint:
                    pts.append(("midpoint", pt))

        return pts

    @staticmethod
    def _line_snaps(item: QGraphicsLineItem) -> list[tuple[str, QPointF]]:
        """Endpoint + midpoint snaps for a QGraphicsLineItem."""
        line = item.line()
        p1  = item.mapToScene(line.p1())
        p2  = item.mapToScene(line.p2())
        mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        return [("endpoint", p1), ("endpoint", p2), ("midpoint", mid)]
