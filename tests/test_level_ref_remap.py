"""Wall / room / node level refs follow a level rename or delete and are repaired on
open (todo: walls' Base / Top Level left pointing at a missing level)."""
import json

from PyQt6.QtCore import QPointF

from firepro3d import level_widget as lw_mod
from firepro3d.level_widget import LevelWidget, _COL_NAME
from firepro3d.room import Room
from firepro3d.wall import WallSegment


def _levels(lm):
    for name, z in (("Level 1", 0.0), ("Level 2", 3000.0), ("Level 3", 6000.0)):
        if lm.get(name) is None:
            lm.add_level(name, elevation=z)
        lm.get(name).elevation = z
    lm.resort()


def _setup(shown_model_view, base="Level 1", top="Level 2"):
    view, scene = shown_model_view
    lm = scene._level_manager
    _levels(lm)
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    w.level = w._base_level = base
    w._top_level = top
    room = Room([QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000), QPointF(0, 2000)])
    scene.addItem(room); scene._rooms.append(room)
    room.level, room._ceiling_level = base, top
    node = scene.add_node(0, -800)
    node.level = base
    node.set_property("Ceiling Level", top)
    scene.push_undo_state()
    widget = LevelWidget(lm, scene)
    scene.levelsRestored.connect(widget.populate)
    return scene, lm, widget, w, room, node


def _row(widget, name):
    return next(r for r in range(widget.table.rowCount())
                if widget.table.item(r, _COL_NAME).text() == name)


def _delete(widget, monkeypatch, *names):
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: True)
    widget.table.clearSelection()
    sm = widget.table.selectionModel()
    for n in names:             # selectRow would replace the selection
        sm.select(widget.table.model().index(_row(widget, n), 0),
                  sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
    widget._delete_level()


def test_rename_repoints_wall_room_and_node_refs(qapp, shown_model_view):
    scene, lm, widget, w, room, node = _setup(shown_model_view)
    z0 = w.z_range_mm()
    widget.table.item(_row(widget, "Level 1"), _COL_NAME).setText("Ground")
    widget.table.item(_row(widget, "Level 2"), _COL_NAME).setText("Mezz")
    assert (w._base_level, w._top_level) == ("Ground", "Mezz")
    assert w.z_range_mm() == z0 == (0.0, 3000.0)
    assert room._ceiling_level == "Mezz"
    assert node.ceiling_level == "Mezz"
    assert node.get_properties()["Ceiling Level"]["value"] == "Mezz"   # mirror follows


def test_delete_base_level_moves_base_to_nearest_below(qapp, shown_model_view, monkeypatch):
    scene, lm, widget, w, room, node = _setup(shown_model_view, base="Level 2", top="Level 3")
    _delete(widget, monkeypatch, "Level 2")
    assert (w._base_level, w._top_level) == ("Level 1", "Level 3")
    assert w.z_range_mm() == (0.0, 6000.0)
    assert node.ceiling_level == "Level 3"


def test_delete_top_level_lifts_top_to_next_above(qapp, shown_model_view, monkeypatch):
    scene, lm, widget, w, room, node = _setup(shown_model_view)        # L1 -> L2
    _delete(widget, monkeypatch, "Level 2")
    assert w._top_level == "Level 3" and w.z_range_mm() == (0.0, 6000.0)
    assert room._ceiling_level == "Level 3"
    assert node.ceiling_level == "Level 1"                             # plain nearest-below


def test_delete_top_with_nothing_above_keeps_old_top_as_offset(qapp, shown_model_view, monkeypatch):
    scene, lm, widget, w, room, node = _setup(shown_model_view)
    _delete(widget, monkeypatch, "Level 2", "Level 3")
    assert (w._base_level, w._top_level) == ("Level 1", "Level 1")
    assert w._top_offset_mm == 3000.0 and w.z_range_mm() == (0.0, 3000.0)


def test_undo_restores_wall_refs_after_delete(qapp, shown_model_view, monkeypatch):
    scene, lm, widget, w, room, node = _setup(shown_model_view)
    _delete(widget, monkeypatch, "Level 2")
    scene.undo()
    w2 = scene._walls[0]
    assert (w2._base_level, w2._top_level) == ("Level 1", "Level 2")
    assert w2.z_range_mm() == (0.0, 3000.0)


def test_open_repairs_refs_to_missing_levels(qapp, shown_model_view, tmp_path):
    scene, lm, widget, w, room, node = _setup(shown_model_view, base="Level 2", top="Level 3")
    path = tmp_path / "dangling.fpd"
    scene.save_to_file(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    for wd in data["walls"]:
        wd["base_level"], wd["top_level"] = "Gone", "Gone Too"      # 26307 Walls 1-4 shape
    for rd in data["rooms"]:
        rd["ceiling_level"] = "Gone Too"
    path.write_text(json.dumps(data), encoding="utf-8")
    scene.load_from_file(str(path))
    w2, r2 = scene._walls[0], scene._rooms[0]
    assert w2.level == "Level 2"
    assert (w2._base_level, w2._top_level) == ("Level 2", "Level 3")   # own, next above own
    assert w2.z_range_mm() == (3000.0, 6000.0)
    assert r2._ceiling_level == "Level 3"
