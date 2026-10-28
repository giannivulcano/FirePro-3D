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
