import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_no_grid_dialog_module():
    import importlib
    try:
        importlib.import_module("firepro3d.grid_lines_dialog")
        assert False, "grid_lines_dialog should be deleted"
    except ModuleNotFoundError:
        pass


def test_default_seed_places_gridlines(qapp):
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    specs = {"gridlines": [
        {"offset": 0.0, "length": 21945.6, "angle_deg": 90.0, "label": "1"},
        {"offset": 7315.2, "length": 21945.6, "angle_deg": 90.0, "label": "2"},
    ]}
    scene.place_grid_lines(specs)
    assert len(scene._gridlines) == 2
