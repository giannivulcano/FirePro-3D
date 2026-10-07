"""Crisp horizontal / vertical canvas strokes (linetypes.md MW-7 / H-MW-f).

P4 probe (2026-10-06): an ALIASED cosmetic stroke of width N paints exactly N
full-intensity rows at any device y, while an anti-aliased one on a pixel
boundary smears into partial rows. So a stroke is split into maximal runs of
exactly axis-aligned straight segments (drawn aliased) and everything else --
diagonals and every curve element -- (drawn under the painter's AA hint).
Classification is in the painter's world frame (item / pose / group rotation
included) and is zoom-free, so splits are cached by value and never on zoom
(delta 3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QPolygonF, QTransform

from .constants import CRISP_AXIS_TOL, CRISP_CLOSE_TOL
from .paper_display import paper_pass_active

_AA = QPainter.RenderHint.Antialiasing
_MOVE = QPainterPath.ElementType.MoveToElement
_LINE = QPainterPath.ElementType.LineToElement
_NO_BRUSH = Qt.BrushStyle.NoBrush
_UNDASHED = (Qt.PenStyle.SolidLine, Qt.PenStyle.NoPen)
_ORTHO_KEY = ("ortho",)       # every signed-permutation 2x2 splits identically


@dataclass(frozen=True)
class CrispSplit:
    """A stroke path partitioned for crisp drawing.

    Attributes:
        axis: Maximal runs of exactly axis-aligned straight segments (aliased).
        other: Diagonals and every curve element (anti-aliased).
        all_axis: Whether the whole path is axis (a Qt-dashed pen splits only
            then, delta 4).
        joint_points: Axis <-> other junction vertices (painter-local), one
            polygon so a paint stamps every joint dot in one ``drawPoints``.
    """
    axis: QPainterPath
    other: QPainterPath
    all_axis: bool
    joint_points: QPolygonF = field(default_factory=QPolygonF, compare=False)


def xf_key(xf: QTransform) -> tuple:
    """Scale-normalised 2x2 of *xf* -- the zoom-free cache key.

    An exact signed permutation (0 / 90 / 180 / 270 deg, mirrors, any uniform
    scale) only permutes / scales |vx|, |vy|, so it classifies every segment
    as the identity does: all of them share one key.
    """
    m11, m12, m21, m22 = xf.m11(), xf.m12(), xf.m21(), xf.m22()
    if ((m12 == 0.0 and m21 == 0.0 and m11 != 0.0 and abs(m11) == abs(m22))
            or (m11 == 0.0 and m22 == 0.0 and m12 != 0.0 and abs(m12) == abs(m21))):
        return _ORTHO_KEY
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
    tol = CRISP_AXIS_TOL
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
        return CrispSplit(QPainterPath(path), QPainterPath(), any_axis)
    if not any_axis:
        return CrispSplit(QPainterPath(), QPainterPath(path), False)
    # Pass 2: mixed -- rebuild maximal runs into the two paths, one subpath
    # at a time. A segment is (class, element index); its end point is
    # xs/ys at the index (line) or index + 2 (curve).
    axis, other = QPainterPath(), QPainterPath()
    joints = QPolygonF()

    def _end(seg):
        j = seg[1] + (2 if seg[0] == 2 else 0)
        return xs[j], ys[j]

    def _emit(sx, sy, segs):
        if not segs:
            return
        ex, ey = _end(segs[-1])
        closed = abs(ex - sx) < CRISP_CLOSE_TOL and abs(ey - sy) < CRISP_CLOSE_TOL
        kinds = [c == 1 for c, _ in segs]
        if closed and all(k == kinds[0] for k in kinds):
            tgt = axis if kinds[0] else other       # one closed run: keep its join
            tgt.moveTo(sx, sy)
            for seg in segs:
                _seg_to(tgt, seg)
            tgt.closeSubpath()
            return
        if closed:
            # Start at the first class change so the start vertex is a run
            # boundary: the run through the old start keeps its real join
            # (no caps there), and the wrap-around vertex is a joint.
            k = next(m for m in range(1, len(segs)) if kinds[m] != kinds[m - 1])
            segs = segs[k:] + segs[:k]
            sx, sy = _end(segs[-1])
        cx, cy = sx, sy
        run = None
        for seg in segs:
            is_axis = seg[0] == 1
            tgt = axis if is_axis else other
            if run is not is_axis:
                if run is not None:
                    joints.append(QPointF(cx, cy))
                tgt.moveTo(cx, cy)
                run = is_axis
            _seg_to(tgt, seg)
            cx, cy = _end(seg)
        if closed:
            joints.append(QPointF(cx, cy))              # last run meets the first

    def _seg_to(tgt, seg):
        c, j = seg
        if c == 2:
            tgt.cubicTo(xs[j], ys[j], xs[j + 1], ys[j + 1], xs[j + 2], ys[j + 2])
        else:
            tgt.lineTo(xs[j], ys[j])

    sx = sy = 0.0
    segs: list = []
    i = 0
    while i < n:
        c = cls[i]
        if c is None:            # MoveTo
            _emit(sx, sy, segs)
            sx, sy, segs = xs[i], ys[i], []
            i += 1
            continue
        segs.append((c, i))
        i += 3 if c == 2 else 1
    _emit(sx, sy, segs)
    return CrispSplit(axis, other, False, joints)


class SplitCache:
    """One owner's cached split, keyed by path value + ``xf_key`` (delta 3)."""

    __slots__ = ("_path", "_key", "_raw", "_split")

    def __init__(self):
        self._path = None
        self._key = None
        self._raw = None          # raw 2x2 of the last lookup (MW-13 fast hit)
        self._split = None

    def get(self, path: QPainterPath, xf: QTransform) -> CrispSplit:
        """The split of *path* under *xf*, recomputed only on a value change.

        Cheap transform key (MW-13): the raw 2x2 equal to the last lookup's
        hits without normalising; an exact signed permutation (any pan /
        uniform zoom of an unrotated item) maps straight to the orthogonal
        key; only a rotated / sheared 2x2 that changed pays ``xf_key``.
        """
        raw = (xf.m11(), xf.m12(), xf.m21(), xf.m22())
        if raw == self._raw and self._split is not None:
            key = self._key
        else:
            m11, m12, m21, m22 = raw
            if ((m12 == 0.0 and m21 == 0.0 and m11 != 0.0 and abs(m11) == abs(m22))
                    or (m11 == 0.0 and m22 == 0.0 and m12 != 0.0
                        and abs(m12) == abs(m21))):
                key = _ORTHO_KEY
            else:
                key = xf_key(xf)
            self._raw = raw
        if self._split is None or key != self._key or path != self._path:
            self._split = split_axis(path, xf)
            self._path = QPainterPath(path)
        self._key = key
        return self._split

    def seed(self, path: QPainterPath, split: CrispSplit) -> None:
        """Pre-load the split of *path* under any orthogonal transform (its
        identity-frame split), so the first canvas paint does no split."""
        self._path = QPainterPath(path)
        self._key = _ORTHO_KEY
        self._raw = None
        self._split = split


def stroke(painter: QPainter, path: QPainterPath, pen: QPen,
           split: CrispSplit | None) -> None:
    """Stroke *path* with *pen* (no brush).

    Cosmetic pens on a canvas draw through *split*: axis runs aliased, the
    rest (and the joint dots) under the painter's own AA hint -- "stay" AA on
    an AA canvas, never AA added to an aliased render. Paper passes,
    non-cosmetic pens, and Qt-dashed pens on a mixed path draw unsplit
    (delta 4). Leaves the painter's AA hint as found, and its pen and brush
    SET (*pen*, or a round-cap copy after joint dots; NoBrush) -- callers
    that need them kept bracket the call with ``save`` / ``restore``.

    Args:
        painter: The active painter.
        path: The stroke path (painter-local).
        pen: The pen to stroke with (callers may pass a tinted copy).
        split: ``split_axis(path, painter.worldTransform())`` or None to draw
            unsplit.
    """
    painter.setBrush(_NO_BRUSH)
    painter.setPen(pen)
    if (split is None or not pen.isCosmetic() or paper_pass_active()
            or (not split.all_axis and pen.style() not in _UNDASHED)):
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
        if not split.joint_points.isEmpty() and pen.widthF() >= 2.0:
            dot = QPen(pen)
            dot.setStyle(Qt.PenStyle.SolidLine)
            dot.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(dot)
            painter.setRenderHint(_AA, aa)
            painter.drawPoints(split.joint_points)
    finally:
        painter.setRenderHint(_AA, aa)


def stroke_cached(cache: SplitCache, painter: QPainter, path: QPainterPath,
                  pen: QPen) -> None:
    """``stroke`` through *cache*, gated BEFORE any split is computed.

    Non-cosmetic pens and paper passes draw unsplit and never touch *cache*
    (a sheet / PDF render must not pay a first split it would not use).
    """
    if not pen.isCosmetic() or paper_pass_active():
        stroke(painter, path, pen, None)
        return
    stroke(painter, path, pen, cache.get(path, painter.worldTransform()))
