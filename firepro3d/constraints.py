"""
constraints.py
==============
Parametric constraint system for FirePro 3D.

Provides a base ``Constraint`` class and two concrete implementations:

* **ConcentricConstraint** -- forces two circles/arcs to share the same centre.
* **DimensionalConstraint** -- fixes the distance between two grip points on
  two different items.

Each constraint knows how to *solve* itself (adjust geometry so the constraint
is satisfied), *serialise* to / from a plain dict, and report *visual_points*
for on-screen indicators.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import QPointF


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rebuild_item(item) -> None:
    """Rebuild an item's visual geometry after its internal state changed.

    Supports CircleItem (setRect) and ArcItem (_rebuild_path).
    """
    # CircleItem — uses _center / _radius and QGraphicsEllipseItem.setRect()
    if hasattr(item, "_center") and hasattr(item, "_radius") and hasattr(item, "setRect"):
        cx = item._center.x()
        cy = item._center.y()
        r = item._radius
        item.setRect(cx - r, cy - r, 2 * r, 2 * r)
    # ArcItem — uses _rebuild_path()
    elif hasattr(item, "_rebuild_path"):
        item._rebuild_path()


def _distance(a: QPointF, b: QPointF) -> float:
    """Euclidean distance between two points."""
    return math.hypot(b.x() - a.x(), b.y() - a.y())


# ─────────────────────────────────────────────────────────────────────────────
# Base class
# ─────────────────────────────────────────────────────────────────────────────

class Constraint:
    """Base class for all parametric constraints."""

    _next_id: int = 0

    def __init__(self) -> None:
        self.id: int = Constraint._next_id
        Constraint._next_id += 1
        self.enabled: bool = True
        self.satisfied: bool = True

    # -- Interface methods (must be overridden) ----------------------------

    def solve(self, moved_item=None) -> bool:
        """Apply the constraint.  Return ``True`` if satisfied."""
        raise NotImplementedError

    def involves(self, item) -> bool:
        """Return ``True`` if this constraint references *item*."""
        raise NotImplementedError

    def visual_points(self) -> list[tuple[str, QPointF]]:
        """Return ``[(type, position), ...]`` for visual indicators.

        *type* is ``'concentric'`` or ``'dimensional'``.
        """
        return []

    def to_dict(self, item_to_id: dict) -> dict:
        """Serialise to a JSON-friendly dict.

        *item_to_id* maps live item references to persistent integer IDs.
        """
        raise NotImplementedError

    @staticmethod
    def from_dict(data: dict, id_to_item: dict) -> Constraint | None:
        """Factory: deserialise from *data*.

        Returns ``None`` if referenced items cannot be found in *id_to_item*.
        """
        ctype = data.get("constraint_type")
        if ctype == "concentric":
            return ConcentricConstraint.from_dict(data, id_to_item)
        elif ctype == "dimensional":
            return DimensionalConstraint.from_dict(data, id_to_item)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ConcentricConstraint
# ─────────────────────────────────────────────────────────────────────────────

class ConcentricConstraint(Constraint):
    """Two circles / arcs share the same centre point.

    When solved, the *non-moved* item's ``_center`` is set to match the
    *moved* item's ``_center``.  If neither item was the one that moved
    (or *moved_item* is ``None``), ``circle_b`` is moved to ``circle_a``.
    """

    def __init__(self, circle_a, circle_b) -> None:
        super().__init__()
        self.circle_a = circle_a  # CircleItem or ArcItem
        self.circle_b = circle_b  # CircleItem or ArcItem

    # -- solve -------------------------------------------------------------

    def solve(self, moved_item=None) -> bool:
        if not self.enabled:
            return True

        if moved_item is self.circle_a:
            # circle_a moved -> snap circle_b's centre to circle_a
            target = self.circle_a._center
            self.circle_b._center = QPointF(target)
            _rebuild_item(self.circle_b)
        elif moved_item is self.circle_b:
            # circle_b moved -> snap circle_a's centre to circle_b
            target = self.circle_b._center
            self.circle_a._center = QPointF(target)
            _rebuild_item(self.circle_a)
        else:
            # Arbitrary: move circle_b to circle_a
            target = self.circle_a._center
            self.circle_b._center = QPointF(target)
            _rebuild_item(self.circle_b)

        # Check satisfaction (should always be satisfied after solve)
        dist = _distance(self.circle_a._center, self.circle_b._center)
        self.satisfied = dist < 1e-6
        return self.satisfied

    # -- involves ----------------------------------------------------------

    def involves(self, item) -> bool:
        return item is self.circle_a or item is self.circle_b

    # -- visual_points -----------------------------------------------------

    def visual_points(self) -> list[tuple[str, QPointF]]:
        # Show a concentric marker at the shared centre
        center = QPointF(self.circle_a._center)
        return [("concentric", center)]

    # -- serialisation -----------------------------------------------------

    def to_dict(self, item_to_id: dict) -> dict:
        return {
            "constraint_type": "concentric",
            "circle_a": item_to_id[self.circle_a],
            "circle_b": item_to_id[self.circle_b],
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict, id_to_item: dict) -> ConcentricConstraint | None:
        a_id = data.get("circle_a")
        b_id = data.get("circle_b")
        if a_id is None or b_id is None:
            return None
        circle_a = id_to_item.get(a_id)
        circle_b = id_to_item.get(b_id)
        if circle_a is None or circle_b is None:
            return None
        obj = cls(circle_a, circle_b)
        obj.enabled = data.get("enabled", True)
        return obj


# ─────────────────────────────────────────────────────────────────────────────
# DimensionalConstraint
# ─────────────────────────────────────────────────────────────────────────────

class DimensionalConstraint(Constraint):
    """Fixed distance between two grip points on two different items.

    The constraint stores item references and grip indices.  When solved it
    reads the current grip positions via ``item.grip_points()[index]``,
    computes the direction vector from A to B, and places B at exactly
    ``distance`` from A using ``item_b.apply_grip()``.

    If *moved_item* is ``item_b``, the roles are reversed so that A adjusts
    instead.
    """

    def __init__(self, item_a, grip_a: int,
                 item_b, grip_b: int,
                 distance: float) -> None:
        super().__init__()
        self.item_a = item_a
        self.grip_a: int = grip_a
        self.item_b = item_b
        self.grip_b: int = grip_b
        self.distance: float = distance

    # -- solve -------------------------------------------------------------

    def solve(self, moved_item=None) -> bool:
        if not self.enabled:
            return True

        grips_a = self.item_a.grip_points()
        grips_b = self.item_b.grip_points()

        if self.grip_a >= len(grips_a) or self.grip_b >= len(grips_b):
            self.satisfied = False
            return False

        pos_a = grips_a[self.grip_a]
        pos_b = grips_b[self.grip_b]

        current_dist = _distance(pos_a, pos_b)

        # Already satisfied?
        if abs(current_dist - self.distance) < 1e-6:
            self.satisfied = True
            return True

        if moved_item is self.item_b:
            # item_b was moved -- adjust item_a so it is `distance` away
            anchor = pos_b
            mobile_pos = pos_a
            mobile_item = self.item_a
            mobile_grip = self.grip_a
        else:
            # Default: item_a is the anchor, adjust item_b
            anchor = pos_a
            mobile_pos = pos_b
            mobile_item = self.item_b
            mobile_grip = self.grip_b

        # Direction from anchor toward the mobile point
        dx = mobile_pos.x() - anchor.x()
        dy = mobile_pos.y() - anchor.y()
        length = math.hypot(dx, dy)

        if length < 1e-9:
            # Coincident points -- pick an arbitrary direction (+X)
            dx, dy = 1.0, 0.0
            length = 1.0

        # Unit vector
        ux = dx / length
        uy = dy / length

        # New position for the mobile grip
        new_pos = QPointF(
            anchor.x() + ux * self.distance,
            anchor.y() + uy * self.distance,
        )

        mobile_item.apply_grip(mobile_grip, new_pos)

        # Verify
        grips_a = self.item_a.grip_points()
        grips_b = self.item_b.grip_points()
        actual = _distance(grips_a[self.grip_a], grips_b[self.grip_b])
        self.satisfied = abs(actual - self.distance) < 0.5
        return self.satisfied

    # -- involves ----------------------------------------------------------

    def involves(self, item) -> bool:
        return item is self.item_a or item is self.item_b

    # -- visual_points -----------------------------------------------------

    def visual_points(self) -> list[tuple[str, QPointF]]:
        grips_a = self.item_a.grip_points()
        grips_b = self.item_b.grip_points()

        if self.grip_a >= len(grips_a) or self.grip_b >= len(grips_b):
            return []

        pa = grips_a[self.grip_a]
        pb = grips_b[self.grip_b]

        midpoint = QPointF(
            (pa.x() + pb.x()) / 2.0,
            (pa.y() + pb.y()) / 2.0,
        )
        return [("dimensional", midpoint)]

    # -- serialisation -----------------------------------------------------

    def to_dict(self, item_to_id: dict) -> dict:
        return {
            "constraint_type": "dimensional",
            "item_a":   item_to_id[self.item_a],
            "grip_a":   self.grip_a,
            "item_b":   item_to_id[self.item_b],
            "grip_b":   self.grip_b,
            "distance": self.distance,
            "enabled":  self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict, id_to_item: dict) -> DimensionalConstraint | None:
        a_id = data.get("item_a")
        b_id = data.get("item_b")
        if a_id is None or b_id is None:
            return None
        item_a = id_to_item.get(a_id)
        item_b = id_to_item.get(b_id)
        if item_a is None or item_b is None:
            return None
        obj = cls(
            item_a, data["grip_a"],
            item_b, data["grip_b"],
            data["distance"],
        )
        obj.enabled = data.get("enabled", True)
        return obj
