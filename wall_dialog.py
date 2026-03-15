"""
wall_dialog.py
==============
Dialog for configuring wall properties before or after placement.
Follows the same pattern as :mod:`roof_dialog`.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QComboBox, QDoubleSpinBox, QLineEdit, QLabel,
)
from PyQt6.QtCore import Qt

from wall import (
    THICKNESS_PRESETS_IN, DEFAULT_THICKNESS_IN,
    FILL_NONE, FILL_SOLID, FILL_HATCH,
    ALIGN_CENTER, ALIGN_INTERIOR, ALIGN_EXTERIOR,
)


class WallDialog(QDialog):
    """Modal dialog for setting wall parameters.

    Usage::

        dlg = WallDialog(parent, levels=level_list)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            params = dlg.get_params()
    """

    def __init__(self, parent=None, *, defaults: dict | None = None,
                 levels: list | None = None):
        super().__init__(parent)
        self.setWindowTitle("Wall Properties")
        self.setMinimumWidth(380)
        self._defaults = defaults or {}
        self._levels = levels or []
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name
        self._name_edit = QLineEdit(self._defaults.get("name", ""))
        form.addRow("Name:", self._name_edit)

        # Thickness
        self._thickness_combo = QComboBox()
        self._thickness_combo.setEditable(True)
        for t in THICKNESS_PRESETS_IN:
            self._thickness_combo.addItem(f"{t} in", float(t))
        # Set current
        cur_thick = self._defaults.get("thickness_in", DEFAULT_THICKNESS_IN)
        found = False
        for i in range(self._thickness_combo.count()):
            if abs(self._thickness_combo.itemData(i) - cur_thick) < 0.01:
                self._thickness_combo.setCurrentIndex(i)
                found = True
                break
        if not found:
            self._thickness_combo.setEditText(f"{cur_thick} in")
        form.addRow("Thickness:", self._thickness_combo)

        # Colour
        self._color_edit = QLineEdit(
            self._defaults.get("color", "#cccccc"))
        self._color_edit.setPlaceholderText("#RRGGBB")
        form.addRow("Colour:", self._color_edit)

        # Fill Mode
        self._fill_combo = QComboBox()
        self._fill_combo.addItems([FILL_NONE, FILL_SOLID, FILL_HATCH])
        cur_fill = self._defaults.get("fill_mode", FILL_NONE)
        idx = self._fill_combo.findText(cur_fill)
        if idx >= 0:
            self._fill_combo.setCurrentIndex(idx)
        form.addRow("Fill Mode:", self._fill_combo)

        # Alignment
        self._align_combo = QComboBox()
        self._align_combo.addItems([ALIGN_CENTER, ALIGN_INTERIOR, ALIGN_EXTERIOR])
        cur_align = self._defaults.get("alignment", ALIGN_CENTER)
        idx = self._align_combo.findText(cur_align)
        if idx >= 0:
            self._align_combo.setCurrentIndex(idx)
        form.addRow("Alignment:", self._align_combo)

        # ── Level dropdowns ──────────────────────────────────────────

        # Base Level
        self._base_combo = QComboBox()
        default_base = self._defaults.get("base_level", "Level 1")
        self._populate_level_combo(self._base_combo, default_base)
        self._base_combo.currentIndexChanged.connect(self._update_height)
        form.addRow("Base Level:", self._base_combo)

        # Base Offset
        self._base_offset_spin = QDoubleSpinBox()
        self._base_offset_spin.setRange(-1000.0, 1000.0)
        self._base_offset_spin.setDecimals(2)
        self._base_offset_spin.setSuffix(" ft")
        self._base_offset_spin.setValue(
            self._defaults.get("base_offset_ft", 0.0))
        self._base_offset_spin.valueChanged.connect(self._update_height)
        form.addRow("Base Offset:", self._base_offset_spin)

        # Top Level
        self._top_combo = QComboBox()
        default_top = self._defaults.get("top_level", "Level 2")
        self._populate_level_combo(self._top_combo, default_top)
        self._top_combo.currentIndexChanged.connect(self._update_height)
        form.addRow("Top Level:", self._top_combo)

        # Top Offset
        self._top_offset_spin = QDoubleSpinBox()
        self._top_offset_spin.setRange(-1000.0, 1000.0)
        self._top_offset_spin.setDecimals(2)
        self._top_offset_spin.setSuffix(" ft")
        self._top_offset_spin.setValue(
            self._defaults.get("top_offset_ft", 0.0))
        self._top_offset_spin.valueChanged.connect(self._update_height)
        form.addRow("Top Offset:", self._top_offset_spin)

        # Height (read-only, computed)
        self._height_label = QLabel()
        self._height_label.setStyleSheet("color: grey; font-size: 11px;")
        form.addRow("Height:", self._height_label)

        outer.addLayout(form)

        # Trigger initial height calculation
        self._update_height()

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ── Helpers ───────────────────────────────────────────────────────

    def _populate_level_combo(self, combo: QComboBox, default_name: str):
        """Populate a level combo from the level list."""
        best_idx = 0
        if self._levels:
            for i, lvl in enumerate(self._levels):
                label = f"{lvl.name}  ({lvl.elevation:.1f} ft)"
                combo.addItem(label, {"name": lvl.name, "elevation": lvl.elevation})
                if lvl.name == default_name:
                    best_idx = i
            combo.setCurrentIndex(best_idx)
        else:
            combo.addItem(f"{default_name}  (0.0 ft)",
                          {"name": default_name, "elevation": 0.0})

    def _get_level_elevation(self, combo: QComboBox) -> float:
        """Get the elevation from the currently selected level combo item."""
        data = combo.currentData()
        if data and isinstance(data, dict):
            return data.get("elevation", 0.0)
        return 0.0

    def _get_level_name(self, combo: QComboBox) -> str:
        """Get the level name from the currently selected level combo item."""
        data = combo.currentData()
        if data and isinstance(data, dict):
            return data.get("name", "")
        return ""

    def _compute_height(self) -> float:
        """Compute height from base/top levels and offsets."""
        base_elev = self._get_level_elevation(self._base_combo)
        top_elev = self._get_level_elevation(self._top_combo)
        base_z = base_elev + self._base_offset_spin.value()
        top_z = top_elev + self._top_offset_spin.value()
        return top_z - base_z

    # ── Slots ─────────────────────────────────────────────────────────

    def _update_height(self, *_args):
        h = self._compute_height()
        self._height_label.setText(f"{h:.2f} ft")

    # ── Data retrieval ────────────────────────────────────────────────

    def get_params(self) -> dict:
        """Return a dict of wall parameters."""
        # Parse thickness from combo (may be edited freeform)
        thickness = DEFAULT_THICKNESS_IN
        data = self._thickness_combo.currentData()
        if data is not None:
            thickness = float(data)
        else:
            text = self._thickness_combo.currentText().replace("in", "").strip()
            try:
                thickness = float(text)
            except (ValueError, TypeError):
                pass

        return {
            "name":           self._name_edit.text().strip(),
            "thickness_in":   thickness,
            "color":          self._color_edit.text().strip() or "#cccccc",
            "fill_mode":      self._fill_combo.currentText(),
            "alignment":      self._align_combo.currentText(),
            "base_level":     self._get_level_name(self._base_combo),
            "base_offset_ft": self._base_offset_spin.value(),
            "top_level":      self._get_level_name(self._top_combo),
            "top_offset_ft":  self._top_offset_spin.value(),
            "height_ft":      self._compute_height(),
        }
