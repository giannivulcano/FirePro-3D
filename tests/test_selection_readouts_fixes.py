"""Selection dimension readouts — integration-review fix round
(selection-mode.md §15, 2d-geometry.md §8). Scene-level; the MainWindow-level
fixes live in test_selection_readouts_mainwindow.py."""
import pytest
from PyQt6.QtCore import QEvent, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QImage, QMouseEvent, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from firepro3d.selection_readouts import SelectionReadoutController


@pytest.fixture
def be(qapp):
    """(view, scene) — shown Block Editor scene at 1 px / mm, centred."""
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(900, 700)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(0, 0)
    v.setFocus()
    sc.set_mode("select")
    QApplication.processEvents()
    yield v, sc
    if sc.readouts.is_editing():
        sc.readouts.cancel_edit()
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def _add_line(sc, x0=-150, x1=150, y=0):
    ln = LineItem(QPointF(x0, y), QPointF(x1, y))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return ln


def _add_rect(sc, x, w=100.0, h=50.0):
    r = RectangleItem(QPointF(x, 0), QPointF(x + w, h))
    sc.addItem(r)
    sc._draw_rects.append(r)
    return r


def _spy_update(monkeypatch, v):
    vp = v.viewport()
    calls = []
    real = vp.update

    def spy(*a):
        calls.append(a)
        return real(*a)
    monkeypatch.setattr(vp, "update", spy)
    return calls


# ── I2: plan scenes pay nothing; selection changes repaint regions ────────
def test_plan_scene_controller_connects_nothing(qapp, monkeypatch):
    hits = []
    for name in ("_on_scene_changed", "_on_selection_changed", "_on_mode_changed"):
        monkeypatch.setattr(SelectionReadoutController, name,
                            lambda self, *a, _n=name: hits.append(_n))
    plan = Model_Space()
    assert plan.receivers(plan.changed) == 0, \
        "any changed receiver disables Qt's direct item->view update path"
    plan.changed.emit([])
    plan.selectionChanged.emit()
    plan.modeChanged.emit("select")
    assert hits == []
    ed = Model_Space(scene_role="block_editor")
    ed.changed.emit([])
    ed.selectionChanged.emit()
    ed.modeChanged.emit("select")
    assert set(hits) == {"_on_scene_changed", "_on_selection_changed",
                         "_on_mode_changed"}


def test_selection_change_repaints_region_not_full_viewport(be, monkeypatch):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    QApplication.processEvents()
    v.viewport().grab()                               # paint pass records rects
    c = next(e.layout.center for e in sc.readouts.layouts(v))
    # Isolate the controller's slot: Model_Space._on_selection_changed (the
    # scene's own gridline/underlay handler) has always full-repainted.
    sc.blockSignals(True)
    sc.clearSelection()
    sc.blockSignals(False)
    calls = _spy_update(monkeypatch, v)
    sc.readouts._on_selection_changed()
    assert calls, "selection change must repaint the readouts"
    assert all(a for a in calls), f"full-viewport update used: {calls}"
    rects = [a[0] for a in calls if isinstance(a[0], QRect)]
    assert any(r.contains(c.toPoint()) for r in rects), rects


# ── I3: multi-select panel edit = one undo step ───────────────────────────
def test_multi_select_panel_edit_is_one_undo_step(be):
    from firepro3d.property_manager import PropertyManager
    v, sc = be
    rects = [_add_rect(sc, x) for x in (0.0, 300.0, 600.0)]
    sc.push_undo_state()
    for r in rects:
        r.setSelected(True)
    pm = PropertyManager()
    pm.show_properties(list(rects))
    pos0 = sc._undo_pos
    pm._apply_property("Width", 80.0)
    assert [r.rect().width() for r in rects] == pytest.approx([80.0] * 3)
    assert sc._undo_pos == pos0 + 1
    sc.undo()
    assert sorted(r.rect().width() for r in sc._draw_rects) == \
        pytest.approx([100.0] * 3)
    pm.deleteLater()


def test_single_select_panel_edit_is_one_undo_step(be):
    from firepro3d.property_manager import PropertyManager
    v, sc = be
    r = _add_rect(sc, 0.0)
    sc.push_undo_state()
    r.setSelected(True)
    pm = PropertyManager()
    pm.show_properties([r])
    pos0 = sc._undo_pos
    pm._apply_property("Width", 80.0)
    assert r.rect().width() == pytest.approx(80.0)
    assert sc._undo_pos == pos0 + 1
    pm.deleteLater()


# ── I4: readout commit refreshes the property panel ───────────────────────
def test_commit_requests_property_update(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    got = []
    sc.requestPropertyUpdate.connect(got.append)
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    sc.readouts.hud.committed.emit({"Length": 500.0})
    assert got, "panel must be told to re-read after a readout commit"
    payload = got[-1]
    targets = payload if isinstance(payload, list) else [payload]
    assert ln in targets


# ── M1: entry_at gates before touching the manipulator ────────────────────
def test_entry_at_gates_before_manipulator(be, monkeypatch):
    v, sc = be

    class _Manip:
        calls = 0

        def isVisible(self):
            return True

        def hit_handle(self, _p):
            _Manip.calls += 1
            return False
    m = _Manip()
    monkeypatch.setattr(sc, "_live_manip", lambda: m)
    assert not sc.readouts.readouts_active()          # nothing selected
    assert sc.readouts.entry_at(v, QPointF(10, 10)) is None
    assert _Manip.calls == 0


# ── M2: virtual overrides never let a readout exception escape ────────────
def test_draw_foreground_survives_paint_error(be, monkeypatch):
    v, sc = be

    def boom(*a):
        raise RuntimeError("paint boom")
    monkeypatch.setattr(sc.readouts, "paint", boom)
    img = QImage(50, 50, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    try:
        v.drawForeground(p, QRectF(0, 0, 50, 50))     # must not raise
    finally:
        p.end()


def test_mouse_move_survives_hover_error(be, monkeypatch):
    v, sc = be

    def boom(*a):
        raise RuntimeError("hover boom")
    monkeypatch.setattr(sc.readouts, "hover_at", boom)
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(20, 20),
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    v.mouseMoveEvent(ev)                              # must not raise


# ── M3: selection / mode slots never raise ────────────────────────────────
def test_selection_and_mode_slots_never_raise(be, monkeypatch):
    v, sc = be

    def boom(*a):
        raise RuntimeError("slot boom")
    monkeypatch.setattr(sc.readouts, "is_editing", boom)
    sc.readouts._on_selection_changed()
    sc.readouts._on_mode_changed("select")


# ── M5: no-op edits push no undo ──────────────────────────────────────────
def test_noop_readout_commit_pushes_no_undo(be):
    v, sc = be
    ln = _add_line(sc)
    sc.push_undo_state()
    ln.setSelected(True)
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    pos0 = sc._undo_pos
    got = []
    sc.requestPropertyUpdate.connect(got.append)
    sc.readouts.hud.committed.emit({"Length": 300.0})
    assert sc._undo_pos == pos0
    assert not sc.readouts.is_editing()
    assert got == []                                  # nothing applied
    assert ln.line().length() == pytest.approx(300.0)


def test_noop_panel_set_property_pushes_no_undo(be):
    v, sc = be
    r = _add_rect(sc, 0.0)
    sc.push_undo_state()
    pos0 = sc._undo_pos
    r.set_property("Width", 100.0)                    # unchanged
    assert sc._undo_pos == pos0
    r.set_property("Width", 120.0)                    # changed
    assert sc._undo_pos == pos0 + 1


# ── M6: leaving a label restores the prior instruction ────────────────────
def test_leaving_label_restores_prior_instruction(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    sc.instructionChanged.emit("Select items to edit")
    got = []
    sc.instructionChanged.connect(got.append)
    c = next(e.layout.center for e in sc.readouts.layouts(v))
    sc.readouts.hover_at(v, c)
    assert got[-1].endswith("click to edit")
    sc.readouts.hover_at(v, QPointF(5, 5))
    assert got[-1] == "Select items to edit"


# ── M10: a mode change cancels an open edit ───────────────────────────────
def test_mode_change_cancels_edit_and_hides_hud(be):
    from PyQt6 import sip
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    hud = sc.readouts.hud
    assert hud is not None and sc.readouts.is_editing()
    sc.set_mode("draw_line")
    assert not sc.readouts.is_editing()
    QApplication.processEvents()
    assert sip.isdeleted(hud) or not hud.isVisible()
    sc.set_mode("select")
