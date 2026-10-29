"""Explode block instances into editable geometry (nested-blocks D9).

Block-Editor-only by contract C1 (Model Space holds no loose geometry).
The full pose ``P = T . R . S . M`` (design DD2) is reproduced on every
exploded item (design DD9); see ``block_pose``.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform

from .block_attributes import hugged_text_record, resolve_fields, resolve_values
from .block_definition import _nested_pose, is_scaffold
from .annotative import model_factor
from .block_pose import is_upright, pose_matrix, valid_scale
from .stroke_style import compose_overrides

_NESTED_TYPE = "block_instance"
_TEXT_TYPE = "text"


def record_key(rec, index: int) -> str:
    """A primitive record's path segment (NB3): its ``uid``, else
    ``"#<index>"`` for a legacy record without one."""
    uid = rec.get("uid")
    return str(uid) if uid else f"#{index}"


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


def instance_pose(inst) -> tuple:
    """``(x, y, rotation, mirrored, scale)`` of a placed instance (an
    annotative block: scale x its plan factor, SB1c)."""
    x, y = inst.block_pos()
    return (x, y, inst.block_rotation(), inst.block_mirrored(),
            inst.block_scale() * model_factor(inst))


def compose_pose(pose, rec, ox, oy) -> tuple:
    """Scene pose of a nested record inside a host at *pose* (design DD9).

    Full matrices, as the compile does (``BlockDefinition._nested_ops``):
    the record pose, then the definition-origin shift, then the host's
    full pose. The position is the composed matrix's translation; rotation,
    mirror and scale come from the closed form below.

    Args:
        pose: The host's ``(x, y, rotation, mirrored, scale)``.
        rec: The nested ``block_instance`` record.
        ox: Host definition origin x.
        oy: Host definition origin y.

    Returns:
        The child's ``(x, y, rotation, mirrored, scale)``.
    """
    hx, hy, hrot, hmir, hs = pose
    t = (_nested_pose(rec) * QTransform.fromTranslate(-ox, -oy)
         * pose_matrix(hx, hy, hrot, hmir, hs))
    # Closed form for the pose parts (exact -- no atan2 / sqrt noise persisted
    # to the record): M . R(a) = R(-a) . M, so a mirrored host negates the
    # child's rotation and toggles its mirror; scales multiply.
    rr = float(rec.get("rotation", 0.0))
    rm = bool(rec.get("mirrored", False))
    rs = valid_scale(rec.get("scale", 1.0))
    if hmir:
        rot, mirrored = hrot - rr, not rm
    else:
        rot, mirrored = hrot + rr, rm
    return (t.dx(), t.dy(), rot, mirrored, hs * rs)


def pose_primitive(item, pose, ox, oy) -> None:
    """Move a definition-local primitive onto a block pose (design DD9).

    ``P = T . R . S . M``: translate by pos - origin, then about the
    insertion point reflect across its vertical when mirrored
    (``manip_reflect`` -- asymmetric end glyphs flip with it), scale
    (``manip_scale_about``) and rotate (``manip_rotate``, Y-up CCW). Text is
    not posed here (``_pose_text``).

    Args:
        item: A non-text 2D primitive (in a scene or scene-free).
        pose: ``(x, y, rotation, mirrored, scale)``.
        ox: Definition origin x.
        oy: Definition origin y.
    """
    px, py, rot, mirrored, s = pose
    pivot = QPointF(px, py)
    if hasattr(item, "translate"):
        item.translate(px - ox, py - oy)
    else:
        item.manip_translate(px - ox, py - oy)
    if mirrored:
        item.manip_reflect(pivot, QPointF(px, py + 1.0))
    if s != 1.0:
        item.manip_scale_about(pivot, s)
    if rot:
        item.manip_rotate(rot, pivot)


def _text_centre(rec) -> QPointF:
    """Definition-local box centre of a text record (the compile's
    ``text_frame`` centre: ``grip_points()[8]`` of the un-posed item)."""
    from .text_item import TextItem
    return TextItem.from_dict(rec).grip_points()[8]


def _scaled_text_record(rec, s: float) -> dict:
    """*rec* with its size fields x *s* (design DD9): cap height, wrap
    width, box height and cell padding; 0 (auto) stays 0; the border weight
    is a line weight and does not scale. Defaults resolve through the one
    record reader so an absent key scales too."""
    from .text_item import TextAnnotationData
    data = TextAnnotationData.from_dict(rec)
    return {**rec, "height_mm": data.height_mm * s,
            "wrap_width_mm": data.wrap_width_mm * s,
            "box_height_mm": data.box_height_mm * s,
            "cell_padding_mm": data.cell_padding_mm * s}


def _pose_text(item, inst, c_def, ox, oy) -> None:
    """Seat an exploded ``TextItem`` on the instance's full pose (design DD9).

    The box centre lands on the pose image of the definition's text box
    centre *c_def*. The reading angle follows the readable rule as rendered
    (``RenderOp.mapped`` + ``BlockInstance._text_path``, design DD6): a
    mirror negates the baseline angle, the instance rotation adds, and the
    text is turned 180 deg when that would read upside down. Un-mirrored
    text keeps the legacy ``angle + rot`` (never turned). The size fields
    were scaled on the record by the caller.

    Args:
        item: The freshly added ``TextItem`` (definition-local position).
        inst: The instance being exploded.
        c_def: Definition-local box centre of the un-scaled text record.
        ox: Definition origin x.
        oy: Definition origin y.
    """
    angle0 = float(item._angle)
    rot = inst.block_rotation()
    if inst.block_mirrored():
        angle = -angle0 + rot
        if not is_upright(angle):
            angle += 180.0
    else:
        angle = angle0 + rot
    target = inst.full_pose_transform().map(QPointF(c_def.x() - ox, c_def.y() - oy))
    c = item.grip_points()[8]
    if angle != angle0:
        item.manip_rotate(angle - angle0, c)
        c = item.grip_points()[8]
    item.manip_translate(target.x() - c.x(), target.y() - c.y())


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


def explode_instances(scene, instances, flatten: bool, uid_map: dict | None = None,
                      *, values: dict | None = None) -> list:
    """Replace each instance by its definition's contents; returns new items.

    Primitives are re-created via ``scene._add_from_dict`` and moved onto the
    instance's full pose (``pose_primitive``, design DD9). Text has no
    reflect / scale hooks: its size fields are scaled
    on the record and ``_pose_text`` seats the readable ``TextItem`` on the
    mapped box centre (design DD6). Nested records become new
    ``BlockInstance``s at the composed full pose (``compose_pose``) -- recursively
    exploded when *flatten*. An instance whose definition is missing, or is
    geom-backed (an imported reference with no authored primitives), is left
    in place. Placement overrides bake onto primitives (WM-11) and compose
    onto nested children per axis (Q7). Dash phase along a reflected arc may
    differ from the instance (design DD10). Does not push undo (the caller
    does).

    Args:
        scene: The Block Editor ``Model_Space``.
        instances: ``BlockInstance`` items to explode.
        flatten: Also explode every nested block, recursively.
        uid_map: When a dict, filled with record path -> new uid for every
            item this call creates (NB5). One map per exploded instance (the
            caller loops); records ``_add_from_dict`` skips (scaffolding) get
            no entry, which is NB5's drop path.
        values: The outermost resolved attribute values, threaded through the
            flatten recursion (A1/A9); ``None`` resolves from *instances*.

    Returns:
        The newly created scene items.
    """
    created: list = []
    for inst in list(instances):
        if not can_explode(inst):
            continue
        d = inst.definition()
        ox, oy = d.origin
        pose = instance_pose(inst)
        s = pose[4]
        if values is None:
            vals = resolve_values(d.effective_attributes(), inst.attributes,
                                  inst.host_values())
        else:
            vals = values
        for i, rec in enumerate(d.primitives):
            key = record_key(rec, i)
            if rec.get("type") == _NESTED_TYPE:
                x, y, *parts = compose_pose(pose, rec, ox, oy)
                kw = dict(zip(("rotation", "mirrored", "scale"), parts))
                child = scene.place_block_instance(
                    rec["block_id"], (x, y),
                    overrides=compose_overrides(inst.overrides,
                                                rec.get("overrides")),
                    **kw)
                child_def = scene.get_block_definition(rec["block_id"])
                if child_def is not None:
                    ckeys = {a["key"] for a in child_def.effective_attributes()}
                    child.set_attributes({k: v for k, v in inst.attributes.items()
                                          if k in ckeys})
                if uid_map is not None:
                    uid_map[key] = child._uid
                if flatten:
                    sub = {} if uid_map is not None else None
                    created.extend(explode_instances(scene, [child], flatten=True,
                                                     uid_map=sub, values=vals))
                    if sub:
                        uid_map.update({f"{key}/{k}": v for k, v in sub.items()})
                    if child.scene() is scene:      # unexplodable (missing) — keep it
                        created.append(child)
                else:
                    created.append(child)
                continue
            if is_scaffold(rec):
                continue   # non-printed reference line: scaffolding (D23)
            is_text = rec.get("type") == _TEXT_TYPE
            keep = False
            if is_text:
                # Bound text explodes to the box it was drawn in: the hugged
                # record (box re-fit round the value, re-anchored), then the
                # value substituted -- the same shape bound_text_ops renders.
                value = resolve_fields(str(rec.get("text", "")), vals)[0]
                rec = dict(hugged_text_record(rec, value))
                rec["text"] = value
                keep = bool(rec.pop("keep_upright", False))
                c_def = _text_centre(rec)
                if s != 1.0:
                    rec = _scaled_text_record(rec, s)
            item = scene._add_from_dict(rec)
            if item is None:
                continue
            if uid_map is not None:
                uid_map[key] = item._uid
            _bake(item, inst.overrides)
            if is_text:
                _pose_text(item, inst, c_def, ox, oy)
                if keep and not inst.block_mirrored() and not is_upright(item._angle):
                    item.manip_rotate(180.0, item.grip_points()[8])
                created.append(item)
                continue
            pose_primitive(item, pose, ox, oy)
            created.append(item)
        scene.remove_block_instance(inst)
    return created
