"""Frame math for gridline-hosted blocks.

A hosted block lives on a reference gridline (design
docs/superpowers/specs/2026-10-22-gridline-hosted-blocks-design.md D2): the
record ``host = {"gridline", "offset_mm", "along_mm", "elevation_mm",
"facing"}`` is the single source of truth, and its plan position is derived.
All functions here are pure (no scene writes) and work in world mm (Y-up).
"""
from __future__ import annotations

import math

PARALLEL_EPS = 1e-6


def ppm_of(scene) -> float:
    """Pixels per mm of *scene* (1.0 when it has no ScaleManager)."""
    sm = getattr(scene, "scale_manager", None)
    return sm.pixels_per_mm if sm is not None else 1.0


def gridline_frame(gl, ppm: float):
    """``(ox, oy, ux, uy, nx, ny)``: world origin, unit direction, left normal."""
    ox, oy = gl._origin.x() / ppm, -gl._origin.y() / ppm
    t = math.radians(gl._angle_deg)
    ux, uy = math.cos(t), math.sin(t)
    return ox, oy, ux, uy, -uy, ux


def world_point(gl, host: dict, ppm: float) -> tuple[float, float]:
    """World-mm position of the hosted point."""
    ox, oy, ux, uy, nx, ny = gridline_frame(gl, ppm)
    a, o = float(host["along_mm"]), float(host["offset_mm"])
    return ox + a * ux + o * nx, oy + a * uy + o * ny


def scene_pos(gl, host: dict, ppm: float) -> tuple[float, float]:
    """Plan-scene position (px, Y-down) of the hosted point."""
    wx, wy = world_point(gl, host, ppm)
    return wx * ppm, -wy * ppm


def is_parallel(basis, gl) -> bool:
    """True when the section's look normal is perpendicular to *gl*."""
    _, _, ux, uy, _, _ = gridline_frame(gl, 1.0)
    return abs(basis.nx * ux + basis.ny * uy) < PARALLEL_EPS


def facing_of(basis, gl) -> int:
    """+1 when *basis* looks from the gridline's + side (N.n >= 0), else -1."""
    _, _, _, _, nx, ny = gridline_frame(gl, 1.0)
    return 1 if basis.nx * nx + basis.ny * ny >= 0.0 else -1


def h_sign(basis, gl) -> int:
    """+1 when the section's h grows along the gridline direction (D.u >= 0)."""
    _, _, ux, uy, _, _ = gridline_frame(gl, 1.0)
    return 1 if basis.dx * ux + basis.dy * uy >= 0.0 else -1


def gridline_depth(basis, gl, ppm: float) -> float:
    """Signed distance of the gridline origin from the cut (``basis.d``)."""
    ox, oy, *_ = gridline_frame(gl, ppm)
    return basis.d(ox, oy)


def host_at(basis, gl, h: float, z: float, ppm: float) -> dict:
    """Host record for a click at section ``(h, z)`` on *gl* (offset 0, G8)."""
    ox, oy, *_ = gridline_frame(gl, ppm)
    along = (h - basis.h(ox, oy)) * h_sign(basis, gl)   # D.u = +-1 when parallel
    return {"gridline": gl._uid, "offset_mm": 0.0, "along_mm": along,
            "elevation_mm": float(z), "facing": facing_of(basis, gl)}


def choose_host(basis, gridlines, ppm: float):
    """The parallel gridline nearest the cut with 0 <= d <= depth (G8), or None.

    Ties keep model order (first wins)."""
    best = None
    for gl in gridlines:
        if not is_parallel(basis, gl):
            continue
        d = gridline_depth(basis, gl, ppm)
        if 0.0 <= d <= basis.depth and (best is None or d < best[0]):
            best = (d, gl)
    return best[1] if best else None


def origin_shift_along(gl, old_origin, new_origin, ppm: float) -> float:
    """World-mm axial component of an origin move (grip 0, D6)."""
    _, _, ux, uy, _, _ = gridline_frame(gl, ppm)
    dx = (new_origin.x() - old_origin.x()) / ppm
    dy = -(new_origin.y() - old_origin.y()) / ppm
    return dx * ux + dy * uy


def section_pose(basis, gl, host: dict, rotation: float, mirrored: bool,
                 ppm: float):
    """``(h, v, depth, mirrored, rotation)`` of the copy in *basis*, or None
    outside ``0 <= depth <= basis.depth`` (G6). A view from the other side
    flips ``mirrored`` and negates the rotation (D4)."""
    wx, wy = world_point(gl, host, ppm)
    d = basis.d(wx, wy)
    if not (0.0 <= d <= basis.depth):
        return None
    back = facing_of(basis, gl) != int(host.get("facing", 1))
    return (basis.h(wx, wy), -float(host["elevation_mm"]), d,
            bool(mirrored) != back, -rotation if back else rotation)


HOST_KEYS = ("gridline", "along_mm", "offset_mm", "elevation_mm", "facing")


def valid_host(host) -> bool:
    """True when *host* is a well-formed host record (D3: a malformed record is
    treated as an unresolved one, so a corrupt file cannot raise in a rebuild)."""
    if not isinstance(host, dict) or any(k not in host for k in HOST_KEYS):
        return False
    try:
        for k in HOST_KEYS[1:]:
            float(host[k])
    except (TypeError, ValueError):
        return False
    return True
