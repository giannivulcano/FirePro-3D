"""
view_range_dialog.py
====================
Dialog for editing the view-range (cut plane) settings of a plan view.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox, QPushButton,
    QLabel, QGroupBox, QComboBox, QHBoxLayout, QWidget,
)
from PyQt6.QtCore import Qt

from .dimension_edit import DimensionEdit
from .level_manager import PlanView, PlanViewManager, LevelManager


class ViewRangeDialog(QDialog):
    """Edit *view_height* (cut plane) and *view_depth* for a PlanView."""

    def __init__(self, plan_view: PlanView, level_manager: LevelManager,
                 plan_view_manager: PlanViewManager, scale_manager,
                 parent=None, scene=None):
        super().__init__(parent)
        self.setWindowTitle(f"View Range \u2014 {plan_view.name}")
        self.setMinimumWidth(420)
        self._pv = plan_view
        self._lm = level_manager
        self._pvm = plan_view_manager
        self._sm = scale_manager
        self._scene = scene  # used to auto-derive the default upper bound
        self._updating = False  # guard against re-entrant updates
        # Override intent: True once the user manually edits the cut-plane
        # height (pin it), False after Reset-to-Defaults (opt into dynamic).
        # Seeded from the PlanView's current state.
        self._explicit = bool(getattr(plan_view, "view_height_explicit", True))

        layout = QVBoxLayout(self)

        # Info label
        lvl = self._lm.get(plan_view.level_name)
        if lvl and scale_manager:
            elev_str = scale_manager.format_length(lvl.elevation)
        elif lvl:
            elev_str = f"{lvl.elevation:.1f} mm"
        else:
            elev_str = "?"
        info = QLabel(f"Level: <b>{plan_view.level_name}</b>  "
                      f"(elevation {elev_str})")
        layout.addWidget(info)

        # ── Cut Plane Height ──────────────────────────────────────────
        height_group = QGroupBox("Cut Plane Height")
        height_form = QFormLayout(height_group)

        self._height_edit = DimensionEdit(scale_manager,
                                          initial_mm=plan_view.view_height)
        height_form.addRow("Absolute:", self._height_edit)

        self._height_level, self._height_offset = self._make_level_offset_row(
            height_form, plan_view.view_height)

        layout.addWidget(height_group)

        # ── View Depth ────────────────────────────────────────────────
        depth_group = QGroupBox("View Depth")
        depth_form = QFormLayout(depth_group)

        self._depth_edit = DimensionEdit(scale_manager,
                                         initial_mm=plan_view.view_depth)
        depth_form.addRow("Absolute:", self._depth_edit)

        self._depth_level, self._depth_offset = self._make_level_offset_row(
            depth_form, plan_view.view_depth)

        layout.addWidget(depth_group)

        # Wire signals: level/offset → absolute, absolute → level/offset
        self._height_level.currentTextChanged.connect(
            lambda _: self._ref_to_absolute("height"))
        self._height_offset.valueChanged.connect(
            lambda _: self._ref_to_absolute("height"))
        self._height_edit.valueChanged.connect(
            lambda mm: self._absolute_to_ref("height", mm))

        self._depth_level.currentTextChanged.connect(
            lambda _: self._ref_to_absolute("depth"))
        self._depth_offset.valueChanged.connect(
            lambda _: self._ref_to_absolute("depth"))
        self._depth_edit.valueChanged.connect(
            lambda mm: self._absolute_to_ref("depth", mm))

        # Reset button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        layout.addWidget(reset_btn)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _make_level_offset_row(self, form: QFormLayout,
                                abs_mm: float) -> tuple[QComboBox, DimensionEdit]:
        """Add a Reference Level + Offset row and return the widgets."""
        combo = QComboBox()
        for lv in self._lm.levels:
            combo.addItem(lv.name)

        # Find the closest level and compute offset
        best_level, offset = self._find_best_ref(abs_mm)
        combo.setCurrentText(best_level)

        offset_edit = DimensionEdit(self._sm, initial_mm=offset)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(combo, 1)
        row.addWidget(QLabel("+"))
        row.addWidget(offset_edit, 1)
        container = QWidget()
        container.setLayout(row)
        form.addRow("Ref Level + Offset:", container)

        return combo, offset_edit

    def _find_best_ref(self, abs_mm: float) -> tuple[str, float]:
        """Find the level whose elevation is closest to *abs_mm* and return
        (level_name, offset_mm) such that level.elevation + offset = abs_mm."""
        best_name = self._pv.level_name
        best_dist = float("inf")
        for lv in self._lm.levels:
            dist = abs(lv.elevation - abs_mm)
            if dist < best_dist:
                best_dist = dist
                best_name = lv.name
        lvl = self._lm.get(best_name)
        offset = abs_mm - lvl.elevation if lvl else abs_mm
        return best_name, offset

    def _ref_to_absolute(self, which: str):
        """Level + offset changed → update the absolute DimensionEdit."""
        if self._updating:
            return
        if which == "height":
            # User-driven height edit → pin as explicit override.
            self._explicit = True
        self._updating = True
        try:
            if which == "height":
                combo, offset_edit, abs_edit = (
                    self._height_level, self._height_offset, self._height_edit)
            else:
                combo, offset_edit, abs_edit = (
                    self._depth_level, self._depth_offset, self._depth_edit)
            lvl = self._lm.get(combo.currentText())
            elev = lvl.elevation if lvl else 0.0
            abs_edit.set_value_mm(elev + offset_edit.value_mm())
        finally:
            self._updating = False

    def _absolute_to_ref(self, which: str, abs_mm: float):
        """Absolute DimensionEdit changed → update level + offset."""
        if self._updating:
            return
        if which == "height":
            # User-driven height edit → pin as explicit override.
            self._explicit = True
        self._updating = True
        try:
            if which == "height":
                combo, offset_edit = self._height_level, self._height_offset
            else:
                combo, offset_edit = self._depth_level, self._depth_offset
            # Keep the currently selected reference level; just update offset
            lvl = self._lm.get(combo.currentText())
            elev = lvl.elevation if lvl else 0.0
            offset_edit.set_value_mm(abs_mm - elev)
        finally:
            self._updating = False

    def _reset_defaults(self):
        """Recompute smart defaults and opt back into the dynamic upper bound.

        Resetting clears the explicit-override flag so the plan's upper bound
        auto-derives from the actual floor above on the next activation. The
        shown default prefers ``LevelManager.compute_view_height`` (the same
        auto value used at activation), falling back to the old spacing formula
        when it can't be computed (e.g. no scene / unknown level)."""
        lvl = self._lm.get(self._pv.level_name)
        if lvl is None:
            return
        elev = lvl.elevation

        # Opt back into dynamic upper bound. The commit path reads
        # is_explicit() and writes this onto the shared PlanView on Accept.
        self._explicit = False

        view_height = None
        if self._scene is not None:
            view_height = self._lm.compute_view_height(
                self._scene, self._pv.level_name)
        # No scene (or uncomputable) → the floor-agnostic fallback.
        # NOTE: mirrors LevelManager.fallback_view_height (one home).
        if view_height is None:
            view_height = self._lm.fallback_view_height(self._pv.level_name)
        if view_height is None:
            view_height = elev + lvl.view_top

        view_depth = elev + lvl.view_bottom

        self._updating = True
        try:
            self._height_edit.set_value_mm(view_height)
            self._depth_edit.set_value_mm(view_depth)
            # Update ref level/offset to match
            name, off = self._find_best_ref(view_height)
            self._height_level.setCurrentText(name)
            self._height_offset.set_value_mm(off)
            name, off = self._find_best_ref(view_depth)
            self._depth_level.setCurrentText(name)
            self._depth_offset.set_value_mm(off)
        finally:
            self._updating = False

    def get_values(self) -> tuple[float, float]:
        """Return (view_height, view_depth) in mm."""
        return (self._height_edit.value_mm(), self._depth_edit.value_mm())

    def is_explicit(self) -> bool:
        """Whether the user pinned an explicit cut-plane height.

        True if the height field was manually edited, False after
        Reset-to-Defaults (opt into the dynamic auto-derived upper bound).
        Commit paths write this onto the shared PlanView on Accept.
        """
        return self._explicit
