"""Promote to System, and its inverses Demote from System / Check out to
Workbench (block-system.md "System library tier", authoring path
2026-10-27 Q5/Q6, Phase 2 D1): copy a saved Workbench block into the shipped
tier (``firepro3d/system_blocks/``) under a frozen id, bumping the version.

Source-checkout only (:func:`block_library.dev_gate`). File to file: the
Workbench ``.fpdb`` -- what Save to library wrote -- is the source.
"""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass

from . import block_library, capability_folder


class PromoteRefused(Exception):
    """Promote cannot run; the message is shown to the user as is."""


@dataclass(frozen=True)
class PromoteResult:
    """What a promote wrote (or, from :func:`plan_promote`, would write)."""
    old_id: str
    new_id: str
    version: int
    shipped_version: int | None
    shipped_path: str
    workbench_path: str
    removed_path: str | None     # the old shipped file a rename replaces


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "block"


def _read(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def plan_promote(block_id: str, root: str | None = None, *,
                 project_def=None, registry=None) -> PromoteResult:
    """Check the rules and work out the target, id and version; writes nothing.

    Args:
        block_id: The Workbench block's id.
        root: User block-library root (None = configured).
        project_def: The project's copy of the block, if loaded -- it must be
            saved (``source_status == "library"``).
        registry: Project ``BlockRegistry`` for ref names in a refusal.

    Returns:
        The :class:`PromoteResult` a :func:`promote` would write.

    Raises:
        PromoteRefused: A rule fails (gate, not Workbench, unsaved, refs,
            target held by another shipped id).
    """
    from .block_registry import referenced_ids
    if not block_library.dev_gate():
        raise PromoteRefused("Promote to System needs a source checkout of FirePro3D.")
    found = block_library._find_by_id(block_id, root)
    if (found is None or found[3]["tier"] != "user"
            or not block_library._under_workbench(found[3]["path"], root)):
        raise PromoteRefused(
            "Only blocks saved in the Workbench library can be promoted.")
    _lib, series, _fname, meta = found
    wb_path, name = meta["path"], meta["name"]
    if (project_def is not None
            and block_library.source_status(project_def, root) != "library"):
        raise PromoteRefused(
            "Save the block to the Workbench library first -- Promote copies "
            "the saved file.")
    loaded = block_library.load_block_file(wb_path)
    if loaded is None:
        raise PromoteRefused(f"Could not read {wb_path}.")
    shipped = block_library.shipped_index()
    missing = sorted(r for r in referenced_ids(loaded) if r not in shipped)
    if missing:
        def _label(r):
            d = registry.get(r) if registry is not None else None
            return d.name if d is not None else r
        raise PromoteRefused(
            "These blocks it uses are not System blocks -- promote them first:\n"
            + "\n".join(f"  {_label(r)}" for r in missing))
    target = os.path.join(block_library.system_root(),
                          capability_folder.sanitize(series),
                          capability_folder.sanitize(name) + ".fpdb")
    target_meta = (capability_folder.read_meta(target)
                   if os.path.isfile(target) else None)
    target_id = target_meta["id"] if target_meta else None
    removed = None
    if block_id in shipped:                        # frozen (Q5)
        new_id = block_id
        if target_id not in (None, block_id):
            raise PromoteRefused(
                f"Promoting would replace {os.path.basename(target)}, which "
                "ships another block -- rename this one first.")
        if not block_library._same_path(shipped[block_id], target):
            removed = shipped[block_id]
    elif target_id:                                 # D1: adopt the shipped id
        holder = block_library._find_by_id(target_id, root)
        if (holder is not None and holder[3]["tier"] == "user"
                and not block_library._same_path(holder[3]["path"], wb_path)):
            raise PromoteRefused(
                f"{os.path.basename(holder[3]['path'])} in the Workbench already "
                f"holds the id of {os.path.basename(target)} -- promote that one.")
        new_id = target_id
    else:
        base = f"system-{_slug(series)}-{_slug(name)}"
        new_id, k = base, 1
        while new_id in shipped:
            k += 1
            new_id = f"{base}-{k}"
    shipped_version = None
    if new_id in shipped:
        sv = (capability_folder.read_meta(shipped[new_id]) or {}).get("version")
        shipped_version = sv if isinstance(sv, int) else None
    if shipped_version is not None:
        version = shipped_version + 1
    else:
        try:
            version = int(meta.get("version") or 1)
        except (TypeError, ValueError):
            raise PromoteRefused(f"{wb_path} has an unreadable version.") from None
    return PromoteResult(block_id, new_id, version, shipped_version, target,
                         wb_path, removed)


def promote(block_id: str, root: str | None = None, *,
            project_def=None, registry=None) -> PromoteResult:
    """:func:`plan_promote`, then write the shipped and Workbench files.

    Args:
        block_id: The Workbench block's id.
        root: User block-library root (None = configured).
        project_def: The project's copy of the block, if loaded.
        registry: Project ``BlockRegistry`` for ref names in a refusal.

    Returns:
        The :class:`PromoteResult`; the caller re-points the open project
        when ``old_id != new_id`` (``Model_Space.retarget_block_refs``).

    Raises:
        PromoteRefused: As :func:`plan_promote`; nothing is written.
    """
    res = plan_promote(block_id, root, project_def=project_def,
                       registry=registry)
    rec = _read(res.workbench_path)
    rec.update(id=res.new_id, version=res.version, base_version=res.version)
    shipped = copy.deepcopy(rec)
    shipped["library"] = block_library.SYSTEM_LIBRARY
    rec["library"] = block_library.WORKBENCH_LIBRARY
    try:
        block_library.write_shipped(res.shipped_path, shipped)
        block_library._atomic_write_json(res.workbench_path, rec)
        if res.removed_path:                 # last: a failure leaves both ids
            block_library.delete_shipped(res.removed_path)
    finally:
        for p in (res.shipped_path, res.workbench_path, res.removed_path):
            if p:
                capability_folder.forget(p)
        block_library._notify_changed()
    return res


@dataclass(frozen=True)
class WorkbenchCopy:
    """What a demote / check out wrote (or, from a ``plan_*``, would write)."""
    block_id: str
    shipped_path: str
    workbench_path: str
    workbench_written: bool        # False = an existing Workbench copy is kept
    app_refs: tuple = ()           # app-code names of the id (demote confirm)
    overwrites: tuple = ()         # (name, id) of the other block at the target


def _app_refs(block_id: str) -> tuple:
    """App-code names that still point at *block_id* after a demote (they fall
    back to none: the renderer draws the tone, D-A36)."""
    from .hatch_patterns import DEFAULT_TILE_REF, LEGACY_ALIAS
    out = []
    if block_id == DEFAULT_TILE_REF:
        out.append("App default hatch (walls / floors / roofs)")
    out += [f"Legacy pattern name '{k}'" for k, v in LEGACY_ALIAS.items()
            if v == block_id]
    return tuple(out)


def _plan_workbench(block_id: str, root: str | None, verb: str) -> WorkbenchCopy:
    """Shared check: gate, shipped id, the Workbench target (frozen id kept)."""
    if not block_library.dev_gate():
        raise PromoteRefused(f"{verb} needs a source checkout of FirePro3D.")
    shipped = block_library.shipped_index()
    if block_id not in shipped:
        raise PromoteRefused(f"Only a System block can use {verb}.")
    spath = shipped[block_id]
    meta = capability_folder.read_meta(spath)
    if meta is None:            # defensive: shipped_index lists readable files only
        raise PromoteRefused(f"Could not read {spath}.")
    found = block_library._find_by_id(block_id, root)
    if (found is not None and found[3]["tier"] == "user"
            and block_library._under_workbench(found[3]["path"], root)):
        return WorkbenchCopy(block_id, spath, found[3]["path"], False)
    rel = os.path.relpath(spath, block_library.system_root()).split(os.sep)
    parts = [capability_folder.sanitize(s) for s in rel[:-1]]
    target = os.path.join(block_library._root(root),
                          block_library.WORKBENCH_LIBRARY, *parts,
                          capability_folder.sanitize(meta["name"]) + ".fpdb")
    over = ()
    if os.path.isfile(target):         # another block: overwritten (confirm warns)
        om = capability_folder.read_meta(target) or {}
        over = (om.get("name") or os.path.basename(target)[:-5],
                om.get("id") or "unreadable")
    return WorkbenchCopy(block_id, spath, target, True, overwrites=over)


def _write_workbench(res: WorkbenchCopy) -> None:
    rec = _read(res.shipped_path)
    rec["library"] = block_library.WORKBENCH_LIBRARY
    block_library._atomic_write_json(res.workbench_path, rec)


def plan_checkout(block_id: str, root: str | None = None) -> WorkbenchCopy:
    """Check out to Workbench: check the rules; writes nothing.

    Raises:
        PromoteRefused: Gate off, not shipped, unreadable, or a Workbench file
            already owns the id. Another block at the target path is not a
            refusal: it is named in ``overwrites`` and replaced.
    """
    res = _plan_workbench(block_id, root, "Check out to Workbench")
    if not res.workbench_written:
        raise PromoteRefused(f"Already checked out: {res.workbench_path}")
    return res


def checkout(block_id: str, root: str | None = None) -> WorkbenchCopy:
    """Copy a shipped block into the Workbench under the same id and version
    (the shipped file stays); a later Promote ships it as ``v + 1``."""
    res = plan_checkout(block_id, root)
    try:
        _write_workbench(res)
    finally:
        capability_folder.forget(res.workbench_path)
        block_library._notify_changed()
    return res


def plan_demote(block_id: str, root: str | None = None) -> WorkbenchCopy:
    """Demote from System: check the rules; writes nothing.

    Raises:
        PromoteRefused: Gate off, not shipped, unreadable (as
            :func:`_plan_workbench`; another block at the target path is named
            in ``overwrites``, not refused), or another shipped block
            references the id (demote that one first).
    """
    from .block_registry import referenced_ids
    res = _plan_workbench(block_id, root, "Demote from System")
    users = []
    for other, path in block_library.shipped_index().items():
        if other == block_id:
            continue
        d = block_library.load_block_file(path)
        if d is not None and block_id in referenced_ids(d):
            users.append(d.name or other)
    if users:
        raise PromoteRefused(
            "These System blocks use it -- demote them first:\n"
            + "\n".join(f"  {n}" for n in sorted(users)))
    return WorkbenchCopy(res.block_id, res.shipped_path, res.workbench_path,
                         res.workbench_written, _app_refs(block_id),
                         res.overwrites)


def demote(block_id: str, root: str | None = None) -> WorkbenchCopy:
    """:func:`plan_demote`, then write the Workbench copy (when none owns the
    id; it replaces any other block at the target path) and only then delete
    the shipped file; an emptied series folder goes
    too. Not an undo step; the open project keeps its embedded copy."""
    from . import hatch_patterns
    res = plan_demote(block_id, root)
    try:
        if res.workbench_written:
            _write_workbench(res)
        block_library.delete_shipped(res.shipped_path)
        folder = os.path.dirname(res.shipped_path)
        block_library._drop_stale_index(folder)
        if (not block_library._same_path(folder, block_library.system_root())
                and os.path.isdir(folder) and not os.listdir(folder)):
            os.rmdir(folder)                 # "no empty series folders"
    finally:
        for p in (res.shipped_path, res.workbench_path):
            capability_folder.forget(p)
        hatch_patterns._SHIPPED_CACHE.clear()
        block_library._notify_changed()
    return res
