"""Small themed modal message dialog (house frameless shell)."""
from PyQt6.QtWidgets import QDialog, QLabel, QWidget, QVBoxLayout, QPushButton

from .house_dialog import HouseDialog


class ThemedMessageDialog(HouseDialog):
    """An OK-only info modal on the house shell.

    ``_make_yes_no`` switches to a Yes/No pair (No left, Yes right/primary).
    """

    def __init__(self, title, message, parent=None, theme=None, icon=None):
        super().__init__(parent, title=title, icon=icon, min_width=340,
                         theme=theme)
        self.setObjectName("ThemedMessageDialog")
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        col.addWidget(lbl)
        self.set_body(body)
        self.set_footer_buttons(primary=("OK", self.accept), cancel=False)

    def _make_yes_no(self):
        """Rebuild the footer as a Yes/No pair (No left, Yes right/primary)."""
        if self._footer is not None:
            self._footer.setParent(None)
            self._footer = None
        no = QPushButton("No")
        no.clicked.connect(self.reject)
        self.set_footer_buttons(primary=("Yes", self.accept), cancel=False,
                                extra_left=no)


def themed_info(parent, title, message, icon=None) -> None:
    """Show a themed modal info dialog (matches the house shell)."""
    ThemedMessageDialog(title, message, parent=parent, icon=icon).exec()


def themed_confirm(parent, title, message) -> bool:
    """Show a themed Yes/No modal; return True on Yes."""
    dlg = ThemedMessageDialog(title, message, parent=parent)
    dlg._make_yes_no()
    return dlg.exec() == QDialog.DialogCode.Accepted
