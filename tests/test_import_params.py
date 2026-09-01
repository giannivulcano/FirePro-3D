from firepro3d.underlay_import_dialog import ImportParams


def test_import_params_defaults():
    p = ImportParams()
    assert p.levels == []          # populated by the dialog from current_level
    assert p.scale_verified is False


def test_levels_helper_prefers_params_over_active():
    from firepro3d.model_space import _record_levels
    p = ImportParams()
    p.levels = ["Level 1", "Level 2"]
    assert _record_levels(p, active="Level 1") == ["Level 1", "Level 2"]


def test_levels_helper_falls_back_to_active_when_empty():
    from firepro3d.model_space import _record_levels
    assert _record_levels(ImportParams(), active="Level 3") == ["Level 3"]
