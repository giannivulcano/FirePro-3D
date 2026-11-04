"""Project-file safety: rolling Save backups, atomic write, content counts."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime

from .constants import (
    CONTENT_LOSS_MIN_ITEMS, PROJECT_BACKUP_DIR, PROJECT_BACKUP_KEEP,
)

_MODEL_KEYS = ("nodes", "pipes", "walls", "blocks", "floor_slabs", "roofs",
               "rooms", "gridlines", "underlays")


def write_backup(path: str, now: datetime | None = None) -> str | None:
    """Copy *path* to ``Backups/<stem> <timestamp><ext>`` and prune old copies.

    Returns:
        The backup's path, or None when *path* does not exist yet.
    """
    if not os.path.isfile(path):
        return None
    folder = os.path.join(os.path.dirname(os.path.abspath(path)), PROJECT_BACKUP_DIR)
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(path))
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H%M%S")
    target = os.path.join(folder, f"{stem} {stamp}{ext}")
    shutil.copy2(path, target)
    _prune(folder, stem, ext)
    return target


def _prune(folder: str, stem: str, ext: str) -> None:
    """Keep this project's newest backups; a project whose name merely starts
    with *stem* has its own timestamp pattern and is never touched."""
    pattern = re.compile(re.escape(stem) + r" \d{4}-\d{2}-\d{2} \d{6}" + re.escape(ext))
    own = sorted(n for n in os.listdir(folder) if pattern.fullmatch(n))
    for name in own[:-PROJECT_BACKUP_KEEP]:
        os.remove(os.path.join(folder, name))


def write_atomic(path: str, payload: dict) -> None:
    """Write *payload* as JSON: the original survives any failure."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def scene_item_count(scene) -> int:
    """Model items in *scene*, counted over the keys of :data:`_MODEL_KEYS`."""
    return (len(scene.sprinkler_system.nodes) + len(scene.sprinkler_system.pipes)
            + len(scene._walls) + len(scene._block_instances)
            + len(scene._floor_slabs) + len(scene._roofs) + len(scene._rooms)
            + len(scene._gridlines) + len(scene.underlays))


def file_item_count(path: str) -> int | None:
    """Model items in the project at *path*; None when it cannot be read."""
    try:
        with open(path, "r") as f:
            payload = json.load(f)
        return sum(len(payload.get(k) or []) for k in _MODEL_KEYS)
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def loses_content(on_disk: int | None, in_scene: int) -> bool:
    """Whether saving *in_scene* items over *on_disk* warrants a warning."""
    return (on_disk is not None and on_disk >= CONTENT_LOSS_MIN_ITEMS
            and in_scene * 2 < on_disk)
