"""Explode block instances into editable geometry (nested-blocks D9).

Block-Editor-only by contract C1 (Model Space holds no loose geometry).
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF

from .block_definition import is_scaffold
from .stroke_style import compose_overrides

_NESTED_TYPE = "block_instance"


def can_explode(inst) -> bool:
    """Whether *inst* resolves to a definition with authored primitives.

    A missing definition, or a geom-backed one (an imported reference with
    no authored primitives), cannot be exploded and is left in place.
    """
    d = inst.definition()
    return d is not None and not (not d.primitives and getattr(d, "geoms", None))


def has_nested(instances) -> bool:
    """Whether any instance's definition nests another block.

    Args:
        instances: Placed ``BlockInstance`` items.

    Returns:
        True if at least one resolved definition holds a ``block_instance``
        record.
    """
    for inst in instances:
        d = inst.definition()
        if d is not None and any(p.get("type") == _NESTED_TYPE for p in d.primitives):
            return True
    return False


def _compose(inst, rec, ox, oy):
    """Scene pose of a nested record inside a placed instance.

    Mirrors the compile (``BlockDefinition._nested_ops``): the record's
    definition-local position is shifted by the definition origin, then
    mapped through the instance pose; rotations add (both Y-up CCW).
    """
    t = inst.pose_transform()
    x, y = rec.get("pos", [0.0, 0.0])
    p = t.map(QPointF(float(x) - ox, float(y) - oy))
    return (p.x(), p.y()), inst.block_rotation() + float(rec.get("rotation", 0.0))


def _bake(item, ov) -> None:
    """Bake a placement override onto an exploded primitive (WM-11, Q6)."""
    from . import paper_display as pd
    from .stroke_style import AS_AUTHORED, BY_CATEGORY, normalize_overrides
    st = getattr(item, "style", None)
    if st is None:
        return
    ov = normalize_overrides(ov)
    w, lt = ov["weight"], ov["linetype"]
    if w == BY_CATEGORY:
        st["weight"] = pd.model_blocks_weight()
    elif w != AS_AUTHORED:
        st["weight"] = w
    if lt != AS_AUTHORED:
        st["linetype"] = lt
    sync = getattr(item, "_sync_stroke_pen", None)
    if callable(sync):
        sync()


def explode_instances(scene, instances, flatten: bool) -> list:
    """Replace each instance by its definition's contents; returns new items.

    Primitives are re-created via ``scene._add_from_dict`` and moved onto the
    instance pose (translate by pos - origin, then rotate about pos, Y-up CCW).
    Nested records become new ``BlockInstance``s at the composed pose —
    recursively exploded when *flatten*. An instance whose definition is
    missing, or is geom-backed (an imported reference with no authored
    primitives), is left in place. Placement overrides bake onto primitives
    (WM-11) and compose onto nested children per axis (Q7). Does not push
    undo (the caller does).

    Args:
        scene: The Block Editor ``Model_Space``.
        instances: ``BlockInstance`` items to explode.
        flatten: Also explode every nested block, recursively.

    Returns:
        The newly created scene items.
    """
    created: list = []
    for inst in list(instances):
        if not can_explode(inst):
            continue
        d = inst.definition()
        ox, oy = d.origin
        px, py = inst.block_pos()
        rot = inst.block_rotation()
        pivot = QPointF(px, py)
        for rec in d.primitives:
            if rec.get("type") == _NESTED_TYPE:
                pos, r = _compose(inst, rec, ox, oy)
                child = scene.place_block_instance(
                    rec["block_id"], pos, rotation=r,
                    overrides=compose_overrides(inst.overrides,
                                                rec.get("overrides")))
                if flatten:
                    created.extend(explode_instances(scene, [child], flatten=True))
                    if child.scene() is scene:      # unexplodable (missing) — keep it
                        created.append(child)
                else:
                    created.append(child)
                continue
            if is_scaffold(rec):
                continue   # non-printed reference line: scaffolding (D23)
            item = scene._add_from_dict(rec)
            if item is None:
                continue
            _bake(item, inst.overrides)
            if hasattr(item, "translate"):
                item.translate(px - ox, py - oy)
            else:
                item.manip_translate(px - ox, py - oy)
            if rot:
                item.manip_rotate(rot, pivot)
            created.append(item)
        scene.remove_block_instance(inst)
    return created
