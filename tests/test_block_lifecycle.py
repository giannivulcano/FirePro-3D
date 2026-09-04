"""Registry, serialization, undo, and retirement guard tests (Block system S1)."""
import pytest
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance


def _def(name="A"):
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def test_register_and_place(model_space):
    d = _def()
    model_space.register_block_definition(d)
    assert model_space.get_block_definition(d.id) is d
    inst = model_space.place_block_instance(d.id, (10.0, 20.0), rotation=0.0)
    assert inst in model_space._block_instances
    assert inst.scene() is model_space


def test_definition_edit_propagates_to_instances(model_space):
    d = _def()
    model_space.register_block_definition(d)
    a = model_space.place_block_instance(d.id, (0.0, 0.0))
    b = model_space.place_block_instance(d.id, (50.0, 0.0))
    w_before = a.boundingRect().width()
    d.set_primitives([{"type": "draw_line", "pt1": [0, 0], "pt2": [300, 0],
                       "color": "#ffffff", "lineweight": 1.0}])
    assert a.boundingRect().width() > w_before
    assert abs(a.boundingRect().width() - b.boundingRect().width()) < 1e-6


def test_project_round_trip_blocks(model_space, tmp_path):
    d = _def("RoundTrip")
    model_space.register_block_definition(d)
    model_space.place_block_instance(d.id, (12.0, 34.0), rotation=45.0, level="Level 3")
    fpath = str(tmp_path / "proj.fpd")
    assert model_space.save_to_file(fpath)

    from firepro3d.model_space import Model_Space
    ms2 = Model_Space()
    ms2.load_from_file(fpath)
    assert d.id in ms2._block_definitions
    assert len(ms2._block_instances) == 1
    inst = ms2._block_instances[0]
    assert inst.block_pos() == (12.0, 34.0)
    assert inst.block_rotation() == 45.0
    assert inst.level == "Level 3"
    assert inst.definition().id == d.id


def test_portability_library_absent(model_space, tmp_path):
    d = _def("Portable")
    model_space.register_block_definition(d)
    model_space.place_block_instance(d.id, (0.0, 0.0))
    fpath = str(tmp_path / "p.fpd")
    model_space.save_to_file(fpath)
    from firepro3d.model_space import Model_Space
    ms2 = Model_Space()
    ms2.load_from_file(fpath)
    assert ms2._block_instances[0].definition() is not None


def test_place_then_undo_removes_instance(model_space):
    d = _def("Undoable")
    model_space.register_block_definition(d)
    model_space.push_undo_state()            # baseline: def present, no instances
    model_space.place_block_instance(d.id, (0.0, 0.0))
    model_space.push_undo_state()            # after placing the instance
    assert len(model_space._block_instances) == 1
    model_space.undo()
    assert len(model_space._block_instances) == 0
    model_space.redo()
    assert len(model_space._block_instances) == 1


def test_blockitem_symbol_retired():
    import firepro3d
    with pytest.raises(AttributeError):
        _ = firepro3d.BlockItem


def test_app_imports_clean():
    import subprocess, sys, os
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, "-c", "import main"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"import main failed:\n{r.stderr}"
