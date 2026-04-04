"""
thermal_radiation_dialog.py
============================
Dialog for configuring thermal radiation analysis parameters.
Follows the same pattern as :mod:`wall_dialog` and :mod:`roof_dialog`.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QComboBox, QDoubleSpinBox, QLabel, QCheckBox, QGroupBox,
)
from PyQt6.QtCore import Qt

from dimension_edit import DimensionEdit


class ThermalRadiationDialog(QDialog):
    """Modal dialog for thermal radiation analysis parameters.

    Usage::

        dlg = ThermalRadiationDialog(
            parent, scale_manager=sm,
            num_emitters=3, num_receivers=2,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            params = dlg.get_params()
    """

    def __init__(self, parent=None, *, scale_manager=None,
                 num_emitters: int = 0, num_receivers: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Thermal Radiation Analysis")
        self.setMinimumWidth(420)
        self._sm = scale_manager
        self._num_emitters = num_emitters
        self._num_receivers = num_receivers
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)

        # --- Summary ---
        summary = QLabel(
            f"<b>{self._num_emitters}</b> emitting surface(s),  "
            f"<b>{self._num_receivers}</b> receiving surface(s)"
        )
        summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(summary)

        # --- Temperature group ---
        temp_group = QGroupBox("Temperature")
        temp_form = QFormLayout()
        temp_group.setLayout(temp_form)

        self._fire_curve_combo = QComboBox()
        self._fire_curve_combo.addItems(["Constant", "CAN/ULC-S101", "ISO 834"])
        self._fire_curve_combo.currentTextChanged.connect(self._on_curve_changed)
        temp_form.addRow("Fire Curve:", self._fire_curve_combo)

        self._emitter_temp = QDoubleSpinBox()
        self._emitter_temp.setRange(0, 2000)
        self._emitter_temp.setValue(800)
        self._emitter_temp.setSuffix(" \u00b0C")
        self._emitter_temp.setDecimals(0)
        temp_form.addRow("Emitter Temperature:", self._emitter_temp)

        self._fire_duration = QDoubleSpinBox()
        self._fire_duration.setRange(1, 480)
        self._fire_duration.setValue(60)
        self._fire_duration.setSuffix(" min")
        self._fire_duration.setDecimals(0)
        self._fire_duration.setEnabled(False)
        temp_form.addRow("Fire Duration:", self._fire_duration)

        self._ambient_temp = QDoubleSpinBox()
        self._ambient_temp.setRange(-50, 60)
        self._ambient_temp.setValue(20)
        self._ambient_temp.setSuffix(" \u00b0C")
        self._ambient_temp.setDecimals(0)
        temp_form.addRow("Ambient Temperature:", self._ambient_temp)

        outer.addWidget(temp_group)

        # --- Surface properties group ---
        surf_group = QGroupBox("Surface Properties")
        surf_form = QFormLayout()
        surf_group.setLayout(surf_form)

        self._emissivity = QDoubleSpinBox()
        self._emissivity.setRange(0.0, 1.0)
        self._emissivity.setValue(1.0)
        self._emissivity.setDecimals(2)
        self._emissivity.setSingleStep(0.05)
        surf_form.addRow("Emissivity:", self._emissivity)

        outer.addWidget(surf_group)

        # --- Analysis settings group ---
        analysis_group = QGroupBox("Analysis Settings")
        analysis_form = QFormLayout()
        analysis_group.setLayout(analysis_form)

        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.1, 200.0)
        self._threshold.setValue(12.5)
        self._threshold.setSuffix(" kW/m\u00b2")
        self._threshold.setDecimals(1)
        analysis_form.addRow("Threshold:", self._threshold)

        self._resolution = DimensionEdit(self._sm, initial_mm=500.0)
        self._resolution.setToolTip("Target mesh element size for analysis")
        analysis_form.addRow("Mesh Resolution:", self._resolution)

        self._cutoff = DimensionEdit(self._sm, initial_mm=50000.0)
        self._cutoff.setToolTip("Maximum distance between surfaces to consider")
        analysis_form.addRow("Distance Cutoff:", self._cutoff)

        self._check_los = QCheckBox("Enabled")
        self._check_los.setChecked(True)
        self._check_los.setToolTip(
            "Check line-of-sight obstructions between surfaces.\n"
            "Disable for faster results when no obstructions exist."
        )
        analysis_form.addRow("Obstruction Check:", self._check_los)

        outer.addWidget(analysis_group)

        # --- Buttons ---
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        outer.addWidget(bbox)

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_curve_changed(self, curve: str):
        is_constant = (curve == "Constant")
        self._emitter_temp.setEnabled(is_constant)
        self._fire_duration.setEnabled(not is_constant)

    # ── Public API ────────────────────────────────────────────────────

    def get_params(self) -> dict:
        """Return parameter dictionary for the radiation solver."""
        curve = self._fire_curve_combo.currentText()
        return {
            "fire_curve": curve,
            "emitter_temp_c": self._emitter_temp.value(),
            "fire_duration_min": self._fire_duration.value(),
            "ambient_c": self._ambient_temp.value(),
            "emissivity": self._emissivity.value(),
            "threshold": self._threshold.value(),
            "resolution_mm": self._resolution.value_mm(),
            "cutoff_mm": self._cutoff.value_mm(),
            "check_los": self._check_los.isChecked(),
        }
