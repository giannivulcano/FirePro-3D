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


def readout_key(item, h) -> str | None:
    """The selection-readout ``DimSpec.key`` an edge handle *h* of *item*
    reports, or None (no readout: polygon side, a point handle)."""
    from .geometry_2d import LineItem, PolylineItem, RectangleItem
    if not isinstance(h, str):
        return None
    if isinstance(item, LineItem):                 # reference lines too (RG1)
        return "length" if h == "edge" else None
    if isinstance(item, RectangleItem):
        return _RECT_KEYS.get(h)
    if isinstance(item, PolylineItem) and h.startswith("s") and h[1:].isdigit():
        return f"seg:{h[1:]}"
    return None


def readout_for(ctl, c, by=None):
    """``(item, DimSpec)`` of the readout a single-edge dim maps onto (D48/
    D55: its setter is the typed-edit anchor law), else None."""
    refs = c.refs if isinstance(c.refs, list) else []
    if len(refs) != 1 or not isinstance(refs[0], dict) or sm.is_ground(refs[0]):
        return None
    by = ctl.item_by_uid() if by is None else by
    it = by.get(refs[0].get("uid"))
    key = readout_key(it, refs[0].get("h")) if it is not None else None
    if key is None:
        return None
    fn = getattr(it, "dimension_specs", None)
    for s in (fn() if callable(fn) else ()):
        if s.key == key:
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


def is_edge_readout(key) -> bool:
    """D57: a selection readout of an edge length (line ``length``, rect
    ``width`` / ``height``, polyline ``seg:<i>``) -- Smart Dimension owns these
    in the Block Editor, so the transient readout no longer shows them."""
    return isinstance(key, str) and (key in ("length", "width", "height")
                                     or key.startswith("seg:"))


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


def dim_entries(view, ctl, by=None, held=None) -> list:
    """Every built dim laid out in *view* (D48/D51: always, any selection;
    CS4b D60-D62 drawn graphic at its stored or auto offset). A driving dim
    shows its value (D18: never a different number); a Reference one the
    measured length in parentheses."""
    from . import dim_graphics as dg
    from .selection_readouts import DimSpec, map_spec, readout_text
    if not ctl.enabled:
        return []
    by = ctl.item_by_uid() if by is None else by
    from .geometry_2d import LineItem
    smgr = getattr(ctl._scene, "scale_manager", None)
    ed = dg.terminator_def()
    tlen, reach = dg.terminator_length_px(ed), dg.terminator_reach_px(ed)
    out = []
    for c in ctl.constraints:
        if c.type != "dim_distance" or c.inert:
            continue
        ends = ctl.dim_ends(c, by, held)
        if ends is None:
            continue
        a, b = ends
        r0 = c.refs[0] if len(c.refs) == 1 else None
        it0 = by.get(r0.get("uid")) if isinstance(r0, dict) else None
        # D62 auto side: away from a shape's centre; a line's centre lies on
        # its own edge, so a line (like a two-point dim) takes screen-up.
        away = (it0.sceneBoundingRect().center()
                if it0 is not None and not isinstance(it0, LineItem) else None)
        hit = readout_for(ctl, c, by)
        if hit is not None:
            it, spec = hit
            t = held(it) if held is not None else None
            if t is not None and not t.isIdentity():
                spec = map_spec(spec, t)
        else:
            spec = DimSpec(kind="linear", key=c.id, field="Distance", prefix="",
                           value=0.0, field_kind="dimension",
                           apply=lambda _v: None, a=a, b=b, away=away)
        measured = math.hypot(b.x() - a.x(), b.y() - a.y())
        shown = c.value if (c.driving and c.value is not None) else measured
        spec = replace(spec, value=float(shown), a=a, b=b)   # HUD spec = drawn points
        text = readout_text(spec, smgr)
        if not c.driving:
            text = f"({text})"
        g = dg.layout_dim(view, a, b, dg.offset_of(c.label), text, away=away, tlen=tlen)
        out.append(DimEntry(c.id, spec, g.label, g, ed, reach))
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


def paint_preview(painter, view, ctl, refs, cursor_vp, t) -> None:
    """CS4b D63: the pending dim drawn at the cursor's offset, ``dimension``."""
    from . import dim_graphics as dg
    from .selection_readouts import DimSpec, readout_text
    ends = ctl.dim_ends(sm.Constraint.new("dim_distance", refs))
    if ends is None:
        return
    a, b = ends
    inv, _ok = view.viewportTransform().inverted()
    off = dg.signed_offset(a, b, inv.map(QPointF(cursor_vp)))
    spec = DimSpec(kind="linear", key="preview", field="Distance", prefix="",
                   value=math.hypot(b.x() - a.x(), b.y() - a.y()),
                   field_kind="dimension", apply=lambda _v: None, a=a, b=b)
    text = readout_text(spec, getattr(ctl._scene, "scale_manager", None))
    ed = dg.terminator_def()
    g = dg.layout_dim(view, a, b, off, text, tlen=dg.terminator_length_px(ed))
    dg.paint_dim(painter, g, t.color("dimension"), t, ed)


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
    for e in dim_entries(view, ctl):
        if e.cid == c.id:
            return ReadoutEntry(item=None, spec=e.spec, layout=e.layout)
    return None
