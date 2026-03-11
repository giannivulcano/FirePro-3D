"""
array_dialog.py
===============
Modal dialog for creating linear and polar arrays of selected items.

Returned by :meth:`get_params` as a plain dict ready for
``Model_Space.array_items()``.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QTabWidget, QWidget,
    QLabel, QDoubleSpinBox, QSpinBox, QCheckBox, QDialogButtonBox,
)
from PyQt6.QtCore import Qt


class ArrayDialog(QDialog):
    """
    Two-tab dialog for array creation.

    Linear tab
    ----------
    - Rows  (int ≥ 1)
    - Columns  (int ≥ 1)
    - X Spacing  (float, display units)
    - Y Spacing  (float, display units)

    Polar tab
    ---------
    - Centre X / Y  (float, display units)
    - Count  (int ≥ 2)
    - Total angle  (0 < θ ≤ 360 °)
    - Rotate items checkbox
    """

    def __init__(self, parent=None, scale_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Array")
        self.setMinimumWidth(320)
        self._sm = scale_manager
        self._build_ui()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._linear_tab(), "Linear")
        self._tabs.addTab(self._polar_tab(),  "Polar")
        outer.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _linear_tab(self) -> QWidget:
        w    = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._lin_rows = QSpinBox()
        self._lin_rows.setRange(1, 10_000)
        self._lin_rows.setValue(3)

        self._lin_cols = QSpinBox()
        self._lin_cols.setRange(1, 10_000)
        self._lin_cols.setValue(3)

        _suffix = self._sm.display_unit_suffix() if self._sm else "  units"

        self._lin_xs = QDoubleSpinBox()
        self._lin_xs.setRange(-1_000_000, 1_000_000)
        self._lin_xs.setValue(100)
        self._lin_xs.setDecimals(2)
        self._lin_xs.setSuffix(_suffix)

        self._lin_ys = QDoubleSpinBox()
        self._lin_ys.setRange(-1_000_000, 1_000_000)
        self._lin_ys.setValue(100)
        self._lin_ys.setDecimals(2)
        self._lin_ys.setSuffix(_suffix)

        form.addRow("Rows:",      self._lin_rows)
        form.addRow("Columns:",   self._lin_cols)
        form.addRow("X Spacing:", self._lin_xs)
        form.addRow("Y Spacing:", self._lin_ys)

        note = QLabel(
            "<small>Spacing is measured from the <em>origin</em> of each copy.<br>"
            "Negative spacing arrays in the opposite direction.</small>"
        )
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _polar_tab(self) -> QWidget:
        w    = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._pol_cx = QDoubleSpinBox()
        self._pol_cx.setRange(-1_000_000, 1_000_000)
        self._pol_cx.setValue(0)
        self._pol_cx.setDecimals(2)

        self._pol_cy = QDoubleSpinBox()
        self._pol_cy.setRange(-1_000_000, 1_000_000)
        self._pol_cy.setValue(0)
        self._pol_cy.setDecimals(2)

        self._pol_count = QSpinBox()
        self._pol_count.setRange(2, 10_000)
        self._pol_count.setValue(6)

        self._pol_angle = QDoubleSpinBox()
        self._pol_angle.setRange(0.1, 360.0)
        self._pol_angle.setValue(360.0)
        self._pol_angle.setDecimals(1)
        self._pol_angle.setSuffix("  °")

        self._pol_rotate = QCheckBox("Rotate items to follow arc")
        self._pol_rotate.setChecked(True)

        form.addRow("Centre X:",    self._pol_cx)
        form.addRow("Centre Y:",    self._pol_cy)
        form.addRow("Count:",       self._pol_count)
        form.addRow("Total angle:", self._pol_angle)
        form.addRow("",             self._pol_rotate)
        return w

    # ── Result ────────────────────────────────────────────────────────────────

    def _to_scene(self, val: float) -> float:
        """Convert display-unit value to scene units."""
        if self._sm:
            return self._sm.display_to_scene(val)
        return val

    def get_params(self) -> dict:
        """Return dialog settings as a dict for ``Model_Space.array_items()``."""
        if self._tabs.currentIndex() == 0:
            return {
                "mode":      "linear",
                "rows":      self._lin_rows.value(),
                "cols":      self._lin_cols.value(),
                "x_spacing": self._to_scene(self._lin_xs.value()),
                "y_spacing": self._to_scene(self._lin_ys.value()),
            }
        else:
            return {
                "mode":         "polar",
                "cx":           self._to_scene(self._pol_cx.value()),
                "cy":           self._to_scene(self._pol_cy.value()),
                "count":        self._pol_count.value(),
                "total_angle":  self._pol_angle.value(),
                "rotate_items": self._pol_rotate.isChecked(),
            }
