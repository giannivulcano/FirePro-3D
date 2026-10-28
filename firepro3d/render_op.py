"""RenderOp — one typed draw instruction of a compiled block definition.

hatch-and-fill concept HD4/HD4a: replaces the ``(pen, brush, path)`` tuple and
its ``pen == NoPen ⇒ text`` heuristic. The linetypes ``StrokeOp`` (LT3) is the
``stroke`` half of this same type — extend it, don't fork it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QTransform

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

    def mapped(self, t: QTransform) -> "RenderOp":
        """This op mapped through a similarity *t* (rigid x uniform scale,
        possibly reflecting -- block mirror / scale, design DD5 / DD6).

        A reflecting *t* toggles open-stroke ends' ``mirrored`` flag (no
        start / finish swap: ``map_piece`` keeps the walking direction) and
        un-mirrors TEXT glyphs about their own box-vertical axis so text
        never reads backwards (sets ``readable``).

        Args:
            t: The similarity map (definition-local -> target frame).

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
        return replace(self, path=path,
                       origin=None if self.origin is None else t.map(self.origin),
                       pieces=pieces, ends=ends, text_frame=frame,
                       readable=readable, pattern_frame=pframe)


def apply_overrides(ops, weight=None, linetype=None):
    """*ops* with every styled stroke's weight / linetype replaced (WM2 H2).

    Keyword-agnostic: ``None`` = keep. Text / fill / pattern ops and the
    unstyled placeholder (``weight is None``) are returned as is; the input
    list and its shared flyweight ops are never mutated. With nothing to
    replace the input list itself is returned (the As Authored fast path).
    """
    if weight is None and linetype is None:
        return ops
    kw = {}
    if weight is not None:
        kw["weight"] = weight
    if linetype is not None:
        kw["linetype"] = linetype
    return [replace(op, **kw) if op.kind == STROKE and op.weight is not None
            else op for op in ops]


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


def paint_fill_op(item, painter, pose, op) -> None:
    """Fill / pattern op: boundary posed; pattern stamped in the pose's
    rotation / mirror frame, never its scale (D-A11; lifted from
    ``BlockInstance._paint_fill_op``)."""
    from . import hatch_render as _hr
    from .colour_tokens import resolve_colour
    from .constants import FILL_LEGACY_COLOUR
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
              end_ops=frozenset(), ends=None) -> None:
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
    for i, op in enumerate(ops):
        if op.kind in (FILL, PATTERN):
            xf.unposed()
            paint_fill_op(item, painter, pose, op)
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
    xf.unposed()
