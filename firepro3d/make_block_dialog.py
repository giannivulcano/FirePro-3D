"""MakeBlockDialog — capture name / Library / Series for a new block."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QDialogButtonBox)

from .frameless_shell import FramelessShellMixin


class MakeBlockDialog(FramelessShellMixin, QDialog):
    """Small themed modal: block name + Library + Series.

    Adopts the house frameless chrome (themed ``#shellHeader`` titlebar +
    rounded corners) so it matches the Underlay Manager / import dialogs; the
    form fields inherit the app-wide tokenized QSS.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_frameless_shell(title="Make Block", controls=("close",))
        self.setObjectName("MakeBlockDialog")
        self.setMinimumWidth(340)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._titlebar)          # themed header (objectName shellHeader)

        body = QVBoxLayout()
        body.setContentsMargins(16, 14, 16, 14)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.library_edit = QLineEdit()
        self.series_edit = QLineEdit()
        form.addRow("Name:", self.name_edit)
        form.addRow("Library:", self.library_edit)
        form.addRow("Series:", self.series_edit)
        body.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)
        outer.addLayout(body)

    def values(self) -> tuple[str, str, str]:
        return (self.name_edit.text().strip(), self.library_edit.text().strip(),
                self.series_edit.text().strip())
