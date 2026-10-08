"""LT5 E10 -- real MainWindow: an open plan line's Finish End picked from
the End Types folder loads into the project, DRAWS, and is ONE undo step;
Visible off removes the drawn end; a closed shape shows no end rows; the
same pick inside a Block Editor is one editor step; the ribbon End Type
button toggles the capability and follows undo.

Runs in its OWN pytest process (module-scoped MainWindow fixture).
"""
from PyQt6.QtCore import QPointF, QRectF, QSettings, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtTest import QTest

from firepro3d import app_data, block_library
from firepro3d import stroke_style as ss
from firepro3d.geometry_2d import LineItem, RectangleItem
from tests.lt5_support import v_end
from tests.test_block_editor_ribbon_tab import PAGE, _buttons, _group, _page
from tests.test_constraint_pick_ribbon import (  # noqa: F401
    _plan_index, mw, win_with_editor)

_W, _H = 300, 250


def _render(ms, rect):
    img = QImage(_W, _H, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, _W, _H), rect)
    p.end()
    return img


def _offband_diff(a, b, row=_H // 2, band=4):
    """Pixels that differ outside the line's own rows (the end's arms)."""
    return sum(1 for y in range(_H) if abs(y - row) > band
               for x in range(_W) if a.pixel(x, y) != b.pixel(x, y))


def _folder_end(tmp_path, name="Arrow"):
    root = tmp_path / "ends"
    root.mkdir(exist_ok=True)
    QSettings("GV", "FirePro3D").setValue(app_data.END_DIR_KEY, str(root))
    e = v_end(name=name)
    block_library.save_to_library(e, root=str(root))
    return e


def _select(ms, item, qapp):
    ms.clearSelection()
    item.setSelected(True)
    qapp.processEvents()


def test_e10_folder_end_pick_loads_draws_and_is_one_undo_step(mw, qapp, tmp_path):
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    ms = mw.scene
    ms.set_mode("select")
    e = _folder_end(tmp_path)
    s = ms.scale_manager.drawing_scale or 1.0        # Q4: printed mm x scale
    L = 20.0 * s
    rect = QRectF(L - 5.0 * s, -2.5 * s, 6.0 * s, 5.0 * s)  # 50 px / printed mm
    ln = LineItem(QPointF(0.0, 0.0), QPointF(L, 0.0))
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    ms.push_undo_state()
    uid = ln._uid
    try:
        ms.clearSelection()
        qapp.processEvents()
        before = _render(ms, rect)
        _select(ms, ln, qapp)
        pm = mw.prop_manager
        assert pm._targets == [ln]
        combo = pm._prop_widgets["Finish End"]
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items[:2] == ["By Linetype (None)", "None"] and "Arrow" in items
        pos0 = ms._undo_pos
        combo.setCurrentText("Arrow")                    # the real combo
        qapp.processEvents()
        assert ln.style["finish"]["end"] == e.id
        assert ms.get_block_definition(e.id) is not None
        assert ms._undo_pos == pos0 + 1                  # ONE step
        ms.clearSelection()
        qapp.processEvents()
        drawn = _render(ms, rect)
        assert _offband_diff(before, drawn) > 0          # the arrow's arms draw
        _select(ms, ln, qapp)
        pm._prop_widgets["Finish Visible"].click()        # Visible off
        qapp.processEvents()
        assert ln.style["finish"] == {"end": e.id, "visible": False}
        assert ms._undo_pos == pos0 + 2
        ms.clearSelection()
        qapp.processEvents()
        assert _offband_diff(before, _render(ms, rect)) == 0
        ms.undo()                                        # Visible back on
        qapp.processEvents()
        assert _offband_diff(before, _render(ms, rect)) > 0
        ms.undo()                                        # the pick + the load
        qapp.processEvents()
        assert ms.get_block_definition(e.id) is None
        (ln2,) = [l for l in ms._draw_lines if l._uid == uid]
        assert ln2.style["finish"]["end"] == ss.BY_LINETYPE
        assert _offband_diff(before, _render(ms, rect)) == 0
    finally:
        ms.clearSelection()
        for l in [l for l in ms._draw_lines if l._uid == uid]:
            ms._remove_item_from_lists(l)
        mw._modified = False
        qapp.processEvents()


def test_e10_closed_shape_shows_no_end_rows(mw, qapp):
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    ms = mw.scene
    ms.set_mode("select")
    r = RectangleItem(QPointF(0.0, 0.0), QPointF(100.0, 100.0))
    ms.addItem(r)
    ms._draw_rects.append(r)
    try:
        _select(ms, r, qapp)
        assert mw.prop_manager._targets == [r]
        widgets = mw.prop_manager._prop_widgets
        assert "Linetype" in widgets
        for k in ("Start End", "Finish End", "Start Visible", "Finish Visible"):
            assert k not in widgets, k
    finally:
        ms.clearSelection()
        ms._remove_item_from_lists(r)
        mw._modified = False
        qapp.processEvents()


def test_e10_block_editor_pick_is_one_editor_step(win_with_editor, qapp, tmp_path):
    w = win_with_editor
    ed = w._test_editor
    sc = ed.editor_scene
    e = _folder_end(tmp_path, name="Tick")
    ln = LineItem(QPointF(0.0, 0.0), QPointF(30.0, 0.0))
    ed._add_primitive(ln)
    sc.push_undo_state()
    _select(sc, ln, qapp)
    assert w.prop_manager._targets == [ln]
    pos0 = sc._undo_pos
    w.prop_manager._prop_widgets["Start End"].setCurrentText("Tick")
    qapp.processEvents()
    assert w.scene.get_block_definition(e.id) is not None   # project load
    assert ln.style["start"]["end"] == e.id
    assert sc._undo_pos == pos0 + 1
    sc.undo()
    qapp.processEvents()
    assert sc._draw_lines[-1].style["start"]["end"] == ss.BY_LINETYPE
    w.scene.undo()                                   # drop the project load
    w._modified = False


def test_e10_ribbon_end_type_button_toggles_and_follows_undo(mw, qapp):
    w = mw.block_editor_manager.open_new()
    qapp.processEvents()
    try:
        btns = _buttons(_group(_page(mw, PAGE), "Definition"))
        end, lt = btns["End Type"], btns["Linetype"]
        assert end.isCheckable() and "end type" in end.toolTip().lower()
        QTest.mouseClick(end, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert w.editor_scene.block_end == {"size": "fixed", "trim": 0.0}
        assert end.isChecked() and not lt.isChecked()
        QTest.mouseClick(lt, Qt.MouseButton.LeftButton)     # refused: exclusive
        qapp.processEvents()
        assert not lt.isChecked() and w.editor_scene.block_repeat is None
        w.editor_scene.undo()
        qapp.processEvents()
        assert w.editor_scene.block_end is None and not end.isChecked()
        w.toggle_capability("end")                         # the panel path
        qapp.processEvents()
        assert end.isChecked()
    finally:
        mw.block_editor_manager.close(w)
        qapp.processEvents()
