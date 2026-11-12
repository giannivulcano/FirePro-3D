"""G8 (AC14, L1831): manual-room close / vertex pop and Shift-click floor vertex delete keep
the 8 px tolerance after routing through close_hit. View zoom 2.0 px/mm -> CLOSE_HIT_PX 8 /
2.0 = 4.0 mm; the floor edge band is 12 px / 2.0 = 6.0 mm. Parity guard (behaviour-neutral):
GREEN before and after the change."""
import math

import pytest
from PyQt6.QtCore import QPointF

from tests._snap_polish_helpers import close_view, make_view


@pytest.fixture
def scene2x(qapp):
    view, scene = make_view(role="plan", scale=2.0, mode=None)
    yield scene
    close_view(view, scene)


def _press(scene, x, y):
    q = QPointF(x, y)
    scene._press_room_manual(None, q, q, None, None, None)


@pytest.mark.parametrize("d,closes", [(3.9, True), (4.1, False)])
def test_manual_room_close_tolerance(scene2x, d, closes):
    scene = scene2x
    scene.set_mode("room_manual")
    for x, y in ((0, 0), (1000, 0), (1000, 1000)):
        _press(scene, x, y)
    room = scene._room_manual_active
    _press(scene, d, 0.0)                          # d mm from vertex 0
    if closes:
        assert scene._room_manual_active is None and len(room.boundary) == 3
    else:
        assert scene._room_manual_active is room and len(room.boundary) == 4


@pytest.mark.parametrize("d,pops", [(3.9, True), (4.1, False)])
def test_manual_room_vertex_pop_tolerance(scene2x, d, pops):
    scene = scene2x
    scene.set_mode("room_manual")
    for x, y in ((0, 0), (1000, 0)):
        _press(scene, x, y)
    room = scene._room_manual_active
    _press(scene, 1000 + d, 0.0)                   # d mm from vertex 1
    assert len(room._boundary) == (1 if pops else 3)


@pytest.mark.parametrize("d,deletes", [(3.9, True), (4.1, False)])
def test_shift_floor_vertex_delete_tolerance(scene2x, d, deletes):
    from firepro3d.floor_slab import FloorSlab
    scene = scene2x
    slab = FloorSlab([QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)])
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    k = d / math.sqrt(2.0)
    q = QPointF(k, k)                              # d mm from vertex (0,0), inside the slab
    assert scene._press_select_shift_floor(None, q, q, None, None, None) is True
    # delete -> 3 vertices; else within the 6 mm edge band (k <= 2.9 mm) -> insert -> 5
    assert len(slab._points) == (3 if deletes else 5)
