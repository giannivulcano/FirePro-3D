"""SB2b Marks -- storage, panel rows, save/load + undo round trip (G2 storage half)."""
import json

from PyQt6.QtCore import QPointF

from firepro3d import marks
from firepro3d.element_params import host_values
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.room import Room
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def _populate(ms):
    w = WallSegment(QPointF(0, 0), QPointF(4000, 0), thickness_mm=200.0)
    w.level = "Level 1"
    ms.addItem(w); ms._walls.append(w)
    op = WallOpening(w, feature_id="door_914", offset_along=1000.0)
    op.level = w.level
    w.openings.append(op); ms.addItem(op)
    room = Room([QPointF(0, 0), QPointF(4000, 0), QPointF(4000, 3000), QPointF(0, 3000)])
    room.level = "Level 1"
    room._scale_manager_ref = ms.scale_manager
    ms.addItem(room); ms._rooms.append(room)
    n1 = ms.add_node(0, 5000); n2 = ms.add_node(3000, 5000)
    pipe = ms.add_pipe(n1, n2)
    ms.add_sprinkler(n2)
    marks.set_mark(w, "WL7"); marks.set_mark(op, "D3"); marks.set_mark(room, "104")
    marks.set_mark(pipe, "P9"); marks.set_mark(n2.sprinkler, "S2")
    return w, op, room, pipe, n2.sprinkler


def test_marks_survive_fpd_save_load(qapp, tmp_path):
    ms = _scene()
    _populate(ms)
    f = tmp_path / "m.fpd"
    ms.save_to_file(str(f))
    ms2 = _scene()
    ms2.load_from_file(str(f))
    w2 = ms2._walls[0]
    assert marks.get_mark(w2) == "WL7"
    assert marks.get_mark(w2.openings[0]) == "D3"
    assert marks.get_mark(ms2._rooms[0]) == "104"
    assert [marks.get_mark(p) for p in ms2.sprinkler_system.pipes] == ["P9"]
    sprs = [n.sprinkler for n in ms2.sprinkler_system.nodes if n.has_sprinkler()]
    assert [marks.get_mark(s) for s in sprs] == ["S2"]
    rec = json.loads(f.read_text(encoding="utf-8"))
    assert rec["rooms"][0]["mark"] == "104" and "tag" not in rec["rooms"][0]


def test_marks_survive_undo_redo(qapp):
    ms = _scene()
    w, op, room, pipe, spr = _populate(ms)
    ms.push_undo_state()
    marks.set_mark(w, "CHANGED")
    ms.push_undo_state()
    ms.undo()
    assert marks.get_mark(ms._walls[0]) == "WL7"
    assert marks.get_mark(ms._walls[0].openings[0]) == "D3"
    assert marks.get_mark(ms._rooms[0]) == "104"
    ms.redo()
    assert marks.get_mark(ms._walls[0]) == "CHANGED"


def test_old_file_room_tag_opens_as_mark_and_blank_stays_blank(qapp, tmp_path):
    ms = _scene()
    _populate(ms)
    f = tmp_path / "old.fpd"
    ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))
    r0 = rec["rooms"][0]
    r0.pop("mark"); r0["tag"] = "LOBBY"
    rec["rooms"].append({**r0, "tag": ""})
    f.write_text(json.dumps(rec), encoding="utf-8")
    ms2 = _scene()
    ms2.load_from_file(str(f))
    assert [marks.get_mark(r) for r in ms2._rooms] == ["LOBBY", ""]


def test_panel_rows_and_registry_read_the_mark(qapp):
    ms = _scene()
    w, op, room, pipe, spr = _populate(ms)
    assert w.get_properties()["Mark"]["value"] == "WL7"
    assert op.get_properties()["Mark"]["value"] == "D3"
    rp = room.get_properties()
    assert rp["Mark"]["value"] == "104" and "Room Tag" not in rp
    assert pipe.get_properties()["Mark"]["value"] == "P9"
    assert spr.get_properties()["Mark"]["value"] == "S2"
    for item, want in ((w, "WL7"), (op, "D3"), (room, "104"), (pipe, "P9"), (spr, "S2")):
        assert host_values(item)["Mark"].raw == want


def test_set_property_mark_writes_each_category(qapp):
    ms = _scene()
    w, op, room, pipe, spr = _populate(ms)
    for item in (w, op, room, pipe, spr):
        item.set_property("Mark", "X1")
        assert marks.get_mark(item) == "X1"


def test_room_label_shows_name_not_mark(qapp):
    """SB2b M6 / SB3 Q1: the room tag's bound field is the Name; the Mark stays
    a separate key the tag does not read."""
    from firepro3d.block_attributes import bound_text_ops, normalise_attr
    from firepro3d.block_definition import BlockDefinition
    ms = _scene()
    w, op, room, pipe, spr = _populate(ms)
    room.name = "Lobby"
    d = BlockDefinition.new(name="T", library="", series="", origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": "@[Name]", "x": 0.0,
                                         "y": 0.0, "height_mm": 3.0}])
    d.scale_mode = "annotative"
    d.host_category = "Room"
    d.attributes = [normalise_attr({"key": "Name", "source": "host", "host_key": "Name"})]
    ms.register_block_definition(d)
    ms.annotation_defaults["Room"] = d.id
    assert room._tag.paints()
    _ops, cache = bound_text_ops(d, {}, host_values(room), False, 1.0, None, None)
    assert cache[1][0] == ("Lobby",) and marks.get_mark(room) == "104"
