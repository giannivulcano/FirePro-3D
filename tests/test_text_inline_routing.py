"""Inline-edit key + mouse routing through a SHOWN Model_View with real events
(spec: text-annotation-system § Inline edit).  Keys go through the window's
shortcut map via view.windowHandle() — QTest on the widget can't drive QShortcut."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QKeySequence, QMouseEvent, QShortcut
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.text_item import TextItem, TextAnnotationData, editing_text_item

NO = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
ALT = Qt.KeyboardModifier.AltModifier
KEYPAD = Qt.KeyboardModifier.KeypadModifier


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
    # NOTE: a bare printable key is ALSO self-protected by Qt's own text
    # control (QGraphicsTextItem/QTextControl accepts the ShortcutOverride
    # for a plain character while it holds text-editing focus, independent
    # of our ShortcutOverride block below) — so this case alone does not
    # kill mutation (a); see test_real_window_shortcut_suppressed_while_editing
    # for combos (Escape / Ctrl+D / Ctrl+L) that DO require our block.
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


# Mutation-killing guards for the ShortcutOverride block in Model_View.event(),
# modelled on main.py's REAL window shortcuts: QShortcut("Escape") ->
# self._on_escape, QShortcut("Ctrl+D") -> set_mode("duplicate") (main.py
# lines ~624, ~631-632) — plus Ctrl+L, the ad-hoc probe that first proved the
# block matters for modifier combos (bare printable keys are separately
# self-protected by Qt's text control; see the "B" test above, which does not
# exercise this block).
_REAL_SHORTCUTS = [
    (Qt.Key.Key_Escape, NO, "Escape"),
    (Qt.Key.Key_D, CTRL, "Ctrl+D"),
    (Qt.Key.Key_L, CTRL, "Ctrl+L"),
]


@pytest.mark.parametrize("key,mods,seq", _REAL_SHORTCUTS)
def test_real_window_shortcut_suppressed_while_editing(be, key, mods, seq):
    view, scene = be
    fired = []
    sc = QShortcut(QKeySequence(seq), view)
    sc.activated.connect(lambda: fired.append(1))
    t = _add(scene)
    _editing(scene, t)
    _key(view, key, mods)
    assert fired == []
    if key == Qt.Key.Key_Escape:
        assert editing_text_item(scene) is None    # commits via TextItem, not the window shortcut
    else:
        assert editing_text_item(scene) is t        # inert; editor stays live (Ctrl+D/Ctrl+L unbound in the editor)


@pytest.mark.parametrize("key,mods,seq", _REAL_SHORTCUTS)
def test_real_window_shortcut_fires_when_not_editing(be, key, mods, seq):
    """Negative path: from the default (not-editing) state, the SAME window
    shortcuts fire normally — proves the suppression above is edit-session-
    scoped, not a blanket swallow."""
    view, scene = be
    fired = []
    sc = QShortcut(QKeySequence(seq), view)
    sc.activated.connect(lambda: fired.append(1))
    _key(view, key, mods)
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


def test_f2_ignored_when_mode_not_select(be):
    """Guard: entry is refused outside mode in (None, "select") — set_mode
    clears selection, so the text is re-selected AFTER switching mode to
    isolate the mode guard from the (already-covered) selection-count guard."""
    view, scene = be
    t = _add(scene)
    scene.set_mode("draw_line")
    scene.clearSelection()
    t.setSelected(True)
    assert scene.mode == "draw_line"
    _key(view, Qt.Key.Key_F2)
    assert editing_text_item(scene) is None


@pytest.mark.parametrize("key,mods", [(Qt.Key.Key_Return, CTRL), (Qt.Key.Key_F2, SHIFT)])
def test_entry_ignored_with_real_modifier(be, key, mods):
    """Guard: a genuine modifier combo (Ctrl+Enter, Shift+F2) must still
    refuse entry — only the KeypadModifier bit on Enter is special-cased
    (see test_keypad_enter_enters_edit)."""
    view, scene = be
    t = _add(scene)
    scene.clearSelection()
    t.setSelected(True)
    _key(view, key, mods)
    assert editing_text_item(scene) is None


def test_keypad_enter_enters_edit(be):
    """Numeric-keypad Enter reports as Key_Enter + KeypadModifier — must
    still count as a bare Enter for edit-entry."""
    view, scene = be
    t = _add(scene)
    scene.clearSelection()
    t.setSelected(True)
    _key(view, Qt.Key.Key_Enter, KEYPAD)
    assert editing_text_item(scene) is t


def test_alt_f4_not_swallowed_while_editing(qapp):
    """Alt+F-key (e.g. Alt+F4, close-app) must reach the window system even
    while the model-surface editor owns focus — TextItem.keyPressEvent must
    leave the event un-accepted (ignored) rather than swallowing it like a
    bare F-key.  Driven directly against the item (no shown view needed):
    the claim under test is the event's accept state, not window routing."""
    d = TextAnnotationData(text="Hello", x=0.0, y=0.0, height_mm=40.0, wrap_width_mm=600.0)
    d.color = "#ffffff"
    t = TextItem(d)
    t.begin_edit()
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F4, ALT)
    t.keyPressEvent(ev)
    assert not ev.isAccepted()
    assert t._editing is True                # session stays live; not commit/swallow
