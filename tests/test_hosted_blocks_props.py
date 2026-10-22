"""G13 rows + D10 re-host (keep offset value, keep h, keep elevation)."""
import pytest
from PyQt6.QtWidgets import QApplication

from firepro3d import hosted_blocks as hb
from firepro3d.property_manager import PropertyManager
from tests._hosted_blocks_helpers import gridline, defn


def _setup(ms):
    b = gridline(ms, (0, -3000), (6000, -3000), "B")
    c = gridline(ms, (6000, -5000), (0, -5000), "C")         # anti-parallel
    gridline(ms, (500, 0), (500, -6000), "1")                # perpendicular
    inst = ms.place_block_instance(defn(ms).id, (0, 0), host={
        "gridline": b._uid, "offset_mm": 200.0, "along_mm": 1500.0,
        "elevation_mm": 2400.0, "facing": 1})
    return b, c, inst


def test_rows(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    p = inst.get_properties()
    assert "Level" not in p and "Level Offset" not in p
    assert p["Reference"]["type"] == "enum"
    assert p["Reference"]["value"] == "B"
    assert p["Reference"]["options"] == ["B", "C"]           # parallel only
    assert p["Offset"]["value_mm"] == 200.0
    assert p["Elevation"]["value_mm"] == 2400.0
    assert list(p)[:4] == ["Type", "Reference", "Offset", "Elevation"]


def test_unhosted_rows_unchanged(qapp, make_model_space):
    ms = make_model_space()
    inst = ms.place_block_instance(defn(ms).id, (0, 0))
    p = inst.get_properties()
    assert "Level" in p and "Level Offset" in p and "Reference" not in p


def test_gridlines_parallel(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    perp = ms._gridlines[2]
    assert hb.gridlines_parallel(b, c) and not hb.gridlines_parallel(b, perp)


def test_offset_elevation_reference_edits(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    inst.set_property("Offset", 300.0)
    assert inst.block_pos() == pytest.approx((1500.0, -3300.0))
    inst.set_property("Elevation", 1000.0)
    assert inst.z_range_mm() == (1000.0, 1000.0)
    inst.set_property("Reference", "C")
    # W(offset 0) = (1500, 3000); C origin (6000, 5000), u=(-1,0): along = 4500;
    # n_B.n_C = -1 -> facing -1; offset 300 kept on n_C=(0,-1): world (1500, 4700)
    assert inst.host == {"gridline": c._uid, "offset_mm": 300.0,
                         "along_mm": pytest.approx(4500.0),
                         "elevation_mm": 1000.0, "facing": -1}
    assert inst.block_pos() == pytest.approx((1500.0, -4700.0))


def _commit(inst, key, value):
    pm = PropertyManager()
    pm.show_properties(inst)
    QApplication.processEvents()
    pm._apply_property(key, value)


@pytest.mark.parametrize("key,value,field,new", [
    ("Offset", 300.0, "offset_mm", 300.0),
    ("Elevation", 1000.0, "elevation_mm", 1000.0),
])
def test_each_edit_is_one_undo_step(qapp, make_model_space, key, value, field, new):
    ms = make_model_space(); b, c, inst = _setup(ms)
    ms.push_undo_state()
    depth0 = ms._undo_pos
    old = inst.host[field]
    _commit(inst, key, value)
    assert inst.host[field] == new
    assert ms._undo_pos == depth0 + 1
    ms.undo()
    (now,) = ms._block_instances
    assert now.host[field] == old
    assert now.host["offset_mm"] == (200.0 if field != "offset_mm" else old)


def test_reference_edit_is_one_undo_step(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    ms.push_undo_state()
    depth0 = ms._undo_pos
    _commit(inst, "Reference", "C")
    assert inst.host["gridline"] == c._uid
    assert ms._undo_pos == depth0 + 1
    ms.undo()
    (now,) = ms._block_instances
    assert now.host["gridline"] == b._uid and now.host["offset_mm"] == 200.0


def test_noop_commit_is_no_step(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    ms.push_undo_state()
    depth0 = ms._undo_pos
    _commit(inst, "Offset", 200.0)
    assert ms._undo_pos == depth0
