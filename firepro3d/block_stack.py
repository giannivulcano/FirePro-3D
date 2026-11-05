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
