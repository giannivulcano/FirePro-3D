"""
fs_visibility_dialog.py
=======================
Fire Suppression System visibility / appearance dialog.

Allows the user to set colour and scale factor for each fire-suppression
component type (Pipe, Sprinkler, Water Supply, Fitting, Node).
Settings are persisted via QSettings.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QPushButton, QDoubleSpinBox,
    QDialogButtonBox, QColorDialog, QLabel, QHBoxLayout,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QSettings
import theme as th


# Default colours per component type
_DEFAULTS = {
    "Pipe":         {"color": "#4488ff", "scale": 1.0},
    "Sprinkler":    {"color": "#ff4444", "scale": 1.0},
    "Water Supply": {"color": "#00cccc", "scale": 1.0},
    "Fitting":      {"color": "#44cc44", "scale": 1.0},
    "Node":         {"color": "#888888", "scale": 1.0},
}


class FSVisibilityDialog(QDialog):
    """Modal dialog for fire-suppression component appearance settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fire Suppression Visibility")
        self.setMinimumWidth(340)
        self._settings = QSettings("GV", "FirePro3D")
        self._rows: dict[str, dict] = {}
        self._build_ui()

    def _build_ui(self):
        _t = th.detect()
        outer = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        for name, defaults in _DEFAULTS.items():
            saved_color = self._settings.value(
                f"fs_visibility/{name}/color", defaults["color"])
            saved_scale = float(self._settings.value(
                f"fs_visibility/{name}/scale", defaults["scale"]))

            row_layout = QHBoxLayout()

            # Colour button
            btn = QPushButton()
            btn.setFixedSize(50, 24)
            btn.setProperty("_color", saved_color)
            btn.setStyleSheet(
                f"background: {saved_color}; "
                f"border: 1px solid {_t.border_subtle}; border-radius: 2px;")
            btn.clicked.connect(lambda _, n=name, b=btn: self._pick(n, b))
            row_layout.addWidget(btn)

            # Scale spinbox
            spin = QDoubleSpinBox()
            spin.setRange(0.1, 10.0)
            spin.setSingleStep(0.1)
            spin.setDecimals(1)
            spin.setValue(saved_scale)
            spin.setSuffix("x")
            row_layout.addWidget(spin)

            self._rows[name] = {"btn": btn, "spin": spin}
            form.addRow(QLabel(name), row_layout)

        outer.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _pick(self, name: str, btn: QPushButton):
        _t = th.detect()
        cur = QColor(btn.property("_color"))
        color = QColorDialog.getColor(cur, self, f"{name} colour")
        if color.isValid():
            btn.setProperty("_color", color.name())
            btn.setStyleSheet(
                f"background: {color.name()}; "
                f"border: 1px solid {_t.border_subtle}; border-radius: 2px;")

    def get_settings(self) -> dict[str, dict]:
        """Return current dialog values as {name: {color, scale}}."""
        result = {}
        for name, widgets in self._rows.items():
            result[name] = {
                "color": widgets["btn"].property("_color"),
                "scale": widgets["spin"].value(),
            }
        return result

    def save_settings(self):
        """Persist current values to QSettings."""
        for name, vals in self.get_settings().items():
            self._settings.setValue(f"fs_visibility/{name}/color", vals["color"])
            self._settings.setValue(f"fs_visibility/{name}/scale", vals["scale"])
