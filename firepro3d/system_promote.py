"""Promote to System (block-system.md "System library tier", authoring path
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
    version = (shipped_version + 1 if shipped_version is not None
               else int(meta.get("version") or 1))
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
    block_library.write_shipped(res.shipped_path, shipped)
    if res.removed_path:
        block_library.delete_shipped(res.removed_path)
    block_library._atomic_write_json(res.workbench_path, rec)
    for p in (res.shipped_path, res.workbench_path, res.removed_path):
        if p:
            capability_folder.forget(p)
    block_library._notify_changed()
    return res
