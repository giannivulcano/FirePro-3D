"""Two-tier user library for block definitions.

Layout: ``<root>/<Library>/<Series>/<name>.fpdb`` (a BlockDefinition.to_dict())
plus a per-Series ``index.json`` mapping filename -> {id, name, version,
thumbnail}. Mirrors titleblock_template's atomic-write + tolerant-load + version
divergence, over a folder tree with human-readable filenames. Thumbnails are
reserved (S4). See docs/specs/block-system.md.
"""
from __future__ import annotations

import json
import logging
import os
import re

from .app_data import app_data_dir
from .block_definition import BlockDefinition

_log = logging.getLogger(__name__)
_INDEX = "index.json"


class BlockNameCollision(Exception):
    """Raised by :func:`save_to_library` when the target ``.fpdb`` filename is
    already occupied by a *different* block ``id`` (and ``overwrite`` is False).

    Carries ``existing_name`` (the human name of the block that would be
    clobbered) so the caller can offer an overwrite/cancel prompt.
    """

    def __init__(self, existing_name: str, filename: str):
        super().__init__(
            f"A different block already uses {filename!r} ({existing_name!r})")
        self.existing_name = existing_name
        self.filename = filename


def _root(root: str | None) -> str:
    return root if root is not None else app_data_dir("blocks")


def sanitize(name: str) -> str:
    """Filesystem-safe segment: keep [A-Za-z0-9 _.-], collapse the rest to '_'."""
    s = re.sub(r"[^A-Za-z0-9 _.\-]", "_", (name or "").strip())
    return s or "_"


def _series_dir(root: str | None, library: str, series: str) -> str:
    return os.path.join(_root(root), sanitize(library), sanitize(series))


def _atomic_write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def _read_index(series_dir: str) -> dict:
    path = os.path.join(series_dir, _INDEX)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        _log.warning("Unreadable block index %s: %s", path, exc)
        return {}


def save_to_library(definition: BlockDefinition, root: str | None = None,
                    *, overwrite: bool = False) -> str:
    """Write *definition* to the tree + update the Series index; returns the path.

    Keyed on ``definition.id`` (the frozen identity), not the folder location:

    - **Collision:** if the target ``<name>.fpdb`` is already held by a *different*
      ``id`` and ``overwrite`` is False, raise :class:`BlockNameCollision` without
      touching disk (so the caller can prompt overwrite/cancel).
    - **Re-file:** any stale copy of this same ``id`` living elsewhere in the tree
      (a prior Library/Series/name) is removed, so the block never duplicates.

    Args:
        overwrite: proceed past a cross-``id`` filename collision (clobber the
            other block's ``.fpdb`` + index entry). Confirmed by the caller.
    """
    series_dir = _series_dir(root, definition.library, definition.series)
    filename = sanitize(definition.name) + ".fpdb"
    path = os.path.join(series_dir, filename)

    # (a) Cross-id collision check — BEFORE any mutation, so a refused save is inert.
    target_index = _read_index(series_dir)
    clash = target_index.get(filename)
    if not overwrite and clash is not None and clash.get("id") != definition.id:
        raise BlockNameCollision(clash.get("name", filename), filename)

    # (b) Re-file: drop any stale copy of this id parked at a different location.
    existing = _find_by_id(definition.id, root)
    if existing is not None:
        old_lib, old_series, old_fname, _meta = existing
        if (old_lib, old_series, old_fname) != (sanitize(definition.library),
                                                sanitize(definition.series),
                                                filename):
            delete_from_library(old_lib, old_series, old_fname, root)

    # (c) Write the .fpdb + refresh the Series index.
    _atomic_write_json(path, definition.to_dict())
    index = _read_index(series_dir)
    index[filename] = {"id": definition.id, "name": definition.name,
                       "version": definition.version, "thumbnail": None}
    _atomic_write_json(os.path.join(series_dir, _INDEX), index)
    return path


def _iter_index_entries(root: str | None):
    """Yield ``(library, series, filename, meta)`` for every indexed .fpdb in the
    tree (sorted, deterministic). The single tree-walk shared by ``list_library``
    and the by-id lookups — identity is the ``id``, not the folder location."""
    base = _root(root)
    if not os.path.isdir(base):
        return
    for library in sorted(os.listdir(base)):
        lib_dir = os.path.join(base, library)
        if not os.path.isdir(lib_dir):
            continue
        for series in sorted(os.listdir(lib_dir)):
            series_dir = os.path.join(lib_dir, series)
            if not os.path.isdir(series_dir):
                continue
            for filename, meta in _read_index(series_dir).items():
                yield library, series, filename, meta


def _find_by_id(block_id: str, root: str | None):
    """Locate a block by its ``id`` anywhere in the tree (not just its def's
    current Library/Series folder). Returns ``(library, series, filename, meta)``
    for the first match, or None. Fixes the 're-filed block reads project-only'
    class where a block's on-disk copy lives in a folder other than its current
    metadata would suggest."""
    for library, series, filename, meta in _iter_index_entries(root):
        if meta.get("id") == block_id:
            return library, series, filename, meta
    return None


def list_library(root: str | None = None) -> list[dict]:
    """List library entries from the per-Series indexes (no full .fpdb parse).

    Each entry: {library, series, filename, id, name, version, thumbnail}.
    """
    return [{"library": library, "series": series, "filename": filename, **meta}
            for library, series, filename, meta in _iter_index_entries(root)]


def load_block(library: str, series: str, filename: str,
               root: str | None = None) -> BlockDefinition | None:
    """Load one .fpdb into a BlockDefinition; None if missing/corrupt."""
    path = os.path.join(_series_dir(root, library, series), filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return BlockDefinition.from_dict(json.load(fh))
    except Exception as exc:
        _log.warning("Unreadable block .fpdb %s: %s", path, exc)
        return None


def load_block_file(path: str) -> BlockDefinition | None:
    """Load a BlockDefinition from an arbitrary .fpdb path (a .fpdb IS a
    ``to_dict()`` JSON). None if missing/unreadable/corrupt (logged). Used by
    the browse-anywhere 'Load from Library' file dialog, which is not restricted
    to the library tree."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return BlockDefinition.from_dict(json.load(fh))
    except Exception as exc:
        _log.warning("Unreadable block .fpdb %s: %s", path, exc)
        return None


def source_status(definition: BlockDefinition, root: str | None = None) -> str:
    """Return 'project-only' | 'library' | 'modified' for an embedded def.

    Resolves the library copy by ``id`` across the whole tree, so a block whose
    metadata (Library/Series/name) has drifted from its on-disk location still
    reads correctly instead of falsely 'project-only'.
    """
    found = _find_by_id(definition.id, root)
    if found is None:
        return "project-only"
    _lib, _series, _fname, meta = found
    return "library" if meta.get("version") == definition.version else "modified"


def reload_from_library(definition: BlockDefinition,
                        root: str | None = None) -> BlockDefinition | None:
    """Return the library copy of *definition* (by id), or None if absent.

    Locates the copy by ``id`` anywhere in the tree (not just the def's current
    Library/Series folder)."""
    found = _find_by_id(definition.id, root)
    if found is None:
        return None
    library, series, filename, _meta = found
    return load_block(library, series, filename, root)


def delete_from_library(library: str, series: str, filename: str,
                        root: str | None = None) -> None:
    """Remove a .fpdb + its index entry (no-op when absent)."""
    series_dir = _series_dir(root, library, series)
    path = os.path.join(series_dir, filename)
    if os.path.isfile(path):
        os.remove(path)
    index = _read_index(series_dir)
    if filename in index:
        del index[filename]
        _atomic_write_json(os.path.join(series_dir, _INDEX), index)
