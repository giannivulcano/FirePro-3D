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
from .sketch_solver import LIN_TOL, curve_radius

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


def point_handle_at(it, xy) -> str | None:
    """AC3: the name of item *it*'s point handle sitting on *xy* (scene mm,
    within the match tolerance; nearest wins), or None -- a shape click joins
    only when a new handle lands on its snap point."""
    p = QPointF(*xy)
    pts = [(math.hypot(a.x() - p.x(), a.y() - p.y()), ref["h"])
           for kind, ref, a, _b in item_handles(it, curvy=False)
           if kind == "point" and _close(a, p)]
    return min(pts, key=lambda d: d[0])[1] if pts else None


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


def plan_rim(uid: str, curve: str, target: Target) -> list:
    """AC3: a circle rim click on a POINT snap puts that existing point on
    new curve *curve* of item *uid* -- ``point_on_curve`` point-first (D43);
    ``[]`` for an edge / curve target (no point to hold)."""
    if target.kind != "point":
        return []
    return [("point_on_curve", [dict(target.ref), {"uid": uid, "h": curve}])]


_POLY2_TO_LINE = {"v0": "p1", "v1": "p2", "s0": "edge", "m0": "mid"}


def remap_handle(h: str) -> str | None:
    """AD8: a 2-vertex polyline's handle on the LineItem that replaces it."""
    return _POLY2_TO_LINE.get(h)


def plan_hv(a, b, refs) -> list:
    """AC2: ``[("horizontal" | "vertical", refs)]`` when segment *a* -> *b*
    (``(x, y)`` scene mm) is exactly axis-aligned -- the off-axis delta within
    ``LIN_TOL`` (the H / V row's own bar) and the other above it -- else ``[]``
    (a near-miss is never inferred)."""
    dx, dy = abs(float(b[0]) - float(a[0])), abs(float(b[1]) - float(a[1]))
    if dy <= LIN_TOL < dx:
        return [("horizontal", refs)]
    if dx <= LIN_TOL < dy:
        return [("vertical", refs)]
    return []


def item_hv(it, handles: tuple) -> list:
    """AC2: H / V on item *it*'s segment named by *handles* -- one edge name
    (``("edge",)``, ``("s3",)``) or two point names (``("center", "v0")``),
    read from its adapter; ``[]`` for no adapter / uid or an unknown name."""
    uid = getattr(it, "_uid", None)
    ad = adapter_for(it)
    if uid is None or ad is None or len(handles) not in (1, 2):
        return []
    x = np.array(ad.read(it), dtype=float)
    if len(handles) == 1:
        e = ad.edges(it, 0).get(handles[0])
        if e is None:
            return []
        a, b = e[0].eval(x)[0], e[1].eval(x)[0]
    else:
        pts = ad.points(it, 0)
        if handles[0] not in pts or handles[1] not in pts:
            return []
        a, b = pts[handles[0]].eval(x)[0], pts[handles[1]].eval(x)[0]
    return plan_hv(a, b, [{"uid": uid, "h": h} for h in handles])


def rect_drawn_edge(it, base, side_pt, *, from_center: bool) -> str | None:
    """AC2 R2: the rect edge the user drew -- corner variant: the edge holding
    both *base* and *side_pt* (the first side); centre variant: the edge holding
    *side_pt* (the side whose midpoint was clicked). None when none holds it."""
    for kind, ref, a, b in item_handles(it):
        if kind != "edge":
            continue
        if seg_dist(side_pt, a, b) > AUTO_CONSTRAIN_MATCH_TOL_MM:
            continue
        if from_center or seg_dist(base, a, b) <= AUTO_CONSTRAIN_MATCH_TOL_MM:
            return ref["h"]
    return None
