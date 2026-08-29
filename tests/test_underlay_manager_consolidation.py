import inspect
import firepro3d.dxf_preview_dialog as dpd


def test_import_dialog_has_no_level_combo():
    assert "_level_combo" not in inspect.getsource(dpd)
