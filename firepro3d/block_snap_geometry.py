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
from .block_explode import _TEXT_TYPE, compose_pose, pose_primitive, record_key


def posed_primitives(defn, pose, paths: bool = False):
    """Scene-free 2D items for *defn*'s primitives under *pose*.

    Args:
        defn: The ``BlockDefinition`` (None yields nothing).
        pose: ``(x, y, rotation, mirrored, scale)`` of the placement.
        paths: When True, key every stand-in by its record path and also
            report nested-record origins (the constraint handle table, NB2).

    Returns:
        ``paths=False``: the posed ``geometry_2d`` items (not in any scene),
        nested blocks' primitives included. ``paths=True``: ``(prims,
        origins)`` -- ``prims`` = ``[(path, item), ...]`` and ``origins`` =
        ``[(path, (x, y)), ...]`` for each nested record whose definition
        resolves, where a path is the record's ``uid`` (``"#<index>"`` for a
        legacy record without one), prefixed by each enclosing nested
        record's key joined with ``/``.
    """
    out: list = []
    origins: list = []
    _walk(defn, pose, out, set(), "" if paths else None, origins)
    if not paths:
        return out
    return out, origins


def _join(prefix: str, key: str) -> str:
    return key if not prefix else f"{prefix}/{key}"


def _walk(defn, pose, out: list, active: set, prefix, origins: list) -> None:
    """Append *defn*'s posed primitives to *out*; *active* guards cycles.
    *prefix* None = plain items; a string = ``(path, item)`` pairs."""
    if defn is None or defn.id in active:
        return
    active.add(defn.id)
    try:
        ox, oy = defn.origin
        for i, rec in enumerate(defn.primitives):
            kind = rec.get("type")
            if kind == _NESTED_TYPE:
                child = defn._resolve_nested(rec)
                child_pose = compose_pose(pose, rec, ox, oy)
                sub = None
                if prefix is not None:
                    sub = _join(prefix, record_key(rec, i))
                    if child is not None and child.id not in active:
                        origins.append((sub, (float(child_pose[0]), float(child_pose[1]))))
                _walk(child, child_pose, out, active, sub, origins)
                continue
            if kind == _TEXT_TYPE or is_scaffold(rec):
                continue
            cls = _PRIMITIVE_FACTORY.get(kind)
            if cls is None:
                continue
            item = cls.from_dict(rec)
            pose_primitive(item, pose, ox, oy)
            out.append(item if prefix is None else (_join(prefix, record_key(rec, i)), item))
    finally:
        active.discard(defn.id)
