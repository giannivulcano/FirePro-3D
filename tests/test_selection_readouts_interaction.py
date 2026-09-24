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


_TEARDOWN_SCRIPT = r'''
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF
app = QApplication(sys.argv)
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.geometry_2d import LineItem
sc = Model_Space(scene_role="block_editor")
v = Model_View(sc); v.resize(400, 300); v.show(); app.processEvents()
ln = LineItem(QPointF(-100, 0), QPointF(100, 0)); sc.addItem(ln); ln.setSelected(True)
app.processEvents()
sc.cleanup(); v.close(); v.deleteLater(); app.processEvents()
'''


def test_scene_teardown_with_selection_exits_cleanly():
    """The dying scene emits selectionChanged after sip has marked it deleted;
    a controller slot touching it raised inside a Qt slot -> PyQt6 abort
    (silent exit 127 at interpreter shutdown). Must exit 0."""
    import os, subprocess, sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=root)
    r = subprocess.run([sys.executable, "-c", _TEARDOWN_SCRIPT], cwd=root, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.returncode, r.stderr[-2000:])


# ── Task 11: edit session + input-mode generalization ─────────────────────
from firepro3d.dynamic_input import DynamicInputHud


def _label_center(v, sc, key="length"):
    return next(e.layout.center for e in sc.readouts.layouts(v) if e.spec.key == key)


def test_begin_edit_engages_hud_and_input_mode(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    e = sc.readouts.layouts(v)[0]
    sc.readouts.begin_edit(v, e)
    hud = sc.readouts.hud
    assert isinstance(hud, DynamicInputHud) and hud.is_engaged()
    assert sc.is_input_mode() and sc.active_hud() is hud
    assert ln.isSelected()


def test_commit_applies_one_undo_step(be):
    v, sc = be
    ln = _add_line(sc)
    sc.push_undo_state()
    ln.setSelected(True)
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    pos0 = sc._undo_pos
    sc.readouts.hud.committed.emit({"Length": 500.0})
    assert ln.line().length() == pytest.approx(500.0)
    assert sc._undo_pos == pos0 + 1
    assert not sc.readouts.is_editing() and not sc.is_input_mode()


def test_out_of_range_rejects_and_stays_open(be):
    v, sc = be
    from firepro3d.geometry_2d import ArcItem
    a = ArcItem(QPointF(0, 0), 200.0, 0.0, 90.0)
    sc.addItem(a)
    a.setSelected(True)
    e = next(x for x in sc.readouts.layouts(v) if x.spec.key == "angle")
    sc.readouts.begin_edit(v, e)
    sc.readouts.hud.committed.emit({"Angle": 400.0})
    assert sc.readouts.is_editing() and a._span_deg == pytest.approx(90.0)


def test_escape_cancels(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    ed = sc.readouts.hud.editor("Length")
    QTest.keyClick(ed, Qt.Key.Key_Escape)
    assert not sc.readouts.is_editing()
    assert ln.line().length() == pytest.approx(300.0)


def test_selection_change_cancels(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    sc.clearSelection()
    assert not sc.readouts.is_editing()
