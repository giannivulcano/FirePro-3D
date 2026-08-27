# firepro3d/align_engine.py
"""ALIGN acquire-and-track — pure ray & intersection math (Qt-free).

Entity-agnostic, no Qt imports, no firepro3d imports. Holds the transient
tracking-ray data model (:class:`Ray`, :class:`AcquiredRef`) and the geometry
used by the ALIGN picker: ray builders, path×path / path×segment intersection,
projection-onto-ray, and distance-along-ray.
See docs/specs/align-placement.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ── ALIGN acquire-and-track data model ─────────────────────────────────────

@dataclass(frozen=True)
class Ray:
    """A transient tracking vector (origin + unit direction) in scene units."""
    origin: tuple[float, float]
    direction: tuple[float, float]   # unit vector
    kind: str                        # "hv" | "extension" | "parallel" | "perpendicular"
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
    captured direction and a perpendicular ray (that direction rotated 90°) when
    present. direction-acquire → a parallel ray in the captured direction
    anchored at *active_point*.
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
                    # Perpendicular: object direction rotated 90° ((-uy, ux)),
                    # so the user can draw ACROSS the object through its endpoint.
                    perp = (-u[1], u[0])
                    rays.append(Ray(a.point, perp, "perpendicular", a.source_id))
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

