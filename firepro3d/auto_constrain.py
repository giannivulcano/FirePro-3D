"""Auto Constrain -- snap -> handle resolution and join planning
(parametric-constraint-system.md §13; design AC1 AD1-AD10).

Pure: reads primitive adapters (``sketch_adapters``) and ``OsnapResult``
fields, never writes the scene. ``ConstraintController.auto_join`` performs
the only write; ``GeometryDrawingController`` captures and plans.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QPointF

from .constants import AUTO_CONSTRAIN_MATCH_TOL_MM
from .sketch_adapters import adapter_for
from .sketch_solver import curve_radius

POINT_SNAPS = frozenset({"endpoint", "midpoint", "center"})   # AD6 -> a point handle
EDGE_SNAPS = frozenset({"nearest", "perpendicular"})          # AD6 -> an edge, else a curve


def seg_dist(p, a, b) -> float:
    """Distance from *p* to segment *ab* (any one unit, QPointF-like)."""
    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p.x() - ax) * dx + (p.y() - ay) * dy) / L2))
    return math.hypot(p.x() - ax - t * dx, p.y() - ay - t * dy)


def item_handles(it, *, curvy: bool = True):
    """Yield one item's ``(kind, ref, a, b)`` handles in scene space.

    point ``(p, None | "mid")`` (``"mid"`` = an edge midpoint, D58), edge
    ``(a, b)``, curve ``(centre, (r, item))`` -- only when *curvy*. Hidden
    handles (text ``ins``, polygon ``radius``, ellipse ``rx`` / ``ry``) never.
    The one enumeration shared by pick mode (``PickState._candidates``) and
    the Auto Constrain resolver.
    """
    uid = getattr(it, "_uid", None)
    ad = adapter_for(it)
    if uid is None or ad is None:
        return
    x = np.array(ad.read(it), dtype=float)
    mids = ad.mid_names(it)
    hidden = ad.hidden_names(it)
    for name, e in ad.points(it, 0).items():
        if name in hidden:                    # CS3c: legacy text ins
            continue
        yield ("point", {"uid": uid, "h": name}, QPointF(*e.eval(x)[0]),
               "mid" if name in mids else None)
    for name, (a, b) in ad.edges(it, 0).items():
        yield ("edge", {"uid": uid, "h": name},
               QPointF(*a.eval(x)[0]), QPointF(*b.eval(x)[0]))
    if curvy:
        for name, cv in ad.curves(it, 0).items():
            if name in hidden:                # CS5 D79: defining circles
                continue
            yield ("curve", {"uid": uid, "h": name},
                   QPointF(*cv.center.eval(x)[0]), (curve_radius(cv, x), it))


@dataclass(frozen=True)
class Target:
    """A resolved snap target (AD6). *point* = the snap point, scene mm."""
    kind: str                 # "point" | "edge" | "curve"
    ref: dict                 # HandleRef (§6.2)
    point: tuple
    perpendicular: bool = False


def _close(p, q) -> bool:
    return math.hypot(p.x() - q.x(), p.y() - q.y()) <= AUTO_CONSTRAIN_MATCH_TOL_MM


def resolve_snap(snap) -> Target | None:
    """AD6: the constraint target of one OSNAP result, or None (silently).

    ``origin`` -> the origin ground; END / MID / CEN -> the source item's point
    handle at the snap point; NEA / PER -> the source's edge whose segment holds
    the point, else a circle / arc curve it lies on. Any other kind, an ALIGN
    or grid result, or a source with no adapter -> None.
    """
    if snap is None:
        return None
    t = snap.snap_type
    p = QPointF(snap.point)
    xy = (p.x(), p.y())
    if t == "origin":
        return Target("point", {"ref": "origin"}, xy)
    if t not in POINT_SNAPS and t not in EDGE_SNAPS:
        return None
    src = snap.source_item
    if src is None:
        return None
    cands = list(item_handles(src))
    if t in POINT_SNAPS:
        pts = [(math.hypot(a.x() - p.x(), a.y() - p.y()), ref)
               for kind, ref, a, _b in cands if kind == "point" and _close(a, p)]
        return Target("point", min(pts, key=lambda d: d[0])[1], xy) if pts else None
    per = t == "perpendicular"
    edges = [(d, ref) for d, ref in ((seg_dist(p, a, b), ref)
                                     for kind, ref, a, b in cands if kind == "edge")
             if d <= AUTO_CONSTRAIN_MATCH_TOL_MM]
    if edges:
        return Target("edge", min(edges, key=lambda d: d[0])[1], xy, perpendicular=per)
    for kind, ref, c, rb in cands:
        if kind != "curve":
            continue
        if abs(math.hypot(p.x() - c.x(), p.y() - c.y()) - rb[0]) <= AUTO_CONSTRAIN_MATCH_TOL_MM:
            return Target("curve", ref, xy)
    return None


def matches(target: Target | None, vertex) -> bool:
    """AD4: a stored target applies only to the vertex at its snap point."""
    return target is not None and _close(QPointF(*target.point), QPointF(vertex))


def plan_joins(uid: str, handle: str, incoming_edge: str | None,
               target: Target) -> list:
    """AD7: ``[(ctype, refs), ...]`` joining new handle *handle* of item *uid*
    to *target*; a PER snap on an edge also makes *incoming_edge* (the new
    segment ending at that vertex) perpendicular to it."""
    me = {"uid": uid, "h": handle}
    if target.kind == "point":
        return [("coincident", [me, dict(target.ref)])]
    out = [("point_on_curve", [me, dict(target.ref)])]          # point-first, D43
    if target.perpendicular and target.kind == "edge" and incoming_edge is not None:
        out.append(("perpendicular", [{"uid": uid, "h": incoming_edge}, dict(target.ref)]))
    return out


_POLY2_TO_LINE = {"v0": "p1", "v1": "p2", "s0": "edge", "m0": "mid"}


def remap_handle(h: str) -> str | None:
    """AD8: a 2-vertex polyline's handle on the LineItem that replaces it."""
    return _POLY2_TO_LINE.get(h)
