"""Pick-point region finder (HF4).

Design: ``docs/superpowers/specs/2026-10-20-hf4-pick-region-design.md`` §1.
Pure geometry -- depends on Qt value types and the 2D item constructors only,
never on a scene or a view. ``Arrangement.build`` flattens the drawn paths of
the candidate items (``halo.halo_scene_path``) into tagged segments, splits
them at every crossing, welds vertices within ``CHAIN_WELD_MM``, prunes
dangling edges (recording the open ends) and links half-edges; ``face_at``
walks the tightest-left-turn cycle around a point; ``rebuild`` turns a face
back into exact pieces for ``FilledRegionItem.from_pieces``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath

from .constants import (CHAIN_MIN_LOOP_AREA_MM2, CHAIN_WELD_MM,
                        REGION_FINDER_BUCKETS, REGION_FINDER_NUDGE_MM,
                        REGION_FINDER_SAGITTA_MM)
from .geometry_2d import bezier_sub
from .geometry_intersect import line_line_intersection
from .halo import halo_scene_path

_EPS = 1e-9


@dataclass(frozen=True)
class Tag:
    """Which drawn path element a flattened segment came from.

    Attributes:
        item: The source 2D item (or a posed block stand-in).
        elem: Index of the ``LineTo`` / ``CurveTo`` element in the item's
            ``halo_scene_path`` that drew it.
        kind: ``"line"`` or ``"curve"``.
        bez: The cubic's four ``(x, y)`` control points for ``"curve"``.
        t0: Parameter of the segment's start along the element.
        t1: Parameter of its end (``t1 < t0`` once a walk traverses it backwards).
    """
    item: object
    elem: int
    kind: str
    bez: tuple | None
    t0: float
    t1: float


@dataclass
class Piece:
    """One flattened straight segment in scene coordinates with its tag."""
    x0: float
    y0: float
    x1: float
    y1: float
    tag: Tag

    def sub(self, u0: float, u1: float) -> "Piece":
        """The part ``[u0, u1]`` of this segment, tag parameters interpolated."""
        dx, dy = self.x1 - self.x0, self.y1 - self.y0
        dt = self.tag.t1 - self.tag.t0
        t = self.tag
        return Piece(self.x0 + dx * u0, self.y0 + dy * u0,
                     self.x0 + dx * u1, self.y0 + dy * u1,
                     Tag(t.item, t.elem, t.kind, t.bez, t.t0 + dt * u0, t.t0 + dt * u1))

    def reversed(self) -> "Piece":
        t = self.tag
        return Piece(self.x1, self.y1, self.x0, self.y0,
                     Tag(t.item, t.elem, t.kind, t.bez, t.t1, t.t0))

    def bbox(self) -> tuple:
        return (min(self.x0, self.x1), min(self.y0, self.y1),
                max(self.x0, self.x1), max(self.y0, self.y1))


# ── 1. Flatten ──────────────────────────────────────────────────────────────

def _bez_pt(b, t):
    u = 1.0 - t
    return (u**3 * b[0][0] + 3*u*u*t * b[1][0] + 3*u*t*t * b[2][0] + t**3 * b[3][0],
            u**3 * b[0][1] + 3*u*u*t * b[1][1] + 3*u*t*t * b[2][1] + t**3 * b[3][1])


def _flat_enough(b, sagitta: float) -> bool:
    """Control points within *sagitta* of the chord -> one segment suffices."""
    (x0, y0), (x3, y3) = b[0], b[3]
    dx, dy = x3 - x0, y3 - y0
    L = math.hypot(dx, dy)
    for x, y in (b[1], b[2]):
        d = (math.hypot(x - x0, y - y0) if L < 1e-12
             else abs((x - x0) * dy - (y - y0) * dx) / L)
        if d > sagitta:
            return False
    return True


def _window_hits(win: tuple, x0, y0, x1, y1) -> bool:
    wx0, wy0, wx1, wy1 = win
    return not (max(x0, x1) < wx0 or min(x0, x1) > wx1
                or max(y0, y1) < wy0 or min(y0, y1) > wy1)


def _emit_seg(out: list, win: tuple, p, q, tag: Tag) -> None:
    if math.hypot(q[0] - p[0], q[1] - p[1]) < _EPS:
        return
    if _window_hits(win, p[0], p[1], q[0], q[1]):
        out.append(Piece(p[0], p[1], q[0], q[1], tag))


def _flatten_cubic(out, win, item, elem, b, t0=0.0, t1=1.0, depth=0) -> None:
    piece = bezier_sub(b, t0, t1)
    if depth >= 16 or _flat_enough(piece, REGION_FINDER_SAGITTA_MM):
        _emit_seg(out, win, piece[0], piece[3], Tag(item, elem, "curve", b, t0, t1))
        return
    tm = (t0 + t1) / 2
    _flatten_cubic(out, win, item, elem, b, t0, tm, depth + 1)
    _flatten_cubic(out, win, item, elem, b, tm, t1, depth + 1)


def _flatten(items, window: QRectF) -> list[Piece]:
    """Tagged straight segments of every item's drawn path inside *window*.

    ``MoveTo``/``LineTo`` -> one segment; ``CurveTo`` (cubic; what circles,
    arcs, ellipses and splines draw) -> adaptive subdivision at
    ``REGION_FINDER_SAGITTA_MM``. Segments wholly outside the window (padded
    by the weld tolerance) are dropped.
    """
    pad = CHAIN_WELD_MM
    win = (window.left() - pad, window.top() - pad, window.right() + pad, window.bottom() + pad)
    out: list[Piece] = []
    Move = QPainterPath.ElementType.MoveToElement
    Line = QPainterPath.ElementType.LineToElement
    Curve = QPainterPath.ElementType.CurveToElement
    for item in items:
        path = halo_scene_path(item)
        n = path.elementCount()
        prev = None
        i = 0
        while i < n:
            e = path.elementAt(i)
            if e.type == Move:
                prev = (e.x, e.y)
                i += 1
            elif e.type == Line:
                cur = (e.x, e.y)
                if prev is not None:
                    _emit_seg(out, win, prev, cur, Tag(item, i, "line", None, 0.0, 1.0))
                prev = cur
                i += 1
            elif e.type == Curve and i + 2 < n and prev is not None:
                d1, d2 = path.elementAt(i + 1), path.elementAt(i + 2)
                b = (prev, (e.x, e.y), (d1.x, d1.y), (d2.x, d2.y))
                _flatten_cubic(out, win, item, i, b)
                prev = b[3]
                i += 3
            else:
                i += 1
    return out


# ── 2. Split at crossings ───────────────────────────────────────────────────

def _param_on(p: Piece, q: QPointF) -> float:
    dx, dy = p.x1 - p.x0, p.y1 - p.y0
    L2 = dx * dx + dy * dy
    if L2 < _EPS:
        return 0.0
    return ((q.x() - p.x0) * dx + (q.y() - p.y0) * dy) / L2


def _bucket_grid(pieces: list[Piece], window: QRectF):
    """``{(bx, by): [piece index, ...]}`` over a REGION_FINDER_BUCKETS² grid."""
    B = REGION_FINDER_BUCKETS
    w = max(window.width(), 1e-6) / B
    h = max(window.height(), 1e-6) / B
    ox, oy = window.left(), window.top()
    grid: dict = {}
    for idx, p in enumerate(pieces):
        x0, y0, x1, y1 = p.bbox()
        bx0 = max(0, min(B - 1, int((x0 - ox) // w)))
        bx1 = max(0, min(B - 1, int((x1 - ox) // w)))
        by0 = max(0, min(B - 1, int((y0 - oy) // h)))
        by1 = max(0, min(B - 1, int((y1 - oy) // h)))
        for bx in range(bx0, bx1 + 1):
            for by in range(by0, by1 + 1):
                grid.setdefault((bx, by), []).append(idx)
    return grid


def _split_all(pieces: list[Piece], window: QRectF) -> list[Piece]:
    """Cut every piece at each crossing with another piece (tags interpolated)."""
    grid = _bucket_grid(pieces, window)
    cuts: list[list[float]] = [[] for _ in pieces]
    seen: set = set()
    boxes = [p.bbox() for p in pieces]
    for members in grid.values():
        for a in range(len(members)):
            i = members[a]
            bi = boxes[i]
            for b in range(a + 1, len(members)):
                j = members[b]
                key = (i, j) if i < j else (j, i)
                if key in seen:
                    continue
                seen.add(key)
                bj = boxes[j]
                if bi[2] < bj[0] or bj[2] < bi[0] or bi[3] < bj[1] or bj[3] < bi[1]:
                    continue
                pi, pj = pieces[i], pieces[j]
                q = line_line_intersection(QPointF(pi.x0, pi.y0), QPointF(pi.x1, pi.y1),
                                           QPointF(pj.x0, pj.y0), QPointF(pj.x1, pj.y1))
                if q is None:
                    continue
                cuts[i].append(_param_on(pi, q))
                cuts[j].append(_param_on(pj, q))
    out: list[Piece] = []
    for p, ts in zip(pieces, cuts):
        params = sorted(t for t in ts if _EPS < t < 1.0 - _EPS)
        prev = 0.0
        for t in params + [1.0]:
            if t - prev > _EPS:
                out.append(p.sub(prev, t))
                prev = t
    return out
