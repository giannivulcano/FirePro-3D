"""Selection dimension readouts — controller + posted-event integration
(selection-mode.md §15). Real Block Editor scene, shown Model_View."""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import LineItem, CircleItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from firepro3d import selection_manipulator


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
    return ln


def test_gate_block_editor_select_only(be):
    v, sc = be
    ln = _add_line(sc)
    assert not sc.readouts.readouts_active()          # nothing selected
    ln.setSelected(True)
    assert sc.readouts.readouts_active()
    assert [s.key for _, s in sc.readouts.entries()] == ["length"]
    plan = Model_Space()                               # plan scene: never
    ln2 = LineItem(QPointF(0, 0), QPointF(10, 0))
    plan.addItem(ln2)
    ln2.setSelected(True)
    assert not plan.readouts.readouts_active()


def test_gate_over_grip_limit(be, monkeypatch):
    v, sc = be
    monkeypatch.setattr(selection_manipulator, "GRIP_OBJECT_LIMIT", 2)
    items = [_add_line(sc, y=y) for y in (0, 40, 80)]
    for it in items:
        it.setSelected(True)
    assert not sc.readouts.readouts_active()


def test_layouts_fit_and_hit(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    lays = sc.readouts.layouts(v)
    assert len(lays) == 1 and lays[0].layout.fits
    assert sc.readouts.entry_at(v, lays[0].layout.center) is not None
    assert sc.readouts.entry_at(v, QPointF(5, 5)) is None
