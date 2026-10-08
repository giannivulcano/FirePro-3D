"""Live-scene end-type authoring (LT5 Q8 / Q12): toggle-on seed, Size /
Trim field edits, the push_undo_state pre-capture lock (Continuous + plain
ends) and the panel preview painter (the real end renderer on a Thin and a
Heavy sample line). Mirrors ``linetype_authoring``."""
from __future__ import annotations

import math

SEED = {"size": "fixed", "trim": 0.0}
SIZE_LABELS = {"fixed": "Fixed", "weight_relative": "Weight-relative"}


def _needs_lock(scene) -> list:
    """Styled primitives that are not Continuous or name an explicit end
    (the shared capability content lock, ``linetype_authoring``)."""
    from .linetype_authoring import locked_items
    return locked_items(scene)


def _force_plain(items) -> None:
    """Continuous + By Linetype ends (= plain on Continuous, Q3)."""
    from .linetype_authoring import lock_strokes
    lock_strokes(items)


def begin_end(scene) -> int:
    """Toggle-on body -- the caller pushes the one step.

    Locks the content (Q8) and sets the end capability (Size Fixed, Trim 0).

    Returns:
        The number of primitives converted.
    """
    bad = _needs_lock(scene)
    _force_plain(bad)
    scene.set_block_capability(("end", dict(SEED)), push_undo=False)
    return len(bad)


def pre_capture(scene) -> None:
    """``push_undo_state`` hook for an end-type editor: the lock joins the
    commit's snapshot; never pushes."""
    if scene.block_end is None:
        return
    _force_plain(_needs_lock(scene))


def set_end_field(scene, key: str, value) -> bool:
    """Size (``"Fixed"`` / ``"Weight-relative"``) or Trim (mm >= 0) edit;
    one undo step.

    Returns:
        False (no step) for a no-op or a refused value, else True.
    """
    cap = scene.block_end
    if cap is None:
        return False
    if key == "Size":
        size = ("weight_relative" if str(value) == SIZE_LABELS["weight_relative"]
                else "fixed")
        if size == cap.get("size"):
            return False
        cap["size"] = size
    elif key == "Trim":
        try:
            mm = float(value)
        except (TypeError, ValueError):
            return False
        if (not math.isfinite(mm) or mm < 0.0
                or abs(mm - float(cap.get("trim", 0.0))) <= 1e-9):
            return False
        cap["trim"] = mm
    else:
        return False
    scene.set_block_capability(("end", cap))
    return True


def preview_painter(scene):
    """Panel swatch painter (Q12): the end on a Thin and a Heavy sample line
    through the real end renderer (preview == render).

    Args:
        scene: The end-type Block Editor ``Model_Space``; its capability
            frame's scratch definition is read at paint time.

    Returns:
        ``paint(painter, rect)``; draws nothing without a readable end.
    """
    def paint(painter, rect):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QPen
        from . import stroke_style as ss
        from . import theme as th
        from .constants import END_PREVIEW_PX_PER_MM
        from .end_render import end_trims, paint_ends
        from .path_walk import Seg, to_path, trim_pieces
        f = scene.capability_frame_item()
        d = f.scratch_definition() if f is not None else None
        if d is None or not d.end:
            return
        ends = (ss.NO_ENDS[0], ss.ResolvedEnd(d, None, False))
        m = 8.0
        x0, x1 = rect.left() + m, rect.right() - m
        ink = QColor(th.detect().ink)
        painter.save()
        try:
            for frac, weight in ((1.0 / 3.0, "Thin"), (2.0 / 3.0, "Heavy")):
                y = rect.top() + rect.height() * frac
                pieces = (Seg(x0, y, x1, y),)
                pen = QPen(ink, ss.canvas_px(weight))
                pen.setCosmetic(True)
                kw = {"fixed_factor": END_PREVIEW_PX_PER_MM,
                      "weight_factor": pen.widthF()}
                s0, s1 = end_trims(ends, **kw)
                body = trim_pieces(pieces, s0, s1)
                if body:
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(to_path(body))
                paint_ends(painter, pieces, ends, pen, **kw)
        finally:
            painter.restore()
    return paint
