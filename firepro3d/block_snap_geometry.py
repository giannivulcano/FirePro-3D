"""Posed primitive stand-ins of a placed block (block SNAP / ALIGN parity).

A ``BlockInstance`` paints compiled render ops, so the snap engine's
per-type branches never saw its primitives. ``posed_primitives`` rebuilds
each primitive scene-free from its definition record and moves it onto the
placement's full pose with the Explode pose path
(``block_explode.pose_primitive``), nested blocks recursively
(``block_explode.compose_pose``). The stand-ins are ordinary 2D items in
scene coordinates, so every per-type snap / segment / direction branch
handles them unchanged. Text (snapped by its frame box,
``BlockDefinition.text_snap_points``) and non-printed scaffolding (never
drawn, D23) get no stand-in; a missing or cyclic nested block is skipped.
"""
from __future__ import annotations

from .block_definition import _NESTED_TYPE, _PRIMITIVE_FACTORY, is_scaffold
from .block_explode import compose_pose, pose_primitive

_TEXT_TYPE = "text"


def posed_primitives(defn, pose) -> list:
    """Scene-free 2D items for *defn*'s primitives under *pose*.

    Args:
        defn: The ``BlockDefinition`` (None yields []).
        pose: ``(x, y, rotation, mirrored, scale)`` of the placement.

    Returns:
        Posed ``geometry_2d`` items (not in any scene), nested blocks'
        primitives included.
    """
    out: list = []
    _walk(defn, pose, out, set())
    return out


def _walk(defn, pose, out: list, active: set) -> None:
    """Append *defn*'s posed primitives to *out*; *active* guards cycles."""
    if defn is None or defn.id in active:
        return
    active.add(defn.id)
    try:
        ox, oy = defn.origin
        for rec in defn.primitives:
            kind = rec.get("type")
            if kind == _NESTED_TYPE:
                _walk(defn._resolve_nested(rec),
                      compose_pose(pose, rec, ox, oy), out, active)
                continue
            if kind == _TEXT_TYPE or is_scaffold(rec):
                continue
            cls = _PRIMITIVE_FACTORY.get(kind)
            if cls is None:
                continue
            item = cls.from_dict(rec)
            pose_primitive(item, pose, ox, oy)
            out.append(item)
    finally:
        active.discard(defn.id)
