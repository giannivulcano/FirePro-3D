"""HATCH line families to one rectangular pattern tile (HF7 D6, D7). Pure, Qt-free.

A family is a lattice of translations ``m * offset + n * L * u``. The tile is
the smallest axis-aligned W x H that every family's lattice contains, within a
drift limit and a size cap. Content sits in the cell frame ``stamp_lattice``
uses: x 0..W, y -H..0.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from .constants import HATCH_TILE_MAX_SEGMENTS

_DRIFT = 1e-3       # allowed drift per tile, as a fraction of the finest spacing
_CAP = 64           # tile edge <= this x the finest spacing
_MAX_ROWS = 2048    # rows searched for a dashed family's period
_MAX_DASHES = 64    # dash repeats searched along an axis-aligned family
_DOT = 0.01         # a zero-length dash becomes a line this x the finest spacing
_EPS = 1e-9
_KEY_DIGITS = 4     # key rounding, as decimals of the tile width
_FREE = "free"      # the family sets no constraint on this axis


@dataclass(frozen=True)
class Tile:
    """One converted tile. Segments are (x1, y1, x2, y2) in the cell frame."""
    w: float
    h: float
    spacing: float
    segments: tuple
    key: str


class _Family:
    def __init__(self, rec: dict, origin: tuple[float, float]):
        a = math.radians(rec["angle"])
        self.u = (math.cos(a), math.sin(a))
        self.base = (rec["base"][0] - origin[0], rec["base"][1] - origin[1])
        self.offset = (rec["offset"][0], rec["offset"][1])
        self.dashes = list(rec.get("dashes") or ())
        self.length = sum(abs(d) for d in self.dashes)
        self.signed = self.offset[0] * -self.u[1] + self.offset[1] * self.u[0]
        self.spacing = abs(self.signed)


def _period(f: _Family, smin: float, axis: int):
    """Smallest positive X with X along *axis* in *f*'s lattice.

    Returns ``_FREE`` for an undashed family running along the axis and None
    when no period exists within the search.
    """
    ux, uy = f.u
    ox, oy = f.offset
    uc, oc, ua, oa = (uy, oy, ux, ox) if axis == 0 else (ux, ox, uy, oy)
    if not f.dashes:
        if abs(uc) < _EPS:
            return _FREE
        return f.spacing / abs(uc) if f.spacing > _EPS else None
    best = None
    for m in range(_MAX_ROWS + 1):
        if abs(uc) < _EPS:
            if m and abs(oc) > _EPS:
                break
            cands = [m * oa + k * f.length * ua for k in range(-_MAX_DASHES, _MAX_DASHES + 1)]
        else:
            n = (-m * oc) / (f.length * uc)
            k = round(n)
            if abs(n - k) * f.length > _DRIFT * smin:
                continue
            cands = [m * oa + k * f.length * ua]
        for x in cands:
            x = abs(x)
            if x > _EPS and (best is None or x < best):
                best = x
        if best is not None and m > _CAP:
            break
    return best


def _common(periods: list, smin: float) -> float | None:
    """Least common multiple of *periods* within drift and the cap."""
    vals = [p for p in periods if p != _FREE]
    if any(p is None for p in vals):
        return None
    if not vals:
        return smin
    base = max(vals)
    for k in range(1, _MAX_ROWS + 1):
        x = base * k
        if x > _CAP * smin * 1.0001:
            return None
        if all(abs(x / v - round(x / v)) * v <= _DRIFT * smin for v in vals):
            return x
    return None


def _clip(a, b, w, h):
    """Segment *a*-*b* clipped to x 0..w, y -h..0 (Liang-Barsky); None if outside."""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0]), (dx, w - a[0]), (-dy, a[1] + h), (dy, -a[1])):
        if abs(p) < _EPS:
            if q < -_EPS:       # a stroke on an edge, give or take float noise
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    x1, y1 = a[0] + t0 * dx, a[1] + t0 * dy
    x2, y2 = a[0] + t1 * dx, a[1] + t1 * dy
    return (min(max(x1, 0.0), w), min(max(y1, -h), 0.0),
            min(max(x2, 0.0), w), min(max(y2, -h), 0.0))


def _pieces(f: _Family, smin: float) -> list[tuple[float, float]]:
    """(start, end) of each stroke in one dash repeat, along the line."""
    out, pos = [], 0.0
    for d in f.dashes:
        if d > 0:
            out.append((pos, pos + d))
        elif d == 0:
            half = _DOT * smin / 2
            out.append((pos - half, pos + half))
        pos += abs(d)
    return out


def _family_segments(f: _Family, w, h, smin, out: list) -> bool:
    """Append *f*'s strokes in the cell; False past the segment cap."""
    corners = [(0.0, 0.0), (w, 0.0), (0.0, -h), (w, -h)]
    n = (-f.u[1], f.u[0])
    across = [(c[0] - f.base[0]) * n[0] + (c[1] - f.base[1]) * n[1] for c in corners]
    if f.spacing > _EPS:
        lo = math.floor(min(across) / f.spacing) - 1
        hi = math.ceil(max(across) / f.spacing) + 1
        rows = range(min(lo, -hi), max(hi, -lo) + 1)
    else:
        rows = range(0, 1)
    reach = w + h
    pieces = _pieces(f, smin) if f.dashes else None
    for m in rows:
        ox = f.base[0] + m * f.offset[0]
        oy = f.base[1] + m * f.offset[1]
        along = [(c[0] - ox) * f.u[0] + (c[1] - oy) * f.u[1] for c in corners]
        tmin, tmax = min(along), max(along)
        spans = [(tmin - reach, tmax + reach)]
        if pieces is not None:
            k0 = math.floor(tmin / f.length) - 1
            k1 = math.ceil(tmax / f.length) + 1
            spans = [(k * f.length + a, k * f.length + b)
                     for k in range(k0, k1 + 1) for a, b in pieces]
        for a, b in spans:
            seg = _clip((ox + a * f.u[0], oy + a * f.u[1]),
                        (ox + b * f.u[0], oy + b * f.u[1]), w, h)
            if seg is None or math.hypot(seg[2] - seg[0], seg[3] - seg[1]) < _EPS:
                continue
            # A stroke lying on the right or bottom edge is the same stroke as
            # the one on the left or top edge of the next cell (the lattice is
            # periodic): keep one, or stamping draws it twice.
            if ((abs(seg[0] - w) < _EPS and abs(seg[2] - w) < _EPS)
                    or (abs(seg[1] + h) < _EPS and abs(seg[3] + h) < _EPS)):
                continue
            out.append(seg)
            if len(out) > HATCH_TILE_MAX_SEGMENTS:
                return False
    return True


def key_of(segments, w: float, h: float) -> str:
    """Dedupe key: content scaled to the tile width, so size and order vanish."""
    rows = []
    for x1, y1, x2, y2 in segments:
        a = (round(x1 / w, _KEY_DIGITS), round(y1 / w, _KEY_DIGITS))
        b = (round(x2 / w, _KEY_DIGITS), round(y2 / w, _KEY_DIGITS))
        rows.append((a, b) if a <= b else (b, a))
    text = repr((round(h / w, _KEY_DIGITS), sorted(rows)))
    return hashlib.sha1(text.encode()).hexdigest()


def convert(families: list[dict]) -> Tile | None:
    """The tile of *families* (scene-space records), or None if none exists.

    Bases are taken relative to the first family's, so a hatch's position does
    not change the result: pattern phase is not preserved (design, Changes to
    the concept).
    """
    if not families:
        return None
    origin = (families[0]["base"][0], families[0]["base"][1])
    fams = [_Family(r, origin) for r in families]
    spacings = [f.spacing for f in fams if f.spacing > _EPS]
    if not spacings:
        return None
    smin = min(spacings)
    w = _common([_period(f, smin, 0) for f in fams], smin)
    h = _common([_period(f, smin, 1) for f in fams], smin)
    if w is None or h is None:
        return None
    segments: list = []
    for f in fams:
        if not _family_segments(f, w, h, smin, segments):
            return None
    if not segments:
        return None
    return Tile(w, h, smin, tuple(segments), key_of(segments, w, h))
