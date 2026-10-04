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

import uuid
from typing import Callable, Optional
from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import QBrush, QPainterPath, QPen, QColor, QTransform
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem

from .block_definition import BlockDefinition
from .render_op import STROKE, FILL, PATTERN, TEXT

_PLACEHOLDER_MM = 200.0


class BlockInstance(QGraphicsObject):
    """A placed instance of a BlockDefinition (flyweight consumer)."""

    def __init__(self, *, block_id: str,
                 resolver: Callable[[str], Optional[BlockDefinition]],
                 level: str = "Level 1", level_offset_mm: float = 0.0):
        super().__init__()
        self.block_id = block_id
        self._resolver = resolver
        # Stable primitive id (parametric-constraint-system.md §6.1).
        self._uid: str = uuid.uuid4().hex
        # Level scope lives on the placed instance (containment C3): the block
        # definition's primitives are level-less; the instance carries a level +
        # Z/elevation offset and is filtered by the active level / view-range
        # exactly like any placed model entity (mirrors wall.z_range_mm).
        self.level = level
        self._level_offset_mm = float(level_offset_mm)
        self._display_overrides: dict = {}   # LevelManager user-hidden guard reads this
        self.attributes: dict = {}
        self._pose_x = 0.0
        self._pose_y = 0.0
        self._pose_rot = 0.0   # Y-up CCW degrees
        self._posed_cache = None   # (ops list, pose, posed path) — see _posed_path
        # Paper-render hooks (linetypes.md LT1-2 / H5): set only during a
        # viewport pass by paper_display._apply_block, None on the model canvas.
        self._paper_pen_width: Optional[float] = None
        self._paper_pen_color: Optional[QColor] = None
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

    def to_nested_dict(self) -> dict:
        """Record for this instance nested inside a definition (no level — C3).

        Returns:
            A D2 ``block_instance`` primitive record (definition-local pose).
        """
        return {"type": "block_instance", "block_id": self.block_id,
                "pos": [self._pose_x, self._pose_y], "rotation": self._pose_rot,
                "uid": self._uid}

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

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rotate by ``angle_deg`` (Y-up CCW+) about scene ``pivot``.

        The block's own rotation pivot is its insertion point, so turning by
        ``a2`` about ``pivot`` after ``a1`` about the insertion point equals
        turning the insertion point about ``pivot`` and rotating by
        ``a1 + a2`` about it. Rotating about the insertion point itself only
        changes the rotation. Not normalised (matches ``set_block_rotation``).
        """
        from .cad_math import CAD_Math
        p = CAD_Math.rotate_point(QPointF(self._pose_x, self._pose_y),
                                  pivot, -angle_deg)
        self.prepareGeometryChange()
        self._pose_x, self._pose_y = p.x(), p.y()
        self._pose_rot += float(angle_deg)
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
        for op in ops:
            combined.addPath(op.path)
        return combined

    def _posed_path(self) -> QPainterPath:
        """Pose-mapped combined path, memoised on (compiled ops, pose).

        boundingRect / shape / paint ask for it several times per frame; the
        key is the definition's compiled op list (a new list on every content
        change, held here so its identity can't be recycled) plus the pose, so
        a stale path can't be served and no explicit invalidation is needed.
        """
        ops = self.render_ops()
        pose = (self._pose_x, self._pose_y, self._pose_rot)
        c = self._posed_cache
        if c is not None and c[0] is ops and c[1] == pose and ops:
            return c[2]
        path = self.pose_transform().map(self._local_path())
        self._posed_cache = (ops, pose, path)
        return path

    def geometric_rect(self) -> QRectF:
        """Pen-free posed geometry bounds (for origin / bbox computations)."""
        return self._posed_path().boundingRect()

    def boundingRect(self) -> QRectF:
        r = self._posed_path().boundingRect()
        m = 2.0  # pen margin (mm)
        return r.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        # Copy (implicitly shared, O(1)): callers may mutate what shape()
        # returns; the memoised path must stay intact.
        return QPainterPath(self._posed_path())

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
        selected = self.isSelected()
        for op in ops:
            if op.kind in (FILL, PATTERN):
                self._paint_fill_op(painter, pose, op)
                continue
            if op.kind == TEXT:
                # Text op: the fill carries the colour, so selection/override
                # tint applies to the BRUSH.
                b = QBrush(QColor(op.colour or "#ffffff"))
                if override is not None:
                    b.setColor(override)
                if selected:
                    b.setColor(QColor("#63BE8B"))  # accent; icon-style-guide token
                if self._paper_pen_color is not None:
                    b.setColor(self._paper_pen_color)   # paper B&W/Custom (LT1-2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(b)
            else:
                # Copy — the compiled op pen is shared by every instance.
                p = QPen(op.pen)
                if self._paper_pen_width is not None:
                    p.setCosmetic(False)          # true mm on paper (LT1-2)
                    p.setWidthF(self._paper_pen_width)
                else:
                    p.setCosmetic(True)           # canvas: authored px (LT1-1)
                if override is not None:
                    p.setColor(override)
                if selected:
                    p.setColor(QColor("#63BE8B"))  # accent; icon-style-guide token
                if self._paper_pen_color is not None:
                    p.setColor(self._paper_pen_color)
                painter.setPen(p)
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(pose.map(op.path))

    def _paint_fill_op(self, painter, pose, op) -> None:
        """Fill / pattern op: boundary posed, pattern stamped in scene axes (D-A11)."""
        from .hatch_render import paint_fill
        col = QColor(op.colour or "#888888")
        col.setAlpha(op.alpha)
        if op.kind == FILL:
            paint_fill(painter, pose.map(op.path), scene=self.scene(),
                       background=col, to_scene=self.sceneTransform())
        else:
            origin = pose.map(op.origin if op.origin is not None else QPointF(0, 0))
            paint_fill(painter, pose.map(op.path), scene=self.scene(),
                       tile_ref=op.tile_ref, colour=col,
                       origin=self.sceneTransform().map(origin), scale=op.scale,
                       to_scene=self.sceneTransform())

    def _display_pen_color(self) -> Optional[QColor]:
        """Hook for display-manager 'Blocks' category colour + pre-highlight.

        v1 returns None (use each render-op's authored pen). Full display-manager
        wiring lands with S2/S4.
        """
        return None

    # ── Level scope (C3 — placed-instance property) ──────────────────────
    def z_range_mm(self) -> tuple[float, float] | None:
        """Elevation of this placed block in absolute mm, as a point ``(e, e)``.

        A block is a flat 2D graphic pinned to its level plane; ``e`` is the
        level elevation plus the instance offset. ``None`` when no LevelManager
        is reachable (mirrors ``wall.z_range_mm``).
        """
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return None
        lvl = lm.get(self.level)
        e = (lvl.elevation if lvl is not None else 0.0) + self._level_offset_mm
        return (e, e)

    def _scale_manager(self):
        sc = self.scene()
        return getattr(sc, "scale_manager", None) if sc else None

    def _fmt(self, mm: float) -> str:
        sm = self._scale_manager()
        return sm.format_length(mm) if sm else f"{mm:.1f}"

    def _parse_dim(self, value) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        sm = self._scale_manager()
        if sm is not None:
            try:
                return sm.parse_dimension(str(value))
            except Exception:
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def get_properties(self) -> dict:
        return {
            "Type":         {"type": "label",     "value": "Block"},
            "Level":        {"type": "level_ref", "value": self.level},
            "Level Offset": {"type": "dimension", "value": self._fmt(self._level_offset_mm),
                             "value_mm": self._level_offset_mm},
            # "string" type → editable numeric line-edit (matches the
            # RegularPolygonItem / EllipseItem Rotation convention).
            "Rotation":     {"type": "string",    "value": f"{self._pose_rot:.1f}"},
        }

    def set_property(self, key: str, value) -> None:
        if key == "Level":
            self.level = str(value)
        elif key == "Level Offset":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._level_offset_mm = parsed
        elif key == "Rotation":
            try:
                self.set_block_rotation(float(value))
            except (TypeError, ValueError):
                pass

    # ── Serialization ────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        d = {
            "type": "block_instance",
            "block_id": self.block_id,
            "pos": [self._pose_x, self._pose_y],
            "rotation": self._pose_rot,
            "level": self.level,
            "attributes": dict(self.attributes),
            "uid": self._uid,
        }
        if self._level_offset_mm != 0.0:
            d["level_offset_mm"] = self._level_offset_mm
        return d

    @classmethod
    def from_dict(cls, data: dict,
                  resolver: Callable[[str], Optional[BlockDefinition]]) -> "BlockInstance":
        inst = cls(block_id=data["block_id"], resolver=resolver,
                   level=data.get("level", "Level 1"),
                   level_offset_mm=data.get("level_offset_mm", 0.0))
        pos = data.get("pos", [0.0, 0.0])
        inst._pose_x, inst._pose_y = float(pos[0]), float(pos[1])
        inst._pose_rot = float(data.get("rotation", 0.0))
        inst.attributes = dict(data.get("attributes", {}))
        if data.get("uid"):
            inst._uid = str(data["uid"])
        return inst
