"""Persisted Smart Dimensions — parametric-constraint-system.md D48–D55 (CS4).

A ``dim_distance`` constraint is drawn as a dimension (CS4b D60-D66:
witness lines, dim line, end-type terminators, value text --
``dim_graphics``) at its stored ``label.offset`` or the auto offset (D62).
An edge with a selection readout (line length, rect width / height,
polyline segment) keeps that readout's spec for the HUD field and its typed
setter (D55). Display + pick only; the solve lives in
``constraint_controller``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from PyQt6.QtCore import QPointF, QRectF

from . import sketch_model as sm

_RECT_KEYS = {"top": "width", "bottom": "width", "left": "height", "right": "height"}


def is_dim(c) -> bool:
    """A built dimensional constraint (drawn as a label, never a glyph box)."""
    return c.type in sm.VALUED and not c.inert


def readout_key(item, h, ctype="dim_distance") -> str | None:
    """The selection-readout ``DimSpec.key`` a dim of *ctype* on handle *h*
    of *item* maps onto (D55 / CS5 D73 anchor law), or None."""
    from .geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                              PolylineItem, RectangleItem, RegularPolygonItem)
    if not isinstance(h, str):
        return None
    if ctype in ("dim_radius", "dim_diameter"):
        if isinstance(item, (CircleItem, ArcItem)) and h == "curve":
            return "radius"
        if isinstance(item, RegularPolygonItem) and h == "radius":
            return "radius"
        if isinstance(item, EllipseItem):
            return {"rx": "r1", "ry": "r2"}.get(h)
        return None
    if ctype == "dim_arc_angle":
        return "angle" if isinstance(item, ArcItem) and h == "curve" else None
    if isinstance(item, LineItem):                 # reference lines too (RG1)
        return "length" if h == "edge" else None
    if isinstance(item, RectangleItem):
        return _RECT_KEYS.get(h)
    if isinstance(item, PolylineItem) and h.startswith("s") and h[1:].isdigit():
        return f"seg:{h[1:]}"
    return None


def readout_for(ctl, c, by=None):
    """``(item, DimSpec)`` of the readout a single-ref dim maps onto (D48 /
    D55 / CS5 D73: its setter is the typed-edit anchor law), else None. A
    diameter reads its radius readout doubled (value, minimum) and halves
    what it applies."""
    refs = c.refs if isinstance(c.refs, list) else []
    if len(refs) != 1 or not isinstance(refs[0], dict) or sm.is_ground(refs[0]):
        return None
    by = ctl.item_by_uid() if by is None else by
    it = by.get(refs[0].get("uid"))
    key = readout_key(it, refs[0].get("h"), c.type) if it is not None else None
    if key is None:
        return None
    fn = getattr(it, "dimension_specs", None)
    for s in (fn() if callable(fn) else ()):
        if s.key == key:
            if c.type == "dim_diameter":
                s = replace(s, field="Diameter", prefix="Ø", value=2.0 * s.value,
                            minimum=2.0 * s.minimum,
                            apply=lambda v, f=s.apply: f(v / 2.0))
            return it, s
    return None


def _point_id(ref):
    """Hashable identity of one point ref (a primitive handle or a ground)."""
    if sm.is_ground(ref):
        return ("ref", ref.get("ref"))
    return ("uid", ref.get("uid"), ref.get("h"))


def measure_key(c, by):
    """What a distance dim measures, canonically (D56: one dim per measure).

    An edge is its two endpoint handles (a line's ``edge`` == its ``p1``/
    ``p2``; a polyline ``s<i>`` == ``v<i>``/``v<i+1>``), so the edge and its
    own ends compare equal; a rect's opposite edges share one width / height;
    every side of a regular polygon is the same length. Two points compare as
    an unordered pair. None when the refs do not resolve.
    """
    from .geometry_2d import LineItem, PolylineItem, RectangleItem
    refs = c.refs if isinstance(c.refs, list) else []
    if not all(isinstance(r, dict) for r in refs):
        return None
    if c.type in ("dim_radius", "dim_diameter") and len(refs) == 1:
        return ("radial", refs[0].get("uid"), refs[0].get("h"))      # D71: R == Ø
    if c.type == "dim_arc_angle" and len(refs) == 1:
        return ("sweep", refs[0].get("uid"))
    if c.type == "dim_angle" and len(refs) == 2:
        return ("angle", frozenset(_point_id(r) for r in refs))       # any sector
    if c.type == "dim_point_line" and len(refs) == 2:                 # D81
        # Unordered: the same parallel pair picked either way round is one
        # measure, so the point ref's midpoint handle maps back to its edge.
        p, e = refs
        if not sm.is_ground(p):
            p = {"uid": p.get("uid"), "h": mid_edge_name(p.get("h")) or p.get("h")}
        return ("point_line", frozenset((_point_id(p), _point_id(e))))
    if len(refs) == 2:
        return frozenset((_point_id(refs[0]), _point_id(refs[1])))
    if len(refs) != 1 or sm.is_ground(refs[0]):
        return None
    uid, h = refs[0].get("uid"), refs[0].get("h")
    it = by.get(uid)
    if it is None or not isinstance(h, str):
        return None
    if isinstance(it, LineItem) and h == "edge":
        return frozenset((("uid", uid, "p1"), ("uid", uid, "p2")))
    if isinstance(it, RectangleItem) and h in _RECT_KEYS:
        return ("rect", uid, _RECT_KEYS[h])
    if isinstance(it, PolylineItem) and h.startswith("s") and h[1:].isdigit():
        i, n = int(h[1:]), len(getattr(it, "_points", ()))
        j = (i + 1) % n if n else i + 1
        return frozenset((("uid", uid, f"v{i}"), ("uid", uid, f"v{j}")))
    if h.startswith("s") and h[1:].isdigit():          # regular polygon side
        return ("polygon_side", uid)
    return ("uid", uid, h)


_DIM_READOUT_KEYS = ("length", "width", "height", "radius", "r1", "r2", "angle")


def is_dim_readout(key) -> bool:
    """D57 + CS5 D68: a selection readout whose measure a Smart Dimension
    owns -- every readout the 2D primitives report (edge lengths, radius,
    R1 / R2, arc angle, polyline segment ``seg:<i>`` and corner ``ang:<i>``)
    -- so the Block Editor shows none of them."""
    return isinstance(key, str) and (key in _DIM_READOUT_KEYS
                                     or key.startswith(("seg:", "ang:")))


_RECT_SIDES = {frozenset(("tl", "tr")): "top", frozenset(("tr", "br")): "right",
               frozenset(("br", "bl")): "bottom", frozenset(("bl", "tl")): "left"}


def edge_for_points(refs, by):
    """The edge ref whose two ends are exactly the two point *refs* (a line's
    ``p1``/``p2``, a rect's adjacent corners, a polyline ``v<i>``/``v<i+1>``),
    else None -- a two-point dim on them IS that edge's dim (smoke 2026-10-03)."""
    from .geometry_2d import LineItem, PolylineItem, RectangleItem
    if (len(refs) != 2 or not all(isinstance(r, dict) for r in refs)
            or any(sm.is_ground(r) for r in refs)
            or refs[0].get("uid") != refs[1].get("uid")):
        return None
    uid = refs[0].get("uid")
    it = by.get(uid)
    hs = frozenset((refs[0].get("h"), refs[1].get("h")))
    if isinstance(it, LineItem) and hs == {"p1", "p2"}:
        return {"uid": uid, "h": "edge"}
    if isinstance(it, RectangleItem) and hs in _RECT_SIDES:
        return {"uid": uid, "h": _RECT_SIDES[hs]}
    if isinstance(it, PolylineItem):
        n = len(getattr(it, "_points", ()))
        try:
            i, j = sorted(int(h[1:]) for h in hs if h and h.startswith("v"))
        except (TypeError, ValueError):
            return None
        if j == i + 1:
            return {"uid": uid, "h": f"s{i}"}
        if it.is_closed() and i == 0 and j == n - 1:
            return {"uid": uid, "h": f"s{n - 1}"}
    return None


@dataclass
class DimEntry:
    """One dim laid out for a view: its id, the readout spec (HUD field +
    typed setter), the value label layout, the drawn graphic (CS4b D60) and
    the frame's terminator (``EndDef`` or None = the built-in one, resolved
    once per frame build) with its repaint reach in px."""
    cid: str
    spec: object
    layout: object
    graphic: object
    term: object = None
    reach: float = 7.5


def _radial_points(g: DimGeom, angle):
    """D74: (hit, far) of a radial leader at Y-up *angle* (auto when None);
    polygon / ellipse leaders snap to their nearest defining point."""
    from .geometry_2d import ArcItem, EllipseItem, RegularPolygonItem
    it, c = g.item, g.centre
    if isinstance(it, RegularPolygonItem):
        # Inscribed: vertices at rot + k*step (radius R). Circumscribed: the
        # side midpoints at rot + k*step (apothem) -- the radius curve's r.
        base = it._rotation_deg
        dirs = [base + k * 360.0 / it._sides for k in range(it._sides)]
    elif isinstance(it, EllipseItem):
        off = 0.0 if g.h == "rx" else 90.0
        dirs = [it._rotation_deg + off, it._rotation_deg + off + 180.0]
    else:
        dirs = None
    if angle is None:
        angle = (dirs[0] if dirs else
                 it._start_deg + it._span_deg / 2.0 if isinstance(it, ArcItem) else 45.0)
    if dirs:
        angle = min(dirs, key=lambda d: abs((d - angle + 180.0) % 360.0 - 180.0))
    a = math.radians(angle)
    hit = QPointF(c.x() + g.r * math.cos(a), c.y() - g.r * math.sin(a))
    far = QPointF(c.x() - g.r * math.cos(a), c.y() + g.r * math.sin(a))
    return hit, far


def stored_radius(label) -> float | None:
    """D84: the scene-mm arc radius in a dim's ``label``, or None (auto)."""
    r = label.get("radius") if isinstance(label, dict) else None
    ok = isinstance(r, (int, float)) and not isinstance(r, bool) and math.isfinite(r)
    return float(r) if ok and r > 1e-6 else None


def _angle_arc(view, g: DimGeom, helper, radius=None):
    """D75 / D83 / D84: ``(start_deg, span_deg, r_px, dashed)`` of an angle
    dim; *radius* = the stored scene-mm arc radius (None = auto)."""
    s1, s2 = (float(s) for s in helper["dirs"])
    u = (s1 * g.d1[0], s1 * g.d1[1]); v = (s2 * g.d2[0], s2 * g.d2[1])
    au, av = _yup_deg(*u), _yup_deg(*v)
    span = (av - au + 180.0) % 360.0 - 180.0
    start, span = (au, span) if span >= 0 else (av, -span)
    V = g.vertex
    legs = []
    for seg in (g.seg1, g.seg2):
        if seg is not None:
            legs.append(max(math.hypot(q.x() - V.x(), q.y() - V.y()) for q in seg))
    from .readout_paint import _to_vp          # floats: mapFromScene rounds to int px
    C = _to_vp(view, V)
    probe = _to_vp(view, QPointF(V.x() + 1.0, V.y()))
    s = max(math.hypot(probe.x() - C.x(), probe.y() - C.y()), 1e-9)
    from .constants import SELDIM_ARC_REF_FRAC, SELDIM_ARC_REF_MIN_PX
    r_px = (radius * s if radius is not None else
            max(float(SELDIM_ARC_REF_MIN_PX), SELDIM_ARC_REF_FRAC * min(legs) * s))
    dashed = []
    for seg, d in ((g.seg1, u), (g.seg2, v)):
        if seg is None:
            continue
        n = math.hypot(*d)
        ux, uy = d[0] / n, d[1] / n
        r_mm = r_px / s
        P = (V.x() + ux * r_mm, V.y() + uy * r_mm)
        # Signed distance of each segment end along the arm from the vertex.
        ends = sorted(seg, key=lambda q: (q.x() - V.x()) * ux + (q.y() - V.y()) * uy)
        lo = (ends[0].x() - V.x()) * ux + (ends[0].y() - V.y()) * uy
        hi = (ends[1].x() - V.x()) * ux + (ends[1].y() - V.y()) * uy
        tol = 1e-6 * max(r_mm, 1.0)
        if lo - tol <= r_mm <= hi + tol:
            continue                                  # the segment reaches the arc
        if lo > r_mm:                                 # D83: beyond the arc -> to the vertex
            dashed.append((_to_vp(view, ends[0]), C))
        else:                                         # short of it / the far side -> to the arc
            dashed.append((_to_vp(view, ends[1]), _to_vp(view, QPointF(*P))))
    return start, span, r_px, dashed


def entry_for(view, ctl, c, by=None, held=None, smgr=None, ed=None, tlen=7.5,
              reach=7.5):
    """One ``DimEntry`` for any built dim *c* (CS4b linear, CS5 radial /
    sweep / angle), or None when its geometry does not resolve."""
    from . import dim_graphics as dg
    from .geometry_2d import LineItem
    from .selection_readouts import DimSpec, map_spec, readout_text
    g = dim_geom(ctl, c, by, held)
    if g is None:
        return None
    by = ctl.item_by_uid() if by is None else by
    hit = readout_for(ctl, c, by)
    spec = None
    if hit is not None:
        it, spec = hit
        t = held(it) if held is not None else None
        if t is not None and not t.isIdentity():
            spec = map_spec(spec, t)
    measured = ctl.measure(c)
    shown = c.value if (c.driving and c.value is not None) else measured
    if shown is None:
        return None
    if g.kind == "linear":
        a, b = g.a, g.b
        r0 = c.refs[0] if len(c.refs) == 1 else None
        it0 = by.get(r0.get("uid")) if isinstance(r0, dict) else None
        # D62 auto side: away from a shape's centre; a line's centre lies on
        # its own edge, so a line (like a two-point dim) takes screen-up.
        away = (it0.sceneBoundingRect().center()
                if it0 is not None and not isinstance(it0, LineItem) else None)
        if spec is None:
            spec = DimSpec(kind="linear", key=c.id, field="Distance", prefix="",
                           value=0.0, field_kind="dimension",
                           apply=lambda _v: None, a=a, b=b, away=away)
        spec = replace(spec, value=float(shown), a=a, b=b)   # HUD spec = drawn points
        text = readout_text(spec, smgr)
        if not c.driving:
            text = f"({text})"
        gr = dg.layout_dim(view, a, b, dg.offset_of(c.label), text, away=away, tlen=tlen)
        return DimEntry(c.id, spec, gr.label, gr, ed, reach)
    if g.kind == "angle":
        start, span, r_px, dashed = _angle_arc(view, g, c.helper,
                                               stored_radius(c.label))
        spec = DimSpec(kind="angular", key=c.id, field="Angle", prefix="",
                       value=float(shown), field_kind="span", apply=lambda _v: None,
                       maximum=180.0 - 1e-6, center=g.vertex, start_deg=start,
                       span_deg=span)
    if g.kind == "sweep":                                  # readout rule, leg = r
        from .constants import SELDIM_ARC_REF_FRAC, SELDIM_ARC_REF_MIN_PX
        from .readout_paint import _to_vp
        C0 = _to_vp(view, g.centre)
        C1 = _to_vp(view, QPointF(g.centre.x() + 1.0, g.centre.y()))
        px_per_mm = max(math.hypot(C1.x() - C0.x(), C1.y() - C0.y()), 1e-9)
        rs = stored_radius(c.label)                        # D84
        r_px = (rs * px_per_mm if rs is not None else
                max(float(SELDIM_ARC_REF_MIN_PX), SELDIM_ARC_REF_FRAC * g.r * px_per_mm))
        start, span, dashed = g.start_deg, g.span_deg, []
    if spec is None:                       # no readout spec to carry (radial / sweep)
        return None
    text = readout_text(replace(spec, value=float(shown)), smgr)
    if not c.driving:
        text = f"({text})"
    if g.kind in ("angle", "sweep"):
        gr = dg.layout_arc_dim(view, g.vertex if g.kind == "angle" else g.centre,
                               r_px, start, span, text, dashed)
    else:                                                  # radial (D74)
        lab = c.label if isinstance(c.label, dict) else {}
        ang = lab.get("angle")
        ang = float(ang) if isinstance(ang, (int, float)) and not isinstance(ang, bool) else None
        hit_p, far = _radial_points(g, ang)
        spec = replace(spec, value=float(shown))
        gr = dg.layout_radial(view, g.centre, hit_p, text,
                              far=far if c.type == "dim_diameter" else None, tlen=tlen)
    return DimEntry(c.id, spec, gr.label, gr, ed, reach)


def dim_entries(view, ctl, by=None, held=None, only=None) -> list:
    """Every built dim laid out in *view* (D48/D51: always, any selection;
    CS4b D60-D62 linear, CS5 D74/D75 radial and angular). A driving dim shows
    its value (D18: never a different number); a Reference one the measure
    in parentheses. *only*: a set of dim ids to lay out (D82 visibility)."""
    from . import dim_graphics as dg
    if not ctl.enabled:
        return []
    by = ctl.item_by_uid() if by is None else by
    smgr = getattr(ctl._scene, "scale_manager", None)
    ed = dg.terminator_def()
    tlen, reach = dg.terminator_length_px(ed), dg.terminator_reach_px(ed)
    out = []
    for c in ctl.constraints:
        if not is_dim(c) or (only is not None and c.id not in only):
            continue
        e = entry_for(view, ctl, c, by, held, smgr, ed, tlen, reach)
        if e is not None:
            out.append(e)
    return out


def dim_colour(ctl, c, diag, t):
    """D10/D52 + the colour gate: selected > hover > conflict > suppressed >
    Reference > redundant > driving (``dimension``)."""
    if c.id == ctl.selected_id:
        return t.color("selection")
    if c.id == ctl.hover_id:
        return t.color("selection_hover")
    if c.id in ctl.red:
        return t.color("danger")
    if not c.enabled:
        return t.color("faint")
    if not c.driving:
        return t.color("muted")
    if c.id in diag.redundant:
        return t.color("warn")
    return t.color("dimension")


def paint_dims(painter, view, ctl, dims, t) -> None:
    """Each dim in its state colour (D60; viewport px, painter already
    reset). The dim being edited in the HUD is skipped whole (D66)."""
    from . import dim_graphics as dg
    ro = getattr(ctl._scene, "readouts", None)
    editing = ro.editing_key() if ro is not None else None
    by_id = {c.id: c for c in ctl.constraints}
    diag = ctl.diagnostics()
    for e in dims:
        c = by_id.get(e.cid)
        if c is None or editing == ("dim", e.cid):
            continue
        dg.paint_dim(painter, e.graphic, dim_colour(ctl, c, diag, t), t, e.term)


def dims_rect(view, dims) -> QRectF:
    """Viewport bounds of every drawn dim."""
    from . import dim_graphics as dg
    out = QRectF()
    for e in dims:
        out = out.united(dg.bounds(e.graphic, e.reach))
    return out


def paint_preview(painter, view, ctl, pending, cursor_vp, t) -> None:
    """CS4b D63 / CS5: the pending dim (``(ctype, refs)``) drawn as placed at
    the cursor, ``dimension`` colour."""
    from . import dim_graphics as dg
    ctype, refs = pending
    inv, _ok = view.viewportTransform().inverted()
    helper, label = placement_for(ctl, ctype, refs, inv.map(QPointF(cursor_vp)))
    c = sm.Constraint.new(ctype, refs, helper=helper, label=label)
    c.value = ctl.measure(c)
    ed = dg.terminator_def()
    e = entry_for(view, ctl, c, smgr=getattr(ctl._scene, "scale_manager", None),
                  ed=ed, tlen=dg.terminator_length_px(ed))
    if e is not None:
        dg.paint_dim(painter, e.graphic, t.color("dimension"), t, ed)


def point_map_like(op):
    """A scene-point mapper moving a point exactly as *op* moves a line's
    end (``op(item)`` = the tool's own ``manip_rotate`` / ``manip_reflect`` /
    ``manip_scale_about`` call) -- the tool's convention, never re-derived
    (CS4b D65)."""
    def fn(p):
        from .geometry_2d import LineItem
        it = LineItem(QPointF(p), QPointF(p.x() + 1.0, p.y()))
        op(it)
        return QPointF(it._pt1)
    return fn


def edit_entry(view, ctl, c):
    """A ``ReadoutEntry`` for the HUD edit of dim *c* (its live layout)."""
    from .selection_readouts import ReadoutEntry
    e = entry_for(view, ctl, c)
    return ReadoutEntry(item=None, spec=e.spec, layout=e.layout) if e is not None else None


@dataclass
class DimGeom:
    """Scene geometry one dim measures (CS5). ``kind``: ``"linear"`` (a, b),
    ``"radial"`` (centre, r, item, h), ``"sweep"`` (centre, r, start_deg,
    span_deg), ``"angle"`` (vertex, d1, d2, seg1, seg2 -- seg2 None for an
    axis)."""
    kind: str
    a: object = None
    b: object = None
    centre: object = None
    r: float = 0.0
    item: object = None
    h: str = ""
    start_deg: float = 0.0
    span_deg: float = 0.0
    vertex: object = None
    d1: tuple = (0.0, 0.0)
    d2: tuple = (0.0, 0.0)
    seg1: tuple | None = None
    seg2: tuple | None = None


def _isect(p, d, q, e):
    """Intersection of the lines p + t d and q + s e (scene tuples), or None."""
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-12 * max(math.hypot(*d) * math.hypot(*e), 1e-300):
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return (p[0] + t * d[0], p[1] + t * d[1])


def dim_geom(ctl, c, by=None, held=None) -> DimGeom | None:
    """The scene geometry dim *c* measures, or None when its refs do not
    resolve (or two angle edges are parallel / zero-length, D77)."""
    from .constraint_paint import _ref_geom
    refs = c.refs if isinstance(c.refs, list) else []
    by = ctl.item_by_uid() if by is None else by
    if c.type in sm.LINEAR_DIMS:
        e = ctl.dim_ends(c, by, held)
        return DimGeom("linear", a=e[0], b=e[1]) if e is not None else None
    gs = [_ref_geom(r, by, held) for r in refs]
    if any(g is None for g in gs):
        return None
    if c.type in ("dim_radius", "dim_diameter", "dim_arc_angle"):
        if len(gs) != 1 or gs[0][0] != "curve":
            return None
        centre, r = gs[0][1]
        it = by.get(refs[0].get("uid"))
        if c.type == "dim_arc_angle":
            if not hasattr(it, "_span_deg"):
                return None
            return DimGeom("sweep", centre=centre, r=r, item=it,
                           start_deg=float(it._start_deg), span_deg=float(it._span_deg))
        return DimGeom("radial", centre=centre, r=r, item=it, h=refs[0].get("h"))
    if c.type == "dim_angle" and len(gs) == 2 and gs[0][0] == "edge":
        a1, b1 = gs[0][1]
        d1 = (b1.x() - a1.x(), b1.y() - a1.y())
        if gs[1][0] == "axis":
            q, d2, seg2 = (0.0, 0.0), sm.AXIS_DIRS[gs[1][1]], None
        elif gs[1][0] == "edge":
            a2, b2 = gs[1][1]
            q, d2, seg2 = (a2.x(), a2.y()), (b2.x() - a2.x(), b2.y() - a2.y()), (a2, b2)
        else:
            return None
        if math.hypot(*d1) < 1e-9 or math.hypot(*d2) < 1e-9:
            return None
        v = _isect((a1.x(), a1.y()), d1, q, d2)
        if v is None:
            return None
        return DimGeom("angle", vertex=QPointF(*v), d1=d1, d2=d2, seg1=(a1, b1), seg2=seg2)
    return None


def angle_value(g: DimGeom, helper) -> float | None:
    """Unsigned degrees between ``s1·d1`` and ``s2·d2`` (D72)."""
    try:
        s1, s2 = (float(s) for s in helper["dirs"])
    except (KeyError, TypeError, ValueError):
        return None
    u = (s1 * g.d1[0], s1 * g.d1[1]); v = (s2 * g.d2[0], s2 * g.d2[1])
    return math.degrees(abs(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])))


def sector_helper(g: DimGeom, p) -> dict:
    """D72: the sector holding scene point *p* as ``{"dirs", "sign"}``."""
    w = (p.x() - g.vertex.x(), p.y() - g.vertex.y())
    den = g.d1[0] * g.d2[1] - g.d1[1] * g.d2[0]
    al = (w[0] * g.d2[1] - w[1] * g.d2[0]) / den
    be = (g.d1[0] * w[1] - g.d1[1] * w[0]) / den
    s1, s2 = (1 if al >= 0 else -1), (1 if be >= 0 else -1)
    cr = (s1 * g.d1[0]) * (s2 * g.d2[1]) - (s1 * g.d1[1]) * (s2 * g.d2[0])
    return {"dirs": [s1, s2], "sign": 1 if cr >= 0 else -1}


def _yup_deg(dx, dy) -> float:
    return math.degrees(math.atan2(-dy, dx))


def placement_for(ctl, ctype, refs, p):
    """``(helper, label)`` a placement / drag at scene point *p* gives a dim
    of *ctype* on *refs* (D62 offset, D72 sector, D74 leader angle, D84
    angle / sweep radius)."""
    from . import dim_graphics as dg
    c = sm.Constraint.new(ctype, refs)
    g = dim_geom(ctl, c)
    if g is None:
        return {}, None
    if g.kind == "linear":
        return {}, dg.with_offset(None, dg.signed_offset(g.a, g.b, p))
    if g.kind == "radial":
        return {}, {"angle": _yup_deg(p.x() - g.centre.x(), p.y() - g.centre.y())}
    if g.kind == "angle":                                  # D72 sector + D84 radius
        return sector_helper(g, p), {"radius": math.hypot(
            p.x() - g.vertex.x(), p.y() - g.vertex.y())}
    if g.kind == "sweep":                                  # D84
        return {}, {"radius": math.hypot(p.x() - g.centre.x(), p.y() - g.centre.y())}
    return {}, None


_EDGE_MID = {"edge": "mid", "top": "tm", "right": "rm", "bottom": "bm", "left": "lm"}
PARALLEL_SIN = 1e-9


def edge_mid_name(h) -> str | None:
    """The derived midpoint handle (D58) of edge handle *h*: a line ``edge``
    -> ``mid``, ``s<i>`` -> ``m<i>``, a rect / text side -> its mid."""
    if not isinstance(h, str):
        return None
    if h in _EDGE_MID:
        return _EDGE_MID[h]
    return f"m{h[1:]}" if h.startswith("s") and h[1:].isdigit() else None


_MID_TO_EDGE = {m: e for e, m in _EDGE_MID.items()}


def mid_edge_name(h) -> str | None:
    """Reverse of :func:`edge_mid_name`: midpoint handle *h* -> its edge
    handle (``mid`` -> ``edge``, ``m<i>`` -> ``s<i>``, ``tm`` / ``rm`` /
    ``bm`` / ``lm`` -> ``top`` / ``right`` / ``bottom`` / ``left``); None
    when *h* is not a midpoint handle."""
    if not isinstance(h, str):
        return None
    if h in _MID_TO_EDGE:
        return _MID_TO_EDGE[h]
    return f"s{h[1:]}" if h.startswith("m") and h[1:].isdigit() else None


def _parallel_refs(refs, by):
    """D81: ``[second edge's midpoint, first edge | axis]`` when the two
    picked edges (or the edge and the axis) are parallel, else None."""
    from .constraint_paint import _ref_geom
    g1, g2 = _ref_geom(refs[0], by), _ref_geom(refs[1], by)
    if g1 is None or g2 is None or g1[0] != "edge":
        return None
    a1, b1 = g1[1]
    d1 = (b1.x() - a1.x(), b1.y() - a1.y())
    if g2[0] == "axis":
        d2 = sm.AXIS_DIRS[g2[1]]
    elif g2[0] == "edge":
        a2, b2 = g2[1]
        d2 = (b2.x() - a2.x(), b2.y() - a2.y())
    else:
        return None
    n1, n2 = math.hypot(*d1), math.hypot(*d2)
    if n1 < 1e-9 or n2 < 1e-9:
        return None
    if abs(d1[0] * d2[1] - d1[1] * d2[0]) / (n1 * n2) > PARALLEL_SIN:
        return None
    if g2[0] == "axis":
        mid = edge_mid_name(refs[0].get("h"))
        return [{"uid": refs[0]["uid"], "h": mid}, dict(refs[1])] if mid else None
    mid = edge_mid_name(refs[1].get("h"))
    return [{"uid": refs[1]["uid"], "h": mid}, dict(refs[0])] if mid else None


def classify_dim(refs, by):
    """CS5 D69: ``(record type, refs)`` for a completed Smart Dimension
    pick, or None. Normalises polygon centre + vertex / side midpoint and
    ellipse centre + axis end to the hidden radius curves."""
    from .geometry_2d import ArcItem, CircleItem, EllipseItem, RegularPolygonItem
    from .sketch_adapters import adapter_for
    kinds = []
    for r in refs:
        if not isinstance(r, dict):
            return None
        if sm.is_ground(r):
            kinds.append("axis" if r.get("ref") in ("x_axis", "y_axis") else "point")
            continue
        it = by.get(r.get("uid"))
        h = r.get("h")
        if it is None:
            return None
        ad = adapter_for(it)
        kinds.append("point" if h in ad.points(it, 0) else
                     "edge" if h in ad.edges(it, 0) else
                     "curve" if h in ad.curves(it, 0) else None)
    if None in kinds:
        return None
    if kinds == ["edge"]:
        return "dim_distance", list(refs)
    if kinds == ["curve"]:
        it = by.get(refs[0].get("uid"))
        if isinstance(it, CircleItem):
            return "dim_diameter", list(refs)
        if isinstance(it, ArcItem):
            return "dim_radius", list(refs)
        return None
    if kinds in (["edge", "edge"], ["edge", "axis"]):
        par = _parallel_refs(refs, by)                     # D81: parallel -> linear
        if par is not None:
            return "dim_point_line", par
        return "dim_angle", list(refs)
    if kinds == ["point", "curve"]:
        p, cv = refs
        it = by.get(cv.get("uid"))
        if (isinstance(it, ArcItem) and p.get("uid") == cv.get("uid")
                and p.get("h") == "center"):
            return "dim_arc_angle", [cv]
        return None
    if kinds == ["point", "point"]:
        a, b = refs
        if (not sm.is_ground(a) and not sm.is_ground(b)
                and a.get("uid") == b.get("uid")):
            it = by.get(a.get("uid"))
            hs = {a.get("h"), b.get("h")}
            if "center" in hs:
                other = (hs - {"center"}).pop() if len(hs) == 2 else ""
                uid = a.get("uid")
                if isinstance(it, RegularPolygonItem):
                    want = "v" if it._inscribed else "m"
                    if other[:1] == want and other[1:].isdigit():
                        return "dim_radius", [{"uid": uid, "h": "radius"}]
                if isinstance(it, EllipseItem) and other in ("a0", "a1", "b0", "b1"):
                    return "dim_radius", [{"uid": uid, "h": "rx" if other[0] == "a" else "ry"}]
        return "dim_distance", list(refs)
    return None
