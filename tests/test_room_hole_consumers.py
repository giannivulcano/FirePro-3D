"""Hole consumers (room-detection rework §2.7, D-R4, AC10, AC16). The outer room is the 1b
island case (hand: outer 9800*7800 = 76.44e6, hole 2200*2200 = 4.84e6, inner 1800*1800);
expected values come from those coordinates, never from the code under test."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPolygonF, QTransform

from firepro3d.room import Room
from tests._snap_polish_helpers import click, close_view, make_view, move

OUTER = [(100.0, 100.0), (9900.0, 100.0), (9900.0, 7900.0), (100.0, 7900.0)]
HOLE = [(3900.0, 2900.0), (6100.0, 2900.0), (6100.0, 5100.0), (3900.0, 5100.0)]
INNER = [(4100.0, 3100.0), (5900.0, 3100.0), (5900.0, 4900.0), (4100.0, 4900.0)]


def _pts(xy):
    return [QPointF(x, y) for x, y in xy]


def _rooms(scene):
    """Outer (with hole) first in _rooms, inner second -- the order that made the old
    outer-ring consumers answer 'outer' for a point in the inner room."""
    outer = Room(_pts(OUTER), holes=[_pts(HOLE)])
    outer.name = "Outer"
    inner = Room(_pts(INNER))
    inner.name = "Inner"
    for r in (outer, inner):
        r._show_label = False          # no tag under the pick point (inner's tag sits at (5000, 4000))
        r._update_label()
        scene.addItem(r)
        scene._rooms.append(r)
    return outer, inner


def test_design_area_member_rooms_skip_the_hole(qapp, make_model_space):
    from firepro3d.design_area import DesignArea
    ms = make_model_space()
    outer, inner = _rooms(ms)
    n = ms.add_node(5000, 4000)                 # inside INNER, i.e. in the outer's hole
    ms.add_sprinkler(n)
    da = DesignArea([n.sprinkler])
    ms.addItem(da)
    rooms, roomless = da.member_rooms()
    assert rooms == [inner] and roomless == 0


@pytest.mark.parametrize("holed", [False, True], ids=["control", "holed"])
def test_design_area_tile_is_clipped_out_of_the_hole(qapp, make_model_space, holed):
    """A lone sprinkler at (3000, 4000) draws its fallback square tile; the control (no hole)
    proves the tile reaches x = 4300 (premise); with the hole, no tile covers (4300, 4000)."""
    from firepro3d.design_area import DesignArea
    ms = make_model_space()
    room = Room(_pts(OUTER), holes=[_pts(HOLE)] if holed else None)
    ms.addItem(room)
    ms._rooms.append(room)
    n = ms.add_node(3000, 4000)
    ms.add_sprinkler(n)
    da = DesignArea([n.sprinkler])
    ms.addItem(da)
    ms.design_areas.append(da)
    da.compute_area(ms.scale_manager)

    def covered(x, y):
        return any(p.containsPoint(QPointF(x, y), Qt.FillRule.OddEvenFill) for p in da._tile_polys)

    assert covered(2000, 4000)                   # net area next to the head: always tiled
    assert covered(4300, 4000) is (not holed)    # (4300, 4000) lies in HOLE


@pytest.mark.parametrize("mirror,want", [(False, "Inner"), (True, "Outer")], ids=["facing_in", "facing_out"])
def test_opening_room_probe_skips_the_hole(qapp, make_model_space, mirror, want):
    """Door on the inner rect's bottom wall (4000,3000)->(6000,3000), 200 thick: probe reach =
    100 + ELEMENT_ROOM_PROBE_MM (50) = 150. Facing +y (mirror False, as in
    test_door_room_prefers_facing_side) -> (5000, 3150), inside INNER; mirrored -> (5000, 2850),
    in the outer's net area (HOLE starts at y = 2900)."""
    from firepro3d import element_params as ep
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    ms = make_model_space()
    _rooms(ms)
    w = WallSegment(QPointF(4000, 3000), QPointF(6000, 3000), thickness_mm=200.0)
    ms.addItem(w)
    ms._walls.append(w)
    op = WallOpening(w, feature_id="door_914", offset_along=1000)
    ms.addItem(op)
    op.mirror_facing = mirror
    assert ep.host_values(op)["Room.Name"].raw == want


@pytest.mark.parametrize("holed", [False, True], ids=["control", "holed"])
def test_auto_populate_drops_heads_in_the_hole(qapp, tmp_path, holed):
    import os
    from firepro3d.auto_populate_dialog import AutoPopulateDialog
    from firepro3d.sprinkler_db import SprinklerDatabase
    square = [(0.0, 0.0), (10000.0, 0.0), (10000.0, 10000.0), (0.0, 10000.0)]
    hole = [(4000.0, 4000.0), (6000.0, 4000.0), (6000.0, 6000.0), (4000.0, 6000.0)]
    room = Room(_pts(square), holes=[_pts(hole)] if holed else None)
    db = SprinklerDatabase(path=os.path.join(str(tmp_path), "sprinklers.json"))
    dlg = AutoPopulateDialog(room=room, sprinkler_db=db)
    positions, _sx, _sy, _log = dlg._run_algorithm("grid_uniform", 130.0, 15.0)
    in_hole = [p for p in positions if 4000 < p.x() < 6000 and 4000 < p.y() < 6000]
    if holed:
        assert positions and in_hole == []
    else:
        assert in_hole                        # premise: the outer-ring layout puts a head there


def test_halo_trace_excludes_the_hole(qapp, make_model_space):
    from firepro3d.halo import halo_pick_distance_px
    ms = make_model_space()
    outer, _inner = _rooms(ms)
    # identity device transform: 1 px = 1 mm; (5000, 4000) is 1100 mm from HOLE's nearest edge
    assert halo_pick_distance_px(outer, QPointF(5000, 4000), QTransform()) == pytest.approx(1100.0, abs=1.0)
    assert halo_pick_distance_px(outer, QPointF(1000, 1000), QTransform()) == 0.0


def test_marks_sort_point_reads_the_d_r3_anchor(qapp):
    from firepro3d import marks
    outer = Room(_pts(OUTER), holes=[_pts(HOLE)])
    # D-R3 on y = 4000: intervals [100, 3900] and [6100, 9900], first wins -> x = 2000
    assert marks.sort_point(outer) == pytest.approx((2000.0, 4000.0))


def test_element_params_area_and_perimeter_are_net(qapp, make_model_space):
    from firepro3d import element_params as ep
    ms = make_model_space()
    outer, _inner = _rooms(ms)
    hv = ep.host_values(outer)
    assert hv["Area"].raw == pytest.approx(76.44e6 - 4.84e6)
    assert hv["Perimeter"].raw == pytest.approx(2 * (9800 + 7800) + 4 * 2200)     # 44000 (D-R2)


@pytest.fixture
def picked(qapp):
    view, scene = make_view(role="plan", scale=0.1, mode="select")
    outer, inner = _rooms(scene)
    outer.setZValue(inner.zValue() + 1.0)     # premise: the outer room is drawn on top
    view.centerOn(5000, 4000)
    yield view, scene, outer, inner
    close_view(view, scene)


def test_hole_click_picks_the_inner_room_without_hover(picked):
    view, scene, outer, inner = picked
    click(view, QPointF(5000, 4000))
    assert scene.selectedItems() == [inner]


def test_hole_click_picks_the_inner_room_after_hover(picked):
    view, scene, outer, inner = picked
    move(view, QPointF(5000, 4000))
    click(view, QPointF(5000, 4000))
    assert scene.selectedItems() == [inner]
