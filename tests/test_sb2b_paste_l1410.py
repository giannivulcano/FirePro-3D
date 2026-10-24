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


def test_design_area_paste_carries_badge_layout_not_active(qapp, shown_model_view):
    """F3: a copy keeps the badge offset/angle; it never becomes the active area."""
    view, scene = shown_model_view
    nodes = [scene.add_node(x, 0) for x in (0, 3000)]
    for n in nodes:
        scene.add_sprinkler(n)
    da = DesignArea([n.sprinkler for n in nodes])
    da.level = scene.active_level
    scene.addItem(da)
    scene.design_areas.append(da)
    scene.active_design_area = da
    da.set_badge_offset(QPointF(120.0, -340.0))
    da.badge._angle = 90.0
    _copy_paste(scene, [da, *nodes])
    assert len(scene.design_areas) == 2
    copy = scene.design_areas[1]
    assert copy.badge_offset() == (120.0, -340.0)
    assert copy.badge._angle == 90.0
    assert copy._badge_user_moved is True
    assert scene.active_design_area is da


def _dup_level_setup(scene):
    """Level 2 (3000) + a duplicate of Level 1 at the SAME elevation, like level_widget."""
    lm = scene._level_manager
    lm.add_level("Level 2", 3000.0)
    src = "Level 1"
    new = lm.add_level("Level 3", lm.get(src).elevation).name
    return lm, src, new


def test_duplicate_level_retargets_source_level_refs(qapp, shown_model_view):
    """F1: Duplicate Level re-points refs naming the source level at the new
    level (wall Base, slab Top/Bottom, room Floor), keeps refs to other levels
    (wall Top, room Ceiling), and the copy follows the new level's elevation."""
    view, scene = shown_model_view
    lm, src, new = _dup_level_setup(scene)
    wall = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    wall.level = src
    wall._base_level, wall._top_level = src, "Level 2"
    scene.addItem(wall)
    scene._walls.append(wall)
    slab = FloorSlab(list(SQ))
    slab._top_level = slab._bottom_level = src
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    room = Room(list(SQ))
    room.level = src
    room._ceiling_level = "Level 2"
    room._scale_manager_ref = scene.scale_manager
    scene.addItem(room)
    scene._rooms.append(room)

    scene.duplicate_level_entities(src, new)
    scene.copy_items_to_level([room], new)         # rooms are not in _items_on_level
    lm.get(new).elevation = 6000.0                 # what level_widget's elevation edit does
    lm.update_elevations(scene)

    assert len(scene._walls) == 2 and len(scene._floor_slabs) == 2 and len(scene._rooms) == 2
    cw, cs, cr = scene._walls[1], scene._floor_slabs[1], scene._rooms[1]
    assert (cw._base_level, cw._top_level, cw.level) == (new, "Level 2", new)
    assert cw.z_range_mm()[0] == 6000.0 and wall.z_range_mm()[0] == 0.0
    assert (cs._top_level, cs._bottom_level) == (new, new)
    assert (slab._top_level, slab._bottom_level) == (src, src)
    assert (cr.level, cr._ceiling_level) == (new, "Level 2")
    assert (room.level, room._ceiling_level) == (src, "Level 2")
    assert (wall._base_level, wall._top_level) == (src, "Level 2")


def test_same_level_paste_keeps_level_refs(qapp, shown_model_view):
    """F1 no-op: source == active level changes nothing (Top Level stays)."""
    view, scene = shown_model_view
    scene._level_manager.add_level("Level 2", 3000.0)
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    w.level = scene.active_level
    w._top_level = "Level 2"
    scene.addItem(w)
    scene._walls.append(w)
    _copy_paste(scene, [w])
    assert (scene._walls[1]._base_level, scene._walls[1]._top_level) == ("Level 1", "Level 2")
