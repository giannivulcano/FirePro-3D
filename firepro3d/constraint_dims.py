"""Persisted Smart Dimensions — parametric-constraint-system.md D48–D55 (CS4).

A ``dim_distance`` constraint is drawn by the selection-readout painter
(``readout_paint``) at the readout's own automatic spot when its edge has a
readout (line length, rect width / height, polyline segment -- D48), else on
a synthetic spec between its two points (a thin dashed reference line joins
two separate points). Display + pick only; the solve lives in
``constraint_controller``.
"""
from __future__ import annotations

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
    if isinstance(item, LineItem):                 # covers ReferenceLineItem
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


def dimmed_keys(ctl) -> set:
    """``{(uid, readout key)}`` every dim already shows (D51: the transient
    readout of the same value is suppressed)."""
    out = set()
    if ctl is None or not getattr(ctl, "enabled", False):
        return out
    by = None
    for c in ctl.constraints:
        if not is_dim(c) or not isinstance(c.refs, list) or len(c.refs) != 1:
            continue
        r = c.refs[0]
        if not isinstance(r, dict) or sm.is_ground(r):
            continue
        by = ctl.item_by_uid() if by is None else by
        it = by.get(r.get("uid"))
        key = readout_key(it, r.get("h")) if it is not None else None
        if key is not None:
            out.add((r.get("uid"), key))
    return out
