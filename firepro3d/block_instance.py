"""BlockInstance — a lightweight placed reference to a BlockDefinition.

One QGraphicsObject per placement; no child items. Paints the definition's
SHARED render-ops under this instance's (position, rotation) pose, so N
instances of one block share a single geometry object. See
docs/specs/block-system.md.

The pose is baked into the *geometry* (applied in paint/boundingRect/shape),
NOT into the item's Qt ``transform()``/``pos()`` — those stay identity/origin.
This matches the construction-geometry items (``RectangleItem`` etc.) the
SelectionManipulator was built for, so the block moves in harmony with the
selection frame during a drag (the manipulator's held-transform preview
assumes ``transform()`` carries no pose).
"""

from __future__ import annotations

from typing import Callable, Optional
from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import QPainterPath, QPen, QColor, QTransform
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem

from .block_definition import BlockDefinition

_PLACEHOLDER_MM = 200.0


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
        self._pose_x = 0.0
        self._pose_y = 0.0
        self._pose_rot = 0.0   # Y-up CCW degrees
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        # ItemIsMovable off: native Qt drag is dead in plan view; the
        # SelectionManipulator drives movement via translate().
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

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

    # ── Pose (baked into geometry, not Qt transform) ─────────────────────
    def pose_transform(self) -> QTransform:
        """Local→scene mapping for this instance's (position, rotation)."""
        t = QTransform()
        t.translate(self._pose_x, self._pose_y)
        t.rotate(-self._pose_rot)          # Qt CW+, app Y-up CCW+
        return t

    def set_block_pos(self, x: float, y: float) -> None:
        self.prepareGeometryChange()
        self._pose_x, self._pose_y = float(x), float(y)
        self.update()

    def block_pos(self) -> tuple[float, float]:
        return (self._pose_x, self._pose_y)

    def set_block_rotation(self, deg: float) -> None:
        self.prepareGeometryChange()
        self._pose_rot = float(deg)
        self.update()

    def block_rotation(self) -> float:
        return self._pose_rot

    def translate(self, dx: float, dy: float) -> None:
        """Move by (dx, dy) in scene mm (SelectionManipulator bake contract)."""
        self.prepareGeometryChange()
        self._pose_x += dx
        self._pose_y += dy
        self.update()

    # ── Geometry (pose-baked) ────────────────────────────────────────────
    def _local_path(self) -> QPainterPath:
        ops = self.render_ops()
        combined = QPainterPath()
        if not ops:
            if self.definition() is None:      # orphan placeholder
                h = _PLACEHOLDER_MM / 2.0
                combined.addRect(-h, -h, _PLACEHOLDER_MM, _PLACEHOLDER_MM)
                combined.moveTo(-h, -h)
                combined.lineTo(h, h)
            return combined
        for _pen, path in ops:
            combined.addPath(path)
        return combined

    def _posed_path(self) -> QPainterPath:
        return self.pose_transform().map(self._local_path())

    def boundingRect(self) -> QRectF:
        r = self._posed_path().boundingRect()
        m = 2.0  # pen margin (mm)
        return r.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        return self._posed_path()

    # ── Paint ────────────────────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        pose = self.pose_transform()
        ops = self.render_ops()
        if not ops:
            if self.definition() is None:      # orphan placeholder
                p = QPen(QColor("#c0392b"))
                p.setCosmetic(True)
                painter.setPen(p)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(self._posed_path())
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
            painter.drawPath(pose.map(path))

    def _display_pen_color(self) -> Optional[QColor]:
        """Hook for display-manager 'Blocks' category colour + pre-highlight.

        v1 returns None (use each render-op's authored pen). Full display-manager
        wiring lands with S2/S4.
        """
        return None

    # ── Serialization ────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "type": "block_instance",
            "block_id": self.block_id,
            "pos": [self._pose_x, self._pose_y],
            "rotation": self._pose_rot,
            "level": self.level,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: dict,
                  resolver: Callable[[str], Optional[BlockDefinition]]) -> "BlockInstance":
        inst = cls(block_id=data["block_id"], resolver=resolver,
                   level=data.get("level", "Level 1"))
        pos = data.get("pos", [0.0, 0.0])
        inst._pose_x, inst._pose_y = float(pos[0]), float(pos[1])
        inst._pose_rot = float(data.get("rotation", 0.0))
        inst.attributes = dict(data.get("attributes", {}))
        return inst
