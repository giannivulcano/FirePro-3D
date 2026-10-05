"""Linetype picker source (linetypes.md LT3-12 / H3-i).

Mirrors the hatch pattern picker (hatch-and-fill.md D-A36 / D-A37,
``hatch_patterns.tile_choices`` / ``ensure_pattern_available``): the panel
Linetype row lists Continuous, By Block, the project's linetype (``repeat``)
blocks, then Linetypes-folder linetypes not yet loaded; picking a folder
linetype loads it into the project before its id is stored. An unresolvable
stored id shows as ``"Missing (<id>)"`` (LT3-10) and is never rewritten by
re-picking that label. UI paths only -- never called from paint.
"""
from __future__ import annotations

from .stroke_style import BY_BLOCK, CONTINUOUS

#: Prefix of the panel label shown for an unresolvable linetype id (LT3-10).
MISSING_PREFIX = "Missing"
_FIXED = (("Continuous", CONTINUOUS), ("By Block", BY_BLOCK))


def _folder_linetypes() -> list[tuple[str, str, str]]:
    """``[(name, block_id, path)]`` -- the ``repeat`` blocks of the Linetypes
    folder (``capability_folder.scan``: folder + two levels, mtime cache)."""
    from .app_data import linetypes_dir
    from .capability_folder import scan
    return scan(linetypes_dir(), "repeat")


def linetype_choices(registry=None, exclude=()) -> list[tuple[str, str]]:
    """``[(label, ref)]`` for the panel Linetype row (LT3-12).

    Continuous, By Block, the project's linetype blocks by name, then the
    Linetypes folder's linetypes not already in the project. Labels are unique
    (a colliding name gets `` (project)`` / `` (library)`` appended, as in
    ``hatch_patterns.tile_choices``), so every ref is reachable by label.

    Args:
        registry: Project block registry, or None (fixed + folder only).
        exclude: Block ids to leave out (``hatch_patterns.picker_exclude``:
            the edited block and anything that would cycle).
    """
    from .hatch_patterns import _unique
    out = list(_FIXED)
    used = {label for label, _ in out}
    if registry is not None:
        project = []
        for bid in registry.ids():
            if bid in exclude:
                continue
            d = registry.get(bid)
            if d is not None and d.repeat:
                project.append((d.name or bid, bid))
        for name, bid in sorted(project, key=lambda x: x[0].lower()):
            out.append((_unique(name, used, "project"), bid))
    for name, bid, _path in _folder_linetypes():
        if bid in exclude or (registry is not None
                              and registry.get(bid) is not None):
            continue
        out.append((_unique(name or bid, used, "library"), bid))
    return out


def missing_label(ref: str) -> str:
    """The panel label for an unresolvable linetype id (LT3-10)."""
    return f"{MISSING_PREFIX} ({ref})"


def is_missing_label(value: str) -> bool:
    """True for a ``"Missing (<id>)"`` label (re-picking it changes nothing)."""
    v = str(value)
    return v.startswith(MISSING_PREFIX + " (") and v.endswith(")")


def linetype_ref_from_value(value: str, registry=None, exclude=()) -> str | None:
    """The ref a picked label stands for, or None for an unknown label."""
    v = str(value)
    return next((r for label, r in linetype_choices(registry, exclude)
                 if label == v), None)


def ensure_linetype_available(ref: str | None, scene) -> bool:
    """Load a Linetypes-folder linetype into the project before its id is
    stored (LT3-12; one undo step via ``blocks_browser.ensure_block_loaded``).

    Continuous / By Block, a linetype already in the project registry, or a
    ref that is no folder linetype need nothing. The load targets the PROJECT
    scene (a Block Editor scene's ``_block_registry_owner``).

    Returns:
        False only when *ref* is a folder linetype that failed to load (the
        caller must not keep it); True otherwise.
    """
    if not ref or ref in (CONTINUOUS, BY_BLOCK) or scene is None:
        return True
    project = getattr(scene, "_block_registry_owner", None) or scene
    reg = getattr(project, "block_registry", None)
    if reg is None or reg.get(ref) is not None:
        return True
    for name, bid, path in _folder_linetypes():
        if bid == ref:
            from .blocks_browser import ensure_block_loaded
            return ensure_block_loaded(project, bid, path, name)
    return True
