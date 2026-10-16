"""AC1 AD1/AD10 in the real MainWindow: the Auto Constrain button mirrors
and writes its QSettings key; a placed line + its joins undo as one step
(Ctrl+Z); joins survive save -> close -> reopen."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import LineItem
from tests.test_constraint_e2e import _close_tab, _ctrl, _line, _click  # noqa: F401
from tests.test_constraint_pick_ribbon import (  # noqa: F401
    _editors, _plan_index, mw, win_with_editor)


def _place_line(win, a, b):
    sc = win._active_scene(); view = win._test_editor.view
    sc.set_align_enabled(False)
    sc.set_mode("draw_line")
    _click(view, view.mapFromScene(QPointF(*a)))
    _click(view, view.mapFromScene(QPointF(*b)))
    return sc._draw_lines[-1]


def test_button_mirrors_and_writes_the_setting(win_with_editor):
    win = win_with_editor
    b = win._be_constrain_buttons["Auto Constrain"]
    # A fresh QSettings: the button writes the same store the placement press
    # reads (GeometryDrawingController._auto_infer), never the window's cached
    # self.settings (which predates the per-test isolated QSettings dir).
    s = QSettings("GV", "FirePro3D")
    s.setValue(AUTO_CONSTRAIN_KEY, True)
    win._refresh_constrain_buttons()
    assert b.isCheckable() and b.isChecked() and b.isEnabled()
    b.click()                                             # the REAL button
    assert s.value(AUTO_CONSTRAIN_KEY, True, type=bool) is False
    b.click()
    assert s.value(AUTO_CONSTRAIN_KEY, False, type=bool) is True


def test_default_is_on(win_with_editor):
    QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    win_with_editor._refresh_constrain_buttons()
    assert win_with_editor._be_constrain_buttons["Auto Constrain"].isChecked()


def test_button_off_stops_the_next_placement_joining(win_with_editor):
    """The seam: the REAL button's state is what the next placement press
    reads -- OFF -> a snapped line records nothing, ON again -> it joins."""
    win = win_with_editor
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    win._refresh_constrain_buttons()
    b = win._be_constrain_buttons["Auto Constrain"]
    sc = win._active_scene()
    _line(sc, (0, 0), (200, 0))
    b.click()                                             # -> OFF
    assert not b.isChecked()
    n = _place_line(win, (200, 0), (200, 150))
    assert sc.constraint_ctl.constraints_on(n) == []
    b.click()                                             # -> ON
    m = _place_line(win, (200, 0), (300, 150))
    assert [c.type for c in sc.constraint_ctl.constraints_on(m)] == ["coincident"]


def test_ctrl_z_removes_line_and_joins_together(win_with_editor):
    win = win_with_editor
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    sc = win._active_scene(); view = win._test_editor.view
    a = _line(sc, (0, 0), (200, 0)); sc.push_undo_state()
    n = _place_line(win, (200, 0), (200, 150))
    assert [c.type for c in sc.constraint_ctl.constraints_on(n)] == ["coincident"]
    _ctrl(view, Qt.Key.Key_Z)
    assert sc.constraint_ctl.constraints == []
    assert [l._uid for l in sc._draw_lines] == [a._uid]


def test_joins_survive_save_close_reopen(win_with_editor):
    win = win_with_editor
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    w = win._test_editor; sc = w.editor_scene
    a = _line(sc, (0, 0), (200, 0))
    n = _place_line(win, (200, 0), (200, 150))
    ua, un = a._uid, n._uid
    sc.clearSelection()
    defn = w.commit_block("ac1-e2e", "L", "S")
    assert defn is not None
    _close_tab(win, w)
    w2 = win.block_editor_manager.edit_definition(defn.id)
    QApplication.processEvents()
    (c,) = w2.editor_scene.constraint_ctl.active()
    assert c.type == "coincident"
    assert {(r["uid"], r["h"]) for r in c.refs} == {(un, "p1"), (ua, "p2")}
