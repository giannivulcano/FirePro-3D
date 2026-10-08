"""Arc-length walker over a stroke's analytic pieces (linetypes.md LT3, H3-a).

Pieces live in one coordinate frame (an item's local frame, or a block
definition's origin-relative frame). Angles follow Qt's ``arcTo`` convention:
a point at angle ``a`` (degrees) on a circle is ``(cx + r·cos a, cy − r·sin a)``
in scene (Y-down) coordinates, positive sweep = Qt CCW. Ellipses use Qt's
parametric angle in the ellipse frame ``translate(c)·rotate(−rot)`` (P4
probe 2026-10-04: ``arcMoveTo`` on an ellipse rect is parametric).

Phase (D-L9 / D-L9b): a straight piece's phase is the projection of its
canonical start on its infinite axis, measured from the anchor's projection;
an arc's is ``r × a0``; an ellipse arc's is its arc length from parameter 0;
a curve's is 0.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from functools import lru_cache

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath, QTransform

# Import-safe at module level: stroke_style pulls in only constants and
# paper_display, neither of which imports path_walk (no cycle).
from .stroke_style import ENDS

_EPS = 1e-9
_ELLIPSE_SAMPLES = 512


@dataclass(frozen=True)
class Seg:
    """Straight piece from (x0, y0) to (x1, y1)."""
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class Arc:
    """Circular arc: centre, radius, start angle, sweep (degrees, sweep > 0)."""
    cx: float
    cy: float
    r: float
    a0: float
    sweep: float


@dataclass(frozen=True)
class EllipseArc:
    """Elliptical arc in the frame translate(cx, cy)·rotate(−rot) (degrees).

    ``t0`` / ``sweep`` are Qt parametric angles (degrees, sweep > 0).
    """
    cx: float
    cy: float
    rx: float
    ry: float
    rot: float
    t0: float
    sweep: float


@dataclass(frozen=True)
class Curve:
    """Free curve (splines) as a flattened polyline; phase starts at its start."""
    pts: tuple

    def __post_init__(self):
        # Hash once: cache lookups (``_curve_cum``, the expansion LRU) would
        # otherwise rehash every vertex per dash.
        object.__setattr__(self, "_hash", hash(self.pts))

    def __hash__(self):
        return self._hash

    @classmethod
    def from_path(cls, path: QPainterPath) -> "Curve":
        """Flatten *path* (first subpath) into a Curve.

        Qt's default flattening strays > 0.1 mm from a mm-scale cubic, so the
        path is flattened scaled up by ``LINETYPE_CURVE_FLATTEN_SCALE`` and
        mapped back (~0.01 mm from the drawn curve).
        """
        from .constants import LINETYPE_CURVE_FLATTEN_SCALE as k
        polys = path.toSubpathPolygons(QTransform.fromScale(k, k))
        pts = tuple((p.x() / k, p.y() / k) for p in polys[0]) if polys else ()
        return cls(pts)


Piece = Seg | Arc | EllipseArc | Curve


# ── per-type helpers ──────────────────────────────────────────────────────

def _norm360(a: float) -> float:
    a = math.fmod(a, 360.0)
    return a + 360.0 if a < 0 else a


@lru_cache(maxsize=1024)
def _ellipse_table(rx: float, ry: float) -> tuple:
    """Cumulative arc length at evenly spaced parameters over one turn."""
    n = _ELLIPSE_SAMPLES
    cum = [0.0]
    px, py = rx, 0.0
    for i in range(1, n + 1):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), -ry * math.sin(t)
        cum.append(cum[-1] + math.hypot(x - px, y - py))
        px, py = x, y
    return tuple(cum)


def _ellipse_s_of_t(rx: float, ry: float, t_deg: float) -> float:
    """Arc length from parameter 0 to *t_deg* (any value; whole turns add)."""
    cum = _ellipse_table(rx, ry)
    turns, rem = divmod(t_deg, 360.0)
    f = rem / 360.0 * _ELLIPSE_SAMPLES
    i = min(int(f), _ELLIPSE_SAMPLES - 1)
    s = cum[i] + (cum[i + 1] - cum[i]) * (f - i)
    return turns * cum[-1] + s


def _ellipse_t_of_s(rx: float, ry: float, s: float) -> float:
    """Inverse of ``_ellipse_s_of_t`` (degrees)."""
    cum = _ellipse_table(rx, ry)
    per = cum[-1]
    turns, rem = divmod(s, per)
    i = max(0, min(bisect.bisect_right(cum, rem) - 1, _ELLIPSE_SAMPLES - 1))
    seg = cum[i + 1] - cum[i]
    f = i + ((rem - cum[i]) / seg if seg > _EPS else 0.0)
    return turns * 360.0 + f / _ELLIPSE_SAMPLES * 360.0


def _ellipse_frame(e: EllipseArc) -> QTransform:
    t = QTransform()
    t.translate(e.cx, e.cy)
    t.rotate(-e.rot)
    return t


def point_at_param(e: EllipseArc, t_deg: float) -> QPointF:
    """Point of *e* at Qt parametric angle *t_deg* (scene frame)."""
    a = math.radians(t_deg)
    return _ellipse_frame(e).map(QPointF(e.rx * math.cos(a), -e.ry * math.sin(a)))


@lru_cache(maxsize=256)
def _curve_cum(c: Curve) -> tuple:
    """Cumulative vertex arc lengths of *c*, computed once per Curve value
    (expansion calls ``split`` / ``point_at`` per dash: O(log n) each)."""
    cum = [0.0]
    for (x0, y0), (x1, y1) in zip(c.pts, c.pts[1:]):
        cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
    return tuple(cum)


# ── public API ────────────────────────────────────────────────────────────

def canonical(p):
    """*p* in canonical walking direction (Segs folded to [0°, 180°))."""
    if isinstance(p, Seg):
        dx, dy = p.x1 - p.x0, p.y1 - p.y0
        if dx < -_EPS or (abs(dx) <= _EPS and dy < 0):
            return Seg(p.x1, p.y1, p.x0, p.y0)
        return p
    if isinstance(p, Arc) and p.sweep < 0:
        return Arc(p.cx, p.cy, p.r, _norm360(p.a0 + p.sweep), -p.sweep)
    if isinstance(p, EllipseArc) and p.sweep < 0:
        return EllipseArc(p.cx, p.cy, p.rx, p.ry, p.rot,
                          _norm360(p.t0 + p.sweep), -p.sweep)
    return p


def split_at_zero(p) -> tuple:
    """Canonical *p* broken at every 0° crossing (F1 ruling 2026-10-05).

    An Arc / EllipseArc's dash rhythm restarts at its circle's / ellipse's 0°:
    the phase at any point is its own arc length from 0° (angle in [0, 360)).
    Walking each returned sub-piece from its ``phase0`` realises that, so
    trimming or breaking an arc across 0° never moves surviving dashes. A
    full turn starting at 0° stays one piece (seam at 0°). Other pieces pass
    through as a 1-tuple.
    """
    p = canonical(p)
    if isinstance(p, Arc):
        start, rest = _norm360(p.a0), p.sweep
    elif isinstance(p, EllipseArc):
        start, rest = _norm360(p.t0), p.sweep
    else:
        return (p,)
    out = []
    while rest > _EPS:
        span = min(rest, 360.0 - start)
        if span > _EPS:
            if isinstance(p, Arc):
                out.append(Arc(p.cx, p.cy, p.r, start, span))
            else:
                out.append(EllipseArc(p.cx, p.cy, p.rx, p.ry, p.rot, start, span))
        rest -= span
        start = 0.0
    return tuple(out) or (p,)


def length(p) -> float:
    """Arc length of *p* in its frame's units (mm)."""
    if isinstance(p, Seg):
        return math.hypot(p.x1 - p.x0, p.y1 - p.y0)
    if isinstance(p, Arc):
        return abs(p.r * math.radians(p.sweep))
    if isinstance(p, EllipseArc):
        return abs(_ellipse_s_of_t(p.rx, p.ry, p.t0 + p.sweep)
                   - _ellipse_s_of_t(p.rx, p.ry, p.t0))
    return _curve_cum(p)[-1]


def point_at(p, s: float) -> QPointF:
    """Point at arc length *s* from the piece start.

    Zero-length (degenerate) Arcs / EllipseArcs return their start point.
    """
    if isinstance(p, Seg):
        L = length(p) or 1.0
        f = s / L
        return QPointF(p.x0 + (p.x1 - p.x0) * f, p.y0 + (p.y1 - p.y0) * f)
    if isinstance(p, Arc):
        a = math.radians(p.a0 + (math.degrees(s / p.r) if p.r > _EPS else 0.0))
        return QPointF(p.cx + p.r * math.cos(a), p.cy - p.r * math.sin(a))
    if isinstance(p, EllipseArc):
        if _ellipse_table(p.rx, p.ry)[-1] <= _EPS:
            return point_at_param(p, p.t0)
        s0 = _ellipse_s_of_t(p.rx, p.ry, p.t0)
        return point_at_param(p, _ellipse_t_of_s(p.rx, p.ry, s0 + s))
    if len(p.pts) < 2:
        return QPointF(*p.pts[0]) if p.pts else QPointF()
    cum = _curve_cum(p)
    i = max(0, min(bisect.bisect_right(cum, s) - 1, len(cum) - 2))
    seg = cum[i + 1] - cum[i]
    f = (s - cum[i]) / seg if seg > _EPS else 0.0
    (x0, y0), (x1, y1) = p.pts[i], p.pts[i + 1]
    return QPointF(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)


def phase0(p, anchor: tuple) -> float:
    """Pattern phase at the start of canonical piece *p* (D-L9 / D-L9b)."""
    if isinstance(p, Seg):
        L = length(p)
        if L <= _EPS:
            return 0.0
        ux, uy = (p.x1 - p.x0) / L, (p.y1 - p.y0) / L
        return (p.x0 - anchor[0]) * ux + (p.y0 - anchor[1]) * uy
    if isinstance(p, Arc):
        return p.r * math.radians(_norm360(p.a0))
    if isinstance(p, EllipseArc):
        return _ellipse_s_of_t(p.rx, p.ry, _norm360(p.t0))
    return 0.0


def split(p, s0: float, s1: float):
    """Exact sub-piece of canonical *p* between arc lengths s0 < s1."""
    if isinstance(p, Seg):
        a, b = point_at(p, s0), point_at(p, s1)
        return Seg(a.x(), a.y(), b.x(), b.y())
    if isinstance(p, Arc):
        return Arc(p.cx, p.cy, p.r, p.a0 + math.degrees(s0 / p.r),
                   math.degrees((s1 - s0) / p.r))
    if isinstance(p, EllipseArc):
        base = _ellipse_s_of_t(p.rx, p.ry, p.t0)
        t0 = _ellipse_t_of_s(p.rx, p.ry, base + s0)
        t1 = _ellipse_t_of_s(p.rx, p.ry, base + s1)
        return EllipseArc(p.cx, p.cy, p.rx, p.ry, p.rot, t0, t1 - t0)
    cum = _curve_cum(p)
    a, b = point_at(p, s0), point_at(p, s1)
    i0, i1 = bisect.bisect_right(cum, s0), bisect.bisect_left(cum, s1)
    return Curve(((a.x(), a.y()), *p.pts[i0:i1], (b.x(), b.y())))


def append(path: QPainterPath, p) -> None:
    """Append *p* to *path* as a new subpath (arcs as true curves)."""
    if isinstance(p, Seg):
        path.moveTo(p.x0, p.y0)
        path.lineTo(p.x1, p.y1)
    elif isinstance(p, Arc):
        r = QRectF(p.cx - p.r, p.cy - p.r, 2 * p.r, 2 * p.r)
        path.arcMoveTo(r, p.a0)
        path.arcTo(r, p.a0, p.sweep)
    elif isinstance(p, EllipseArc):
        local = QPainterPath()
        r = QRectF(-p.rx, -p.ry, 2 * p.rx, 2 * p.ry)
        local.arcMoveTo(r, p.t0)
        local.arcTo(r, p.t0, p.sweep)
        path.addPath(_ellipse_frame(p).map(local))
    elif p.pts:
        path.moveTo(*p.pts[0])
        for q in p.pts[1:]:
            path.lineTo(*q)


def to_path(pieces) -> QPainterPath:
    """All *pieces* as one path (one subpath each)."""
    path = QPainterPath()
    for p in pieces:
        append(path, p)
    return path


def map_piece(p, t: QTransform):
    """*p* mapped through a rigid, orientation-preserving transform *t*.

    Raises:
        ValueError: *t* reflects (determinant < 0) -- arc angles and sweeps
            would silently come out wrong.
    """
    if t.m11() * t.m22() - t.m12() * t.m21() < 0:
        raise ValueError("map_piece needs an orientation-preserving transform")
    d = math.degrees(math.atan2(-t.m12(), t.m11()))      # Qt-angle offset
    if isinstance(p, Seg):
        a, b = t.map(QPointF(p.x0, p.y0)), t.map(QPointF(p.x1, p.y1))
        return Seg(a.x(), a.y(), b.x(), b.y())
    if isinstance(p, Arc):
        c = t.map(QPointF(p.cx, p.cy))
        return Arc(c.x(), c.y(), p.r, _norm360(p.a0 + d), p.sweep)
    if isinstance(p, EllipseArc):
        c = t.map(QPointF(p.cx, p.cy))
        return EllipseArc(c.x(), c.y(), p.rx, p.ry, p.rot + d, p.t0, p.sweep)
    return Curve(tuple((q.x(), q.y()) for q in
                       (t.map(QPointF(*xy)) for xy in p.pts)))


def total_length(pieces) -> float:
    """Sum of piece lengths."""
    return sum(length(p) for p in pieces)


def point_at_total(pieces, s: float) -> QPointF | None:
    """Point at arc length *s* along the concatenated pieces (badge anchor).

    Zero-length pieces are skipped; all-degenerate pieces give the first
    piece's start.
    """
    if not pieces:
        return None
    last = None
    for p in pieces:
        L = length(p)
        if L <= _EPS:
            continue
        if s <= L:
            return point_at(p, s)
        s -= L
        last = p
    if last is not None:
        return point_at(last, length(last))
    return point_at(pieces[0], 0.0)


# ── LT5: stroke ends ──────────────────────────────────────────────────────

def tangent_at(p, s: float) -> tuple[float, float]:
    """Unit direction of travel of *p* at arc length *s* (piece frame).

    Follows ``point_at``'s parametrisation: a Seg runs (x0, y0) -> (x1, y1)
    as given (never canonicalised); an Arc / EllipseArc runs from ``a0`` /
    ``t0`` by +s -- on Qt's Y-down circle the point at angle ``a`` is
    ``(cx + r cos a, cy - r sin a)``, so its s-derivative is
    ``(-sin a, -cos a)``; a Curve takes the flattened segment at *s*
    (zero-length segments skipped, looking forward first). ``(0.0, 0.0)``
    for a degenerate piece.
    """
    if isinstance(p, Seg):
        dx, dy = p.x1 - p.x0, p.y1 - p.y0
    elif isinstance(p, Arc):
        if p.r <= _EPS:
            return (0.0, 0.0)
        a = math.radians(p.a0) + s / p.r
        dx, dy = -math.sin(a), -math.cos(a)
    elif isinstance(p, EllipseArc):
        if _ellipse_table(p.rx, p.ry)[-1] <= _EPS:
            return (0.0, 0.0)
        t = math.radians(_ellipse_t_of_s(
            p.rx, p.ry, _ellipse_s_of_t(p.rx, p.ry, p.t0) + s))
        f = _ellipse_frame(p)
        o = f.map(QPointF(0.0, 0.0))
        v = f.map(QPointF(-p.rx * math.sin(t), -p.ry * math.cos(t)))
        dx, dy = v.x() - o.x(), v.y() - o.y()
    else:
        pts = p.pts
        if len(pts) < 2:
            return (0.0, 0.0)
        cum = _curve_cum(p)
        i = max(0, min(bisect.bisect_right(cum, s) - 1, len(cum) - 2))
        dx = dy = 0.0
        for j in [*range(i, len(pts) - 1), *range(i - 1, -1, -1)]:
            (x0, y0), (x1, y1) = pts[j], pts[j + 1]
            if math.hypot(x1 - x0, y1 - y0) > _EPS:
                dx, dy = x1 - x0, y1 - y0
                break
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > _EPS else (0.0, 0.0)


def end_frame(pieces, which: str, trim: float):
    """Attach point + outward unit vector of one stroke end (LT5 Q5 / Q6).

    *which* is ``"start"`` (s = 0 of the first live piece) or ``"finish"``
    (the end of the last). +X of the end block is *outward*: with *trim* > 0
    -X runs from the endpoint to the point *trim* along the path (clamped to
    the length) -- the chord; with *trim* == 0, or a zero chord (an open
    path whose trim point lands back on its end), the endpoint tangent
    pointing off the stroke. Zero-length pieces are skipped.

    Returns:
        ``(attach QPointF, (dx, dy))``, or None for no pieces / a zero-length
        stroke.

    Raises:
        ValueError: *which* is not one of ``stroke_style.ENDS``.
    """
    if which not in ENDS:
        raise ValueError(f"end_frame: which must be one of {ENDS}, got {which!r}")
    live = [p for p in pieces if length(p) > _EPS]
    total = total_length(live)
    if not live or total <= _EPS:
        return None
    start = which == "start"
    at = point_at(live[0], 0.0) if start else point_at(live[-1], length(live[-1]))
    t = min(max(float(trim), 0.0), total)
    if t > _EPS:
        q = point_at_total(live, t if start else total - t)
        dx, dy = at.x() - q.x(), at.y() - q.y()
        n = math.hypot(dx, dy)
        if n > _EPS:
            return at, (dx / n, dy / n)
    if start:
        tx, ty = tangent_at(live[0], 0.0)
        return at, (-tx, -ty)
    return at, tangent_at(live[-1], length(live[-1]))


def trim_pieces(pieces, s0: float, s1: float) -> tuple:
    """*pieces* with *s0* cut from the start and *s1* from the end (LT5).

    Cross-piece on ``split``. A piece kept whole is returned as the same
    object (caches keyed on pieces still hit); zero-length pieces drop out
    once trimming. Negative trims read 0; both <= 0 returns *pieces*
    unchanged (as a tuple); ``s0 + s1`` >= the total length returns ``()``.
    """
    s0, s1 = max(float(s0), 0.0), max(float(s1), 0.0)
    if s0 <= 0.0 and s1 <= 0.0:
        return tuple(pieces)
    hi_total = total_length(pieces) - s1
    if s0 >= hi_total - _EPS:
        return ()
    out, off = [], 0.0
    for p in pieces:
        L = length(p)
        a, b = max(s0 - off, 0.0), min(hi_total - off, L)
        off += L
        if b - a <= _EPS:
            continue
        out.append(p if (a <= 0.0 and b >= L) else split(p, a, b))
    return tuple(out)
