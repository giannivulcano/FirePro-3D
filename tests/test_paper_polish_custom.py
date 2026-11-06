"""Paper polish AC3: Custom... through the real panel row, and the drop dialog
refusing text it cannot read."""
import gc

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog

from firepro3d import themed_message
from firepro3d.paper_space import (SCALE_CUSTOM, SheetViewPropertiesDialog,
                                   ViewportProperties)
from firepro3d.property_manager import PropertyManager
from tests._sb4d_helpers import dispose, plan_scene
from tests._sb4f_helpers import place


@pytest.fixture
def panels():
    made = []
    yield made
    for pm in made:
        pm._refresh_timer.stop()
        pm.close()
        pm.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    gc.collect()


@pytest.fixture
def rig(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    seen = []
    ms._show_status = lambda msg, *a: seen.append(msg)
    view, ps, vp = place(ms, sec, det)
    ps.commit_viewport_edit(vp, scale=0.01)
    seen.clear()
    yield ps, vp, seen
    dispose(ms, sec, tabs)


def _row(panels, ps, vp):
    pm = PropertyManager()
    panels.append(pm)
    pm.resize(400, 600)
    pm.show()
    QTest.qWaitForWindowExposed(pm)
    pm.show_properties(ViewportProperties(ps, vp))
    QApplication.processEvents()
    return pm


def _answer(monkeypatch, text, ok=True):
    asked = []

    def fake(parent, title, label, *, initial=""):
        asked.append(initial)
        return text, ok
    monkeypatch.setattr(themed_message, "themed_input_text", fake)
    return asked


def test_custom_sets_a_typed_scale_in_one_undo_step(rig, panels, monkeypatch):
    ps, vp, seen = rig
    asked = _answer(monkeypatch, '1"=15\'')
    pm = _row(panels, ps, vp)
    row = pm._prop_widgets["Scale"]
    assert row.itemText(row.count() - 1) == SCALE_CUSTOM
    count = ps.undo_stack.count()
    row.setCurrentText(SCALE_CUSTOM)
    QTest.qWait(300)                             # past the panel's debounced refresh
    assert asked == ["1:100"]
    assert vp.data.scale == pytest.approx(1 / 180)
    assert ps.undo_stack.count() == count + 1
    row = pm._prop_widgets["Scale"]
    assert row.currentText() == "1:180"          # listed as its own entry (D6)
    assert row.itemText(row.count() - 1) == SCALE_CUSTOM
    ps.undo_stack.undo()
    assert vp.data.scale == pytest.approx(0.01)


def test_bad_text_keeps_the_scale_and_shows_a_notice(rig, panels, monkeypatch):
    ps, vp, seen = rig
    _answer(monkeypatch, "banana")
    pm = _row(panels, ps, vp)
    count = ps.undo_stack.count()
    pm._prop_widgets["Scale"].setCurrentText(SCALE_CUSTOM)
    QTest.qWait(300)
    assert vp.data.scale == pytest.approx(0.01)
    assert ps.undo_stack.count() == count
    assert len(seen) == 1 and "banana" in seen[0]
    assert pm._prop_widgets["Scale"].currentText() == "1:100"


def test_cancel_changes_nothing_and_the_row_reads_the_old_scale(rig, panels, monkeypatch):
    ps, vp, seen = rig
    _answer(monkeypatch, "1:50", ok=False)
    pm = _row(panels, ps, vp)
    count = ps.undo_stack.count()
    pm._prop_widgets["Scale"].setCurrentText(SCALE_CUSTOM)
    QTest.qWait(300)
    assert vp.data.scale == pytest.approx(0.01)
    assert ps.undo_stack.count() == count
    assert seen == []
    assert pm._prop_widgets["Scale"].currentText() == "1:100"


def test_the_drop_dialog_refuses_bad_scale_text(qapp):
    seen = []
    dlg = SheetViewPropertiesDialog("Plan", notify=seen.append)
    dlg._scale_combo.setCurrentText("banana")
    dlg.accept()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert len(seen) == 1
    dlg._scale_combo.setCurrentText('1"=15\'')
    dlg.accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.get_scale() == pytest.approx(1 / 180)
    dlg.deleteLater()
