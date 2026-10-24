"""SB2a G-B1 + AC3/AC4: a host-bound block resolves @[key] from a real door."""
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.block_attributes import format_value, normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.element_params import HostValue
from firepro3d.geometry_2d import LineItem
from firepro3d.property_manager import PropertyManager
from firepro3d.room import Room
from firepro3d.scale_manager import DisplayUnit, ScaleManager
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening
from tests.test_sb1a_instance import _glyph_key, _texts, _text


def _rec(**kw):
    return normalise_attr({"key": "W", **kw})


def test_format_value_host_value_branch():
    sm = ScaleManager()
    sm.display_unit, sm.precision = DisplayUnit.METRIC_M, 3
    hv = HostValue(914.0, "length", sm)
    assert format_value(_rec(), hv) == "0.914 m"                       # text -> .text
    assert format_value(_rec(type="number", precision=1), hv) == "0.9"  # number -> .number
    assert format_value(_rec(prefix="W=", suffix="!"), hv) == "W=0.914 m!"
    assert format_value(_rec(), HostValue(None, "length", sm)) == "?"
    assert format_value(_rec(type="number"), HostValue("Oak", "text", sm)) == "?"


def _scene(ms):
    room = Room([QPointF(0, 0), QPointF(4000, 0), QPointF(4000, 3000), QPointF(0, 3000)])
    room.name = "Office"
    ms.addItem(room)
    ms._rooms.append(room)
    w = WallSegment(QPointF(0, 0), QPointF(4000, 0), thickness_mm=200.0)
    ms.addItem(w)
    ms._walls.append(w)
    op = WallOpening(w, feature_id="door_914", offset_along=2000)
    ms.addItem(op)
    return op


_PRIMS = [_text("@[W]"), _text("@[R]", y=-10.0), _text("@[N]", y=-20.0)]


def _defs(ms):
    line = LineItem(QPointF(0, 0), QPointF(20, 0)).to_dict()
    bound = BlockDefinition.new(name="DoorTag", library="", series="", origin=(0.0, 0.0),
                                primitives=[line] + _PRIMS)
    bound.attributes = [
        _rec(source="host", host_key="Width"),
        normalise_attr({"key": "R", "source": "host", "host_key": "Room.Name"}),
        normalise_attr({"key": "N", "type": "number", "precision": 1, "source": "host",
                        "host_key": "Width"})]
    bound.host_category = "Door"
    ref = BlockDefinition.new(name="Ref", library="", series="", origin=(0.0, 0.0),
                              primitives=[line] + _PRIMS)
    ref.attributes = [normalise_attr({"key": k}) for k in ("W", "R", "N")]
    for d in (bound, ref):
        ms.register_block_definition(d)
    return bound, ref


def _painted_as(inst, ref_inst, values):
    """The bound instance paints exactly the glyphs of *values* typed by hand."""
    ref_inst.set_attributes(values)
    return [_glyph_key(o) for o in _texts(inst)] == [_glyph_key(o) for o in _texts(ref_inst)]


def test_bound_door_tag_resolves_refreshes_and_reflows(qapp, make_model_space):
    ms = make_model_space()
    sm = ms.scale_manager
    sm.display_unit, sm.precision = DisplayUnit.METRIC_MM, 0
    op = _scene(ms)
    bound, ref = _defs(ms)
    inst = ms.place_block_instance(bound.id, (0.0, 0.0))
    ref_inst = ms.place_block_instance(ref.id, (0.0, 0.0))   # same pose: same local glyph boxes
    assert inst.host is None                                  # gridline record untouched
    assert _painted_as(inst, ref_inst, {"W": "?", "R": "?", "N": "?"})   # no host yet
    calls = []
    real = inst.prepareGeometryChange
    inst.prepareGeometryChange = lambda: (calls.append(1), real())[1]
    inst.element_host = op
    inst.refresh_bound()
    assert calls
    assert _painted_as(inst, ref_inst, {"W": "914 mm", "R": "Office", "N": "914.0"})
    assert ms.instances_bound_to(op) == [inst]
    # AC4: a host property edit through the real panel dispatch
    rect0, n0 = inst.boundingRect(), len(calls)
    pm = PropertyManager()
    pm.show_properties(op)
    QApplication.processEvents()
    pm._apply_property("Width", 1000.0)
    assert op.width_mm == 1000.0
    assert len(calls) > n0                                    # prepareGeometryChange ran
    assert _painted_as(inst, ref_inst, {"W": "1000 mm", "R": "Office", "N": "1000.0"})
    assert inst.boundingRect() != rect0
    # AC3: unit switch through the real refresh path
    n1 = len(calls)
    sm.display_unit, sm.precision = DisplayUnit.METRIC_M, 3
    ms._refresh_all_labels()
    assert len(calls) > n1
    assert _painted_as(inst, ref_inst, {"W": "1.000 m", "R": "Office", "N": "1.0"})
    # override still wins (SB1a D4); a deleted host -> placeholders
    inst.set_attributes({"W": "X"})
    assert _painted_as(inst, ref_inst, {"W": "X", "R": "Office", "N": "1.0"})
    inst.set_attributes({})
    ms.removeItem(op)
    assert inst.host_values() is None
    assert _painted_as(inst, ref_inst, {"W": "?", "R": "?", "N": "?"})


def test_refresh_bound_is_quiet_when_nothing_changed(qapp, make_model_space):
    ms = make_model_space()
    op = _scene(ms)
    bound, _ref = _defs(ms)
    inst = ms.place_block_instance(bound.id, (0.0, 0.0))
    inst.element_host = op
    inst.refresh_bound()
    calls = []
    inst.prepareGeometryChange = lambda: calls.append(1)
    inst.refresh_bound()
    assert calls == []
