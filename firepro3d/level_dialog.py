"""
level_dialog.py
===============
The Level Manager dialog (ribbon Build > Datums > Levels): a HouseDialog wrapping a
LevelWidget with a Close-only footer (view-relationships section 12; chrome per
ui-design-system.md; mockup docs/mockups/level-manager-tuner.html).
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from .house_dialog import HouseDialog
from .level_manager import LevelManager
from .level_widget import LevelWidget
from .theme import M


class LevelDialog(HouseDialog):
    """Modal Level Manager. Forwards the widget's signals so main.py can chain them
    into the hidden hub widget (one consumer list — section 12 D4)."""

    activeLevelChanged = pyqtSignal(str)
    levelsChanged = pyqtSignal()
    duplicateLevel = pyqtSignal(str, str)
    levelRenamed = pyqtSignal(str, str)
    levelsRemoved = pyqtSignal(list)

    def __init__(self, manager: LevelManager, scene=None, parent=None):
        super().__init__(parent, title="Level Manager", resizable=True)
        self.widget = LevelWidget(manager, scene=scene, parent=self)
        self.body_layout().addWidget(self.widget, 1)
        self.set_footer_buttons(cancel=False, close=("Close", self.accept))
        self.setMinimumSize(*M.LEVEL_DLG_MIN)     # the old dialog's floor (table + glyph row + footer)
        self.resize(*M.LEVEL_DLG_SIZE)        # after set_footer_buttons: it adjustSize()s
        self.widget.activeLevelChanged.connect(self.activeLevelChanged)
        self.widget.levelsChanged.connect(self.levelsChanged)
        self.widget.duplicateLevel.connect(self.duplicateLevel)
        self.widget.levelRenamed.connect(self.levelRenamed)
        self.widget.levelsRemoved.connect(self.levelsRemoved)
