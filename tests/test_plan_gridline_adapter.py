"""Editor/Build slice 2 Task 4: the gridline adapter; a locked gridline is
fixed in the solve (ruling L1); hosted blocks follow a solve as they follow
a grip drag (ruling H1, D5 / D6). Guard T9. Expected block positions are
derived from the hosted-block contract (offset 200 mm, along 1500 mm on
gridline B; tests/test_hosted_blocks_follow.py::_setup), not from the code
under test."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.constraint_controller import CONFLICT_STATUS
from firepro3d.sketch_adapters import adapter_for
from tests._hosted_blocks_helpers import defn, gridline


def _setup(ms):
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    d = defn(ms)
    inst = ms.place_block_instance(d.id, (0, 0), host={
        "gridline": gl._uid, "offset_mm": 200.0, "along_mm": 1500.0,
        "elevation_mm": 0.0, "facing": 1})
    return gl, inst


def test_read_write_round_trip_keeps_bubbles(qapp, make_model_space):
    ms = make_model_space()
    gl = gridline(ms, (0, 0), (3000, 3000 * math.tan(math.radians(-30))), "A")
    ad = adapter_for(gl)
    far = gl._far_point()
    assert ad.read(gl) == pytest.approx([0.0, 0.0, far.x(), far.y()])
    off1, off2 = gl._bubble1_offset, gl._bubble2_offset
    ad.write(gl, [0.0, 0.0, 4000.0, 0.0])             # new length + angle
    assert gl._length == pytest.approx(4000.0)
    assert gl._angle_deg == pytest.approx(0.0, abs=1e-9)
    assert (gl._bubble1_offset, gl._bubble2_offset) == (off1, off2)
    assert set(ad.points(gl, 0)) == {"p1", "p2", "mid"}
    assert set(ad.edges(gl, 0)) == {"edge"}


def test_t9_axial_origin_slide_leaves_hosted_block_put(qapp, make_model_space):
    """T9a: a length dim edit slides the origin along the axis (direction
    unchanged) -> the block stays put (D6 compensation)."""
    ms = make_model_space()
    gl, inst = _setup(ms)
    before = inst.block_pos()
    assert before == pytest.approx((1500.0, -3200.0))
    ctl = ms.constraint_ctl
    c = ctl.add("dim_distance", [{"uid": gl._uid, "h": "edge"}])
    assert c is not None
    assert ctl.set_value(c.id, 4000.0) is True
    assert gl._length == pytest.approx(4000.0, abs=1e-6)
    assert gl._angle_deg == pytest.approx(0.0, abs=1e-9)
    assert gl._origin.y() == pytest.approx(-3000.0, abs=1e-6)
    assert inst.block_pos() == pytest.approx(before, abs=1e-6)


def test_t9_sideways_solve_moves_hosted_block_and_lock_holds(qapp, make_model_space):
    """T9b + L1: A is locked (fixed); B is held parallel to A by a dim from
    B's origin to A's edge; editing the dim shifts B sideways and its block
    rides along. Expected: B at y = -3500, block 200 mm beyond it."""
    ms = make_model_space()
    gl_b, inst = _setup(ms)
    gl_a = gridline(ms, (0, 0), (6000, 0), "A")
    gl_a.locked = True
    ctl = ms.constraint_ctl
    assert ctl.add("parallel", [{"uid": gl_a._uid, "h": "edge"},
                                {"uid": gl_b._uid, "h": "edge"}]) is not None
    c = ctl.add("dim_point_line", [{"uid": gl_b._uid, "h": "p1"},
                                   {"uid": gl_a._uid, "h": "edge"}])
    assert c is not None and c.value == pytest.approx(3000.0)
    assert ctl.set_value(c.id, 3500.0) is True
    assert (gl_a._origin.x(), gl_a._origin.y()) == (0.0, 0.0)     # locked: fixed
    assert gl_a._far_point().y() == pytest.approx(0.0, abs=1e-9)
    assert gl_b._origin.y() == pytest.approx(-3500.0, abs=1e-6)
    assert gl_b._far_point().y() == pytest.approx(-3500.0, abs=1e-6)
    assert inst.block_pos() == pytest.approx((1500.0, -3700.0), abs=1e-6)


def test_l1_two_locked_gridlines_conflict_and_nothing_moves(qapp, make_model_space):
    ms = make_model_space()
    gl_b, _inst = _setup(ms)
    gl_a = gridline(ms, (0, 0), (6000, 0), "A")
    c = ms.constraint_ctl.add("dim_point_line", [{"uid": gl_b._uid, "h": "p1"},
                                                 {"uid": gl_a._uid, "h": "edge"}])
    assert c is not None
    gl_a.locked = True
    gl_b.locked = True
    ctl = ms.constraint_ctl
    msgs = []
    ms._show_status = lambda m, *a, **k: msgs.append(m)
    assert ctl.set_value(c.id, 3500.0) is False
    assert msgs and msgs[-1] == CONFLICT_STATUS
    assert gl_b._origin.y() == pytest.approx(-3000.0)
    assert (gl_a._origin.x(), gl_a._origin.y()) == (0.0, 0.0)
    assert "__locked__" not in {x.id for x in ctl.constraints}
    assert "__locked__" not in ctl.red
