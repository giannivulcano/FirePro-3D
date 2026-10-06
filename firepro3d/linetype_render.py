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

from . import hatch_render as _hr
from . import paper_display as _pd
from . import path_walk as pw
from . import stroke_style as _ss
from .constants import (LINETYPE_AXIS_TOL_MM, LINETYPE_CACHE_MAX,
                        LINETYPE_DEF_CACHE_MAX, LINETYPE_DOT_MM, LINETYPE_LOD_MIN_PERIOD_PX,
                        LINETYPE_MAX_PERIODS)


def axis_role(p1, p2, length: float):
    """LT3-3 role of one unit Line (origin-relative points).

    Returns:
        ``("dash", start, length)`` (clamped to ``[0, length]``),
        ``("dot", x)`` (a zero-length axis Line inside the frame), or None
        (off-axis, wholly outside, or a clamped sliver -- never a dot).
    """
    (x1, y1), (x2, y2) = p1, p2
    tol = LINETYPE_AXIS_TOL_MM
    if abs(y1) > tol or abs(y2) > tol:
        return None
    a, b = sorted((x1, x2))
    if b - a <= tol:
        if -tol <= a <= length + tol:
            return ("dot", round(min(max(a, 0.0), length), 9))
        return None
    a, b = max(a, 0.0), min(b, length)
    if b - a <= tol:
        return None
    return ("dash", round(a, 9), round(b - a, 9))


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
    screen: str = "scale"  # "fixed" | "scale" (LTS-1)

    # (id, version, origin) -> (primitives list, LinetypeDef | None); LRU,
    # LINETYPE_DEF_CACHE_MAX. Origin is in the key: the origin setter moves
    # the unit without a bump. The held primitives list is a hit only when it
    # *is* the definition's list (two copies sharing id + version read apart);
    # holding the ref keeps its identity from being recycled (the
    # ``hatch_render._lattice`` idiom).
    _CACHE = OrderedDict()

    @classmethod
    def from_block(cls, defn) -> "LinetypeDef | None":
        """Read *defn*'s unit; None when it is not a well-formed linetype."""
        rep = getattr(defn, "repeat", None)
        if not rep:
            return None
        ox, oy = defn.origin
        key = (defn.id, defn.version, (ox, oy))
        hit = cls._CACHE.get(key)
        if hit is not None and hit[0] is defn.primitives:
            cls._CACHE.move_to_end(key)
            return hit[1]
        length = float(rep["length"])
        dashes, dots, weights = [], [], []
        for prim in defn.primitives:
            if prim.get("type") != "draw_line":
                continue
            (x1, y1), (x2, y2) = prim["pt1"], prim["pt2"]
            role = axis_role((x1 - ox, y1 - oy), (x2 - ox, y2 - oy), length)
            if role is None:
                continue
            if role[0] == "dot":
                dots.append(role[1])
                continue
            dashes.append((role[1], role[2]))
            w = (prim.get("style") or {}).get("weight")
            if _ss.is_named_weight(w):
                weights.append(w)
        if not (0.0 < length < math.inf) or (not dashes and not dots):
            res = None
        else:
            dash_weight = None
            if weights:
                dash_weight = max(weights, key=_pd.resolve_line_weight_mm)
            res = cls(defn.id, defn.version, length, tuple(sorted(dashes)),
                      tuple(sorted(dots)), dash_weight, rep["size"],
                      rep.get("screen", "scale"))
        cls._CACHE[key] = (defn.primitives, res)
        cls._CACHE.move_to_end(key)
        while len(cls._CACHE) > LINETYPE_DEF_CACHE_MAX:
            cls._CACHE.popitem(last=False)
        return res


_EXPAND: OrderedDict = OrderedDict()


def expand(pieces, lt: LinetypeDef, factor: float, anchor: tuple):
    """``(dash_path, dot_path)`` for *pieces* in *lt* scaled by *factor*.

    Cached on (pieces, the *lt* reading itself, factor, anchor) -- keyed on
    the frozen reading's value, so a re-read that differs (e.g. a moved
    origin without a version bump) never hits a stale expansion. Returns the
    same tuple object on a hit: the paths are shared cached objects and must
    be treated as read-only.
    """
    if not period_ok(lt, factor):
        return QPainterPath(), QPainterPath()   # never walk a bad period
    key = (tuple(pieces), lt, round(factor, 9),
           (round(anchor[0], 6), round(anchor[1], 6)))
    hit = _EXPAND.get(key)
    if hit is not None:
        _EXPAND.move_to_end(key)
        return hit
    period = lt.period * factor
    dashes = [(s * factor, n * factor) for s, n in lt.dashes]
    dots = [d * factor for d in lt.dots]
    dash_path, dot_path = QPainterPath(), QPainterPath()
    # Canonical pieces, arcs / ellipse arcs broken at 0° (rhythm restarts there).
    for p in (q for raw in pieces for q in pw.split_at_zero(raw)):
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

    Returns False -- nothing drawn -- when there is no linetype, no pieces, a
    non-positive / non-finite scaled period, or (screen only, ``_lod_ok``) the on-screen period is below
    ``LINETYPE_LOD_MIN_PERIOD_PX``; the caller then draws its unchanged plain
    stroke. Paper passes always expand.
    """
    if lt is None or not pieces or not period_ok(lt, factor):
        return False
    if not _lod_ok(painter, lt.period * factor):
        return False
    dash, dot = expand(pieces, lt, factor, anchor)
    painter.save()
    try:
        draw_expansion(painter, dash, dot, QPen(pen))
    finally:
        painter.restore()
    return True


def draw_expansion(painter, dash: QPainterPath, dot: QPainterPath,
                   pen: QPen) -> None:
    """Stroke an ``expand`` result: dashes flat-capped, dots round-capped.

    The low-level half of ``paint_stroke`` for callers that already decided
    period / LOD and hold the expansion (``BlockInstance.paint``). Leaves
    the painter's pen and brush changed -- the caller brackets it with
    ``save`` / ``restore`` -- and sets *pen*'s cap style (pass a copy).
    """
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(dash)
    if not dot.isEmpty():
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(dot)


def period_ok(lt: LinetypeDef, factor: float) -> bool:
    """True when the scaled period is positive and finite (else no dashes:
    a zero / negative / NaN / inf length factor would not terminate or
    would draw nothing)."""
    period = lt.period * factor
    return period > 0.0 and math.isfinite(period)


def _lod_ok(painter, period: float) -> bool:
    """Screen-only LOD (D-L21): paper/PDF passes always expand."""
    if _pd.paper_pass_active():
        return True
    return lod_ok_at(period, _hr._device_scale(painter))


def lod_ok_at(period: float, device_scale: float) -> bool:
    """The screen LOD test (D-L21) for a period at a known device scale
    (device px per painter unit); callers handle the paper-pass bypass."""
    return period * device_scale >= LINETYPE_LOD_MIN_PERIOD_PX


def mid_point(pieces) -> QPointF | None:
    """Point at half the total length (missing-linetype badge anchor)."""
    return pw.point_at_total(pieces, pw.total_length(pieces) / 2.0) if pieces else None


# Missing-glyph geometry (mockup option A) in mockup units: authored on a
# 12-unit grid, scaled to LINETYPE_BADGE_PX. The glyph's farthest point from
# its anchor is _BADGE_REACH units (triangle apex / base corners); the bounds
# pad adds _BADGE_AA_PX of antialiasing fringe. One home for both.
_BADGE_GRID = 12.0
_BADGE_REACH = 7.0
_BADGE_AA_PX = 1.0


def _badge_unit() -> float:
    """Device px per mockup unit at the current ``LINETYPE_BADGE_PX``."""
    from . import constants
    return constants.LINETYPE_BADGE_PX / _BADGE_GRID


def badge_pad_px() -> float:
    """Device-px half-extent the missing glyph needs around its anchor: the
    bounds pad of an item that may draw it (the glyph's reach + AA fringe)."""
    return _BADGE_REACH * _badge_unit() + _BADGE_AA_PX


def sync_missing_tooltip(item, missing_id) -> None:
    """Name *missing_id* in *item*'s own tooltip (LT3-10); restore the
    previous tooltip once it resolves again. Only writes on a change."""
    cur = getattr(item, "_lt_tip_id", None)
    if cur == missing_id:
        return
    if missing_id:
        if cur is None:
            item._lt_tip_prev = item.toolTip()
        item.setToolTip(f"Missing linetype: {missing_id} — drawn Continuous")
    else:
        item.setToolTip(getattr(item, "_lt_tip_prev", ""))
    item._lt_tip_id = missing_id


def paint_missing_badge(painter, at: QPointF) -> None:
    """Canvas-only missing-linetype glyph at item point *at* (LT3-10).

    Approved mockup option A (2026-10-04): a filled amber (theme ``warn``)
    triangle with a white '!' drawn as geometry (no font dependency), in
    device space at a fixed ``LINETYPE_BADGE_PX`` size. Callers skip it
    during a paper pass (``paper_display.paper_pass_active``).
    """
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QColor, QPainter, QPolygonF
    from . import theme
    c = painter.transform().map(at)
    k = _badge_unit()                            # mockup geometry: 12-unit grid
    r = _BADGE_REACH * k
    painter.save()
    painter.resetTransform()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.detect().warn))
    painter.drawPolygon(QPolygonF([QPointF(c.x(), c.y() - r),
                                   QPointF(c.x() + r, c.y() + 5 * k),
                                   QPointF(c.x() - r, c.y() + 5 * k)]))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(QRectF(c.x() - 0.9 * k, c.y() - 2.6 * k,
                                   1.8 * k, 4.6 * k), 0.6 * k, 0.6 * k)
    painter.drawEllipse(QPointF(c.x(), c.y() + 3.7 * k), 1.0 * k, 1.0 * k)
    painter.restore()
