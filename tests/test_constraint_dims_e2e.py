"""Smart Dimension E2E — live MainWindow, real ribbon / clicks / keys / HUD
(parametric-constraint-system.md D50-D52, CS4b D63-D64, §11 #2)."""
import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import constraint_dims as cd
from firepro3d import dim_graphics as dg
from tests.test_constraint_e2e import _click, _drag, _line, _send   # noqa: F401
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


def _place(v, x, y):
    _click(v, v.mapFromScene(QPointF(x, y)))


# -- CS4b D63: placement ------------------------------------------------------

def test_e2e_tool_pick_edge_then_place_then_type_value(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc, v = ed.editor_scene, ed.view
    ln = _line(sc, (0, 0), (300, 0))
    w._block_mode_buttons["constrain_dim_distance"].click()
    QApplication.processEvents()
    _click(v, v.mapFromScene(QPointF(75, 0)))      # the edge (off its midpoint, CS3b)
    assert sc.constraint_ctl.constraints == [] and not sc.readouts.is_editing()
    _place(v, 150, -50)                            # D63 placement click
    (c,) = sc.constraint_ctl.constraints
    assert dg.offset_of(c.label) == pytest.approx(-50.0, abs=1.0)
    assert sc.readouts.is_editing()                # D50 HUD after placement
    _type(sc, "Length", "250")
    assert _len(ln) == pytest.approx(250.0, abs=1e-6)
    assert (ln._pt1.x(), ln._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-9)  # D55
    assert sc.mode == "constrain_dim_distance"     # tool stays live
    sc.set_mode("select")
    QApplication.processEvents()
    ln.setSelected(True)
    QApplication.processEvents()
    _drag(v, QPointF(ln._pt2), QPointF(ln._pt2.x() + 80, ln._pt2.y() + 40))
    assert _len(ln) == pytest.approx(250.0, abs=1e-6)              # dim held


def test_e2e_selected_line_skips_to_placement_then_esc_keeps_value(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc, v = ed.editor_scene, ed.view
    ln = _line(sc, (0, 0), (300, 0))
    ln.setSelected(True)
    QApplication.processEvents()
    w._block_mode_buttons["constrain_dim_distance"].click()
    QApplication.processEvents()
    assert sc.constraint_ctl.constraints == [] and not sc.readouts.is_editing()
    _place(v, 150, 40)
    (c,) = sc.constraint_ctl.constraints
    assert dg.offset_of(c.label) == pytest.approx(40.0, abs=1.0)
    QTest.keyClick(sc.readouts.hud.editor("Length"), Qt.Key.Key_Escape)
    QApplication.processEvents()
    assert c.value == pytest.approx(300.0) and _len(ln) == pytest.approx(300.0)
    assert not sc.readouts.is_editing()


def test_e2e_two_points_then_place_esc_drops_only_the_pending_dim(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc, v = ed.editor_scene, ed.view
    a = _line(sc, (0, -100), (0, -50))
    b = _line(sc, (200, -100), (200, -50))
    w._block_mode_buttons["constrain_dim_distance"].click()
    QApplication.processEvents()
    _click(v, v.mapFromScene(QPointF(0, -100)))
    _click(v, v.mapFromScene(QPointF(200, -100)))
    assert sc.constraint_ctl.constraints == []
    n = len(sc._undo_stack)
    w._on_escape()                                  # the window Escape slot
    QApplication.processEvents()
    assert sc.mode == "constrain_dim_distance"      # D63: tool stays live
    assert sc.constraint_ctl.constraints == [] and len(sc._undo_stack) == n
    _click(v, v.mapFromScene(QPointF(0, -100)))
    _click(v, v.mapFromScene(QPointF(200, -100)))
    _place(v, 100, -150)
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


def test_e2e_refused_pick_never_asks_for_placement(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc, v = ed.editor_scene, ed.view
    ln = _line(sc, (0, 0), (300, 0))
    sc.constraint_ctl.add("dim_distance", [{"uid": ln._uid, "h": "edge"}])
    w._block_mode_buttons["constrain_dim_distance"].click()
    QApplication.processEvents()
    _click(v, v.mapFromScene(QPointF(75, 0)))      # D56 repeat
    assert sc.constraint_ctl.pick.pending is None and not sc.constraint_ctl.pick.picks
    assert len(sc.constraint_ctl.constraints) == 1


def test_e2e_bare_d_starts_smart_dimension_in_the_editor_only(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc, v = ed.editor_scene, ed.view
    ln = _line(sc, (0, 0), (300, 0))
    ln.setSelected(True)
    v.setFocus()
    QApplication.processEvents()
    QTest.keyClick(v, Qt.Key.Key_D)
    QApplication.processEvents()
    assert sc.mode == "constrain_dim_distance"
    assert sc.constraint_ctl.pick.pending == [{"uid": ln._uid, "h": "edge"}]
    plan_mode = w.scene.mode
    QTest.keyClick(w.view, Qt.Key.Key_D)          # plan canvas: no-op
    QApplication.processEvents()
    assert w.scene.mode == plan_mode


# -- CS4b D64: drag a placed dim ----------------------------------------------

def _placed(sc, off):
    ln = _line(sc, (0, 0), (300, 0))
    c = sc.constraint_ctl.add("dim_distance", [{"uid": ln._uid, "h": "edge"}],
                              label={"offset": off})
    sc.set_mode("select")
    sc.clearSelection()
    QApplication.processEvents()
    return ln, c


def test_e2e_drag_dim_line_moves_its_offset_one_undo_step(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc, v = ed.editor_scene, ed.view
    ln, c = _placed(sc, -40.0)
    n = len(sc._undo_stack)
    _drag(v, QPointF(60, -40), QPointF(60, 30))         # through to the other side
    assert dg.offset_of(c.label) == pytest.approx(30.0, abs=1.0)
    assert len(sc._undo_stack) == n + 1
    assert _len(ln) == pytest.approx(300.0)              # geometry untouched
    sc.undo()
    QApplication.processEvents()
    (c2,) = sc.constraint_ctl.constraints
    assert dg.offset_of(c2.label) == pytest.approx(-40.0)


def test_e2e_esc_mid_drag_restores_the_offset(win_with_editor):
    w = win_with_editor
    ed = w._test_editor
    sc, v = ed.editor_scene, ed.view
    ln, c = _placed(sc, -40.0)
    n = len(sc._undo_stack)
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    va = QPointF(v.mapFromScene(QPointF(60, -40)))
    vb = QPointF(v.mapFromScene(QPointF(60, -90)))
    _send(v, QEvent.Type.MouseMove, va, NB, NB)
    _send(v, QEvent.Type.MouseButtonPress, va, L, L)
    for k in range(1, 6):
        _send(v, QEvent.Type.MouseMove, va + (vb - va) * (k / 5), NB, L)
    assert dg.offset_of(c.label) == pytest.approx(-90.0, abs=1.0)
    w._on_escape()
    _send(v, QEvent.Type.MouseButtonRelease, vb, L, NB)
    assert dg.offset_of(c.label) == pytest.approx(-40.0)
    assert len(sc._undo_stack) == n


def test_e2e_click_on_dim_line_selects_without_moving(win_with_editor):
    w = win_with_editor
    sc, v = w._test_editor.editor_scene, w._test_editor.view
    ln, c = _placed(sc, -40.0)
    n = len(sc._undo_stack)
    _click(v, v.mapFromScene(QPointF(60, -40)))
    assert sc.constraint_ctl.selected_id == c.id
    assert dg.offset_of(c.label) == pytest.approx(-40.0) and len(sc._undo_stack) == n


# -- panel ---------------------------------------------------------------------

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
