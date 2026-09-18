"""
test_block_instance_level.py
============================
Containment contract C3: a model-placed BlockInstance is level-scoped — it
carries a level + Z/elevation offset, computes a z_range, is filtered by the
active level / view-range via LevelManager.apply_to_scene, exposes editable
Level/Offset/Rotation property rows, and round-trips both offset and level
through file + undo serialization.

These guards replace the retired test_geo2d_level_manager.py (which asserted the
pre-C3 contract that *primitives* were level-scoped).
"""

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.block_instance import BlockInstance


def _scene():
    s = Model_Space()
    s._level_manager = LevelManager()
    return s


def _inst(s, level="Level 1", offset=0.0):
    inst = BlockInstance(block_id="x", resolver=lambda _id: None,
                         level=level, level_offset_mm=offset)
    s._block_instances.append(inst)
    s.addItem(inst)
    return inst


def test_z_range_reflects_level_elevation_plus_offset(qapp):
    s = _scene()
    e1 = s._level_manager.get("Level 1").elevation
    inst = _inst(s, level="Level 1", offset=300.0)
    assert inst.z_range_mm() == (e1 + 300.0, e1 + 300.0)


def test_visible_only_on_active_level_without_view_range(qapp):
    s = _scene()
    inst = _inst(s, level="Level 1")
    s._level_manager.apply_to_scene(s, active_level="Level 2")
    assert inst.isVisible() is False
    s._level_manager.apply_to_scene(s, active_level="Level 1")
    assert inst.isVisible() is True


def test_appears_on_adjacent_level_when_in_view_range(qapp):
    s = _scene()
    inst = _inst(s, level="Level 1", offset=0.0)   # elevation 0
    # Viewing Level 2 with a range that dips below 0 includes the block.
    s._level_manager.apply_to_scene(
        s, active_level="Level 2", view_height=3000.0, view_depth=-500.0)
    assert inst.isVisible() is True


def test_hidden_when_offset_pushes_out_of_range(qapp):
    s = _scene()
    inst = _inst(s, level="Level 1", offset=5000.0)  # above view_height
    s._level_manager.apply_to_scene(
        s, active_level="Level 1", view_height=2896.0, view_depth=-1000.0)
    assert inst.isVisible() is False


def test_property_rows_present_and_offset_editable(qapp):
    s = _scene()
    inst = _inst(s, level="Level 1", offset=0.0)
    props = inst.get_properties()
    assert props["Level"]["type"] == "level_ref"
    assert props["Level"]["value"] == "Level 1"
    assert "Level Offset" in props
    assert "Rotation" in props
    e1 = s._level_manager.get("Level 1").elevation
    inst.set_property("Level Offset", 300.0)
    assert inst.z_range_mm() == (e1 + 300.0, e1 + 300.0)
    inst.set_property("Level", "Level 2")
    assert inst.level == "Level 2"


def test_offset_and_level_survive_file_roundtrip(qapp):
    s = _scene()
    inst = _inst(s, level="Level 2", offset=250.0)
    d = inst.to_dict()
    assert d["level"] == "Level 2"
    assert d["level_offset_mm"] == 250.0
    inst2 = BlockInstance.from_dict(d, resolver=lambda _id: None)
    assert inst2.level == "Level 2"
    assert inst2._level_offset_mm == 250.0


def test_offset_and_level_survive_undo_capture_restore(qapp):
    s = _scene()
    _inst(s, level="Level 2", offset=250.0)
    snap = s._capture_network()
    s._restore_network(snap)
    got = [i for i in s._block_instances]
    assert len(got) == 1
    assert got[0].level == "Level 2"
    assert got[0]._level_offset_mm == 250.0
