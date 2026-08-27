"""Per-field tests for SnappingPane: live-apply, QSettings persistence, and Reset.

Isolation strategy: monkeypatch ``preferences_dialog.QSettings`` so every
internal ``QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)`` call inside the pane
returns an INI-backed instance writing to ``tmp_path``.  This avoids touching
the real Windows registry (NativeFormat) that the pane normally uses.

The ``snap_globals`` autouse fixture saves/restores ``snap_engine`` module
globals that apply() mutates, so tests don't leak state between each other.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings

from firepro3d import snap_engine
from firepro3d.preferences_dialog import (
    SnappingPane,
    _FACTORY_DEFAULTS,
    _SNAP_TYPES,
    _QSETTINGS_ORG,
    _QSETTINGS_APP,
)


# ── QSettings isolation ───────────────────────────────────────────────────────

@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Return a QSettings backed by a temp INI file.

    Monkeypatches ``preferences_dialog.QSettings`` so that any call to
    ``QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)`` inside the pane returns
    this isolated instance instead of the real Windows registry object.
    """
    ini_path = str(tmp_path / "snap_test.ini")
    settings_instance = QSettings(ini_path, QSettings.Format.IniFormat)

    import firepro3d.preferences_dialog as pd_mod

    def _fake_qsettings(org=None, app=None):
        # Called as QSettings(org, app) — always return our INI instance
        return settings_instance

    monkeypatch.setattr(pd_mod, "QSettings", _fake_qsettings)
    return settings_instance


# ── Module-global leak guard ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def snap_globals():
    """Save and restore snap_engine module globals mutated by apply()."""
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    saved_hyst = snap_engine.SNAP_HYSTERESIS_PX
    yield
    snap_engine.SNAP_TOLERANCE_PX = saved_tol
    snap_engine.SNAP_HYSTERESIS_PX = saved_hyst


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_pane(isolated_settings) -> SnappingPane:  # noqa: ANN001
    """Build a headless SnappingPane (no scene/view) and load it."""
    pane = SnappingPane()
    pane.load()
    return pane


# ── _FACTORY_DEFAULTS exported ────────────────────────────────────────────────

def test_factory_defaults_exported(qapp):
    """_FACTORY_DEFAULTS is a public dict with the expected keys."""
    required = {"tol_px", "hysteresis_px", "grip_px", "grid_mm", "angle_deg", "align"}
    required |= {attr for _, attr in _SNAP_TYPES}
    assert required.issubset(_FACTORY_DEFAULTS.keys())


# ── Aperture (formerly "snap radius") ────────────────────────────────────────

def test_aperture_applies_live(qapp, isolated_settings):
    """_tol_spin drives snap_engine.SNAP_TOLERANCE_PX on apply()."""
    pane = _make_pane(isolated_settings)
    pane._tol_spin.setValue(33)
    pane.apply()
    assert snap_engine.SNAP_TOLERANCE_PX == 33


def test_aperture_persists_to_qsettings(qapp, isolated_settings):
    """apply() writes snap/tolerance_px to QSettings."""
    pane = _make_pane(isolated_settings)
    pane._tol_spin.setValue(17)
    pane.apply()
    assert isolated_settings.value("snap/tolerance_px", type=int) == 17


# ── Hysteresis ────────────────────────────────────────────────────────────────

def test_hysteresis_applies_live(qapp, isolated_settings):
    """_hyst_spin drives snap_engine.SNAP_HYSTERESIS_PX on apply()."""
    pane = _make_pane(isolated_settings)
    pane._hyst_spin.setValue(6)
    pane.apply()
    assert snap_engine.SNAP_HYSTERESIS_PX == 6


def test_hysteresis_persists_to_qsettings(qapp, isolated_settings):
    """apply() writes snap/hysteresis_px to QSettings."""
    pane = _make_pane(isolated_settings)
    pane._hyst_spin.setValue(8)
    pane.apply()
    assert isolated_settings.value("snap/hysteresis_px", type=int) == 8


def test_hysteresis_roundtrip(qapp, isolated_settings):
    """Hysteresis written by apply() is readable back from QSettings."""
    pane = _make_pane(isolated_settings)
    pane._hyst_spin.setValue(5)
    pane.apply()
    # Simulate a fresh pane reading back persisted value
    snap_engine.SNAP_HYSTERESIS_PX = isolated_settings.value("snap/hysteresis_px", type=int)
    assert snap_engine.SNAP_HYSTERESIS_PX == 5


# ── Grip ─────────────────────────────────────────────────────────────────────

def test_grip_persists_to_qsettings(qapp, isolated_settings):
    """apply() writes snap/grip_tolerance_px to QSettings."""
    pane = _make_pane(isolated_settings)
    pane._grip_spin.setValue(300)
    pane.apply()
    assert isolated_settings.value("snap/grip_tolerance_px", type=int) == 300


# ── Grid ──────────────────────────────────────────────────────────────────────

def test_grid_persists_to_qsettings(qapp, isolated_settings):
    """apply() writes snap/grid_size to QSettings."""
    pane = _make_pane(isolated_settings)
    pane._grid_edit.set_value_mm(50.0)
    pane.apply()
    val = isolated_settings.value("snap/grid_size", type=float)
    assert val == pytest.approx(50.0)


# ── Angle snap ────────────────────────────────────────────────────────────────

def test_angle_persists_to_qsettings(qapp, isolated_settings):
    """apply() writes snap/angle_deg to QSettings."""
    pane = _make_pane(isolated_settings)
    pane._angle_spin.setValue(30)
    pane.apply()
    assert isolated_settings.value("snap/angle_deg", type=int) == 30


# ── Snap-type checkboxes (all 8) ──────────────────────────────────────────────

@pytest.mark.parametrize("attr", [attr for _, attr in _SNAP_TYPES])
def test_snap_type_persists_to_qsettings(qapp, isolated_settings, attr):
    """Each snap-type checkbox writes its snap/<attr> key on apply()."""
    pane = _make_pane(isolated_settings)
    cb = pane._snap_cbs[attr]
    original = cb.isChecked()
    cb.setChecked(not original)
    pane.apply()
    saved = isolated_settings.value(f"snap/{attr}")
    # QSettings may return bool or str on different platforms
    if isinstance(saved, str):
        saved = saved.lower() not in ("false", "0")
    assert bool(saved) is (not original)


def test_all_snap_types_persist(qapp, isolated_settings):
    """All 8 snap-type checkboxes persist their new values simultaneously."""
    pane = _make_pane(isolated_settings)
    # Uncheck all
    for attr, cb in pane._snap_cbs.items():
        cb.setChecked(False)
    pane.apply()
    for _, attr in _SNAP_TYPES:
        saved = isolated_settings.value(f"snap/{attr}")
        if isinstance(saved, str):
            saved = saved.lower() not in ("false", "0")
        assert bool(saved) is False, f"snap/{attr} should be False"


# ── Inference ─────────────────────────────────────────────────────────────────

def test_align_persists_to_qsettings(qapp, isolated_settings):
    """apply() writes align/enabled to QSettings."""
    pane = _make_pane(isolated_settings)
    pane._align_cb.setChecked(False)
    pane.apply()
    saved = isolated_settings.value("align/enabled")
    if isinstance(saved, str):
        saved = saved.lower() not in ("false", "0")
    assert bool(saved) is False


# ── Reset to Defaults ─────────────────────────────────────────────────────────

def test_reset_restores_all_factory_defaults(qapp, isolated_settings):
    """reset_to_defaults() sets every widget to _FACTORY_DEFAULTS AND live-applies."""
    pane = _make_pane(isolated_settings)

    # Dirty every field
    pane._tol_spin.setValue(99)
    pane._hyst_spin.setValue(9)
    pane._grip_spin.setValue(500)
    pane._angle_spin.setValue(15)
    for attr, cb in pane._snap_cbs.items():
        cb.setChecked(False)
    pane._align_cb.setChecked(False)

    pane.reset_to_defaults()

    # Widget values match factory
    assert pane._tol_spin.value() == _FACTORY_DEFAULTS["tol_px"]
    assert pane._hyst_spin.value() == _FACTORY_DEFAULTS["hysteresis_px"]
    assert pane._grip_spin.value() == _FACTORY_DEFAULTS["grip_px"]
    assert pane._angle_spin.value() == int(_FACTORY_DEFAULTS["angle_deg"])
    assert pane._align_cb.isChecked() is _FACTORY_DEFAULTS["align"]
    for attr, cb in pane._snap_cbs.items():
        assert cb.isChecked() is True, f"snap_cb[{attr}] should be checked after reset"

    # Live engine globals also reset
    assert snap_engine.SNAP_TOLERANCE_PX == _FACTORY_DEFAULTS["tol_px"]
    assert snap_engine.SNAP_HYSTERESIS_PX == _FACTORY_DEFAULTS["hysteresis_px"]


def test_reset_live_applies_tol_and_hyst(qapp, isolated_settings):
    """reset_to_defaults() live-applies tol and hyst regardless of prior widget state."""
    pane = _make_pane(isolated_settings)
    snap_engine.SNAP_TOLERANCE_PX = 99
    snap_engine.SNAP_HYSTERESIS_PX = 99
    pane.reset_to_defaults()
    assert snap_engine.SNAP_TOLERANCE_PX == _FACTORY_DEFAULTS["tol_px"]
    assert snap_engine.SNAP_HYSTERESIS_PX == _FACTORY_DEFAULTS["hysteresis_px"]


def test_reset_persists_via_apply(qapp, isolated_settings):
    """reset_to_defaults() calls apply(), so factory values land in QSettings."""
    pane = _make_pane(isolated_settings)
    pane.reset_to_defaults()
    assert isolated_settings.value("snap/tolerance_px", type=int) == _FACTORY_DEFAULTS["tol_px"]
    assert isolated_settings.value("snap/hysteresis_px", type=int) == _FACTORY_DEFAULTS["hysteresis_px"]


# ── Revert ────────────────────────────────────────────────────────────────────

def test_revert_restores_hysteresis(qapp, isolated_settings):
    """revert() restores snap_engine.SNAP_HYSTERESIS_PX to the load()-time snapshot."""
    snap_engine.SNAP_HYSTERESIS_PX = 7
    pane = _make_pane(isolated_settings)  # load() snapshots SNAP_HYSTERESIS_PX = 7
    pane._hyst_spin.setValue(12)
    pane.apply()
    assert snap_engine.SNAP_HYSTERESIS_PX == 12
    pane.revert()
    assert snap_engine.SNAP_HYSTERESIS_PX == 7
    assert pane._hyst_spin.value() == 7


def test_revert_restores_tol(qapp, isolated_settings):
    """revert() restores SNAP_TOLERANCE_PX to the load()-time value."""
    snap_engine.SNAP_TOLERANCE_PX = 25
    pane = _make_pane(isolated_settings)
    pane._tol_spin.setValue(80)
    pane.apply()
    pane.revert()
    assert snap_engine.SNAP_TOLERANCE_PX == 25


# ── Live-scene apply / reset coverage ────────────────────────────────────────

def test_apply_pushes_all_fields_to_live_scene(qapp, isolated_settings, make_model_space):
    """apply() with a live scene+view pushes EVERY guarded field to the live objects.

    This test covers the ``if self._scene is not None`` branches that the
    headless-pane tests cannot reach — catching any "1-of-N settings didn't
    apply live" regression.
    """
    from firepro3d.model_view import Model_View

    ms = make_model_space()
    view = Model_View(ms)

    pane = SnappingPane(scene=ms, view=view)
    pane.load()

    # Set clearly non-default widget values
    pane._tol_spin.setValue(25)
    pane._hyst_spin.setValue(7)
    pane._grip_spin.setValue(300)
    pane._angle_spin.setValue(30)
    pane._snap_cbs["snap_endpoint"].setChecked(False)
    pane._align_cb.setChecked(False)

    pane.apply()

    # Module globals (always live)
    assert snap_engine.SNAP_TOLERANCE_PX == 25
    assert snap_engine.SNAP_HYSTERESIS_PX == 7

    # Live scene attributes (guarded branches)
    assert getattr(ms, "_grip_tolerance_px", None) == 300
    assert ms._snap_angle_deg == 30
    assert ms._snap_engine.snap_endpoint is False
    assert ms._align_enabled is False


def test_reset_pushes_factory_to_live_scene(qapp, isolated_settings, make_model_space):
    """reset_to_defaults() via apply() pushes factory values to the live engine.

    Verifies that the reset path (which calls apply()) also reaches the
    live-scene guarded branches, not just the module globals.
    """
    from firepro3d.model_view import Model_View

    ms = make_model_space()
    view = Model_View(ms)

    # Dirty the live engine before constructing the pane
    ms._snap_engine.snap_endpoint = False
    ms._snap_angle_deg = 15
    ms._grip_tolerance_px = 500

    pane = SnappingPane(scene=ms, view=view)
    pane.load()

    pane.reset_to_defaults()

    # Live engine must now reflect factory values
    assert ms._snap_engine.snap_endpoint is True
    assert ms._snap_angle_deg == _FACTORY_DEFAULTS["angle_deg"]
    assert getattr(ms, "_grip_tolerance_px", None) == _FACTORY_DEFAULTS["grip_px"]

    # Module globals also reset
    assert snap_engine.SNAP_TOLERANCE_PX == _FACTORY_DEFAULTS["tol_px"]
    assert snap_engine.SNAP_HYSTERESIS_PX == _FACTORY_DEFAULTS["hysteresis_px"]


# ── Label / widget existence ──────────────────────────────────────────────────

def test_hyst_spin_exists(qapp):
    """SnappingPane has a _hyst_spin attribute after construction."""
    pane = SnappingPane()
    assert hasattr(pane, "_hyst_spin"), "_hyst_spin widget must exist on SnappingPane"


def test_reset_button_callable(qapp):
    """reset_to_defaults is a callable method on SnappingPane."""
    pane = SnappingPane()
    assert callable(getattr(pane, "reset_to_defaults", None))
