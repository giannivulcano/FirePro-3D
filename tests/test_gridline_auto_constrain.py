"""Gridline Auto Constrain (2026-10-28): placed gridlines take exact H / V
plus driving point-to-line spacing dims to the nearest near-parallel
neighbour on each side (R1-R8); the blue on-selection readouts are retired."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d import auto_constrain as ac
from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space


def _gl(sc, a, b, uid=None):
    """A gridline registered the way placement registers it."""
    gl = GridlineItem(QPointF(*a), QPointF(*b))
    if uid is not None:
        gl._uid = uid
    sc._register_gridline(gl)
    return gl


def _canon(recs):
    return sorted((t, tuple((r["uid"], r["h"]) for r in refs)) for t, refs in recs)


def _recs(sc):
    return _canon([(c.type, c.refs) for c in sc.constraint_ctl.constraints])


@pytest.fixture
def plan_sc(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    sc = Model_Space()                       # default role: plan
    yield sc
    QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    sc.cleanup()


# -- Task 1: planner ---------------------------------------------------------

def test_planner_exact_vertical_dims_both_sides(plan_sc):
    sc = plan_sc
    a = _gl(sc, (0, -1500), (0, 1500), "A")
    b = _gl(sc, (3000, -1500), (3000, 1500), "B")
    d = _gl(sc, (1000, -1500), (1000, 1500), "D")
    recs, remove = ac.plan_gridline_join(d, sc._gridlines, [])
    assert _canon(recs) == _canon([
        ("vertical", [{"uid": "D", "h": "edge"}]),
        ("dim_point_line", [{"uid": "D", "h": "mid"}, {"uid": "A", "h": "edge"}]),
        ("dim_point_line", [{"uid": "D", "h": "mid"}, {"uid": "B", "h": "edge"}])])
    assert remove == []


def test_planner_near_miss_gets_parallel_not_hv(plan_sc):
    sc = plan_sc
    _gl(sc, (0, -1500), (0, 1500), "A")
    d = _gl(sc, (1000, -1500), (1001, 1500), "D")      # 0.019 deg off vertical
    recs, _ = ac.plan_gridline_join(d, sc._gridlines, [])
    assert _canon(recs) == _canon([
        ("parallel", [{"uid": "D", "h": "edge"}, {"uid": "A", "h": "edge"}]),
        ("dim_point_line", [{"uid": "D", "h": "mid"}, {"uid": "A", "h": "edge"}])])


def test_planner_ignores_crossing_and_coincident_lines(plan_sc):
    sc = plan_sc
    _gl(sc, (-1500, 0), (1500, 0), "H")                # perpendicular: not a neighbour
    _gl(sc, (1000, -900), (1000, 900), "DUP")          # same line: no spacing
    _gl(sc, (2000, -1500), (2000, 1500), "OFF")        # the one real neighbour
    d = _gl(sc, (1000, -1500), (1000, 1500), "D")
    recs, _ = ac.plan_gridline_join(d, sc._gridlines, [])
    assert _canon(recs) == _canon([
        ("vertical", [{"uid": "D", "h": "edge"}]),
        ("dim_point_line", [{"uid": "D", "h": "mid"}, {"uid": "OFF", "h": "edge"}])])


def test_planner_outside_angle_tolerance_is_not_a_neighbour(plan_sc):
    sc = plan_sc
    _gl(sc, (2000, -1500), (2032, 1500), "TILT")       # atan(32/3000) = 0.61 deg > 0.5
    d = _gl(sc, (1000, -1500), (1000, 1500), "D")
    recs, _ = ac.plan_gridline_join(d, sc._gridlines, [])
    assert _canon(recs) == _canon([("vertical", [{"uid": "D", "h": "edge"}])])


def test_planner_rechain_names_the_pair_dim(plan_sc):
    sc = plan_sc
    a = _gl(sc, (0, -1500), (0, 1500), "A")
    b = _gl(sc, (3000, -1500), (3000, 1500), "B")
    ab = sc.constraint_ctl.add(
        "dim_point_line", [{"uid": "B", "h": "mid"}, {"uid": "A", "h": "edge"}])
    assert ab is not None
    d = _gl(sc, (1000, -1500), (1000, 1500), "D")
    _recs_, remove = ac.plan_gridline_join(d, sc._gridlines, sc.constraint_ctl.constraints)
    assert remove == [ab.id]


def test_planner_rechain_keeps_a_reference_dim(plan_sc):
    sc = plan_sc
    _gl(sc, (0, -1500), (0, 1500), "A")
    _gl(sc, (3000, -1500), (3000, 1500), "B")
    ref = sc.constraint_ctl.add(
        "dim_point_line", [{"uid": "B", "h": "mid"}, {"uid": "A", "h": "edge"}])
    sc.constraint_ctl.set_driving(ref.id, False)
    d = _gl(sc, (1000, -1500), (1000, 1500), "D")
    _recs_, remove = ac.plan_gridline_join(d, sc._gridlines, sc.constraint_ctl.constraints)
    assert remove == []


def test_planner_one_side_never_removes(plan_sc):
    sc = plan_sc
    _gl(sc, (0, -1500), (0, 1500), "A")
    _gl(sc, (3000, -1500), (3000, 1500), "B")
    sc.constraint_ctl.add(
        "dim_point_line", [{"uid": "B", "h": "mid"}, {"uid": "A", "h": "edge"}])
    d = _gl(sc, (5000, -1500), (5000, 1500), "D")         # outside the pair
    recs, remove = ac.plan_gridline_join(d, sc._gridlines, sc.constraint_ctl.constraints)
    assert remove == []
    assert [r for r in _canon(recs) if r[0] == "dim_point_line"] == _canon([
        ("dim_point_line", [{"uid": "D", "h": "mid"}, {"uid": "B", "h": "edge"}])])


def test_planner_reversed_direction_and_nearest_wins(plan_sc):
    sc = plan_sc
    _gl(sc, (3000, 1500), (3000, -1500), "FAR")           # drawn downward
    _gl(sc, (2000, 1500), (2000, -1500), "NEAR")          # nearer, same side
    d = _gl(sc, (0, -1500), (0, 1500), "D")
    recs, _ = ac.plan_gridline_join(d, sc._gridlines, [])
    assert _canon(recs) == _canon([
        ("vertical", [{"uid": "D", "h": "edge"}]),
        ("dim_point_line", [{"uid": "D", "h": "mid"}, {"uid": "NEAR", "h": "edge"}])])


def test_planner_near_horizontal_straddles_zero_and_pi(plan_sc):
    sc = plan_sc
    _gl(sc, (-1500, 1000), (1500, 999), "UP")             # angle just under pi (mod pi)
    d = _gl(sc, (-1500, 0), (1500, 1), "D")                # angle just over 0
    recs, _ = ac.plan_gridline_join(d, sc._gridlines, [])
    assert ("dim_point_line", (("D", "mid"), ("UP", "edge"))) in _canon(recs)


def test_auto_join_restores_removed_when_nothing_kept(plan_sc):
    sc = plan_sc
    ctl = sc.constraint_ctl
    _gl(sc, (0, -1500), (0, 1500), "A")
    _gl(sc, (3000, -1500), (3000, 1500), "B")
    ab = ctl.add("dim_point_line", [{"uid": "B", "h": "mid"}, {"uid": "A", "h": "edge"}])
    before = [c.to_dict() for c in ctl.constraints]
    kept = ctl.auto_join([("dim_point_line", [{"uid": "NOPE", "h": "mid"},
                                              {"uid": "A", "h": "edge"}])], remove=[ab.id])
    assert kept == []
    assert [c.to_dict() for c in ctl.constraints] == before


# -- Task 1: controller remove= + shared commit helper -------------------------

def test_auto_join_remove_is_inside_the_callers_step(plan_sc):
    sc = plan_sc
    ctl = sc.constraint_ctl
    _gl(sc, (0, -1500), (0, 1500), "A")
    _gl(sc, (3000, -1500), (3000, 1500), "B")
    ab = ctl.add("dim_point_line", [{"uid": "B", "h": "mid"}, {"uid": "A", "h": "edge"}])
    d = _gl(sc, (1000, -1500), (1000, 1500), "D")
    n_undo = len(sc._undo_stack)
    recs, remove = ac.plan_gridline_join(d, sc._gridlines, ctl.constraints)
    kept = ac.plan_commit(sc, recs, None, remove)
    assert len(kept) == 3
    assert ab.id not in {c.id for c in ctl.constraints}
    assert _recs(sc) == _canon(recs)
    assert not ctl.red
    assert len(sc._undo_stack) == n_undo                # no push of its own (D147)


def test_plan_commit_follows_toggle_xor_shift(plan_sc):
    sc = plan_sc
    _gl(sc, (0, -1500), (0, 1500), "A")
    d = _gl(sc, (1000, -1500), (1000, 1500), "D")
    recs, _ = ac.plan_gridline_join(d, sc._gridlines, [])
    shift = Qt.KeyboardModifier.ShiftModifier
    assert ac.plan_commit(sc, recs, shift) == []         # toggle on + Shift = off
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    assert ac.plan_commit(sc, recs, None) == []          # typed / non-press = toggle
    assert ac.plan_commit(sc, recs, Qt.KeyboardModifier.NoModifier) == []
    assert len(ac.plan_commit(sc, recs, shift)) == 2     # toggle off + Shift = on


# -- Task 2: draw_gridline through real presses (plan view) ------------------

from tests._snap_polish_helpers import click, close_view, make_view, move  # noqa: E402

NO = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


@pytest.fixture
def pv(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    view, sc = make_view(role="plan", scale=1.0, mode=None)
    sc.set_align_enabled(False)
    sc.toggle_snap(False)              # posted clicks land exactly (no OSNAP pull)
    yield view, sc
    QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    close_view(view, sc)


def _place(view, sc, a, b, mods=NO):
    sc.set_mode("draw_gridline")
    assert sc.mode == "draw_gridline"
    n0 = len(sc._gridlines)
    move(view, QPointF(*a), mods); click(view, QPointF(*a), mods)
    move(view, QPointF(*b), mods); click(view, QPointF(*b), mods)
    assert len(sc._gridlines) == n0 + 1
    return sc._gridlines[-1]


def _dims(sc):
    return [c for c in sc.constraint_ctl.constraints if c.type == "dim_point_line"]


def _pair(c):
    return frozenset(r.get("uid") for r in c.refs if isinstance(r, dict))


def test_g1_exact_vertical_placement_gets_vertical(pv):
    view, sc = pv
    g = _place(view, sc, (0, -200), (0, 200))
    assert _recs(sc) == _canon([("vertical", [{"uid": g._uid, "h": "edge"}])])


def test_g1_near_miss_gets_nothing(pv):
    view, sc = pv
    _place(view, sc, (0, -200), (3, 200))
    assert sc.constraint_ctl.constraints == []


def test_g2_neighbour_dim_is_driving_and_moves_the_new_gridline(pv):
    view, sc = pv
    a = _place(view, sc, (-100, -200), (-100, 200))
    b = _place(view, sc, (100, -200), (100, 200))
    (dim,) = _dims(sc)
    assert _pair(dim) == {a._uid, b._uid} and dim.driving
    assert dim.refs[0]["uid"] == b._uid and dim.refs[0]["h"] == "mid"
    assert abs(dim.value - 200.0) < 1e-6
    assert sc.constraint_ctl.set_value(dim.id, 300.0)
    assert abs(a._origin.x() - (-100.0)) < 1e-3          # the older line holds
    assert abs(b._origin.x() - 200.0) < 1e-3             # the new line moved


def test_g9_locked_neighbour_never_moves(pv):
    view, sc = pv
    a = _place(view, sc, (-100, -200), (-100, 200))
    a._locked = True
    b = _place(view, sc, (100, -200), (100, 200))
    (dim,) = _dims(sc)
    assert sc.constraint_ctl.set_value(dim.id, 250.0)
    assert abs(a._origin.x() - (-100.0)) < 1e-6
    assert abs(b._origin.x() - 150.0) < 1e-3


def test_g3_insert_between_rechains_and_g5_undo_restores(pv):
    view, sc = pv
    a = _place(view, sc, (-200, -200), (-200, 200))
    b = _place(view, sc, (200, -200), (200, 200))
    before = [c.to_dict() for c in sc.constraint_ctl.constraints]
    assert {_pair(c) for c in _dims(sc)} == {frozenset({a._uid, b._uid})}
    d = _place(view, sc, (0, -200), (0, 200))
    assert {_pair(c) for c in _dims(sc)} == {frozenset({a._uid, d._uid}),
                                              frozenset({d._uid, b._uid})}
    assert not sc.constraint_ctl.red
    sc.undo(); QApplication.processEvents()
    assert d._uid not in {g._uid for g in sc._gridlines}
    assert [c.to_dict() for c in sc.constraint_ctl.constraints] == before


@pytest.mark.parametrize("toggle,mods,expect", [
    (True, SHIFT, False), (False, NO, False), (False, SHIFT, True)])
def test_g4_toggle_xor_shift(pv, toggle, mods, expect):
    view, sc = pv
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, toggle)
    _place(view, sc, (0, -200), (0, 200), mods)
    assert bool(sc.constraint_ctl.constraints) is expect


@pytest.mark.parametrize("toggle", [True, False])
def test_typed_completion_follows_the_toggle(pv, toggle):
    view, sc = pv
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, toggle)
    sc.set_mode("draw_gridline")
    move(view, QPointF(0, -200)); click(view, QPointF(0, -200))
    assert sc._commit_draw_line_at(QPointF(0, 200))      # the Dynamic Input commit
    assert bool(sc.constraint_ctl.constraints) is toggle


def test_auto_join_clears_selected_and_hover_on_a_removed_dim(plan_sc):
    sc = plan_sc
    ctl = sc.constraint_ctl
    _gl(sc, (0, -1500), (0, 1500), "A")
    _gl(sc, (3000, -1500), (3000, 1500), "B")
    ab = ctl.add("dim_point_line", [{"uid": "B", "h": "mid"}, {"uid": "A", "h": "edge"}])
    d = _gl(sc, (1000, -1500), (1000, 1500), "D")
    ctl.selected_id = ctl.hover_id = ab.id
    recs, remove = ac.plan_gridline_join(d, sc._gridlines, ctl.constraints)
    assert ac.plan_commit(sc, recs, None, remove)
    assert ctl.selected_id is None and ctl.hover_id is None


# -- Task 3: copies + paste ---------------------------------------------------

from PyQt6.QtTest import QTest  # noqa: E402


def test_g7_array_copies_chain_in_order_one_undo_step(plan_sc):
    sc = plan_sc
    src = _gl(sc, (0, -1500), (0, 1500), "S")
    sc.push_undo_state()
    sc._start_gridline_replicate(src, "array")
    sc._replicate_count = 3
    assert sc._commit_gridline_replicate_at(500.0)
    c1, c2, c3 = sc._gridlines[-3:]
    pairs = {frozenset(r["uid"] for r in c.refs)
             for c in sc.constraint_ctl.constraints if c.type == "dim_point_line"}
    assert pairs == {frozenset({c1._uid, "S"}), frozenset({c2._uid, c1._uid}),
                     frozenset({c3._uid, c2._uid})}
    assert sum(c.type == "vertical" for c in sc.constraint_ctl.constraints) == 3
    sc.undo(); QApplication.processEvents()
    assert [g._uid for g in sc._gridlines] == ["S"]
    assert sc.constraint_ctl.constraints == []


def test_g7_offset_copy_gets_its_spacing_dim(plan_sc):
    sc = plan_sc
    _gl(sc, (0, -1500), (0, 1500), "S")
    sc._start_gridline_replicate(sc._gridlines[-1], "offset")
    assert sc._commit_gridline_replicate_at(-750.0)
    cp = sc._gridlines[-1]
    (dim,) = [c for c in sc.constraint_ctl.constraints if c.type == "dim_point_line"]
    assert dim.refs[0]["uid"] == cp._uid and dim.refs[1]["uid"] == "S"
    assert abs(dim.value - 750.0) < 1e-6


def test_g7_paste_joins_like_a_placement(plan_sc):
    sc = plan_sc
    src = _gl(sc, (0, -1500), (0, 1500), "S")
    new = sc.paste_items(QPointF(600, 0), data=[src.to_dict()])
    (cp,) = [g for g in new if isinstance(g, GridlineItem)]
    assert _recs(sc) == _canon([
        ("vertical", [{"uid": cp._uid, "h": "edge"}]),
        ("dim_point_line", [{"uid": cp._uid, "h": "mid"}, {"uid": "S", "h": "edge"}])])


def test_g7_polar_copy_joins_at_its_turned_pose(pv):
    """Polar Array turns each pasted copy after paste_items: the join must see
    the final pose (x=-100), not the coincident pre-turn copy."""
    view, sc = pv
    src = _gl(sc, (100, -50), (100, 50), "S")
    sc.push_undo_state()
    sc.clearSelection(); src.setSelected(True)
    assert sc._modify_ctl.start("array")
    QTest.keyClick(view.viewport(), Qt.Key.Key_Right)       # Linear -> 2D
    QTest.keyClick(view.viewport(), Qt.Key.Key_Right)       # 2D -> Polar
    click(view, QPointF(0, 0))                              # centre
    assert sc.begin_dynamic_input() is True
    sc.dynamic_input.editor("Count").setText("2")
    sc.dynamic_input.editor("Total").setText("360")
    sc.dynamic_input._accept()
    (cp,) = [g for g in sc._gridlines if g is not src]
    assert abs(cp.grip_points()[0].x() + 100) < 1e-6        # turned 180 about 0,0
    (dim,) = [c for c in sc.constraint_ctl.constraints if c.type == "dim_point_line"]
    assert dim.refs[0]["uid"] == cp._uid and dim.refs[1]["uid"] == "S"
    assert abs(dim.value - 200.0) < 1e-6
