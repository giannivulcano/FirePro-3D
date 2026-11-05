"""Block stacking: Layer Height and the block band's z (block stacking D4-D7).

Stacking applies in ``block_editor`` scenes only; plan stacking stays
elevation-based (``level_manager``).
"""
from __future__ import annotations

from .constants import (LAYER_HEIGHT_MAX, LAYER_HEIGHT_MIN, Z_BLOCK_STACK,
                        Z_BLOCK_STACK_STEP)


def clamp_layer_height(raw) -> int:
    """A record's or a row's Layer Height as a whole number in range.

    Args:
        raw: Any value; a hand-edited record may hold anything.

    Returns:
        The clamped height, 0 when *raw* is not a finite number.
    """
    try:
        v = int(float(raw))
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(LAYER_HEIGHT_MIN, min(LAYER_HEIGHT_MAX, v))


def stack_z(height: int) -> float:
    """Qt z of a block at Layer Height *height*."""
    return Z_BLOCK_STACK + height * Z_BLOCK_STACK_STEP


def restack(scene, blocks: list, to_front: bool) -> None:
    """Bring *blocks* to the front or send them to the back as one undo step
    (D7): one above the scene's highest, or one below its lowest, keeping
    their relative order. Heights clamp at the range's ends.

    Args:
        scene: The stacking scene.
        blocks: The ``BlockInstance`` s to move.
        to_front: True for Bring to Front.
    """
    heights = [b.layer_height for b in scene._block_instances]
    order = {id(b): i for i, b in enumerate(scene._block_instances)}
    ranked = sorted(blocks, key=lambda b: (b.layer_height, order.get(id(b), 0)),
                    reverse=not to_front)
    step = 1 if to_front else -1
    base = max(heights) if to_front else min(heights)
    with scene.deferred_undo_push():
        for n, b in enumerate(ranked, 1):
            b.set_layer_height(base + n * step)
        scene.request_undo_push()
