"""RenderOp — one typed draw instruction of a compiled block definition.

hatch-and-fill concept HD4/HD4a: replaces the ``(pen, brush, path)`` tuple and
its ``pen == NoPen ⇒ text`` heuristic. The linetypes ``StrokeOp`` (LT3) is the
``stroke`` half of this same type — extend it, don't fork it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPen, QTransform

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
        colour: Unresolved colour string (fill / pattern / text).
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
