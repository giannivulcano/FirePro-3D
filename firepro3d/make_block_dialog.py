"""MakeBlockDialog — capture name / Library / Series for a new block."""
from PyQt6.QtWidgets import QFormLayout, QLineEdit

from .house_dialog import HouseDialog


class MakeBlockDialog(HouseDialog):
    """Themed modal on the house frameless shell: header (icon+title) + a form
    body + canonical footer (Cancel-left / Create-right)."""

    def __init__(self, parent=None, theme=None):
        super().__init__(parent, title="Make Block", icon="insert_block_icon.svg",
                         min_width=380, theme=theme)
        self.setObjectName("MakeBlockDialog")
        # Add the form directly to the #dialogBody layout — a bare QWidget
        # wrapper would inherit the app-wide `QWidget { background: ground }`
        # (dark canvas) fill and mismatch the surface body (see ui-design-system.md).
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(14)
        self.name_edit = QLineEdit()
        self.library_edit = QLineEdit()
        self.series_edit = QLineEdit()
        form.addRow("Name", self.name_edit)
        form.addRow("Library", self.library_edit)
        form.addRow("Series", self.series_edit)
        self.body_layout().addLayout(form)
        self.set_footer_buttons(primary=("Create", self.accept), cancel=True)

    def values(self) -> tuple[str, str, str]:
        return (self.name_edit.text().strip(), self.library_edit.text().strip(),
                self.series_edit.text().strip())
