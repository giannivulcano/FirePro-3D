"""MakeBlockDialog — capture name / Library / Series for a new block."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QPushButton, QFrame)

from .frameless_shell import FramelessShellMixin
from .theme import build_underlay_manager_qss, detect


class MakeBlockDialog(FramelessShellMixin, QDialog):
    """Themed modal built on the house frameless shell (matches the Underlay
    Manager): tokenized ``#shellHeader`` titlebar with icon, a ``#dialogBody``
    content rail for the fields, and a ``#footerBar`` rail for the buttons.
    """

    def __init__(self, parent=None, theme=None):
        super().__init__(parent)
        theme = theme or detect()
        self.init_frameless_shell(title="Make Block", controls=("close",),
                                  icon="insert_block_icon.svg")
        self.setObjectName("MakeBlockDialog")
        self.setStyleSheet(build_underlay_manager_qss(theme))
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._titlebar)                  # tokenized header rail

        body = QFrame(objectName="dialogBody")          # content rail
        col = QVBoxLayout(body)
        col.setContentsMargins(20, 18, 20, 18)
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(14)
        self.name_edit = QLineEdit()
        self.library_edit = QLineEdit()
        self.series_edit = QLineEdit()
        form.addRow("Name", self.name_edit)
        form.addRow("Library", self.library_edit)
        form.addRow("Series", self.series_edit)
        col.addLayout(form)
        root.addWidget(body)

        footer = QFrame(objectName="footerBar")         # button rail
        fb = QHBoxLayout(footer)
        fb.setContentsMargins(16, 10, 16, 10)
        fb.setSpacing(8)
        fb.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Create")
        ok.setProperty("variant", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        fb.addWidget(cancel)
        fb.addWidget(ok)
        root.addWidget(footer)

    def values(self) -> tuple[str, str, str]:
        return (self.name_edit.text().strip(), self.library_edit.text().strip(),
                self.series_edit.text().strip())
