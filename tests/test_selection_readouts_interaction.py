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


# ── Task 12: view routing — hover, press, paint ───────────────────────────
def _move(v, vp):
    QApplication.sendEvent(v.viewport(), QMouseEvent(
        QEvent.Type.MouseMove, QPointF(vp), Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))


def _click(v, vp):
    for t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(v.viewport(), QMouseEvent(
            t, QPointF(vp), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))


def test_hover_label_beats_parent_halo(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    c = _label_center(v, sc)
    _move(v, c)
    assert sc.readouts._hover is not None
    assert sc.halo_item() is None                     # label won, not the line


def test_click_label_opens_editor_without_selection_change(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    c = _label_center(v, sc)
    _move(v, c)
    _click(v, c)
    assert sc.readouts.is_editing()
    assert sc.selectedItems() == [ln]
    assert not getattr(v, "_rb_active", False)


def test_click_label_works_with_halo_disabled(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    sc.halo_enabled = False
    _click(v, _label_center(v, sc))
    assert sc.readouts.is_editing()


def test_click_away_cancels_and_is_consumed(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    _click(v, _label_center(v, sc))
    _click(v, v.mapFromScene(QPointF(400, 300)))       # empty canvas
    assert not sc.readouts.is_editing()
    assert sc.selectedItems() == [ln]                  # press consumed, no deselect


def test_hidden_label_not_pickable(be):
    v, sc = be
    ln = _add_line(sc, -2, 2)                          # 4 px long: label can't fit
    ln.setSelected(True)
    lay = sc.readouts.layouts(v)[0].layout
    assert not lay.fits
    _click(v, lay.center)
    assert not sc.readouts.is_editing()


def test_grip_beats_label(be, monkeypatch):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    c = _label_center(v, sc)
    m = sc._live_manip()
    monkeypatch.setattr(m, "hit_handle", lambda _p: True)
    assert sc.readouts.entry_at(v, c) is None


# ── Task 13: integration guards — live refresh, units, transient, Ctrl+Z ──
from firepro3d.scale_manager import DisplayUnit


def _text_of(v, sc, key="length"):
    return next(e.layout.text for e in sc.readouts.layouts(v) if e.spec.key == key)


def test_grip_drag_updates_text(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    before = _text_of(v, sc)
    ln.apply_grip(2, QPointF(450, 0))                 # the grip path's mutation
    assert _text_of(v, sc) != before


def test_units_change_repaints_without_mouse_move(be, monkeypatch):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    QApplication.processEvents()
    calls = []
    monkeypatch.setattr(sc.readouts, "refresh", lambda: calls.append(1))
    sc.set_display_unit(DisplayUnit.METRIC_MM)
    assert calls, "units change must force a readout repaint"
    assert _text_of(v, sc).endswith("mm")


def _add_tracked_line(sc):
    """A line registered in the scene's tracking list, so undo snapshots it
    (bare ``addItem`` is invisible to ``_capture_network``)."""
    ln = _add_line(sc)
    sc._draw_lines.append(ln)
    return ln


def test_undo_restores_value(be):
    v, sc = be
    ln = _add_tracked_line(sc)
    sc.push_undo_state()
    ln.setSelected(True)
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    sc.readouts.hud.committed.emit({"Length": 500.0})
    assert ln.line().length() == pytest.approx(500.0)
    sc.undo()
    restored = [i for i in sc.items() if isinstance(i, LineItem)]
    assert len(restored) == 1
    assert restored[0].line().length() == pytest.approx(300.0)


def test_ctrl_z_in_field_is_field_undo_not_scene_undo(be):
    v, sc = be
    ln = _add_tracked_line(sc)
    sc.push_undo_state()
    ln.setSelected(True)
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    pos0 = sc._undo_pos
    ed = sc.readouts.hud.editor("Length")
    QTest.keyClicks(ed, "9")
    QTest.keyClick(ed, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert sc._undo_pos == pos0 and sc.readouts.is_editing()
    assert ln.line().length() == pytest.approx(300.0)


def test_hidden_in_placement_and_text_edit(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    assert sc.readouts.entries() != []                # precondition: visible
    sc.set_mode("draw_line")
    assert sc.readouts.entries() == []


def test_transient_not_in_bounding_rect_or_serialization(be, monkeypatch):
    """Readouts add no scene items and no bounding-rect extent.

    Selecting also shows the selection manipulator's grip handles (real
    QGraphicsItems, not readouts), so the baseline is the SAME selection with
    the readout gate forced off; turning readouts on must change nothing.
    """
    v, sc = be
    ln = _add_line(sc)
    d0 = ln.to_dict()
    ctl = sc.readouts
    monkeypatch.setattr(ctl, "readouts_active", lambda: False)
    ln.setSelected(True)
    QApplication.processEvents()
    r0 = sc.itemsBoundingRect()
    ids0 = {id(i) for i in sc.items()}
    monkeypatch.undo()                                # readouts back on
    ctl.refresh()
    QApplication.processEvents()
    assert ctl.entries() != []                        # precondition: visible
    v.viewport().grab()                               # force a real paint pass
    assert sc.itemsBoundingRect() == r0
    assert {id(i) for i in sc.items()} == ids0
    assert ln.to_dict() == d0
    assert all(type(i).__module__ not in ("firepro3d.selection_readouts",
                                          "firepro3d.readout_paint")
               for i in sc.items())


# ── Contract fix: the canvas is inert while a readout edit is open (§15) ──
def test_halo_suppressed_while_editing(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    body = v.mapFromScene(QPointF(-120, 0))           # line body, away from the HUD
    _move(v, body)
    assert sc.halo_item() is ln                       # precondition: HALO live
    _move(v, v.mapFromScene(QPointF(400, 300)))       # off the line
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    _move(v, body)
    assert sc.halo_item() is None


def test_begin_edit_clears_existing_halo(be):
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    _move(v, v.mapFromScene(QPointF(-120, 0)))
    assert sc.halo_item() is ln                       # precondition
    sc.readouts.begin_edit(v, sc.readouts.layouts(v)[0])
    assert sc.halo_item() is None


# ── Perf: scene changes repaint only the readout region ───────────────────
def test_scene_change_repaints_readout_region_not_full_viewport(be, monkeypatch):
    """A geometry change dirties old ∪ new readout rects, never the whole
    viewport (the full repaint cost ~2.7x per grip step on a dense scene)."""
    from PyQt6.QtCore import QRect
    v, sc = be
    ln = _add_line(sc)
    ln.setSelected(True)
    QApplication.processEvents()
    v.viewport().grab()                               # a paint pass records rects
    old_c = _label_center(v, sc)
    vp = v.viewport()
    calls = []
    real = vp.update

    def spy(*a):
        calls.append(a)
        return real(*a)
    monkeypatch.setattr(vp, "update", spy)
    ln.apply_grip(1, QPointF(0, 200))                 # translate: label moves 200 px
    QApplication.processEvents()
    new_c = _label_center(v, sc)
    assert (new_c - old_c).manhattanLength() > 100    # precondition: label moved
    assert calls, "scene change must repaint the readouts"
    assert all(a for a in calls), f"full-viewport update used: {calls}"
    rects = [a[0] for a in calls if isinstance(a[0], QRect)]
    assert any(r.contains(old_c.toPoint()) and r.contains(new_c.toPoint())
               for r in rects), rects
