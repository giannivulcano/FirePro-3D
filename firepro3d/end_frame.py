"""Block Editor end-type frame (LT5 Q12; mockup gate passed 2026-10-07).

No frame box. At the origin (the attach point) an accent crosshair (+-8 px)
and a +X arrow (28 px, cosmetic) say "the line ends here, outward is +X"; a
35 % sample line (18 mm) comes in from -X and stops at the trim point, cut
back through the real end trims (preview == render); one circular X-only
grip at (-trim, 0) sets Trim (>= 0). The record lives on the scene
(``Model_Space.block_capability``); this item only draws and edits it.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem

from .capability_frame import (_HIT_PX, CAPABILITY_FRAME_TAG, FRAME_PEN_PX,
                               PREVIEW_OPACITY, CapabilityFrameItem)
from .constants import END_GLYPH_ARM_PX, END_GLYPH_HALF_PX, END_SAMPLE_MM
from .end_render import FIXED

_TRIM_GRIP = 0
_HEAD_PX, _HEAD_HALF_PX = 6.0, 3.0        # arrowhead on the +X arm (px)


class _AttachGlyph(QGraphicsItem):
    """Screen-constant attach glyph: accent crosshair + +X arrow (mockup gate).

    A child of the frame at the origin that ignores view transforms, so it
    keeps its pixel size at any zoom; not selectable, takes no mouse and is
    tagged as frame chrome (never a snap target).

    Args:
        parent: The owning :class:`EndFrame`.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setData(0, CAPABILITY_FRAME_TAG)     # never a snap target

    def boundingRect(self) -> QRectF:
        """Crosshair + arrow arm in device px, 1 px pad."""
        h = END_GLYPH_HALF_PX + 1.0
        return QRectF(-h, -h, h + END_GLYPH_ARM_PX + 1.0, 2.0 * h)

    def paint(self, painter, option, widget=None):
        """Accent crosshair (+-8 px), then the +X arm and filled head."""
        from . import theme as th
        col = QColor(th.detect().accent_primary)
        pen = QPen(col, FRAME_PEN_PX)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        h, a = END_GLYPH_HALF_PX, END_GLYPH_ARM_PX
        painter.drawLine(QPointF(-h, 0.0), QPointF(h, 0.0))
        painter.drawLine(QPointF(0.0, -h), QPointF(0.0, h))
        painter.drawLine(QPointF(0.0, 0.0), QPointF(a - _HEAD_PX, 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(col)
        painter.drawPolygon(QPolygonF([QPointF(a, 0.0),
                                       QPointF(a - _HEAD_PX, -_HEAD_HALF_PX),
                                       QPointF(a - _HEAD_PX, _HEAD_HALF_PX)]))


class EndFrame(CapabilityFrameItem):
    """The end-type frame of one Block Editor scene.

    Args:
        scene: The Block Editor ``Model_Space`` whose end record this draws.
    """

    KIND = "end"

    def __init__(self, scene):
        super().__init__(scene)
        self._glyph = _AttachGlyph(self)

    def _trim(self) -> float:
        """Trim (mm, >= 0); 0 when unset / malformed (never raises -- runs
        inside Qt virtuals)."""
        c = self._cap()
        try:
            t = float(c.get("trim", 0.0)) if c else 0.0
        except (TypeError, ValueError):
            return 0.0
        return t if t > 0.0 else 0.0

    def _sample_pieces(self) -> tuple:
        """The untrimmed sample: 18 mm + trim, ending on the attach point."""
        from .path_walk import Seg
        return (Seg(-(self._trim() + END_SAMPLE_MM), 0.0, 0.0, 0.0),)

    def _sample_body(self) -> tuple:
        """The drawn sample: cut back by the real end trims at real size
        (k = 1 in the editor for both sizes: 1 authored mm = 1 scene mm)."""
        from . import stroke_style as ss
        from .end_render import end_trims
        from .path_walk import trim_pieces
        pieces = self._sample_pieces()
        d = self.scratch_definition()
        if d is None:
            return pieces
        ends = (ss.NO_ENDS[0], ss.ResolvedEnd(d, None, False))
        s0, s1 = end_trims(ends, fixed_factor=1.0, weight_factor=1.0)
        return trim_pieces(pieces, s0, s1)

    def _rect(self) -> QRectF:
        """The sample line's extent (-(trim + 18 mm) .. 0), 1 mm tall --
        the manipulator box and the bounds base (no drawn frame)."""
        t = self._trim()
        return QRectF(-(t + END_SAMPLE_MM), -0.5, t + END_SAMPLE_MM, 1.0)

    def _ring_rect(self) -> QRectF:
        """No preview ring: the bounds are the sample line's rect."""
        return self._rect()

    def _paint_ring(self, painter, pen, col) -> None:
        """Unused: no ring (``paint`` is overridden)."""

    def _circular_grips(self) -> set:
        """The trim grip draws circular (LT4-style)."""
        return {_TRIM_GRIP}

    def _axis_path(self) -> QPainterPath:
        """The untrimmed sample axis, -(trim + 18 mm) to the attach point."""
        p = QPainterPath()
        p.moveTo(-(self._trim() + END_SAMPLE_MM), 0.0)
        p.lineTo(0.0, 0.0)
        return p

    def shape(self) -> QPainterPath:
        """Pick shape: a screen-constant stroke along the sample line."""
        from .view_scale import scene_hit_width
        s = QPainterPathStroker()
        s.setWidth(scene_hit_width(self, _HIT_PX, 1.0))
        return s.createStroke(self._axis_path())

    def halo_trace_path(self, scene_scale=None) -> QPainterPath:
        """HALO = the sample axis (there is no frame outline)."""
        return self._axis_path()

    def paint(self, painter, option, widget=None):
        """The 35 % sample line only -- no frame box (mockup gate)."""
        if self._cap() is None:
            return
        from . import theme as th
        from .path_walk import to_path
        pen = QPen(QColor(th.detect().text_primary), FRAME_PEN_PX)
        pen.setCosmetic(True)
        body = self._sample_body()
        painter.save()
        try:
            painter.setOpacity(painter.opacity() * PREVIEW_OPACITY)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if body:
                painter.drawPath(to_path(body))
        finally:
            painter.restore()

    def grip_points(self) -> list[QPointF]:
        """[Trim grip] on the axis at (-trim, 0), scene coords."""
        return [QPointF(-self._trim(), 0.0)] if self._cap() else []

    def apply_grip(self, index: int, pos: QPointF) -> None:
        """X-only trim grip; dragging past the origin clamps trim at 0 in the
        capability slot (``set_block_capability`` -> ``_norm_end``, the one
        home of the trim >= 0 rule)."""
        c = self._cap()
        if c is None or index != _TRIM_GRIP:
            return
        c["trim"] = -pos.x()     # clamped at 0 by the slot (_norm_end)
        c.setdefault("size", FIXED)
        self._sc.set_block_capability(("end", c), push_undo=False)
