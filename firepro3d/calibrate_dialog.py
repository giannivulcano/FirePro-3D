"""
Calibration dialog — shown after the user picks two scene points.
Asks for the real-world distance and unit, then calibrates the ScaleManager.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QComboBox, QDialogButtonBox
)


class CalibrateDialog(QDialog):
    """Ask user for the real-world distance between two picked points."""

    UNITS = [
        ("Feet",        "ft"),
        ("Inches",      "in"),
        ("Meters",      "m"),
        ("Millimeters", "mm"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Scale — Enter Distance")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        # Instruction
        layout.addWidget(QLabel("Enter the real-world distance between the two points you picked:"))

        # Distance + unit row
        row = QHBoxLayout()

        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(0.001, 999999.0)
        self.distance_spin.setDecimals(4)
        self.distance_spin.setValue(10.0)
        self.distance_spin.setSuffix("")
        row.addWidget(self.distance_spin)

        self.unit_combo = QComboBox()
        for label, _ in self.UNITS:
            self.unit_combo.addItem(label)
        self.unit_combo.setCurrentIndex(0)  # default Feet
        row.addWidget(self.unit_combo)

        layout.addLayout(row)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_distance(self) -> float:
        return self.distance_spin.value()

    def get_unit_code(self) -> str:
        """Return the short unit code: 'ft', 'in', 'm', 'mm'."""
        idx = self.unit_combo.currentIndex()
        return self.UNITS[idx][1]

