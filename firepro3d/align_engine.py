# firepro3d/align_engine.py
"""ALIGN acquire-and-track — pure ray & intersection math (Qt-free).

Entity-agnostic, no Qt imports, no firepro3d imports. Holds the transient
tracking-ray data model (:class:`Ray`, :class:`AcquiredRef`) and the geometry
used by the ALIGN picker: ray builders, path×path / path×segment intersection,
projection-onto-ray, and distance-along-ray.
See docs/specs/align-placement.md.

NOTE: :class:`ReferenceFeature`, :class:`Guide`, :class:`AlignResult`, and
:class:`AlignEngine` below are the *retired* auto-proximity H/V engine, kept as
thin backward-compat shims so the old Model_Space seam (``_collect_alignment_refs``
+ ``_align_engine.resolve``) and its gridline/wall providers keep the suite green.
Task 6 rewrites that seam onto the acquire machine and removes these shims.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


# ── ALIGN acquire-and-track data model ─────────────────────────────────────

@dataclass(frozen=True)
class Ray:
    """A transient tracking vector (origin + unit direction) in scene units."""
    origin: tuple[float, float]
    direction: tuple[float, float]   # unit vector
    kind: str                        # "hv" | "extension" | "parallel"
    source_id: int


@dataclass(frozen=True)
class AcquiredRef:
    """One acquisition snapshot held by AlignController."""
    point: tuple[float, float] | None      # None for a pure direction-acquire
    direction: tuple[float, float] | None  # extension/parallel dir (raw, un-normalised)
    flavor: str                            # "point" | "direction"
    snap_type: str
    source_id: int


def _unit(dx: float, dy: float) -> tuple[float, float] | None:
    n = math.hypot(dx, dy)
    if n < 1e-9:
        return None
    return (dx / n, dy / n)


def rays_for_acquired(acquired: list[AcquiredRef],
                      active_point: tuple[float, float]) -> list[Ray]:
    """Build the transient tracking rays for the current acquired set.

    point-acquire → H + V rays from the point; + an extension ray along its
    captured direction when present. direction-acquire → a parallel ray in the
    captured direction anchored at *active_point*.
    """
    rays: list[Ray] = []
    for a in acquired:
        if a.flavor == "point" and a.point is not None:
            rays.append(Ray(a.point, (1.0, 0.0), "hv", a.source_id))
            rays.append(Ray(a.point, (0.0, 1.0), "hv", a.source_id))
            if a.direction is not None:
                u = _unit(*a.direction)
                if u is not None:
                    rays.append(Ray(a.point, u, "extension", a.source_id))
        elif a.flavor == "direction" and a.direction is not None:
            u = _unit(*a.direction)
            if u is not None:
                rays.append(Ray(active_point, u, "parallel", a.source_id))
    return rays


def path_x_path(a: Ray, b: Ray) -> tuple[float, float] | None:
    """Intersection of two infinite rays, or None if parallel/degenerate."""
    x1, y1 = a.origin
    dx1, dy1 = a.direction
    x3, y3 = b.origin
    dx2, dy2 = b.direction
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-9:
        return None
    t = ((x3 - x1) * dy2 - (y3 - y1) * dx2) / denom
    return (x1 + t * dx1, y1 + t * dy1)


def path_x_segment(ray: Ray, s1: tuple[float, float],
                   s2: tuple[float, float]) -> tuple[float, float] | None:
    """Intersection of an infinite ray with a finite segment, or None."""
    x1, y1 = ray.origin
    dx1, dy1 = ray.direction
    x3, y3 = s1
    x4, y4 = s2
    dx2, dy2 = x4 - x3, y4 - y3
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-9:
        return None
    t = ((x3 - x1) * dy2 - (y3 - y1) * dx2) / denom   # along the ray (infinite)
    u = ((x3 - x1) * dy1 - (y3 - y1) * dx1) / denom   # along the segment [0,1]
    if u < -1e-9 or u > 1 + 1e-9:
        return None
    return (x1 + t * dx1, y1 + t * dy1)


def project_to_ray(pt: tuple[float, float],
                   ray: Ray) -> tuple[tuple[float, float], float]:
    """Return (foot on the ray, signed distance-from-origin along it)."""
    px, py = pt
    ox, oy = ray.origin
    dx, dy = ray.direction
    t = (px - ox) * dx + (py - oy) * dy      # dir is unit → t is signed distance
    return ((ox + t * dx, oy + t * dy), t)


def point_along_ray(ray: Ray, distance: float) -> tuple[float, float]:
    """Return origin + distance·direction."""
    ox, oy = ray.origin
    dx, dy = ray.direction
    return (ox + distance * dx, oy + distance * dy)


# ── Retired auto-proximity H/V engine (backward-compat shims, Task 6 removes) ─

@dataclass(frozen=True)
class ReferenceFeature:
    """A point/edge/face an active placement point can align to."""
    kind: str            # "point" (now); "edge"/"face" reserved
    x: float
    y: float
    source_id: int       # id() of the source item — for excluding the active item
    label: str = ""      # "endpoint"/"bubble" — glyph/debug


@dataclass
class Guide:
    orientation: str     # "h" or "v"
    coord: float         # y for "h", x for "v"
    ref: ReferenceFeature


@dataclass
class AlignResult:
    snapped: tuple[float, float]
    guides: list[Guide] = field(default_factory=list)
    priority: str = "free"   # "guide-intersection" | "single-guide" | "free"


class AlignEngine:
    """Pure geometry. No Qt, no scene knowledge. Model_Space owns one."""

    def resolve(self, cursor: tuple[float, float],
                refs: list[ReferenceFeature], tol: float) -> AlignResult:
        cx, cy = cursor
        # Nearest vertical (shared X) and horizontal (shared Y) candidate within tol.
        best_v = self._nearest(refs, key=lambda r: abs(r.x - cx), tol=tol)
        best_h = self._nearest(refs, key=lambda r: abs(r.y - cy), tol=tol)
        guides: list[Guide] = []
        sx, sy = cx, cy
        if best_v is not None:
            guides.append(Guide("v", best_v.x, best_v))
            sx = best_v.x
        if best_h is not None:
            guides.append(Guide("h", best_h.y, best_h))
            sy = best_h.y
        if best_v is not None and best_h is not None:
            priority = "guide-intersection"
        elif guides:
            priority = "single-guide"
        else:
            priority = "free"
        return AlignResult(snapped=(sx, sy), guides=guides, priority=priority)

    @staticmethod
    def _nearest(refs, key, tol):
        best, best_d = None, tol
        for r in refs:
            d = key(r)
            if d < best_d:            # strict: ties keep the earlier candidate
                best_d = d
                best = r
        return best
