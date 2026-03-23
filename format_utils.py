"""
format_utils.py
===============
Shared dimension formatting and scale-manager access for all scene items.

Eliminates the duplicated ``_fmt()`` and ``_get_scale_manager()`` methods
that were copy-pasted across pipe.py, node.py, sprinkler.py, wall.py,
room.py, roof.py, floor_slab.py, and wall_opening.py.
"""

from __future__ import annotations


def get_scale_manager(item) -> "ScaleManager | None":
    """Return the ScaleManager from *item*'s scene, or a stored fallback.

    Checks in order:
    1. ``item.scene().scale_manager``
    2. ``item._scene_ref.scale_manager``  (template objects not in a scene)
    3. ``item._scale_manager_ref``        (geometry items with stored ref)
    4. ``item.node.scene().scale_manager`` (sprinklers via parent node)
    """
    # Direct scene access
    sc = item.scene() if callable(getattr(item, "scene", None)) else None
    if sc is not None and hasattr(sc, "scale_manager"):
        return sc.scale_manager

    # Sprinkler → node → scene
    node = getattr(item, "node", None)
    if node is not None:
        nsc = node.scene() if callable(getattr(node, "scene", None)) else None
        if nsc is not None and hasattr(nsc, "scale_manager"):
            return nsc.scale_manager

    # Fallback: stored scene reference (survives _clear_scene resets)
    ref = getattr(item, "_scene_ref", None)
    if ref is not None and hasattr(ref, "scale_manager"):
        return ref.scale_manager

    # Fallback: direct scale_manager reference on geometry items
    sm = getattr(item, "_scale_manager_ref", None)
    if sm is not None:
        return sm

    return None


def fmt_length(item, mm: float) -> str:
    """Format *mm* as a display string using *item*'s scene ScaleManager.

    Falls back to ``'{mm:.1f} mm'`` if no ScaleManager is available.
    """
    sm = get_scale_manager(item)
    return sm.format_length(mm) if sm else f"{mm:.1f} mm"
