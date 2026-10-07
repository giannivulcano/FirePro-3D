"""Crisp horizontal / vertical canvas strokes (linetypes.md MW-7 / H-MW-f).

P4 probe (2026-10-06): an ALIASED cosmetic stroke of width N paints exactly N
full-intensity rows at any device y, while an anti-aliased one on a pixel
boundary smears into partial rows. So a stroke is split into maximal runs of
exactly axis-aligned straight segments (drawn aliased) and everything else --
diagonals and every curve element -- (drawn anti-aliased). Classification is
in the painter's world frame (item / pose / group rotation included) and is
zoom-free, so splits are cached by value and never on zoom (delta 3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QPolygonF, QTransform

_AXIS_TOL = 1e-6          # relative off-axis tolerance: float noise only
_AA = QPainter.RenderHint.Antialiasing
_MOVE = QPainterPath.ElementType.MoveToElement
_LINE = QPainterPath.ElementType.LineToElement


@dataclass(frozen=True)
class CrispSplit:
    """A stroke path partitioned for crisp drawing.

    Attributes:
        axis: Maximal runs of exactly axis-aligned straight segments (aliased).
        other: Diagonals and every curve element (anti-aliased).
        joints: Axis <-> other junction vertices (painter-local).
        all_axis: Whether the whole path is axis (a Qt-dashed pen splits only
            then, delta 4).
        joint_points: *joints* as one polygon, built once so a paint stamps
            every joint dot in a single ``drawPoints`` call.
    """
    axis: QPainterPath
    other: QPainterPath
    joints: tuple
    all_axis: bool
    joint_points: QPolygonF = field(default_factory=QPolygonF, compare=False)


def xf_key(xf: QTransform) -> tuple:
    """Scale-normalised 2x2 of *xf* -- the zoom-free cache key."""
    s = math.sqrt(abs(xf.m11() * xf.m22() - xf.m12() * xf.m21())) or 1.0
    return (round(xf.m11() / s, 6), round(xf.m12() / s, 6),
            round(xf.m21() / s, 6), round(xf.m22() / s, 6))


def split_axis(path: QPainterPath, xf: QTransform) -> CrispSplit:
    """Partition *path* (painter-local) by how its straight segments land
    under *xf*'s 2x2.

    Args:
        path: The stroke path in painter-local coordinates.
        xf: The painter's world transform (only its 2x2 is read).

    Returns:
        The ``CrispSplit`` of *path*.
    """
    a11, a12, a21, a22 = xf.m11(), xf.m12(), xf.m21(), xf.m22()
    tol = _AXIS_TOL
    at = path.elementAt
    n = path.elementCount()
    # Pass 1 (floats only): classify every element. A uniform path -- the
    # common case: all-axis rectangles, all-diagonal hatches, all curves --
    # is returned as-is, with no rebuilt geometry.
    # Per element: None move / curve data, 1 axis line, 0 other line, 2 curve.
    cls = [None] * n
    xs = [0.0] * n
    ys = [0.0] * n
    any_axis = any_other = False
    cx = cy = 0.0
    i = 0
    while i < n:
        e = at(i)
        t = e.type
        xs[i], ys[i] = e.x, e.y
        if t == _MOVE:
            cx, cy = e.x, e.y
            i += 1
            continue
        if t == _LINE:
            dx, dy = e.x - cx, e.y - cy
            vx, vy = dx * a11 + dy * a21, dx * a12 + dy * a22
            ax, ay = abs(vx), abs(vy)
            ok = (ax > 0.0 or ay > 0.0) and min(ax, ay) <= tol * math.hypot(vx, vy)
            cls[i] = 1 if ok else 0
            if ok:
                any_axis = True
            else:
                any_other = True
            cx, cy = e.x, e.y
            i += 1
            continue
        cls[i] = 2               # CurveToElement (+ two CurveToDataElement)
        any_other = True
        for j in (i + 1, i + 2):
            d = at(j)
            xs[j], ys[j] = d.x, d.y
        cx, cy = xs[i + 2], ys[i + 2]
        i += 3
    if not any_other:
        return CrispSplit(QPainterPath(path), QPainterPath(), (), any_axis)
    if not any_axis:
        return CrispSplit(QPainterPath(), QPainterPath(path), (), False)
    # Pass 2: mixed -- rebuild maximal runs into the two paths.
    axis, other = QPainterPath(), QPainterPath()
    joints: list[QPointF] = []
    sx = sy = cx = cy = 0.0
    run = None                # open run in this subpath: True axis / False other
    runs = 0                  # runs started in this subpath
    first_tgt = None

    def _close_if_single():
        # A one-run closed subpath keeps its closing join (a rectangle).
        if runs == 1 and abs(cx - sx) < 1e-9 and abs(cy - sy) < 1e-9:
            first_tgt.closeSubpath()

    i = 0
    while i < n:
        c = cls[i]
        x, y = xs[i], ys[i]
        if c is None:            # MoveTo
            _close_if_single()
            cx = sx = x
            cy = sy = y
            run, runs, first_tgt = None, 0, None
            i += 1
            continue
        is_axis = c == 1
        tgt = axis if is_axis else other
        if run is not is_axis:
            if run is not None:
                joints.append(QPointF(cx, cy))
            tgt.moveTo(cx, cy)
            run = is_axis
            runs += 1
            if first_tgt is None:
                first_tgt = tgt
        if c != 2:
            tgt.lineTo(x, y)
            cx, cy = x, y
            i += 1
            continue
        cx, cy = xs[i + 2], ys[i + 2]
        other.cubicTo(x, y, xs[i + 1], ys[i + 1], cx, cy)
        i += 3
    _close_if_single()
    return CrispSplit(axis, other, tuple(joints), False, QPolygonF(joints))


class SplitCache:
    """One owner's cached split, keyed by path value + ``xf_key`` (delta 3)."""

    __slots__ = ("_path", "_key", "_split")

    def __init__(self):
        self._path = None
        self._key = None
        self._split = None

    def get(self, path: QPainterPath, xf: QTransform) -> CrispSplit:
        """The split of *path* under *xf*, recomputed only on a value change."""
        key = xf_key(xf)
        if self._split is None or key != self._key or path != self._path:
            self._split = split_axis(path, xf)
            self._path = QPainterPath(path)
            self._key = key
        return self._split


def stroke(painter: QPainter, path: QPainterPath, pen: QPen,
           split: CrispSplit | None) -> None:
    """Stroke *path* with *pen* (no brush).

    Cosmetic pens on a canvas draw through *split*: axis runs aliased, the
    rest (and the joint dots) under the painter's own AA hint -- "stay" AA on
    an AA canvas, never AA added to an aliased render. Paper passes,
    non-cosmetic pens, and Qt-dashed pens on a mixed path draw unsplit
    (delta 4). Leaves the painter's AA hint as found.

    Args:
        painter: The active painter.
        path: The stroke path (painter-local).
        pen: The pen to stroke with (callers may pass a tinted copy).
        split: ``split_axis(path, painter.worldTransform())`` or None to draw
            unsplit.
    """
    from .paper_display import paper_pass_active
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    dashed = pen.style() not in (Qt.PenStyle.SolidLine, Qt.PenStyle.NoPen)
    if (split is None or not pen.isCosmetic() or paper_pass_active()
            or (dashed and not split.all_axis)):
        painter.drawPath(path)
        return
    aa = painter.testRenderHint(_AA)
    try:
        if split.all_axis:
            painter.setRenderHint(_AA, False)
            painter.drawPath(path)
            return
        if not split.other.isEmpty():
            painter.drawPath(split.other)        # the painter's own AA hint
        if not split.axis.isEmpty():
            painter.setRenderHint(_AA, False)
            painter.drawPath(split.axis)
        if split.joints and pen.widthF() >= 2.0:
            dot = QPen(pen)
            dot.setStyle(Qt.PenStyle.SolidLine)
            dot.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(dot)
            painter.setRenderHint(_AA, aa)
            painter.drawPoints(split.joint_points)
    finally:
        painter.setRenderHint(_AA, aa)
