"""BlockInstance — a lightweight placed reference to a BlockDefinition.

One QGraphicsObject per placement; no child items. Paints the definition's
SHARED render-ops under this instance's (pos, rotation) transform, so N
instances of one block share a single geometry object. See
docs/specs/block-system.md.
"""

from __future__ import annotations

from typing import Callable, Optional
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPen, QColor
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem

from .block_definition import BlockDefinition


class BlockInstance(QGraphicsObject):
    """A placed instance of a BlockDefinition (flyweight consumer)."""

    def __init__(self, *, block_id: str,
                 resolver: Callable[[str], Optional[BlockDefinition]],
                 level: str = "Level 1"):
        super().__init__()
        self.block_id = block_id
        self._resolver = resolver
        self.level = level
        self.attributes: dict = {}
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

    # ── Definition access ────────────────────────────────────────────────
    def definition(self) -> Optional[BlockDefinition]:
        return self._resolver(self.block_id)

    def render_ops(self):
        d = self.definition()
        return d.render_ops() if d is not None else []

    def on_definition_changed(self) -> None:
        """Called by the definition when its geometry changes: repaint."""
        self.prepareGeometryChange()
        self.update()

    # ── Rotation (app angles are Y-up CCW+, Qt setRotation is CW+) ────────
    def set_block_rotation(self, deg: float) -> None:
        self.setRotation(-float(deg))

    def block_rotation(self) -> float:
        return -self.rotation()

    # ── Geometry ─────────────────────────────────────────────────────────
    def _shared_path(self) -> QPainterPath:
        combined = QPainterPath()
        for _pen, path in self.render_ops():
            combined.addPath(path)
        return combined

    def boundingRect(self) -> QRectF:
        r = self._shared_path().boundingRect()
        m = 2.0  # pen margin (mm)
        return r.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        return self._shared_path()

    # ── Paint ────────────────────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        ops = self.render_ops()
        if not ops:
            return
        override = self._display_pen_color()   # display-manager / pre-highlight hook
        for pen, path in ops:
            p = QPen(pen)
            p.setCosmetic(True)
            if override is not None:
                p.setColor(override)
            if self.isSelected():
                p.setColor(QColor("#63BE8B"))  # accent; see icon-style-guide accent token
            painter.setPen(p)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

    def _display_pen_color(self) -> Optional[QColor]:
        """Hook for display-manager 'Blocks' category colour + pre-highlight.

        v1 returns None (use each render-op's authored pen). Full display-manager
        wiring lands with S2/S4.
        """
        return None

    # ── Serialization ────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "pos": [self.pos().x(), self.pos().y()],
            "rotation": self.block_rotation(),
            "level": self.level,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: dict,
                  resolver: Callable[[str], Optional[BlockDefinition]]) -> "BlockInstance":
        inst = cls(block_id=data["block_id"], resolver=resolver,
                   level=data.get("level", "Level 1"))
        pos = data.get("pos", [0.0, 0.0])
        inst.setPos(pos[0], pos[1])
        inst.set_block_rotation(data.get("rotation", 0.0))
        inst.attributes = dict(data.get("attributes", {}))
        return inst
