"""RenderOp — one typed draw instruction of a compiled block definition.

hatch-and-fill concept HD4/HD4a: replaces the ``(pen, brush, path)`` tuple and
its ``pen == NoPen ⇒ text`` heuristic. The linetypes ``StrokeOp`` (LT3) is the
``stroke`` half of this same type — extend it, don't fork it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPainterPathStroker, QPen, QTransform

STROKE = "stroke"
FILL = "fill"
PATTERN = "pattern"
TEXT = "text"


def orient_part(t: QTransform) -> tuple:
    """Rotation / reflection part of similarity *t* as ``(m11, m12, m21, m22)``:
    translation dropped, uniform scale divided out (hatch D-A11 block-pose
    exception -- a pattern turns and mirrors with its block, never resizes)."""
    s = math.sqrt(abs(t.m11() * t.m22() - t.m12() * t.m21())) or 1.0
    return (t.m11() / s, t.m12() / s, t.m21() / s, t.m22() / s)


def pattern_orient(frame, *xfs) -> QTransform:
    """Pattern axes in the target frame: *frame* (a PATTERN op's
    ``pattern_frame``, None = identity) then each of *xfs*' ``orient_part``."""
    o = QTransform(*frame, 0.0, 0.0) if frame else QTransform()
    for x in xfs:
        o = o * QTransform(*orient_part(x), 0.0, 0.0)
    return o


@dataclass(frozen=True, eq=False)
class RenderOp:
    """A compiled draw op in definition-local, origin-relative coordinates.

    Attributes:
        kind: ``"stroke"`` | ``"fill"`` | ``"pattern"`` | ``"text"``.
        path: Stroke geometry, or the closed clip (fill / pattern), or the
            filled glyph outline (text).
        pen: Authored pen (stroke only).
        colour: Unresolved colour string (stroke / fill / pattern / text).
        alpha: 0–255 opacity for fill / pattern.
        tile_ref: Pattern tile block id or legacy alias (pattern only).
        origin: Pattern origin, definition-local (pattern only).
        scale: Pattern scale multiplier (pattern only).
        weight: Unresolved stroke weight -- a named weight or
            ``"by_linetype"``; None for reference-mode / placeholder ops
            (stroke only, LT2 H-c').
        pieces: Analytic stroke pieces (``path_walk`` Seg / Arc / EllipseArc /
            Curve), definition-local and origin-relative (stroke only, LT3).
        linetype: The style's raw linetype value; None for reference-mode /
            placeholder ops (stroke only, LT3). ``origin`` doubles as a
            stroke's phase anchor -- its defining definition's origin, so a
            nested block keeps its own phase after ``mapped``.
        ends: ``(start, finish)`` normalised end records
            (``{"end", "visible"[, "mirrored"]}``) of an OPEN styled stroke
            (``stroke_style.open_stroke``); None for closed / unstyled /
            reference / placeholder ops (stroke only, LT5). Resolved at
            paint, never compiled into ops (flyweight compile).
        text_frame: ``(cx, cy, baseline_angle)`` of a TEXT op's box --
            centre (definition-local) and Y-up baseline angle (degrees);
            None for non-text ops (block mirror/scale DD6).
        readable: True once a reflecting ``mapped`` un-mirrored this TEXT
            op's glyphs; paint then keeps it upright (DD6).
        pattern_frame: ``orient_part`` of every definition -> parent map a
            PATTERN op went through (nested poses, the mirror / scale
            variant); None = identity, and always None for other kinds
            (hatch D-A11 block-pose exception).
        clip_out: The part of this op hidden by opaque nested blocks above it,
            definition-local (block stacking D1); None = nothing covers it.
            Ops of one covered block share one path object, so paint opens
            one clip per run.
        fixed: Never restyled by a placement / nested-record override on
            any axis -- the red missing-nested placeholder (WM3 D2).
        keep_colour: Never recoloured by a placement / nested-record
            Colour override -- a text's box fill, so the text stays
            readable (WM3 ruling R3). Weight / linetype never touch a FILL
            op anyway, so this is a colour-only exemption (not ``fixed``).

    Ops are shared flyweights — never mutate ``path`` / ``pen`` / ``origin``
    in place; build a new op (``mapped``).
    """

    kind: str
    path: QPainterPath
    pen: QPen | None = None
    colour: str | None = None
    alpha: int = 255
    tile_ref: str | None = None
    origin: QPointF | None = None
    scale: float = 1.0
    weight: str | None = None
    pieces: tuple = ()
    linetype: str | None = None
    ends: tuple | None = None
    text_frame: tuple | None = None
    readable: bool = False
    pattern_frame: tuple | None = None
    clip_out: QPainterPath | None = None
    fixed: bool = False
    keep_colour: bool = False

    def mapped(self, t: QTransform, clips: dict | None = None) -> "RenderOp":
        """This op mapped through a similarity *t* (rigid x uniform scale,
        possibly reflecting -- block mirror / scale, design DD5 / DD6).

        A reflecting *t* toggles open-stroke ends' ``mirrored`` flag (no
        start / finish swap: ``map_piece`` keeps the walking direction) and
        un-mirrors TEXT glyphs about their own box-vertical axis so text
        never reads backwards (sets ``readable``).

        Args:
            t: The similarity map (definition-local -> target frame).
            clips: Optional memo, source clip id -> mapped clip, so a mapped
                list keeps its shared clip objects.

        Returns:
            A new op; this shared flyweight is never mutated.
        """
        flip = t.m11() * t.m22() - t.m12() * t.m21() < 0
        pieces = self.pieces
        if pieces:
            from .path_walk import map_piece
            pieces = tuple(map_piece(p, t) for p in pieces)
        frame, readable = self.text_frame, self.readable
        if self.kind == TEXT and frame is not None:
            cx, cy, ang = frame
            a = math.radians(ang)
            g = t
            if flip:
                # Box vertical in scene (Y-down) coords for a Y-up baseline
                # angle a is (sin a, cos a); Qt ``A * B`` applies A first.
                from .transform_ghost import reflect_transform
                g = reflect_transform(QPointF(cx, cy),
                                      QPointF(cx + math.sin(a), cy + math.cos(a))) * t
                readable = True
            path = g.map(self.path)
            q0 = g.map(QPointF(cx, cy))
            q1 = g.map(QPointF(cx + math.cos(a), cy - math.sin(a)))
            from .block_pose import norm_deg
            frame = (q0.x(), q0.y(), norm_deg(math.degrees(
                math.atan2(-(q1.y() - q0.y()), q1.x() - q0.x()))))
        else:
            path = t.map(self.path)
        ends = self.ends
        if flip and ends:
            from .stroke_style import toggle_mirrored
            st = {"start": dict(ends[0]), "finish": dict(ends[1])}
            toggle_mirrored(st)
            ends = (st["start"], st["finish"])
        pframe = self.pattern_frame
        if self.kind == PATTERN:
            pframe = orient_part(pattern_orient(pframe, t))
        clip = self.clip_out
        if clip is not None:
            hit = clips.get(id(clip)) if clips is not None else None
            if hit is None:
                hit = t.map(clip)
                if clips is not None:
                    clips[id(clip)] = hit
            clip = hit
        return replace(self, path=path,
                       origin=None if self.origin is None else t.map(self.origin),
                       pieces=pieces, ends=ends, text_frame=frame,
                       readable=readable, pattern_frame=pframe, clip_out=clip)


def apply_overrides(ops, weight=None, linetype=None, colour=None):
    """*ops* with a placement / nested-record override applied (WM2 H2, WM3 D2).

    ``None`` = keep, per axis. Weight / linetype replace styled strokes only
    (text, fill, pattern and unstyled ``weight is None`` strokes are kept).
    *colour* replaces ``op.colour`` on EVERY kind -- styled and imported
    reference strokes (Q2), text, fill, pattern -- with ``by_category``
    written as the internal ``token:blocks`` (resolved at paint) -- except a
    ``keep_colour`` op (a text's box fill, R3). A ``fixed`` op (the
    missing-nested placeholder) is never restyled on any axis. The input
    list and its shared flyweight ops are never mutated; with nothing to
    replace the input list itself is returned (the As Authored fast path).
    """
    if weight is None and linetype is None and colour is None:
        return ops
    kw = {}
    if weight is not None:
        kw["weight"] = weight
    if linetype is not None:
        kw["linetype"] = linetype
    ck = colour
    if colour is not None:
        from .constants import TOKEN_BLOCKS
        from .stroke_style import BY_CATEGORY
        ck = TOKEN_BLOCKS if colour == BY_CATEGORY else colour
    out = []
    for op in ops:
        if op.fixed:
            out.append(op)              # WM3 D2: the placeholder keeps its red
            continue
        k = dict(kw) if kw and op.kind == STROKE and op.weight is not None else {}
        if ck is not None and not op.keep_colour:
            k["colour"] = ck
        out.append(replace(op, **k) if k else op)
    return out


_MASK_FLATTEN = 8.0     # mask grid: curves flatten and points snap at 1/8 mm


def _ring_area(poly) -> float:
    """Absolute area of a ``QPolygonF`` ring."""
    n = poly.size()
    a = 0.0
    for i in range(n):
        u, v = poly[i], poly[(i + 1) % n]
        a += u.x() * v.y() - v.x() * u.y()
    return abs(a) / 2


def ops_mask(ops) -> QPainterPath:
    """The area an opaque block hides, in its ops' frame (block stacking D2,
    amended 2026-11-05): the block's silhouette. Its stroke, fill and pattern
    ink is flattened and snapped to a 1/``_MASK_FLATTEN`` mm grid, stroked at
    ``MASK_GAP_MM`` so a gap narrower than that closes, and only the outer
    outline of each connected piece is kept and filled. Pieces that do not
    touch each get their own outline; a hole inside one stays covered. An
    outline is outset by ``MASK_GAP_MM / 2``. Text never counts.

    Args:
        ops: Compiled ops.

    Returns:
        The mask; empty when *ops* has no ink.
    """
    from .constants import MASK_GAP_MM
    f = _MASK_FLATTEN
    grid = QTransform.fromScale(f, f)
    ink = QPainterPath()
    for op in ops:
        if op.kind not in (STROKE, FILL, PATTERN):
            continue
        closed = op.kind != STROKE
        for poly in op.path.toSubpathPolygons(grid):
            n = poly.size()
            if not n:
                continue
            pts = [QPointF(round(poly[i].x()), round(poly[i].y())) for i in range(n)]
            ink.moveTo(pts[0])
            for q in pts[1:]:                      # a lone point adds no run: no mask
                ink.lineTo(q)
            if closed:
                ink.closeSubpath()
    mask = QPainterPath()
    if ink.isEmpty():
        return mask
    stroker = QPainterPathStroker()
    stroker.setWidth(MASK_GAP_MM * f)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    rings = [r for r in stroker.createStroke(ink).simplified().toSubpathPolygons()
             if r.size() > 2]
    rings.sort(key=_ring_area, reverse=True)
    kept: list = []
    for r in rings:                      # a ring inside a kept ring is a hole
        box = r.boundingRect()
        if not any(kb.contains(box) and k.containsPoint(r[0], Qt.FillRule.OddEvenFill)
                   for k, kb in kept):
            kept.append((r, box))
    mask.setFillRule(Qt.FillRule.WindingFill)
    for r, _box in kept:
        mask.addPolygon(r)
        mask.closeSubpath()
    return QTransform.fromScale(1 / f, 1 / f).map(mask)


def keep_path(frame: QRectF, cover: QPainterPath) -> QPainterPath:
    """Clip path keeping *frame* outside *cover* (odd-even: no boolean, and
    *cover*'s holes stay kept). A *cover* part beyond *frame* is kept too,
    which is harmless: nothing paints outside the frame."""
    p = QPainterPath()
    p.addRect(frame)
    p.addPath(cover)
    p.setFillRule(Qt.FillRule.OddEvenFill)
    return p


def keep_frame(painter, item) -> QRectF:
    """The frame a cover clip keeps, in the item's frame (painter unposed).

    The item's rect is sized at the visible view's zoom; a painter at another
    zoom (second view, print) scales a Fixed-size pose differently, so the
    frame also covers the device area.
    """
    frame = item.boundingRect()
    inv, ok = painter.worldTransform().inverted()
    if ok:
        frame = frame.united(inv.mapRect(QRectF(painter.viewport())))
    return frame


class ClipRun:
    """Opens one painter clip per run of ops sharing a ``clip_out``.

    The painter's state stack also holds its world transform, so every switch
    happens unposed; *xf* re-poses lazily. The op loops compare
    ``op.clip_out is not run.cur`` inline, so an unclipped block pays one
    attribute read per op.
    """

    __slots__ = ("_painter", "_xf", "_pose", "_item", "cur")

    def __init__(self, painter, xf, pose: QTransform, item):
        self._painter = painter
        self._xf = xf
        self._pose = pose
        self._item = item
        self.cur = None

    def enter(self, clip) -> None:
        """Close the open run and start one for *clip* (None = no clip)."""
        self._xf.unposed()
        if self.cur is not None:
            self._painter.restore()
        self.cur = clip
        if clip is not None:
            self._painter.save()
            self._painter.setClipPath(keep_path(keep_frame(self._painter, self._item),
                                                self._pose.map(clip)),
                                      Qt.ClipOperation.IntersectClip)


class PoseXf:
    """Per-paint world-transform toggle for block ops (MW-7; moved from
    ``block_instance._PoseXf`` for the SB3 lift).

    The posed transform (pose x item frame) is composed once per paint and
    switched to / from with ``setWorldTransform`` -- no per-op painter
    ``save`` / ``restore``. Crisp stroke ops draw under it; every other op
    (fills, text, linetype expansions, paper strokes) calls ``unposed`` first.
    """

    __slots__ = ("_painter", "_base", "_pose", "_posed", "_on")

    def __init__(self, painter, pose: QTransform):
        self._painter = painter
        self._base = painter.worldTransform()
        self._pose = pose
        self._posed = None
        self._on = False

    def posed(self) -> None:
        """Switch the painter to the posed transform (composed once)."""
        if not self._on:
            if self._posed is None:
                self._posed = self._pose * self._base
            self._painter.setWorldTransform(self._posed)
            self._on = True

    def unposed(self) -> None:
        """Switch the painter back to the item frame it had at paint start."""
        if self._on:
            self._painter.setWorldTransform(self._base)
            self._on = False


def text_path(op, pose_rot: float) -> QPainterPath:
    """A TEXT op's glyph path, turned 180 deg about its box centre when a
    mirror left it reading upside down under rotation *pose_rot* (DD6;
    lifted from ``BlockInstance._text_path``)."""
    from .block_pose import is_upright
    fr = op.text_frame
    if not op.readable or fr is None:
        return op.path
    if is_upright(fr[2] + pose_rot):
        return op.path
    t = QTransform()
    t.translate(fr[0], fr[1])
    t.rotate(180.0)
    t.translate(-fr[0], -fr[1])
    return t.map(op.path)


def paper_op_width(item, weight) -> float:
    """Non-cosmetic paper width for a stroke op's resolved *weight* (LT2-5;
    lifted from ``BlockInstance._paper_op_width``): a named weight plots at
    its own mm divided by the viewport scale, everything else takes the
    category weight ``item._paper_pen_width``."""
    from . import paper_display as _pd
    from .stroke_style import is_named_weight
    if not is_named_weight(weight) or not item._paper_scale:
        return item._paper_pen_width
    return _pd.resolve_line_weight_mm(weight) / max(item._paper_scale, 1e-9)


def stroke_op(item, painter, ops, i, op, pose, pen, xf=None, path=None) -> None:
    """Stroke op *i* of *ops* with *pen* (MW-7 / H-MW-f; lifted from
    ``BlockInstance._stroke_op``). Canvas (cosmetic) pens draw crisp through
    ``item._crisp_ops`` (a per-item ``(ops list, {slot: SplitCache})``);
    paper / non-cosmetic pens draw the exact pre-MW call. *path* (LT5)
    replaces the op's own path with a split-cache slot of its own; an empty
    one draws nothing. Leaves the posed transform on (the caller's rule)."""
    from . import crisp_stroke as _cs
    from . import paper_display as _pd
    if path is None:
        path, slot = op.path, i
    else:
        if path.isEmpty():
            return
        slot = -1 - i
    if not pen.isCosmetic() or _pd.paper_pass_active():
        if xf is not None:
            xf.unposed()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(pose.map(path))
        return
    c = item._crisp_ops
    if c is None or c[0] is not ops:
        c = item._crisp_ops = (ops, {})
    cache = c[1].get(slot)
    if cache is None:
        cache = c[1][slot] = _cs.SplitCache()
    own = xf is None
    if own:
        xf = PoseXf(painter, pose)
    xf.posed()
    try:
        _cs.stroke(painter, path, pen, cache.get(path, painter.worldTransform()))
    finally:
        if own:
            xf.unposed()


def paint_fill_op(item, painter, pose, op, colour=None) -> None:
    """Fill / pattern op: boundary posed; pattern stamped in the pose's
    rotation / mirror frame, never its scale (D-A11; lifted from
    ``BlockInstance._paint_fill_op``). *colour* (a QColor) replaces the op's
    own colour -- the symbol Fill tint (SB4g D8 / R9) -- except on a
    ``keep_colour`` op; the op's alpha is kept."""
    from . import hatch_render as _hr
    from .colour_tokens import resolve_colour
    from .constants import FILL_LEGACY_COLOUR
    if colour is not None and not op.keep_colour:
        col = QColor(colour)
    else:
        col = resolve_colour(op.colour or FILL_LEGACY_COLOUR, item=item)
    col.setAlpha(op.alpha)
    if op.kind == FILL:
        _hr.paint_fill(painter, pose.map(op.path), scene=item.scene(),
                       background=col, to_scene=item.sceneTransform())
    else:
        st = item.sceneTransform()
        origin = pose.map(op.origin if op.origin is not None else QPointF(0, 0))
        _hr.paint_fill(painter, pose.map(op.path), scene=item.scene(),
                       tile_ref=op.tile_ref, colour=col,
                       origin=st.map(origin), scale=op.scale, to_scene=st,
                       orient=pattern_orient(op.pattern_frame, pose, st))


def paint_ops(painter, ops, pose, item, *, override=None, selected=False, tint=None,
              end_ops=frozenset(), ends=None, fill_override=None) -> None:
    """Paint *ops* of a block with no linetype refs (every stroke solid) --
    the pre-LT3 loop lifted from ``BlockInstance._paint_plain_ops`` (SB3
    D-A: one op painter for a placed instance and a ``BoundLabelItem``).

    *item* supplies the per-item paint state: ``_paper_pen_width``,
    ``_paper_pen_color``, ``_paper_scale`` (paper_display._apply_block hooks),
    ``_is_ghost``, ``_crisp_ops``, ``_pose_rot``, ``scene()``,
    ``sceneTransform()``. *override* is the display-manager pen colour,
    *tint* the constraint tint (stroke ops only), *selected* paints the
    theme accent on the canvas (never on paper). LT5: stroke ops in *end_ops*
    are offered to *ends(i, op, pen, xf) -> bool* first (True = the callback
    drew the op with its ends); with *ends* None or *end_ops* empty (every
    legacy block, every label) none of that runs and the loop is the pre-LT5
    one. The canvas width is reused while consecutive ops share a weight.
    *fill_override* (QColor) colours FILL / PATTERN ops instead of their own
    colour (the symbol Fill tint, SB4g D8); *override* stays stroke / text only.
    """
    from . import theme as _theme
    from .colour_tokens import paint_resolver
    from .constants import TOKEN_AUTO
    from .stroke_style import canvas_px
    on_paper = item._paper_pen_width is not None
    last_w, last_px = None, None
    xf = PoseXf(painter, pose)    # posed world transform, toggled per op (MW-7)
    rc = paint_resolver(item)     # each distinct colour once per paint (G12)
    sel = (QColor(_theme.detect().accent)       # canvas selection (R5)
           if selected and not on_paper else None)
    paper_color = item._paper_pen_color
    clip = ClipRun(painter, xf, pose, item)
    for i, op in enumerate(ops):
        if op.clip_out is not clip.cur:
            clip.enter(op.clip_out)
        if op.kind in (FILL, PATTERN):
            xf.unposed()
            paint_fill_op(item, painter, pose, op, fill_override)
            continue
        if op.kind == TEXT:
            xf.unposed()
            # Text op: the fill carries the colour, so selection/override
            # tint applies to the BRUSH.
            b = QBrush(rc(op.colour or TOKEN_AUTO))
            if override is not None:
                b.setColor(override)
            # Selection is canvas feedback -- never plots (LT1-2).
            if sel is not None:
                b.setColor(sel)  # theme accent (R5)
            if paper_color is not None:
                b.setColor(paper_color)   # paper B&W/Custom (LT1-2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(b)
        else:
            # Copy -- the compiled op pen is shared by every instance.
            p = QPen(op.pen)
            if op.colour is not None:
                p.setColor(rc(op.colour))
            w = op.weight
            if on_paper:
                p.setCosmetic(False)          # true mm on paper (LT1-2)
                p.setWidthF(paper_op_width(item, w))
            else:
                p.setCosmetic(True)           # canvas (LT2-4)
                if w is not None:
                    if w != last_w or last_px is None:
                        last_w, last_px = w, canvas_px(w)
                    p.setWidthF(last_px)
            if override is not None:
                p.setColor(override)
            if tint is not None:
                p.setColor(tint)              # pen COPY (MW-12)
            if sel is not None:
                p.setColor(sel)  # theme accent (R5)
            if paper_color is not None:
                p.setColor(paper_color)
            if (ends is not None and end_ops and i in end_ops and not item._is_ghost
                    and ends(i, op, p, xf)):
                continue
            stroke_op(item, painter, ops, i, op, pose, p, xf)
            continue
        painter.drawPath(pose.map(text_path(op, item._pose_rot)))
    if clip.cur is not None:
        clip.enter(None)
    xf.unposed()
