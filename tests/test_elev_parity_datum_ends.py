"""Elevation-parity D7 / AC10 / AC11: level-datum and gridline end edits in a
section persist per section on the SectionMarker (gridline uid / level name
keyed), survive rebuilds, model edits, tab switches and save / reopen, are one
undo step on the plan stack, and the right datum grip draws where dragged.

Drags are posted QMouseEvents on the SHOWN section view's viewport (the
tests/test_constraint_live_drag.py ``_send`` idiom): QTest.mouseMove would move
the real cursor. Undo / redo go through the wired window QShortcut.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.section_scene import ElevDatumItem, ElevGridlineItem
from tests._mainwindow_helpers import dispose_main_window
from tests.test_sb4c_level_datum import BG, _render

L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
DATUM_PULL_MM = 2000.0     # test choice: the right end is pulled this far left of the auto end
GRID_PULL_MM = 700.0       # test choice: the gridline's bottom end is pulled this far up
GRID_X_MM = 2500.0         # test choice: plan x of the test gridline (crosses the north cut)


def _send(v, etype, scene_pt, button, buttons):
    vp = QPointF(v.mapFromScene(scene_pt))
    gp = QPointF(v.viewport().mapToGlobal(vp.toPoint()))
    QApplication.sendEvent(v.viewport(), QMouseEvent(
        etype, vp, gp, button, buttons, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def _drag(v, a: QPointF, b: QPointF) -> None:
    """Hover, press on *a*, move through the midpoint to *b*, release."""
    _send(v, QEvent.Type.MouseMove, a, NB, NB)
    _send(v, QEvent.Type.MouseButtonPress, a, L, L)
    _send(v, QEvent.Type.MouseMove,
          QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0), NB, L)
    _send(v, QEvent.Type.MouseMove, b, NB, L)
    _send(v, QEvent.Type.MouseButtonRelease, b, L, NB)


def _px_mm(v) -> float:
    """Scene mm per viewport pixel on the shown view (posted points snap to px)."""
    return 1.0 / v.transform().m11()


def _datum(sec, level_name: str) -> ElevDatumItem:
    (dt,) = [i for i in sec.items()
             if isinstance(i, ElevDatumItem) and i._level.name == level_name]
    return dt


def _ink(sec, rect: QRectF) -> int:
    """Painted (non-background) pixels of *sec* inside scene *rect* (5 mm / px)."""
    w, h = max(int(rect.width() / 5.0), 1), max(int(rect.height() / 5.0), 1)
    img = _render(sec, rect, w, h)
    return sum(1 for x in range(w) for y in range(h) if img.pixel(x, y) != BG)


def _drag_datum_right(v, sec, level_name: str = "Level 1"):
    """Select *level_name*'s datum and drag its right grip DATUM_PULL_MM left.
    Holds the debounced rebuild so the live item can be read. Returns
    (item, start h, target h)."""
    dt = _datum(sec, level_name)
    p2 = QPointF(dt.line().p2())
    target = QPointF(p2.x() - DATUM_PULL_MM, p2.y())
    v.fitInView(QRectF(p2.x() - 4000.0, p2.y() - 2500.0, 5000.0, 5000.0),
                Qt.AspectRatioMode.KeepAspectRatio)
    QApplication.processEvents()
    sec.clearSelection()
    dt.setSelected(True)
    QApplication.processEvents()
    _drag(v, p2, target)
    sec._rebuild_timer.stop()
    return dt, p2.x(), target.x()


def test_right_grip_drag_moves_the_painted_line_end(qapp, section_scene_for):
    """Absorbed "Level datum right grip is invisible": the line is painted to the
    dragged right end (p2), not the construction h_max. Ink right of the new
    end is gone, ink left of it stays."""
    from firepro3d.elevation_view import SectionView
    _ms, sec = section_scene_for("north")
    sec.rebuild()
    auto_right = sec.basis.h_max                        # the crop box = the auto right end
    v = SectionView(sec)
    try:
        v.resize(900, 700)
        v.show()
        QTest.qWaitForWindowExposed(v)
        dt, start, target = _drag_datum_right(v, sec)
        assert start == pytest.approx(auto_right)
        end = dt.line().p2().x()
        assert end == pytest.approx(target, abs=2 * _px_mm(v))
        sec.clearSelection()                            # no manipulator frame in the render
        QApplication.processEvents()
        gone = _ink(sec, QRectF(end + 150.0, -150.0, auto_right - end - 300.0, 300.0))
        kept = _ink(sec, QRectF(end - 1850.0, -150.0, 1700.0, 300.0))
        assert kept > 0, "datum line not painted left of its right end"
        assert gone == 0, "datum line still painted past its dragged right end"
    finally:
        sec._rebuild_timer.stop()
        v.close()


# ── Shown MainWindow on a section tab (AC10 / AC11) ──────────────────────────

@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh, SHOWN MainWindow per test (tests/test_level_manager_mainwindow.py
    idiom) with the post-open template-push offer stubbed."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d.view_3d import View3D
    from firepro3d import snap_engine
    main_mod.View3D = View3D
    monkeypatch.setattr(main_mod.MainWindow, "_maybe_offer_template_push", lambda self: None)
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    w.resize(1200, 800)
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(300)
    yield w
    # A pending debounced rebuild / view refresh on a dropped scene crashes the next test.
    for s in list(w.section_manager.open_scenes):
        s._rebuild_timer.stop()
    if hasattr(w, "_view_refresh_timer"):
        w._view_refresh_timer.stop()
    dispose_main_window(w)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


# The forced rebuild: the one shared def (integrator PI-12).
from tests._section_window_helpers import settle as _settle  # noqa: E402


def _north(win):
    """Open the North elevation tab; returns (view, scene), rebuilt."""
    win._activate_elevation("north")
    QTest.qWait(150)
    v = win.central_tabs.currentWidget()
    sec = v.scene()
    _settle(sec)
    return v, sec


def _grid(sec, uid: str) -> ElevGridlineItem:
    (eg,) = [i for i in sec.items() if isinstance(i, ElevGridlineItem)
             and i._gridline is not None and i._gridline._uid == uid]
    return eg


def _drag_grid_bottom(v, sec, uid: str):
    """Select the elevation gridline over plan gridline *uid* and drag its
    bottom grip GRID_PULL_MM up. Returns (top v before, target v)."""
    eg = _grid(sec, uid)
    q = QPointF(eg.line().p2())
    target = QPointF(q.x(), q.y() - GRID_PULL_MM)
    v.fitInView(QRectF(q.x() - 2500.0, q.y() - 2500.0, 5000.0, 5000.0),
                Qt.AspectRatioMode.KeepAspectRatio)
    QApplication.processEvents()
    sec.clearSelection()
    eg.setSelected(True)
    QApplication.processEvents()
    top = eg.line().p1().y()
    _drag(v, q, target)
    sec._rebuild_timer.stop()
    return top, target.y()


def _ctrl(win, key) -> None:
    QTest.keyClick(win.windowHandle(), key, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()


def test_datum_end_drag_is_recorded_rebuilt_and_one_undo_step(mw):
    win = mw
    scene = win.scene
    v, sec = _north(win)
    auto_left, auto_right = sec.basis.h_min, sec.basis.h_max   # the crop box (auto extent)
    scene.push_undo_state()                                      # baseline step
    _settle(sec)                  # R-F4-02: the push's debounced rebuild runs now, not mid-drag
    depth, pos = len(scene._undo_stack), scene._undo_pos
    _dt, start, target = _drag_datum_right(v, sec)
    assert start == pytest.approx(auto_right)
    rec = sec.marker.datum_ends["Level 1"]
    assert rec["right"] == pytest.approx(target, abs=2 * _px_mm(v))
    assert rec["left"] == pytest.approx(auto_left)
    assert set(sec.marker.datum_ends) == {"Level 1"}            # only the dragged datum
    assert len(scene._undo_stack) == depth + 1                   # AC11: exactly one step
    assert scene._undo_pos == pos + 1
    _settle(sec)
    assert _datum(sec, "Level 1").line().p2().x() == pytest.approx(rec["right"])
    assert _datum(sec, "Level 1").line().p1().x() == pytest.approx(auto_left)
    assert _datum(sec, "Level 2").line().p2().x() == pytest.approx(auto_right)
    _ctrl(win, Qt.Key.Key_Z)                                     # wired window shortcut
    assert sec.marker.datum_ends == {}
    _settle(sec)
    assert _datum(sec, "Level 1").line().p2().x() == pytest.approx(sec.basis.h_max)


def test_datum_end_survives_model_edit_tab_switch_and_save_reopen(mw, tmp_path):
    from firepro3d.wall import WallSegment
    win = mw
    scene = win.scene
    v, sec = _north(win)
    dt, _start, target = _drag_datum_right(v, sec)
    right = sec.marker.datum_ends["Level 1"]["right"]
    assert right == pytest.approx(target, abs=2 * _px_mm(v))
    # A model edit: its push's debounced rebuild runs on its own (interval 100 ms).
    wall = WallSegment(QPointF(-8000.0, 9000.0), QPointF(-7000.0, 9000.0), thickness_mm=200.0)
    scene.addItem(wall)
    scene._walls.append(wall)
    scene.push_undo_state()
    QTest.qWait(300)
    rebuilt = _datum(sec, "Level 1")
    assert rebuilt is not dt                                     # the scene was re-projected
    assert rebuilt.line().p2().x() == pytest.approx(right)
    # A tab switch away and back, then a forced rebuild.
    sec_idx = win.central_tabs.currentIndex()
    plan_idx = next(i for i in range(win.central_tabs.count())
                    if win.central_tabs.tabText(i).startswith("Plan: "))
    win.central_tabs.setCurrentIndex(plan_idx)
    QTest.qWait(150)
    win.central_tabs.setCurrentIndex(sec_idx)
    QTest.qWait(150)
    _settle(sec)
    assert _datum(sec, "Level 1").line().p2().x() == pytest.approx(right)
    # Save / reopen through the real open path.
    path = str(tmp_path / "ends.fpd")
    assert scene.save_to_file(path)
    win._modified = False
    win._load_project(path)
    sec2 = win.section_manager.get_or_build_scene("north")
    _settle(sec2)
    assert sec2.marker.datum_ends["Level 1"]["right"] == pytest.approx(right)
    assert _datum(sec2, "Level 1").line().p2().x() == pytest.approx(right)


def test_gridline_end_drag_is_uid_keyed_undoable_and_persists(mw, tmp_path):
    from tests._hosted_blocks_helpers import gridline
    win = mw
    scene = win.scene
    gl = gridline(scene, (GRID_X_MM, -3000.0), (GRID_X_MM, 3000.0), "F7")
    uid = gl._uid
    v, sec = _north(win)
    bottom0 = _grid(sec, uid).line().p2().y()
    scene.push_undo_state()                                      # baseline step
    _settle(sec)                  # R-F4-02: the push's debounced rebuild runs now, not mid-drag
    depth = len(scene._undo_stack)
    top, target = _drag_grid_bottom(v, sec, uid)
    rec = sec.marker.gridline_z_overrides[uid]
    assert "F7" not in sec.marker.gridline_z_overrides
    assert rec["v_bot"] == pytest.approx(target, abs=2 * _px_mm(v))
    assert rec["v_top"] == pytest.approx(top)
    assert len(scene._undo_stack) == depth + 1                   # AC11
    _settle(sec)
    assert _grid(sec, uid).line().p2().y() == pytest.approx(rec["v_bot"])
    _ctrl(win, Qt.Key.Key_Z)
    assert uid not in sec.marker.gridline_z_overrides
    _settle(sec)
    assert _grid(sec, uid).line().p2().y() == pytest.approx(bottom0)
    _ctrl(win, Qt.Key.Key_Y)
    assert sec.marker.gridline_z_overrides[uid] == rec
    path = str(tmp_path / "grid_ends.fpd")
    assert scene.save_to_file(path)
    win._modified = False
    win._load_project(path)
    sec2 = win.section_manager.get_or_build_scene("north")
    _settle(sec2)
    assert sec2.marker.gridline_z_overrides[uid] == rec
    assert _grid(sec2, uid).line().p2().y() == pytest.approx(rec["v_bot"])


def test_an_untouched_selected_datum_writes_no_record(mw):
    """OPEN-7 (integrator): two datums selected, one end dragged (the grip
    write, then the manipulator's commit hook): only the dragged datum gets a
    record, and the gesture is ONE undo step.
    RED when: the ``_built_line`` early return is deleted from
    ``ElevDatumItem._commit_grip_override`` (Level 2 is pinned to its auto
    extent: two keys)."""
    win = mw
    scene = win.scene
    v, sec = _north(win)
    d1, d2 = _datum(sec, "Level 1"), _datum(sec, "Level 2")
    scene.push_undo_state()                                      # baseline step
    _settle(sec)
    d1, d2 = _datum(sec, "Level 1"), _datum(sec, "Level 2")
    sec.clearSelection()
    d1.setSelected(True)
    d2.setSelected(True)
    depth = len(scene._undo_stack)
    p2 = d1.line().p2()
    d1.apply_grip(1, QPointF(p2.x() - DATUM_PULL_MM, p2.y()))   # the grip's write
    sec._commit_elev_grip("move")                                # the manipulator's release hook
    assert set(sec.marker.datum_ends) == {"Level 1"}
    assert len(scene._undo_stack) == depth + 1
