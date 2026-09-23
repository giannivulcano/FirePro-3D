"""Inline-edit key + mouse routing through a SHOWN Model_View with real events
(spec: text-annotation-system § Inline edit).  Keys go through the window's
shortcut map via view.windowHandle() — QTest on the widget can't drive QShortcut."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QKeySequence, QMouseEvent, QShortcut, QTextCursor
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


# ── Mouse gate ──────────────────────────────────────────────────────────────

def _mouse(view, etype, pt, mods=NO, buttons=Qt.MouseButton.LeftButton,
           button=Qt.MouseButton.LeftButton):
    vp = view.mapFromScene(pt)
    # Pass the GLOBAL position too: QGraphicsScene hit-tests presses via
    # widget->mapFromGlobal(screenPos), and the 5-arg ctor seeds the global
    # position from QCursor::pos() — every item-level press would miss.
    gp = view.viewport().mapToGlobal(vp)
    ev = QMouseEvent(etype, QPointF(vp), QPointF(gp), button, buttons, mods)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def _click(view, pt, mods=NO):
    _mouse(view, QEvent.Type.MouseButtonPress, pt, mods)
    _mouse(view, QEvent.Type.MouseButtonRelease, pt, mods, Qt.MouseButton.NoButton)


def _dbl(view, pt):
    _click(view, pt)
    _mouse(view, QEvent.Type.MouseButtonDblClick, pt)
    _mouse(view, QEvent.Type.MouseButtonRelease, pt, NO, Qt.MouseButton.NoButton)


def _char_pt(t, pos):
    """Scene point just right of the caret slot *pos* (mid line).

    Restores the item's text cursor afterwards: measuring must not move the
    live caret/anchor (a Shift-click test measures between its two clicks)."""
    saved = t.textCursor()
    c = t.textCursor(); c.setPosition(pos); t.setTextCursor(c)
    r = t.caret_rect_local()
    t.setTextCursor(saved)
    return t.mapToScene(QPointF(r.x() + 2.0, r.center().y()))


def test_double_click_unselected_text_enters_with_caret_at_click(be):
    view, scene = be
    t = _add(scene, "Hello")
    pt = _char_pt(t, 2)
    scene.clearSelection()
    _dbl(view, pt)
    assert editing_text_item(scene) is t
    assert t.textCursor().position() in (2, 3)


def test_double_click_ignored_while_placement_tool_active(be):
    view, scene = be
    t = _add(scene, "Hello")
    scene.set_mode("draw_line")
    _dbl(view, _char_pt(t, 2))
    assert editing_text_item(scene) is None


def test_click_inside_moves_caret(be):
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    _click(view, _char_pt(t, 6))
    assert editing_text_item(scene) is t
    assert t.textCursor().position() in (6, 7)


def test_drag_inside_selects_text_not_moves(be):
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    pos0 = t.pos()
    a, b = _char_pt(t, 0), _char_pt(t, 5)
    _mouse(view, QEvent.Type.MouseButtonPress, a)
    _mouse(view, QEvent.Type.MouseMove, b)
    _mouse(view, QEvent.Type.MouseButtonRelease, b, NO, Qt.MouseButton.NoButton)
    assert t.textCursor().hasSelection()
    assert t.pos() == pos0


def test_shift_click_extends_selection(be):
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    _click(view, _char_pt(t, 0))
    _click(view, _char_pt(t, 5), Qt.KeyboardModifier.ShiftModifier)
    assert t.textCursor().hasSelection()


def test_double_click_while_editing_selects_word(be):
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    _dbl(view, _char_pt(t, 7))
    assert t.textCursor().selectedText() == "world"


def test_triple_click_selects_line(be):
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    pt = _char_pt(t, 7)
    _dbl(view, pt)
    _click(view, pt)
    assert t.textCursor().selectedText() == "Hello world"


def test_outside_press_commits_and_is_handled(be):
    view, scene = be
    t = _add(scene, "Hello")
    other = _add(scene, "Other", y=1000.0)
    _editing(scene, t)
    pt = _char_pt(other, 1)
    # A real click is preceded by hover: select-mode picks a TextItem through
    # the HALO preselection (halo_update runs on view mouse-move), not the
    # press-time item_under resolve (which has no TextItem branch).
    _mouse(view, QEvent.Type.MouseMove, pt, NO, Qt.MouseButton.NoButton)
    _click(view, pt)
    assert editing_text_item(scene) is None
    assert other.isSelected()


def test_handle_drag_resizes_and_keeps_editing(be):
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    QApplication.processEvents()
    m = scene._live_manip()
    br = t.grip_points()[4]                        # bottom-right corner grip
    assert m is not None and m.hit_handle(br), "precondition: BR grip is a handle"
    w0 = t.data.wrap_width_mm
    dst = QPointF(br.x() + 300.0, br.y())
    _mouse(view, QEvent.Type.MouseButtonPress, br)
    _mouse(view, QEvent.Type.MouseMove, dst)
    _mouse(view, QEvent.Type.MouseButtonRelease, dst, NO, Qt.MouseButton.NoButton)
    QApplication.processEvents()
    assert editing_text_item(scene) is t
    assert t.data.wrap_width_mm > w0
    assert t.hasFocus(), "keyboard handed back to the editor after the handle press"


def test_escape_mid_handle_drag_cancels_drag_keeps_editing(be):
    """Esc during a live manipulator drag while editing cancels the GESTURE
    (box restored) and leaves the edit session open — it must not commit the
    text mid-gesture (the scene's editing bypass must not pre-empt it)."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    QApplication.processEvents()
    m = scene._live_manip()
    br = t.grip_points()[4]
    assert m is not None and m.hit_handle(br), "precondition: BR grip is a handle"
    w0 = t.data.wrap_width_mm
    dst = QPointF(br.x() + 300.0, br.y())
    _mouse(view, QEvent.Type.MouseButtonPress, br)
    _mouse(view, QEvent.Type.MouseMove, dst)
    assert m.is_dragging(), "precondition: handle drag is live"
    _key(view, Qt.Key.Key_Escape)
    assert not m.is_dragging()
    assert t.data.wrap_width_mm == pytest.approx(w0)
    assert editing_text_item(scene) is t
    _mouse(view, QEvent.Type.MouseButtonRelease, dst, NO, Qt.MouseButton.NoButton)
    assert editing_text_item(scene) is t


# ── Text wins over handles while editing (user decision) ────────────────────

def _caret_to(t, pos):
    c = t.textCursor(); c.setPosition(pos); t.setTextCursor(c)


def test_press_on_centre_grip_mid_edit_moves_caret_not_box(be):
    """The centre move grip is never a handle while editing: a press there
    positions the caret; no manipulator drag, box unchanged."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    QApplication.processEvents()
    m = scene._live_manip()
    centre = t.grip_points()[TextItem.MOVE_GRIP_INDEX]
    assert m.hit_handle(centre), "precondition: centre grip is a handle"
    assert not any(r.contains(t.mapFromScene(centre)) for r in t.content_rects_local()),         "precondition: centre grip lies outside the painted text"
    _caret_to(t, 0)
    pos0, w0 = t.pos(), t.data.wrap_width_mm
    dst = QPointF(centre.x() + 200.0, centre.y() + 200.0)
    _mouse(view, QEvent.Type.MouseButtonPress, centre)
    assert not m.is_dragging()
    _mouse(view, QEvent.Type.MouseMove, dst)
    _mouse(view, QEvent.Type.MouseButtonRelease, dst, NO, Qt.MouseButton.NoButton)
    assert editing_text_item(scene) is t
    assert t.textCursor().position() == len("Hello world")   # caret moved to the press
    assert t.pos() == pos0 and t.data.wrap_width_mm == w0


def test_press_on_char0_over_left_mid_grip_places_caret(be):
    """A resize handle overlapping PAINTED text loses to the caret."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    QApplication.processEvents()
    m = scene._live_manip()
    pt = _char_pt(t, 0)
    assert m.hit_handle(pt), "precondition: char 0 overlaps the left mid-edge grip"
    _caret_to(t, 5)
    w0 = t.data.wrap_width_mm
    _click(view, pt)
    assert editing_text_item(scene) is t
    assert t.textCursor().position() in (0, 1)
    assert not t.textCursor().hasSelection()
    assert t.data.wrap_width_mm == w0


def test_right_click_inside_editing_box_reaches_native_text_menu(be, monkeypatch):
    """Right press + QContextMenuEvent through the viewport → the scene gate
    hands the event to the editing TextItem's (native) context menu."""
    from PyQt6.QtGui import QContextMenuEvent
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    calls = []
    monkeypatch.setattr(TextItem, "contextMenuEvent",
                        lambda self, ev: calls.append((self, QPointF(ev.pos()))))
    # Never block on a real menu if the gate misses.
    monkeypatch.setattr(scene, "_show_entity_context_menu",
                        lambda *a, **k: calls.append("entity-menu"))
    pt = _char_pt(t, 3)
    _mouse(view, QEvent.Type.MouseButtonPress, pt, NO, Qt.MouseButton.RightButton,
           Qt.MouseButton.RightButton)
    vp = view.mapFromScene(pt)
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, vp,
                           view.viewport().mapToGlobal(vp), NO)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()
    assert len(calls) == 1 and calls[0][0] is t
    assert t.boundingRect().contains(calls[0][1])        # item-local pos
    assert editing_text_item(scene) is t


def test_right_click_outside_editing_box_commits(be):
    """M6: a right-click OUTSIDE the editing box commits the session (mirrors
    the left-press outside-commit rule) — only a right-click INSIDE the box
    keeps it live for the native context menu (see the "inside" test above)."""
    view, scene = be
    t = _add(scene, "Hello")
    other = _add(scene, "Other", y=1000.0)
    _editing(scene, t)
    pt = _char_pt(other, 1)
    _mouse(view, QEvent.Type.MouseMove, pt, NO, Qt.MouseButton.NoButton)
    _mouse(view, QEvent.Type.MouseButtonPress, pt, NO, Qt.MouseButton.RightButton,
           Qt.MouseButton.RightButton)
    assert editing_text_item(scene) is None
    assert t.data.text == "Hello"


def test_middle_click_pan_does_not_commit_edit(be):
    """M6 (negative path): a middle-click (pan) — INSIDE or outside the box —
    must never commit; Model_View intercepts MiddleButton for panning before
    it ever reaches the scene's mouse gate."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    pt = _char_pt(t, 2)
    _mouse(view, QEvent.Type.MouseButtonPress, pt, NO, Qt.MouseButton.MiddleButton,
           Qt.MouseButton.MiddleButton)
    assert editing_text_item(scene) is t
    _mouse(view, QEvent.Type.MouseButtonRelease, pt, NO, Qt.MouseButton.NoButton,
           Qt.MouseButton.MiddleButton)
    assert editing_text_item(scene) is t


# ── Coverage gap (b): clipboard while editing must not touch the scene ──────

def test_ctrl_c_ctrl_v_while_editing_leave_scene_untouched(be):
    """Coverage gap (b): Ctrl+C / Ctrl+V while editing are the text control's
    own clipboard ops (spec: 'Ctrl+A/C/X/V act on text') — they must not
    reach the scene's own copy/paste (item count unchanged, no scene items
    pasted), and the system clipboard ends up holding the copied TEXT, not a
    serialized scene item."""
    from PyQt6.QtGui import QGuiApplication
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    n_items = len(scene._texts)
    saved_clip = QGuiApplication.clipboard().text()
    try:
        c = t.textCursor()
        c.setPosition(0)
        c.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        t.setTextCursor(c)
        _key(view, Qt.Key.Key_C, CTRL)
        assert QGuiApplication.clipboard().text() == "Hello"
        c2 = t.textCursor()
        c2.setPosition(len(t.toPlainText()))
        t.setTextCursor(c2)
        _key(view, Qt.Key.Key_V, CTRL)
        assert editing_text_item(scene) is t
        assert len(scene._texts) == n_items
        assert "Hello" in t.toPlainText()
    finally:
        QGuiApplication.clipboard().setText(saved_clip)


# ── Coverage gap (c): plan-role scene, legacy-loaded TextItem ───────────────

def test_plan_role_scene_inline_edit_full_cycle(shown_model_view):
    """Coverage gap (c): the model-surface inline-edit contract holds on a
    PLAN-role scene too, not only scene_role='block_editor' — with a TextItem
    added directly (mirrors a legacy-loaded project's text, never routed
    through _press_text). Double-click enters edit, typing works, Esc
    commits."""
    view, scene = shown_model_view
    assert scene.scene_role != "block_editor"
    t = _add(scene, "Hello")
    scene.clearSelection()
    pt = _char_pt(t, 2)
    _dbl(view, pt)
    assert editing_text_item(scene) is t
    _key(view, Qt.Key.Key_X)
    assert "x" in t.toPlainText().lower()
    _key(view, Qt.Key.Key_Escape)
    assert editing_text_item(scene) is None
    assert "x" in t.data.text.lower()


def test_double_click_on_centre_grip_of_selected_text_enters_edit(be):
    """Entry: text wins over the centre grip too (spec Q7) — double-click
    anywhere inside the box enters edit, caret at the click."""
    view, scene = be
    t = _add(scene, "Hello world")
    scene.clearSelection()
    t.setSelected(True)
    QApplication.processEvents()
    m = scene._live_manip()
    centre = t.grip_points()[TextItem.MOVE_GRIP_INDEX]
    assert m.hit_handle(centre), "precondition: centre grip is a handle"
    pos0 = t.pos()
    _dbl(view, centre)
    assert editing_text_item(scene) is t
    assert t.pos() == pos0                     # the first click's grip gesture moved nothing
    assert t.textCursor().position() == len("Hello world")   # nearest slot to the click


# ── Review follow-ups (Task 5 review I1/I2/M3/M5/M6) ────────────────────────

def test_lost_release_then_commit_does_not_swallow_next_manip_release(be):
    """I1: a gate-consumed press whose release is lost (session committed
    mid-gesture) must not leave a stale flag that swallows the NEXT gesture's
    release — the manipulator would stay stuck mid-drag."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    _mouse(view, QEvent.Type.MouseButtonPress, _char_pt(t, 2))   # gate-consumed
    scene._text_edit_ctl.commit()        # e.g. modal / autosave; release lost
    assert editing_text_item(scene) is None
    scene.clearSelection()
    t.setSelected(True)
    QApplication.processEvents()
    m = scene._live_manip()
    br = t.grip_points()[4]
    w0 = t.data.wrap_width_mm
    dst = QPointF(br.x() + 300.0, br.y())
    _mouse(view, QEvent.Type.MouseButtonPress, br)
    _mouse(view, QEvent.Type.MouseMove, dst)
    assert m.is_dragging(), "precondition: handle drag is live"
    _mouse(view, QEvent.Type.MouseButtonRelease, dst, NO, Qt.MouseButton.NoButton)
    assert not m.is_dragging(), "manipulator stuck: release swallowed by a stale flag"
    assert t.data.wrap_width_mm > w0


def test_stale_flag_buttonless_move_does_not_extend_selection(be):
    """I1: after a lost release, a new session's plain hover (no button) must
    not extend the text selection."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    _mouse(view, QEvent.Type.MouseButtonPress, _char_pt(t, 2))
    scene._text_edit_ctl.commit()
    _editing(scene, t)                    # new session via the Enter/F2 path
    _mouse(view, QEvent.Type.MouseMove, _char_pt(t, 8), NO, Qt.MouseButton.NoButton)
    assert not t.textCursor().hasSelection(), "hover extended the selection"


def test_context_menu_reaches_editing_item_under_overlapping_text(be, monkeypatch):
    """I2: a non-editing TextItem stacked above the editing one must let the
    right-click through (ignore) instead of opening its own Delete menu."""
    from PyQt6.QtGui import QContextMenuEvent
    import firepro3d.text_item as text_item_mod
    view, scene = be
    t = _add(scene, "Hello world")
    other = _add(scene, "Zzzzzzzzzzzz")
    other.setZValue(t.zValue() + 1)
    _editing(scene, t)
    menus, got = [], []

    class _FakeMenu:                       # never block on a real QMenu.exec
        def __init__(self, *a, **k):
            menus.append(self)

        def addAction(self, *a, **k):
            return object()

        def exec(self, *a, **k):
            return None

    monkeypatch.setattr(text_item_mod, "QMenu", _FakeMenu)
    real = TextItem.contextMenuEvent

    def _spy(self, ev):
        got.append(self)
        if self is t:                      # editing item: record only (native menu blocks)
            ev.accept()
            return
        real(self, ev)

    monkeypatch.setattr(TextItem, "contextMenuEvent", _spy)
    pt = _char_pt(t, 3)
    vp = view.mapFromScene(pt)
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, vp,
                           view.viewport().mapToGlobal(vp), NO)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()
    assert menus == [], "overlapping item opened its own menu"
    assert got and got[-1] is t
    assert editing_text_item(scene) is t


def test_fast_click_far_from_double_click_is_caret_not_line(be):
    """M3: a quick third click far from the word-select is a caret click, not
    a triple-click line select."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    _dbl(view, _char_pt(t, 1))
    _click(view, _char_pt(t, 9))
    assert not t.textCursor().hasSelection(), "far fast click selected the line"
    assert t.textCursor().position() in (9, 10)


def test_drag_select_keeps_cursor_readout_live(be):
    """M5: the status-bar X/Y readout stays live during a drag-select."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    seen = []
    scene.cursorMoved.connect(seen.append)
    a, b = _char_pt(t, 1), _char_pt(t, 5)
    _mouse(view, QEvent.Type.MouseButtonPress, a)
    seen.clear()
    _mouse(view, QEvent.Type.MouseMove, b)
    _mouse(view, QEvent.Type.MouseButtonRelease, b, NO, Qt.MouseButton.NoButton)
    assert t.textCursor().hasSelection()
    assert seen, "cursorMoved starved during drag-select"


def _spy_release_pipeline(monkeypatch, scene):
    """Count calls into the scene's post-gate release pipeline (its first
    statement after the gate reads the live manipulator)."""
    calls = []
    real = scene._live_manip

    def _spy():
        calls.append(1)
        return real()

    monkeypatch.setattr(scene, "_live_manip", _spy)
    return calls


def test_drag_select_release_is_consumed_by_gate(be, monkeypatch):
    """M6: the release ending a drag-select belongs to the text editor — it
    must not run the scene's manipulator / rubber-band release pipeline."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    a, b = _char_pt(t, 1), _char_pt(t, 5)
    _mouse(view, QEvent.Type.MouseButtonPress, a)
    _mouse(view, QEvent.Type.MouseMove, b)
    calls = _spy_release_pipeline(monkeypatch, scene)
    _mouse(view, QEvent.Type.MouseButtonRelease, b, NO, Qt.MouseButton.NoButton)
    assert calls == []
    assert t.textCursor().hasSelection()


def test_double_click_entry_release_is_consumed_by_gate(be, monkeypatch):
    """M6: the release that follows a double-click entry is swallowed."""
    view, scene = be
    t = _add(scene, "Hello world")
    scene.clearSelection()
    pt = _char_pt(t, 2)
    _click(view, pt)
    _mouse(view, QEvent.Type.MouseButtonDblClick, pt)
    assert editing_text_item(scene) is t
    calls = _spy_release_pipeline(monkeypatch, scene)
    _mouse(view, QEvent.Type.MouseButtonRelease, pt, NO, Qt.MouseButton.NoButton)
    assert calls == []


def test_double_click_entry_rotated_centre_aligned_places_caret(be):
    """M6: entry caret lands at the clicked character on a 30° rotated,
    centre-aligned box (hit-test honours rotation + alignment)."""
    view, scene = be
    t = _add(scene, "Hello world")
    t.data.align = "C"
    t._apply_format()
    t.set_angle(30.0)
    QApplication.processEvents()
    pt = _char_pt(t, 7)
    scene.clearSelection()
    _dbl(view, pt)
    assert editing_text_item(scene) is t
    assert t.textCursor().position() in (7, 8)


def test_lost_release_mid_session_does_not_hijack_next_handle_drag(be):
    """I1: a gate-consumed press whose release is lost while the session
    stays live must not leave the next handle drag hijacked (every press
    drops the stale pairing flags)."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    _mouse(view, QEvent.Type.MouseButtonPress, _char_pt(t, 2))   # release lost
    m = scene._live_manip()
    br = t.grip_points()[4]
    w0 = t.data.wrap_width_mm
    dst = QPointF(br.x() + 300.0, br.y())
    _mouse(view, QEvent.Type.MouseButtonPress, br)
    _mouse(view, QEvent.Type.MouseMove, dst)
    _mouse(view, QEvent.Type.MouseButtonRelease, dst, NO, Qt.MouseButton.NoButton)
    assert not m.is_dragging()
    assert t.data.wrap_width_mm > w0
    assert editing_text_item(scene) is t


def test_buttonless_move_after_lost_release_does_not_extend_selection(be):
    """I1: a hover (no button held) after a lost release, within the same
    session, must not extend the text selection."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    _mouse(view, QEvent.Type.MouseButtonPress, _char_pt(t, 2))   # release lost
    _mouse(view, QEvent.Type.MouseMove, _char_pt(t, 8), NO, Qt.MouseButton.NoButton)
    assert not t.textCursor().hasSelection()


def test_right_release_mid_drag_select_does_not_end_it(be):
    """I1: only the LEFT release ends a drag-select — a right-button release
    arriving mid-drag leaves the selection gesture live."""
    view, scene = be
    t = _add(scene, "Hello world")
    _editing(scene, t)
    a, b = _char_pt(t, 1), _char_pt(t, 5)
    _mouse(view, QEvent.Type.MouseButtonPress, a)
    _mouse(view, QEvent.Type.MouseButtonRelease, a, NO, Qt.MouseButton.LeftButton,
           Qt.MouseButton.RightButton)
    _mouse(view, QEvent.Type.MouseMove, b)
    assert t.textCursor().hasSelection()
