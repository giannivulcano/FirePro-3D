"""CS15 Smart Dimension point-line E2E -- live MainWindow, real ribbon /
clicks / HUD (D133-D135)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import CircleItem
from tests.test_constraint_cs5_e2e import _add, _at, _tool
from tests.test_constraint_dims_e2e import _place, _type
from tests.test_constraint_e2e import _line
from tests.test_constraint_pick_ribbon import mw, win_with_editor  # noqa: F401


def test_e2e_point_then_edge_place_type(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    ln = _line(sc, (0, 0), (300, 0))
    c = _add(sc, CircleItem(QPointF(100, -90), 20), "_draw_circles")
    _tool(w)
    _at(v, 100, -90)                                   # the circle centre
    assert "line / axis" in sc.constraint_ctl.pick.status()
    _at(v, 220, 0)                                     # the line, off its mid / ends
    assert sc.constraint_ctl.constraints == []
    _place(v, 40, -45)
    (d,) = sc.constraint_ctl.constraints
    assert d.type == "dim_point_line" and d.value == pytest.approx(90.0)
    assert d.refs == [{"uid": c._uid, "h": "center"}, {"uid": ln._uid, "h": "edge"}]
    assert sc.readouts.is_editing()
    _type(sc, "Distance", "120")
    assert (c._center.x(), c._center.y()) == pytest.approx((100.0, -120.0), abs=1e-6)
    assert (ln._pt1.y(), ln._pt2.y()) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_e2e_point_then_x_axis(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    _add(sc, CircleItem(QPointF(100, -90), 20), "_draw_circles")
    _tool(w)
    _at(v, 100, -90)
    _at(v, 250, 0)                                     # the X axis
    _place(v, 40, -45)
    (d,) = sc.constraint_ctl.constraints
    assert d.type == "dim_point_line" and d.refs[1] == {"ref": "x_axis"}
    assert d.value == pytest.approx(90.0)


def test_e2e_edge_then_point_still_places_the_length(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    ln = _line(sc, (0, 0), (300, 0))
    _add(sc, CircleItem(QPointF(100, -90), 20), "_draw_circles")
    _tool(w)
    _at(v, 220, 0)                                     # edge first
    _place(v, 100, -90)                                # on the circle's centre point
    (d,) = sc.constraint_ctl.constraints
    assert d.type == "dim_distance" and d.refs == [{"uid": ln._uid, "h": "edge"}]
    assert d.value == pytest.approx(300.0)
