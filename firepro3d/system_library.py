"""Startup migration into the read-only System library tier (SB1b D5).

Idempotent by on-disk state, no flag: (1) the D-A39 seeded hatch copies are
cleaned -- a copy byte-identical to its shipped file is deleted, an edited
copy keeps its content under a fresh id (an ordinary user block); (2) the
user library's ``System/`` defaults folder moves to ``Styles/`` unless a
Hatch patterns / Linetypes / End types override points into it.
"""

from __future__ import annotations

import filecmp
import json
import logging
import os
import shutil
import uuid

from . import block_library, capability_folder
from .app_data import (END_DIR_KEY, HATCH_DIR_KEY, LINETYPE_DIR_KEY,
                       block_library_dir, configured_dir)
from .hatch_patterns import (HATCH_SEEDED_KEY, _seeded_folders,
                             shipped_pattern_files)

_log = logging.getLogger(__name__)

STYLES_FOLDER = "Styles"


def migrate_user_library() -> dict:
    """Run both migration steps.

    Returns:
        ``{removed, reided, moved, skipped}`` -- lists of affected paths.
    """
    report = {"removed": [], "reided": [], "moved": [], "skipped": []}
    _clean_seeded_hatches(report)
    _move_system_folder(report)
    if any(report.values()):
        block_library._notify_changed()
    return report


def _clean_seeded_hatches(report: dict) -> None:
    folders = _seeded_folders()
    if not folders:
        return
    shipped = dict(shipped_pattern_files())
    for folder in folders:
        try:
            names = sorted(e.path for e in os.scandir(folder)
                           if e.is_file() and e.name.lower().endswith(".fpdb"))
        except OSError:
            continue                              # folder gone: skipped
        for path in names:
            meta = capability_folder.read_meta(path)
            src = shipped.get(meta["id"]) if meta else None
            if src is None:
                continue
            try:
                if filecmp.cmp(path, src, shallow=False):
                    os.remove(path)
                    report["removed"].append(path)
                else:
                    _reid(path)
                    report["reided"].append(path)
            except OSError:
                _log.warning("Seeded hatch %s not migrated", path, exc_info=True)
                continue
            capability_folder.forget(path)
    from PyQt6.QtCore import QSettings
    QSettings("GV", "FirePro3D").remove(HATCH_SEEDED_KEY)


def _reid(path: str) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    data["id"] = uuid.uuid4().hex
    block_library._atomic_write_json(path, data)


def _inside(path: str, folder: str) -> bool:
    p = os.path.normcase(os.path.abspath(path))
    f = os.path.normcase(os.path.abspath(folder))
    return p == f or p.startswith(f + os.sep)


def _move_system_folder(report: dict) -> None:
    base = block_library_dir()
    src = os.path.join(base, block_library.SYSTEM_LIBRARY)
    if not os.path.isdir(src):
        return
    for key in (HATCH_DIR_KEY, LINETYPE_DIR_KEY, END_DIR_KEY):
        override = configured_dir(key)
        if override and _inside(override, src):
            return                                # explicit override: never moved
    dst = os.path.join(base, STYLES_FOLDER)
    if not os.path.exists(dst):
        os.replace(src, dst)
        report["moved"].append(src)
        return
    for dirpath, _dirs, files in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        for f in files:
            target = os.path.normpath(os.path.join(dst, rel, f))
            if os.path.exists(target):
                _log.warning("Styles migration: %s exists; left in System/", target)
                report["skipped"].append(os.path.join(dirpath, f))
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(os.path.join(dirpath, f), target)
            report["moved"].append(os.path.join(dirpath, f))
    for dirpath, _dirs, _files in os.walk(src, topdown=False):
        try:
            os.rmdir(dirpath)                     # only empty folders go
        except OSError:
            pass
