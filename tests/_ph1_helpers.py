"""Shared builders for the PH1 phasing guards (tests/test_ph1_*.py)."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

SQ = [QPointF(0, 0), QPointF(3000, 0), QPointF(3000, 2000), QPointF(0, 2000)]
VOID = [QPointF(1000, 500), QPointF(2000, 500), QPointF(2000, 1500), QPointF(1000, 1500)]


_MADE: list = []      # every scene() this test built; ph1_cleanup ends them


def scene():
    """A Model_Space with a LevelManager (Level 1 @ 0.0)."""
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    ms._level_manager = LevelManager()
    _MADE.append(ms)
    return ms


@pytest.fixture(autouse=True)
def ph1_cleanup(qapp):
    """M3 (test_pipe_polish_panel.py:16-33 precedent): every scene() is cleaned up
    at teardown. Autouse fixtures set up first and tear down LAST, so the panel
    fixture's timers are already stopped. Each test_ph1_* module imports this name."""
    yield
    for ms in _MADE:
        ms.cleanup()
    _MADE.clear()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def save_raw(ms, tmp_path, name="ph1.fpd"):
    """save_to_file -> (path, parsed JSON payload)."""
    import json
    path = str(tmp_path / name)
    assert ms.save_to_file(path, backup=False)
    with open(path, encoding="utf-8") as fh:
        return path, json.load(fh)


def load(path):
    """A fresh registry, then load_from_file into a new scene."""
    from firepro3d import phase_registry
    phase_registry.reset_project_table()
    out = scene()
    assert out.load_from_file(path)
    return out


def click(view, scene_pt):
    """A posted (non-spontaneous) left click; never moves the OS cursor."""
    vp = view.viewport()
    p = view.mapFromScene(scene_pt)
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, ev)


# -- one builder per phased kind (each adds to *ms* and returns the item) --------
def add_wall(ms):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0, 0), QPointF(4000, 0))
    ms.addItem(w); ms._walls.append(w)
    return w


def add_opening(ms):
    from firepro3d.wall_opening import WallOpening
    w = add_wall(ms)
    op = WallOpening(w, feature_id="door_914", offset_along=1000.0)
    op.level = w.level
    w.openings.append(op); ms.addItem(op)
    return op


def add_slab(ms):
    from firepro3d.floor_slab import FloorSlab
    s = FloorSlab(points=list(SQ))
    ms.addItem(s); ms._floor_slabs.append(s)
    return s


def add_floor_opening(ms):
    from firepro3d.floor_opening import FloorOpening
    s = add_slab(ms)
    op = FloorOpening(list(VOID), host=s)
    s.add_opening(op); ms.addItem(op)
    return op


def add_roof(ms):
    from firepro3d.roof import RoofItem
    r = RoofItem(list(SQ))
    r._scale_manager_ref = ms.scale_manager
    ms.addItem(r); ms._roofs.append(r)
    return r


def add_room(ms):
    from firepro3d.room import Room
    r = Room(list(SQ))
    r._scale_manager_ref = ms.scale_manager
    ms.addItem(r); ms._rooms.append(r)
    return r


def add_pipe(ms):
    a, b = ms.add_node(0.0, 0.0), ms.add_node(1000.0, 0.0)
    return ms.add_pipe(a, b)


def add_sprinkler(ms):
    return ms.add_sprinkler(ms.add_node(500.0, 500.0))


def add_water_supply(ms):
    from firepro3d.water_supply import WaterSupply
    ws = WaterSupply(200.0, 200.0)
    ms.addItem(ws); ms.water_supply_node = ws; ms.sprinkler_system.supply_node = ws
    return ws


def block_definition(ms, name="PH1"):
    from firepro3d.block_definition import BlockDefinition
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=[{"type": "draw_line", "pt1": [0, 0],
                                         "pt2": [100, 0], "color": "#ffffff",
                                         "lineweight": 1.0}], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


def add_block(ms):
    return ms.place_block_instance(block_definition(ms).id, (0.0, 0.0))


FIND = {
    "wall": lambda ms: ms._walls[0],
    "opening": lambda ms: ms._walls[0].openings[0],
    "floor_slab": lambda ms: ms._floor_slabs[0],
    "floor_opening": lambda ms: ms._floor_slabs[0].openings[0],
    "roof": lambda ms: ms._roofs[0],
    "room": lambda ms: ms._rooms[0],
    "pipe": lambda ms: ms.sprinkler_system.pipes[0],
    "sprinkler": lambda ms: ms.sprinkler_system.sprinklers[0],
    "water_supply": lambda ms: ms.water_supply_node,
    "block": lambda ms: ms._block_instances[0],
}
ADD = {"wall": add_wall, "opening": add_opening, "floor_slab": add_slab,
       "floor_opening": add_floor_opening, "roof": add_roof, "room": add_room,
       "pipe": add_pipe, "sprinkler": add_sprinkler,
       "water_supply": add_water_supply, "block": add_block}


@pytest.fixture
def panel(qapp, tmp_path):
    """Factory ``panel(item) -> PropertyManager`` showing *item*; teardown stops
    every refresh timer (a dropped panel's 50 ms timer can abort the run)."""
    from firepro3d.property_manager import PropertyManager
    from firepro3d.sprinkler_db import SprinklerDatabase
    made = []

    def _make(item):
        pm = PropertyManager()
        pm.set_sprinkler_db(SprinklerDatabase(path=str(tmp_path / "sprinklers.json")))
        made.append(pm)
        pm.show_properties(item)
        QApplication.processEvents()
        return pm

    yield _make
    for pm in made:
        pm._refresh_timer.stop()
        pm.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
