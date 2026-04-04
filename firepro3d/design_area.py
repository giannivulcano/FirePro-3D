"""
design_area.py
==============
Persistent annotation representing a fire suppression design area.

Stores a set of sprinklers, a hazard classification, and displays
as a bounding rectangle on the scene.  The rectangle is derived from
NFPA 13 per-sprinkler coverage areas (A = S × L), where:
  S = spacing along the branch line
  L = distance between branch lines
with wall-proximity detection to use 2× wall distance when applicable.

Multiple design areas can coexist; the active one is used for
hydraulic calculations.
"""

import math

from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem, QStyle
from PyQt6.QtCore import Qt, QRectF, QPointF
from constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath

HAZARD_OPTIONS = [
    "Light Hazard",
    "Ordinary Hazard Group 1",
    "Ordinary Hazard Group 2",
    "Extra Hazard Group 1",
    "Extra Hazard Group 2",
]

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


# ── Default coverage fallback ────────────────────────────────────────


def _fallback_side(sprinkler, ppm: float) -> float:
    """Return a square side length (scene units) derived from Coverage Area."""
    try:
        cov_sqft = float(
            sprinkler._properties.get("Coverage Area", {}).get("value", 130))
    except (ValueError, TypeError):
        cov_sqft = 130.0
    # 1 sqft = 92 903 mm²  →  side_mm = √(cov_sqft × 92903)
    side_mm = math.sqrt(cov_sqft * 92_903.0)
    return side_mm * ppm


# =====================================================================


class DesignArea(QGraphicsRectItem):
    """Selectable design-area rectangle that tracks a set of sprinklers."""

    def __init__(self, sprinklers=None, parent=None):
        super().__init__(parent)
        self._sprinklers: list = list(sprinklers or [])
        self._properties: dict = {
            "Hazard Classification": {
                "type": "enum",
                "value": "Ordinary Hazard Group 1",
                "options": HAZARD_OPTIONS,
            },
            "System Name": {"type": "string", "value": "System 1"},
            "Area": {"type": "label", "value": "0"},
        }
        self.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(255, 200, 0, 40)))
        self.setZValue(2)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.level: str = DEFAULT_LEVEL
        self.user_layer: str = DEFAULT_USER_LAYER
        self._update_rect()

    # ------------------------------------------------------------------
    # Sprinkler management

    @property
    def sprinklers(self) -> list:
        return self._sprinklers

    def add_sprinkler(self, spr):
        if spr not in self._sprinklers:
            self._sprinklers.append(spr)
            self._update_rect()

    def remove_sprinkler(self, spr):
        if spr in self._sprinklers:
            self._sprinklers.remove(spr)
            self._update_rect()

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
        self._update_rect()

    # ------------------------------------------------------------------
    # Bounding rectangle — NFPA 13 S × L per sprinkler

    def _update_rect(self):
        """Recompute bounding box from per-sprinkler S × L protection areas.

        When scene context (walls, scale) is available, each sprinkler's
        protection rectangle is computed via NFPA 13 S × L logic.  The
        design-area rectangle is the axis-aligned bounding box of the
        union of all rotated per-sprinkler rectangles.

        Falls back to a fixed 300-unit margin when the item has not yet
        been added to a scene.
        """
        if not self._sprinklers:
            self.setRect(QRectF())
            self._properties["Area"]["value"] = "0"
            return

        valid = [s for s in self._sprinklers if s.node]
        if not valid:
            self.setRect(QRectF())
            return

        # Try to obtain scene context
        # Model space is always 1 px ≈ 1 mm (default), even before formal
        # calibration, so we use pixels_per_mm unconditionally.
        scene = self.scene() if callable(getattr(self, "scene", None)) else None
        sm = getattr(scene, "scale_manager", None) if scene else None
        ppm = sm.pixels_per_mm if sm else 1.0  # default 1 px = 1 mm

        if scene is None:
            # Fallback: fixed margin (pre-scene or uncalibrated)
            xs = [s.node.scenePos().x() for s in valid]
            ys = [s.node.scenePos().y() for s in valid]
            margin = 300.0
            self.setRect(QRectF(
                min(xs) - margin, min(ys) - margin,
                max(xs) - min(xs) + 2 * margin,
                max(ys) - min(ys) + 2 * margin,
            ))
            return

        # Gather walls on the same level
        walls = [w for w in getattr(scene, "_walls", [])
                 if getattr(w, "level", "") == self.level]

        # All sprinklers on the same level (for L cross-branch lookup)
        all_sprs = [s for s in getattr(
            getattr(scene, "sprinkler_system", None), "sprinklers", [])
            if s.node and getattr(s.node, "level", "") == self.level]

        all_corners: list[tuple[float, float]] = []

        for spr in valid:
            S, L = _compute_s_l(spr, all_sprs, walls, ppm)

            # Fallback when S or L could not be determined
            if S < 1e-6:
                S = _fallback_side(spr, ppm)
            if L < 1e-6:
                L = _fallback_side(spr, ppm)

            # Store display values on the sprinkler
            from scale_manager import DisplayUnit
            S_mm = S / ppm
            L_mm = L / ppm
            if sm.display_unit == DisplayUnit.IMPERIAL:
                S_ft = S_mm / 304.8
                L_ft = L_mm / 304.8
                spr._properties["S Spacing"]["value"] = f"{S_ft:.1f} ft"
                spr._properties["L Spacing"]["value"] = f"{L_ft:.1f} ft"
            elif sm.display_unit == DisplayUnit.METRIC_M:
                spr._properties["S Spacing"]["value"] = f"{S_mm / 1000:.2f} m"
                spr._properties["L Spacing"]["value"] = f"{L_mm / 1000:.2f} m"
            else:
                spr._properties["S Spacing"]["value"] = f"{S_mm:.0f} mm"
                spr._properties["L Spacing"]["value"] = f"{L_mm:.0f} mm"

            # Build the 4 corners of the rotated protection rectangle
            pos = spr.node.scenePos()
            cx, cy = pos.x(), pos.y()
            angle = _branch_direction(spr.node) or 0.0
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            hs = S / 2.0   # half-S along branch
            hl = L / 2.0   # half-L perpendicular

            for sx_sign in (-1, +1):
                for sy_sign in (-1, +1):
                    lx = sx_sign * hs
                    ly = sy_sign * hl
                    wx = cx + lx * cos_a - ly * sin_a
                    wy = cy + lx * sin_a + ly * cos_a
                    all_corners.append((wx, wy))

        if not all_corners:
            self.setRect(QRectF())
            return

        min_x = min(c[0] for c in all_corners)
        max_x = max(c[0] for c in all_corners)
        min_y = min(c[1] for c in all_corners)
        max_y = max(c[1] for c in all_corners)
        self.setRect(QRectF(min_x, min_y, max_x - min_x, max_y - min_y))

    # ------------------------------------------------------------------
    # Area computation

    def compute_area(self, scale_manager):
        """Recompute the design-area rect (S × L) and area property."""
        self._update_rect()

        if not scale_manager:
            return
        ppm = scale_manager.pixels_per_mm
        if ppm <= 0:
            ppm = 1.0  # default 1 px = 1 mm

        # Sum individual S × L areas from sprinkler properties
        total_area = 0.0
        unit = None
        for spr in self._sprinklers:
            s_val = spr._properties.get("S Spacing", {}).get("value", "---")
            l_val = spr._properties.get("L Spacing", {}).get("value", "---")
            try:
                s_parts = s_val.split()
                l_parts = l_val.split()
                s_num = float(s_parts[0])
                l_num = float(l_parts[0])
                unit = s_parts[1] if len(s_parts) > 1 else "ft"
                total_area += s_num * l_num
            except (ValueError, IndexError):
                pass

        if total_area > 0 and unit:
            if unit == "ft":
                self._properties["Area"]["value"] = f"{total_area:.0f} sq ft"
            elif unit == "m":
                self._properties["Area"]["value"] = f"{total_area:.1f} m\u00b2"
            elif unit == "mm":
                # Convert mm² to m²
                self._properties["Area"]["value"] = f"{total_area / 1e6:.1f} m\u00b2"
        else:
            # Fallback: bounding-box area
            r = self.rect()
            w_mm = r.width() / ppm
            h_mm = r.height() / ppm
            from scale_manager import DisplayUnit
            if scale_manager.display_unit == DisplayUnit.METRIC_M:
                area = (w_mm / 1000.0) * (h_mm / 1000.0)
                self._properties["Area"]["value"] = f"{area:.1f} m\u00b2"
            else:
                area_sqft = (w_mm / 304.8) * (h_mm / 304.8)
                self._properties["Area"]["value"] = f"{area_sqft:.0f} sq ft"

    # ------------------------------------------------------------------
    # Property API

    def get_properties(self) -> dict:
        return self._properties.copy()

    def set_property(self, key: str, value: str):
        if key in self._properties:
            self._properties[key]["value"] = str(value)

    # ------------------------------------------------------------------
    # Paint override for selection highlight

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # Suppress default selection rectangle
        option.state &= ~QStyle.StateFlag.State_Selected

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.rect())
        return path
