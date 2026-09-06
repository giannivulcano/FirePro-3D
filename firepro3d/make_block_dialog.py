"""MakeBlockDialog — capture name / Library / Series for a new block."""
from PyQt6.QtWidgets import QFormLayout, QLineEdit, QWidget, QVBoxLayout

from .house_dialog import HouseDialog


class MakeBlockDialog(HouseDialog):
    """Themed modal on the house frameless shell: header (icon+title) + a form
    body + canonical footer (Cancel-left / Create-right)."""

    def __init__(self, parent=None, theme=None):
        super().__init__(parent, title="Make Block", icon="insert_block_icon.svg",
                         min_width=380, theme=theme)
        self.setObjectName("MakeBlockDialog")
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 0, 0)
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
        self.set_body(body)
        self.set_footer_buttons(primary=("Create", self.accept), cancel=True)

    def values(self) -> tuple[str, str, str]:
        return (self.name_edit.text().strip(), self.library_edit.text().strip(),
                self.series_edit.text().strip())
