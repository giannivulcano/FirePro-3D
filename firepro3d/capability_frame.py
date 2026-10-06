"""Block Editor capability frames (hatch D-A32 tile, linetypes LT4 repeat).

``CapabilityFrameItem`` is a non-primitive overlay (``data(0) ==
CAPABILITY_FRAME_TAG``): a dashed accent rect with grips and a 35 % repeat
preview ring (preview ≡ render). Selectable and HALO-pickable so the
manipulator shows its grips (U3); a no-op ``manip_translate`` keeps it
anchored at the block origin. Excluded from ``gather_primitives`` (no
tracking list), snap targets (``snap_engine._NON_TARGET_TAGS``) and delete
(``Model_Space.delete_items``); a Block Editor scene never reaches paper.
The state lives on the scene (``Model_Space.block_capability``, in the undo
snapshot); a frame only draws and edits it. Subclasses: ``tile_frame.TileFrame``,
``repeat_frame.RepeatFrame``.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QGraphicsItem

from .constants import Z_BELOW_GEOMETRY

CAPABILITY_FRAME_TAG = "capability_frame"
PREVIEW_OPACITY = 0.35        # repeat-preview opacity (HF2 mockup variant A)
FRAME_DASH = [5, 4]           # dash pattern in pen widths (= px at 1 px cosmetic)
FRAME_PEN_PX = 1.0            # cosmetic frame / preview pen width
_HIT_PX = 8.0                 # frame pick stroke width, screen px


def frame_for(scene, kind: str):
    """The frame item for *kind* (``"tile"`` / ``"repeat"``)."""
    if kind == "repeat":
        from .repeat_frame import RepeatFrame
        return RepeatFrame(scene)
    from .tile_frame import TileFrame
    return TileFrame(scene)


class CapabilityFrameItem(QGraphicsItem):
    """Shared chrome of the Block Editor capability frames.

    Subclasses implement ``KIND``, ``_rect``, ``_ring_rect``, ``_paint_ring``,
    ``grip_points``, ``apply_grip`` and ``_circular_grips``.

    Args:
        scene: The Block Editor ``Model_Space`` whose capability this draws.
    """

    KIND = ""
    #: Anchored at the block origin: a manipulator body move bakes nothing
    #: and pushes no undo step (``SelectionManipulator._bake_move``).
    MANIP_ANCHORED = True

    def __init__(self, scene):
        super().__init__()
        self._sc = scene
        self.setData(0, CAPABILITY_FRAME_TAG)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(Z_BELOW_GEOMETRY + 1)
        self._preview = None            # scratch BlockDefinition, or None

    # ── state ─────────────────────────────────────────────────────────────
    def _cap(self) -> dict | None:
        """This frame's capability dict (a copy), or None."""
        c = self._sc.block_capability
        return dict(c[1]) if c and c[0] == self.KIND else None

    # ── geometry ──────────────────────────────────────────────────────────
    def boundingRect(self) -> QRectF:
        return self._ring_rect().adjusted(-1.0, -1.0, 1.0, 1.0)

    def shape(self) -> QPainterPath:
        from .view_scale import scene_hit_width
        p = QPainterPath()
        p.addRect(self._rect())
        s = QPainterPathStroker()
        s.setWidth(scene_hit_width(self, _HIT_PX, 1.0))
        return s.createStroke(p)

    def halo_trace_path(self, scene_scale=None) -> QPainterPath:
        """HALO = the frame outline only (a click inside picks the content)."""
        p = QPainterPath()
        p.addRect(self._rect())
        return p

    def manip_bounds(self) -> QRectF:
        """The manipulator wraps the frame rect, not the preview ring."""
        return self.mapRectToScene(self._rect())

    def manip_frame_redundant(self) -> bool:
        """The dashed frame rect is already the box -- no second dashed frame."""
        return True

    def prepare_capability_change(self) -> None:
        """Call BEFORE the scene's capability changes: bounds derive from it."""
        self.prepareGeometryChange()

    prepare_tile_change = prepare_capability_change   # HF2 name

    def invalidate_preview(self) -> None:
        """Content or capability changed: rebuild the scratch on next paint."""
        self._preview = None
        self.update()

    def scratch_definition(self):
        """A throwaway definition compiled from the live editor content with
        this frame's capability (the preview ≡ render source)."""
        cap = self._cap()
        if self._preview is None and cap:
            from .block_definition import BlockDefinition
            editor = getattr(self._sc, "_tile_editor", None)
            items = editor.gather_primitives() if editor is not None else []
            prims = [it.to_nested_dict() if hasattr(it, "to_nested_dict")
                     else it.to_dict() for it in items]
            d = BlockDefinition.new(name="preview", library="", series="",
                                    primitives=prims, origin=(0.0, 0.0),
                                    **{self.KIND: cap})
            d._resolve = self._sc.get_block_definition
            self._preview = d
        return self._preview

    # ── paint ─────────────────────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        if self._cap() is None:
            return
        from . import theme as th
        tok = th.detect()
        ring = QPainterPath()
        ring.addRect(self._ring_rect())
        inner = QPainterPath()
        inner.addRect(self._rect())
        col = QColor(tok.text_primary)
        pen = QPen(col, FRAME_PEN_PX)
        pen.setCosmetic(True)
        painter.save()
        painter.setClipPath(ring.subtracted(inner), Qt.ClipOperation.IntersectClip)
        painter.setOpacity(painter.opacity() * PREVIEW_OPACITY)
        self._paint_ring(painter, pen, col)
        painter.restore()
        pen = QPen(QColor(tok.accent_primary), FRAME_PEN_PX)
        pen.setCosmetic(True)
        pen.setDashPattern(FRAME_DASH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._rect())

    # ── manipulator protocol (U3) ─────────────────────────────────────────
    def manip_handles(self):
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular=self._circular_grips())

    def manip_translate(self, dx: float, dy: float) -> None:
        """Parity-only (the manipulator wraps translate-capable items): the
        frame is anchored at the block origin, so a body drag is inert."""

    def manip_capabilities(self) -> set:
        return {"translate"}

    # ── property panel ────────────────────────────────────────────────────
    def get_properties(self) -> dict:
        if self.KIND != "tile":
            return {}
        from .tile_frame import tile_properties
        return tile_properties(self._sc)

    def set_property(self, key, value) -> None:
        if self.KIND != "tile":
            return
        editor = getattr(self._sc, "_tile_editor", None)
        if editor is not None:
            from .tile_frame import set_tile_property
            set_tile_property(self._sc, editor, key, value)
