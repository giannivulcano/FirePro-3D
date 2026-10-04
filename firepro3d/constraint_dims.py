"""Persisted Smart Dimensions — parametric-constraint-system.md D48–D55 (CS4).

A ``dim_distance`` constraint is drawn by the selection-readout painter
(``readout_paint``) at the readout's own automatic spot when its edge has a
readout (line length, rect width / height, polyline segment -- D48), else on
a synthetic spec between its two points (a thin dashed reference line joins
two separate points). Display + pick only; the solve lives in
``constraint_controller``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPen

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


@dataclass
class DimEntry:
    """One dim laid out for a view: its id, the spec it draws, the readout
    layout, and whether a dashed reference line joins two separate points."""
    cid: str
    spec: object
    layout: object
    two_point: bool


def dim_entries(view, ctl, by=None, held=None) -> list:
    """Every built dim laid out in *view* (D48/D51: always, any selection).
    A driving dim shows its value (D18: never a different number); a
    Reference one the measured length in parentheses."""
    from .readout_paint import layout_linear
    from .selection_readouts import DimSpec, map_spec, readout_text
    if not ctl.enabled:
        return []
    by = ctl.item_by_uid() if by is None else by
    smgr = getattr(ctl._scene, "scale_manager", None)
    out = []
    for c in ctl.constraints:
        if c.type != "dim_distance" or c.inert:
            continue
        hit = readout_for(ctl, c, by)
        if hit is not None:
            it, spec = hit
            t = held(it) if held is not None else None
            if t is not None and not t.isIdentity():
                spec = map_spec(spec, t)
            two = False
        else:
            ends = ctl.dim_ends(c, by, held)
            if ends is None:
                continue
            a, b = ends
            r0 = c.refs[0] if len(c.refs) == 1 else None
            it0 = by.get(r0.get("uid")) if isinstance(r0, dict) else None
            spec = DimSpec(kind="linear", key=c.id, field="Distance", prefix="",
                           value=0.0, field_kind="dimension",
                           apply=lambda _v: None, a=a, b=b,
                           away=it0.sceneBoundingRect().center() if it0 else None)
            two = len(c.refs) == 2
        measured = math.hypot(spec.b.x() - spec.a.x(), spec.b.y() - spec.a.y())
        shown = c.value if (c.driving and c.value is not None) else measured
        spec = replace(spec, value=float(shown))
        text = readout_text(spec, smgr)
        if not c.driving:
            text = f"({text})"
        out.append(DimEntry(c.id, spec, layout_linear(view, spec, text), two))
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
    """Dashed reference lines (two-point dims), then each label in its state
    colour (viewport px, painter already reset). The dim being edited in the
    HUD is skipped."""
    from .readout_paint import _to_vp, paint_readout
    ro = getattr(ctl._scene, "readouts", None)
    editing = ro.editing_key() if ro is not None else None
    by_id = {c.id: c for c in ctl.constraints}
    diag = ctl.diagnostics()
    for e in dims:
        c = by_id.get(e.cid)
        if c is None or editing == ("dim", e.cid):
            continue
        col = dim_colour(ctl, c, diag, t)
        if e.two_point:
            pen = QPen(t.color("muted"), 1.0)
            pen.setDashPattern([6.0, 4.0])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(_to_vp(view, e.spec.a), _to_vp(view, e.spec.b))
        paint_readout(painter, e.layout, t, color=col)


def dims_rect(view, dims) -> QRectF:
    """Viewport bounds of every dim label + reference line."""
    from .readout_paint import _to_vp, label_path
    out = QRectF()
    for e in dims:
        out = out.united(label_path(e.layout).boundingRect())
        if e.two_point:
            a, b = _to_vp(view, e.spec.a), _to_vp(view, e.spec.b)
            out = out.united(QRectF(a, b).normalized().adjusted(-1, -1, 1, 1))
    return out


def edit_entry(view, ctl, c):
    """A ``ReadoutEntry`` for the HUD edit of dim *c* (its live layout)."""
    from .selection_readouts import ReadoutEntry
    for e in dim_entries(view, ctl):
        if e.cid == c.id:
            return ReadoutEntry(item=None, spec=e.spec, layout=e.layout)
    return None
