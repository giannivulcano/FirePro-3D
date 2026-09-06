"""Small themed modal message dialog (house frameless shell)."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame)

from .frameless_shell import FramelessShellMixin
from .theme import build_dialog_qss, detect


class ThemedMessageDialog(FramelessShellMixin, QDialog):
    """An OK-only info modal matching the house shell (tokenized header +
    ``#dialogBody`` rail + ``#footerBar``). Reuses the ``#MakeBlockDialog`` QSS
    scope so no extra theme rules are needed.
    """

    def __init__(self, title, message, parent=None, theme=None, icon=None):
        super().__init__(parent)
        theme = theme or detect()
        self.init_frameless_shell(title=title, controls=("close",), icon=icon)
        self.setObjectName("ThemedMessageDialog")
        self.setProperty("houseDialog", True)
        self.setStyleSheet(build_dialog_qss(theme))
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
        self._footer_layout = fb
        fb.addStretch(1)
        ok = QPushButton("OK")
        ok.setProperty("variant", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        fb.addWidget(ok)
        root.addWidget(footer)

    def _make_yes_no(self):
        """Swap the OK-only footer for a right-aligned Yes/No button pair."""
        while self._footer_layout.count():
            item = self._footer_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._footer_layout.addStretch(1)
        yes = QPushButton("Yes")
        yes.setProperty("variant", "primary")
        yes.setDefault(True)
        yes.clicked.connect(self.accept)
        self._footer_layout.addWidget(yes)
        no = QPushButton("No")
        no.clicked.connect(self.reject)
        self._footer_layout.addWidget(no)


def themed_info(parent, title, message, icon=None) -> None:
    """Show a themed modal info dialog (matches the house shell)."""
    ThemedMessageDialog(title, message, parent=parent, icon=icon).exec()


def themed_confirm(parent, title, message) -> bool:
    """Show a themed Yes/No modal; return True on Yes."""
    from PyQt6.QtWidgets import QDialog
    dlg = ThemedMessageDialog(title, message, parent=parent)
    dlg._make_yes_no()
    return dlg.exec() == QDialog.DialogCode.Accepted
