"""Block Editor linetype repeat frame (linetypes.md LT4-7 / LT4-9, H4-b).

A dashed accent rect from the origin to Length around the X axis; one X-only
end grip changes the trailing gap (LT4-2) and stops at the axis content's end
(LT4-9); the unit repeats one period each side at 35 % through the real
linetype renderer (preview ≡ render, LT4-7).
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF

from .capability_frame import CapabilityFrameItem
from .constants import REPEAT_FRAME_HALF_H_MM

_LEN_GRIP = 0
_MIN_LEN = 0.1            # mm -- the grip can't collapse the frame


class RepeatFrame(CapabilityFrameItem):
    """The linetype unit frame of one Block Editor scene."""

    KIND = "repeat"

    def _length(self) -> float:
        c = self._cap()
        return float(c["length"]) if c else 0.0

    def _rect(self) -> QRectF:
        hh = REPEAT_FRAME_HALF_H_MM
        return QRectF(0.0, -hh, self._length(), 2.0 * hh)

    def _ring_rect(self) -> QRectF:
        """One period each side of the frame (frame = centre cell)."""
        r = self._rect()
        return r.adjusted(-r.width(), 0.0, r.width(), 0.0)

    def _circular_grips(self) -> set:
        return {_LEN_GRIP}

    def _paint_ring(self, painter, pen, col) -> None:
        from .linetype_render import LinetypeDef, draw_expansion, expand
        from .path_walk import Seg
        d = self.scratch_definition()
        lt = LinetypeDef.from_block(d) if d is not None else None
        if lt is None:
            return
        n = self._length()
        pieces = (Seg(-n, 0.0, 0.0, 0.0), Seg(n, 0.0, 2.0 * n, 0.0))
        dash, dot = expand(pieces, lt, 1.0, (0.0, 0.0))
        draw_expansion(painter, dash, dot, pen)

    def grip_points(self) -> list[QPointF]:
        """[Length end grip] on the axis, in scene coords."""
        return [QPointF(self._length(), 0.0)] if self._cap() else []

    def apply_grip(self, index: int, pos: QPointF) -> None:
        """X-only Length grip: trailing gap only, clamped at the content end."""
        c = self._cap()
        if c is None or index != _LEN_GRIP:
            return
        from .linetype_pattern import content_end
        editor = getattr(self._sc, "_tile_editor", None)
        prims = [it.to_dict() for it in editor.gather_primitives()
                 if hasattr(it, "to_dict")] if editor is not None else []
        c["length"] = max(pos.x(), content_end(prims), _MIN_LEN)
        self._sc.set_block_capability(("repeat", c), push_undo=False)
