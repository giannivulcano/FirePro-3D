"""D1: Block Editor page carries Edit + Modify groups acting on the editor scene.

Governing spec: docs/specs/scene-tools.md D1 (surface) / D3 (select-first).
"""
from __future__ import annotations

import json
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QToolButton

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from firepro3d.modify_tools_controller import ModifyToolsController
from main import MainWindow
from tests._modify_tools_helpers import ignore_os_mouse
from tests._snap_polish_helpers import click


@pytest.fixture(scope="module")
def _main_window_singleton(qapp, tmp_path_factory):
    """Module-scoped MainWindow (same pattern as test_ribbon_contextual.py).

    The autosave path is redirected to a temp dir so a real recovery file on
    this machine can't pop the modal "Recover Unsaved Work" dialog when a test
    pumps events (``_check_recovery`` runs on a 500 ms single-shot).
    """
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    recovery = str(tmp_path_factory.mktemp("autosave") / "recovery.FPD")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MainWindow, "_autosave_path", staticmethod(lambda: recovery))
        win = MainWindow()
        win.show()
        QTest.qWaitForWindowExposed(win)
        yield win
        win._modified = False
        win.close()
        win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def main_window(_main_window_singleton):
    """Per-test view of the shared MainWindow."""
    yield _main_window_singleton


def _wait_until(pred, timeout_s: float = 2.0) -> None:
    """Bounded event-pumping poll (PyQt6 6.9 has no QTest.qWaitFor)."""
    import time
    t0 = time.monotonic()
    while not pred() and time.monotonic() - t0 < timeout_s:
        QTest.qWait(10)


def _buttons(page):
    return {b.text().replace("\n", " "): b for b in page.findChildren(QToolButton)}


def test_modify_group_builder_has_four_tools(main_window):
    from firepro3d.ribbon_bar import RibbonPage
    page = RibbonPage()
    main_window.build_modify_group(page, main_window._active_scene)
    names = set(_buttons(page))
    assert {"Move", "Rotate", "Offset", "Array"} <= names


def test_edit_group_buttons_route_to_their_entry_points(main_window, monkeypatch):
    from firepro3d.ribbon_bar import RibbonPage

    class _Ctl:
        def __init__(self): self.calls = []
        def start(self, tool): self.calls.append(tool); return True

    class _FakeScene:
        def __init__(self): self._modify_ctl = _Ctl()

    fake = _FakeScene()
    # Delete routes through MainWindow's one Delete chokepoint (text-edit
    # guard, empty-canvas refusal — view-3d.md I5), not the scene_getter.
    monkeypatch.setattr(main_window, "_delete_if_not_editing",
                        lambda: fake._modify_ctl.calls.append("delete"))
    page = RibbonPage()
    main_window.build_edit_group(page, lambda: fake)
    b = _buttons(page)
    for label, tool in (("Copy", "copy"), ("Cut", "cut"), ("Paste", "paste"),
                        ("Duplicate", "duplicate"), ("Delete", "delete")):
        b[label].click()
    assert fake._modify_ctl.calls == ["copy", "cut", "paste", "duplicate", "delete"]  # [RED]


def test_tooltips_show_shift_keys(main_window):
    from firepro3d.ribbon_bar import RibbonPage
    page = RibbonPage()
    main_window.build_modify_group(page, main_window._active_scene)
    main_window.build_edit_group(page, main_window._active_scene)
    b = _buttons(page)
    for label, key in (("Move", "Shift+M"), ("Rotate", "Shift+R"),
                       ("Flip", "Shift+F"), ("Mirror", "Shift+I"),
                       ("Offset", "Shift+O"), ("Array", "Shift+A"),
                       ("Copy", "Shift+C"), ("Cut", "Shift+X"),
                       ("Paste", "Shift+V"), ("Duplicate", "Shift+D")):
        assert key in b[label].toolTip(), label
    assert b["Delete"].toolTip()


def _group_title(b):
    from firepro3d.ribbon_bar import RibbonGroup, _VLabel
    w = b
    while w is not None and not isinstance(w, RibbonGroup):
        w = w.parentWidget()
    assert w is not None, "button not inside a RibbonGroup"
    return w.findChild(_VLabel).text()


def test_block_editor_page_edit_modify_end_to_end(main_window, qapp):
    """Real path: open the Block Editor; its page carries Edit + Modify; the
    selection-needing buttons follow the editor scene's selection; clicking
    Move with a selected line enters "move" on the EDITOR scene (not plan)."""
    from firepro3d.geometry_2d import LineItem
    main_window.scene.clearSelection()
    main_window._open_block_editor()
    qapp.processEvents()
    ed = main_window._active_editor_widget()
    try:
        assert ed is not None
        btns = main_window._be_modify_buttons
        edit = {"Copy", "Cut", "Paste", "Duplicate", "Delete"}
        modify = {"Move", "Rotate", "Scale", "Flip", "Mirror", "Offset", "Array", "Explode"}
        assert set(btns) == edit | modify
        for label, b in btns.items():
            assert _group_title(b) == ("EDIT" if label in edit else "MODIFY"), label
            assert b.toolTip(), label
            assert not b.icon().isNull(), label

        editor = main_window._active_scene()
        assert editor is ed.editor_scene and editor is not main_window.scene
        editor.clearSelection()
        qapp.processEvents()
        for label in ("Copy", "Cut", "Duplicate", "Delete", "Move", "Rotate",
                      "Scale", "Flip", "Mirror", "Array"):
            assert not btns[label].isEnabled(), label
        # Paste follows the clipboard payload (D5 / I1), refreshed on change.
        from PyQt6.QtWidgets import QApplication
        # Windows delivers the clipboard's dataChanged asynchronously: poll.
        QApplication.clipboard().setText("")
        _wait_until(lambda: not btns["Paste"].isEnabled())
        assert not btns["Paste"].isEnabled()
        QApplication.clipboard().setText(json.dumps(
            {"fp3d_clipboard": 1, "base": [0, 0], "scene_role": "block_editor",
             "items": [LineItem(QPointF(0, 0), QPointF(1, 0)).to_dict()]}))
        _wait_until(lambda: btns["Paste"].isEnabled())
        assert btns["Paste"].isEnabled()
        assert btns["Offset"].isEnabled()

        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        editor.addItem(line)
        line.setSelected(True)
        qapp.processEvents()
        assert btns["Move"].isEnabled()             # [RED]
        btns["Move"].click()
        assert editor.mode == "move"
        assert main_window.scene.mode != "move"
        editor.set_mode(None)
    finally:
        if ed is not None:
            ed._modified = False
            main_window.block_editor_manager.close(ed)
            qapp.processEvents()


def _open_editor_with_line(main_window, qapp):
    from firepro3d.geometry_2d import LineItem
    main_window.scene.clearSelection()
    main_window._open_block_editor()
    qapp.processEvents()
    ed = main_window._active_editor_widget()
    assert ed is not None
    editor = ed.editor_scene
    line = LineItem(QPointF(0, 0), QPointF(100, 0))
    editor.addItem(line); editor._draw_lines.append(line)
    line.setSelected(True)
    qapp.processEvents()
    return ed, editor, line


def _close_editor(main_window, ed, qapp):
    if ed is not None:
        ed._modified = False
        main_window.block_editor_manager.close(ed)
        qapp.processEvents()


def test_copy_click_enters_copy_base_on_the_editor_scene(main_window, qapp):
    """I-4(c): real editor scene — Copy click enters copy_base THERE."""
    ed = None
    try:
        ed, editor, line = _open_editor_with_line(main_window, qapp)
        btns = main_window._be_modify_buttons
        btns["Copy"].click()
        assert editor.mode == "copy_base"
        assert main_window.scene.mode != "copy_base"
        assert line.isSelected()
        editor.set_mode(None)
    finally:
        _close_editor(main_window, ed, qapp)


def test_modal_buttons_light_with_their_mode_and_clear_on_exit(main_window, qapp):
    """I-3 (spec I1): modal Edit/Modify buttons are in _block_mode_buttons —
    lit while their tool runs, cleared on exit; Delete stays plain, Cut lights
    its own button (DD10)."""
    ed = None
    try:
        ed, editor, line = _open_editor_with_line(main_window, qapp)
        btns = main_window._be_modify_buttons
        reg = main_window._block_mode_buttons
        for label, modes in (("Copy", ("copy_base",)),
                             ("Cut", (ModifyToolsController.CUT_BUTTON_KEY,)),
                             ("Paste", ("paste",)),
                             ("Duplicate", ("duplicate",)), ("Move", ("move",)),
                             ("Rotate", ("rotate",)),
                             ("Offset", ("offset", "offset_side")),
                             ("Array", ("array",))):
            assert btns[label].isCheckable(), label
            for m in modes:
                assert reg[m] is btns[label], (label, m)
        assert not btns["Delete"].isCheckable()

        btns["Move"].click()
        assert editor.mode == "move"
        assert btns["Move"].isChecked()                         # [RED]
        editor.set_mode(None)                                   # Esc / commit path
        assert not btns["Move"].isChecked()

        # Offset lights for both of its modes.
        editor._modify_ctl.start("offset")
        assert btns["Offset"].isChecked()
        editor.set_mode("offset_side")
        assert btns["Offset"].isChecked()
        editor.set_mode(None)
        assert not btns["Offset"].isChecked()
    finally:
        _close_editor(main_window, ed, qapp)


def test_clicking_the_lit_tool_button_cancels_it(main_window, qapp):
    ed = None
    try:
        ed, editor, line = _open_editor_with_line(main_window, qapp)
        b = main_window._be_modify_buttons["Duplicate"]
        b.click()
        assert editor.mode == "duplicate" and b.isChecked()
        b.click()                                               # un-toggle
        assert editor.mode in (None, "select")
        assert not b.isChecked()
    finally:
        _close_editor(main_window, ed, qapp)


def test_refused_start_leaves_the_button_unchecked(main_window, qapp):
    ed = None
    try:
        ed, editor, line = _open_editor_with_line(main_window, qapp)
        b = main_window._be_modify_buttons["Move"]
        editor.clearSelection()
        qapp.processEvents()
        b.setEnabled(True)                  # stale enable state: start() refuses
        b.click()
        assert editor.mode in (None, "select")
        assert not b.isChecked()
    finally:
        _close_editor(main_window, ed, qapp)


def _reading_order(btns, labels):
    """Labels sorted by on-screen position: column (left edge of the button's
    column widget), then top-to-bottom inside it — the ribbon's reading order."""
    from PyQt6.QtCore import QPoint

    def key(label):
        b = btns[label]
        win = b.window()
        return (b.parentWidget().mapTo(win, QPoint(0, 0)).x(),
                b.mapTo(win, QPoint(0, 0)).y())
    return sorted(labels, key=key)


MODIFY_ORDER = ["Move", "Rotate", "Scale", "Flip", "Mirror", "Offset", "Array", "Explode"]


def test_modify_group_reading_order(main_window, qapp):
    """DD11: Move · Rotate · Scale · Flip · Mirror · Offset · Array · Explode."""
    ed = None
    try:
        ed, editor, line = _open_editor_with_line(main_window, qapp)
        btns = main_window._be_modify_buttons
        assert _reading_order(btns, MODIFY_ORDER) == MODIFY_ORDER         # [RED]
    finally:
        _close_editor(main_window, ed, qapp)


def test_flip_mirror_buttons_tooltip_light_and_enter_their_modes(main_window, qapp):
    ed = None
    try:
        ed, editor, line = _open_editor_with_line(main_window, qapp)
        btns = main_window._be_modify_buttons
        reg = main_window._block_mode_buttons
        for label, key, mode in (("Scale", "Shift+S", "scale"),
                                 ("Flip", "Shift+F", "flip"),
                                 ("Mirror", "Shift+I", "mirror")):
            b = btns[label]
            assert key in b.toolTip(), label
            assert b.isCheckable() and reg[mode] is b
            assert not b.icon().isNull()
            assert b.isEnabled()
            b.click()
            assert editor.mode == mode and b.isChecked()                  # [RED]
            editor.set_mode(None)
            assert not b.isChecked()
            line.setSelected(True)
    finally:
        _close_editor(main_window, ed, qapp)


def test_cut_lights_its_own_button_and_untoggle_cancels(main_window, qapp):
    """DD10 / M8: during Cut the Cut button is lit and Copy is not; clicking
    the lit Cut cancels (nothing cut, no undo step); a committed Cut unlights
    it; Copy lights only Copy."""
    ed = None
    try:
        ed, editor, line = _open_editor_with_line(main_window, qapp)
        ignore_os_mouse(ed.view)
        editor.push_undo_state()            # baseline holds the line (undo target)
        line.setSelected(True)
        btns = main_window._be_modify_buttons
        p0 = editor._undo_pos
        btns["Cut"].click()
        assert editor.mode == "copy_base"
        assert btns["Cut"].isChecked()                              # [RED]
        assert not btns["Copy"].isChecked()
        btns["Cut"].click()                                         # un-toggle
        assert editor.mode in (None, "select")
        assert not btns["Cut"].isChecked()
        assert line.scene() is editor and editor._undo_pos == p0    # nothing cut
        # A real Cut commit: base click on the editor view removes the line.
        line.setSelected(True)
        btns["Cut"].click()
        assert btns["Cut"].isChecked()
        click(ed.view, QPointF(100, 0))
        assert line.scene() is None and editor._undo_pos == p0 + 1
        assert not btns["Cut"].isChecked() and not btns["Copy"].isChecked()
        editor.undo()
        line = editor._draw_lines[0]
        line.setSelected(True)
        btns["Copy"].click()
        assert btns["Copy"].isChecked() and not btns["Cut"].isChecked()
        editor.set_mode(None)
        assert not btns["Copy"].isChecked()
    finally:
        _close_editor(main_window, ed, qapp)


# Modes a scene emits through a literal ``set_mode`` outside the dispatch
# tables: thermal radiation (main.py) and the Annotate/Block-Editor Dimension
# button. (``wall_rect`` / ``floor_rect`` fold into wall / floor before
# ``modeChanged``; ``pan`` / ``pick_point`` are the underlay preview view's own
# modes, not a Model_Space's.)
_LITERAL_MODES = ("radiation_emitter", "radiation_receiver", "dimension")


def _dispatched_modes():
    """Every mode a scene enters through the dispatch / tool registries."""
    from firepro3d.model_space import Model_Space
    mtc = ModifyToolsController
    modes = (set(Model_Space._PRESS_DISPATCH) | set(Model_Space._MOVE_DISPATCH)
             | set(Model_Space._PREVIEW_DISPATCH) | set(mtc._TOOL_MODE.values())
             | set(_LITERAL_MODES))
    for extra in mtc._TOOL_EXTRA_MODES.values():
        modes |= set(extra)
    return sorted("" if m is None else m for m in modes)


def test_badge_has_a_friendly_label_for_every_dispatched_mode(main_window, qapp):
    """DD10 / M8: a real modeChanged emission for every dispatched mode puts
    that mode's friendly tool name on the footer badge."""
    sc = main_window.scene
    badge = main_window.footer.mode_badge
    try:
        missing = []
        for m in _dispatched_modes():
            sc.modeChanged.emit(m)
            label = MainWindow._MODE_LABELS.get(m)
            if label is None:
                missing.append(m)
                continue
            assert badge.text() == label.upper(), m
        assert missing == []                                          # [RED]
        for m, shown in (("copy_base", "COPY"), ("offset_side", "OFFSET"),
                         ("draw_line", "LINE"), ("gridline_array", "ARRAY GRIDLINES"),
                         ("flip", "FLIP"), ("mirror", "MIRROR"), ("scale", "SCALE"),
                         ("array", "ARRAY"), ("", "SELECT")):
            sc.modeChanged.emit(m)
            assert badge.text() == shown, m
    finally:
        sc.modeChanged.emit(sc.mode or "")


def test_badge_reads_the_tool_name_for_real_tool_runs(main_window, qapp):
    """M8: real tool runs on the editor scene — Cut reads CUT (not COPY BASE),
    Copy COPY, Offset OFFSET in both of its modes, Array ARRAY, Scale / Flip /
    Mirror their own names."""
    ed = None
    try:
        ed, editor, line = _open_editor_with_line(main_window, qapp)
        btns = main_window._be_modify_buttons
        badge = main_window.footer.mode_badge
        btns["Cut"].click()
        assert badge.text() == "CUT"                                  # [RED]
        editor.set_mode(None)
        assert badge.text() == "SELECT"
        line.setSelected(True)
        btns["Copy"].click()
        assert badge.text() == "COPY"
        editor.set_mode(None)
        editor._modify_ctl.start("offset")
        assert badge.text() == "OFFSET"
        editor.set_mode("offset_side")
        assert badge.text() == "OFFSET"
        editor.set_mode(None)
        for tool, shown in (("array", "ARRAY"), ("scale", "SCALE"),
                            ("flip", "FLIP"), ("mirror", "MIRROR")):
            line.setSelected(True)
            assert editor._modify_ctl.start(tool), tool
            assert badge.text() == shown, tool
            editor.set_mode(None)
    finally:
        _close_editor(main_window, ed, qapp)


def test_flip_mirror_scale_buttons_carry_their_approved_icons(main_window, qapp):
    """DD11: the Modify buttons show the approved art. Ground truth is the
    authored SVG rendered through the real loader, compared pixel-for-pixel
    with what the live button holds."""
    from PyQt6.QtCore import QSize
    from firepro3d import icons, theme as th
    ed = None
    try:
        main_window.scene.clearSelection()
        main_window._open_block_editor()
        qapp.processEvents()
        ed = main_window._active_editor_widget()
        btns = main_window._be_modify_buttons
        variant = icons.DARK if th.detect().name == icons.DARK else icons.LIGHT
        sz = QSize(th.M.RIBBON_SMALL_ICON, th.M.RIBBON_SMALL_ICON)
        images = {}
        for label, fn in (("Scale", "scale_icon.svg"), ("Flip", "flip_icon.svg"),
                          ("Mirror", "mirror_icon.svg")):
            got = btns[label].icon().pixmap(sz).toImage()
            want = icons.themed_icon(fn, variant).pixmap(sz).toImage()
            assert got == want, label                                    # [RED]
            assert btns[label].toolTip(), label                          # tooltip present
            images[label] = got
        # the three glyphs are distinguishable (content, not shape — VC2)
        assert images["Flip"] != images["Mirror"] != images["Scale"] != images["Flip"]
    finally:
        _close_editor(main_window, ed, qapp)
