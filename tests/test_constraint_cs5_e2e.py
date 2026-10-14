"""CS5 Smart Dimension E2E -- live MainWindow, real ribbon / clicks / HUD
(D69-D78, §11 #2)."""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import ArcItem, CircleItem, EllipseItem, LineItem, RegularPolygonItem
from tests.test_constraint_dims_e2e import _place, _type
from tests.test_constraint_e2e import _click, _drag, _line   # noqa: F401
from tests.test_constraint_pick_ribbon import (_editors, _plan_index, mw,  # noqa: F401
                                               win_with_editor)


def _tool(w):
    w._block_mode_buttons["constrain_dim_distance"].click()
    QApplication.processEvents()


def _at(v, x, y):
    _click(v, v.mapFromScene(QPointF(x, y)))


def _add(sc, it, lst):
    sc.addItem(it); getattr(sc, lst).append(it); return it


def test_e2e_circle_click_place_type_diameter(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    c = _add(sc, CircleItem(QPointF(0, 0), 60), "_draw_circles")
    _tool(w)
    _at(v, 60 * math.cos(math.radians(30)), -60 * math.sin(math.radians(30)))
    assert sc.constraint_ctl.constraints == []
    _place(v, 120, -90)
    (d,) = sc.constraint_ctl.constraints
    assert d.type == "dim_diameter" and sc.readouts.is_editing()
    _type(sc, "Diameter", "50")
    assert c._radius == pytest.approx(25.0, abs=1e-6)
    assert (c._center.x(), c._center.y()) == pytest.approx((0.0, 0.0))


def test_e2e_selected_arc_skips_to_radius_placement(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    a = _add(sc, ArcItem(QPointF(0, 0), 60, 20, 120), "_draw_arcs")
    a.setSelected(True); QApplication.processEvents()
    _tool(w)
    _place(v, 0, -120)
    (d,) = sc.constraint_ctl.constraints
    assert d.type == "dim_radius" and d.label["angle"] == pytest.approx(90.0, abs=2.0)


def test_e2e_arc_centre_then_arc_gives_sweep(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    a = _add(sc, ArcItem(QPointF(0, 0), 80, 20, 120), "_draw_arcs")
    _tool(w)
    _at(v, 0, 0)                                                   # the arc centre
    _at(v, 80 * math.cos(math.radians(80)), -80 * math.sin(math.radians(80)))
    _place(v, 40, -40)
    (d,) = sc.constraint_ctl.constraints
    assert d.type == "dim_arc_angle" and d.value == pytest.approx(120.0)
    _type(sc, "Angle", "90")
    assert (a._start_deg, a._span_deg) == pytest.approx((20.0, 90.0), abs=1e-6)


def test_e2e_two_lines_sector_by_placement_then_type(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    l1 = _line(sc, (0, 0), (150, 0))
    l2 = _line(sc, (0, 0), (75, -129.9038105677))                  # 60 deg
    _tool(w)
    _at(v, 110, 0)                                                  # edge 1 (off its mid)
    _at(v, 50, -86.6025403784)                                      # edge 2 -> angle path
    assert sc.constraint_ctl.constraints == []
    _place(v, -60, -30)                                             # the 120 deg sector
    (d,) = sc.constraint_ctl.constraints
    assert d.type == "dim_angle" and d.value == pytest.approx(120.0, abs=1e-6)
    _type(sc, "Angle", "100")
    ang = math.degrees(math.atan2(-(l2._pt2.y() - l2._pt1.y()), l2._pt2.x() - l2._pt1.x()))
    assert ang == pytest.approx(80.0, abs=1e-6)                     # 180 - 100
    assert (l1._pt2.x(), l1._pt2.y()) == pytest.approx((150.0, 0.0))


def test_e2e_edge_then_axis_angle(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    _line(sc, (40, -40), (140, -140))
    _tool(w)
    _at(v, 110, -110)
    _at(v, 300, 0)                                                  # the X axis
    _place(v, 200, -30)
    (d,) = sc.constraint_ctl.constraints
    assert d.type == "dim_angle" and d.refs[1] == {"ref": "x_axis"}
    assert d.value == pytest.approx(45.0, abs=1e-6)


def test_e2e_parallel_lines_give_a_linear_dim(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    _line(sc, (0, 0), (150, 0))
    l2 = _line(sc, (0, -60), (150, -60))
    _tool(w)
    _at(v, 110, 0); _at(v, 110, -60)                                # two parallel edges
    _place(v, 170, -30)
    (d,) = sc.constraint_ctl.constraints
    assert d.type == "dim_point_line" and d.value == pytest.approx(60.0)
    _type(sc, "Distance", "90")
    assert (l2._pt1.y(), l2._pt2.y()) == pytest.approx((-90.0, -90.0), abs=1e-6)


def test_e2e_polygon_centre_vertex_is_R_and_ellipse_axis_end_is_R1(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    pg = _add(sc, RegularPolygonItem(QPointF(0, 0), 6, 60.0), "_draw_polygons")
    e = _add(sc, EllipseItem(QPointF(300, 0), 80, 45, 0), "_draw_ellipses")
    _tool(w)
    _at(v, 0, 0); _at(v, 60, 0); _place(v, 90, -40)
    sc.readouts.cancel_edit()
    _at(v, 300, 0); _at(v, 380, 0); _place(v, 420, -40)
    sc.readouts.cancel_edit()
    a, b = sc.constraint_ctl.constraints
    assert (a.type, a.refs[0]["h"]) == ("dim_radius", "radius")
    assert (b.type, b.refs[0]["h"]) == ("dim_radius", "rx")


def test_e2e_drag_sector_one_undo_step_and_save_reopen(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    l1 = _line(sc, (0, 0), (150, 0))
    _line(sc, (0, 0), (75, -129.9038105677))
    _tool(w)
    _at(v, 110, 0); _at(v, 50, -86.6025403784); _place(v, 60, -20)
    sc.readouts.cancel_edit()
    sc.set_mode("select"); QApplication.processEvents()
    (d,) = sc.constraint_ctl.constraints
    assert d.value == pytest.approx(60.0, abs=1e-6)
    from firepro3d.constraint_paint import _frame
    g = next(e for e in _frame(v, sc.constraint_ctl).dims if e.cid == d.id).graphic
    C, r, st, sp = g.arcs[0]
    a = math.radians(st + sp / 2)
    on = QPointF(C.x() + r * math.cos(a), C.y() - r * math.sin(a))
    n = len(sc._undo_stack)
    _drag(v, v.mapToScene(on.toPoint()), QPointF(-60, -20))
    assert d.value == pytest.approx(120.0, abs=1e-6)
    assert (l1._pt2.x(), l1._pt2.y()) == pytest.approx((150.0, 0.0))
    assert len(sc._undo_stack) == n + 1
    recs = sc.constraint_ctl.to_records()
    sc.constraint_ctl.load(recs)
    (d2,) = sc.constraint_ctl.constraints
    assert (d2.type, d2.value, d2.helper) == ("dim_angle", pytest.approx(120.0), d.helper)


def _label_ink(v, sc, it):
    """Count non-background pixels in the item's old radius-readout label box."""
    from firepro3d.readout_paint import layout_linear
    from firepro3d.selection_readouts import readout_text
    spec = next(s for s in it.dimension_specs() if s.key == "radius")
    lay = layout_linear(v, spec, readout_text(spec, getattr(sc, "scale_manager", None)))
    img = v.viewport().grab().toImage()
    dpr = img.devicePixelRatio()
    bg = img.pixelColor(2, 2)
    n = 0
    for dx in range(-int(lay.width / 2), int(lay.width / 2)):
        q = img.pixelColor(int((lay.center.x() + dx) * dpr), int(lay.center.y() * dpr))
        n += abs(q.value() - bg.value()) > 40
    return n


def test_e2e_selected_circle_shows_no_readout_pixels(win_with_editor):
    w = win_with_editor; ed = w._test_editor; sc, v = ed.editor_scene, ed.view
    c = _add(sc, CircleItem(QPointF(0, 0), 80), "_draw_circles")
    sc.set_mode("select"); c.setSelected(True)
    v.viewport().update(); QApplication.processEvents()
    assert _label_ink(v, sc, c) == 0                       # D68: retired
    sc.readouts.show_dim_readouts = True                   # positive control
    sc.readouts.refresh(); v.viewport().update(); QApplication.processEvents()
    try:
        assert _label_ink(v, sc, c) > 0
    finally:
        sc.readouts.show_dim_readouts = False
