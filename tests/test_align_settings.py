"""Per-knob tests for the Preferences SNAP-pane ALIGN settings.

The 1-of-6 lesson: EVERY ALIGN knob must (a) live-apply to the running seam,
(b) round-trip through QSettings, and (c) be restored by Reset-to-Defaults.
Each knob below is covered on all three axes.

Isolation: monkeypatch ``preferences_dialog.QSettings`` so the pane's internal
``QSettings(org, app)`` calls write to a temp INI (never the Windows registry).
The ``model_space`` fixture supplies a live ``Model_Space`` with an
``AlignController`` so live-apply asserts against observable state
(``_align_controller.dwell_ms`` etc.), not just widget values.
"""

from __future__ import annotations

import pytest

from firepro3d.preferences_dialog import SnappingPane
from firepro3d.constants import (
    ALIGN_PATH_TOL_PX, ALIGN_DWELL_MS, ALIGN_MAX_POINTS,
    ALIGN_DIR_HV_DEFAULT, ALIGN_DIR_EXTENSION_DEFAULT, ALIGN_DIR_PARALLEL_DEFAULT,
    ALIGN_DIR_PERPENDICULAR_DEFAULT,
)


@pytest.fixture
def patched_qsettings(tmp_settings, monkeypatch):
    """Redirect the pane's internal QSettings(org, app) to the temp INI."""
    import firepro3d.preferences_dialog as pd_mod

    def _fake_qsettings(org=None, app=None):
        return tmp_settings

    monkeypatch.setattr(pd_mod, "QSettings", _fake_qsettings)
    return tmp_settings


@pytest.fixture
def pane(model_space, patched_qsettings):
    """A loaded SnappingPane bound to the live model_space + temp QSettings."""
    p = SnappingPane(scene=model_space)
    p.load()
    return p


# ── path-tolerance ─────────────────────────────────────────────────────────────

def test_path_tol_live_applies(qapp, pane, model_space):
    pane.set_align_path_tol(35)
    pane.apply()
    assert model_space._align_path_tol_px == 35


def test_path_tol_roundtrips(qapp, pane, patched_qsettings):
    pane.set_align_path_tol(35)
    pane.apply()
    assert patched_qsettings.value("align/path_tol_px", type=int) == 35


def test_path_tol_reset_restores_factory(qapp, pane, model_space):
    pane.set_align_path_tol(99)
    pane.reset_to_defaults()
    assert model_space._align_path_tol_px == ALIGN_PATH_TOL_PX


# ── dwell ──────────────────────────────────────────────────────────────────────

def test_dwell_live_applies(qapp, pane, model_space):
    pane.set_align_dwell(250)
    pane.apply()
    assert model_space._align_controller.dwell_ms == 250


def test_dwell_roundtrips(qapp, pane, patched_qsettings):
    pane.set_align_dwell(250)
    pane.apply()
    assert patched_qsettings.value("align/dwell_ms", type=int) == 250


def test_dwell_reset_restores_factory(qapp, pane, model_space):
    pane.set_align_dwell(999)
    pane.reset_to_defaults()
    assert model_space._align_controller.dwell_ms == ALIGN_DWELL_MS


# ── max-points ─────────────────────────────────────────────────────────────────

def test_max_points_live_applies(qapp, pane, model_space):
    pane.set_align_max_points(3)
    pane.apply()
    assert model_space._align_controller.max_points == 3


def test_max_points_roundtrips(qapp, pane, patched_qsettings):
    pane.set_align_max_points(3)
    pane.apply()
    assert patched_qsettings.value("align/max_points", type=int) == 3


def test_max_points_reset_restores_factory(qapp, pane, model_space):
    pane.set_align_max_points(2)
    pane.reset_to_defaults()
    assert model_space._align_controller.max_points == ALIGN_MAX_POINTS


# ── per-direction toggles (H/V, Extension, Parallel) ──────────────────────────

def test_hv_toggle_live_applies(qapp, pane, model_space):
    pane.set_align_hv_enabled(False)
    pane.apply()
    assert model_space._align_controller.dir_hv_enabled is False


def test_hv_toggle_roundtrips(qapp, pane, patched_qsettings):
    pane.set_align_hv_enabled(False)
    pane.apply()
    assert patched_qsettings.value("align/dir_hv", type=bool) is False


def test_hv_toggle_reset_restores_factory(qapp, pane, model_space):
    pane.set_align_hv_enabled(False)
    pane.reset_to_defaults()
    assert model_space._align_controller.dir_hv_enabled is ALIGN_DIR_HV_DEFAULT


def test_extension_toggle_live_applies(qapp, pane, model_space):
    pane.set_align_extension_enabled(False)
    pane.apply()
    assert model_space._align_controller.dir_extension_enabled is False


def test_extension_toggle_roundtrips(qapp, pane, patched_qsettings):
    pane.set_align_extension_enabled(False)
    pane.apply()
    assert patched_qsettings.value("align/dir_extension", type=bool) is False


def test_extension_toggle_reset_restores_factory(qapp, pane, model_space):
    pane.set_align_extension_enabled(False)
    pane.reset_to_defaults()
    assert (model_space._align_controller.dir_extension_enabled
            is ALIGN_DIR_EXTENSION_DEFAULT)


def test_parallel_toggle_live_applies(qapp, pane, model_space):
    pane.set_align_parallel_enabled(False)
    pane.apply()
    assert model_space._align_controller.dir_parallel_enabled is False


def test_parallel_toggle_roundtrips(qapp, pane, patched_qsettings):
    pane.set_align_parallel_enabled(False)
    pane.apply()
    assert patched_qsettings.value("align/dir_parallel", type=bool) is False


def test_parallel_toggle_reset_restores_factory(qapp, pane, model_space):
    pane.set_align_parallel_enabled(False)
    pane.reset_to_defaults()
    assert (model_space._align_controller.dir_parallel_enabled
            is ALIGN_DIR_PARALLEL_DEFAULT)


def test_perpendicular_toggle_live_applies(qapp, pane, model_space):
    pane.set_align_perpendicular_enabled(False)
    pane.apply()
    assert model_space._align_controller.dir_perpendicular_enabled is False


def test_perpendicular_toggle_roundtrips(qapp, pane, patched_qsettings):
    pane.set_align_perpendicular_enabled(False)
    pane.apply()
    assert patched_qsettings.value("align/dir_perpendicular", type=bool) is False


def test_perpendicular_toggle_reset_restores_factory(qapp, pane, model_space):
    pane.set_align_perpendicular_enabled(False)
    pane.reset_to_defaults()
    assert (model_space._align_controller.dir_perpendicular_enabled
            is ALIGN_DIR_PERPENDICULAR_DEFAULT)


# ── master ALIGN on/off ────────────────────────────────────────────────────────

def test_master_live_applies(qapp, pane, model_space):
    pane.set_align_master(False)
    pane.apply()
    assert model_space._align_enabled is False


def test_master_roundtrips(qapp, pane, patched_qsettings):
    pane.set_align_master(False)
    pane.apply()
    assert patched_qsettings.value("align/enabled", type=bool) is False


def test_master_reset_restores_factory(qapp, pane, model_space):
    pane.set_align_master(False)
    pane.reset_to_defaults()
    assert model_space._align_enabled is True


# ── per-direction gating actually reaches build_rays ──────────────────────────

def test_disabled_hv_omits_hv_rays(qapp, pane, model_space):
    """Ground truth: turning H/V off means build_rays emits no hv rays."""
    pane.set_align_hv_enabled(False)
    pane.apply()
    ctrl = model_space._align_controller
    ctrl.on_move((0.0, 0.0),
                 {"point": (0.0, 0.0), "snap_type": "midpoint",
                  "source_id": 1, "direction": None}, elapsed_ms=500)
    rays = ctrl.build_rays(active_point=(0.0, 0.0))
    assert all(r.kind != "hv" for r in rays)
