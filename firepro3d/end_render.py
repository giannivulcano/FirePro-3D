"""End-type renderer (linetypes.md "Ends"; LT5 design C).

One renderer for raw primitives (Block Editor, plan canvas, paper) and placed
block stroke ops (plain + linetyped): an end type is a block with an ``end``
capability, resolved and drawn at PAINT -- never compiled into the host's op
list (flyweight compile: its size depends on the paint's weight and printed
factor; ``path_walk.map_piece`` refuses reflection). Each end draws under
``translate(attach) . rotate(outward) . scale(k) [. scale(1, -1)]``: origin =
the attach point, +X = outward (Q5); k = the printed factor (Fixed) or the
line's pen width in painter units (Weight-relative). All content takes the
using line's colour and resolved width (Q7).
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QTransform

from . import hatch_render as _hr
from . import linetype_render as _lr
from . import paper_display as _pd
from . import path_walk as pw
from .constants import END_DEF_CACHE_MAX, END_JOIN_TOL_MM, END_XF_CACHE_MAX
from .render_op import FILL, PATTERN, STROKE, TEXT
from .stroke_style import ENDS

FIXED = "fixed"
WEIGHT_RELATIVE = "weight_relative"
NO_TRIMS = (0.0, 0.0)
_NO_BRUSH = Qt.BrushStyle.NoBrush

# (id, version) -> (compiled ops list, EndDef); LRU, END_DEF_CACHE_MAX.
# A hit only when the held list *is* the definition's current one: an origin
# move recompiles without a version bump (the LinetypeDef idiom); holding the
# list keeps its identity from being recycled.
_CACHE: OrderedDict = OrderedDict()

# Value-keyed paint memos (END_XF_CACHE_MAX, cleared when full): pieces are
# frozen dataclasses hashing by value, so equal geometry hits and an edited
# stroke (new pieces) misses -- no invalidation needed.
_XF: dict = {}       # (pieces, which, trim, k, mirrored) -> QTransform | None
_RECT: dict = {}     # (pieces, ((EndDef | missing id, mirrored), ...), ff, wf, badge) -> QRectF | None


@dataclass(frozen=True)
class EndDef:
    """An end block read for painting (definition-local, attach-relative mm).

    Attributes:
        block_id: The definition read.
        version: Its version at the read.
        size: ``"fixed"`` (1 authored mm = 1 printed mm) or
            ``"weight_relative"`` (1 authored mm = 1 x the line's weight).
        trim: How far back (authored units) the stroke stops (Q5).
        ops: The block's compiled ops -- origin-relative = attach-relative.
        bounds: ``(x0, y0, x1, y1)`` over every op path, unscaled.
        reach: Farthest ``bounds`` corner from the attach point, unscaled.
        has_stroke: True when any op is a stroke (``_draw_end`` builds its
            scaled pen copy only then).
    """
    block_id: str
    version: int
    size: str
    trim: float
    ops: tuple
    bounds: tuple = (0.0, 0.0, 0.0, 0.0)
    reach: float = 0.0
    has_stroke: bool = False

    @classmethod
    def from_block(cls, defn) -> "EndDef | None":
        """Read *defn*; None when it is not an end type (no ``end``)."""
        if defn is None:
            return None
        e = getattr(defn, "is_end", None)        # copy-free gate (paint path)
        if not (e if e is not None else getattr(defn, "end", None)):
            return None
        ops = defn.render_ops()
        key = (defn.id, defn.version)
        hit = _CACHE.get(key)
        if hit is not None and hit[0] is ops:
            _CACHE.move_to_end(key)
            return hit[1]
        cap = defn.end or {}                     # the one copy, on a miss only
        xs, ys = [], []
        for op in ops:
            if op.path.isEmpty():
                continue
            r = op.path.controlPointRect()
            xs += (r.left(), r.right())
            ys += (r.top(), r.bottom())
        b = (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)
        reach = max(math.hypot(x, y) for x in (b[0], b[2]) for y in (b[1], b[3]))
        res = cls(defn.id, defn.version,
                  WEIGHT_RELATIVE if cap.get("size") == WEIGHT_RELATIVE else FIXED,
                  float(cap.get("trim", 0.0)), tuple(ops), b, reach,
                  any(op.kind == STROKE for op in ops))
        _CACHE[key] = (ops, res)
        _CACHE.move_to_end(key)
        while len(_CACHE) > END_DEF_CACHE_MAX:
            _CACHE.popitem(last=False)
        return res


def _ok(k: float) -> bool:
    return k > 0.0 and math.isfinite(k)


def end_scales(end_def: EndDef, *, fixed_factor: float,
               weight_factor: float) -> float:
    """k for *end_def*: the printed factor (Fixed) or the line's pen width in
    painter units (Weight-relative)."""
    return float(weight_factor if end_def.size == WEIGHT_RELATIVE else fixed_factor)


def end_trims(ends, *, fixed_factor: float, weight_factor: float) -> tuple:
    """``(s0, s1)`` painter units the stroke stops short of each end (0 for
    None / missing / unscalable ends)."""
    out = []
    for e in ends:
        ed = EndDef.from_block(e.defn) if e.defn is not None else None
        k = end_scales(ed, fixed_factor=fixed_factor,
                       weight_factor=weight_factor) if ed is not None else 0.0
        out.append(ed.trim * k if ed is not None and _ok(k) else 0.0)
    return (out[0], out[1])


def _frame_xf(at, outward, k: float, mirrored: bool) -> QTransform:
    """translate(attach) . rotate(outward) . scale(k) [. scale(1, -1)]."""
    t = QTransform()
    t.translate(at.x(), at.y())
    t.rotate(math.degrees(math.atan2(outward[1], outward[0])))
    t.scale(k, k)
    if mirrored:
        t.scale(1.0, -1.0)
    return t


def _end_xf(pieces, which: str, trim: float, k: float,
            mirrored: bool) -> QTransform | None:
    """The end frame transform of one end (``_frame_xf`` at
    ``path_walk.end_frame``), memoised on its inputs; None when the stroke
    has no frame (no / zero-length pieces)."""
    key = (pieces, which, trim, k, mirrored)
    t = _XF.get(key, False)
    if t is False:
        fr = pw.end_frame(pieces, which, trim)
        t = _frame_xf(fr[0], fr[1], k, mirrored) if fr is not None else None
        if len(_XF) >= END_XF_CACHE_MAX:
            _XF.clear()
        _XF[key] = t
    return t


def _alpha(col: QColor, alpha: int) -> QColor:
    c = QColor(col)
    c.setAlphaF(col.alphaF() * alpha / 255.0)
    return c


def _draw_end(painter, ed: EndDef, t: QTransform, k: float, pen: QPen,
              scene) -> None:
    """Draw *ed*'s ops under end frame *t* with the using line's *pen*.

    Lean (LT5 perf): the scaled pen copy only for an end with a stroke op;
    an opaque fill paints the pen colour straight (no alpha copy / brush).
    """
    sp = None
    if ed.has_stroke:
        sp = pen
        if not pen.isCosmetic():
            sp = QPen(pen)
            sp.setWidthF(pen.widthF() / k)  # the frame's scale(k) must not widen it
    col = pen.color()
    painter.save()
    try:
        painter.setWorldTransform(t, True)
        for op in ed.ops:
            kind = op.kind
            if kind == FILL:
                painter.fillPath(op.path, col if op.alpha == 255
                                 else QBrush(_alpha(col, op.alpha)))
            elif kind == STROKE:
                painter.setPen(sp)
                painter.setBrush(_NO_BRUSH)
                painter.drawPath(op.path)
            elif kind == TEXT:
                painter.fillPath(op.path, col)
            elif op.kind == PATTERN:
                _hr.paint_fill(painter, op.path, scene=scene,
                               tile_ref=op.tile_ref, colour=_alpha(col, op.alpha),
                               origin=op.origin, scale=op.scale)
    finally:
        painter.restore()


def paint_ends(painter, pieces, ends, pen, *, fixed_factor: float,
               weight_factor: float, scene=None, badges: bool = True) -> None:
    """Draw each resolved end of *pieces* (painter-local) with *pen*.

    *ends* = ``(start, finish)`` ``ResolvedEnd``s. A missing end draws the
    canvas-only missing glyph at its attach point (never on a paper pass;
    *badges* False skips it -- the selection-highlight pass). Ends are never
    LOD-dropped. Leaves the painter state as found.
    """
    if not pieces:
        return
    badge = badges and not _pd.paper_pass_active()
    for which, e in zip(ENDS, ends):
        if e.defn is None:
            if e.missing_id and badge:
                fr = pw.end_frame(pieces, which, 0.0)
                if fr is not None:
                    _lr.paint_missing_badge(painter, fr[0])
            continue
        ed = EndDef.from_block(e.defn)
        if ed is None or not ed.ops:
            continue
        k = end_scales(ed, fixed_factor=fixed_factor, weight_factor=weight_factor)
        if not _ok(k):
            continue
        t = _end_xf(pieces, which, ed.trim * k, k, e.mirrored)
        if t is None:
            continue
        _draw_end(painter, ed, t, k, pen, scene)


def ends_rect(pieces, ends, *, fixed_factor: float, weight_factor: float,
              badge: float = 0.0) -> QRectF | None:
    """Painter-local bounds of the ends drawn on *pieces* (exact frame-mapped
    op bounds; a missing end: +-*badge* around its attach point), or None.

    Memoised on (pieces, each end's ``EndDef`` / missing id + mirrored,
    factors, badge) -- every input -- returning a copy (callers may adjust
    it)."""
    key = (pieces, tuple((EndDef.from_block(e.defn) if e.defn is not None
                          else e.missing_id, e.mirrored) for e in ends),
           fixed_factor, weight_factor, badge)
    r = _RECT.get(key, False)
    if r is False:
        r = _ends_rect(pieces, ends, fixed_factor, weight_factor, badge)
        if len(_RECT) >= END_XF_CACHE_MAX:
            _RECT.clear()
        _RECT[key] = r
    return QRectF(r) if r is not None else None


def _ends_rect(pieces, ends, fixed_factor, weight_factor, badge) -> QRectF | None:
    """``ends_rect``'s uncached body."""
    r = None
    for which, e in zip(ENDS, ends):
        q = None
        if e.defn is None:
            if e.missing_id and badge > 0.0:
                fr = pw.end_frame(pieces, which, 0.0)
                if fr is not None:
                    a = fr[0]
                    q = QRectF(a.x() - badge, a.y() - badge, 2 * badge, 2 * badge)
        else:
            ed = EndDef.from_block(e.defn)
            if ed is not None:
                k = end_scales(ed, fixed_factor=fixed_factor,
                               weight_factor=weight_factor)
                t = _end_xf(pieces, which, ed.trim * k, k, e.mirrored) if _ok(k) else None
                if t is not None:
                    x0, y0, x1, y1 = ed.bounds
                    q = t.mapRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        if q is not None:
            r = q if r is None else r.united(q)
    return r


def ends_reach(ends, *, fixed_factor: float, weight_factor: float,
               badge: float = 0.0) -> float:
    """Largest distance any drawn end reaches from its attach point (the
    radial bounds pad of a placed block)."""
    reach = 0.0
    for e in ends:
        if e.defn is None:
            if e.missing_id:
                reach = max(reach, badge)
            continue
        ed = EndDef.from_block(e.defn)
        if ed is None:
            continue
        k = end_scales(ed, fixed_factor=fixed_factor, weight_factor=weight_factor)
        if _ok(k):
            reach = max(reach, ed.reach * k)
    return reach


def trimmed_path(pieces, s0: float, s1: float) -> QPainterPath:
    """*pieces* with *s0* / *s1* cut from their ends as one stroke path:
    abutting pieces stay one connected subpath (joins kept, never caps);
    empty when the trims consume the whole length (Q5)."""
    path = QPainterPath()
    for p in pw.trim_pieces(pieces, s0, s1):
        sub = pw.to_path((p,))
        if sub.isEmpty():
            continue
        if path.isEmpty():
            path = sub
            continue
        a, b = path.currentPosition(), sub.elementAt(0)
        if abs(a.x() - b.x) <= END_JOIN_TOL_MM and abs(a.y() - b.y) <= END_JOIN_TOL_MM:
            path.connectPath(sub)
        else:
            path.addPath(sub)
    return path


def linetype_has_default_end(ref, registry) -> bool:
    """True when linetype *ref* resolves to a linetype block whose repeat
    record names a default end -- the LT5 fast-path gate (False for every
    pre-LT5 linetype). Hot (every paint / boundingRect of a linetyped
    end-less line): one registry get, no repeat-record copy."""
    d = registry.get(ref) if registry is not None else None
    return d is not None and bool(getattr(d, "has_default_ends", False))
