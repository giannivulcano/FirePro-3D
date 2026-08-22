"""Unified Preferences dialog — tabbed QDialog with snapshot/revert panes.

New settings live here first (design-of-record: 2026-08-22-ribbon-overhaul).
Panes own their own persistence target (QSettings or the project dict).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QVBoxLayout, QWidget, QDialogButtonBox,
)


class SettingsPane(QWidget):
    """Base pane. Subclasses implement load/apply/revert and build their UI."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title

    def load(self):   ...   # snapshot current state + populate widgets
    def apply(self):  ...   # commit staged values to the persistence target
    def revert(self): ...   # restore the snapshot


class PreferencesDialog(QDialog):
    def __init__(self, panes: list[SettingsPane], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(560)
        self._panes = panes
        lay = QVBoxLayout(self)
        self._tabs = QTabWidget()
        for pane in panes:
            pane.load()
            self._tabs.addTab(pane, pane.title)
        lay.addWidget(self._tabs)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_all)
        lay.addWidget(box)

    def _apply_all(self):
        for pane in self._panes:
            pane.apply()

    def accept(self):
        self._apply_all()
        super().accept()

    def reject(self):
        for pane in self._panes:
            pane.revert()
        super().reject()
