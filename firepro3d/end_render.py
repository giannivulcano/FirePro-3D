"""End-type renderer (linetypes.md "Ends"; LT5 design C).

One renderer for raw primitives (Block Editor, plan canvas, paper) and placed
block stroke ops (plain + linetyped): an end type is a block with an ``end``
capability, resolved and drawn at PAINT -- never compiled into the host's op
list (flyweight compile: its size depends on the paint's device scale and
printed factor; ``path_walk.map_piece`` refuses reflection). Each end draws
under ``translate(attach) . rotate(outward) . scale(k) [. scale(1, -1)]``:
origin = the attach point, +X = outward (Q5); k = (the screen factor for a
Fixed-size end on a model canvas; else, on a model canvas, the Model scale
denominator N when the line end or the end type sets one (ET1 Q12); else
the printed factor) x the line's per-end Scale (ET1). All content takes the
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
from .constants import (END_DEF_CACHE_MAX, END_JOIN_TOL_MM, END_XF_CACHE_MAX,
                        FIXED_END_PX_PER_MM)
from .render_op import FILL, PATTERN, STROKE, TEXT
from .stroke_style import ENDS, ResolvedEnd, model_scale_value

SCREEN_FIXED = "fixed"          # EndDef.screen: constant px on model canvases (ET1 Q6)
SCREEN_SCALE = "scale"
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
_RECT: dict = {}     # (pieces, ((EndDef | missing id, mirrored, scale, model_scale), ...), printed, screen, badge) -> QRectF | None


@dataclass(frozen=True)
class EndDef:
    """An end block read for painting (definition-local, attach-relative mm).

    Attributes:
        block_id: The definition read.
        version: Its version at the read.
        screen: ``"fixed"`` (printed mm x FIXED_END_PX_PER_MM at any zoom on
            a model canvas) or ``"scale"`` (printed mm under the Drafting
            rule).
        trim: How far back (authored units) the stroke stops (Q5).
        ops: The block's compiled ops -- origin-relative = attach-relative.
        bounds: ``(x0, y0, x1, y1)`` over every op path, unscaled.
        reach: Farthest ``bounds`` corner from the attach point, unscaled.
        has_stroke: True when any op is a stroke (``_draw_end`` builds its
            scaled pen copy only then).
        model_scale: The end type's Model scale denominator N (1:N) a
            Scale-with-zoom end previews at on a model canvas, or None =
            Project, the scene's drawing scale (ET1 Q12a).
    """
    block_id: str
    version: int
    screen: str
    trim: float
    ops: tuple
    bounds: tuple = (0.0, 0.0, 0.0, 0.0)
    reach: float = 0.0
    has_stroke: bool = False
    model_scale: float | None = None

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
                  SCREEN_FIXED if cap.get("screen") == SCREEN_FIXED else SCREEN_SCALE,
                  float(cap.get("trim", 0.0)), tuple(ops), b, reach,
                  any(op.kind == STROKE for op in ops),
                  model_scale_value(cap.get("model_scale")))
        _CACHE[key] = (ops, res)
        _CACHE.move_to_end(key)
        while len(_CACHE) > END_DEF_CACHE_MAX:
            _CACHE.popitem(last=False)
        return res


def _ok(k: float) -> bool:
    return k > 0.0 and math.isfinite(k)


def model_scale_of(end_def: EndDef, end) -> float | None:
    """The Model scale denominator N a Scale-with-zoom *end_def* drawn as
    *end* previews at on a model canvas: the line end's override, else the
    end type's, else None (Project: the printed factor) -- ET1 Q12a/b."""
    return getattr(end, "model_scale", None) or end_def.model_scale


def end_scales(end_def: EndDef, end, *, printed: float, screen) -> float:
    """k for *end_def* drawn as *end* (a ``ResolvedEnd``), times the line's
    per-end Scale (ET1 spec B). One place decides the base (ET1 Q12a):

    * a model canvas (*screen* not None) and a Fixed-size end -> the screen
      factor (painter units per printed mm);
    * a model canvas and a Model scale (``model_scale_of``) -> its N;
    * else (Project, or any paper pass / preview) -> the printed factor.
    """
    if screen is not None:
        if end_def.screen == SCREEN_FIXED:
            base = screen
        else:
            base = model_scale_of(end_def, end) or printed
    else:
        base = printed
    return float(base) * float(getattr(end, "scale", 1.0) or 1.0)


def end_trims(ends, *, printed: float, screen=None) -> tuple:
    """``(s0, s1)`` painter units the stroke stops short of each end (0 for
    None / missing / unscalable ends)."""
    out = []
    for e in ends:
        ed = EndDef.from_block(e.defn) if e.defn is not None else None
        k = end_scales(ed, e, printed=printed, screen=screen) if ed is not None else 0.0
        out.append(ed.trim * k if ed is not None and _ok(k) else 0.0)
    return (out[0], out[1])


def screen_factor(*, paper_scale, role, device_scale: float):
    """Painter units per printed mm for a Fixed-size end at this paint, or
    None off a model canvas (the LTS-2 scope, ``screen_fixed_here``)."""
    if not _lr.screen_fixed_here(paper_scale=paper_scale, role=role):
        return None
    return FIXED_END_PX_PER_MM / max(float(device_scale), 1e-12)


def short_on_screen(pieces, ends, trims, screen) -> bool:
    """ET1 Q7 (LTS-7 parity): True when a Fixed-size end is drawn at a screen
    factor and the trims consume the whole stroke -- the caller then draws
    the plain stroke and only badges."""
    if screen is None or not pieces or not has_fixed(ends):
        return False                     # no Fixed-size end: never measure
    return trims[0] + trims[1] >= pw.total_length(pieces)


def has_fixed(ends) -> bool:
    """True when any drawable end of *ends* is On screen Fixed size."""
    for e in ends:
        if e.defn is not None:
            ed = EndDef.from_block(e.defn)
            if ed is not None and ed.screen == SCREEN_FIXED:
                return True
    return False


def badges_only(ends) -> tuple:
    """*ends* with every drawable end dropped (badges kept)."""
    return tuple(ResolvedEnd(None, e.missing_id, e.mirrored, e.scale, e.model_scale)
                 for e in ends)


def mark_screen_ends(item, drew: bool) -> None:
    """Record on *item* (and its scene's ``_screen_end_items``) whether it
    draws a Fixed-size end at a screen factor (ET1 spec C): the view's zoom
    hook re-prepares exactly those items. Callers invoke it only with a
    screen factor (a paper pass never touches the mark): a paint with what
    it drew, a bounds read with True when it bounded a Fixed-size end (the
    zoom can change before the first paint). A True mark taken outside a
    scene registers on the next call inside one. *item* initialises
    ``_screen_ends`` False."""
    if drew == item._screen_ends and not drew:
        return
    reg = getattr(item.scene(), "_screen_end_items", None)
    if drew == item._screen_ends and (reg is None or item in reg):
        return
    item._screen_ends = drew
    if reg is not None:
        (reg.add if drew else reg.discard)(item)


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


def paint_ends(painter, pieces, ends, pen, *, printed: float, screen=None,
               scene=None, badges: bool = True) -> bool:
    """Draw each resolved end of *pieces* (painter-local) with *pen*.

    *ends* = ``(start, finish)`` ``ResolvedEnd``s. A missing end draws the
    canvas-only missing glyph at its attach point (never on a paper pass;
    *badges* False skips it -- the selection-highlight pass). Ends are never
    LOD-dropped. Leaves the painter state as found.

    Returns:
        True when a Fixed-size end drew at the screen factor (its scene
        bounds follow the zoom -- ``mark_screen_ends``).
    """
    if not pieces:
        return False
    badge = badges and not _pd.paper_pass_active()
    drew_screen = False
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
        k = end_scales(ed, e, printed=printed, screen=screen)
        if not _ok(k):
            continue
        t = _end_xf(pieces, which, ed.trim * k, k, e.mirrored)
        if t is None:
            continue
        _draw_end(painter, ed, t, k, pen, scene)
        if screen is not None and ed.screen == SCREEN_FIXED:
            drew_screen = True
    return drew_screen


def ends_rect(pieces, ends, *, printed: float, screen=None,
              badge: float = 0.0) -> QRectF | None:
    """Painter-local bounds of the ends drawn on *pieces* (exact frame-mapped
    op bounds; a missing end: +-*badge* around its attach point), or None.

    Memoised on (pieces, each end's ``EndDef`` (its Model scale included) /
    missing id + mirrored + scale + Model scale override, factors, badge) --
    every input -- returning a copy (callers may adjust it)."""
    key = (pieces, tuple((EndDef.from_block(e.defn) if e.defn is not None
                          else e.missing_id, e.mirrored, e.scale, e.model_scale)
                         for e in ends),
           printed, screen, badge)
    r = _RECT.get(key, False)
    if r is False:
        r = _ends_rect(pieces, ends, printed, screen, badge)
        if len(_RECT) >= END_XF_CACHE_MAX:
            _RECT.clear()
        _RECT[key] = r
    return QRectF(r) if r is not None else None


def _ends_rect(pieces, ends, printed, screen, badge) -> QRectF | None:
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
                k = end_scales(ed, e, printed=printed, screen=screen)
                t = _end_xf(pieces, which, ed.trim * k, k, e.mirrored) if _ok(k) else None
                if t is not None:
                    x0, y0, x1, y1 = ed.bounds
                    q = t.mapRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        if q is not None:
            r = q if r is None else r.united(q)
    return r


def ends_reach(ends, *, printed: float, screen=None, badge: float = 0.0,
               model: bool = True) -> float:
    """Largest distance any drawn end reaches from its attach point (the
    radial bounds pad of a placed block). ``printed=1.0, screen=None``
    gives every end's unit reach; ``printed=0.0, screen=1.0, model=False``
    the unit reach of the Fixed-size ends alone; ``printed=1.0, screen=0.0,
    model=False`` that of the Project Scale-with-zoom ends alone;
    ``printed=0.0, screen=0.0`` the model-canvas reach (painter units) of
    the Model-scaled ends alone (ET1 Q12; an unscalable k skips the end).
    *model* False skips every end a Model scale sizes at this *screen*."""
    reach = 0.0
    for e in ends:
        if e.defn is None:
            if e.missing_id:
                reach = max(reach, badge)
            continue
        ed = EndDef.from_block(e.defn)
        if ed is None:
            continue
        if (not model and screen is not None and ed.screen != SCREEN_FIXED
                and model_scale_of(ed, e)):
            continue
        k = end_scales(ed, e, printed=printed, screen=screen)
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
