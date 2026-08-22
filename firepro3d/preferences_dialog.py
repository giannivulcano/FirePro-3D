"""Unified Preferences dialog — tabbed QDialog with snapshot/revert panes.

New settings live here first (design-of-record: 2026-08-22-ribbon-overhaul).
Panes own their own persistence target (QSettings or the project dict).
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QLabel, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)


class SettingsPane(QWidget):
    """Base pane. Subclasses implement load/apply/revert and build their UI."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title

    def load(self):   ...   # snapshot current state + populate widgets
    def apply(self):  ...   # commit staged values to the persistence target
    def revert(self): ...   # restore the snapshot


_SNAP_TYPES: list[tuple[str, str]] = [
    ("Endpoint",      "snap_endpoint"),
    ("Midpoint",      "snap_midpoint"),
    ("Intersection",  "snap_intersection"),
    ("Center",        "snap_center"),
    ("Quadrant",      "snap_quadrant"),
    ("Nearest",       "snap_nearest"),
    ("Perpendicular", "snap_perpendicular"),
    ("Tangent",       "snap_tangent"),
]

_QSETTINGS_ORG  = "GV"
_QSETTINGS_APP  = "FirePro3D"


class SnappingPane(SettingsPane):
    """Preferences pane for OSNAP / snap-tolerance / grid / inference settings.

    Ports the two existing snap dialogs in ``main.py``:
    - ``_open_snap_tolerance_dialog`` — snap radius, grip radius, 8 snap-type
      checkboxes, alignment-guides toggle.
    - ``_open_snap_settings`` — grid spacing (mm), angle-snap increment.

    This pane has **no reference to the scene or view**; it reads and writes:
    - ``snap_engine.SNAP_TOLERANCE_PX`` (module-level int)
    - QSettings keys for everything that requires a live scene/view object
      (grip tolerance, per-type flags, grid size, angle, inference).
      MainWindow.restore_settings reads those back into the scene on startup.
    """

    def __init__(self, parent=None):
        super().__init__("Snapping", parent)
        self._snapshot: dict = {}
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        from .dimension_edit import DimensionEdit

        outer = QVBoxLayout(self)

        tabs = QTabWidget()
        outer.addWidget(tabs)

        # ── Tab 1: OSNAP ─────────────────────────────────────────────────────
        osnap_tab = QWidget()
        osnap_layout = QVBoxLayout(osnap_tab)

        # Tolerance group
        tol_group = QGroupBox("Tolerance")
        tol_form = QFormLayout(tol_group)

        self._tol_spin = QSpinBox()
        self._tol_spin.setRange(5, 1000)
        self._tol_spin.setSingleStep(5)
        self._tol_spin.setSuffix(" px")
        tol_form.addRow("Snap radius:", self._tol_spin)

        self._grip_spin = QSpinBox()
        self._grip_spin.setRange(100, 1000)
        self._grip_spin.setSingleStep(50)
        self._grip_spin.setSuffix(" px")
        tol_form.addRow("Grip handle radius:", self._grip_spin)

        osnap_layout.addWidget(tol_group)

        # Snap types group
        types_group = QGroupBox("Snap Types")
        types_layout = QVBoxLayout(types_group)
        self._snap_cbs: dict[str, QCheckBox] = {}
        for label, attr in _SNAP_TYPES:
            cb = QCheckBox(label)
            types_layout.addWidget(cb)
            self._snap_cbs[attr] = cb
        osnap_layout.addWidget(types_group)

        tabs.addTab(osnap_tab, "OSNAP")

        # ── Tab 2: Grid / Angle ──────────────────────────────────────────────
        grid_tab = QWidget()
        grid_form = QFormLayout(grid_tab)

        self._grid_edit = DimensionEdit(None, initial_mm=10.0)
        grid_form.addRow("Grid spacing:", self._grid_edit)

        self._angle_spin = QSpinBox()
        self._angle_spin.setRange(1, 90)
        self._angle_spin.setSuffix("°")
        grid_form.addRow("Angle snap:", self._angle_spin)

        tabs.addTab(grid_tab, "Grid / Angle")

        # ── Tab 3: Inference ─────────────────────────────────────────────────
        inf_tab = QWidget()
        inf_layout = QVBoxLayout(inf_tab)

        self._align_cb = QCheckBox("Alignment Guides")
        self._align_cb.setObjectName("inference_alignment_guides")
        inf_layout.addWidget(self._align_cb)

        coming_soon = QGroupBox("Dynamic Input · Equal Spacing")
        coming_soon.setEnabled(False)
        cs_layout = QVBoxLayout(coming_soon)
        cs_label = QLabel("Coming soon")
        cs_label.setStyleSheet("color: #888;")
        cs_layout.addWidget(cs_label)
        inf_layout.addWidget(coming_soon)
        inf_layout.addStretch()

        tabs.addTab(inf_tab, "Inference")

    # ── SettingsPane protocol ─────────────────────────────────────────────────

    def load(self) -> None:
        """Snapshot current engine/QSettings state and populate widgets."""
        from firepro3d import snap_engine

        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)

        tol_px = snap_engine.SNAP_TOLERANCE_PX
        grip_px = s.value("snap/grip_tolerance_px", 200, type=int)
        grid_mm = s.value("snap/grid_size", 10.0, type=float)
        angle_deg = s.value("snap/angle_deg", 45, type=int)
        inference = s.value("inference/alignment_guides", True, type=bool)

        snap_flags: dict[str, bool] = {}
        for _, attr in _SNAP_TYPES:
            val = s.value(f"snap/{attr}", True)
            if isinstance(val, str):
                val = val.lower() not in ("false", "0")
            snap_flags[attr] = bool(val)

        # Build snapshot before touching widgets
        self._snapshot = {
            "tol_px":    tol_px,
            "grip_px":   grip_px,
            "grid_mm":   grid_mm,
            "angle_deg": angle_deg,
            "inference": inference,
            **snap_flags,
        }

        # Populate widgets
        self._tol_spin.setValue(tol_px)
        self._grip_spin.setValue(grip_px)
        self._grid_edit.set_value_mm(grid_mm)
        self._angle_spin.setValue(int(angle_deg))
        self._align_cb.setChecked(inference)
        for attr, cb in self._snap_cbs.items():
            cb.setChecked(snap_flags[attr])

    def apply(self) -> None:
        """Write widget values to snap_engine and persist to QSettings."""
        from firepro3d import snap_engine

        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)

        # Module-level tolerance — write live
        snap_engine.SNAP_TOLERANCE_PX = self._tol_spin.value()
        s.setValue("snap/tolerance_px", snap_engine.SNAP_TOLERANCE_PX)

        # Grip tolerance — QSettings only (scene owns the live value)
        s.setValue("snap/grip_tolerance_px", self._grip_spin.value())

        # Per-type flags — QSettings only (scene._snap_engine owns the live values)
        for attr, cb in self._snap_cbs.items():
            s.setValue(f"snap/{attr}", cb.isChecked())

        # Grid / angle — QSettings only (view/scene own the live values)
        s.setValue("snap/grid_size", self._grid_edit.value_mm())
        s.setValue("snap/angle_deg", self._angle_spin.value())

        # Inference — QSettings only
        s.setValue("inference/alignment_guides", self._align_cb.isChecked())

    def revert(self) -> None:
        """Restore the snapshot to snap_engine (undoes any live changes)."""
        from firepro3d import snap_engine

        if not self._snapshot:
            return

        snap_engine.SNAP_TOLERANCE_PX = self._snapshot["tol_px"]
        # Populate widgets back to snapshot values so the UI is consistent
        self._tol_spin.setValue(self._snapshot["tol_px"])
        self._grip_spin.setValue(self._snapshot["grip_px"])
        self._grid_edit.set_value_mm(self._snapshot["grid_mm"])
        self._angle_spin.setValue(int(self._snapshot["angle_deg"]))
        self._align_cb.setChecked(self._snapshot["inference"])
        for attr, cb in self._snap_cbs.items():
            cb.setChecked(self._snapshot[attr])


class PreferencesDialog(QDialog):
    def __init__(self, panes: list[SettingsPane], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(560)
        self._panes = panes
        lay = QVBoxLayout(self)
        self._tabs = QTabWidget()
        for pane in panes:
            pane.load()
            self._tabs.addTab(pane, pane.title)
        lay.addWidget(self._tabs)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_all)
        lay.addWidget(box)

    def _apply_all(self):
        for pane in self._panes:
            pane.apply()

    def accept(self):
        self._apply_all()
        super().accept()

    def reject(self):
        for pane in self._panes:
            pane.revert()
        super().reject()
