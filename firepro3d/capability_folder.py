"""Capability-folder scan shared by the Hatch patterns, Linetypes and End Types folders.

hatch-and-fill.md D-A37 (``tile``) and linetypes.md LT3-13 / H3-i
(``repeat``): a capability folder is any folder of ``.fpdb`` blocks (a Series,
a Library or a Library root) whose blocks carrying the capability flag are
offered in the matching picker. Pure filesystem + JSON — no Qt, no block
imports — and never called from paint paths.
"""
from __future__ import annotations

import json
import logging
import os
import re

#: The capability flags a scan can select on (``.fpdb`` top-level keys).
FLAGS = ("tile", "repeat", "end")

_log = logging.getLogger(__name__)
_SCAN_CACHE: dict = {}       # (abs folder, flag) -> (stamp, [(name, id, path)])
_PARSE_CACHE: dict = {}      # (path, mtime_ns, size, ino) -> read_meta dict | None
_LOGGED: set = set()         # paths already logged as unreadable (log once)


def _log_once(path: str, exc) -> None:
    if path not in _LOGGED:
        _LOGGED.add(path)
        _log.warning("Capability folder: unreadable %s: %s", path, exc)


def sanitize(name: str) -> str:
    """Filesystem-safe segment: keep [A-Za-z0-9 _.-], collapse the rest to '_'.

    The ``.fpdb`` file-name rule (``block_library`` names files with it)."""
    s = re.sub(r"[^A-Za-z0-9 _.\-]", "_", (name or "").strip())
    return s or "_"


def owns_name(path: str, meta: dict) -> bool:
    """True when *path*'s file name is still the one its stored name gives --
    the original, not a copy made to vary it (a copy shares the id)."""
    return os.path.basename(path)[:-5] == sanitize(meta.get("name"))


def _scan_dirs(folder: str) -> list[str]:
    """*folder*, its subfolders and their subfolders (a Series, a Library or a
    Library root all work as the capability folder), sorted for determinism."""
    dirs, level = [folder], [folder]
    for _depth in range(2):
        nxt = []
        for d in level:
            try:
                subs = sorted(e.path for e in os.scandir(d) if e.is_dir())
            except OSError:
                continue
            nxt.extend(subs)
        dirs.extend(nxt)
        level = nxt
    return dirs


def _dir_stamp(dirs: list[str]) -> tuple:
    """Cache key: every .fpdb path in *dirs* with its mtime."""
    stamp = []
    for d in dirs:
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            if e.is_file() and e.name.lower().endswith(".fpdb"):
                try:
                    stamp.append((e.path, e.stat().st_mtime_ns))
                except OSError:
                    continue
    return tuple(stamp)


def read_meta(path: str) -> dict | None:
    """``{id, name, library, series, version, kind, tile, repeat, end}`` read
    from the ``.fpdb``
    itself, cached per (path, mtime, size, file id) -- a save inside one
    clock tick still changes the file id (atomic replace) -- ; None if
    unreadable (logged once).

    The one parse shared by the capability pickers and ``block_library``'s
    disk walk -- there is no index (retired 2026-10-10).
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_mtime_ns, st.st_size, st.st_ino)
    if key in _PARSE_CACHE:
        return _PARSE_CACHE[key]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("not a block definition")
        res = {"id": data.get("id") or "", "name": data.get("name") or "",
               "library": data.get("library") or "",
               "series": data.get("series") or "",
               "version": data.get("version", 1),
               "kind": data.get("kind") or "block",
               **{f: bool(data.get(f)) for f in FLAGS}}
    except Exception as exc:          # noqa: BLE001 — skip silently, log once
        _log_once(path, exc)
        res = None
    _PARSE_CACHE[key] = res
    return res


def forget(path: str) -> None:
    """Drop every cached parse of *path* (the app just wrote or removed it)."""
    norm = os.path.normcase(os.path.abspath(path))
    for key in [k for k in _PARSE_CACHE
                if os.path.normcase(os.path.abspath(k[0])) == norm]:
        del _PARSE_CACHE[key]
    _SCAN_CACHE.clear()


def scan(folder: str, flag: str) -> list[tuple[str, str, str]]:
    """Capability blocks in *folder* plus two levels of subfolders.

    Each ``.fpdb`` is read for *flag* (:func:`read_meta`, cached per mtime).
    Cached on (folder, flag) + every .fpdb mtime, so a newly saved or
    hand-copied block appears without a restart. Unreadable files are skipped
    (logged once). Never called from paint paths.

    Args:
        folder: Folder to scan.
        flag: The capability flag — ``"tile"`` (hatch patterns),
            ``"repeat"`` (linetypes) or ``"end"`` (end types).

    Returns:
        ``[(name, block_id, .fpdb path)]`` sorted by name; first id wins.
    """
    if flag not in FLAGS:
        raise ValueError(f"unknown capability flag {flag!r}")
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        return []
    dirs = _scan_dirs(folder)
    stamp = _dir_stamp(dirs)
    hit = _SCAN_CACHE.get((folder, flag))
    if hit is not None and hit[0] == stamp:
        return list(hit[1])
    metas = [(path, read_meta(path)) for path, _mtime in stamp]
    metas = [(p, m) for p, m in metas if m is not None and m["id"] and m[flag]]
    # A copied file shares its original's id: the file whose name still
    # matches its stored name owns the id (as in ``block_library``), else
    # the first in scan order.
    owner: dict = {}
    for path, meta in metas:
        if owns_name(path, meta):
            owner.setdefault(meta["id"], path)
    for path, meta in metas:
        owner.setdefault(meta["id"], path)
    out = [(meta["name"] or os.path.basename(path)[:-5], meta["id"], path)
           for path, meta in metas if owner[meta["id"]] == path]
    out.sort(key=lambda x: x[0].lower())
    _SCAN_CACHE[(folder, flag)] = (stamp, out)
    return list(out)
