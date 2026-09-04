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


def save_to_library(definition: BlockDefinition, root: str | None = None) -> str:
    """Write *definition* to the tree + update the Series index; returns the path."""
    series_dir = _series_dir(root, definition.library, definition.series)
    filename = sanitize(definition.name) + ".fpdb"
    path = os.path.join(series_dir, filename)
    _atomic_write_json(path, definition.to_dict())
    index = _read_index(series_dir)
    index[filename] = {"id": definition.id, "name": definition.name,
                       "version": definition.version, "thumbnail": None}
    _atomic_write_json(os.path.join(series_dir, _INDEX), index)
    return path


def list_library(root: str | None = None) -> list[dict]:
    """List library entries from the per-Series indexes (no full .fpdb parse).

    Each entry: {library, series, filename, id, name, version, thumbnail}.
    """
    base = _root(root)
    out: list[dict] = []
    if not os.path.isdir(base):
        return out
    for library in sorted(os.listdir(base)):
        lib_dir = os.path.join(base, library)
        if not os.path.isdir(lib_dir):
            continue
        for series in sorted(os.listdir(lib_dir)):
            series_dir = os.path.join(lib_dir, series)
            if not os.path.isdir(series_dir):
                continue
            for filename, meta in _read_index(series_dir).items():
                out.append({"library": library, "series": series,
                            "filename": filename, **meta})
    return out


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


def _index_entry_for(definition: BlockDefinition, root: str | None) -> dict | None:
    """Find the library index entry with the same id in the def's Library/Series."""
    series_dir = _series_dir(root, definition.library, definition.series)
    for _fname, meta in _read_index(series_dir).items():
        if meta.get("id") == definition.id:
            return meta
    return None


def source_status(definition: BlockDefinition, root: str | None = None) -> str:
    """Return 'project-only' | 'library' | 'modified' for an embedded def."""
    entry = _index_entry_for(definition, root)
    if entry is None:
        return "project-only"
    return "library" if entry.get("version") == definition.version else "modified"


def reload_from_library(definition: BlockDefinition,
                        root: str | None = None) -> BlockDefinition | None:
    """Return the library copy of *definition* (by id), or None if absent."""
    series_dir = _series_dir(root, definition.library, definition.series)
    for fname, meta in _read_index(series_dir).items():
        if meta.get("id") == definition.id:
            return load_block(definition.library, definition.series, fname, root)
    return None


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
