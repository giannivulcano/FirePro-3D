"""
block_item.py — BlockItem for FirePro 3D CAD
A named group of geometry items that behaves as a single selectable/moveable unit.
Supports:
  • Anonymous groups (auto-named "Group1", "Group2", …)
  • Named reusable blocks (stored in Model_Space._block_definitions)
  • Nested groups (from_dict recurses through child dicts via item_factory)
  • Full serialization / deserialization
"""

from PyQt6.QtWidgets import QGraphicsItemGroup, QGraphicsItem
from PyQt6.QtCore import QPointF


class BlockItem(QGraphicsItemGroup):
    """A group of geometry items that act as a single selectable unit."""

    def __init__(self, child_items=None, block_name: str = ""):
        super().__init__()
        self._block_name: str = block_name
        self._child_refs: list = list(child_items or [])
        # Make the group itself selectable and moveable; children inherit movement
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.user_layer: str = "0"
        for item in self._child_refs:
            self.addToGroup(item)

    # ── Transform ────────────────────────────────────────────────────────

    def translate(self, dx: float, dy: float):
        """Move the block group by (dx, dy)."""
        self.moveBy(dx, dy)

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def block_name(self) -> str:
        return self._block_name

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "type":       "block_item",
            "block_name": self._block_name,
            "pos":        [self.pos().x(), self.pos().y()],
            "children":   [c.to_dict() for c in self._child_refs
                           if hasattr(c, "to_dict")],
            "user_layer": self.user_layer,
        }

    @classmethod
    def from_dict(cls, data: dict, item_factory) -> "BlockItem":
        """Reconstruct a BlockItem from a dict.  item_factory(d) → item dispatches
        by data["type"], and must handle "block_item" recursively."""
        children = []
        for d in data.get("children", []):
            child = item_factory(d)
            if child is not None:
                children.append(child)
        blk = cls(children, data.get("block_name", ""))
        blk.setPos(QPointF(*data.get("pos", [0.0, 0.0])))
        blk.user_layer = data.get("user_layer", "0")
        return blk
