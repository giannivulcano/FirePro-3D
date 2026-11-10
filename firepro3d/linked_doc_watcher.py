"""linked_doc_watcher.py
========================
Change detection for sheet-linked documents (sheet-linked-document design D4).

Word and OneDrive save by writing a temp file and renaming it over the
original, which drops a file-level watch. So the watcher watches each linked
file's parent FOLDER, debounces each folder's events, then compares every
linked file in that folder against its (mtime, size) baseline - the values
recorded with the snapshot - and emits ``changed(path)`` only for a real
difference.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal

from .constants import LINKED_DOC_DEBOUNCE_MS


def _key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


class LinkedDocWatcher(QObject):
    """Watches linked files' folders; emits ``changed(abs_path)``.

    Args:
        parent: Owning QObject.
        debounce_ms: Quiet time after a folder's last event before the scan.
    """

    changed = pyqtSignal(str)

    def __init__(self, parent=None, debounce_ms: int = LINKED_DOC_DEBOUNCE_MS):
        super().__init__(parent)
        self._fsw = QFileSystemWatcher(self)
        self._fsw.directoryChanged.connect(self._on_dir_changed)
        self._debounce_ms = int(debounce_ms)
        self._baselines: dict = {}     # file key -> (mtime, size)
        self._paths: dict = {}         # file key -> absolute path as given
        self._timers: dict = {}        # folder key -> single-shot QTimer

    def set_files(self, baselines: dict) -> None:
        """Watch exactly these files: ``{abs_path: (mtime, size)}``."""
        self._baselines = {_key(p): (float(v[0]), int(v[1]))
                           for p, v in baselines.items()}
        self._paths = {_key(p): os.path.abspath(p) for p in baselines}
        wanted = {}
        for k, path in self._paths.items():
            folder = os.path.dirname(path)
            if os.path.isdir(folder):
                wanted[os.path.dirname(k)] = folder
        current = list(self._fsw.directories())
        drop = [d for d in current if _key(d) not in wanted]
        if drop:
            self._fsw.removePaths(drop)
        have = {_key(d) for d in current}
        add = [folder for k, folder in wanted.items() if k not in have]
        if add:
            self._fsw.addPaths(add)

    def set_baseline(self, path: str, mtime: float, size: int) -> None:
        """Record the (mtime, size) a refresh just took, so it does not re-fire."""
        k = _key(path)
        if k in self._baselines:
            self._baselines[k] = (float(mtime), int(size))

    def watched_dirs(self) -> "list[str]":
        """The folders currently watched."""
        return list(self._fsw.directories())

    def _on_dir_changed(self, folder: str) -> None:
        k = _key(folder)
        timer = self._timers.get(k)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(self._debounce_ms)
            timer.timeout.connect(lambda k=k: self._scan(k))
            self._timers[k] = timer
        timer.start()                  # restart: debounce to the last event

    def _scan(self, folder_key: str) -> None:
        for k, base in list(self._baselines.items()):
            if os.path.dirname(k) != folder_key:
                continue
            try:
                st = os.stat(self._paths[k])
            except OSError:
                continue               # gone or mid-rename: the next event rescans
            if (st.st_mtime, st.st_size) != base:
                self.changed.emit(self._paths[k])
