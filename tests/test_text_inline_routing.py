"""Inline-edit key + mouse routing through a SHOWN Model_View with real events
(spec: text-annotation-system § Inline edit).  Keys go through the window's
shortcut map via view.windowHandle() — QTest on the widget can't drive QShortcut."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeySequence, QMouseEvent, QShortcut
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.text_item import TextItem, TextAnnotationData, editing_text_item

NO = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture
def be(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    scene.push_undo_state()
    view.activateWindow()
    view.setFocus()
    QApplication.processEvents()
    return view, scene


def _add(scene, text="Hello", x=0.0, y=0.0):
    d = TextAnnotationData(text=text, x=x, y=y, height_mm=60.0, wrap_width_mm=900.0)
    d.color = "#ffffff"
    t = TextItem(d)
    scene.addItem(t)
    scene._texts.append(t)
    t._apply_format()
    return t


def _key(view, key, mods=NO):
    QTest.keyClick(view.windowHandle(), key, mods)
    QApplication.processEvents()


def _editing(scene, t):
    scene.clearSelection()
    t.setSelected(True)
    scene._text_edit_ctl.begin(t)
    QApplication.processEvents()


def test_tool_letter_types_instead_of_switching_tool(be):
    view, scene = be
    t = _add(scene)
    _editing(scene, t)
    _key(view, Qt.Key.Key_L)
    assert scene.mode in (None, "select")
    assert "l" in t.toPlainText().lower()


def test_tool_letter_switches_tool_when_not_editing(be):
    view, scene = be
    _key(view, Qt.Key.Key_L)
    assert scene.mode == "draw_line"


def test_window_shortcut_suppressed_while_editing(be):
    view, scene = be
    fired = []
    sc = QShortcut(QKeySequence("B"), view)
    sc.activated.connect(lambda: fired.append(1))
    t = _add(scene)
    _editing(scene, t)
    _key(view, Qt.Key.Key_B)
    assert fired == [] and "b" in t.toPlainText().lower()
    scene.commit_text_edit()
    _key(view, Qt.Key.Key_B)
    assert fired == [1]                          # negative path: shortcut alive


def test_ctrl_s_still_fires_while_editing(be):
    view, scene = be
    fired = []
    sc = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), view)
    sc.activated.connect(lambda: fired.append(1))
    t = _add(scene)
    _editing(scene, t)
    _key(view, Qt.Key.Key_S, CTRL)
    assert fired == [1]


@pytest.mark.parametrize("key", [Qt.Key.Key_Space, Qt.Key.Key_Left, Qt.Key.Key_Home,
                                 Qt.Key.Key_Tab, Qt.Key.Key_Delete])
def test_navigation_and_edit_keys_stay_in_editor(be, key):
    view, scene = be
    t = _add(scene)
    _editing(scene, t)
    n_items, n_undo = len(scene._texts), len(scene._undo_stack)
    _key(view, key)
    assert editing_text_item(scene) is t
    assert scene.mode in (None, "select")
    assert (len(scene._texts), len(scene._undo_stack)) == (n_items, n_undo)


def test_tab_inserts_tab_character(be):
    view, scene = be
    t = _add(scene, "ab")
    _editing(scene, t)
    _key(view, Qt.Key.Key_Tab)
    assert "\t" in t.toPlainText()


def test_ctrl_z_is_editor_undo_not_scene_undo(be):
    view, scene = be
    t = _add(scene, "ab")
    _editing(scene, t)
    _key(view, Qt.Key.Key_X)
    pos = scene._undo_pos
    _key(view, Qt.Key.Key_Z, CTRL)
    assert editing_text_item(scene) is t and scene._undo_pos == pos
    assert t.toPlainText() == "ab"


def test_ctrl_a_selects_text_not_items(be):
    view, scene = be
    other = _add(scene, "Other", y=600.0)
    t = _add(scene, "ab")
    _editing(scene, t)
    _key(view, Qt.Key.Key_A, CTRL)
    assert t.textCursor().hasSelection()
    assert not other.isSelected()


def test_ctrl_b_is_inert(be):
    view, scene = be
    t = _add(scene)
    _editing(scene, t)
    _key(view, Qt.Key.Key_B, CTRL)
    assert t.data.bold is False and editing_text_item(scene) is t


@pytest.mark.parametrize("key,mods", [(Qt.Key.Key_Escape, NO), (Qt.Key.Key_Return, CTRL)])
def test_commit_keys(be, key, mods):
    view, scene = be
    t = _add(scene)
    _editing(scene, t)
    _key(view, Qt.Key.Key_X)
    _key(view, key, mods)
    assert editing_text_item(scene) is None
    assert "x" in t.data.text.lower()


def test_enter_is_newline(be):
    view, scene = be
    t = _add(scene, "ab")
    _editing(scene, t)
    _key(view, Qt.Key.Key_Return)
    assert "\n" in t.toPlainText() and editing_text_item(scene) is t


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_F2])
def test_enter_or_f2_enters_edit_on_single_selected_text(be, key):
    view, scene = be
    t = _add(scene)
    scene.clearSelection()
    t.setSelected(True)
    _key(view, key)
    assert editing_text_item(scene) is t
    assert t.textCursor().position() == len("Hello")


def test_f2_ignored_with_multi_selection(be):
    view, scene = be
    a, b = _add(scene), _add(scene, "B", y=600.0)
    a.setSelected(True)
    b.setSelected(True)
    _key(view, Qt.Key.Key_F2)
    assert editing_text_item(scene) is None
