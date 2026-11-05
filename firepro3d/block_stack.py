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
    before = [b.layer_height for b in ranked]
    with scene.deferred_undo_push():
        for n, b in enumerate(ranked, 1):
            b.set_layer_height(base + n * step)
        if [b.layer_height for b in ranked] != before:    # a no-op stays silent
            scene.request_undo_push()


def _scene_mask(block, rect=None):
    """An opaque *block*'s mask in scene mm, read live (the rows cache does not
    invalidate on move); None when its box misses *rect* (when given)."""
    m = block.opaque_mask()
    if block.transform().isIdentity():
        if rect is not None and not m.boundingRect().intersects(rect):
            return None
        return m
    return block.sceneTransform().map(m)             # a manipulator's held preview


def _opaque_rows(scene) -> list:
    """The scene's opaque blocks, bottom first (``BlockInstance._opaque_rows``)."""
    from .block_instance import BlockInstance
    return BlockInstance._opaque_rows(scene)


def cover_over(item) -> "QPainterPath | None":
    """The area of *item* hidden by opaque blocks, scene mm (D4, amended
    2026-11-05), or None.

    Only a schematic hides loose geometry: the gate is the scene's
    ``opaque_blocks`` default, which the Block Editor sets for a schematic and
    ``SchematicSceneManager.scene_for`` sets for its render scene. A plain
    scene costs one attribute read. Loose geometry sits above every block by
    z, so every opaque block covers it; there is no z test.

    Args:
        item: A loose primitive in a scene.

    Returns:
        The union of the masks that touch the item's scene rect; None when the
        scene is not a schematic, nothing overlaps, or *item* has no scene
        (a ghost).
    """
    sc = item.scene()
    if sc is None or not getattr(sc, "opaque_blocks", False):
        return None
    rows = _opaque_rows(sc)
    if not rows:
        return None
    rect = item.sceneBoundingRect()
    masks = []
    for _z, _seq, blk in rows:
        m = _scene_mask(blk, rect)
        if m is not None and m.intersects(rect):
            masks.append(m)
    if not masks:
        return None
    from .block_instance import BlockInstance
    return BlockInstance._union_prefix(sc._opaque_stack[2], masks)


def covered_at(scene, point) -> bool:
    """True when *point* (scene mm) lies inside an opaque block's mask in a
    schematic: a click there picks the block, not the loose geometry under it
    (D8). False for any other scene."""
    if not getattr(scene, "opaque_blocks", False):
        return False
    for _z, _seq, blk in _opaque_rows(scene):
        m = _scene_mask(blk)
        if m.boundingRect().contains(point) and m.contains(point):
            return True
    return False
