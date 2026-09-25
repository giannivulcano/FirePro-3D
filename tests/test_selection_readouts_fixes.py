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


# ── M3: selection / mode slots never raise ────────────────────────────────
def test_selection_and_mode_slots_never_raise(be, monkeypatch):
    v, sc = be

    def boom(*a):
        raise RuntimeError("slot boom")
    monkeypatch.setattr(sc.readouts, "is_editing", boom)
    sc.readouts._on_selection_changed()
    sc.readouts._on_mode_changed("select")
