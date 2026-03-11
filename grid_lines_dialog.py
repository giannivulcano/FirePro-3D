"""
grid_lines_dialog.py
====================
Dialog for placing a regular grid of construction lines on the canvas.

Horizontal lines are infinite construction lines parallel to the X-axis.
Vertical   lines are infinite construction lines parallel to the Y-axis.

The user specifies:
  - Count, first position, and spacing for each direction.

Returned by :meth:`get_params` as a plain dict ready for
``Model_Space.place_grid_lines()``.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox,
    QDoubleSpinBox, QSpinBox, QDialogButtonBox,
    QLabel,
)
from PyQt6.QtCore import Qt


class GridLinesDialog(QDialog):
    """
    Dialog for creating a regular construction-line grid.

    Horizontal group
    ----------------
    - Count    (int ≥ 0)
    - First Y  (float, scene Y-coordinate of the topmost H-line)
    - Spacing  (float, scene units between each H-line, may be negative)

    Vertical group
    --------------
    - Count    (int ≥ 0)
    - First X  (float, scene X-coordinate of the leftmost V-line)
    - Spacing  (float, scene units between each V-line, may be negative)
    """

    def __init__(self, parent=None, scale_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Place Grid Lines")
        self.setMinimumWidth(300)
        self._sm = scale_manager
        self._build_ui()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        note = QLabel(
            "<small>Grid lines are placed as <em>construction lines</em> "
            "and can be deleted individually.  They are saved with the file.</small>"
        )
        note.setWordWrap(True)
        outer.addWidget(note)

        _suffix = self._sm.display_unit_suffix() if self._sm else "  units"

        # ── Horizontal lines ─────────────────────────────────────────────
        h_group = QGroupBox("Horizontal Lines  (parallel to X-axis)")
        h_form  = QFormLayout(h_group)
        h_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._h_count = QSpinBox()
        self._h_count.setRange(0, 1_000)
        self._h_count.setValue(5)

        self._h_first = QDoubleSpinBox()
        self._h_first.setRange(-1_000_000, 1_000_000)
        self._h_first.setValue(0)
        self._h_first.setDecimals(2)
        self._h_first.setSuffix(_suffix)

        self._h_spacing = QDoubleSpinBox()
        self._h_spacing.setRange(-1_000_000, 1_000_000)
        self._h_spacing.setValue(100)
        self._h_spacing.setDecimals(2)
        self._h_spacing.setSuffix(_suffix)

        h_form.addRow("Count:",    self._h_count)
        h_form.addRow("First Y:",  self._h_first)
        h_form.addRow("Spacing:",  self._h_spacing)
        outer.addWidget(h_group)

        # ── Vertical lines ───────────────────────────────────────────────
        v_group = QGroupBox("Vertical Lines  (parallel to Y-axis)")
        v_form  = QFormLayout(v_group)
        v_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._v_count = QSpinBox()
        self._v_count.setRange(0, 1_000)
        self._v_count.setValue(5)

        self._v_first = QDoubleSpinBox()
        self._v_first.setRange(-1_000_000, 1_000_000)
        self._v_first.setValue(0)
        self._v_first.setDecimals(2)
        self._v_first.setSuffix(_suffix)

        self._v_spacing = QDoubleSpinBox()
        self._v_spacing.setRange(-1_000_000, 1_000_000)
        self._v_spacing.setValue(100)
        self._v_spacing.setDecimals(2)
        self._v_spacing.setSuffix(_suffix)

        v_form.addRow("Count:",    self._v_count)
        v_form.addRow("First X:",  self._v_first)
        v_form.addRow("Spacing:",  self._v_spacing)
        outer.addWidget(v_group)

        # ── Buttons ──────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ── Result ────────────────────────────────────────────────────────────────

    def _to_scene(self, val: float) -> float:
        """Convert display-unit value to scene units."""
        if self._sm:
            return self._sm.display_to_scene(val)
        return val

    def get_params(self) -> dict:
        """Return dialog settings as a dict for ``Model_Space.place_grid_lines()``."""
        return {
            "h_count":    self._h_count.value(),
            "h_first":    self._to_scene(self._h_first.value()),
            "h_spacing":  self._to_scene(self._h_spacing.value()),
            "v_count":    self._v_count.value(),
            "v_first":    self._to_scene(self._v_first.value()),
            "v_spacing":  self._to_scene(self._v_spacing.value()),
        }
