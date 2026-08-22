"""Unified Preferences dialog — tabbed QDialog with snapshot/revert panes.

New settings live here first (design-of-record: 2026-08-22-ribbon-overhaul).
Panes own their own persistence target (QSettings or the project dict).
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
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

    When constructed with live ``scene``, ``view``, and ``osnap_toolbar``
    references the pane applies changes live (mirroring the old dialogs) and
    reverts them on Cancel.  Without those references only
    ``snap_engine.SNAP_TOLERANCE_PX`` is applied live; all other settings are
    written to / read from QSettings (MainWindow.restore_settings picks them up
    on next startup).

    Args:
        scene: The live ``Model_Space`` (or compatible) scene, or ``None``.
        view: The live ``Model_View`` (or compatible) view, or ``None``.
        osnap_toolbar: The live OSNAP toolbar that exposes
            ``refresh_from_engine()``, or ``None``.
        parent: Optional Qt parent widget.
    """

    def __init__(self, scene=None, view=None, osnap_toolbar=None, parent=None):
        super().__init__("Snapping", parent)
        self._scene = scene
        self._view = view
        self._osnap_toolbar = osnap_toolbar
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
        """Snapshot current engine/live-object/QSettings state and populate widgets.

        When ``self._scene`` / ``self._view`` are set the snapshot is taken
        from the live objects (authoritative at runtime).  Otherwise QSettings
        are used as the source of truth (startup / no-scene unit tests).
        ``snap_engine.SNAP_TOLERANCE_PX`` is always snapshotted from the
        module global.
        """
        from firepro3d import snap_engine

        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)

        # Always from the module global
        tol_px = snap_engine.SNAP_TOLERANCE_PX

        if self._scene is not None:
            eng = self._scene._snap_engine
            grip_px = int(getattr(self._scene, "_grip_tolerance_px", 200))
            angle_deg = int(self._scene._snap_angle_deg)
            inference = bool(self._scene._inference_enabled)
            snap_flags: dict[str, bool] = {
                attr: bool(getattr(eng, attr, True)) for _, attr in _SNAP_TYPES
            }
        else:
            grip_px = s.value("snap/grip_tolerance_px", 200, type=int)
            angle_deg = s.value("snap/angle_deg", 45, type=int)
            inference = s.value("inference/alignment_guides", True, type=bool)
            snap_flags = {}
            for _, attr in _SNAP_TYPES:
                val = s.value(f"snap/{attr}", True)
                if isinstance(val, str):
                    val = val.lower() not in ("false", "0")
                snap_flags[attr] = bool(val)

        if self._view is not None:
            grid_mm = float(self._view._grid_size)
        else:
            grid_mm = s.value("snap/grid_size", 10.0, type=float)

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
        """Write widget values to snap_engine, live objects, and QSettings.

        Live writes are guarded by ``self._scene is not None`` /
        ``self._view is not None`` so the pane is safe to use without a live
        scene (unit tests, headless mode).
        """
        from firepro3d import snap_engine

        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)

        # ── Module-level snap tolerance (always live) ─────────────────────────
        snap_engine.SNAP_TOLERANCE_PX = self._tol_spin.value()
        s.setValue("snap/tolerance_px", snap_engine.SNAP_TOLERANCE_PX)

        # ── Grip tolerance ────────────────────────────────────────────────────
        grip_px = self._grip_spin.value()
        s.setValue("snap/grip_tolerance_px", grip_px)
        if self._scene is not None:
            self._scene._grip_tolerance_px = grip_px

        # ── Per-type snap flags ───────────────────────────────────────────────
        if self._scene is not None:
            eng = self._scene._snap_engine
        for attr, cb in self._snap_cbs.items():
            val = cb.isChecked()
            s.setValue(f"snap/{attr}", val)
            if self._scene is not None:
                setattr(eng, attr, val)

        # ── Grid spacing ──────────────────────────────────────────────────────
        grid_mm = self._grid_edit.value_mm()
        s.setValue("snap/grid_size", grid_mm)
        if self._view is not None:
            self._view.set_grid(self._view._grid_visible, grid_mm)

        # ── Angle snap ────────────────────────────────────────────────────────
        angle_deg = self._angle_spin.value()
        s.setValue("snap/angle_deg", angle_deg)
        if self._scene is not None:
            self._scene._snap_angle_deg = angle_deg

        # ── Inference (alignment guides) ──────────────────────────────────────
        inference = self._align_cb.isChecked()
        s.setValue("inference/alignment_guides", inference)
        if self._scene is not None:
            self._scene.set_inference_enabled(inference)

        # ── OSNAP toolbar sync ────────────────────────────────────────────────
        if self._osnap_toolbar is not None:
            self._osnap_toolbar.refresh_from_engine()

    def revert(self) -> None:
        """Restore snapshot to live objects and snap_engine (undoes any Apply).

        Live writes are guarded by the same ``self._scene`` / ``self._view``
        None checks as ``apply()``.  The OSNAP toolbar is refreshed if present
        so it reflects the rolled-back state.
        """
        from firepro3d import snap_engine

        if not self._snapshot:
            return

        # ── Module-level snap tolerance (always) ──────────────────────────────
        snap_engine.SNAP_TOLERANCE_PX = self._snapshot["tol_px"]

        # ── Live scene objects ─────────────────────────────────────────────────
        if self._scene is not None:
            self._scene._grip_tolerance_px = self._snapshot["grip_px"]
            self._scene._snap_angle_deg = self._snapshot["angle_deg"]
            self._scene.set_inference_enabled(self._snapshot["inference"])
            eng = self._scene._snap_engine
            for _, attr in _SNAP_TYPES:
                setattr(eng, attr, self._snapshot[attr])

        # ── Live view ─────────────────────────────────────────────────────────
        if self._view is not None:
            self._view.set_grid(self._view._grid_visible, self._snapshot["grid_mm"])

        # ── OSNAP toolbar sync ────────────────────────────────────────────────
        if self._osnap_toolbar is not None:
            self._osnap_toolbar.refresh_from_engine()

        # ── Populate widgets back to snapshot values ───────────────────────────
        self._tol_spin.setValue(self._snapshot["tol_px"])
        self._grip_spin.setValue(self._snapshot["grip_px"])
        self._grid_edit.set_value_mm(self._snapshot["grid_mm"])
        self._angle_spin.setValue(int(self._snapshot["angle_deg"]))
        self._align_cb.setChecked(self._snapshot["inference"])
        for attr, cb in self._snap_cbs.items():
            cb.setChecked(self._snapshot[attr])


# Ordered list of (label, DisplayUnit value-string) for the unit combo.
# Mirrors _build_units_menu in main.py exactly.
_UNIT_OPTIONS: list[tuple[str, str]] = [
    ("Imperial (ft-in)", "imperial"),
    ("Metric (m)",       "m"),
    ("Metric (mm)",      "mm"),
]


class UnitsPane(SettingsPane):
    """Preferences pane for display unit and decimal precision.

    Mirrors the Units / Precision ribbon menus (``_build_units_menu`` /
    ``_build_precision_menu`` in ``main.py``) as an editable pane.

    When constructed with a live ``scale_manager``, ``apply()`` writes
    directly to ``scale_manager.display_unit`` and ``scale_manager.precision``
    (the same attributes set by the ribbon menus) AND persists to QSettings.
    ``revert()`` restores the snapshot taken at ``load()`` time.

    The optional ``on_changed`` callback is fired after every ``apply()`` so
    the caller can trigger a display refresh (e.g. re-render pipe labels).

    No-arg construction (``UnitsPane()``) is valid for unit tests; in that
    mode only QSettings are written; no live objects are mutated.

    Args:
        scale_manager: The live ``ScaleManager`` instance, or ``None``.
        on_changed: Optional zero-arg callable fired after each ``apply()``.
        parent: Optional Qt parent widget.
    """

    def __init__(
        self,
        scale_manager=None,
        on_changed: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__("Units & Precision", parent)
        self._sm = scale_manager
        self._on_changed = on_changed
        self._snapshot: dict = {}
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        form_group = QGroupBox("Display")
        form = QFormLayout(form_group)

        self._unit_combo = QComboBox()
        for label, _ in _UNIT_OPTIONS:
            self._unit_combo.addItem(label)
        form.addRow("Units:", self._unit_combo)

        self._precision_spin = QSpinBox()
        self._precision_spin.setRange(0, 6)
        self._precision_spin.setSuffix(" decimal places")
        form.addRow("Precision:", self._precision_spin)

        outer.addWidget(form_group)
        outer.addStretch()

    # ── SettingsPane protocol ─────────────────────────────────────────────────

    def load(self) -> None:
        """Snapshot current state and populate widgets.

        Source of truth priority: live ScaleManager (if present) → QSettings.
        """
        if self._sm is not None:
            unit_str = self._sm.display_unit.value if self._sm.display_unit is not None else "mm"
            precision = int(self._sm.precision)
        else:
            s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            unit_str  = s.value("display/unit", "mm", type=str)
            precision = s.value("display/precision", 2, type=int)

        self._snapshot = {"unit_str": unit_str, "precision": precision}

        # Populate combo — fall back to last item if value not found
        idx = next(
            (i for i, (_, v) in enumerate(_UNIT_OPTIONS) if v == unit_str),
            len(_UNIT_OPTIONS) - 1,
        )
        self._unit_combo.setCurrentIndex(idx)
        self._precision_spin.setValue(precision)

    def apply(self) -> None:
        """Write widget values to live ScaleManager and QSettings."""
        from firepro3d.scale_manager import DisplayUnit

        idx      = self._unit_combo.currentIndex()
        unit_str = _UNIT_OPTIONS[idx][1]
        precision = self._precision_spin.value()

        # Live update
        if self._sm is not None:
            self._sm.display_unit = DisplayUnit(unit_str)
            self._sm.precision    = precision

        # Persist
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        s.setValue("display/unit",      unit_str)
        s.setValue("display/precision", precision)

        if self._on_changed is not None:
            self._on_changed()

    def revert(self) -> None:
        """Restore snapshot to live ScaleManager and repopulate widgets."""
        from firepro3d.scale_manager import DisplayUnit

        if not self._snapshot:
            return

        unit_str  = self._snapshot["unit_str"]
        precision = self._snapshot["precision"]

        if self._sm is not None:
            self._sm.display_unit = DisplayUnit(unit_str)
            self._sm.precision    = precision

        idx = next(
            (i for i, (_, v) in enumerate(_UNIT_OPTIONS) if v == unit_str),
            len(_UNIT_OPTIONS) - 1,
        )
        self._unit_combo.setCurrentIndex(idx)
        self._precision_spin.setValue(precision)


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
