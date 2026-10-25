"""SB2b M14 -- Level.number: stored, default by elevation, never shifts, editable, printed by {level}."""
import json

from PyQt6.QtCore import QPointF

from firepro3d import marks
from firepro3d.element_params import host_values
from firepro3d.level_manager import LevelManager
from firepro3d.level_widget import LevelWidget, _COL_NUM
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment


def test_defaults_numbered_by_elevation():
    lm = LevelManager(); lm.reset()
    assert [(l.name, l.number) for l in lm.levels] == [("Level 1", 1), ("Level 2", 2), ("Level 3", 3)]


def test_old_file_levels_numbered_by_elevation_order():
    lm = LevelManager()
    lm.from_list([{"name": "Roof", "elevation_mm": 9000.0},
                  {"name": "Ground", "elevation_mm": 0.0},
                  {"name": "Mid", "elevation_mm": 4000.0}])
    assert {l.name: l.number for l in lm.levels} == {"Ground": 1, "Mid": 2, "Roof": 3}


def test_stored_numbers_never_shift_when_adding():
    lm = LevelManager()
    lm.from_list([{"name": "A", "elevation_mm": 0.0, "number": 7},
                  {"name": "B", "elevation_mm": 3000.0, "number": 9}])
    new = lm.add_level(elevation=1500.0)
    assert {l.name: l.number for l in lm.levels if l is not new} == {"A": 7, "B": 9}
    assert new.number == 2          # 1 + levels at or below 1500 mm


def test_number_round_trips_fpd(qapp, tmp_path):
    ms = Model_Space(); ms._level_manager = LevelManager(); ms._level_manager.reset()
    ms._level_manager.levels[1].number = 5
    f = tmp_path / "l.fpd"
    ms.save_to_file(str(f))
    assert json.loads(f.read_text(encoding="utf-8"))["levels"][1]["number"] == 5
    ms2 = Model_Space(); ms2._level_manager = LevelManager()
    ms2.load_from_file(str(f))
    assert ms2._level_manager.get("Level 2").number == 5


def test_number_column_edit_and_level_token(qapp, shown_model_view):
    view, scene = shown_model_view
    lm = scene._level_manager
    widget = LevelWidget(lm, scene)
    widget.table.item(0, _COL_NUM).setText("4")
    assert lm.levels[0].number == 4
    widget.table.item(0, _COL_NUM).setText("abc")         # refused, reverts
    assert lm.levels[0].number == 4 and widget.table.item(0, _COL_NUM).text() == "4"
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    w.level = lm.levels[0].name
    scene.addItem(w); scene._walls.append(w)
    assert host_values(w)["Level.Number"].raw == 4
    scene.mark_patterns["Wall"] = "{level}-{n}"
    marks.mint(scene, w)
    assert marks.get_mark(w) == "4-1"
    widget.deleteLater()
