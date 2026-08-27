from PyQt6.QtCore import QPointF
from firepro3d.floor_slab import FloorSlab


def _square():
    return [QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)]


def test_new_schema_roundtrip_byte_identical():
    s = FloorSlab(points=_square())
    s._top_mode = "level"; s._top_level = "Level 2"; s._top_offset_mm = -50.0
    s._bottom_mode = "absolute"; s._bottom_abs_z_mm = 100.0
    d1 = s.to_dict()
    d2 = FloorSlab.from_dict(d1).to_dict()
    assert d1 == d2


def test_legacy_migration_maps_to_two_boundary():
    legacy = {"type": "floor_slab", "points": [[0, 0], [1000, 0], [1000, 1000], [0, 1000]],
              "color": "#8888cc", "thickness_mm": 203.2, "level": "Level 2",
              "level_offset_mm": -25.0, "name": "Slab 1"}
    s = FloorSlab.from_dict(legacy)
    assert s._top_mode == "level" and s._top_level == "Level 2" and s._top_offset_mm == -25.0
    assert s._bottom_mode == "thickness" and s._thickness_mm == 203.2 and s.name == "Slab 1"


def test_resave_drops_legacy_keys():
    legacy = {"type": "floor_slab", "points": [[0, 0], [1000, 0], [0, 1000]],
              "thickness_mm": 152.4, "level": "Level 1", "level_offset_mm": 0.0}
    d = FloorSlab.from_dict(legacy).to_dict()
    assert "level_offset_mm" not in d and "thickness_ft" not in d
    assert "level" not in d
    assert d["top_mode"] == "level" and d["bottom_mode"] == "thickness"


def test_legacy_thickness_ft_converted():
    legacy = {"type": "floor_slab", "points": [[0, 0], [1000, 0], [0, 1000]],
              "thickness_ft": 0.5, "level": "Level 1"}
    s = FloorSlab.from_dict(legacy)
    assert abs(s._thickness_mm - 152.4) < 1e-6


def test_legacy_zrange_parity():
    from tests.test_floor_elevation_model import _FakeLM, _FakeScene
    lm = _FakeLM({"Level 1": 0.0})
    legacy = {"type": "floor_slab", "points": [[0, 0], [1000, 0], [0, 1000]],
              "thickness_mm": 152.4, "level": "Level 1", "level_offset_mm": 0.0}
    s = FloorSlab.from_dict(legacy)
    s._scene = _FakeScene(lm)
    assert s.z_range_mm() == (-152.4, 0.0)


def test_undo_path_preserves_floor_slab(qapp):
    """Dual-path parity: _capture_network/_restore_network round-trip the new
    two-boundary schema for FloorSlab (both delegate to to_dict/from_dict)."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    s = FloorSlab(points=_square())
    s._top_mode = "level"; s._top_level = "Level 2"; s._top_offset_mm = -50.0
    s._bottom_mode = "absolute"; s._bottom_abs_z_mm = 100.0
    s.name = "Slab X"
    before = s.to_dict()
    scene.addItem(s); scene._floor_slabs.append(s)
    snap = scene._capture_network()
    scene._restore_network(snap)
    assert len(scene._floor_slabs) == 1
    assert scene._floor_slabs[0].to_dict() == before
