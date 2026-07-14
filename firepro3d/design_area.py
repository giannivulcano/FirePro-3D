"""
design_area.py
==============
Persistent annotation representing a fire suppression design area.

Stores a set of sprinklers and a hazard classification, and displays as
the union of per-sprinkler protection tiles.  Two deliberate value
systems (2026-07-11):

* **Calc** — per-sprinkler ``As = min(NFPA S×L, listed Coverage Area)``
  where S/L follow the NFPA 13 measurement convention (max of distance
  to the next sprinkler and 2× wall distance); listing violations are
  recorded in ``spacing_warnings``.
* **Drawing** — tessellating tiles: half the gap toward each neighbour,
  full distance to a facing wall (stop at it), √(listed coverage)/2 on
  open sides.  Tiles never overlap or overshoot walls.

Multiple design areas can coexist; the active one is used for
hydraulic calculations.  Each design area is bound to a level.
"""

import math
from dataclasses import dataclass, field

from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsItem, QStyle
from PyQt6.QtCore import Qt, QPointF, QRectF
from .constants import (DEFAULT_LEVEL, SQFT_TO_MM2, Z_DESIGN_AREA,
                        Z_DESIGN_AREA_CONFIRMED,
                        DA_BADGE_WIDTH_MM, DA_BADGE_TEXT_MM, DA_BADGE_TITLE_MM,
                        DA_BADGE_PAD_MM, DA_BADGE_CORNER_MM, DA_BADGE_LINE_MM)
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QPolygonF, QFont
from .nfpa_curves import (HAZARD_ABBREV, STORAGE_HAZARDS, interpolate_density)

HAZARD_OPTIONS = [
    "Light Hazard",
    "Ordinary Hazard Group 1",
    "Ordinary Hazard Group 2",
    "Extra Hazard Group 1",
    "Extra Hazard Group 2",
]

# Nominal orifice by K-factor (NFPA 13 nominal sizes)
K_TO_ORIFICE: dict[float, str] = {
    2.8: '¼"Ø', 4.2: '⅜"Ø', 5.6: '½"Ø', 8.0: '17/32"Ø',
    11.2: '⅝"Ø', 14.0: '¾"Ø', 16.8: '¾"Ø',
}

_TBD = "TBD"

# Unit conversions for the shared area/density formatters below.
SQFT_TO_M2 = SQFT_TO_MM2 / 1e6          # ft² → m²
GPM_FT2_TO_MM_MIN = 40.746              # gpm/ft² → mm/min


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def _is_imperial(scale_manager) -> bool:
    """True when project display units are imperial.

    Falls back to imperial when no scale manager is available — design
    criteria values are stored in ft² (NFPA basis), so the native unit
    is the safe default."""
    if scale_manager is None:
        return True
    from .scale_manager import DisplayUnit
    return scale_manager.display_unit == DisplayUnit.IMPERIAL


def format_area_sqft(sqft: float, scale_manager) -> str:
    """Format an internally-ft² area per project units.

    Imperial → "1500 sq ft" (project convention, matching Room area
    formatting); metric → "139.4 m²".  Shared by the design-area panel,
    Room design-point button face, and the hydraulic report."""
    if _is_imperial(scale_manager):
        return f"{sqft:.0f} sq ft"
    return f"{sqft * SQFT_TO_M2:.1f} m²"


def format_density(gpm_ft2: float, scale_manager) -> str:
    """Format an internally-gpm/ft² density per project units.

    Imperial → "0.15 gpm/ft²"; metric → "6.11 mm/min"
    (1 gpm/ft² = 40.746 mm/min).  Display-only — no parsing."""
    if _is_imperial(scale_manager):
        return f"{gpm_ft2:.2f} gpm/ft²"
    return f"{gpm_ft2 * GPM_FT2_TO_MM_MIN:.2f} mm/min"


def _dedupe_numeric(values) -> list[str]:
    """Dedupe strings on their numeric value ("130" vs "130.0" collapse
    to one entry, formatted "{v:g}"); non-parseable strings dedupe as-is."""
    seen: set = set()
    out: list[str] = []
    for v in values:
        key = float(v) if _is_float(v) else v
        if key in seen:
            continue
        seen.add(key)
        out.append(f"{key:g}" if isinstance(key, float) else v)
    return out


def system_capacity_gal(pipes) -> float:
    """Water volume of the pipe network in US gallons.

    gal/ft of pipe = 0.040802 × ID²(in) (π/4 · d² · 12 in³ / 231)."""
    total = 0.0
    for p in pipes:
        d = p.get_inner_diameter()
        total += 0.040802 * d * d * p.get_length_ft()
    return total

# ── Geometry helpers ─────────────────────────────────────────────────


def _point_to_segment_dist(px: float, py: float,
                           x1: float, y1: float,
                           x2: float, y2: float) -> float:
    """Minimum distance from point (px, py) to line segment (x1,y1)-(x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _closest_point_on_segment(px: float, py: float,
                              x1: float, y1: float,
                              x2: float, y2: float) -> tuple[float, float]:
    """Closest point on segment (x1,y1)-(x2,y2) to point (px, py)."""
    dx, dy = x2 - x1, y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return (x1, y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
    return (x1 + t * dx, y1 + t * dy)


def _wall_distance_on_side(px: float, py: float,
                           dir_x: float, dir_y: float,
                           walls) -> float | None:
    """Distance along a direction ray to the first wall centreline hit.

    Ray-cast from (px, py) along (dir_x, dir_y) against every wall
    segment — works for walls at any angle.  (The earlier ±45°
    normal-alignment cone missed diagonal walls entirely, letting tiles
    sail through them; 2026-07-13 smoke test.)

    Args:
        px, py: Query point (scene units).
        dir_x, dir_y: Unit direction defining the side.
        walls: Iterable of wall segments exposing ``pt1``/``pt2``.

    Returns:
        Distance in scene units, or ``None`` when the ray hits no wall.
    """
    best: float | None = None
    eps = 1e-9
    for wall in walls:
        ax, ay = wall.pt1.x(), wall.pt1.y()
        sx = wall.pt2.x() - ax
        sy = wall.pt2.y() - ay
        denom = dir_x * sy - dir_y * sx
        if abs(denom) < 1e-12:
            continue  # segment parallel to the ray
        ex, ey = ax - px, ay - py
        t = (ex * sy - ey * sx) / denom          # distance along the ray
        u = (ex * dir_y - ey * dir_x) / denom    # position along the segment
        if t <= eps or u < -1e-6 or u > 1.0 + 1e-6:
            continue
        if best is None or t < best:
            best = t
    return best


# ── Branch-line helpers ──────────────────────────────────────────────


def _branch_direction(node) -> float | None:
    """Return the branch-line angle (radians) for a node.

    * 1 pipe  → that pipe's angle from the node
    * 2 pipes → average of the two unit vectors (handling 180° reversal)
    * 3+ pipes → find the two most co-linear (dot closest to −1) and
                 return their average direction
    * 0 pipes → None
    """
    pipes = getattr(node, "pipes", [])
    if not pipes:
        return None

    pos = node.scenePos()
    # Unit vectors pointing outward from *node* along each pipe
    vectors: list[tuple[float, float]] = []
    for pipe in pipes:
        if pipe.node1 is node and pipe.node2 is not None:
            other = pipe.node2.scenePos()
        elif pipe.node2 is node and pipe.node1 is not None:
            other = pipe.node1.scenePos()
        else:
            continue
        dx = other.x() - pos.x()
        dy = other.y() - pos.y()
        length = math.hypot(dx, dy)
        if length > 1e-6:
            vectors.append((dx / length, dy / length))

    if not vectors:
        return None

    if len(vectors) == 1:
        return math.atan2(vectors[0][1], vectors[0][0])

    if len(vectors) == 2:
        # Average, flipping second if opposing
        ref = vectors[0]
        vx, vy = vectors[1]
        if ref[0] * vx + ref[1] * vy < 0:
            vx, vy = -vx, -vy
        return math.atan2(ref[1] + vy, ref[0] + vx)

    # 3+ pipes — pick the two most co-linear (dot product closest to −1)
    best_dot = 2.0
    best_pair = (0, 1)
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            d = vectors[i][0] * vectors[j][0] + vectors[i][1] * vectors[j][1]
            if d < best_dot:
                best_dot = d
                best_pair = (i, j)
    a, b = best_pair
    ref = vectors[a]
    vx, vy = vectors[b]
    if ref[0] * vx + ref[1] * vy < 0:
        vx, vy = -vx, -vy
    return math.atan2(ref[1] + vy, ref[0] + vx)


def _walk_branch(start_node, direction_sign: int, branch_angle: float,
                 angle_tol: float = math.radians(30)):
    """Walk along a branch from *start_node* in one direction.

    Parameters
    ----------
    direction_sign : +1 or −1 relative to *branch_angle*
    angle_tol      : maximum angular deviation to keep following a pipe

    Returns list of ``(sprinkler_node, cumulative_distance)`` found.
    Only follows pipes whose angle is within *angle_tol* of the target
    direction and only passes through nodes with exactly 2 pipes
    (mid-run nodes).  Stops at the first sprinkler, at a junction,
    or when no aligned pipe is found.
    """
    results: list[tuple] = []
    current = start_node
    visited = {id(start_node)}
    cumulative = 0.0
    target = branch_angle if direction_sign > 0 else branch_angle + math.pi

    while True:
        best_pipe = None
        best_node = None
        best_diff = angle_tol  # only accept pipes within tolerance

        for pipe in current.pipes:
            other = pipe.node2 if pipe.node1 is current else pipe.node1
            if other is None or id(other) in visited:
                continue
            pos_c = current.scenePos()
            pos_o = other.scenePos()
            dx = pos_o.x() - pos_c.x()
            dy = pos_o.y() - pos_c.y()
            pipe_angle = math.atan2(dy, dx)
            diff = abs(math.atan2(math.sin(pipe_angle - target),
                                  math.cos(pipe_angle - target)))
            if diff < best_diff:
                best_diff = diff
                best_pipe = pipe
                best_node = other

        if best_pipe is None or best_node is None:
            break

        visited.add(id(best_node))
        cumulative += best_pipe.length

        if best_node.has_sprinkler():
            results.append((best_node, cumulative))
            break  # found nearest sprinkler in this direction

        # Only continue through pass-through nodes (exactly 2 pipes)
        if len(best_node.pipes) != 2:
            break
        current = best_node

    return results


def _same_branch_nodes(start_node, branch_angle: float,
                       angle_tol: float = math.radians(30)) -> set:
    """Return the set of node *id*s reachable along the branch from *start_node*.

    Walks in both directions, following pipes aligned with *branch_angle*,
    passing through nodes with exactly 2 pipes.  Stops at junctions or
    angle deviations.  Used to exclude same-branch sprinklers from the
    L (between-branch) calculation.
    """
    result = {id(start_node)}
    for sign in (+1, -1):
        current = start_node
        target = branch_angle if sign > 0 else branch_angle + math.pi
        while True:
            best_node = None
            best_diff = angle_tol

            for pipe in current.pipes:
                other = pipe.node2 if pipe.node1 is current else pipe.node1
                if other is None or id(other) in result:
                    continue
                pos_c = current.scenePos()
                pos_o = other.scenePos()
                dx = pos_o.x() - pos_c.x()
                dy = pos_o.y() - pos_c.y()
                pipe_angle = math.atan2(dy, dx)
                diff = abs(math.atan2(math.sin(pipe_angle - target),
                                      math.cos(pipe_angle - target)))
                if diff < best_diff:
                    best_diff = diff
                    best_node = other

            if best_node is None:
                break
            result.add(id(best_node))
            if len(best_node.pipes) != 2:
                break
            current = best_node
    return result


# ── Per-sprinkler S × L computation ─────────────────────────────────


def _compute_s_l(sprinkler, all_sprinklers, walls, ppm: float):
    """Compute S and L for one sprinkler, in **scene units**.

    Parameters
    ----------
    sprinkler      : Sprinkler object
    all_sprinklers : iterable of all Sprinkler objects on the same level
    walls          : list of WallSegment objects on the same level
    ppm            : pixels_per_mm from scale_manager

    Returns (S_scene, L_scene).
    """
    node = sprinkler.node
    if node is None:
        return (0.0, 0.0)

    pos = node.scenePos()
    px, py = pos.x(), pos.y()

    branch_angle = _branch_direction(node)
    if branch_angle is None:
        return (0.0, 0.0)

    cos_b = math.cos(branch_angle)
    sin_b = math.sin(branch_angle)

    # ── S (along-branch spacing) ──────────────────────────────────
    fwd = _walk_branch(node, +1, branch_angle)
    bwd = _walk_branch(node, -1, branch_angle)

    s_from_sprinklers = 0.0
    if fwd and bwd:
        s_from_sprinklers = max(fwd[0][1], bwd[0][1])
    elif fwd:
        s_from_sprinklers = fwd[0][1] * 2.0
    elif bwd:
        s_from_sprinklers = bwd[0][1] * 2.0

    # Nearest wall perpendicular to branch (wall normal aligns with branch)
    s_from_wall = float("inf")
    for wall in walls:
        wnx, wny = wall.normal()
        dot = abs(wnx * cos_b + wny * sin_b)
        if dot > math.cos(math.radians(45)):
            d = _point_to_segment_dist(px, py,
                                       wall.pt1.x(), wall.pt1.y(),
                                       wall.pt2.x(), wall.pt2.y())
            if d < s_from_wall:
                s_from_wall = d

    s_wall = 2.0 * s_from_wall if s_from_wall != float("inf") else 0.0
    S = max(s_from_sprinklers, s_wall)

    # ── L (between-branch spacing) ────────────────────────────────
    # Perpendicular unit vector
    perp_x, perp_y = -sin_b, cos_b

    same_branch = _same_branch_nodes(node, branch_angle)

    l_from_sprinklers = float("inf")
    for other_spr in all_sprinklers:
        if other_spr is sprinkler:
            continue
        if other_spr.node is None:
            continue
        if id(other_spr.node) in same_branch:
            continue
        opos = other_spr.node.scenePos()
        dx = opos.x() - px
        dy = opos.y() - py
        perp_dist = abs(dx * perp_x + dy * perp_y)
        if perp_dist < l_from_sprinklers:
            l_from_sprinklers = perp_dist

    l_spr = l_from_sprinklers if l_from_sprinklers != float("inf") else 0.0

    # Nearest wall parallel to branch (wall normal perpendicular to branch)
    l_from_wall = float("inf")
    for wall in walls:
        wnx, wny = wall.normal()
        dot = abs(wnx * cos_b + wny * sin_b)
        if dot < math.cos(math.radians(45)):
            d = _point_to_segment_dist(px, py,
                                       wall.pt1.x(), wall.pt1.y(),
                                       wall.pt2.x(), wall.pt2.y())
            if d < l_from_wall:
                l_from_wall = d

    l_wall = 2.0 * l_from_wall if l_from_wall != float("inf") else 0.0
    L = max(l_spr, l_wall)

    return (S, L)


# ── Drawn-tile geometry (tessellating, wall-clipped) ─────────────────


def _listed_coverage_sqft(sprinkler) -> float:
    """Listed coverage area (ft²) from the sprinkler spec, default 130."""
    try:
        return float(
            sprinkler._properties.get("Coverage Area", {}).get("value", 130))
    except (ValueError, TypeError):
        return 130.0


def _tile_extents(sprinkler, all_sprinklers, walls, ppm: float):
    """Per-side drawn-tile extents for one sprinkler, in scene units.

    Rule per side (2026-07-11 grill): the nearer of half the distance to
    the nearest neighbour on that side and the full distance to the
    nearest facing wall on that side; √(listed coverage)/2 when neither
    exists.  Tiles therefore tessellate — no overlap, no wall overshoot.

    This is the DRAWING geometry only.  The calc value As keeps the NFPA
    13 measurement convention (see ``DesignArea._update_shape``).

    Returns:
        ``((fwd, back, left, right), branch_angle)`` where fwd/back are
        along the branch and left/right along the +/− perpendicular.
        For a sprinkler with no branch direction, all four extents are
        the coverage fallback and the angle is 0.0.
    """
    fallback = math.sqrt(_listed_coverage_sqft(sprinkler) * SQFT_TO_MM2) / 2.0 * ppm

    node = sprinkler.node
    if node is None:
        return ((fallback,) * 4, 0.0)

    branch_angle = _branch_direction(node)
    if branch_angle is None:
        return ((fallback,) * 4, 0.0)

    pos = node.scenePos()
    px, py = pos.x(), pos.y()
    cos_b, sin_b = math.cos(branch_angle), math.sin(branch_angle)
    perp_x, perp_y = -sin_b, cos_b

    # Neighbour half-gaps along the branch (walk stops at first sprinkler)
    fwd_walk = _walk_branch(node, +1, branch_angle)
    bwd_walk = _walk_branch(node, -1, branch_angle)
    half_fwd = fwd_walk[0][1] / 2.0 if fwd_walk else None
    half_bwd = bwd_walk[0][1] / 2.0 if bwd_walk else None

    # Cross-branch neighbour half-gaps per perpendicular side
    same_branch = _same_branch_nodes(node, branch_angle)
    half_left: float | None = None
    half_right: float | None = None
    for other in all_sprinklers:
        if other is sprinkler or other.node is None:
            continue
        if id(other.node) in same_branch:
            continue
        opos = other.node.scenePos()
        proj = ((opos.x() - px) * perp_x + (opos.y() - py) * perp_y)
        if proj > 1e-6:
            half = proj / 2.0
            if half_left is None or half < half_left:
                half_left = half
        elif proj < -1e-6:
            half = -proj / 2.0
            if half_right is None or half < half_right:
                half_right = half

    def _side(neigh_half, dir_x, dir_y):
        wall_d = _wall_distance_on_side(px, py, dir_x, dir_y, walls)
        candidates = [c for c in (neigh_half, wall_d) if c is not None]
        return min(candidates) if candidates else fallback

    return ((_side(half_fwd, cos_b, sin_b),
             _side(half_bwd, -cos_b, -sin_b),
             _side(half_left, perp_x, perp_y),
             _side(half_right, -perp_x, -perp_y)),
            branch_angle)


# Minimum sprinkler-to-wall-line distance (mm) below which a wall casts
# no shadow (sprinkler effectively ON the wall — occluder quad degenerates).
_WALL_SHADOW_MIN_DIST_MM = 1.0

# Occluder end extension (mm): seals hairline gaps where joined wall
# centrelines meet within snap tolerance, without materially growing the
# shadow of a genuinely freestanding stub.
_WALL_SHADOW_END_EXT_MM = 10.0


def _clip_tile_at_walls(poly: QPolygonF, walls, spos: QPointF,
                        ppm: float) -> QPolygonF:
    """Remove the parts of the tile occluded by walls (sprinkler line of
    sight).

    Per-side ray extents are flat, so a slanted wall crossing the tile
    leaves corners poking past it whenever the room-polygon clip doesn't
    carry that edge — stale room boundary (room detected before the wall
    was drawn), dead-end partitions, unconnected walls, or no room at
    all (2026-07-13 smoke test).  Each nearby wall segment casts a
    shadow quad from the sprinkler's viewpoint (segment endpoints
    projected away from the sprinkler); subtracting it clips the tile
    exactly at the physical wall while keeping coverage past a wall's
    open end wherever the sprinkler still has line of sight.  Segment
    ends are extended by ``_WALL_SHADOW_END_EXT_MM`` to seal hairline
    junction gaps; the connected piece containing the sprinkler is kept,
    so a shadow that fully severs the tile also discards the far side.
    """
    if poly.isEmpty():
        return poly
    bbox = poly.boundingRect()
    min_dist = _WALL_SHADOW_MIN_DIST_MM * ppm
    reach = 3.0 * math.hypot(bbox.width(), bbox.height())
    sx, sy = spos.x(), spos.y()
    path: QPainterPath | None = None
    for wall in walls:
        p1, p2 = wall.pt1, wall.pt2
        wx, wy = p2.x() - p1.x(), p2.y() - p1.y()
        length = math.hypot(wx, wy)
        if length < 1e-9:
            continue
        # Sprinkler (nearly) on the wall line → no usable shadow
        if abs((sx - p1.x()) * wy - (sy - p1.y()) * wx) / length < min_dist:
            continue
        ext = _WALL_SHADOW_END_EXT_MM * ppm
        seg_bbox = QRectF(p1, p2).normalized()
        if not seg_bbox.adjusted(-ext, -ext, ext, ext).intersects(bbox):
            continue
        ux, uy = wx / length, wy / length
        ax, ay = p1.x() - ux * ext, p1.y() - uy * ext
        bx, by = p2.x() + ux * ext, p2.y() + uy * ext
        da_len = math.hypot(ax - sx, ay - sy)
        db_len = math.hypot(bx - sx, by - sy)
        if da_len < 1e-9 or db_len < 1e-9:
            continue
        shadow = QPainterPath()
        shadow.addPolygon(QPolygonF([
            QPointF(ax, ay),
            QPointF(bx, by),
            QPointF(bx + (bx - sx) / db_len * reach,
                    by + (by - sy) / db_len * reach),
            QPointF(ax + (ax - sx) / da_len * reach,
                    ay + (ay - sy) / da_len * reach)]))
        shadow.closeSubpath()
        if path is None:
            path = QPainterPath()
            path.addPolygon(poly)
            path.closeSubpath()
        path = path.subtracted(shadow)
    if path is None:
        return poly
    best: QPolygonF | None = None
    best_area = -1.0
    for sub in path.simplified().toSubpathPolygons():
        if sub.containsPoint(spos, Qt.FillRule.OddEvenFill):
            return sub
        area = abs(sum(sub[i].x() * sub[(i + 1) % sub.count()].y()
                       - sub[(i + 1) % sub.count()].x() * sub[i].y()
                       for i in range(sub.count()))) / 2.0
        if area > best_area:
            best_area = area
            best = sub
    return best if best is not None else poly


def _inflate_polygon(poly: QPolygonF, d: float) -> QPolygonF:
    """Push each vertex *d* scene units away from the polygon centroid.

    Exactly-touching tiles (shared half-gap edges) otherwise survive
    ``QPainterPath.united`` as interior seams; a tiny inflation makes
    them genuinely overlap so the union merges into one outline.
    """
    n = poly.count()
    if n == 0 or d <= 0:
        return QPolygonF(poly)
    cx = sum(poly[i].x() for i in range(n)) / n
    cy = sum(poly[i].y() for i in range(n)) / n
    out = []
    for i in range(n):
        vx, vy = poly[i].x() - cx, poly[i].y() - cy
        length = math.hypot(vx, vy)
        if length < 1e-9:
            out.append(QPointF(poly[i]))
        else:
            out.append(QPointF(poly[i].x() + vx / length * d,
                               poly[i].y() + vy / length * d))
    return QPolygonF(out)


def _tile_polygon(cx: float, cy: float, angle: float,
                  fwd: float, back: float,
                  left: float, right: float):
    """Rotated tile polygon for one sprinkler.

    Local frame: +X along the branch (fwd/back), +Y along the +perp
    direction (left/right).
    """
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    corners = ((fwd, left), (fwd, -right), (-back, -right), (-back, left))
    pts = []
    for lx, ly in corners:
        pts.append(QPointF(cx + lx * cos_a - ly * sin_a,
                           cy + lx * sin_a + ly * cos_a))
    return QPolygonF(pts)


# ── Default coverage fallback ────────────────────────────────────────


def _fallback_side(sprinkler, ppm: float) -> float:
    """Return a square side length (scene units) derived from Coverage Area."""
    try:
        cov_sqft = float(
            sprinkler._properties.get("Coverage Area", {}).get("value", 130))
    except (ValueError, TypeError):
        cov_sqft = 130.0
    side_mm = math.sqrt(cov_sqft * SQFT_TO_MM2)
    return side_mm * ppm


# =====================================================================


@dataclass
class EffectiveCriteria:
    """Resolved design criteria (room inheritance applied)."""
    hazard: str
    base_area_sqft: float
    density: float
    system_type: str                 # "Wet" | "Dry"
    inherited: bool
    governing_room: str | None
    required_area_sqft: float
    drawn_area_sqft: float
    warnings: list[str] = field(default_factory=list)


class DesignArea(QGraphicsPathItem):
    """Selectable design-area shape that tracks a set of sprinklers.

    Drawn geometry: union of per-sprinkler tessellating tiles
    (``_tile_extents``) — clipped at walls, sharing half-gaps between
    neighbours.  Calc geometry: per-sprinkler ``As = min(NFPA S×L,
    listed Coverage Area)`` accumulated in ``_as_entries`` with
    listing-violation messages in ``spacing_warnings``.
    """

    def __init__(self, sprinklers=None, parent=None):
        super().__init__(parent)
        self._sprinklers: list = list(sprinklers or [])
        self._as_entries: list = []        # (sprinkler, as_sqft, sxl_sqft, listed_sqft)
        self.spacing_warnings: list[str] = []
        self._tile_polys: list = []        # QPolygonF per sprinkler (paint overlay)
        self._hyd_snapshot: dict | None = None
        # Display Manager overrides ("Design Area" category):
        # color = confirmed-outline colour, fill = editing fill/border hue
        self._display_color: str | None = None
        self._display_fill_color: str | None = None
        self._properties: dict = {
            "Hazard Classification": {
                "type": "enum",
                "value": "Ordinary Hazard Group 1",
                "options": HAZARD_OPTIONS,
            },
            "System Name": {"type": "string", "value": "System 1"},
            "Level": {"type": "label", "value": DEFAULT_LEVEL},
            "Area": {"type": "label", "value": "0"},
            "System Type": {"type": "enum", "value": "Wet",
                            "options": ["Wet", "Dry"]},
            # Value stored in ft² (NFPA basis); get_properties converts
            # the displayed value/suffix per project units.
            "Design Area (Base)": {"type": "string", "value": "1500",
                                   "suffix": "sq ft"},
            "Show Badge": {"type": "bool", "value": True},
        }
        self.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(255, 200, 0, 40)))
        self.sync_z_for_mode(editing=False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._creation_level: str = DEFAULT_LEVEL
        self._update_shape()
        self._badge_user_moved: bool = False
        self.badge = DesignAreaBadge(self)
        self._sync_badge()

    @property
    def level(self) -> str:
        """Level of the member sprinklers (read-only, derived).

        A design area is specific to a set of sprinklers — its level is a
        fact about them, not an independent attribute.  The creation-time
        level is only the fallback while the area has no members.
        """
        for s in self._sprinklers:
            if s.node:
                return getattr(s.node, "level", DEFAULT_LEVEL)
        return self._creation_level

    @level.setter
    def level(self, value: str):
        # Fallback for empty areas only — with members, level derives
        # from the sprinklers (creation sites and load paths still assign)
        self._creation_level = value or DEFAULT_LEVEL

    @property
    def drawn_area_sqft(self) -> float:
        """Σ capped As of the member sprinklers (the picked/drawn area)."""
        return sum(a for _s, a, _x, _l in self._as_entries)

    def member_rooms(self) -> tuple[list, int]:
        """Rooms (same level) containing member sprinklers, plus the count
        of member sprinklers inside no room."""
        scene = self.scene()
        rooms: list = []
        roomless = 0
        if scene is None:
            return rooms, 0
        polys = [(r, QPolygonF(r.boundary))
                 for r in getattr(scene, "_rooms", [])
                 if getattr(r, "level", "") == self.level]
        for spr in self._sprinklers:
            node = getattr(spr, "node", None)
            if node is None:
                continue
            pos = node.scenePos()
            hit = next((r for r, poly in polys
                        if poly.containsPoint(pos, Qt.FillRule.OddEvenFill)),
                       None)
            if hit is None:
                roomless += 1
            elif hit not in rooms:
                rooms.append(hit)
        return rooms, roomless

    def effective_criteria(self) -> "EffectiveCriteria":
        """Resolve hazard / design point / system type per the inheritance
        rules (grill 2026-07-14): single room inherits read-only; multi-room
        most-demanding governs (Dry > Wet); storage-class rooms disengage;
        no rooms → the area's own stored values. Inherited values are
        written back so a later disengage keeps the last effective ones."""
        rooms, roomless = self.member_rooms()
        return self._effective_criteria_impl(rooms, roomless)

    def _effective_criteria_impl(self, rooms: list,
                                 roomless: int) -> "EffectiveCriteria":
        """Criteria resolution given a pre-computed member_rooms() result
        (lets badge_rows reuse a single room scan per paint)."""
        warnings: list[str] = []
        no_curve = [r for r in rooms
                    if getattr(r, "_hazard_class", "") not in HAZARD_OPTIONS]

        if rooms and not no_curve:
            def rank(r):
                return (HAZARD_OPTIONS.index(r._hazard_class)
                        if r._hazard_class in HAZARD_OPTIONS else -1)
            top_hazard = max(rooms, key=rank)._hazard_class
            candidates = [r for r in rooms if r._hazard_class == top_hazard]
            gov = max(candidates,
                      key=lambda r: (r.design_point() or (0.0, 0.0))[0])
            base, dens = gov.design_point() or (0.0, 0.0)
            hazard = top_hazard
            system = ("Dry" if any(getattr(r, "_system_type", "Wet") == "Dry"
                                   for r in rooms) else "Wet")
            inherited = True
            gov_name = gov.name or "(unnamed room)"
            if len(rooms) > 1:
                listing = ", ".join(
                    f"{r.name or '(unnamed)'}: "
                    f"{HAZARD_ABBREV.get(r._hazard_class, r._hazard_class)}"
                    for r in rooms)
                warnings.append(
                    f"Design area spans {len(rooms)} rooms ({listing}) — "
                    f"most demanding governs: {hazard}.")
            if roomless:
                warnings.append(
                    f"{roomless} design sprinkler(s) outside any room — "
                    f"room criteria govern.")
            # Write-back: disengaging later keeps the last effective values.
            self._properties["Hazard Classification"]["value"] = hazard
            self._properties["System Type"]["value"] = system
            self._properties["Design Area (Base)"]["value"] = f"{base:.0f}"
        else:
            if no_curve:
                hz = no_curve[0]._hazard_class
                if hz in STORAGE_HAZARDS:
                    warnings.append(
                        f"Room hazard '{hz}' requires storage protection "
                        f"criteria (not yet supported) — set design hazard "
                        f"manually.")
                else:
                    warnings.append(
                        f"Room hazard '{hz}' has no density/area curve — "
                        f"set design hazard manually.")
            hazard = self._properties["Hazard Classification"]["value"]
            system = self._properties["System Type"]["value"]
            try:
                base = float(self._properties["Design Area (Base)"]["value"])
            except (TypeError, ValueError):
                base = 0.0
            dens = interpolate_density(hazard, base) if base > 0 else 0.0
            inherited = False
            gov_name = None

        required = base * (1.3 if system == "Dry" else 1.0)
        drawn = self.drawn_area_sqft
        if required > 0 and drawn < required:
            note = " (+30% dry system)" if system == "Dry" else ""
            warnings.append(
                f"Drawn design area {drawn:.0f} ft² is below the required "
                f"{required:.0f} ft²{note} — enlarge the sprinkler selection.")

        return EffectiveCriteria(hazard, base, dens, system, inherited,
                                 gov_name, required, drawn, warnings)

    def sync_z_for_mode(self, editing: bool):
        """Editing fill sits under geometry; the confirmed outline sits
        above all geometry and gridline bubbles (2026-07-13 smoke test)."""
        self.setZValue(Z_DESIGN_AREA if editing else Z_DESIGN_AREA_CONFIRMED)
        # Badge hides in editing mode; guard covers pre-badge __init__ calls.
        self._sync_badge()

    # ------------------------------------------------------------------
    # Sprinkler management

    @property
    def sprinklers(self) -> list:
        return self._sprinklers

    def add_sprinkler(self, spr):
        if spr not in self._sprinklers:
            self._hyd_snapshot = None
            self._sprinklers.append(spr)
            self._update_shape()

    def remove_sprinkler(self, spr):
        if spr in self._sprinklers:
            self._hyd_snapshot = None
            self._sprinklers.remove(spr)
            self._update_shape()

    def toggle_sprinkler(self, spr):
        if spr in self._sprinklers:
            self.remove_sprinkler(spr)
            return False  # removed
        else:
            self.add_sprinkler(spr)
            return True   # added

    def set_sprinklers(self, sprinklers: list):
        """Replace the full sprinkler set (e.g. from rectangle selection)."""
        self._sprinklers = list(sprinklers)
        self._update_shape()

    # ------------------------------------------------------------------
    # Tile-union shape + per-sprinkler As bookkeeping

    def _update_shape(self):
        """Rebuild the tile-union path and per-sprinkler As bookkeeping.

        Drawing: union of ``_tile_polygon`` tiles (wall-clipped,
        half-gap-shared).  Calc: NFPA S×L per sprinkler via
        ``_compute_s_l`` (unchanged convention), capped at the listed
        coverage area; violations recorded in ``spacing_warnings``.
        Falls back to fixed-margin tiles when not yet on a scene.
        """
        self._as_entries = []
        self.spacing_warnings = []
        self._tile_polys = []
        self._properties["Level"]["value"] = self.level

        valid = [s for s in self._sprinklers if s.node]
        if not valid:
            self.setPath(QPainterPath())
            self._properties["Area"]["value"] = "0"
            return

        # Model space is always 1 px ≈ 1 mm (default), even before formal
        # calibration, so we use pixels_per_mm unconditionally.
        scene = self.scene() if callable(getattr(self, "scene", None)) else None
        sm = getattr(scene, "scale_manager", None) if scene else None
        ppm = sm.pixels_per_mm if sm else 1.0  # default 1 px = 1 mm

        if scene is None:
            # Pre-scene fallback: fixed square margin per sprinkler
            path = QPainterPath()
            for s in valid:
                pos = s.node.scenePos()
                poly = _tile_polygon(pos.x(), pos.y(), 0.0,
                                     300.0, 300.0, 300.0, 300.0)
                sub = QPainterPath()
                sub.addPolygon(poly)
                sub.closeSubpath()
                path = path.united(sub)
            self.setPath(path)
            return

        # Walls, rooms, and sprinklers on the same level
        walls = [w for w in getattr(scene, "_walls", [])
                 if getattr(w, "level", "") == self.level]
        room_polys = []
        for room in getattr(scene, "_rooms", []):
            if getattr(room, "level", "") != self.level:
                continue
            pts = room.boundary
            if len(pts) >= 3:
                room_polys.append(QPolygonF(pts))
        all_sprs = [s for s in getattr(
            getattr(scene, "sprinkler_system", None), "sprinklers", [])
            if s.node and getattr(s.node, "level", "") == self.level]

        from .scale_manager import DisplayUnit
        path = QPainterPath()

        for spr in valid:
            # ── Calc: NFPA S×L measurement convention, capped at listing ──
            S, L = _compute_s_l(spr, all_sprs, walls, ppm)
            if S < 1e-6:
                S = _fallback_side(spr, ppm)
            if L < 1e-6:
                L = _fallback_side(spr, ppm)

            S_mm = S / ppm
            L_mm = L / ppm
            if sm.display_unit == DisplayUnit.IMPERIAL:
                spr._properties["S Spacing"]["value"] = f"{S_mm / 304.8:.1f} ft"
                spr._properties["L Spacing"]["value"] = f"{L_mm / 304.8:.1f} ft"
            elif sm.display_unit == DisplayUnit.METRIC_M:
                spr._properties["S Spacing"]["value"] = f"{S_mm / 1000:.2f} m"
                spr._properties["L Spacing"]["value"] = f"{L_mm / 1000:.2f} m"
            else:
                spr._properties["S Spacing"]["value"] = f"{S_mm:.0f} mm"
                spr._properties["L Spacing"]["value"] = f"{L_mm:.0f} mm"

            sxl_sqft = (S_mm * L_mm) / SQFT_TO_MM2
            listed = _listed_coverage_sqft(spr)
            as_sqft = min(sxl_sqft, listed)
            self._as_entries.append((spr, as_sqft, sxl_sqft, listed))
            if sxl_sqft > listed + 0.5:
                pos = spr.node.scenePos()
                self.spacing_warnings.append(
                    f"Sprinkler at ({pos.x():.0f}, {pos.y():.0f}): computed "
                    f"S×L {sxl_sqft:.0f} ft² exceeds listed coverage "
                    f"{listed:.0f} ft² — spacing violates the listing; "
                    f"using {listed:.0f} ft².")

            # ── Drawing: tessellating wall-clipped tile ───────────────────
            (fwd, back, left, right), angle = _tile_extents(
                spr, all_sprs, walls, ppm)
            pos = spr.node.scenePos()
            poly = _tile_polygon(pos.x(), pos.y(), angle,
                                 fwd, back, left, right)
            # Clip to the containing room polygon — per-side distances
            # can't express slanted boundaries (diagonal walls), so a
            # rectangle corner would poke outside the room.
            for room_poly in room_polys:
                if room_poly.containsPoint(pos, Qt.FillRule.OddEvenFill):
                    clipped = poly.intersected(room_poly)
                    if not clipped.isEmpty():
                        poly = clipped
                    break
            # Cut along the wall segments themselves — the room clip only
            # stops slanted boundaries when the detected room polygon
            # carries that edge (stale rooms / dead-end partitions don't).
            poly = _clip_tile_at_walls(poly, walls, pos, ppm)
            self._tile_polys.append(poly)
            sub = QPainterPath()
            sub.addPolygon(_inflate_polygon(poly, 10.0 * ppm))
            sub.closeSubpath()
            path = path.united(sub)

        self.setPath(path.simplified())

    # ------------------------------------------------------------------
    # Area computation

    def compute_area(self, scale_manager):
        """Recompute the tile shape and the Area property (Σ capped As)."""
        self._update_shape()
        # Re-centre auto-badge now that the shape may have changed.
        self._sync_badge()
        if not scale_manager:
            return

        total_sqft = sum(a for _spr, a, _sxl, _listed in self._as_entries)
        from .scale_manager import DisplayUnit
        if total_sqft > 0:
            if scale_manager.display_unit == DisplayUnit.IMPERIAL:
                self._properties["Area"]["value"] = f"{total_sqft:.0f} sq ft"
            else:
                self._properties["Area"]["value"] = (
                    f"{total_sqft * SQFT_TO_MM2 / 1e6:.1f} m²")
        else:
            self._properties["Area"]["value"] = "0"

    # ------------------------------------------------------------------
    # Property API

    def get_properties(self) -> dict:
        rooms, roomless = self.member_rooms()   # single scan, reused below
        crit = self._effective_criteria_impl(rooms, roomless)
        sm = (getattr(self.scene(), "scale_manager", None)
              if self.scene() else None)
        props: dict = {}
        for k, v in self._properties.items():
            props[k] = dict(v)
        props["Hazard Classification"]["value"] = crit.hazard
        props["System Type"]["value"] = crit.system_type
        # Stored value stays ft² (NFPA basis); metric projects see/edit m²
        # (set_property converts the panel string back to ft²).
        if _is_imperial(sm):
            props["Design Area (Base)"]["value"] = f"{crit.base_area_sqft:.0f}"
            props["Design Area (Base)"]["suffix"] = "sq ft"
        else:
            props["Design Area (Base)"]["value"] = (
                f"{crit.base_area_sqft * SQFT_TO_M2:.1f}")
            props["Design Area (Base)"]["suffix"] = "m²"
        if crit.inherited:
            for k in ("Hazard Classification", "System Type",
                      "Design Area (Base)"):
                props[k]["readonly"] = True
        props["Design Density"] = {
            "type": "label",
            "value": format_density(crit.density, sm) if crit.density else "—"}
        req_note = " (+30% dry)" if crit.system_type == "Dry" else ""
        props["Required Area"] = {
            "type": "label",
            "value": (format_area_sqft(crit.required_area_sqft, sm) + req_note
                      if crit.required_area_sqft else "—")}
        if crit.governing_room:
            props["Criteria From"] = {"type": "label",
                                      "value": crit.governing_room}
        props["Rooms"] = {
            "type": "label",
            "value": (", ".join((r.name or "(unnamed)") for r in rooms)
                      if rooms else "—")}
        if crit.warnings:
            props["⚠ Warnings"] = {"type": "label",
                                    "value": "\n".join(crit.warnings)}
        return props

    def set_property(self, key: str, value):
        if key in ("Hazard Classification", "System Type",
                   "Design Area (Base)") and self.effective_criteria().inherited:
            return  # read-only while room criteria govern
        if key == "Design Area (Base)":
            # Metric panels show/edit m²; convert back so the stored
            # value stays ft² (NFPA basis) — symmetric with get_properties.
            sm = (getattr(self.scene(), "scale_manager", None)
                  if self.scene() else None)
            if not _is_imperial(sm):
                try:
                    value = f"{float(value) / SQFT_TO_M2:.0f}"
                except (TypeError, ValueError):
                    pass
            self._properties[key]["value"] = str(value)
            return
        if key == "Show Badge":
            self._properties["Show Badge"]["value"] = value in (True, "True")
            self._sync_badge()
            return
        if key in self._properties:
            self._properties[key]["value"] = str(value)

    def _sync_badge(self):
        """Visible only when confirmed (not editing) and Show Badge is on.

        Auto-centres on the area centroid until the user drags it."""
        if getattr(self, "badge", None) is None:
            return
        editing = getattr(self.scene(), "mode", None) == "design_area"
        show = bool(self._properties["Show Badge"]["value"])
        self.badge.setVisible(show and not editing and bool(self._sprinklers))
        if not self._badge_user_moved:
            c = self.path().boundingRect().center()
            w, h = badge_fixed_size_mm()
            # Use _syncing flag so itemChange doesn't mark the badge user-moved
            # during an auto-centre setPos, and sceneModified is not emitted.
            self.badge._syncing = True
            try:
                self.badge.setPos(c.x() - w / 2, c.y() - h / 2)
            finally:
                self.badge._syncing = False

    # ── Grip protocol (badge drag — Room-label precedent) ─────────────
    # DesignArea sits at item-pos origin, so parent coords == scene coords.

    def grip_points(self) -> list:
        """Single grip at the badge centre — badge drag, like the room label."""
        if getattr(self, "badge", None) is None or not self.badge.isVisible():
            return []
        w, h = badge_fixed_size_mm()
        return [self.badge.pos() + QPointF(w / 2, h / 2)]

    def apply_grip(self, index: int, pos):
        if index != 0 or getattr(self, "badge", None) is None:
            return
        w, h = badge_fixed_size_mm()
        self.badge.setPos(pos.x() - w / 2, pos.y() - h / 2)

    def badge_offset(self) -> tuple[float, float]:
        """Current badge position in parent (DesignArea item) coordinates."""
        return (self.badge.pos().x(), self.badge.pos().y())

    def set_badge_offset(self, pos):
        """Set badge position explicitly (file load / undo restore).

        Sets _badge_user_moved so _sync_badge auto-centre does not override.
        Uses _syncing flag to suppress sceneModified during load.
        """
        self._badge_user_moved = True
        # Suppress sceneModified during programmatic restore; _badge_user_moved
        # is set explicitly above so no information is lost.
        self.badge._syncing = True
        try:
            self.badge.setPos(pos)
        finally:
            self.badge._syncing = False

    # ------------------------------------------------------------------
    # Hydraulic snapshot

    def set_hydraulic_snapshot(self, snap: dict | None):
        """Store calc results for the badge (None → TBD cells)."""
        self._hyd_snapshot = snap
        self.update()
        if getattr(self, "badge", None) is not None:
            self.badge.update()

    # ------------------------------------------------------------------
    # Badge data assembly

    def badge_rows(self) -> list:
        """DESIGN CRITERIA table content: list of rows, each a list of
        (label, value) cells — 1 cell = full-width row, 2 cells = split."""
        rooms, roomless = self.member_rooms()  # single scan per paint
        crit = self._effective_criteria_impl(rooms, roomless)
        snap = self._hyd_snapshot

        # Occupancy: prefer the governing room's, then first non-empty.
        gov = next((r for r in rooms
                    if (r.name or "(unnamed room)") == crit.governing_room),
                   None)
        occ = getattr(gov, "_occupancy", "") if gov is not None else ""
        if not occ:
            occ = next((getattr(r, "_occupancy", "") for r in rooms
                        if getattr(r, "_occupancy", "")), "")
        abbrev = HAZARD_ABBREV.get(crit.hazard, crit.hazard)
        occ_cell = f"{abbrev} — {occ}" if occ else abbrev

        if crit.system_type == "Dry":
            pipes = getattr(getattr(self.scene(), "sprinkler_system", None),
                            "pipes", [])
            cap = f"{system_capacity_gal(pipes):.0f} gal" if pipes else _TBD
        else:
            cap = "N/A"

        # Dedupe on numeric value ("130" vs "130.0", "5.6" vs "5.60"
        # would otherwise both survive a string-set dedupe).
        raw_ks = [str(s._properties.get("K-Factor", {}).get("value", ""))
                  for s in self._sprinklers
                  if isinstance(getattr(s, "_properties", None), dict)]
        ks = sorted(_dedupe_numeric(v for v in raw_ks if v),
                    key=lambda v: float(v) if _is_float(v) else 0.0)
        raw_covs = [str(s._properties.get("Coverage Area", {}).get("value", ""))
                    for s in self._sprinklers
                    if isinstance(getattr(s, "_properties", None), dict)]
        covs = sorted(_dedupe_numeric(v for v in raw_covs if v),
                      key=lambda v: float(v) if _is_float(v) else 0.0)
        orifices = sorted({K_TO_ORIFICE.get(float(k), "")
                           for k in ks if _is_float(k)} - {""})
        k_cell = "/".join(ks) if ks else _TBD
        if snap and ks:
            k_cell += f" @ {snap['remote_head_psi']:.1f} psi"
        cov_cell = ("/".join(covs) + " ft²") if covs else _TBD

        if snap:
            total = snap["total_demand_gpm"] + snap.get("hose_gpm", 0.0)
            demand = (f"TOTAL DEMAND INCLUDING HOSE OF {total:.0f} usgpm "
                      f"@ {snap['demand_psi']:.1f} psi")
            n_calc = str(snap["sprinklers_calculated"])
        else:
            demand = "TOTAL DEMAND INCLUDING HOSE: TBD (run hydraulic calc)"
            n_calc = _TBD

        name = self._properties["System Name"]["value"]
        return [
            [("DESIGN CRITERIA", "")],
            [("SYSTEM ID", name),
             ("ZONE", crit.system_type.upper())],
            [("OCCUPANCY", occ_cell), ("SYSTEM CAPACITY", cap)],
            [("DENSITY", f"{crit.density:.2f} usgpm/ft²"),
             ("AREA OF APPLICATION", f"{crit.drawn_area_sqft:.0f} ft²")],
            [("COVERAGE PER SPRINKLER", cov_cell), ("STORAGE HEIGHT", "N/A")],
            [("ORIFICE", "/".join(orifices) if orifices else _TBD),
             ('"K" FACTOR', k_cell)],
            [("HOSE ALLOWANCE — INSIDE", _TBD), ("OUTSIDE", _TBD)],
            [("DOMESTIC WATER ALLOWANCE", self._domestic_cell()),
             ("SPRINKLERS CALCULATED", n_calc)],
            [(demand, "")],
            [("", "")],        # blank footer band — mirrors the title row (user tweak, mockup gate)
        ]

    def _domestic_cell(self) -> str:
        ws = getattr(self.scene(), "water_supply_node", None)
        if ws is None:
            return _TBD
        return f"{ws.domestic_allowance_gpm:.0f} usgpm"

    # ------------------------------------------------------------------
    # Paint override — two visual states (2026-07-11 smoke test):
    # editing (scene in design_area mode): yellow fill + faint tile edges;
    # confirmed (any other mode): red dashed outline only.
    # (no shape() override: QGraphicsPathItem's default — the set path —
    # is correct and must not be narrowed; see paint-culling hazard)

    def paint(self, painter, option, widget=None):
        editing = getattr(self.scene(), "mode", None) == "design_area"
        if editing:
            base = QColor(self._display_fill_color or "#ffc800")
            border = QPen(base, 2, Qt.PenStyle.DashLine)
            painter.setPen(border)
            fill = QColor(base)
            fill.setAlpha(40)
            painter.setBrush(QBrush(fill))
            painter.drawPath(self.path())
            if len(self._tile_polys) > 1:
                edge = QColor(base)
                edge.setAlpha(90)
                edge_pen = QPen(edge, 0)
                edge_pen.setCosmetic(True)
                painter.setPen(edge_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for poly in self._tile_polys:
                    painter.drawPolygon(poly)
        else:
            # Confirmed: dashed outline TRACING the selection boundary
            # (L-shapes keep their notch — 2026-07-13 smoke round 3; the
            # bounding-rect box swallowed the notch).  Tiles are inflated
            # ~10mm before union so touching rows merge into one outline.
            # Cosmetic: 2 device px at any zoom — a 2 scene-mm pen is
            # sub-pixel when zoomed to building scale (invisible).
            pen = QPen(QColor(self._display_color or "#dc1e1e"), 2,
                       Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())
        # Suppress default selection rectangle
        option.state &= ~QStyle.StateFlag.State_Selected


# ── Design-criteria badge painter (module-level, used by DesignAreaBadge;
#    kept item-agnostic so paper-space badge items could reuse it later) ───────

_BADGE_ROW_COUNT = 10  # title + 8 content rows + footer band (fixed layout)


def badge_fixed_size_mm() -> tuple[float, float]:
    """Badge size from constants alone — the layout is a fixed 10 rows."""
    h = 2 * (DA_BADGE_TITLE_MM + 2 * DA_BADGE_PAD_MM)
    h += (_BADGE_ROW_COUNT - 2) * (DA_BADGE_TEXT_MM + 2 * DA_BADGE_PAD_MM)
    return DA_BADGE_WIDTH_MM, h


def badge_size_mm(rows) -> tuple[float, float]:
    """Return (width, height) of the badge table in model mm."""
    # first and last rows use the taller title height; all rows between use text height
    title_h = DA_BADGE_TITLE_MM + 2 * DA_BADGE_PAD_MM
    text_h = DA_BADGE_TEXT_MM + 2 * DA_BADGE_PAD_MM
    n = len(rows)
    if n <= 1:
        h = title_h
    else:
        h = title_h + (n - 2) * text_h + title_h
    return DA_BADGE_WIDTH_MM, h


def paint_badge(painter, rows, color):
    """Draw the DESIGN CRITERIA table at (0,0) in model-mm coordinates.

    Filleted outer border, straight inner cell borders, opaque white fill
    (document table — must stay legible over tiles/geometry)."""
    w, h = badge_size_mm(rows)
    pen = QPen(color, DA_BADGE_LINE_MM)
    painter.setPen(pen)
    painter.setBrush(QBrush(QColor("white")))
    painter.drawRoundedRect(QRectF(0, 0, w, h),
                            DA_BADGE_CORNER_MM, DA_BADGE_CORNER_MM)

    font = QFont("Arial")
    y = 0.0
    last = len(rows) - 1
    for i, row in enumerate(rows):
        row_h = (DA_BADGE_TITLE_MM if i == 0 or i == last else DA_BADGE_TEXT_MM) \
            + 2 * DA_BADGE_PAD_MM
        if i > 0:
            painter.drawLine(QPointF(0, y), QPointF(w, y))
        cells = row if isinstance(row, list) else [row]
        cell_w = w / len(cells)
        for j, (label, value) in enumerate(cells):
            x = j * cell_w
            if j > 0:
                painter.drawLine(QPointF(x, y), QPointF(x, y + row_h))
            rect = QRectF(x + DA_BADGE_PAD_MM, y,
                          cell_w - 2 * DA_BADGE_PAD_MM, row_h)
            if i == 0:
                font.setPixelSize(int(DA_BADGE_TITLE_MM))
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
            else:
                font.setPixelSize(int(DA_BADGE_TEXT_MM))
                font.setBold(False)
                painter.setFont(font)
                painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter
                                 | Qt.AlignmentFlag.AlignLeft, label + "  ")
                if value:
                    font.setBold(True)
                    painter.setFont(font)
                    lbl_w = painter.fontMetrics().horizontalAdvance(label + "  ")
                    vrect = rect.adjusted(lbl_w, 0, 0, 0)
                    painter.drawText(vrect, Qt.AlignmentFlag.AlignVCenter
                                     | Qt.AlignmentFlag.AlignLeft, value)
        y += row_h


# ── Draggable on-scene badge ─────────────────────────────────────────────────

class DesignAreaBadge(QGraphicsItem):
    """Draggable DESIGN CRITERIA table, child of a DesignArea.

    Model-space mm sizing (scales with zoom; correct at viewport scale on
    plotted sheets). Rows recompute on every paint — cheap (a handful of
    rooms/sprinklers) and keeps the badge live with room edits.

    The class is defined after DesignArea because it takes a DesignArea
    instance as a constructor argument.  Python resolves ``DesignAreaBadge``
    at call time inside DesignArea.__init__, so forward-reference issues do
    not arise.
    """

    def __init__(self, area: "DesignArea"):
        super().__init__(area)
        self._area = area
        self._syncing: bool = False   # guards itemChange during auto-centre/load
        # No ItemIsMovable: Model_Space never forwards select-mode presses
        # to Qt items, so item-drag is dead scene-wide — the badge moves
        # via the parent DesignArea's grip protocol instead.
        # ItemSendsGeometryChanges stays so itemChange fires on setPos.
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(1)  # above the parent outline

    def boundingRect(self) -> QRectF:
        # badge_rows() always returns _BADGE_ROW_COUNT (10) rows, so width
        # and height are constant — derive from constants alone to avoid
        # a scene traversal inside Qt's hottest geometry callback.
        w, h = badge_fixed_size_mm()
        m = DA_BADGE_LINE_MM
        return QRectF(-m, -m, w + 2 * m, h + 2 * m)

    def paint(self, painter, option, widget=None):
        color = QColor(self._area._display_color or "#ff0000")
        paint_badge(painter, self._area.badge_rows(), color)

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and not self._syncing
                and self.scene() is not None):
            self._area._badge_user_moved = True
            if hasattr(self.scene(), "sceneModified"):
                self.scene().sceneModified.emit()
        return super().itemChange(change, value)
