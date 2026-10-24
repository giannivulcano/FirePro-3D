"""SB2b G-P1 (todo L1410) -- paste family copies walls+openings, rooms, floors, roofs, design areas; copies mint."""
from PyQt6.QtCore import QPointF

from firepro3d import marks
from firepro3d.design_area import DesignArea
from firepro3d.floor_slab import FloorSlab
from firepro3d.roof import RoofItem
from firepro3d.room import Room
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening

SQ = [QPointF(0, 0), QPointF(3000, 0), QPointF(3000, 2000), QPointF(0, 2000)]


def _wall_with_door(scene):
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    w.level = scene.active_level
    scene.addItem(w)
    scene._walls.append(w)
    marks.mint(scene, w)
    op = WallOpening(w, feature_id="door_914", offset_along=1000.0)
    op.level = w.level
    w.openings.append(op)
    scene.addItem(op)
    marks.mint(scene, op)
    return w, op


def _copy_paste(scene, items, offset=QPointF(0, 5000)):
    scene.clearSelection()
    for it in items:
        it.setSelected(True)
    scene.copy_selected_items()
    return scene.paste_items(offset)


def test_paste_wall_with_door_creates_both_and_mints(qapp, shown_model_view):
    view, scene = shown_model_view
    w, op = _wall_with_door(scene)
    _copy_paste(scene, [w])
    assert len(scene._walls) == 2
    copy = scene._walls[1]
    assert len(copy.openings) == 1
    assert copy.pt1.y() == w.pt1.y() + 5000          # translated
    assert copy.openings[0]._wall is copy
    assert copy.openings[0]._offset_along == op._offset_along   # rides the translated wall
    assert marks.get_mark(copy) == "WL2"
    assert marks.get_mark(copy.openings[0]) == "D2"
    assert marks.get_mark(w) == "WL1" and marks.get_mark(op) == "D1"


def test_duplicate_room_floor_roof(qapp, shown_model_view):
    view, scene = shown_model_view
    room = Room(list(SQ))
    room.level = scene.active_level
    room._scale_manager_ref = scene.scale_manager
    scene.addItem(room)
    scene._rooms.append(room)
    marks.mint(scene, room)
    slab = FloorSlab(list(SQ))
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    roof = RoofItem(list(SQ))
    roof._scale_manager_ref = scene.scale_manager
    scene.addItem(roof)
    scene._roofs.append(roof)
    scene.clearSelection()
    for it in (room, slab, roof):
        it.setSelected(True)
    scene._modify_ctl.commit_duplicate(QPointF(8000, 0))
    assert (len(scene._rooms), len(scene._floor_slabs), len(scene._roofs)) == (2, 2, 2)
    assert marks.get_mark(scene._rooms[1]) != marks.get_mark(room)
    assert marks.get_mark(scene._rooms[1]) != ""
    assert scene._rooms[1]._boundary[0].x() == room._boundary[0].x() + 8000
    assert scene._floor_slabs[1]._points[0].x() == slab._points[0].x() + 8000
    assert scene._roofs[1]._points[0].x() == roof._points[0].x() + 8000


def test_design_area_pasted_only_with_all_its_sprinklers(qapp, shown_model_view, monkeypatch):
    view, scene = shown_model_view
    msgs = []
    nodes = [scene.add_node(x, 0) for x in (0, 3000)]
    for n in nodes:
        scene.add_sprinkler(n)
    da = DesignArea([n.sprinkler for n in nodes])
    da.level = scene.active_level
    scene.addItem(da)
    scene.design_areas.append(da)
    _copy_paste(scene, [da, *nodes])
    assert len(scene.design_areas) == 2
    assert len(scene.design_areas[1].sprinklers) == 2
    monkeypatch.setattr(scene, "_show_status", lambda m, t=5000: msgs.append(m))
    _copy_paste(scene, [da], offset=QPointF(0, 9000))   # sprinklers not copied
    assert len(scene.design_areas) == 2
    assert "design area" in msgs[-1].lower()
