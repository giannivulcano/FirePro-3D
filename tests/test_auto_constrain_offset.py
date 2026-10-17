"""AC4: an Offset in the Block Editor ties its copy to the source (spec §13,
D155-D156): line -> parallel + driving point-line gap dim; circle / arc ->
concentric; every other shape -> nothing. Shown view, posted events."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtTest import QTest

from firepro3d import auto_constrain as ac
from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import ArcItem, CircleItem, LineItem, RectangleItem
from tests._modify_tools_helpers import add_primitive
from tests._snap_polish_helpers import click, close_view, make_view, move

SHIFT = Qt.KeyboardModifier.ShiftModifier


# -- pure planner -------------------------------------------------------------

def test_plan_offset_line_is_parallel_then_gap_dim(qapp):
    a, b = LineItem(QPointF(0, 0), QPointF(100, 0)), LineItem(QPointF(0, 30), QPointF(100, 30))
    assert ac.plan_offset(a, b) == [
        ("parallel", [{"uid": b._uid, "h": "edge"}, {"uid": a._uid, "h": "edge"}]),
        ("dim_point_line", [{"uid": b._uid, "h": "mid"}, {"uid": a._uid, "h": "edge"}])]


@pytest.mark.parametrize("make", [
    lambda r: CircleItem(QPointF(0, 0), r),
    lambda r: ArcItem(QPointF(0, 0), r, 0.0, 90.0)])
def test_plan_offset_curve_is_concentric(qapp, make):
    a, b = make(50.0), make(55.0)
    assert ac.plan_offset(a, b) == [
        ("concentric", [{"uid": b._uid, "h": "curve"}, {"uid": a._uid, "h": "curve"}])]


def test_plan_offset_other_shapes_record_nothing(qapp):
    a = RectangleItem(QPointF(0, 0), QPointF(100, -50))
    b = RectangleItem(QPointF(-5, 5), QPointF(105, -55))
    assert ac.plan_offset(a, b) == []


def test_plan_offset_needs_both_uids(qapp):
    a, b = LineItem(QPointF(0, 0), QPointF(100, 0)), LineItem(QPointF(0, 30), QPointF(100, 30))
    b._uid = None
    assert ac.plan_offset(a, b) == []


@pytest.fixture
def vs(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    yield view, sc
    QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    close_view(view, sc)


def _recs(sc):
    return [(c.type, [(r.get("uid"), r.get("h")) for r in c.refs])
            for c in sc.constraint_ctl.constraints]


def _type_distance(sc, text):
    assert sc.begin_dynamic_input() is True
    sc.dynamic_input.editor("Distance").setText(text)
    sc.dynamic_input._accept()


def _offset_line_by_click(view, sc, mods=Qt.KeyboardModifier.NoModifier):
    src, attr = add_primitive(sc, "line")                   # (0,0)-(100,0)
    sc._modify_ctl.start("offset")
    move(view, QPointF(50, 30))
    click(view, QPointF(50, 30), mods)
    lines = getattr(sc, attr)
    assert len(lines) == 2
    return src, lines[-1]


def test_line_offset_click_records_parallel_and_gap_dim(vs):
    view, sc = vs
    src, cp = _offset_line_by_click(view, sc)
    assert _recs(sc) == [("parallel", [(cp._uid, "edge"), (src._uid, "edge")]),
                         ("dim_point_line", [(cp._uid, "mid"), (src._uid, "edge")])]
    dim = sc.constraint_ctl.constraints[1]
    assert dim.driving is True
    assert dim.value == pytest.approx(30.0, abs=0.5)        # the cursor gap


def test_editing_the_gap_dim_moves_the_copy_parallel(vs):
    view, sc = vs
    src, cp = _offset_line_by_click(view, sc)
    dim = sc.constraint_ctl.constraints[1]
    assert sc.constraint_ctl.set_value(dim.id, 45.0) is True
    p1, p2 = cp.grip_points()[0], cp.grip_points()[1]
    assert abs(p1.y()) == pytest.approx(45.0, abs=1e-6)
    assert p2.y() == pytest.approx(p1.y(), abs=1e-6)       # still parallel
    s1, s2 = src.grip_points()[0], src.grip_points()[1]
    assert (s1.y(), s2.y()) == pytest.approx((0.0, 0.0), abs=1e-6)   # source held


def test_typed_distance_follows_the_toggle_and_drives_the_dim(vs):
    view, sc = vs
    src, attr = add_primitive(sc, "line")
    sc._modify_ctl.start("offset")
    move(view, QPointF(50, 30))
    _type_distance(sc, "20")
    assert [t for t, _ in _recs(sc)] == ["parallel", "dim_point_line"]
    assert sc.constraint_ctl.constraints[1].value == pytest.approx(20.0, abs=1e-6)


def test_enter_follows_the_toggle(vs):
    view, sc = vs
    add_primitive(sc, "line")
    sc._modify_ctl.start("offset")
    move(view, QPointF(50, 30))
    QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
    assert [t for t, _ in _recs(sc)] == ["parallel", "dim_point_line"]


@pytest.mark.parametrize("name", ["circle", "arc"])
def test_curve_offset_records_concentric(vs, name):
    view, sc = vs
    src, attr = add_primitive(sc, name)
    sc._modify_ctl.start("offset")
    move(view, QPointF(400, -400))
    _type_distance(sc, "5")
    cp = getattr(sc, attr)[-1]
    assert cp is not src
    assert _recs(sc) == [("concentric", [(cp._uid, "curve"), (src._uid, "curve")])]


def test_rect_offset_records_nothing(vs):
    view, sc = vs
    src, attr = add_primitive(sc, "rect")
    sc._modify_ctl.start("offset")
    move(view, QPointF(400, -400))
    _type_distance(sc, "5")
    assert len(getattr(sc, attr)) == 2 and _recs(sc) == []


def test_shift_click_records_nothing(vs):
    view, sc = vs
    _offset_line_by_click(view, sc, SHIFT)
    assert _recs(sc) == []


def test_toggle_off_records_nothing(vs):
    view, sc = vs
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    _offset_line_by_click(view, sc)
    assert _recs(sc) == []


def test_one_undo_removes_copy_and_relations(vs):
    view, sc = vs
    src, attr = add_primitive(sc, "line")
    p0 = sc._undo_pos
    sc._modify_ctl.start("offset")
    move(view, QPointF(50, 30))
    click(view, QPointF(50, 30))
    assert sc._undo_pos == p0 + 1 and len(_recs(sc)) == 2
    sc.undo()
    assert len(sc._draw_lines) == 1 and _recs(sc) == []


def test_plan_space_offset_never_calls_the_constraint_controller(qapp, monkeypatch):
    view, sc = make_view(role="plan", scale=1.0)        # make_view defaults to block_editor
    try:
        calls = []
        monkeypatch.setattr(sc.constraint_ctl, "auto_join",
                            lambda recs: calls.append(recs) or [])
        QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
        _offset_line_by_click(view, sc)
        assert calls == []
    finally:
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
        close_view(view, sc)
