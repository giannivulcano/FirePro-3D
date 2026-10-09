"""RenderOp — one typed draw instruction of a compiled block definition.

hatch-and-fill concept HD4/HD4a: replaces the ``(pen, brush, path)`` tuple and
its ``pen == NoPen ⇒ text`` heuristic. The linetypes ``StrokeOp`` (LT3) is the
``stroke`` half of this same type — extend it, don't fork it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPen, QTransform

STROKE = "stroke"
FILL = "fill"
PATTERN = "pattern"
TEXT = "text"


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

    def mapped(self, t: QTransform) -> "RenderOp":
        """This op with ``path`` / ``origin`` / ``pieces`` mapped through *t*."""
        pieces = self.pieces
        if pieces:
            from .path_walk import map_piece
            pieces = tuple(map_piece(p, t) for p in pieces)
        return replace(self, path=t.map(self.path),
                       origin=None if self.origin is None else t.map(self.origin),
                       pieces=pieces)


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
