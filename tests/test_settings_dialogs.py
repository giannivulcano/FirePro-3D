"""Tests for the settings package refactor.

Verifies that panes are importable from firepro3d.settings.panes, that
firepro3d.preferences_dialog still re-exports everything tests depend on,
and that the new SystemSettingsDialog / ProjectSettingsDialog work correctly.
"""


def test_panes_importable_from_settings_package(qapp):
    from firepro3d.settings.panes import (
        SettingsPane, UXPane, UnitsPane, ImportPane,
        GeneralPane, UIPane, ProjectInfoPane,
    )
    assert issubclass(UXPane, SettingsPane)


def test_preferences_dialog_shim_reexports(qapp):
    from firepro3d.preferences_dialog import (
        SnappingPane, UnitsPane, ImportPane, GeneralPane, UIPane,
        ProjectInfoPane, SettingsPane, _QSETTINGS_ORG, _QSETTINGS_APP,
    )
    from firepro3d.settings.panes import UXPane
    assert _QSETTINGS_ORG == "GV" and _QSETTINGS_APP == "FirePro3D"
    assert SnappingPane is UXPane


def test_uxpane_has_snap_align_halo_switchbar(qapp):
    from firepro3d.ui_kit import SwitchBar
    from firepro3d.settings.panes import UXPane
    p = UXPane()
    bars = p.findChildren(SwitchBar)
    assert bars, "UXPane must use a SwitchBar"
    assert set(bars[0]._btns.keys()) == {"snap", "align", "halo"}


def test_uxpane_snap_has_angle_no_grid(qapp):
    from firepro3d.settings.panes import UXPane
    p = UXPane()
    assert hasattr(p, "_angle_spin")
    assert not hasattr(p, "_grid_edit")   # grid-spacing removed


def test_uxpane_halo_reads_and_writes_live_scene(qapp, make_model_space):
    """The HALO toggle must read/write the scene's real `halo_enabled` attr
    (regression: it used a bogus `_halo_enabled`, so load() ignored the live
    state and apply() never wrote it)."""
    from firepro3d.settings.panes import UXPane
    scene = make_model_space()
    scene.halo_enabled = False
    p = UXPane(scene=scene)
    p.load()
    assert p._halo_enable.isChecked() is False   # load() read scene.halo_enabled
    p._halo_enable.setChecked(True)
    p.apply()
    assert scene.halo_enabled is True            # apply() wrote scene.halo_enabled


# ── New dialog tests ─────────────────────────────────────────────────────────

def test_system_settings_dialog_rail(qapp, make_model_space):
    from firepro3d.settings.system_settings_dialog import SystemSettingsDialog
    # make_model_space() returns a Model_Space (factory); the view is attached
    # internally but not returned.
    scene = make_model_space()
    view = getattr(scene, "_view_for_test", None)
    dlg = SystemSettingsDialog(scene=scene, view=view, snap_toolbar=None)
    assert dlg.rail_keys() == ["general", "ux", "ui", "import"]
    assert dlg._stack.count() == 4
    dlg.deleteLater()


def test_project_settings_dialog_rail_and_save_default(
        qapp, model_scene, tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings.project_settings_dialog import ProjectSettingsDialog
    scene = model_scene()
    dlg = ProjectSettingsDialog(
        scene=scene, get_info=lambda: {}, set_info=lambda d: None,
    )
    assert dlg.rail_keys() == ["project_info", "units"]
    # Drive the dialog widget so _apply_all() in _on_save_default() commits
    # the right value to the scene (not a direct scene mutation).
    units_pane = dlg._panes["units"]
    combo = units_pane._unit_combo
    imperial_idx = next(
        i for i in range(combo.count())
        if combo.itemText(i).startswith("Imperial")
    )
    combo.setCurrentIndex(imperial_idx)
    dlg._on_save_default()
    import os, json
    with open(os.path.join(str(tmp_path), "default.fpdt")) as f:
        assert json.load(f)["scale"]["display_unit"] == "imperial"
    dlg.deleteLater()
