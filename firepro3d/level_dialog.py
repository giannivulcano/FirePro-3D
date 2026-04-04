"""
level_dialog.py
===============
Modal dialog wrapping the LevelWidget for standalone access from the ribbon.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt

from level_manager import LevelManager
from level_widget import LevelWidget


class LevelDialog(QDialog):
    """Modal dialog for managing levels (add/remove/edit/duplicate).

    Wraps the existing LevelWidget and exposes its signals so main.py
    can react to level changes.
    """

    activeLevelChanged = pyqtSignal(str)
    levelsChanged = pyqtSignal()
    duplicateLevel = pyqtSignal(str, str)

    def __init__(self, manager: LevelManager, scene=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Level Manager")
        self.setMinimumSize(420, 350)
        self.resize(480, 450)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Embed the existing LevelWidget
        self._widget = LevelWidget(manager, scene=scene, parent=self)
        layout.addWidget(self._widget)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # Forward signals
        self._widget.activeLevelChanged.connect(self.activeLevelChanged.emit)
        self._widget.levelsChanged.connect(self.levelsChanged.emit)
        self._widget.duplicateLevel.connect(self.duplicateLevel.emit)

    def populate(self):
        """Refresh the embedded widget."""
        self._widget.populate()
