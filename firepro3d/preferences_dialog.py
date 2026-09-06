"""Unified Preferences dialog — tabbed QDialog with snapshot/revert panes.

New settings live here first (design-of-record: 2026-08-22-ribbon-overhaul).
Panes own their own persistence target (QSettings or the project dict).
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .constants import (
    ALIGN_PATH_TOL_PX, ALIGN_DWELL_MS, ALIGN_MAX_POINTS,
    ALIGN_DIR_HV_DEFAULT, ALIGN_DIR_EXTENSION_DEFAULT, ALIGN_DIR_PARALLEL_DEFAULT,
    ALIGN_DIR_PERPENDICULAR_DEFAULT, PDF_BEZIER_FLATTEN_TOL,
)
from .app_data import default_root, ROOT_KEY as _DATA_ROOT_KEY


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

_FACTORY_DEFAULTS: dict = {
    "tol_px":       15,
    "hysteresis_px": 3,
    "grip_px":      200,
    "grid_mm":      10.0,
    "angle_deg":    45,
    "align":        True,
    # ── ALIGN knobs (docs/superpowers/specs/…-align-tracking-design.md D7) ──
    "align_path_tol_px": int(ALIGN_PATH_TOL_PX),
    "align_dwell_ms":    ALIGN_DWELL_MS,
    "align_max_points":  ALIGN_MAX_POINTS,
    "align_dir_hv":        ALIGN_DIR_HV_DEFAULT,
    "align_dir_extension": ALIGN_DIR_EXTENSION_DEFAULT,
    "align_dir_parallel":  ALIGN_DIR_PARALLEL_DEFAULT,
    "align_dir_perpendicular": ALIGN_DIR_PERPENDICULAR_DEFAULT,
    **{attr: True for _, attr in _SNAP_TYPES},
}


class SnappingPane(SettingsPane):
    """Preferences pane for SNAP / snap-tolerance / grid / ALIGN settings.

    Ports the two existing snap dialogs in ``main.py``:
    - ``_open_snap_tolerance_dialog`` — snap radius, grip radius, 8 snap-type
      checkboxes, alignment-guides toggle.
    - ``_open_snap_settings`` — grid spacing (mm), angle-snap increment.

    When constructed with live ``scene``, ``view``, and ``snap_toolbar``
    references the pane applies changes live (mirroring the old dialogs) and
    reverts them on Cancel.  Without those references only
    ``snap_engine.SNAP_TOLERANCE_PX`` is applied live; all other settings are
    written to / read from QSettings (MainWindow.restore_settings picks them up
    on next startup).

    Args:
        scene: The live ``Model_Space`` (or compatible) scene, or ``None``.
        view: The live ``Model_View`` (or compatible) view, or ``None``.
        snap_toolbar: The live SNAP toolbar that exposes
            ``refresh_from_engine()``, or ``None``.
        parent: Optional Qt parent widget.
    """

    def __init__(self, scene=None, view=None, snap_toolbar=None, parent=None):
        super().__init__("Snapping", parent)
        self._scene = scene
        self._view = view
        self._snap_toolbar = snap_toolbar
        self._snapshot: dict = {}
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        from .dimension_edit import DimensionEdit

        outer = QVBoxLayout(self)

        tabs = QTabWidget()
        outer.addWidget(tabs)

        # ── Tab 1: SNAP ──────────────────────────────────────────────────────
        snap_tab = QWidget()
        snap_layout = QVBoxLayout(snap_tab)

        # Tolerance group
        tol_group = QGroupBox("Tolerance")
        tol_form = QFormLayout(tol_group)

        self._tol_spin = QSpinBox()
        self._tol_spin.setRange(5, 1000)
        self._tol_spin.setSingleStep(5)
        self._tol_spin.setSuffix(" px")
        tol_form.addRow("Snap aperture:", self._tol_spin)

        self._hyst_spin = QSpinBox()
        self._hyst_spin.setRange(0, 50)
        self._hyst_spin.setSingleStep(1)
        self._hyst_spin.setSuffix(" px")
        tol_form.addRow("Hysteresis:", self._hyst_spin)

        self._grip_spin = QSpinBox()
        self._grip_spin.setRange(100, 1000)
        self._grip_spin.setSingleStep(50)
        self._grip_spin.setSuffix(" px")
        tol_form.addRow("Grip handle radius:", self._grip_spin)

        snap_layout.addWidget(tol_group)

        # Snap types group
        types_group = QGroupBox("Snap Types")
        types_layout = QVBoxLayout(types_group)
        self._snap_cbs: dict[str, QCheckBox] = {}
        for label, attr in _SNAP_TYPES:
            cb = QCheckBox(label)
            types_layout.addWidget(cb)
            self._snap_cbs[attr] = cb
        snap_layout.addWidget(types_group)

        tabs.addTab(snap_tab, "SNAP")

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

        # ── Tab 3: ALIGN ─────────────────────────────────────────────────────
        inf_tab = QWidget()
        inf_layout = QVBoxLayout(inf_tab)

        self._align_cb = QCheckBox("ALIGN (master on/off · F11)")
        self._align_cb.setObjectName("align_enabled")
        inf_layout.addWidget(self._align_cb)

        # Acquire / tracking tunables
        tune_group = QGroupBox("Acquire & Tracking")
        tune_form = QFormLayout(tune_group)

        self._align_tol_spin = QSpinBox()
        self._align_tol_spin.setRange(5, 200)
        self._align_tol_spin.setSingleStep(5)
        self._align_tol_spin.setSuffix(" px")
        tune_form.addRow("Path snap aperture:", self._align_tol_spin)

        self._align_dwell_spin = QSpinBox()
        self._align_dwell_spin.setRange(0, 3000)
        self._align_dwell_spin.setSingleStep(50)
        self._align_dwell_spin.setSuffix(" ms")
        tune_form.addRow("Acquire dwell:", self._align_dwell_spin)

        self._align_maxpts_spin = QSpinBox()
        self._align_maxpts_spin.setRange(1, 20)
        self._align_maxpts_spin.setSingleStep(1)
        tune_form.addRow("Max acquired points:", self._align_maxpts_spin)

        inf_layout.addWidget(tune_group)

        # Per-direction ray-kind toggles
        dir_group = QGroupBox("Tracking Directions")
        dir_layout = QVBoxLayout(dir_group)
        self._align_hv_cb = QCheckBox("Horizontal / Vertical")
        self._align_ext_cb = QCheckBox("Extension (collinear)")
        self._align_par_cb = QCheckBox("Parallel")
        self._align_perp_cb = QCheckBox("Perpendicular")
        for cb in (self._align_hv_cb, self._align_ext_cb, self._align_par_cb,
                   self._align_perp_cb):
            dir_layout.addWidget(cb)
        inf_layout.addWidget(dir_group)
        inf_layout.addStretch()

        tabs.addTab(inf_tab, "ALIGN")

        # ── Reset to Defaults button ──────────────────────────────────────────
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        outer.addWidget(reset_btn)

    # ── ALIGN knob setters / getters ──────────────────────────────────────────
    # Thin wrappers so callers (and tests) drive the widgets by name; apply()
    # reads the widgets, so setting a value then apply()-ing live-applies it.

    def set_align_path_tol(self, px: int) -> None:
        self._align_tol_spin.setValue(int(px))

    def align_path_tol(self) -> int:
        return self._align_tol_spin.value()

    def set_align_dwell(self, ms: int) -> None:
        self._align_dwell_spin.setValue(int(ms))

    def align_dwell(self) -> int:
        return self._align_dwell_spin.value()

    def set_align_max_points(self, n: int) -> None:
        self._align_maxpts_spin.setValue(int(n))

    def align_max_points(self) -> int:
        return self._align_maxpts_spin.value()

    def set_align_hv_enabled(self, on: bool) -> None:
        self._align_hv_cb.setChecked(bool(on))

    def align_hv_enabled(self) -> bool:
        return self._align_hv_cb.isChecked()

    def set_align_extension_enabled(self, on: bool) -> None:
        self._align_ext_cb.setChecked(bool(on))

    def align_extension_enabled(self) -> bool:
        return self._align_ext_cb.isChecked()

    def set_align_parallel_enabled(self, on: bool) -> None:
        self._align_par_cb.setChecked(bool(on))

    def align_parallel_enabled(self) -> bool:
        return self._align_par_cb.isChecked()

    def set_align_perpendicular_enabled(self, on: bool) -> None:
        self._align_perp_cb.setChecked(bool(on))

    def align_perpendicular_enabled(self) -> bool:
        return self._align_perp_cb.isChecked()

    def set_align_master(self, on: bool) -> None:
        self._align_cb.setChecked(bool(on))

    def align_master(self) -> bool:
        return self._align_cb.isChecked()

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

        # Always from the module globals
        tol_px = snap_engine.SNAP_TOLERANCE_PX
        hyst_px = snap_engine.SNAP_HYSTERESIS_PX

        if self._scene is not None:
            eng = self._scene._snap_engine
            grip_px = int(getattr(self._scene, "_grip_tolerance_px", 200))
            angle_deg = int(self._scene._snap_angle_deg)
            align_on = bool(self._scene._align_enabled)
            # ALIGN tunables come from the live controller when present; a
            # partial scene (test double) falls back to the factory defaults.
            ctrl = getattr(self._scene, "_align_controller", None)
            align_tol = int(getattr(self._scene, "_align_path_tol_px",
                                    ALIGN_PATH_TOL_PX))
            align_dwell = int(getattr(ctrl, "dwell_ms", ALIGN_DWELL_MS))
            align_maxpts = int(getattr(ctrl, "max_points", ALIGN_MAX_POINTS))
            align_hv = bool(getattr(ctrl, "dir_hv_enabled", ALIGN_DIR_HV_DEFAULT))
            align_ext = bool(getattr(ctrl, "dir_extension_enabled",
                                     ALIGN_DIR_EXTENSION_DEFAULT))
            align_par = bool(getattr(ctrl, "dir_parallel_enabled",
                                     ALIGN_DIR_PARALLEL_DEFAULT))
            align_perp = bool(getattr(ctrl, "dir_perpendicular_enabled",
                                      ALIGN_DIR_PERPENDICULAR_DEFAULT))
            snap_flags: dict[str, bool] = {
                attr: bool(getattr(eng, attr, True)) for _, attr in _SNAP_TYPES
            }
        else:
            grip_px = s.value("snap/grip_tolerance_px", 200, type=int)
            angle_deg = s.value("snap/angle_deg", 45, type=int)
            align_on = s.value("align/enabled", True, type=bool)
            align_tol = s.value("align/path_tol_px", int(ALIGN_PATH_TOL_PX), type=int)
            align_dwell = s.value("align/dwell_ms", ALIGN_DWELL_MS, type=int)
            align_maxpts = s.value("align/max_points", ALIGN_MAX_POINTS, type=int)
            align_hv = s.value("align/dir_hv", ALIGN_DIR_HV_DEFAULT, type=bool)
            align_ext = s.value("align/dir_extension",
                                ALIGN_DIR_EXTENSION_DEFAULT, type=bool)
            align_par = s.value("align/dir_parallel",
                                ALIGN_DIR_PARALLEL_DEFAULT, type=bool)
            align_perp = s.value("align/dir_perpendicular",
                                 ALIGN_DIR_PERPENDICULAR_DEFAULT, type=bool)
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
            "tol_px":       tol_px,
            "hysteresis_px": hyst_px,
            "grip_px":      grip_px,
            "grid_mm":      grid_mm,
            "angle_deg":    angle_deg,
            "align":        align_on,
            "align_path_tol_px": align_tol,
            "align_dwell_ms":    align_dwell,
            "align_max_points":  align_maxpts,
            "align_dir_hv":        align_hv,
            "align_dir_extension": align_ext,
            "align_dir_parallel":  align_par,
            "align_dir_perpendicular": align_perp,
            **snap_flags,
        }

        # Populate widgets
        self._tol_spin.setValue(tol_px)
        self._hyst_spin.setValue(hyst_px)
        self._grip_spin.setValue(grip_px)
        self._grid_edit.set_value_mm(grid_mm)
        self._angle_spin.setValue(int(angle_deg))
        self._align_cb.setChecked(align_on)
        self._align_tol_spin.setValue(int(align_tol))
        self._align_dwell_spin.setValue(int(align_dwell))
        self._align_maxpts_spin.setValue(int(align_maxpts))
        self._align_hv_cb.setChecked(bool(align_hv))
        self._align_ext_cb.setChecked(bool(align_ext))
        self._align_par_cb.setChecked(bool(align_par))
        self._align_perp_cb.setChecked(bool(align_perp))
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

        # ── Hysteresis (always live) ──────────────────────────────────────────
        snap_engine.SNAP_HYSTERESIS_PX = self._hyst_spin.value()
        s.setValue("snap/hysteresis_px", snap_engine.SNAP_HYSTERESIS_PX)

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
                setattr(eng, attr, val)
        else:
            for attr, cb in self._snap_cbs.items():
                s.setValue(f"snap/{attr}", cb.isChecked())

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

        # ── ALIGN master on/off ───────────────────────────────────────────────
        align_on = self._align_cb.isChecked()
        s.setValue("align/enabled", align_on)
        if self._scene is not None:
            self._scene.set_align_enabled(align_on)

        # ── ALIGN tunables (path-tol / dwell / max-points / directions) ───────
        align_tol = self._align_tol_spin.value()
        align_dwell = self._align_dwell_spin.value()
        align_maxpts = self._align_maxpts_spin.value()
        align_hv = self._align_hv_cb.isChecked()
        align_ext = self._align_ext_cb.isChecked()
        align_par = self._align_par_cb.isChecked()
        align_perp = self._align_perp_cb.isChecked()
        s.setValue("align/path_tol_px", align_tol)
        s.setValue("align/dwell_ms", align_dwell)
        s.setValue("align/max_points", align_maxpts)
        s.setValue("align/dir_hv", align_hv)
        s.setValue("align/dir_extension", align_ext)
        s.setValue("align/dir_parallel", align_par)
        s.setValue("align/dir_perpendicular", align_perp)
        if self._scene is not None:
            self._scene._align_path_tol_px = float(align_tol)
            ctrl = getattr(self._scene, "_align_controller", None)
            if ctrl is not None:
                ctrl.dwell_ms = align_dwell
                ctrl.max_points = align_maxpts
                ctrl.set_direction_flags(hv=align_hv, extension=align_ext,
                                         parallel=align_par,
                                         perpendicular=align_perp)

        # ── SNAP toolbar sync ─────────────────────────────────────────────────
        if self._snap_toolbar is not None:
            self._snap_toolbar.refresh_from_engine()

    def revert(self) -> None:
        """Restore snapshot to live objects and snap_engine (undoes any Apply).

        Live writes are guarded by the same ``self._scene`` / ``self._view``
        None checks as ``apply()``.  The SNAP toolbar is refreshed if present
        so it reflects the rolled-back state.
        """
        from firepro3d import snap_engine

        if not self._snapshot:
            return

        # ── Module-level snap tolerance (always) ──────────────────────────────
        snap_engine.SNAP_TOLERANCE_PX = self._snapshot["tol_px"]

        # ── Hysteresis (always) ───────────────────────────────────────────────
        snap_engine.SNAP_HYSTERESIS_PX = self._snapshot["hysteresis_px"]

        # ── Live scene objects ─────────────────────────────────────────────────
        if self._scene is not None:
            self._scene._grip_tolerance_px = self._snapshot["grip_px"]
            self._scene._snap_angle_deg = self._snapshot["angle_deg"]
            self._scene.set_align_enabled(self._snapshot["align"])
            self._scene._align_path_tol_px = float(
                self._snapshot["align_path_tol_px"])
            ctrl = getattr(self._scene, "_align_controller", None)
            if ctrl is not None:
                ctrl.dwell_ms = self._snapshot["align_dwell_ms"]
                ctrl.max_points = self._snapshot["align_max_points"]
                ctrl.set_direction_flags(
                    hv=self._snapshot["align_dir_hv"],
                    extension=self._snapshot["align_dir_extension"],
                    parallel=self._snapshot["align_dir_parallel"],
                    perpendicular=self._snapshot["align_dir_perpendicular"])
            eng = self._scene._snap_engine
            for _, attr in _SNAP_TYPES:
                setattr(eng, attr, self._snapshot[attr])

        # ── Live view ─────────────────────────────────────────────────────────
        if self._view is not None:
            self._view.set_grid(self._view._grid_visible, self._snapshot["grid_mm"])

        # ── SNAP toolbar sync ─────────────────────────────────────────────────
        if self._snap_toolbar is not None:
            self._snap_toolbar.refresh_from_engine()

        # ── Populate widgets back to snapshot values ───────────────────────────
        self._tol_spin.setValue(self._snapshot["tol_px"])
        self._hyst_spin.setValue(self._snapshot["hysteresis_px"])
        self._grip_spin.setValue(self._snapshot["grip_px"])
        self._grid_edit.set_value_mm(self._snapshot["grid_mm"])
        self._angle_spin.setValue(int(self._snapshot["angle_deg"]))
        self._align_cb.setChecked(self._snapshot["align"])
        self._align_tol_spin.setValue(int(self._snapshot["align_path_tol_px"]))
        self._align_dwell_spin.setValue(int(self._snapshot["align_dwell_ms"]))
        self._align_maxpts_spin.setValue(int(self._snapshot["align_max_points"]))
        self._align_hv_cb.setChecked(bool(self._snapshot["align_dir_hv"]))
        self._align_ext_cb.setChecked(bool(self._snapshot["align_dir_extension"]))
        self._align_par_cb.setChecked(bool(self._snapshot["align_dir_parallel"]))
        self._align_perp_cb.setChecked(
            bool(self._snapshot["align_dir_perpendicular"]))
        for attr, cb in self._snap_cbs.items():
            cb.setChecked(self._snapshot[attr])

    def reset_to_defaults(self) -> None:
        """Set every SNAP-pane widget to factory defaults and apply live."""
        d = _FACTORY_DEFAULTS
        self._tol_spin.setValue(d["tol_px"])
        self._hyst_spin.setValue(d["hysteresis_px"])
        self._grip_spin.setValue(d["grip_px"])
        self._grid_edit.set_value_mm(d["grid_mm"])
        self._angle_spin.setValue(int(d["angle_deg"]))
        self._align_cb.setChecked(d["align"])
        self._align_tol_spin.setValue(int(d["align_path_tol_px"]))
        self._align_dwell_spin.setValue(int(d["align_dwell_ms"]))
        self._align_maxpts_spin.setValue(int(d["align_max_points"]))
        self._align_hv_cb.setChecked(bool(d["align_dir_hv"]))
        self._align_ext_cb.setChecked(bool(d["align_dir_extension"]))
        self._align_par_cb.setChecked(bool(d["align_dir_parallel"]))
        self._align_perp_cb.setChecked(bool(d["align_dir_perpendicular"]))
        for attr, cb in self._snap_cbs.items():
            cb.setChecked(d[attr])
        self.apply()


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
            precision = s.value("display/precision", 3, type=int)

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


# Dock defaults as used in MainWindow.restore_settings.
# Report docks (hydraulics/radiation) are transient run-results, force-hidden
# on startup by restore_settings, so they are intentionally NOT listed here.
_DOCK_ITEMS: list[tuple[str, str, bool]] = [
    ("Browser",          "dock/browser",     True),
    ("Properties",       "dock/properties",  True),
]


class ImportPane(SettingsPane):
    """Preferences pane for import and conversion settings.

    Covers:
    - ODA File Converter executable path (QSettings key ``dwg/oda_converter_path``).

    - PDF rasterisation DPI + import-mode **defaults** (QSettings keys
      ``import/pdf_dpi`` / ``import/pdf_import_mode``). The import dialog seeds
      its PDF Options combos from these; a per-import override does not write
      back (one-off).

    - PDF bézier flatten tolerance (QSettings key
      ``import/pdf_bezier_flatten_tol``). Unlike the defaults above this is a
      live extraction parameter: it feeds ``_flatten_bezier`` AND the PDF cache
      key, so changing it re-extracts underlays on next load/refresh.

    This is a QSettings-only preference; no live-object mutation is needed.
    Construct with no args.
    """

    def __init__(self, parent=None):
        super().__init__("Import & Conversion", parent)
        self._snapshot: dict = {}
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        # ── ODA Converter group ───────────────────────────────────────────────
        oda_group = QGroupBox("DWG Conversion (ODA File Converter)")
        oda_form = QFormLayout(oda_group)

        oda_row = QWidget()
        oda_row_layout = QHBoxLayout(oda_row)
        oda_row_layout.setContentsMargins(0, 0, 0, 0)
        self._oda_edit = QLineEdit()
        self._oda_edit.setPlaceholderText("Path to ODAFileConverter.exe…")
        oda_row_layout.addWidget(self._oda_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_oda)
        oda_row_layout.addWidget(browse_btn)
        oda_form.addRow("Executable:", oda_row)

        outer.addWidget(oda_group)

        # ── PDF import defaults ───────────────────────────────────────────────
        pdf_group = QGroupBox("PDF Import Defaults")
        pdf_form = QFormLayout(pdf_group)
        self._dpi_combo = QComboBox()
        self._dpi_combo.addItems(["72", "150", "300"])
        pdf_form.addRow("Rasterisation DPI:", self._dpi_combo)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Auto", "Vectors", "Raster"])
        pdf_form.addRow("Import mode:", self._mode_combo)
        # Bézier flatten tolerance — curve tessellation quality for vector PDF
        # imports. Higher = coarser (fewer points, faster/smaller), lower =
        # smoother curves. In PDF points (paper-space); changing it re-extracts
        # the underlay on next load/refresh (it is part of the PDF cache key).
        self._flatten_tol_spin = QDoubleSpinBox()
        self._flatten_tol_spin.setRange(0.25, 4.0)
        self._flatten_tol_spin.setSingleStep(0.25)
        self._flatten_tol_spin.setDecimals(2)
        self._flatten_tol_spin.setSuffix(" pt")
        _flatten_tip = (
            "How finely curves in a vector PDF are broken into straight "
            "segments, measured in PDF points (1 pt = 1/72 inch on the sheet).\n\n"
            "• Lower value → smoother curves, but more points (larger, slower "
            "underlay). 0.25 pt is finer than the old default.\n"
            "• Higher value → fewer points (smaller, faster underlay), but "
            "curves look faceted when you zoom in past plot scale.\n\n"
            "Only affects vector PDF imports. Changing it re-extracts the "
            "underlay on the next project load, or immediately when you use "
            "Refresh in the Underlay Manager.")
        self._flatten_tol_spin.setToolTip(_flatten_tip)
        # Explicit label so the tooltip also shows when hovering the label text
        # (a QFormLayout string row auto-makes an untooltipped QLabel).
        _flatten_lbl = QLabel("Curve flatten tolerance:")
        _flatten_lbl.setToolTip(_flatten_tip)
        pdf_form.addRow(_flatten_lbl, self._flatten_tol_spin)
        outer.addWidget(pdf_group)

        outer.addStretch()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _browse_oda(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Locate ODA File Converter",
            self._oda_edit.text() or "",
            "Executables (*.exe);;All files (*)",
        )
        if path:
            self._oda_edit.setText(path)

    # ── SettingsPane protocol ─────────────────────────────────────────────────

    def load(self) -> None:
        """Snapshot current QSettings values and populate widgets."""
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)

        oda_path = s.value("dwg/oda_converter_path", "", type=str)
        dpi = s.value("import/pdf_dpi", 150, type=int)
        mode = s.value("import/pdf_import_mode", "auto", type=str)
        flatten_tol = s.value("import/pdf_bezier_flatten_tol",
                              PDF_BEZIER_FLATTEN_TOL, type=float)
        self._snapshot = {"oda_path": oda_path, "dpi": dpi, "mode": mode,
                          "flatten_tol": flatten_tol}
        self._oda_edit.setText(oda_path)
        self._dpi_combo.setCurrentText(str(dpi))
        self._mode_combo.setCurrentText(mode.capitalize())
        self._flatten_tol_spin.setValue(flatten_tol)

    def apply(self) -> None:
        """Write widget values to QSettings."""
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        s.setValue("dwg/oda_converter_path", self._oda_edit.text())
        s.setValue("import/pdf_dpi", int(self._dpi_combo.currentText()))
        s.setValue("import/pdf_import_mode", self._mode_combo.currentText().lower())
        s.setValue("import/pdf_bezier_flatten_tol", self._flatten_tol_spin.value())

    def revert(self) -> None:
        """Restore snapshot values to widgets (no live objects to roll back)."""
        if not self._snapshot:
            return
        self._oda_edit.setText(self._snapshot["oda_path"])
        self._dpi_combo.setCurrentText(str(self._snapshot["dpi"]))
        self._mode_combo.setCurrentText(self._snapshot["mode"].capitalize())
        self._flatten_tol_spin.setValue(self._snapshot["flatten_tol"])


class GeneralPane(SettingsPane):
    """Preferences pane for general application defaults.

    Currently covers dock-panel visibility defaults, mapped to the same
    QSettings keys that ``MainWindow.restore_settings`` reads on startup
    (``dock/browser``, ``dock/properties``, ``dock/hydraulics``,
    ``dock/radiation``).

    These are QSettings-only preferences; no live-object mutation is
    performed (dock visibility at runtime is controlled by the View menu).
    Construct with no args.
    """

    def __init__(self, parent=None):
        super().__init__("General", parent)
        self._snapshot: dict = {}
        self._dock_checks: dict[str, QCheckBox] = {}
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        dock_group = QGroupBox("Dock panel defaults (shown on startup)")
        dock_layout = QVBoxLayout(dock_group)

        for label, _key, _default in _DOCK_ITEMS:
            short_key = _key.split("/", 1)[1]  # "browser", "properties", etc.
            cb = QCheckBox(label)
            cb.setChecked(_default)
            dock_layout.addWidget(cb)
            self._dock_checks[short_key] = cb

        outer.addWidget(dock_group)

        # ── Data folder (block / sprinkler / title-block libraries) ──────────
        data_group = QGroupBox("Data folder")
        dv = QVBoxLayout(data_group)
        hint = QLabel(
            "Where FirePro3D stores your block, sprinkler and title-block "
            "libraries. Leave blank for the default. Changing this does not move "
            "existing content — copy it over yourself if needed.")
        hint.setWordWrap(True)
        dv.addWidget(hint)
        row = QHBoxLayout()
        self._data_folder_edit = QLineEdit()
        self._data_folder_edit.setPlaceholderText(default_root())
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_data_folder)
        reset = QPushButton("Reset")
        reset.clicked.connect(self._data_folder_edit.clear)
        row.addWidget(self._data_folder_edit, 1)
        row.addWidget(browse)
        row.addWidget(reset)
        dv.addLayout(row)
        outer.addWidget(data_group)

        outer.addStretch()

    def _pick_data_folder(self) -> None:
        start = self._data_folder_edit.text().strip() or default_root()
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose FirePro3D data folder", start)
        if chosen:
            self._data_folder_edit.setText(chosen)

    # ── SettingsPane protocol ─────────────────────────────────────────────────

    def load(self) -> None:
        """Snapshot current QSettings values and populate checkboxes."""
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)

        snapshot: dict[str, bool] = {}
        for _label, qkey, default in _DOCK_ITEMS:
            short_key = qkey.split("/", 1)[1]
            raw = s.value(qkey, default)
            # QSettings on Windows can return str; coerce to bool.
            if isinstance(raw, str):
                val = raw.lower() not in ("false", "0")
            else:
                val = bool(raw)
            snapshot[short_key] = val
            self._dock_checks[short_key].setChecked(val)

        self._snapshot = snapshot
        df = s.value(_DATA_ROOT_KEY, "", type=str) or ""
        self._data_folder_snapshot = df
        self._data_folder_edit.setText(df)

    def apply(self) -> None:
        """Write checkbox states + the data-folder override to QSettings."""
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)

        for _label, qkey, _default in _DOCK_ITEMS:
            short_key = qkey.split("/", 1)[1]
            s.setValue(qkey, self._dock_checks[short_key].isChecked())

        # Blank clears the override (falls back to the default root).
        s.setValue(_DATA_ROOT_KEY, self._data_folder_edit.text().strip())

    def revert(self) -> None:
        """Restore snapshot values to checkboxes + the data-folder field."""
        for short_key, val in (self._snapshot or {}).items():
            if short_key in self._dock_checks:
                self._dock_checks[short_key].setChecked(val)
        self._data_folder_edit.setText(getattr(self, "_data_folder_snapshot", ""))


# Ordered list of (label, dict-key) for the standard project-info fields.
# Mirrors _STANDARD_FIELDS in MainWindow._open_project_info exactly.
_PROJECT_INFO_FIELDS: list[tuple[str, str]] = [
    ("Project Name",           "name"),
    ("Project Number",         "number"),
    ("Address Line 1",         "address1"),
    ("Address Line 2",         "address2"),
    ("Address Line 3",         "address3"),
    ("Client",                 "client"),
    ("Client Address Line 1",  "client_address1"),
    ("Client Address Line 2",  "client_address2"),
    ("Client Address Line 3",  "client_address3"),
    ("Designer",               "designer"),
    ("Description",            "description"),
]


class UIPane(SettingsPane):
    """UI preferences — application theme (System / Light / Dark).

    QSettings-only (key ``ui/theme``, read by ``theme.detect()``). On apply the
    ``on_theme_changed`` callback re-styles the live application; some already-
    open dialogs/toolbars pick up the change when next reopened.
    """

    _THEME_KEY = "ui/theme"
    _CROSSHAIR_KEY = "ui/crosshair"
    _IMMERSIVE_KEY = "ui/immersive"
    _CHOICES = [("System", "system"), ("Light", "light"), ("Dark", "dark")]

    def __init__(self, on_theme_changed: Callable[[], None] | None = None,
                 on_crosshair_changed: Callable[[bool], None] | None = None,
                 on_immersive_changed: Callable[[bool], None] | None = None,
                 parent=None):
        super().__init__("UI", parent)
        self._on_theme_changed = on_theme_changed
        self._on_crosshair_changed = on_crosshair_changed
        self._on_immersive_changed = on_immersive_changed
        self._snapshot = "system"
        self._crosshair_snapshot = True
        self._immersive_snapshot = False

        form = QFormLayout(self)
        self._theme_combo = QComboBox()
        for label, _value in self._CHOICES:
            self._theme_combo.addItem(label)
        form.addRow("Theme:", self._theme_combo)

        self._crosshair_cb = QCheckBox("Show crosshair cursor")
        form.addRow(self._crosshair_cb)

        self._immersive_cb = QCheckBox("Maximize window on startup")
        form.addRow(self._immersive_cb)

        hint = QLabel(
            "System follows your OS light/dark setting. Changes apply to the "
            "main window immediately; some dialogs update when reopened.")
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        form.addRow(hint)

    def load(self):
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        val = str(s.value(self._THEME_KEY, "system")).lower()
        self._snapshot = val
        idx = next((i for i, (_, v) in enumerate(self._CHOICES) if v == val), 0)
        self._theme_combo.setCurrentIndex(idx)
        cx = s.value(self._CROSSHAIR_KEY, True, type=bool)
        self._crosshair_snapshot = cx
        self._crosshair_cb.setChecked(cx)
        im = s.value(self._IMMERSIVE_KEY, False, type=bool)
        self._immersive_snapshot = im
        self._immersive_cb.setChecked(im)

    def apply(self):
        val = self._CHOICES[self._theme_combo.currentIndex()][1]
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        s.setValue(self._THEME_KEY, val)
        s.sync()
        if val != self._snapshot:
            # Invalidate theme.py's cached preference, then restyle live.
            from . import theme as _th
            _th.refresh_theme_preference()
            if self._on_theme_changed is not None:
                self._on_theme_changed()
        self._snapshot = val

        cx = self._crosshair_cb.isChecked()
        s.setValue(self._CROSSHAIR_KEY, cx)
        s.sync()
        if cx != self._crosshair_snapshot and self._on_crosshair_changed is not None:
            self._on_crosshair_changed(cx)
        self._crosshair_snapshot = cx

        im = self._immersive_cb.isChecked()
        s.setValue(self._IMMERSIVE_KEY, im)
        s.sync()
        if im != self._immersive_snapshot and self._on_immersive_changed is not None:
            self._on_immersive_changed(im)
        self._immersive_snapshot = im

    def revert(self):
        idx = next(
            (i for i, (_, v) in enumerate(self._CHOICES) if v == self._snapshot), 0)
        self._theme_combo.setCurrentIndex(idx)
        self._crosshair_cb.setChecked(self._crosshair_snapshot)
        self._immersive_cb.setChecked(self._immersive_snapshot)


class ProjectInfoPane(SettingsPane):
    """Preferences pane for per-project metadata.

    This pane is fundamentally different from the QSettings-backed panes: its
    data lives in ``scene._project_info`` (a plain dict inside the project
    file), not in QSettings.  The caller supplies ``get_info`` / ``set_info``
    callbacks so the pane stays decoupled from ``MainWindow``.

    ``apply()`` calls ``set_info(edited_dict)`` — the caller is responsible for
    writing that dict to ``scene._project_info`` **and** calling
    ``_push_titleblock_template()`` so the paper scene re-renders with the new
    values (that push is wired in Task D6, not here).

    No-arg construction is valid: both callbacks default to no-ops so the pane
    builds and loads empty without raising.

    Args:
        get_info: Zero-arg callable returning the current project-info dict, or
            ``None`` (treated as returning ``{}``).
        set_info: One-arg callable receiving the edited dict on ``apply()``, or
            ``None`` (apply becomes a no-op persist-side, widgets still update).
        parent: Optional Qt parent widget.
    """

    def __init__(
        self,
        get_info: Callable[[], dict] | None = None,
        set_info: Callable[[dict], None] | None = None,
        parent=None,
    ):
        super().__init__("Project Info", parent)
        self._get_info = get_info
        self._set_info = set_info
        self._snapshot: dict = {}
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        # Table with two columns: Property | Value
        self._table = QTableWidget(len(_PROJECT_INFO_FIELDS), 2)
        self._table.setHorizontalHeaderLabels(["Property", "Value"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)

        # Pre-populate the Property column (read-only labels)
        from PyQt6.QtCore import Qt
        for row, (label, _key) in enumerate(_PROJECT_INFO_FIELDS):
            prop_item = QTableWidgetItem(label)
            prop_item.setFlags(prop_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, prop_item)
            self._table.setItem(row, 1, QTableWidgetItem(""))

        outer.addWidget(self._table)

        # Add / Remove custom row buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add Property")
        remove_btn = QPushButton("- Remove Property")
        add_btn.clicked.connect(self._add_custom_row)
        remove_btn.clicked.connect(self._remove_custom_row)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _add_custom_row(self) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setItem(r, 0, QTableWidgetItem(""))
        self._table.setItem(r, 1, QTableWidgetItem(""))
        self._table.editItem(self._table.item(r, 0))

    def _remove_custom_row(self) -> None:
        row = self._table.currentRow()
        if row >= len(_PROJECT_INFO_FIELDS):
            self._table.removeRow(row)

    def _read_dict_from_table(self) -> dict:
        """Build the project-info dict from current table widget state."""
        result: dict = {}
        for row, (_label, key) in enumerate(_PROJECT_INFO_FIELDS):
            item = self._table.item(row, 1)
            result[key] = item.text() if item else ""
        custom = []
        for row in range(len(_PROJECT_INFO_FIELDS), self._table.rowCount()):
            k_item = self._table.item(row, 0)
            v_item = self._table.item(row, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k:
                custom.append({"key": k, "value": v})
        if custom:
            result["custom"] = custom
        return result

    def _populate_table_from_dict(self, info: dict) -> None:
        """Write ``info`` values into the table widgets (standard + custom rows)."""
        # Standard rows (always present)
        for row, (_label, key) in enumerate(_PROJECT_INFO_FIELDS):
            item = self._table.item(row, 1)
            if item is None:
                self._table.setItem(row, 1, QTableWidgetItem(info.get(key, "")))
            else:
                item.setText(info.get(key, ""))

        # Remove any existing custom rows
        while self._table.rowCount() > len(_PROJECT_INFO_FIELDS):
            self._table.removeRow(self._table.rowCount() - 1)

        # Re-insert custom rows
        from PyQt6.QtCore import Qt
        for entry in info.get("custom", []):
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(entry.get("key", "")))
            self._table.setItem(r, 1, QTableWidgetItem(entry.get("value", "")))

    # ── Test helper ──────────────────────────────────────────────────────────

    def _set_field(self, key: str, value: str) -> None:
        """Set a standard field's value widget by dict-key name (for tests)."""
        for row, (_label, fkey) in enumerate(_PROJECT_INFO_FIELDS):
            if fkey == key:
                item = self._table.item(row, 1)
                if item is None:
                    self._table.setItem(row, 1, QTableWidgetItem(value))
                else:
                    item.setText(value)
                return
        raise KeyError(f"Unknown project-info field key: {key!r}")

    def _get_field(self, key: str) -> str:
        """Get a standard field's current widget value by dict-key name (for tests)."""
        for row, (_label, fkey) in enumerate(_PROJECT_INFO_FIELDS):
            if fkey == key:
                item = self._table.item(row, 1)
                return item.text() if item else ""
        raise KeyError(f"Unknown project-info field key: {key!r}")

    # ── SettingsPane protocol ─────────────────────────────────────────────────

    def load(self) -> None:
        """Snapshot current project-info dict and populate table widgets.

        Calls ``get_info()`` (or uses ``{}`` if not supplied) to obtain the
        current dict, takes a deep copy as the snapshot, then populates the
        table.  Custom rows are rebuilt from ``info["custom"]``.
        """
        info = dict(self._get_info() or {}) if self._get_info is not None else {}
        self._snapshot = dict(info)
        # Preserve nested custom list as a deep copy
        if "custom" in info:
            self._snapshot["custom"] = [dict(r) for r in info["custom"]]
        self._populate_table_from_dict(info)

    def apply(self) -> None:
        """Read widget state and call set_info(edited_dict).

        Does NOT touch QSettings.  If ``set_info`` was not supplied, the widget
        values are still read (allowing revert to work) but nothing is persisted.
        """
        edited = self._read_dict_from_table()
        if self._set_info is not None:
            self._set_info(edited)

    def revert(self) -> None:
        """Restore table widgets to the snapshot taken at load() time.

        Does NOT call set_info — revert must leave the project source untouched.
        """
        if not self._snapshot:
            return
        self._populate_table_from_dict(self._snapshot)


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
