"""
underlay_cache.py
=================
Geometry-dict cache for underlay files (DXF / PDF).

Stores the intermediate geometry dicts (output of ezdxf / PyMuPDF parsing)
as JSON in a sibling ``.fpd.cache/`` directory.  On project reload the
expensive source-file parsing is skipped when a fresh cache entry exists.

Cache key:  ``<sanitised_basename>_<hex_hash>.json``
Freshness:  source-file modification timestamp stored inside the cache file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re

_CACHE_VERSION = 1


def cache_dir_for_project(project_path: str) -> str:
    """Return the cache directory path for a given project file.

    Args:
        project_path: Absolute path to the ``.fpd`` project file.

    Returns:
        Absolute path of the sibling ``<project_path>.cache`` directory.
    """
    return project_path + ".cache"


def compute_cache_key(
    source_path: str,
    page: int = 0,
    selected_layers: list[str] | None = None,
    layout: str = "",
) -> str:
    """Return a deterministic cache filename for the given source parameters.

    The key is built from a SHA-256 hash of the normalised absolute path,
    the page number, and the sorted layer list.  The basename is sanitised
    so the result is a safe filename on all platforms.

    Args:
        source_path: Path to the source DXF or PDF file.
        page: Page/sheet index (0-based).  Defaults to ``0``.
        selected_layers: Optional list of layer names to include.  Order
            is irrelevant — the list is sorted before hashing.

    Returns:
        A filename of the form ``<sanitised_basename>_<hex16>.json``.
    """
    norm_path = os.path.normpath(os.path.abspath(source_path))
    layers_repr = "|".join(sorted(selected_layers)) if selected_layers else ""
    raw = f"{norm_path}|{page}|{layers_repr}|{layout}"
    hex16 = hashlib.sha256(raw.encode()).hexdigest()[:16]

    base = os.path.basename(norm_path)
    sanitised = re.sub(r"[^\w\-]", "_", base)[:40]
    return f"{sanitised}_{hex16}.json"


def write_cache(
    cache_dir: str,
    key: str,
    geom_list: list[dict],
    source_mtime: float,
) -> None:
    """Write geometry dicts to the cache.

    Creates *cache_dir* if it does not exist.  Existing entries are
    overwritten atomically via a rename so partial writes are not visible.

    Args:
        cache_dir: Directory that holds cache files.
        key: Filename returned by :func:`compute_cache_key`.
        geom_list: List of geometry dicts to persist.
        source_mtime: Modification time of the source file (``os.path.getmtime``).
    """
    os.makedirs(cache_dir, exist_ok=True)
    payload = {
        "version": _CACHE_VERSION,
        "source_mtime": source_mtime,
        "geom_count": len(geom_list),
        "geoms": geom_list,
    }
    cache_file = os.path.join(cache_dir, key)
    tmp_file = cache_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    os.replace(tmp_file, cache_file)


def read_cache(
    cache_dir: str,
    key: str,
    source_mtime: float | None,
) -> list[dict] | None:
    """Read geometry dicts from the cache if the entry is fresh.

    Args:
        cache_dir: Directory that holds cache files.
        key: Filename returned by :func:`compute_cache_key`.
        source_mtime: Current modification time of the source file, or
            ``None`` to skip the freshness check (useful when the source
            file is no longer present on disk).

    Returns:
        The list of geometry dicts, or ``None`` if the cache is missing,
        corrupt, the wrong version, or stale.
    """
    cache_file = os.path.join(cache_dir, key)
    if not os.path.isfile(cache_file):
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("version") != _CACHE_VERSION:
        return None

    if source_mtime is not None:
        cached_mtime = payload.get("source_mtime")
        if cached_mtime is None or source_mtime != cached_mtime:
            return None

    geoms = payload.get("geoms")
    if not isinstance(geoms, list):
        return None
    return geoms


def delete_cache(cache_dir: str, key: str) -> None:
    """Remove a cache entry.  No-op if the file does not exist.

    Args:
        cache_dir: Directory that holds cache files.
        key: Filename returned by :func:`compute_cache_key`.
    """
    cache_file = os.path.join(cache_dir, key)
    try:
        os.remove(cache_file)
    except FileNotFoundError:
        pass
