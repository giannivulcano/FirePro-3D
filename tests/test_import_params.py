from firepro3d.dxf_preview_dialog import ImportParams


def test_import_params_defaults():
    p = ImportParams()
    assert p.levels == []          # populated by the dialog from current_level
    assert p.scale_verified is False
