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
    room._hazard_class, room._occupancy = "Ordinary Hazard Group 1", "Retail"
    room._system_type, room._ceiling_type = "Dry", "Obstructed"
    hv = ep.host_values(room)
    assert (hv["HazardClass"].raw, hv["Occupancy"].raw) == ("Ordinary Hazard Group 1", "Retail")
    assert (hv["SystemType"].raw, hv["CeilingType"].raw) == ("Dry", "Obstructed")
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
    assert dv["Sill"].raw == pytest.approx(0.0)              # feature.py:56 door_914 sill 0
    assert dv["Type"].raw == "914 × 2032"               # feature.py:56 type_name
    wv = ep.host_values(w)
    assert wv["Name"].raw == "W-North" and wv["Level.Name"].raw == "Level 1"
    assert wv["Height"].raw == pytest.approx(3000.0)         # Level 1 (0) -> Level 2 (3000), wall.py:186-190
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


@pytest.mark.parametrize("ppm", [1.0, 2.0])
def test_pipe_and_sprinkler_values(qapp, make_model_space, ppm):
    ms = make_model_space()
    ms.scale_manager.set_pixels_per_mm(ppm)
    ms._level_manager = LevelManager()
    room = _room(ms, ppm)
    a, b = Node(0, 0), Node(3000 * ppm, 0)                   # scene px; z stays mm
    for n in (a, b):
        ms.addItem(n)
    a.z_pos, b.z_pos = 0.0, 4000.0
    p = Pipe(a, b)
    ms.addItem(p)
    p.level = b.level = "Level 1"
    pv = ep.host_values(p)
    assert pv["Length"].raw == pytest.approx(5000.0)         # 3-4-5, true 3D, calibrated
    assert pv["Schedule"].raw == "Sch 40" and pv["Material"].raw == "Galvanized Steel"  # pipe.py:91,93
    assert pv["Level.Name"].raw == "Level 1"
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
    # class defaults, sprinkler.py:28-40 (Model defaults to "" -> None, so set it)
    assert sv["Manufacturer"].raw == "Tyco" and sv["Orientation"].raw == "Upright"
    assert sv["Temperature"].raw == "155°F" and sv["MinPressure"].raw == pytest.approx(7.0)
    assert sv["Model"].raw is None
    spr._properties["Model"]["value"] = "TY-FRB"
    assert ep.host_values(spr)["Model"].raw == "TY-FRB"
    assert sv["Level.Name"].raw == "Level 1"
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


def test_unknown_level_gives_none_ceiling_and_volume(qapp, make_model_space):
    ms = make_model_space()
    ms._level_manager = LevelManager()
    room = _room(ms)
    assert ep.host_values(room)["CeilingHeight"].raw is not None
    room.level = "Nope"                                      # Room._ceiling_height_mm would say 0.0
    hv = ep.host_values(room)
    assert hv["CeilingHeight"].raw is None and hv["Volume"].raw is None
    room.level = "Level 1"
    room._ceiling_level = "Nope"
    hv = ep.host_values(room)
    assert hv["CeilingHeight"].raw is None and hv["Volume"].raw is None


def test_sprinkler_room_prefers_same_level(qapp, make_model_space):
    ms = make_model_space()
    ms._level_manager = LevelManager()
    r1, r2 = _room(ms, name="Office"), _room(ms, name="Office")
    r1._tag, r2._tag = "L1", "L2"
    r1.level, r2.level = "Level 1", "Level 2"
    n = Node(0, 0)
    ms.addItem(n)
    n.add_sprinkler()
    n._room_name = "Office"
    n.level = "Level 2"
    assert ep.host_values(n.sprinkler)["Room.Mark"].raw == "L2"
    n.level = "Level 1"
    assert ep.host_values(n.sprinkler)["Room.Mark"].raw == "L1"
    n.level = "Level 3"                                      # no same-level room: first by name
    assert ep.host_values(n.sprinkler)["Room.Mark"].raw == "L1"


def test_paramspec_rejects_unknown_kind_and_number_is_safe():
    with pytest.raises(ValueError):
        ep.ParamSpec("X", "X", "bogus", 1, lambda i: None)
    assert ep.HostValue("abc", "length").number is None      # never raises from paint
    assert ep.HostValue("abc", "text").text == "abc"


def _sm(unit):
    from firepro3d.scale_manager import ScaleManager
    sm = ScaleManager()
    sm.display_unit = unit
    sm.precision = 3
    return sm


_I, _M = DisplayUnit.IMPERIAL, DisplayUnit.METRIC_M
_D = '1"Ø'
# (kind, raw, {unit: (text, number)}) -- strings from units-and-formatting.md s3 / T1 tests;
# diameter strings from pipe.py:38-48 maps; length from the ' " feet-inches format (24 in = 2' 0").
_DISPATCH = [
    ("text", "abc", {_I: ("abc", None), _M: ("abc", None)}),
    ("number", 120.0, {_I: ("120", 120.0), _M: ("120", 120.0)}),
    ("number", 5.6, {_I: ("5.6", 5.6), _M: ("5.6", 5.6)}),
    ("length", 609.6, {_I: ("2' 0\"", 24.0), _M: ("0.610 m", 0.6096)}),
    ("area", 12e6, {_I: ("129.2 sq ft", 12e6 / 304.8 ** 2), _M: ("12.00 m²", 12.0)}),
    ("volume", 3.24e10, {_I: ("1144 cu ft", 3.24e10 / 304.8 ** 3), _M: ("32.4 m³", 32.4)}),
    ("area_sqft", 130.0, {_I: ("130 sq ft", 130.0), _M: ("12.1 m²", 130.0 * 0.09290304)}),
    ("pressure", 16.04, {_I: ("16.0 psi", 16.04), _M: ("16.0 psi", 16.04)}),
    ("flow", 22.4, {_I: ("22 gpm", 22.4), _M: ("22 gpm", 22.4)}),
    ("velocity", 5.56, {_I: ("5.6 ft/s", 5.56), _M: ("5.6 ft/s", 5.56)}),
    ("pipe_id", 1.049, {_I: ('1.049"', 1.049), _M: ("26.6 mm", 1.049 * 25.4)}),
    # angle kind prints a 0..360 bearing (ScaleManager.format_bearing): 270 stays 270
    ("angle", 270.0, {_I: ("270°", 270.0), _M: ("270°", 270.0)}),
    ("angle", -90.0, {_I: ("270°", 270.0), _M: ("270°", 270.0)}),
    ("angle", 359.999, {_I: ("0°", 0.0), _M: ("0°", 0.0)}),   # .number agrees with the text
    ("angle", 45.0, {_I: ("45°", 45.0), _M: ("45°", 45.0)}),
    ("diameter", _D, {_I: ('Ø 1"', None), _M: ("Ø 25 mm", None)}),
    ("diameter", "weird", {_I: ("weird", None), _M: ("weird", None)}),
]


def test_dispatch_covers_every_kind():
    assert {k for k, _r, _e in _DISPATCH} == set(ep.KINDS)


@pytest.mark.parametrize("unit", [_I, _M])
@pytest.mark.parametrize("kind,raw,expect", _DISPATCH,
                         ids=[f"{k}-{r}" for k, r, _e in _DISPATCH])
def test_host_value_kind_dispatch(kind, raw, expect, unit):
    hv = ep.HostValue(raw, kind, _sm(unit))
    text, number = expect[unit]
    assert hv.text == text
    if number is None:
        assert hv.number is None
    else:
        assert hv.number == pytest.approx(number)
    assert ep.HostValue(None, kind, _sm(unit)).text is None
    assert ep.HostValue(None, kind, _sm(unit)).number is None


def test_host_value_without_scale_manager_uses_default():
    from firepro3d.scale_manager import ScaleManager
    d = ScaleManager()
    hv = ep.HostValue(12e6, "area")
    assert hv.text == d.format_area_mm2(12e6)
    assert hv.number == pytest.approx(d.area_mm2_value(12e6))


def test_getter_failure_yields_none(qapp, make_model_space):
    ms = make_model_space()
    room = _room(ms)
    room._boundary = None                                    # breaks the shoelace
    hv = ep.host_values(room)
    assert hv["Area"].raw is None and hv["Name"].raw == "Office"
