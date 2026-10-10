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

#: The capability flags a scan can select on (``.fpdb`` top-level keys).
FLAGS = ("tile", "repeat", "end")

_log = logging.getLogger(__name__)
_SCAN_CACHE: dict = {}       # (abs folder, flag) -> (stamp, [(name, id, path)])
_PARSE_CACHE: dict = {}      # (.fpdb path, mtime_ns) -> read_meta dict | None
_LOGGED: set = set()         # paths already logged as unreadable (log once)


def _log_once(path: str, exc) -> None:
    if path not in _LOGGED:
        _LOGGED.add(path)
        _log.warning("Capability folder: unreadable %s: %s", path, exc)


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
    """``{id, name, version, kind, tile, repeat, end}`` read from the ``.fpdb``
    itself, cached per (path, mtime); None if unreadable (logged once).

    The one parse shared by the capability pickers and ``block_library``'s
    disk walk -- there is no index (retired 2026-10-10).
    """
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        return None
    key = (path, mtime)
    if key in _PARSE_CACHE:
        return _PARSE_CACHE[key]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("not a block definition")
        res = {"id": data.get("id") or "", "name": data.get("name") or "",
               "version": data.get("version", 1),
               "kind": data.get("kind") or "block",
               **{f: bool(data.get(f)) for f in FLAGS}}
    except Exception as exc:          # noqa: BLE001 — skip silently, log once
        _log_once(path, exc)
        res = None
    _PARSE_CACHE[key] = res
    return res


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
    out, seen = [], set()
    for path, _mtime in stamp:
        meta = read_meta(path)
        if meta is None:
            continue
        bid = meta["id"]
        if meta[flag] and bid and bid not in seen:
            seen.add(bid)
            out.append((meta["name"] or os.path.basename(path)[:-5], bid, path))
    out.sort(key=lambda x: x[0].lower())
    _SCAN_CACHE[(folder, flag)] = (stamp, out)
    return list(out)
