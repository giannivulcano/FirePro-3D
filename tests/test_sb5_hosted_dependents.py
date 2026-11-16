"""SB5 Task 7 -- HostedDependents (D5).

G-follow parity (AC6): gridline-hosted block poses after each gridline mutator
and each section write-back equal the base 2509b668 capture. Raw source: plan
Task 7 Step 1, probe ``sb5_probe_follow_baseline.py`` run at c437d5a9 (source
identical to 2509b668) on 2026-11-13; tuple = (x, y, rotation, along_mm,
offset_mm, elevation_mm).

G-bound refresh (AC8, Q10): a block bound to a door re-shapes when its wall is
moved (manipulator drag commit) or gripped, and paints the restored host's
values after undo / redo.
"""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d import hosted_dependents
from firepro3d.scale_manager import DisplayUnit
from tests._sb5_helpers import door_scene, named_room
from tests.test_hosted_blocks_edit import _setup as _sec_setup
from tests.test_hosted_blocks_follow import _setup as _plan_setup
from tests.test_sb2a_binding import _defs, _painted_as

BASELINE = [
    ("translate", 1600.0, -3250.0, 0.0, 1500.0, 200.0, 0.0),
    ("rotate", -200.0, -4500.0, 0.0, 1500.0, 200.0, 0.0),
    ("origin_x", 1800.0, -3200.0, 0.0, 1500.0, 200.0, 0.0),
    ("origin_y_angle", -200.0, -3500.0, 0.0, 1500.0, 200.0, 0.0),
    ("perpendicular", 1500.0, -3100.0, 0.0, 1500.0, 200.0, 0.0),
    ("grip0_back", 1500.0, -3200.0, 0.0, 2200.0, 200.0, 0.0),
    ("grip0_fwd", 1500.0, -3200.0, 0.0, 600.0, 200.0, 0.0),
    ("grip1", 1500.0, -3200.0, 0.0, 1500.0, 200.0, 0.0),
    ("grip2", 1500.0, -3200.0, 0.0, 1500.0, 200.0, 0.0),
    ("grip3", 1500.0, -3200.0, 0.0, 1500.0, 200.0, 0.0),
    ("section_translate", 2800.0, -3000.0, 0.0, 2800.0, 0.0, 1400.0),
    ("section_rotate", 2500.0, -3000.0, 45.0, 2500.0, 0.0, 1200.0),
]

MUTATORS = {
    "translate": lambda gl: gl.translate(100.0, -50.0),
    "rotate": lambda gl: gl.manip_rotate(90.0, QPointF(0, -3000)),
    "origin_x": lambda gl: gl.set_property("Origin X", 300.0),
    "origin_y_angle": lambda gl: (gl.set_property("Origin Y", 2000.0),
                                  gl.set_property("Angle", 90.0)),
    "perpendicular": lambda gl: gl.move_perpendicular(100.0),
    "grip0_back": lambda gl: gl.apply_grip(0, QPointF(-700, -3000)),
    "grip0_fwd": lambda gl: gl.apply_grip(0, QPointF(900, -3000)),
    "grip1": lambda gl: gl.apply_grip(1, QPointF(9000, -3000)),
    "grip2": lambda gl: gl.apply_grip(2, QPointF(-500, -3000)),
    "grip3": lambda gl: gl.apply_grip(3, QPointF(7000, -3000)),
}


def _pose(inst):
    x, y = inst.block_pos()
    return (round(x, 6), round(y, 6), round(inst.block_rotation(), 6),
            round(float(inst.host["along_mm"]), 6),
            round(float(inst.host["offset_mm"]), 6),
            round(float(inst.host["elevation_mm"]), 6))


@pytest.mark.parametrize("row", BASELINE, ids=[r[0] for r in BASELINE])
def test_g_follow_parity_with_base(qapp, make_model_space, section_scene_for, row):
    name, want = row[0], row[1:]
    if name in MUTATORS:
        ms = make_model_space()
        gl, inst = _plan_setup(ms)
        MUTATORS[name](gl)
    else:
        ms, sec, gl, inst = _sec_setup(section_scene_for)
        cp = sec._hosted_copies[id(inst)]
        if name == "section_translate":
            cp.translate(300.0, -200.0)
        else:
            cp.manip_rotate(45.0, QPointF(*cp.block_pos()))
        qapp.processEvents()
    assert _pose(inst) == pytest.approx(want, abs=1e-6)
    assert hosted_dependents.dependents_of(ms, gl) == [inst]


def _bound_door_tag(ms):
    sm = ms.scale_manager
    sm.display_unit, sm.precision = DisplayUnit.METRIC_MM, 0
    op = door_scene(ms)                                   # wall (0,0)-(4000,0) in "Office"
    named_room(ms, "Laboratory East", x0=6000.0)          # (6000,0)-(10000,3000); wider than "914 mm" so the frame grows
    bound, ref = _defs(ms)
    inst = ms.place_block_instance(bound.id, (0.0, -2000.0))
    ref_inst = ms.place_block_instance(ref.id, (0.0, -2000.0))
    inst.element_host = op
    inst.refresh_bound()
    return op, inst, ref_inst, bound, ref


def _instances(ms, bound, ref):
    inst = next(b for b in ms._block_instances if b.block_id == bound.id)
    ref_inst = next(b for b in ms._block_instances if b.block_id == ref.id)
    return inst, ref_inst


def test_g_bound_refresh_on_move_grip_undo_redo(qapp, make_model_space):
    ms = make_model_space()
    op, inst, ref_inst, bound, ref = _bound_door_tag(ms)
    ms.push_undo_state()
    assert _painted_as(inst, ref_inst, {"W": "914 mm", "R": "Office", "N": "914.0"})
    rect_office = inst.boundingRect()
    calls = []
    real = inst.prepareGeometryChange
    inst.prepareGeometryChange = lambda: (calls.append(1), real())[1]
    wall = op.wall
    # Move: the real manipulator drag; its commit_hook is push_undo_state.
    m = ms._live_manip()
    ms.clearSelection()
    wall.setSelected(True)
    QApplication.processEvents()
    assert m._items, "manipulator did not wrap the wall"
    p0 = ms._undo_pos
    start, end = QPointF(1000.0, 0.0), QPointF(7000.0, 0.0)
    m._begin("move", start, start)
    m._update(end, Qt.KeyboardModifier.NoModifier, end)
    m._finish(end, Qt.KeyboardModifier.NoModifier)
    assert ms._undo_pos == p0 + 1
    # THE RED LINE: the commit re-shapes the block (prepareGeometryChange), so
    # Qt invalidates its old and new frame (NoIndex scene, MinimalViewportUpdate
    # view): without it the stale text stays on screen. Text and rect below are
    # resolved lazily and are GREEN at base too -- coverage, not the gate
    # (tests/test_sb2a_binding.py precedent for the `calls` gate).
    assert calls
    assert _painted_as(inst, ref_inst, {"W": "914 mm", "R": "Laboratory East", "N": "914.0"})
    assert inst.boundingRect() != rect_office
    # Grip: the wall's start-point grip handle, through the same manipulator.
    n1 = len(calls)
    handle = wall.manip_handles()[0]
    g0, g1 = QPointF(wall.grip_points()[0]), QPointF(500.0, 0.0)
    m._begin_handle(handle, g0, g0)
    m._update(g1, Qt.KeyboardModifier.NoModifier, g1)
    m._finish(g1, Qt.KeyboardModifier.NoModifier)
    assert ms._undo_pos == p0 + 2
    assert len(calls) > n1
    assert _painted_as(inst, ref_inst, {"W": "914 mm", "R": "Office", "N": "914.0"})
    # Undo / redo rebuild the blocks; each paints its restored host.
    ms.undo()
    inst2, ref2 = _instances(ms, bound, ref)
    assert _painted_as(inst2, ref2, {"W": "914 mm", "R": "Laboratory East", "N": "914.0"})
    ms.redo()
    inst3, ref3 = _instances(ms, bound, ref)
    assert _painted_as(inst3, ref3, {"W": "914 mm", "R": "Office", "N": "914.0"})
