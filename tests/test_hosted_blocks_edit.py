"""D10: drag moves along + elevation only; Delete removes the model block."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._hosted_blocks_helpers import gridline, defn
from tests.test_section_classification import _placed_scene


def _setup(section_scene_for, reverse_gl=False, a=(0, 0), b=(10000, 0)):
    ms, sec = _placed_scene(section_scene_for, a, b, 8000.0)
    if reverse_gl:
        gl = gridline(ms, (6000, -3000), (0, -3000), "B")   # u runs against +x
    else:
        gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    sec.rebuild()
    inst = sec.place_hosted_block(defn(ms).id, QPointF(2500.0, -1200.0))
    return ms, sec, gl, inst


def _drag_real(sec, copies, dx, dy):
    """Press/move/release on the section's real SelectionManipulator."""
    m = sec._live_manip()            # rebuild() deletes it; heal BEFORE selecting
    sec.clearSelection()
    for c in copies:
        c.setSelected(True)
    QApplication.processEvents()
    assert m._items, "manipulator did not wrap the hosted copy"
    start = QPointF(copies[0].block_pos()[0], copies[0].block_pos()[1])
    end = QPointF(start.x() + dx, start.y() + dy)
    m._begin("move", start, start)
    m._update(end, Qt.KeyboardModifier.NoModifier, end)
    m._finish(end, Qt.KeyboardModifier.NoModifier)


def test_translate_moves_in_plane_one_undo(qapp, section_scene_for):
    ms, sec, gl, inst = _setup(section_scene_for)
    depth0 = ms._undo_pos
    cp = sec._hosted_copies[id(inst)]
    cp.translate(300.0, -200.0)
    qapp.processEvents()
    assert inst.host["along_mm"] == pytest.approx(2800.0)
    assert inst.host["elevation_mm"] == pytest.approx(1400.0)
    assert inst.host["offset_mm"] == 0.0 and inst.host["gridline"] == gl._uid
    assert ms._undo_pos == depth0 + 1
    ms.undo()
    g2 = ms.gridline_by_uid(gl._uid)
    (back,) = ms.hosted_blocks_on(g2)
    assert back.host["along_mm"] == pytest.approx(2500.0)


def test_manipulator_drag_real_path(qapp, section_scene_for):
    """The same move driven through the section's real manipulator drag."""
    ms, sec, gl, inst = _setup(section_scene_for)
    depth0 = ms._undo_pos
    cp = sec._hosted_copies[id(inst)]
    _drag_real(sec, [cp], 300.0, -200.0)
    # Pushed synchronously by the manipulator's release hook (no event loop yet).
    assert ms._undo_pos == depth0 + 1
    assert inst.host["along_mm"] == pytest.approx(2800.0)
    assert inst.host["elevation_mm"] == pytest.approx(1400.0)
    assert inst.host["offset_mm"] == 0.0 and inst.host["gridline"] == gl._uid
    QTest.qWait(300)                                  # sceneModified -> deferred rebuild
    assert ms._undo_pos == depth0 + 1                 # the timer fallback did not add one
    # The section redraws the copy at the new position (no manual rebuild).
    cp2 = sec._hosted_copies[id(inst)]
    assert cp2.block_pos()[0] == pytest.approx(2800.0)
    assert cp2.block_pos()[1] == pytest.approx(-1400.0)
    # Pinned: rebuild() drops the selection; re-select after rebuild is not implemented.
    assert not cp2.isSelected() and not sec.selectedItems()


def test_multi_select_drag_is_one_undo_step(qapp, section_scene_for):
    ms, sec, gl, inst = _setup(section_scene_for)
    inst2 = sec.place_hosted_block(defn(ms, "B").id, QPointF(4000.0, -900.0))
    sec.rebuild()
    depth0 = ms._undo_pos
    copies = [sec._hosted_copies[id(inst)], sec._hosted_copies[id(inst2)]]
    _drag_real(sec, copies, 100.0, 0.0)
    qapp.processEvents()
    assert inst.host["along_mm"] == pytest.approx(2600.0)
    assert inst2.host["along_mm"] == pytest.approx(4100.0)
    assert ms._undo_pos == depth0 + 1


@pytest.mark.parametrize("reverse_gl", [False, True])
def test_h_sign_moves_along_the_right_way(qapp, section_scene_for, reverse_gl):
    """With u opposite to h, a +h drag lowers along; world position follows h."""
    ms, sec, gl, inst = _setup(section_scene_for, reverse_gl=reverse_gl)
    a0 = inst.host["along_mm"]
    h0 = inst.block_pos()[0]
    sec._hosted_copies[id(inst)].translate(300.0, 0.0)
    qapp.processEvents()
    sign = -1.0 if reverse_gl else 1.0
    assert inst.host["along_mm"] == pytest.approx(a0 + sign * 300.0)
    # Ground truth: the block's plan x (h runs along +x here) moved +300 mm.
    assert inst.block_pos()[0] - h0 == pytest.approx(300.0 * ms.scale_manager.pixels_per_mm)


def test_locked_host_gridline_still_lets_block_drag(qapp, section_scene_for):
    ms, sec, gl, inst = _setup(section_scene_for)
    gl._locked = True
    _drag_real(sec, [sec._hosted_copies[id(inst)]], 300.0, 0.0)
    qapp.processEvents()
    assert inst.host["along_mm"] == pytest.approx(2800.0)
    assert inst.host["gridline"] == gl._uid and gl._locked is True


def _window_with_hosted_block():
    """Real MainWindow, a placed section's tab current, a hosted block selected
    in it and a plain plan gridline selected in the PLAN scene."""
    from tests.test_section_manager import _main_window
    ms = None
    win = _main_window()
    ms = win.scene
    marker = win.section_manager.place_section(QPointF(0.0, 0.0), QPointF(10000.0, 0.0))
    view = win.section_manager.open_section(marker.name)
    QApplication.processEvents()
    sec = view.scene()
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    plan_gl = gridline(ms, (0, -9000), (6000, -9000), "P")
    sec.rebuild()
    inst = sec.place_hosted_block(defn(ms).id, QPointF(2500.0, -1200.0))
    assert inst is not None
    QApplication.processEvents()
    ms.clearSelection()
    plan_gl.setSelected(True)
    win.show()
    QTest.qWaitForWindowExposed(win)
    win.central_tabs.setCurrentWidget(view)       # plan selection can switch tabs
    QApplication.processEvents()
    assert win.central_tabs.currentWidget() is view
    sec.clearSelection()
    sec._hosted_copies[id(inst)].setSelected(True)
    view.setFocus()
    assert plan_gl.isSelected() and sec.selectedItems()
    return win, ms, sec, gl, plan_gl, inst


def test_delete_shortcut_in_a_section_tab_deletes_the_section_selection(qapp):
    """Real window-level Delete (QShortcut -> _delete_if_not_editing) in a
    section tab removes the hosted model block, never the plan selection."""
    from tests._mainwindow_helpers import dispose_main_window
    win, ms, sec, gl, plan_gl, inst = _window_with_hosted_block()
    try:
        depth0 = ms._undo_pos
        host_uid = inst.host["gridline"]       # the window has default gridlines too
        QTest.keyClick(win.windowHandle(), Qt.Key.Key_Delete)
        QApplication.processEvents()
        assert inst not in ms._block_instances
        assert plan_gl in ms._gridlines and plan_gl.scene() is ms
        assert plan_gl.isSelected()
        assert ms._undo_pos == depth0 + 1
        ms.undo()
        QApplication.processEvents()
        (back,) = ms._block_instances
        assert back.host["gridline"] == host_uid
        assert back.host["along_mm"] == pytest.approx(2500.0)
    finally:
        dispose_main_window(win)


def test_delete_ribbon_path_in_a_section_tab_deletes_the_section_selection(qapp):
    from tests._mainwindow_helpers import dispose_main_window
    win, ms, sec, gl, plan_gl, inst = _window_with_hosted_block()
    try:
        depth0 = ms._undo_pos
        win._delete_if_not_editing()
        assert inst not in ms._block_instances
        assert plan_gl in ms._gridlines and plan_gl.isSelected()
        assert ms._undo_pos == depth0 + 1
    finally:
        dispose_main_window(win)


def test_delete_elev_selected_removes_model_block_one_undo(qapp, section_scene_for):
    ms, sec, gl, inst = _setup(section_scene_for)
    depth0 = ms._undo_pos
    sec.clearSelection()
    sec._hosted_copies[id(inst)].setSelected(True)
    sec._delete_elev_selected()
    assert inst not in ms._block_instances
    assert ms._undo_pos == depth0 + 1
    ms.undo()
    assert len(ms.hosted_blocks_on(ms.gridline_by_uid(gl._uid))) == 1
