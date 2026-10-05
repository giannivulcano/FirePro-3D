"""Linetype expansion renderer (linetypes.md LT3, H3-c; concept LD-A / LD3).

One renderer for raw primitives (Block Editor) and compiled block ops (plan
canvas, viewports, PDF). Expansion is explicit geometry in the pieces' own
frame — never a QPen dash pattern (width-multiple units collapse). Continuous
strokes never reach this module's expansion (``paint_stroke`` returns False and
the caller draws its unchanged plain stroke).
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainterPath, QPen

from . import path_walk as pw
from .constants import (LINETYPE_AXIS_TOL_MM, LINETYPE_CACHE_MAX,
                        LINETYPE_DOT_MM, LINETYPE_LOD_MIN_PERIOD_PX,
                        LINETYPE_MAX_PERIODS)


@dataclass(frozen=True)
class LinetypeDef:
    """A repeat block read per LT3-3 (definition-local mm)."""
    block_id: str
    version: int
    period: float
    dashes: tuple          # ((start, length), ...)
    dots: tuple            # (pos, ...)
    dash_weight: str | None
    size: str              # "drafting" | "model"

    _CACHE = {}            # (id, version) -> LinetypeDef | None

    @classmethod
    def from_block(cls, defn) -> "LinetypeDef | None":
        """Read *defn*'s unit; None when it is not a well-formed linetype."""
        rep = getattr(defn, "repeat", None)
        if not rep:
            return None
        key = (defn.id, defn.version)
        if key in cls._CACHE:
            return cls._CACHE[key]
        length = float(rep["length"])
        ox, oy = defn.origin
        dashes, dots, weights = [], [], []
        for prim in defn.primitives:
            if prim.get("type") != "draw_line":
                continue
            (x1, y1), (x2, y2) = prim["pt1"], prim["pt2"]
            x1, x2, y1, y2 = x1 - ox, x2 - ox, y1 - oy, y2 - oy
            if abs(y1) > LINETYPE_AXIS_TOL_MM or abs(y2) > LINETYPE_AXIS_TOL_MM:
                continue
            a, b = sorted((x1, x2))
            if b < -LINETYPE_AXIS_TOL_MM or a > length + LINETYPE_AXIS_TOL_MM:
                continue
            a, b = max(a, 0.0), min(b, length)
            if b - a <= LINETYPE_AXIS_TOL_MM:
                dots.append(round(a, 9))
            else:
                dashes.append((round(a, 9), round(b - a, 9)))
                w = (prim.get("style") or {}).get("weight")
                from .stroke_style import is_named_weight
                if is_named_weight(w):
                    weights.append(w)
        if length <= 0 or (not dashes and not dots):
            res = None
        else:
            dash_weight = None
            if weights:
                from .paper_display import resolve_line_weight_mm
                dash_weight = max(weights, key=resolve_line_weight_mm)
            res = cls(defn.id, defn.version, length, tuple(sorted(dashes)),
                      tuple(sorted(dots)), dash_weight, rep["size"])
        cls._CACHE[key] = res
        return res


_EXPAND: OrderedDict = OrderedDict()


def expand(pieces, lt: LinetypeDef, factor: float, anchor: tuple):
    """``(dash_path, dot_path)`` for *pieces* in *lt* scaled by *factor*.

    Cached on (pieces, linetype id + version, factor, anchor); returns the
    same tuple object on a hit.
    """
    key = (tuple(pieces), lt.block_id, lt.version, round(factor, 9),
           (round(anchor[0], 6), round(anchor[1], 6)))
    hit = _EXPAND.get(key)
    if hit is not None:
        _EXPAND.move_to_end(key)
        return hit
    period = lt.period * factor
    dashes = [(s * factor, n * factor) for s, n in lt.dashes]
    dots = [d * factor for d in lt.dots]
    dash_path, dot_path = QPainterPath(), QPainterPath()
    for raw in pieces:
        p = pw.canonical(raw)
        L = pw.length(p)
        if L <= 1e-9:
            continue
        if L / period > LINETYPE_MAX_PERIODS:
            pw.append(dash_path, p)                 # safety cap: continuous
            continue
        ph = pw.phase0(p, anchor)
        k = math.floor(ph / period)
        while k * period - ph < L:
            base = k * period - ph                   # s of this unit's start
            for st, ln in dashes:
                a, b = max(base + st, 0.0), min(base + st + ln, L)
                if b - a > 1e-9:
                    pw.append(dash_path, pw.split(p, a, b))
            for d in dots:
                s = base + d
                if -1e-9 <= s <= L + 1e-9:
                    q = pw.point_at(p, min(max(s, 0.0), L))
                    dot_path.moveTo(q)
                    dot_path.lineTo(q.x() + LINETYPE_DOT_MM, q.y())
            k += 1
    res = (dash_path, dot_path)
    _EXPAND[key] = res
    while len(_EXPAND) > LINETYPE_CACHE_MAX:
        _EXPAND.popitem(last=False)
    return res


def paint_stroke(painter, pieces, lt, pen: QPen, *, factor: float,
                 anchor: tuple) -> bool:
    """Draw *pieces* dashed in *lt* with *pen* (LT3 one paint entry).

    Returns False -- nothing drawn -- when there is no linetype, no pieces, or
    (screen only, ``_lod_ok``) the on-screen period is below
    ``LINETYPE_LOD_MIN_PERIOD_PX``; the caller then draws its unchanged plain
    stroke. Paper passes always expand.
    """
    if lt is None or not pieces:
        return False
    if not _lod_ok(painter, lt.period * factor):
        return False
    dash, dot = expand(pieces, lt, factor, anchor)
    p = QPen(pen)
    p.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(p)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(dash)
    if not dot.isEmpty():
        p.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(p)
        painter.drawPath(dot)
    return True


def _lod_ok(painter, period: float) -> bool:
    """Screen-only LOD (D-L21): paper/PDF passes always expand."""
    from .paper_display import paper_pass_active
    if paper_pass_active():
        return True
    from .hatch_render import _device_scale
    return period * _device_scale(painter) >= LINETYPE_LOD_MIN_PERIOD_PX


def mid_point(pieces) -> QPointF | None:
    """Point at half the total length (missing-linetype badge anchor)."""
    return pw.point_at_total(pieces, pw.total_length(pieces) / 2.0) if pieces else None
