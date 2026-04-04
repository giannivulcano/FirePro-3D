"""
wall_dialog.py
==============
Dialog for configuring wall properties before or after placement.
Follows the same pattern as :mod:`roof_dialog`.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QComboBox, QLineEdit, QLabel,
)
from PyQt6.QtCore import Qt

from .wall import (
    THICKNESS_PRESETS_IN, DEFAULT_THICKNESS_MM,
    FILL_NONE, FILL_SOLID, FILL_HATCH, FILL_SECTION,
    ALIGN_CENTER, ALIGN_INTERIOR, ALIGN_EXTERIOR,
)
from .dimension_edit import DimensionEdit



class WallDialog(QDialog):
    """Modal dialog for setting wall parameters.

    All dimensions are passed and returned in mm.

    Usage::

        dlg = WallDialog(parent, levels=level_list, scale_manager=sm)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            params = dlg.get_params()
    """

    def __init__(self, parent=None, *, defaults: dict | None = None,
                 levels: list | None = None, scale_manager=None,
                 level_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Wall Properties")
        self.setMinimumWidth(380)
        self._defaults = defaults or {}
        self._level_manager = level_manager
        # Support both new level_manager and legacy levels list
        if self._level_manager is not None:
            self._levels = self._level_manager.levels
        else:
            self._levels = levels or []
        self._sm = scale_manager
        self._build_ui()

    # ── Helpers ───────────────────────────────────────────────────────

    def _fmt_mm(self, mm: float) -> str:
        """Format a length in mm using the ScaleManager."""
        if self._sm:
            return self._sm.format_length(mm)
        return f"{mm:.1f} mm"

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name
        self._name_edit = QLineEdit(self._defaults.get("name", ""))
        form.addRow("Name:", self._name_edit)

        # Thickness (combo shows inches presets; stored as mm internally)
        self._thickness_combo = QComboBox()
        self._thickness_combo.setEditable(True)
        for t in THICKNESS_PRESETS_IN:
            self._thickness_combo.addItem(f"{t} in", float(t) * 25.4)  # store mm
        # Set current from mm default
        cur_thick_mm = self._defaults.get("thickness_mm", DEFAULT_THICKNESS_MM)
        found = False
        for i in range(self._thickness_combo.count()):
            if abs(self._thickness_combo.itemData(i) - cur_thick_mm) < 0.5:
                self._thickness_combo.setCurrentIndex(i)
                found = True
                break
        if not found:
            self._thickness_combo.setEditText(self._fmt_mm(cur_thick_mm))
        form.addRow("Thickness:", self._thickness_combo)

        # Colour
        self._color_edit = QLineEdit(
            self._defaults.get("color", "#cccccc"))
        self._color_edit.setPlaceholderText("#RRGGBB")
        form.addRow("Colour:", self._color_edit)

        # Fill Mode
        self._fill_combo = QComboBox()
        self._fill_combo.addItems([FILL_NONE, FILL_SOLID, FILL_SECTION])
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

        # Base Offset (DimensionEdit — stores mm internally)
        base_off_mm = self._defaults.get("base_offset_mm", 0.0)
        self._base_offset_edit = DimensionEdit(
            self._sm, initial_mm=base_off_mm, parent=self)
        self._base_offset_edit.valueChanged.connect(self._update_height)
        form.addRow("Base Offset:", self._base_offset_edit)

        # Top Level
        self._top_combo = QComboBox()
        default_top = self._defaults.get("top_level", "Level 2")
        self._populate_level_combo(self._top_combo, default_top)
        self._top_combo.currentIndexChanged.connect(self._update_height)
        form.addRow("Top Level:", self._top_combo)

        # Top Offset (DimensionEdit — stores mm internally)
        top_off_mm = self._defaults.get("top_offset_mm", 0.0)
        self._top_offset_edit = DimensionEdit(
            self._sm, initial_mm=top_off_mm, parent=self)
        self._top_offset_edit.valueChanged.connect(self._update_height)
        form.addRow("Top Offset:", self._top_offset_edit)

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
                label = f"{lvl.name}  ({self._fmt_mm(lvl.elevation)})"
                combo.addItem(label, {"name": lvl.name, "elevation_mm": lvl.elevation})
                if lvl.name == default_name:
                    best_idx = i
            combo.setCurrentIndex(best_idx)
        else:
            combo.addItem(f"{default_name}  ({self._fmt_mm(0.0)})",
                          {"name": default_name, "elevation_mm": 0.0})

    def _get_level_elevation_mm(self, combo: QComboBox) -> float:
        """Get the elevation in mm from the currently selected level combo item."""
        data = combo.currentData()
        if data and isinstance(data, dict):
            return data.get("elevation_mm", 0.0)
        return 0.0

    def _get_level_name(self, combo: QComboBox) -> str:
        """Get the level name from the currently selected level combo item."""
        data = combo.currentData()
        if data and isinstance(data, dict):
            return data.get("name", "")
        return ""

    def _compute_height_mm(self) -> float:
        """Compute height in mm from base/top levels and offsets."""
        base_mm = self._get_level_elevation_mm(self._base_combo)
        top_mm = self._get_level_elevation_mm(self._top_combo)
        base_z = base_mm + self._base_offset_edit.value_mm()
        top_z = top_mm + self._top_offset_edit.value_mm()
        return top_z - base_z

    # ── Slots ─────────────────────────────────────────────────────────

    def _update_height(self, *_args):
        h_mm = self._compute_height_mm()
        self._height_label.setText(self._fmt_mm(h_mm))

    # ── Data retrieval ────────────────────────────────────────────────

    def get_params(self) -> dict:
        """Return a dict of wall parameters (all dimensions in mm)."""
        # Parse thickness from combo (item data is already in mm)
        thickness_mm = DEFAULT_THICKNESS_MM
        data = self._thickness_combo.currentData()
        if data is not None:
            thickness_mm = float(data)
        else:
            # Freeform text — try to parse with ScaleManager
            text = self._thickness_combo.currentText().strip()
            if self._sm:
                from .scale_manager import ScaleManager
                parsed = ScaleManager.parse_dimension(text, self._sm.bare_number_unit())
                if parsed is not None:
                    thickness_mm = parsed
                else:
                    # Last resort: strip "in" and parse as inches
                    try:
                        thickness_mm = float(text.replace("in", "").strip()) * 25.4
                    except (ValueError, TypeError):
                        pass
            else:
                try:
                    thickness_mm = float(text.replace("in", "").strip()) * 25.4
                except (ValueError, TypeError):
                    pass

        return {
            "name":           self._name_edit.text().strip(),
            "thickness_mm":   thickness_mm,
            "color":          self._color_edit.text().strip() or "#cccccc",
            "fill_mode":      self._fill_combo.currentText(),
            "alignment":      self._align_combo.currentText(),
            "base_level":     self._get_level_name(self._base_combo),
            "base_offset_mm": self._base_offset_edit.value_mm(),
            "top_level":      self._get_level_name(self._top_combo),
            "top_offset_mm":  self._top_offset_edit.value_mm(),
            "height_mm":      self._compute_height_mm(),
        }
