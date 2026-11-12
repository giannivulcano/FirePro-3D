"""hydraulic_node_badge.py -- a Node's hydraulic badge, drawn by the System
block mapped for the "Hydraulic Node" category (SB4e; system-blocks.md).

Top-level in the tag band (SB4d D5), synced by its node's ``itemChange``.
Not selectable and takes no clicks: HALO resolves a hit on it to the node
(``Model_Space._halo_resolve``), and the node's selection rings it on screen.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPen

from .bound_label import OutlinedLabel
from .constants import HYD_BADGE_OFFSET_MM, HYD_BADGE_STACK_STEP_MM, Z_ANNOT_TAG

BADGE_SIDES = ("Above", "Below", "Left", "Right")
BADGE_POSITION_OPTIONS = ("Auto",) + BADGE_SIDES       # R3: Auto = re-picked each layout
_SIDE_VECTORS = {"Right": (1.0, 0.0), "Left": (-1.0, 0.0),
                 "Above": (0.0, -1.0), "Below": (0.0, 1.0)}

# Preferred order when auto-placing
_AUTO_ORDER = ["Right", "Left", "Above", "Below"]


def best_position_for_node(node) -> str:
    """Choose a badge position that avoids connected pipe directions.

    Examines angles of all pipes connected to *node* and picks the first
    position from Right / Left / Above / Below that is furthest from any
    pipe direction.
    """
    if not node.pipes:
        return "Right"

    # Collect normalised pipe angles from this node (radians, 0 = right)
    angles: list[float] = []
    npos = node.scenePos()
    for pipe in node.pipes:
        other = node.other_end(pipe)
        if other is None:
            continue
        opos = other.scenePos()
        dx = opos.x() - npos.x()
        dy = opos.y() - npos.y()
        if abs(dx) < 0.1 and abs(dy) < 0.1:
            continue
        angles.append(math.atan2(dy, dx))

    if not angles:
        return "Right"

    # Direction angles for each position
    dir_angles = {
        "Right": 0.0,
        "Left":  math.pi,
        "Below": math.pi / 2,    # positive Y is down in scene coords
        "Above": -math.pi / 2,
    }

    best = "Right"
    best_min_dist = -1.0
    for pos in _AUTO_ORDER:
        da = dir_angles[pos]
        # Minimum angular distance to any pipe
        min_dist = min(
            min(abs(da - a), 2 * math.pi - abs(da - a))
            for a in angles
        )
        if min_dist > best_min_dist:
            best_min_dist = min_dist
            best = pos
    return best


def layout_badges(nodes) -> None:
    """Place every badge among *nodes* (R8): badge-bearing nodes group by plan
    XY (rounded mm); a group's side is its highest-elevation node's Badge
    Position (Auto -> ``best_position_for_node`` of that node; the first such
    node wins a tie); members stack in *nodes* order, a row for Above / Below
    and a column for Left / Right (S2: a non-top node's fixed side is kept
    but unused while stacked)."""
    groups: dict[tuple, list] = {}
    for n in nodes:
        if getattr(n, "_hydraulic_badge", None) is None:
            continue
        sp = n.scenePos()
        groups.setdefault((round(sp.x()), round(sp.y())), []).append(n)
    for members in groups.values():
        lead = max(members, key=lambda m: m.z_pos)
        side = (lead.badge_position if lead.badge_position in BADGE_SIDES
                else best_position_for_node(lead))
        for i, n in enumerate(members):
            n._hydraulic_badge.set_layout(side, i, len(members))


class HydraulicNodeBadge(OutlinedLabel):
    """The block mapped for "Hydraulic Node", bound to its node (the host)."""

    def __init__(self, node):
        super().__init__(node, child=False)            # top-level (SB4d D5)
        self._display_overrides: dict = {}             # DM row Visible (R7)
        self._side = "Right"
        self._stack_index = 0
        self._stack_total = 1
        self.setZValue(Z_ANNOT_TAG)

    @property
    def side(self) -> str:
        return self._side

    def set_layout(self, side: str, index: int, total: int) -> None:
        self._side, self._stack_index, self._stack_total = side, index, total
        self.place()

    def place(self) -> None:
        """Anchor = node + side offset + stack shift, authored paper mm x k
        (k follows the drawing scale on the canvas and 1 / S in a paper pass)."""
        k = self._k(None, self.definition())
        vx, vy = _SIDE_VECTORS.get(self._side, _SIDE_VECTORS["Right"])
        shift = (self._stack_index - (self._stack_total - 1) / 2.0) * HYD_BADGE_STACK_STEP_MM * k
        off = QPointF(vx * HYD_BADGE_OFFSET_MM * k, vy * HYD_BADGE_OFFSET_MM * k)
        off += QPointF(shift, 0.0) if self._side in ("Above", "Below") else QPointF(0.0, shift)
        self.set_anchor(self.host.scenePos() + off)

    def refresh(self) -> None:
        super().refresh()
        self.place()                  # k may have moved with the drawing scale / mapping

    def overlay_pens(self) -> list:
        """Screen-only ring while the node is selected (AC5); never plots."""
        from .paper_display import shows_selection    # lazy: paper_display imports this module
        if not shows_selection(self.host):
            return []
        pen = QPen(QColor("cyan"), 2)
        pen.setCosmetic(True)
        return [pen]
