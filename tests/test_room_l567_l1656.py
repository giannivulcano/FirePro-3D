"""G7 (AC12 L567, AC13 L1656). Raw sources: 6000 x 4000 scene units at pixels_per_mm 2 =
3000 x 2000 mm (area 6.0e6 mm2, perimeter 10000 mm); LevelManager defaults Level 1 @ 0,
Level 2 @ 3048 (1b probe_out6); 1 sq ft = 304.8**2 mm2."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.room import Room

RECT = [QPointF(0, 0), QPointF(6000, 0), QPointF(6000, 4000), QPointF(0, 4000)]


def test_l567_panel_area_perimeter_volume_coverage_calibrated(qapp, make_model_space):
    from firepro3d import element_params as ep
    from firepro3d.level_manager import LevelManager
    ms = make_model_space()
    ms._level_manager = LevelManager()
    ms.scale_manager.set_pixels_per_mm(2.0)
    r = Room(list(RECT))
    r.level, r._ceiling_level = "Level 1", "Level 2"
    ms.addItem(r)
    ms._rooms.append(r)
    n = ms.add_node(3000, 2000)
    ms.add_sprinkler(n)
    n.z_pos = 1000.0                                  # premise: inside the room's z range (0..3048)
    props = r.get_properties()
    sm = ms.scale_manager
    assert props["Area"]["value"] == sm.format_area_mm2(6.0e6)
    assert props["Perimeter"]["value"] == sm.format_length(10000.0)
    assert props["Volume"]["value"] == sm.format_volume_mm3(6.0e6 * 3048.0)
    assert props["Coverage/Sprinkler"]["value"] == f"{6.0e6 / 304.8 ** 2:.1f} sq ft"     # 64.6
    assert ep.host_values(r)["Area"].raw == pytest.approx(6.0e6)                       # AC12 parity


def test_l567_auto_populate_area_label_calibrated(qapp, make_model_space, tmp_path):
    import os
    from firepro3d.auto_populate_dialog import AutoPopulateDialog
    from firepro3d.sprinkler_db import SprinklerDatabase
    ms = make_model_space()
    ms.scale_manager.set_pixels_per_mm(2.0)
    r = Room(list(RECT))
    ms.addItem(r)
    ms._rooms.append(r)
    db = SprinklerDatabase(path=os.path.join(str(tmp_path), "sprinklers.json"))
    dlg = AutoPopulateDialog(room=r, sprinkler_db=db)
    assert dlg._room_area_sqft == pytest.approx(6.0e6 / 304.8 ** 2)


@pytest.mark.parametrize("floor,ceil,want_h", [("Level 1", "Level 2", 3048.0 - 300.0),
                                                ("Level 0", "Level 1", 3048.0)],
                         ids=["slab_at_ceiling", "slab_elsewhere"])
def test_l1656_ceiling_slab_matched_by_top_level(qapp, floor, ceil, want_h):
    """A 300 mm slab topped at Level 2 (its retired .level stays the 'Level 1' default):
    it is the ceiling slab of a Level 1 -> Level 2 room (3048 - 300 = 2748, 1b probe 7) and
    of no Level 0 -> Level 1 room (0 - (-3048) = 3048)."""
    from firepro3d.floor_slab import FloorSlab
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    lm = LevelManager()
    ms._level_manager = lm
    lm.add_level("Level 0", elevation=-3048.0)
    slab = FloorSlab([QPointF(0, 0), QPointF(5000, 0), QPointF(5000, 5000)])
    slab._top_level = "Level 2"
    slab._thickness_mm = 300.0
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    assert slab.z_range_mm() == pytest.approx((2748.0, 3048.0))     # premise (1b probe 7)
    r = Room([QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000)])
    ms.addItem(r)
    ms._rooms.append(r)
    r.level, r._ceiling_level, r._ceiling_offset = floor, ceil, 0.0
    floor_z = lm.get(floor).elevation
    assert r._ceiling_height_mm() == pytest.approx(want_h)
    assert r.z_range_mm() == pytest.approx((floor_z, floor_z + want_h))
