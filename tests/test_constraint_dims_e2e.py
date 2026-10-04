"""CS4 Smart Dimension E2E — live MainWindow, real ribbon / clicks / HUD
(parametric-constraint-system.md D50-D52, §11 #2)."""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import constraint_dims as cd
from tests.test_constraint_e2e import _click, _drag, _line          # noqa: F401
from tests.test_constraint_pick_ribbon import (                        # noqa: F401
    _editors, _plan_index, mw, win_with_editor)


def _len(ln):
    return math.hypot(ln._pt2.x() - ln._pt1.x(), ln._pt2.y() - ln._pt1.y())


def _type(sc, field, text):
    ed = sc.readouts.hud.editor(field)
    ed.selectAll()
    QTest.keyClicks(ed, text)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    QApplication.processEvents()


def test_e2e_tool_pick_edge_type_value_drives_and_drag_holds(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc, v = ed.editor_scene, ed.view
    ln = _line(sc, (0, 0), (300, 0))
    w._block_mode_buttons["constrain_dim_distance"].click()
    QApplication.processEvents()
    assert sc.mode == "constrain_dim_distance"
    _click(v, v.mapFromScene(QPointF(150, 0)))                     # the edge
    assert sc.readouts.is_editing()                                # D50 HUD
    _type(sc, "Length", "250")
    assert _len(ln) == pytest.approx(250.0, abs=1e-6)
    assert (ln._pt1.x(), ln._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-9)  # D55
    assert sc.mode == "constrain_dim_distance"                     # tool stays live
    sc.set_mode("select")
    QApplication.processEvents()
    ln.setSelected(True)
    QApplication.processEvents()
    _drag(v, QPointF(ln._pt2), QPointF(ln._pt2.x() + 80, ln._pt2.y() + 40))
    assert _len(ln) == pytest.approx(250.0, abs=1e-6)              # dim held


def test_e2e_selection_first_then_esc_keeps_value_and_dim(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc = ed.editor_scene
    ln = _line(sc, (0, 0), (300, 0))
    ln.setSelected(True)
    QApplication.processEvents()
    w._block_mode_buttons["constrain_dim_distance"].click()        # D50 selection-first
    QApplication.processEvents()
    assert sc.readouts.is_editing()
    QTest.keyClick(sc.readouts.hud.editor("Length"), Qt.Key.Key_Escape)
    QApplication.processEvents()
    (c,) = sc.constraint_ctl.constraints
    assert c.type == "dim_distance" and c.value == pytest.approx(300.0)
    assert _len(ln) == pytest.approx(300.0)
    assert not sc.readouts.is_editing()


def test_e2e_two_point_dim_click_selects_double_click_edits(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc, v = ed.editor_scene, ed.view
    a = _line(sc, (0, -100), (0, -50))
    b = _line(sc, (200, -100), (200, -50))
    w._block_mode_buttons["constrain_dim_distance"].click()
    QApplication.processEvents()
    _click(v, v.mapFromScene(QPointF(0, -100)))
    _click(v, v.mapFromScene(QPointF(200, -100)))
    assert sc.readouts.is_editing()
    QTest.keyClick(sc.readouts.hud.editor("Distance"), Qt.Key.Key_Escape)
    sc.set_mode("select")
    QApplication.processEvents()
    ctl = sc.constraint_ctl
    (e,) = cd.dim_entries(v, ctl)
    _click(v, e.layout.center)
    assert ctl.selected_id == e.cid and not sc.readouts.is_editing()
    QTest.mouseDClick(v.viewport(), Qt.MouseButton.LeftButton,
                      pos=e.layout.center.toPoint())
    QApplication.processEvents()
    assert sc.readouts.editing_key() == ("dim", e.cid)
    _type(sc, "Distance", "100")
    assert b._pt1.x() - a._pt1.x() == pytest.approx(100.0, abs=1e-6)


def test_e2e_panel_value_and_driving(win_with_editor):
    w = win_with_editor
    sc = w._test_editor.editor_scene
    ln = _line(sc, (0, 0), (300, 0))
    ctl = sc.constraint_ctl
    c = ctl.add("dim_distance", [{"uid": ln._uid, "h": "edge"}])
    from firepro3d.constraint_controller import ConstraintAdapter
    ad = ConstraintAdapter(ctl, c)
    props = ad.get_properties()
    assert props["Driving"]["value"] is True and props["Value"]["value_mm"] == 300.0
    ad.set_property("Value", 120.0)
    assert _len(ln) == pytest.approx(120.0, abs=1e-6)
    ad.set_property("Driving", False)
    assert not c.driving
    assert ConstraintAdapter(ctl, c).get_properties()["Value"]["type"] == "label"
    rows = ctl.panel_rows(ConstraintAdapter(ctl, c))["rows"]
    assert rows[0]["text"].startswith("Smart Dimension") and "(" in rows[0]["text"]
