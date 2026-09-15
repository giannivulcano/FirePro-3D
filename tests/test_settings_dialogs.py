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
