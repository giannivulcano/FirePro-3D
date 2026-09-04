"""MakeBlockDialog — capture name / Library / Series for a new block."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QDialogButtonBox, QFrame)

from .frameless_shell import FramelessShellMixin
from .theme import build_underlay_manager_qss, detect


class MakeBlockDialog(FramelessShellMixin, QDialog):
    """Themed modal built on the house frameless shell (matches the Underlay
    Manager): tokenized ``#shellHeader`` titlebar + a darker ``#dialogBody``
    content rail holding the name / Library / Series fields.
    """

    def __init__(self, parent=None, theme=None):
        super().__init__(parent)
        theme = theme or detect()
        self.init_frameless_shell(title="Make Block", controls=("close",))
        self.setObjectName("MakeBlockDialog")
        self.setStyleSheet(build_underlay_manager_qss(theme))
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._titlebar)                  # tokenized header rail

        body = QFrame(objectName="dialogBody")          # darker content rail
        col = QVBoxLayout(body)
        col.setContentsMargins(18, 16, 18, 16)
        col.setSpacing(16)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(12)
        self.name_edit = QLineEdit()
        self.library_edit = QLineEdit()
        self.series_edit = QLineEdit()
        form.addRow("Name", self.name_edit)
        form.addRow("Library", self.library_edit)
        form.addRow("Series", self.series_edit)
        col.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        col.addWidget(buttons)
        root.addWidget(body)

    def values(self) -> tuple[str, str, str]:
        return (self.name_edit.text().strip(), self.library_edit.text().strip(),
                self.series_edit.text().strip())
