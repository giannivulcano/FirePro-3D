"""G1-G4, AC15/AC16 (room-detection rework): rooms placed through Room mode's press
dispatch (posted clicks on a shown view) on walls built with the wall tool. Expected areas
are hand-computed interior-face areas: body offset along n = (-dy, dx)/L of each wall's click line
is Center [-t/2, +t/2], Left [0, +t], Right [-t, 0] (consistent with every 1b truth row);
values marked (1b) match .todo/room-detect-1b.md §2."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.wall import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT
from tests._room_detect_helpers import (add_wall, area, click_room, polyline_walls, rect_walls,
                                        room_view, settle, simple, statuses, wall_tool, xy)
from tests._snap_polish_helpers import close_view

C, L, R = ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT
IN_WALL = "Click inside a room, not on a wall"
OPEN = "Not enclosed — no closed wall boundary at the click point"

# Mid-span tee: 6000 x 4000 rect, 200 walls, partition (3000,0)->(3000,4000); clicks (1500,2000), (4500,2000)
#   Center: bays x 100..2900 | 3100..5900, y 100..3900 -> 2800*3800 = 10.64e6 each (1b)
#   Left ccw: rect inward (200..5800 x 200..3800), partition 2800..3000 -> 2600*3600 = 9.36e6 | 2800*3600 = 10.08e6 (1b)
#   Right ccw: rect outward (0..6000 x 0..4000), partition 3000..3200 -> 3000*4000 = 12.0e6 | 2800*4000 = 11.2e6 (1b)
#   Left cw: rect outward, partition 2800..3000 -> 2800*4000 = 11.2e6 | 3000*4000 = 12.0e6 (1b)
#   Right cw: rect inward, partition 3000..3200 -> 2800*3600 = 10.08e6 | 2600*3600 = 9.36e6 (1b)
MID = [(C, True, (10.64e6, 10.64e6)), (L, True, (9.36e6, 10.08e6)), (R, True, (12.0e6, 11.2e6)),
       (C, False, (10.64e6, 10.64e6)), (L, False, (11.2e6, 12.0e6)), (R, False, (10.08e6, 9.36e6))]
# Near-end tee (t = 300/9000 = 0.033): 9000 x 4000 rect, 100 walls, partition (300,0)->(300,4000);
# clicks (150,2000), (5000,2000)
#   Center: x 50..250 | 350..8950, y 50..3950 -> 200*3900 = 0.78e6 | 8600*3900 = 33.54e6 (1b)
#   Left ccw: inner 100..8900 x 100..3900, partition 200..300 -> 100*3800 = 0.38e6 | 8600*3800 = 32.68e6 (1b)
#   Right ccw: inner 0..9000 x 0..4000, partition 300..400 -> 300*4000 = 1.2e6 | 8600*4000 = 34.4e6 (1b)
#   Left cw: inner 0..9000 x 0..4000, partition 200..300 -> 200*4000 = 0.8e6 | 8700*4000 = 34.8e6 (hand)
#   Right cw: inner 100..8900 x 100..3900, partition 300..400 -> 200*3800 = 0.76e6 | 8500*3800 = 32.3e6 (hand)
NEAR = [(C, True, (0.78e6, 33.54e6)), (L, True, (0.38e6, 32.68e6)), (R, True, (1.2e6, 34.4e6)),
        (C, False, (0.78e6, 33.54e6)), (L, False, (0.8e6, 34.8e6)), (R, False, (0.76e6, 32.3e6))]


def _ids(cases):
    return [f"{a}-{'ccw' if ccw else 'cw'}" for a, ccw, _w in cases]


@pytest.fixture
def plan(qapp):
    view, scene = room_view()
    yield view, scene
    close_view(view, scene)


def _place(view, scene, click, log):
    n0 = len(scene._rooms)
    click_room(view, QPointF(*click))
    assert len(scene._rooms) == n0 + 1, log[-1:] if log else log
    return scene._rooms[-1]


@pytest.mark.parametrize("align,ccw,want", MID, ids=_ids(MID))
def test_g1_mid_span_tee_both_bays(plan, align, ccw, want):
    view, scene = plan
    rect_walls(scene, 0, 0, 6000, 4000, align=align, ccw=ccw)
    wall_tool(scene, (3000, 0), (3000, 4000), align=align)
    scene.set_mode("room")
    log = statuses(scene)
    for click, w in zip(((1500, 2000), (4500, 2000)), want):
        pts = xy(_place(view, scene, click, log).boundary)
        assert simple(pts)
        assert area(pts) == pytest.approx(w, abs=1.0)


@pytest.mark.parametrize("align,ccw,want", NEAR, ids=_ids(NEAR))
def test_g1_near_end_tee_both_bays(plan, align, ccw, want):
    view, scene = plan
    rect_walls(scene, 0, 0, 9000, 4000, align=align, th=100.0, ccw=ccw)
    wall_tool(scene, (300, 0), (300, 4000), align=align, th=100.0)
    scene.set_mode("room")
    log = statuses(scene)
    for click, w in zip(((150, 2000), (5000, 2000)), want):
        pts = xy(_place(view, scene, click, log).boundary)
        assert simple(pts)
        assert area(pts) == pytest.approx(w, abs=1.0)


@pytest.mark.parametrize("end_y", [0.0, 100.0], ids=["centreline", "host_face"])
def test_g2_polyline_u_room_tees_into_host(plan, end_y):
    """6000x4000 Center-200 host + a polyline U (2000,end)->(2000,2000)->(4000,2000)->(4000,end):
    U bodies x 1900..2100 / 3900..4100, top y 1900..2100, ends coped to the host face y = 100.
      inside: 1800 * 1800 = 3.24e6; rest: 5800*3800 - 2200*(2100-100) = 17.64e6 (1b e-face rows)."""
    view, scene = plan
    rect_walls(scene, 0, 0, 6000, 4000)
    chain = polyline_walls(scene, [(2000, end_y), (2000, 2000), (4000, 2000), (4000, end_y)])
    assert len(chain) == 3 and chain[0].pt1.y() == pytest.approx(end_y)   # premise: parked as asked
    scene.set_mode("room")
    log = statuses(scene)
    for click, w in (((3000, 1000), 3.24e6), ((1000, 3000), 17.64e6)):
        pts = xy(_place(view, scene, click, log).boundary)
        assert simple(pts)
        assert area(pts) == pytest.approx(w, abs=1.0)


def _island(scene):
    rect_walls(scene, 0, 0, 10000, 8000)
    rect_walls(scene, 4000, 3000, 6000, 5000)


@pytest.mark.parametrize("click", [(3700, 4000), (1000, 1000)], ids=["near", "far"])
def test_g3_island_hole_near_and_far(plan, click):
    """AC3: outer ring 9800*7800 = 76.44e6, hole 2200*2200 = 4.84e6, net 71.6e6 (1b case d)."""
    view, scene = plan
    _island(scene)
    scene.set_mode("room")
    room = _place(view, scene, click, statuses(scene))
    assert area(xy(room.boundary)) == pytest.approx(76.44e6, abs=1.0)
    assert len(room.holes) == 1
    assert area(xy(room.holes[0])) == pytest.approx(4.84e6, abs=1.0)
    assert room._compute_area_mm2() == pytest.approx(71.6e6, abs=2.0)


def test_g3_inner_allowed_and_same_face_refused(plan):
    """AC4: an inner room inside an existing big room is allowed; re-clicking either face is
    refused. Inner face 1800*1800 = 3.24e6."""
    view, scene = plan
    _island(scene)
    scene.set_mode("room")
    log = statuses(scene)
    _place(view, scene, (3700, 4000), log)
    inner = _place(view, scene, (5000, 4000), log)
    assert area(xy(inner.boundary)) == pytest.approx(3.24e6, abs=1.0) and inner.holes == []
    for again in ((1000, 1000), (5000, 4100)):
        click_room(view, QPointF(*again))
        assert log[-1] == "Room already exists here" and len(scene._rooms) == 2


def test_g3_late_island_punches_hole_in_one_undo_step(plan):
    """AC15 (D-R1) + AC16 tag: outer room first (no island yet), then the island's walls and
    room; the outer gets the hole in the same undo step, and its tag leaves the hole."""
    view, scene = plan
    rect_walls(scene, 0, 0, 10000, 8000)
    scene.set_mode("room")
    log = statuses(scene)
    outer = _place(view, scene, (1000, 1000), log)
    assert area(xy(outer.boundary)) == pytest.approx(76.44e6, abs=1.0) and outer.holes == []
    rect_walls(scene, 4000, 3000, 6000, 5000)
    assert outer.holes == []                                   # walls alone change no room (§8.5)
    scene.set_mode("room")
    pos0 = scene._undo_pos
    _place(view, scene, (5000, 4000), log)
    assert log[-1] == "Created Room 2" and scene._undo_pos == pos0 + 1
    assert len(outer.holes) == 1
    assert area(xy(outer.holes[0])) == pytest.approx(4.84e6, abs=1.0)
    assert outer._compute_area_mm2() == pytest.approx(71.6e6, abs=2.0)
    # D-R3 on y = (100+7900)/2 = 4000: crossings 100 | 3900, 6100 | 9900 -> equal 3800 intervals,
    # first wins -> x = 2000
    assert (outer._tag.pos().x(), outer._tag.pos().y()) == pytest.approx((2000.0, 4000.0), abs=1e-6)
    scene.undo()
    (back,) = scene._rooms
    assert back.holes == [] and area(xy(back.boundary)) == pytest.approx(76.44e6, abs=1.0)


def test_g4_click_in_wall_thickness_refused(plan):
    view, scene = plan
    rect_walls(scene, 0, 0, 6000, 4000)
    scene.set_mode("room")
    log = statuses(scene)
    click_room(view, QPointF(3000, 0))                  # bottom wall centreline: inside its body
    assert log[-1] == IN_WALL and scene._rooms == []


@pytest.mark.parametrize("gap,closes", [(0.5, True), (5.0, False)], ids=["0.5mm", "5mm"])
def test_g4_gap_closes_only_within_tolerance(plan, gap, closes):
    """Right wall starts gap mm above the bottom wall's face (y = 100 + gap); added directly so
    the wall tool's 20 mm auto-join cannot close it. Closed face 5800*3800 = 22.04e6 (probe P4-1)."""
    view, scene = plan
    add_wall(scene, (0, 0), (6000, 0))
    add_wall(scene, (6000, 100 + gap), (6000, 4000))
    add_wall(scene, (6000, 4000), (0, 4000))
    add_wall(scene, (0, 4000), (0, 0))
    settle(scene)
    scene.set_mode("room")
    log = statuses(scene)
    click_room(view, QPointF(3000, 2000))
    if closes:
        assert len(scene._rooms) == 1
        assert area(xy(scene._rooms[0].boundary)) == pytest.approx(22.04e6, abs=1.0)
    else:
        assert log[-1] == OPEN and scene._rooms == []


def test_g4_x_crossing_splits_rooms(plan):
    """AC7: walls drawn through each other (no node at (3000,2000)); cells 2800*1800 = 5.04e6 (1b i)."""
    view, scene = plan
    rect_walls(scene, 0, 0, 6000, 4000)
    wall_tool(scene, (3000, 0), (3000, 4000))
    wall_tool(scene, (0, 2000), (6000, 2000))
    scene.set_mode("room")
    log = statuses(scene)
    for click in ((1500, 1000), (4500, 3000)):
        pts = xy(_place(view, scene, click, log).boundary)
        assert area(pts) == pytest.approx(5.04e6, abs=1.0)


def test_g4_hidden_wall_does_not_bound(plan):
    """AC8: a hidden partition is ignored -> the whole rect face 5800*3800 = 22.04e6."""
    view, scene = plan
    rect_walls(scene, 0, 0, 6000, 4000)
    wall_tool(scene, (3000, 0), (3000, 4000)).setVisible(False)
    scene.set_mode("room")
    room = _place(view, scene, (1500, 2000), statuses(scene))
    assert area(xy(room.boundary)) == pytest.approx(22.04e6, abs=1.0)


def test_g4_door_does_not_break_room(plan):
    """AC8: a door in the bottom wall never opens the room (bodies are not cut, P2 Q2)."""
    view, scene = plan
    rect_walls(scene, 0, 0, 6000, 4000)
    scene.set_mode("opening", template="door_914")
    click_room(view, QPointF(3000, 0), scale=0.5)
    assert sum(len(w.openings) for w in scene._walls) == 1          # premise: the door exists
    scene.set_mode("room")
    room = _place(view, scene, (3000, 2000), statuses(scene))
    assert area(xy(room.boundary)) == pytest.approx(22.04e6, abs=1.0)
