"""SB2a G1 + AC1/AC2: element attribute registry over real hosts."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import element_params as ep
from firepro3d.gridline import GridlineItem
from firepro3d.hydraulic_solver import HydraulicResult
from firepro3d.level_manager import LevelManager
from firepro3d.node import Node
from firepro3d.pipe import Pipe
from firepro3d.room import Room
from firepro3d.scale_manager import DisplayUnit
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening

# AC1: the spec's key table, transcribed by hand (element-parameters.md §Key table).
EXPECTED = {
    "Room": [("Name", 1), ("Mark", 1), ("HazardClass", 1), ("Occupancy", 1),
             ("SystemType", 1), ("CeilingType", 1), ("Area", 2), ("Perimeter", 2),
             ("CeilingHeight", 2), ("Volume", 2), ("Level.Name", 4), ("Level.Number", 4)],
    "Pipe": [("Mark", 1), ("Diameter", 1), ("Schedule", 1), ("Material", 1), ("CFactor", 1),
             ("Length", 2), ("InnerDiameter", 2), ("Flow", 3), ("Velocity", 3),
             ("FrictionLoss", 3), ("Level.Name", 4), ("Level.Number", 4)],
    "Sprinkler": [("Mark", 1), ("Manufacturer", 1), ("Model", 1), ("Orientation", 1),
                  ("KFactor", 1), ("Temperature", 1), ("MinPressure", 1), ("CoverageArea", 1),
                  ("Elevation", 2), ("Pressure", 3), ("Flow", 3), ("NodeNumber", 3),
                  ("Room.Name", 4), ("Room.Mark", 4), ("Level.Name", 4), ("Level.Number", 4)],
    "Wall": [("Name", 1), ("Mark", 1), ("Thickness", 1), ("Length", 2), ("Height", 2),
             ("Level.Name", 4), ("Level.Number", 4)],
    "Gridline": [("Mark", 1), ("Length", 2), ("Angle", 2)],
}
_OPENING = [("Mark", 1), ("Family", 1), ("Type", 1), ("Width", 1), ("Height", 1), ("Sill", 1),
            ("Wall.Mark", 4), ("Wall.Name", 4), ("Room.Name", 4), ("Room.Mark", 4),
            ("Level.Name", 4), ("Level.Number", 4)]
for _c in ("Door", "Window", "Opening"):
    EXPECTED[_c] = _OPENING


def test_registry_matches_key_table():
    assert ep.CATEGORIES == ("Room", "Pipe", "Sprinkler", "Wall", "Door", "Window",
                             "Opening", "Gridline")
    for cat in ep.CATEGORIES:
        got = [(k, s.tier) for k, s in ep.PARAMS[cat].items()]
        assert got == EXPECTED[cat], cat
        for k, s in ep.PARAMS[cat].items():
            assert s.key == k and s.label and callable(s.getter)
            assert s.kind in ep.KINDS
    labels = {k: s.label for k, s in ep.PARAMS["Room"].items()}
    assert labels["HazardClass"] == "Hazard class" and labels["Name"] == "Name"
    assert ep.PARAMS["Pipe"]["CFactor"].label == "C-factor"


def _room(ms, ppm=1.0, name="Office"):
    s = ppm
    r = Room([QPointF(0, 0), QPointF(4000 * s, 0), QPointF(4000 * s, 3000 * s),
              QPointF(0, 3000 * s)])
    r.name = name
    r._tag = "R1"
    r._ceiling_offset = 0.0
    ms.addItem(r)
    ms._rooms.append(r)
    return r


def _door_scene(ms, ppm=1.0):
    w = WallSegment(QPointF(0, 0), QPointF(4000 * ppm, 0), thickness_mm=200.0)
    w.name = "W-North"
    ms.addItem(w)
    ms._walls.append(w)
    op = WallOpening(w, feature_id="door_914", offset_along=2000 * ppm)
    ms.addItem(op)
    return w, op


@pytest.mark.parametrize("ppm", [1.0, 2.0])
def test_room_wall_door_gridline_raw_values(qapp, make_model_space, ppm):
    ms = make_model_space()
    ms.scale_manager.set_pixels_per_mm(ppm)
    ms._level_manager = LevelManager()      # make_model_space has none; seeds Level 1/2/3
    ms._level_manager.get("Level 2").elevation = 3000.0   # default 3048.0 (level_manager.py:256)
    room = _room(ms, ppm)
    hv = ep.host_values(room)
    assert hv["Name"].raw == "Office" and hv["Mark"].raw == "R1"
    assert hv["Area"].raw == pytest.approx(12e6)            # 4 m x 3 m
    assert hv["Perimeter"].raw == pytest.approx(14000.0)
    assert hv["CeilingHeight"].raw == pytest.approx(3000.0)  # Level 2 - Level 1, offset 0
    assert hv["Volume"].raw == pytest.approx(3.6e10)
    assert hv["Level.Name"].raw == "Level 1"
    assert hv["Level.Number"].raw is None                    # E4: SB2b
    w, op = _door_scene(ms, ppm)
    assert ep.category_of(op) == "Door"
    dv = ep.host_values(op)
    assert dv["Width"].raw == pytest.approx(914.0)           # feature.py door_914
    assert dv["Height"].raw == pytest.approx(2032.0)
    assert dv["Family"].raw == "Single-Flush"
    assert dv["Wall.Name"].raw == "W-North"
    assert dv["Room.Name"].raw == "Office"                   # facing side (+normal) is in the room
    assert dv["Room.Mark"].raw == "R1"
    assert dv["Mark"].raw is None
    wv = ep.host_values(w)
    assert wv["Length"].raw == pytest.approx(4000.0)
    assert wv["Thickness"].raw == pytest.approx(200.0)
    g = GridlineItem(QPointF(0, 0), QPointF(0, 6000 * ppm), "A")
    ms.addItem(g)
    gv = ep.host_values(g)
    assert gv["Mark"].raw == "A"
    assert gv["Length"].raw == pytest.approx(6000.0)
    assert gv["Angle"].raw == pytest.approx(270.0)           # atan2(-dy, dx), y down


def test_door_room_falls_back_to_other_side(qapp, make_model_space):
    ms = make_model_space()
    # the only room is on the -y side of the wall (boundary y in [-3000, 0]);
    # the door faces +y (mirror_facing False), so the other side is used
    r2 = Room([QPointF(0, -3000), QPointF(4000, -3000), QPointF(4000, 0), QPointF(0, 0)])
    r2.name = "Hall"
    ms.addItem(r2)
    ms._rooms.append(r2)
    _w, op = _door_scene(ms)
    assert ep.host_values(op)["Room.Name"].raw == "Hall"


def test_door_room_prefers_facing_side(qapp, make_model_space):
    """E6: with a room on both sides, the facing side wins; mirror_facing flips it."""
    ms = make_model_space()
    for name, y0 in (("Office", 0), ("Hall", -3000)):         # +y side / -y side of the wall
        r = Room([QPointF(0, y0), QPointF(4000, y0), QPointF(4000, y0 + 3000),
                  QPointF(0, y0 + 3000)])
        r.name = name
        ms.addItem(r)
        ms._rooms.append(r)
    _w, op = _door_scene(ms)
    assert ep.host_values(op)["Room.Name"].raw == "Office"    # facing = +normal = +y
    op.mirror_facing = True
    assert ep.host_values(op)["Room.Name"].raw == "Hall"


def _hr(**kw):
    base = dict(node_pressures={}, pipe_flows={}, pipe_velocity={}, pipe_friction_loss={},
                required_node_pressures={}, total_demand=0.0, hose_stream_gpm=0.0,
                required_pressure=0.0, supply_pressure=0.0, passed=True, messages=[],
                node_numbers={}, node_labels={})
    base.update(kw)
    return HydraulicResult(**base)


def test_pipe_and_sprinkler_values(qapp, make_model_space):
    ms = make_model_space()
    room = _room(ms)
    a, b = Node(0, 0), Node(3000, 0)
    for n in (a, b):
        ms.addItem(n)
    a.z_pos, b.z_pos = 0.0, 4000.0
    p = Pipe(a, b)
    ms.addItem(p)
    pv = ep.host_values(p)
    assert pv["Length"].raw == pytest.approx(5000.0)         # 3-4-5, true 3D
    assert pv["Diameter"].raw == '1"Ø'
    assert pv["InnerDiameter"].raw == pytest.approx(1.049)   # Sch 40 1"
    assert pv["CFactor"].raw == pytest.approx(120.0)
    assert pv["Flow"].raw is None                            # E7: no solve
    b.add_sprinkler()
    spr = b.sprinkler
    b._room_name = "Office"
    assert ep.category_of(spr) == "Sprinkler"
    ms.hydraulic_result = _hr(node_pressures={b: 16.0}, pipe_flows={p: 22.4},
                              pipe_velocity={p: 5.5}, pipe_friction_loss={p: 1.25},
                              node_labels={b: "3a"})
    sv = ep.host_values(spr)
    assert sv["KFactor"].raw == pytest.approx(5.6)
    assert sv["Pressure"].raw == pytest.approx(16.0)
    assert sv["Flow"].raw == pytest.approx(5.6 * 4.0)        # K * sqrt(P)
    assert sv["NodeNumber"].raw == "3a"
    assert sv["Elevation"].raw == pytest.approx(4000.0)
    assert sv["Room.Name"].raw == "Office" and sv["Room.Mark"].raw == "R1"
    assert sv["CoverageArea"].raw == pytest.approx(130.0)
    pv = ep.host_values(p)
    assert pv["Flow"].raw == pytest.approx(22.4)
    assert pv["FrictionLoss"].raw == pytest.approx(1.25)


def test_unit_switch_reformats_text_and_number(qapp, make_model_space):
    ms = make_model_space()
    _w, op = _door_scene(ms)
    sm = ms.scale_manager
    sm.precision = 3
    sm.display_unit = DisplayUnit.METRIC_MM
    assert ep.host_values(op)["Width"].text == "914.000 mm"
    sm.display_unit = DisplayUnit.METRIC_M
    hv = ep.host_values(op)["Width"]
    assert hv.text == "0.914 m" and hv.number == pytest.approx(0.914)
    assert ep.host_values(op)["Family"].number is None       # text kind


def test_category_of_every_class_and_unrelated(qapp, make_model_space):
    ms = make_model_space()
    w = WallSegment(QPointF(0, 0), QPointF(4000, 0))
    ms.addItem(w)
    kinds = {}
    for fid in ("door_914", "window_900", "blank_900"):
        kinds[fid] = ep.category_of(WallOpening(w, feature_id=fid, offset_along=1000))
    assert kinds == {"door_914": "Door", "window_900": "Window", "blank_900": "Opening"}
    assert ep.category_of(w) == "Wall"
    assert ep.category_of(_room(ms)) == "Room"
    assert ep.category_of(GridlineItem(QPointF(0, 0), QPointF(0, 10), "1")) == "Gridline"
    n = Node(0, 0)
    assert ep.category_of(n) is None                         # bare node: not a category (Q2)
    assert ep.category_of(object()) is None
    assert ep.host_values(object()) == {}


def test_getter_failure_yields_none(qapp, make_model_space):
    ms = make_model_space()
    room = _room(ms)
    room._boundary = None                                    # breaks the shoelace
    hv = ep.host_values(room)
    assert hv["Area"].raw is None and hv["Name"].raw == "Office"
