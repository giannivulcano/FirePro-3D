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
from PyQt6.QtCore import QPointF, Qt

from .constants import AUTO_CONSTRAIN_MATCH_TOL_MM, GRIDLINE_NEIGHBOUR_ANGLE_TOL_DEG
from .geometry_2d import ArcItem, CircleItem, LineItem
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


def plan_offset(src, copy) -> list:
    """AC4 (D155): the records tying an Offset *copy* to its *src* -- a line
    (reference line included) -> ``parallel`` [copy edge, source edge] + a
    ``dim_point_line`` [copy mid, source edge] (the D81 parallel-pair gap dim,
    measured at add, D50); a circle / arc -> ``concentric`` [copy, source]
    (radii stay free); any other shape, or a missing uid, -> ``[]``."""
    su, cu = getattr(src, "_uid", None), getattr(copy, "_uid", None)
    if su is None or cu is None:
        return []
    if isinstance(src, LineItem) and isinstance(copy, LineItem):
        return [("parallel", [{"uid": cu, "h": "edge"}, {"uid": su, "h": "edge"}]),
                ("dim_point_line", [{"uid": cu, "h": "mid"}, {"uid": su, "h": "edge"}])]
    if isinstance(src, (CircleItem, ArcItem)) and type(copy) is type(src):
        return [("concentric", [{"uid": cu, "h": "curve"}, {"uid": su, "h": "curve"}])]
    return []


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


# -- Slice 3 (G11): wall placement records, plan only --------------------------

def toggle_on() -> bool:
    """AD1: the global Auto Constrain toggle (QSettings)."""
    from PyQt6.QtCore import QSettings
    from .constants import AUTO_CONSTRAIN_DEFAULT, AUTO_CONSTRAIN_KEY
    return QSettings("GV", "FirePro3D").value(
        AUTO_CONSTRAIN_KEY, AUTO_CONSTRAIN_DEFAULT, type=bool)


def infer_on(shift: bool) -> bool:
    """D139: infer on this press = toggle XOR Shift."""
    return toggle_on() != bool(shift)


def plan_ctl(scene):
    """G11: *scene*'s ConstraintController when plan constraints are live
    (never in a Block Editor scene), else None."""
    ctl = getattr(scene, "constraint_ctl", None)
    if ctl is None or not ctl.enabled or ctl.block_editor:
        return None
    return ctl


def plan_on(modifiers) -> bool:
    """D139 for a plan placement: toggle XOR Shift; *modifiers* None (a typed
    completion or a non-press path: copies, paste, the seed) = the toggle."""
    if modifiers is None:
        return toggle_on()
    return infer_on(bool(modifiers & Qt.KeyboardModifier.ShiftModifier))


def plan_commit(scene, records, modifiers, remove=()) -> list:
    """G11 / PD2: add *records* (and delete *remove* ids) through
    ``auto_join`` when :func:`plan_on`; runs before the caller's own
    ``push_undo_state`` (D147). Returns the kept constraints."""
    ctl = plan_ctl(scene)
    if ctl is None or not (records or remove) or not plan_on(modifiers):
        return []
    return ctl.auto_join(records, remove=remove)


def wall_drawn_handles(wall) -> tuple:
    """PD1: ``(end1, end2, edge)`` handle names on the wall's CLICK line
    (``_pt1`` / ``_pt2``): Center -> centerline, Left -> right face,
    Right -> left face (``_WallAdapter._offsets``)."""
    from .wall import ALIGN_LEFT, ALIGN_RIGHT
    a = getattr(wall, "_alignment", None)
    if a == ALIGN_LEFT:
        return ("p1r", "p2r", "face_r")
    if a == ALIGN_RIGHT:
        return ("p1l", "p2l", "face_l")
    return ("p1", "p2", "edge")


def plan_wall_join(wall, idx: int, other, other_idx: int | None = None) -> list:
    """G11: end *idx* of new *wall* joined to *other* -- its end *other_idx*
    (miter, ``coincident``) or, with None, its click line (tee,
    ``point_on_curve``); ``[]`` without uids. Reuses :func:`plan_joins`."""
    wu, ou = getattr(wall, "_uid", None), getattr(other, "_uid", None)
    if wu is None or ou is None:
        return []
    oh = wall_drawn_handles(other)
    if other_idx is None:
        tgt = Target("edge", {"uid": ou, "h": oh[2]}, (0.0, 0.0))
    else:
        tgt = Target("point", {"uid": ou, "h": oh[other_idx]}, (0.0, 0.0))
    return plan_joins(wu, wall_drawn_handles(wall)[idx], None, tgt)


def plan_wall_hv(wall) -> list:
    """G11: ``horizontal`` / ``vertical`` on the click line when exact."""
    uid = getattr(wall, "_uid", None)
    if uid is None:
        return []
    a, b = wall._pt1, wall._pt2
    return plan_hv((a.x(), a.y()), (b.x(), b.y()),
                   [{"uid": uid, "h": wall_drawn_handles(wall)[2]}])


def plan_wall_rect(walls) -> list:
    """PD4: ``perpendicular`` between consecutive rectangle sides (3; a 4th
    is redundant)."""
    out = []
    for a, b in zip(walls, walls[1:]):
        if getattr(a, "_uid", None) and getattr(b, "_uid", None):
            out.append(("perpendicular", [{"uid": a._uid, "h": wall_drawn_handles(a)[2]},
                                          {"uid": b._uid, "h": wall_drawn_handles(b)[2]}]))
    return out


# -- Gridline Auto Constrain (2026-10-28): plan scene only ---------------------

def _gl_vars(gl):
    """(ox, oy, fx, fy): origin + far end, as the solver reads them."""
    return tuple(float(v) for v in adapter_for(gl).read(gl))


def plan_gridline_join(gl, gridlines, constraints=()) -> tuple:
    """R1 / R2 / R6: records for gridline *gl* against the other *gridlines*.

    H / V on its edge when exactly axis-aligned (D148); per side, the nearest
    gridline within ``GRIDLINE_NEIGHBOUR_ANGLE_TOL_DEG`` of parallel (a
    coincident one is skipped) gets ``parallel`` -- unless both are the same
    exact axis -- and a driving ``dim_point_line`` [gl mid, neighbour edge].
    With a neighbour on both sides, every ``dim_point_line`` in
    *constraints* between those two is named for removal (re-chain).

    Returns:
        ``(records, remove_ids)``.
    """
    uid = getattr(gl, "_uid", None)
    if uid is None or adapter_for(gl) is None:
        return [], []
    ox, oy, fx, fy = _gl_vars(gl)
    ln = math.hypot(fx - ox, fy - oy)
    if ln <= LIN_TOL:
        return [], []
    nx, ny = -(fy - oy) / ln, (fx - ox) / ln
    s0 = ox * nx + oy * ny
    ang = math.atan2(fy - oy, fx - ox) % math.pi
    tol = math.radians(GRIDLINE_NEIGHBOUR_ANGLE_TOL_DEG)
    hv = plan_hv((ox, oy), (fx, fy), [{"uid": uid, "h": "edge"}])
    below = above = None                                 # (distance, gridline)
    for o in gridlines:
        if o is gl or getattr(o, "_uid", None) is None or adapter_for(o) is None:
            continue
        v = _gl_vars(o)
        d = abs(math.atan2(v[3] - v[1], v[2] - v[0]) % math.pi - ang)
        if min(d, math.pi - d) > tol:
            continue
        s = v[0] * nx + v[1] * ny - s0
        if abs(s) <= AUTO_CONSTRAIN_MATCH_TOL_MM:
            continue                                     # coincident: no spacing
        if s < 0 and (below is None or -s < below[0]):
            below = (-s, o)
        elif s > 0 and (above is None or s < above[0]):
            above = (s, o)
    recs = list(hv)
    for side in (below, above):
        if side is None:
            continue
        o = side[1]
        v = _gl_vars(o)
        o_hv = plan_hv((v[0], v[1]), (v[2], v[3]), [])
        if not hv or not o_hv or hv[0][0] != o_hv[0][0]:
            recs.append(("parallel", [{"uid": uid, "h": "edge"},
                                      {"uid": o._uid, "h": "edge"}]))
        recs.append(("dim_point_line", [{"uid": uid, "h": "mid"},
                                        {"uid": o._uid, "h": "edge"}]))
    remove = []
    if below is not None and above is not None:
        pair = {below[1]._uid, above[1]._uid}
        remove = [c.id for c in constraints if c.type == "dim_point_line"
                  and {r.get("uid") for r in c.refs if isinstance(r, dict)} == pair]
    return recs, remove


def join_gridlines(scene, new, modifiers) -> list:
    """R7 / R8: auto-join each gridline of *new* as if placed one at a time
    (later ones are not yet neighbours), inside the caller's undo step.
    Returns the kept constraints."""
    ctl = plan_ctl(scene)
    if ctl is None or not new or not plan_on(modifiers):
        return []
    kept = []
    for i, gl in enumerate(new):
        later = {id(g) for g in new[i + 1:]}
        pool = [g for g in scene._gridlines if id(g) not in later]
        recs, remove = plan_gridline_join(gl, pool, ctl.constraints)
        kept += plan_commit(scene, recs, modifiers, remove)
    return kept
