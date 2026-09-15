"""Tests for the settings package refactor.

Verifies that panes are importable from firepro3d.settings.panes and that
firepro3d.preferences_dialog still re-exports everything tests depend on.
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
