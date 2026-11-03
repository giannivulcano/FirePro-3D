"""Stroke corner joints (design docs/superpowers/specs/2026-11-03-stroke-corner-joins-design.md).

Qt cannot miter across two ``drawPath`` calls, so a corner shared by two
strokes (two items, or the two runs of the crisp axis split) is closed by
filling the OUTER wedge between their flat ends in the stroke's colour.
``joint_wedge`` is pure math; ``JointIndex`` pairs coincident ends inside one
container; ``joinable`` is the paint-time AC4 / AC6 match.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainterPath, QPolygonF

from .constants import CHAIN_WELD_MM, STROKE_MITER_LIMIT

_EPS = 1e-9


def joint_wedge(corner: QPointF, d_a, d_b, half_w: float,
                limit: float = STROKE_MITER_LIMIT) -> QPolygonF | None:
    """The outer wedge closing the corner of two flat-ended strokes (D2).

    Qt semantics (P4 probe, 2026-11-03): a MiterJoin past its limit is not
    bevelled, it is *clipped*. Both outer edges, extended past the corner,
    are cut at ``limit * half_w`` from the corner's flat-end foot (Qt limit =
    ``limit / 2`` pen widths), joined by a chord. The wedge reproduces that
    so a patched joint is pixel-identical to an in-item vertex.

    Args:
        corner: The shared endpoint.
        d_a: Unit direction of stroke A *away* from the corner (dx, dy).
        d_b: Unit direction of stroke B away from the corner.
        half_w: Half the stroke width, in the frame of *corner*.
        limit: Miter limit as the PDF ratio (miter length / width).

    Returns:
        ``[corner, outer edge of A, miter tip, outer edge of B]``; past the
        limit ``[corner, outer edge of A, clip on A's edge, clip on B's edge,
        outer edge of B]``; None when the strokes are collinear (straight
        through: nothing to fill) or overlap (parallel / zero tangent).
    """
    ax, ay = d_a
    bx, by = d_b
    cross = ax * by - ay * bx
    if abs(cross) < _EPS or half_w <= 0.0:
        return None                      # straight through, reversed or degenerate
    dot = ax * bx + ay * by
    # Outer normals: perpendicular to each stroke, pointing away from the other.
    na = (-ay, ax) if (-ay * bx + ax * by) < 0.0 else (ay, -ax)
    nb = (-by, bx) if (-by * ax + bx * ay) < 0.0 else (by, -bx)
    cx, cy = corner.x(), corner.y()
    pa = QPointF(cx + na[0] * half_w, cy + na[1] * half_w)
    pb = QPointF(cx + nb[0] * half_w, cy + nb[1] * half_w)
    # Interior angle theta between the strokes: cos = dot. The miter tip lies
    # on each outer edge's extension at half_w / tan(theta / 2) past the
    # corner (and half_w / sin(theta / 2) from it along the exterior bisector).
    half = math.acos(max(-1.0, min(1.0, dot))) / 2.0
    s = math.sin(half)
    t = math.tan(half)
    if s < _EPS or t < _EPS or 1.0 / t > limit:
        cut = limit * half_w
        return QPolygonF([
            corner, pa,
            QPointF(pa.x() - ax * cut, pa.y() - ay * cut),
            QPointF(pb.x() - bx * cut, pb.y() - by * cut),
            pb,
        ])
    bx_, by_ = -(ax + bx), -(ay + by)
    n = math.hypot(bx_, by_)
    reach = half_w / s
    tip = QPointF(cx + bx_ / n * reach, cy + by_ / n * reach)
    return QPolygonF([corner, pa, tip, pb])


def fill_wedge(painter, wedge: QPolygonF, colour) -> None:
    """Fill *wedge* with *colour*, no pen, under the painter's current transform."""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    painter.drawPolygon(wedge)


def unit(dx: float, dy: float) -> tuple:
    """(dx, dy) normalised; (0.0, 0.0) for a (near-)zero vector. The one
    unit-vector implementation of the stroke-joint code."""
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > _EPS else (0.0, 0.0)


def map_dir(xf, d) -> tuple:
    """*d* through *xf*'s 2x2, re-normalised ((0, 0) stays (0, 0))."""
    return unit(d[0] * xf.m11() + d[1] * xf.m21(),
                d[0] * xf.m12() + d[1] * xf.m22())


def joint_pad(width: float) -> float:
    """Reach of a joint wedge past the corner for a stroke *width* wide: the
    miter tip at the limit and the clip points past it both sit
    ``half_w * sqrt(1 + limit^2)`` from the corner. The one derivation the
    bounds pads (scene items and block instances) share."""
    return 0.5 * width * math.sqrt(1.0 + STROKE_MITER_LIMIT * STROKE_MITER_LIMIT)


def bevel_wedge(corner: QPointF, d_a, d_b, half_w: float) -> QPolygonF | None:
    """The bevel triangle ``[corner, outer edge of A, outer edge of B]`` --
    what Qt's BevelJoin fills at an in-item vertex. None when collinear."""
    ax, ay = d_a
    bx, by = d_b
    if abs(ax * by - ay * bx) < _EPS or half_w <= 0.0:
        return None
    na = (-ay, ax) if (-ay * bx + ax * by) < 0.0 else (ay, -ax)
    nb = (-by, bx) if (-by * ax + bx * ay) < 0.0 else (by, -bx)
    cx, cy = corner.x(), corner.y()
    return QPolygonF([corner,
                      QPointF(cx + na[0] * half_w, cy + na[1] * half_w),
                      QPointF(cx + nb[0] * half_w, cy + nb[1] * half_w)])


def fill_wedges_device(painter, joints, pen) -> None:
    """D3 / D7 cosmetic case: each ``(point, d_in, d_out)`` mapped through
    ``painter.worldTransform()`` to device space and filled under an identity
    transform with ``half_w = pen.widthF() / 2`` in the pen's colour, in the
    pen's own join style (m4): Bevel -> the bevel triangle, Round -> a dot,
    Miter -> the miter at ``pen.miterLimit() * 2`` (the PDF ratio). Model
    geometry pens are Miter limit 2 (``stroke_pen``), i.e. the stroke limit.
    Leaves the painter's transform / pen / brush as found."""
    xf = painter.worldTransform()
    half_w = pen.widthF() / 2.0
    js = pen.joinStyle()
    painter.save()
    try:
        painter.resetTransform()
        for pt, d_in, d_out in joints:
            c = xf.map(pt)
            da = map_dir(xf, (-d_in[0], -d_in[1]))
            db = map_dir(xf, d_out)
            if js == Qt.PenJoinStyle.RoundJoin:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(pen.color())
                painter.drawEllipse(c, half_w, half_w)
                continue
            if js == Qt.PenJoinStyle.BevelJoin:
                w = bevel_wedge(c, da, db, half_w)
            else:
                w = joint_wedge(c, da, db, half_w, limit=pen.miterLimit() * 2.0)
            if w is not None:
                fill_wedge(painter, w, pen.color())
    finally:
        painter.restore()


@dataclass(frozen=True, eq=False, slots=True)
class JointEnd:
    """One open-stroke end in its container's frame (scene mm for loose
    items, definition-local for block ops). ``tx, ty`` point from the end
    INTO the stroke (away from the corner). Identity-compared: two ends of
    one owner are distinct records."""
    x: float
    y: float
    tx: float
    ty: float
    which: str          # "start" | "finish"
    owner: object       # the item (scene) or op index (block definition)

    @property
    def point(self) -> QPointF:
        return QPointF(self.x, self.y)

    @property
    def away(self) -> tuple:
        return (self.tx, self.ty)


@dataclass(frozen=True)
class JointAttrs:
    """Paint-time facts of one end for the AC4 / AC6 match."""
    weight: str
    colour: str
    inked: bool
    has_end_type: bool
    visible: bool = True


def joinable(a: JointAttrs | None, b: JointAttrs | None) -> bool:
    """AC4 + AC6: both present, visible, inked, no end type, same weight
    name, same colour string."""
    return (a is not None and b is not None and a.visible and b.visible
            and a.inked and b.inked and not a.has_end_type and not b.has_end_type
            and a.weight == b.weight and a.colour == b.colour)


class JointIndex:
    """Coincident-end lookup for one container (D4 / D5).

    Ends live in a dict keyed on their point quantised to a ``tol`` grid;
    ``partner`` scans the 3x3 neighbourhood and matches on exact distance
    <= *tol*. A match needs EXACTLY two ends at the point (the queried one
    included) -- a star of three, or a lone end, has no partner (AC4's
    count half; the attribute half is ``joinable`` at paint).
    """

    def __init__(self, tol: float = CHAIN_WELD_MM):
        self._tol = float(tol)
        self._cells: dict[tuple, list] = {}
        self._by_key: dict = {}

    def _cell(self, x: float, y: float) -> tuple:
        return (math.floor(x / self._tol), math.floor(y / self._tol))

    def register(self, key, ends) -> tuple:
        """Replace *key*'s ends with *ends* (an iterable of ``JointEnd``);
        returns the ends it replaced (``()`` when none)."""
        old = self.unregister(key)
        ends = tuple(ends)
        if ends:
            self._by_key[key] = ends
            for e in ends:
                self._cells.setdefault(self._cell(e.x, e.y), []).append(e)
        return old

    def unregister(self, key) -> tuple:
        old = self._by_key.pop(key, ())
        for e in old:
            c = self._cell(e.x, e.y)
            lst = self._cells.get(c)
            if lst is not None:
                lst.remove(e)
                if not lst:
                    del self._cells[c]
        return old

    def ends_of(self, key) -> tuple:
        """The ends currently registered for *key* (``()`` when none)."""
        return self._by_key.get(key, ())

    def neighbours(self, pt: QPointF) -> list:
        """Every registered end within *tol* of *pt*."""
        cx, cy = self._cell(pt.x(), pt.y())
        px, py, tol = pt.x(), pt.y(), self._tol
        out = []
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for e in self._cells.get((cx + i, cy + j), ()):
                    if math.hypot(e.x - px, e.y - py) <= tol:
                        out.append(e)
        return out

    def partner(self, end: JointEnd) -> JointEnd | None:
        near = self.neighbours(end.point)
        if len(near) != 2 or end not in near:
            return None
        other = near[0] if near[1] is end else near[1]
        if other.owner is end.owner:
            return None               # a coincident-open seam stays flat (m5)
        return other

    def clear(self) -> None:
        self._cells.clear()
        self._by_key.clear()

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_key.values())


def ends_of_pieces(pieces, owner, xf=None) -> tuple:
    """The two ``JointEnd``s of an open stroke from its ``stroke_pieces()``,
    optionally mapped through *xf* (a QTransform: item -> container frame).
    ``()`` for no / zero-length pieces. Uses ``path_walk.end_frame`` with a
    zero trim: its outward vector reversed is the away-from-corner tangent."""
    from .path_walk import end_frame
    out = []
    for which in ("start", "finish"):
        fr = end_frame(pieces, which, 0.0)
        if fr is None:
            return ()
        at, (ox, oy) = fr
        away = (-ox, -oy)
        if xf is not None:
            at = xf.map(at)
            away = map_dir(xf, away)
        out.append(JointEnd(at.x(), at.y(), away[0], away[1], which, owner))
    return tuple(out)


def end_inked(dash: QPainterPath, pt: QPointF, tol: float = 1e-6) -> bool:
    """AC6: True when the expanded dash path starts or ends at *pt* -- the
    first / last dash is clipped at the stroke end, so an inked end is a
    dash boundary sitting on the endpoint. Dots never count."""
    n = dash.elementCount()
    if n == 0:
        return False
    for i in (0, n - 1):
        e = dash.elementAt(i)
        if abs(e.x - pt.x()) <= tol and abs(e.y - pt.y()) <= tol:
            return True
    return False


def wedge_for_pair(a: JointEnd, b: JointEnd, half_w: float, xf=None) -> QPolygonF | None:
    """The wedge between partner ends *a* and *b* (same point within tol).

    *xf* maps the ends' container frame to the paint frame (device for a
    cosmetic pen, item-local for a paper pen) and *half_w* is in that frame.
    The corner is the midpoint of the two ends.
    """
    corner = QPointF((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
    da, db = a.away, b.away
    if xf is not None:
        corner = xf.map(corner)
        da = map_dir(xf, da)
        db = map_dir(xf, db)
    return joint_wedge(corner, da, db, half_w)
