"""Exact wall solids for the 3D view (3D wall solids design D6).

Pure geometry, no Qt: band prisms are unioned and opening cuts subtracted
with manifold3d, which guarantees a closed manifold result.
"""
from __future__ import annotations

import logging
import math

import manifold3d as m3
import numpy as np

log = logging.getLogger(__name__)

_DIGITS = 4                 # vertices rounded to 1e-4 mm (D6)
_MIN_AREA = 1e-6            # mm^2: a smaller band polygon is degenerate (D8)
_MIN_DZ = 1e-6              # mm

Pt = tuple[float, float]
Seg = tuple[Pt, Pt]


def _signed_area(pts: list[Pt]) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
               in zip(pts, pts[1:] + pts[:1])) / 2.0


def _prism(poly, z0: float, z1: float):
    pts = [(round(float(x), _DIGITS), round(float(y), _DIGITS)) for x, y in poly]
    if len(pts) < 3 or abs(_signed_area(pts)) < _MIN_AREA or z1 - z0 < _MIN_DZ:
        return None
    if _signed_area(pts) < 0:
        pts.reverse()                      # CCW: kept by the Positive fill rule
    return m3.Manifold.extrude(m3.CrossSection([pts]), z1 - z0).translate(
        (0.0, 0.0, z0))


def _evaluate(solid, boxes) -> dict | None:
    s = (m3.Manifold.batch_boolean([solid, *boxes], m3.OpType.Subtract)
         if boxes else solid)
    if s.status() != m3.Error.NoError or s.is_empty():
        return None
    mesh = s.to_mesh()
    v = np.asarray(mesh.vert_properties, dtype=float)[:, :3]
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    return {"vertices": v.tolist(), "faces": f.tolist()}


def build_solid(bands, cuts) -> dict | None:
    """Union the band prisms, subtract the cut prisms.

    Args:
        bands: ``[(polygon, z0, z1)]``, polygon = ``[(x, y)]`` in mm.
        cuts: ``[(rect, z0, z1)]`` in the same frame.

    Returns:
        ``{"vertices", "faces"}`` or None (no valid band, or manifold failed
        even without cuts - D8).
    """
    prisms = [p for p in (_prism(*b) for b in bands) if p is not None]
    if not prisms:
        return None
    solid = (prisms[0] if len(prisms) == 1
             else m3.Manifold.batch_boolean(prisms, m3.OpType.Add))
    boxes = [p for p in (_prism(*c) for c in cuts) if p is not None]
    out = _evaluate(solid, boxes)
    if out is None and boxes:
        log.warning("wall solid: opening cut failed; wall drawn uncut")
        out = _evaluate(solid, [])
    return out


def subtract_collinear(a: list[Seg], b: list[Seg], tol: float) -> list[Seg]:
    """Parts of each segment in *a* not covered by a collinear segment of *b*.

    A *b* segment counts only when both its ends lie within *tol* of the *a*
    segment's line; its projection onto the *a* segment is removed.
    """
    out: list[Seg] = []
    for (p, q) in a:
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = math.hypot(dx, dy)
        if length <= tol:
            continue
        ux, uy = dx / length, dy / length
        covered = []
        for (r, s) in b:
            dr = (r[0] - p[0]) * uy - (r[1] - p[1]) * ux
            ds = (s[0] - p[0]) * uy - (s[1] - p[1]) * ux
            if abs(dr) > tol or abs(ds) > tol:
                continue
            tr = (r[0] - p[0]) * ux + (r[1] - p[1]) * uy
            ts = (s[0] - p[0]) * ux + (s[1] - p[1]) * uy
            lo, hi = max(0.0, min(tr, ts)), min(length, max(tr, ts))
            if hi - lo > tol:
                covered.append((lo, hi))
        t = 0.0
        for lo, hi in sorted(covered):
            if lo - t > tol:
                out.append(((p[0] + ux * t, p[1] + uy * t),
                            (p[0] + ux * lo, p[1] + uy * lo)))
            t = max(t, hi)
        if length - t > tol:
            out.append(((p[0] + ux * t, p[1] + uy * t), q))
    return out
