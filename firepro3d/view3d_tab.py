"""The 3D Model canvas tab's presence: close = hide, reopen leftmost, pref.

Governed by ``docs/specs/view-3d.md`` §10 I1–I4/I7. The View3D widget is a
keep-alive singleton — this controller never deletes it.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QTabWidget, QWidget

PREF_KEY = "ui/view3d_open"
TAB_TITLE = "3D Model"


class View3DTabController:
    """Owns whether the 3D view is a canvas tab.

    Args:
        tabs: The canvas ``QTabWidget``.
        view_3d: The keep-alive 3D view widget (must offer ``clear_pick()``).
        settings: The app ``QSettings`` holding ``ui/view3d_open``.
    """

    def __init__(self, tabs: QTabWidget, view_3d: QWidget, settings: QSettings):
        self._tabs = tabs
        self._view = view_3d
        self._settings = settings

    def is_open(self) -> bool:
        """Whether the 3D view is currently a canvas tab.

        Returns:
            True when the 3D view widget is present in the tab widget.
        """
        return self._tabs.indexOf(self._view) != -1

    def open(self) -> None:
        """Show the 3D tab leftmost and current, and remember it open (I2, I3).

        Idempotent: a repeat call (e.g. a double-fired browser activation)
        never adds a second tab — it only re-selects the existing one.
        """
        if not self.is_open():
            self._tabs.insertTab(0, self._view, TAB_TITLE)
        self._tabs.setCurrentIndex(self._tabs.indexOf(self._view))
        self._settings.setValue(PREF_KEY, True)

    def close(self, *, remember: bool = True) -> None:
        """Remove the tab, keep the widget alive, drop the 3D pick (I1, I7).

        Args:
            remember: When True, persist the closed state to ``ui/view3d_open``
                (a user close). False closes without touching the pref
                (startup restore).
        """
        self._view.clear_pick()
        idx = self._tabs.indexOf(self._view)
        if idx != -1:
            self._tabs.removeTab(idx)
        if remember:
            self._settings.setValue(PREF_KEY, False)

    def apply_startup_pref(self) -> None:
        """Close the tab at startup when the user last left it closed (I4)."""
        if not self._settings.value(PREF_KEY, True, type=bool):
            self.close(remember=False)
