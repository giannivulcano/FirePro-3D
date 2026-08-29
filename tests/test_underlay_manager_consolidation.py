import inspect
import firepro3d.dxf_preview_dialog as dpd
import firepro3d.display_manager as dm


def test_import_dialog_has_no_level_combo():
    assert "_level_combo" not in inspect.getsource(dpd)


def test_display_manager_has_no_underlays_tab():
    src = inspect.getsource(dm)
    assert "_build_underlays_tab" not in src
    assert "_underlay_snapshot" not in src
    assert "hidden_in_views" not in src
