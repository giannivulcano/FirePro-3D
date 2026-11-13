"""Replace-and-delete prompt for an in-use Custom line weight (LW-DC-5)."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout,
)

from .paper_display import LineWeightDef, _nearest_def


class WeightReplaceDialog(QDialog):
    """Ask which weight replaces a deleted one that references still name.

    The combo lists every candidate sorted by width (item text
    ``"<name>  <w:.2f>"``, userData = the weight name), preselecting the
    nearest width (a tie goes to the thinner, as MW-5).

    Args:
        name: The weight being deleted.
        width_mm: Its width in millimetres.
        count: How many references use it.
        candidates: Every other weight (the replacement choices).
        parent: Owning widget (the Display Manager, for its stylesheet).
    """

    def __init__(self, name: str, width_mm: float, count: int,
                 candidates: list[LineWeightDef], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Replace Line Weight")
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        noun = "reference" if count == 1 else "references"
        layout.addWidget(QLabel(
            f"‘{name}’ ({width_mm:.2f} mm) is used by {count} "
            f"{noun}. Replace with:"))
        self._combo = QComboBox()
        for d in sorted(candidates, key=lambda d: d.width_mm):
            self._combo.addItem(f"{d.name}  {d.width_mm:.2f}", d.name)
        near = _nearest_def(width_mm, candidates)
        if near is not None:
            self._combo.setCurrentIndex(self._combo.findData(near.name))
        layout.addWidget(self._combo)
        buttons = QDialogButtonBox()
        ok = buttons.addButton("Replace && Delete",
                               QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen(self) -> str:
        """The chosen replacement's weight name (the combo's userData)."""
        return self._combo.currentData() or ""
