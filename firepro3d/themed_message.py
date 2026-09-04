"""Small themed modal message dialog (house frameless shell)."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame)

from .frameless_shell import FramelessShellMixin
from .theme import build_underlay_manager_qss, detect


class ThemedMessageDialog(FramelessShellMixin, QDialog):
    """An OK-only info modal matching the house shell (tokenized header +
    ``#dialogBody`` rail + ``#footerBar``). Reuses the ``#MakeBlockDialog`` QSS
    scope so no extra theme rules are needed.
    """

    def __init__(self, title, message, parent=None, theme=None, icon=None):
        super().__init__(parent)
        theme = theme or detect()
        self.init_frameless_shell(title=title, controls=("close",), icon=icon)
        self.setObjectName("MakeBlockDialog")   # shared QSS scope (see theme.py)
        self.setStyleSheet(build_underlay_manager_qss(theme))
        self.setMinimumWidth(340)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._titlebar)

        body = QFrame(objectName="dialogBody")
        col = QVBoxLayout(body)
        col.setContentsMargins(20, 18, 20, 18)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        col.addWidget(lbl)
        root.addWidget(body)

        footer = QFrame(objectName="footerBar")
        fb = QHBoxLayout(footer)
        fb.setContentsMargins(16, 10, 16, 10)
        fb.addStretch(1)
        ok = QPushButton("OK")
        ok.setProperty("variant", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        fb.addWidget(ok)
        root.addWidget(footer)


def themed_info(parent, title, message, icon=None) -> None:
    """Show a themed modal info dialog (matches the house shell)."""
    ThemedMessageDialog(title, message, parent=parent, icon=icon).exec()
