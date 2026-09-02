from firepro3d.underlay import Underlay


def test_name_roundtrips():
    u = Underlay(type="dxf", path="/x/floor.dxf", name="Ground Floor")
    d = u.to_dict()
    assert d["name"] == "Ground Floor"
    assert Underlay.from_dict(d).name == "Ground Floor"


def test_name_defaults_empty_and_optional_in_dict():
    u = Underlay(type="dxf", path="/x/floor.dxf")
    assert u.name == ""
    d = u.to_dict()
    d.pop("name", None)          # old projects lack "name"
    assert Underlay.from_dict(d).name == ""


def test_import_params_carries_name(qapp):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None, levels=["Level 1"], current_level="Level 1")
    dlg._name_edit.setText("  Ground Floor  ")
    assert dlg.get_import_params().name == "Ground Floor"   # stripped
    dlg._name_edit.setText("")
    assert dlg.get_import_params().name == ""


def test_manager_name_prefers_field_over_basename():
    from firepro3d.underlay import Underlay
    from firepro3d import underlay_manager
    rec = Underlay(type="pdf", path="/a/sheet-A1.pdf", name="Level 2 Plan")
    assert underlay_manager._DetailsPanel._name(rec) == "Level 2 Plan"
    rec2 = Underlay(type="pdf", path="/a/sheet-A1.pdf")
    assert underlay_manager._DetailsPanel._name(rec2) == "sheet-A1.pdf"


def test_manager_model_name_helper():
    from firepro3d.underlay import Underlay
    from firepro3d.underlay_manager_model import _record_name
    assert _record_name(
        Underlay(type="pdf", path="/a/sheet-A1.pdf", name="  Level 2 Plan  ")
    ) == "Level 2 Plan"
    assert _record_name(
        Underlay(type="pdf", path="/a/sheet-A1.pdf")) == "sheet-A1.pdf"

