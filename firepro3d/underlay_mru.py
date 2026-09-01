"""Project-scoped recent-underlay-sources list, backed by QSettings."""
from __future__ import annotations
from PyQt6.QtCore import QSettings

_KEY = "underlay/recent_sources"


class RecentSources:
    def __init__(self, settings: QSettings | None = None, cap: int = 5):
        self._s = settings if settings is not None else QSettings("GV", "FirePro3D")
        self._cap = cap

    def list(self) -> list[str]:
        raw = self._s.value(_KEY, [])
        if isinstance(raw, str):          # QSettings collapses 1-item lists
            return [raw]
        return list(raw or [])

    def add(self, path: str) -> None:
        items = [p for p in self.list() if p != path]
        items.insert(0, path)
        self._s.setValue(_KEY, items[: self._cap])
