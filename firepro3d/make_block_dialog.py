"""MakeBlockDialog — capture name / Library / Series for a new block."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QDialogButtonBox)


class MakeBlockDialog(QDialog):
    """Small modal dialog: block name + Library + Series."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Make Block")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.library_edit = QLineEdit()
        self.series_edit = QLineEdit()
        form.addRow("Name:", self.name_edit)
        form.addRow("Library:", self.library_edit)
        form.addRow("Series:", self.series_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str]:
        return (self.name_edit.text().strip(), self.library_edit.text().strip(),
                self.series_edit.text().strip())
