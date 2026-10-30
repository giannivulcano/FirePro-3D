"""view-relationships section 12.4 — LevelManager order / Add / Delete rules (Level Manager task)."""
import json

from PyQt6.QtCore import QPointF

from firepro3d.constants import DEFAULT_LEVEL_GAP_MM
from firepro3d.floor_slab import FloorSlab
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment


def _lm(*rows):
    """rows: (name, elevation_mm, number) in FILE order."""
    lm = LevelManager()
    lm.from_list([{"name": n, "elevation_mm": e, "number": k} for n, e, k in rows])
    return lm


def _names(lm):
    return [l.name for l in lm.levels]


def test_from_list_resorts_an_out_of_order_file_and_keeps_fields():
    lm = _lm(("Roof", 9000.0, 3), ("Ground", 0.0, 1), ("Mid", 4000.0, 2))
    assert _names(lm) == ["Ground", "Mid", "Roof"]
    assert [(l.number, l.elevation) for l in lm.levels] == [(1, 0.0), (2, 4000.0), (3, 9000.0)]


def test_ties_keep_their_prior_relative_order():
    lm = _lm(("Y", 1524.0, 5), ("X", 1524.0, 6), ("Z", 0.0, 1))   # tied pair in reverse alpha file order
    assert _names(lm) == ["Z", "Y", "X"]                           # a (elevation, name) key would give Z, X, Y


def test_add_level_is_inserted_by_elevation_and_resort_follows_an_edit():
    lm = LevelManager()                                   # Level 1/2/3 at 0/3048/6096
    new = lm.add_level(elevation=1524.0)
    assert _names(lm) == ["Level 1", new.name, "Level 2", "Level 3"]
    lm.get("Level 3").elevation = 100.0
    lm.resort()
    assert _names(lm) == ["Level 1", "Level 3", new.name, "Level 2"]


def test_next_elevation_above_top():
    assert DEFAULT_LEVEL_GAP_MM == 3048.0                  # 10'-0" (section 12.4 Add)
    assert _lm(("Ground", 0.0, 1)).next_elevation_above_top() == 3048.0
    assert LevelManager().next_elevation_above_top() == 9144.0          # 6096 + (6096 - 3048)
    assert _lm(("A", 0.0, 1), ("B", 5000.0, 2)).next_elevation_above_top() == 10000.0


def test_delete_targets_nearest_remaining_below_lowest_goes_up():
    lm = _lm(("Ground", 0.0, 1), ("Mezz", 1524.0, 2), ("L2", 3048.0, 3), ("Roof", 9144.0, 4))
    assert lm.delete_targets(["Mezz", "Roof"]) == {"Mezz": "Ground", "Roof": "L2"}
    assert lm.delete_targets(["Ground"]) == {"Ground": "Mezz"}
    assert lm.delete_targets(["Ground", "Mezz", "L2", "Roof"]) == {}
    assert lm.delete_targets(["Mezz", "L2"]) == {"Mezz": "Ground", "L2": "Ground"}


def test_remove_levels_repoints_items_and_floor_boundary_refs(qapp):
    # Targets are computed against the levels that REMAIN after the whole selection goes:
    # Mezz is deleted too, so Roof falls to L2, Mezz to Ground.
    scene = Model_Space()
    lm = _lm(("Ground", 0.0, 1), ("Mezz", 1524.0, 2), ("L2", 3048.0, 3), ("Roof", 9144.0, 4))
    scene._level_manager = lm
    wall = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    wall.level = "Roof"
    scene.addItem(wall); scene._walls.append(wall)
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)])
    slab._top_level = "Roof"; slab._bottom_level = "Mezz"
    scene.addItem(slab); scene._floor_slabs.append(slab)
    targets = lm.remove_levels(["Mezz", "Roof"], [wall], scene=scene)
    assert targets == {"Mezz": "Ground", "Roof": "L2"}
    assert _names(lm) == ["Ground", "L2"]
    assert wall.level == "L2"
    assert (slab._top_level, slab._bottom_level) == ("L2", "Ground")


def test_remove_levels_refuses_to_empty_the_list(qapp):
    lm = _lm(("Ground", 0.0, 1), ("Roof", 9144.0, 2))
    assert lm.remove_levels(["Ground", "Roof"], [], scene=None) == {}
    assert _names(lm) == ["Ground", "Roof"]


def test_save_order_is_lowest_first(qapp, tmp_path):
    ms = Model_Space()
    ms._level_manager = _lm(("Roof", 9000.0, 3), ("Ground", 0.0, 1))
    f = tmp_path / "o.fpd"
    ms.save_to_file(str(f))
    saved = json.loads(f.read_text(encoding="utf-8"))["levels"]
    assert [d["name"] for d in saved] == ["Ground", "Roof"]
    assert [d["number"] for d in saved] == [1, 3]
