"""Task 9: Architecture > Annotations group, and Note gated by canvas kind (D1, D11)."""
import os

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QIcon
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel

import main as _main_module
from firepro3d import icons
from firepro3d.assets import asset_path
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from firepro3d.model_space import NOTE_OFF_HINT
from firepro3d.ribbon_bar import RibbonGroup
from main import MainWindow
from tests._mainwindow_helpers import dispose_main_window


@pytest.fixture(scope="module")
def main_window(qapp):
    saved = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    dispose_main_window(win)
    snap_engine.SNAP_TOLERANCE_PX = saved


def _arch_group_titles(win):
    tb = win.ribbon._tab_bar
    page = next(win.ribbon._stack.widget(i) for i in range(tb.count())
                if tb.tabText(i) == "Architecture")
    lay = page._layout                        # RibbonPage keeps no group list: walk the layout
    out = []
    for i in range(lay.count()):
        w = lay.itemAt(i).widget()
        if isinstance(w, RibbonGroup):
            out.append(w.findChild(QLabel).text().upper())
    return out


def test_annotations_group_sits_between_datums_and_underlay(main_window):
    t = _arch_group_titles(main_window)
    assert t.index("DATUMS") + 1 == t.index("ANNOTATIONS") == t.index("UNDERLAY") - 1


def test_unbuilt_buttons_are_disabled_with_a_tooltip(main_window):
    for b in (main_window._ann_dimension_btn, main_window._ann_keyed_btn):
        assert not b.isEnabled() and "coming soon" in b.toolTip().lower()


def test_note_follows_the_canvas_kind(main_window):
    btn = main_window._mode_buttons["note"]
    live = btn.toolTip()
    main_window._set_canvas_context("plan")
    assert btn.isEnabled()
    for kind in ("section", "paper", "3d", "block", "schematic"):
        main_window._set_canvas_context(kind)
        assert not btn.isEnabled()
        assert btn.toolTip() == NOTE_OFF_HINT          # names where Note works, not "open a block"
    main_window._set_canvas_context("detail")
    assert btn.isEnabled() and btn.toolTip() == live
    main_window._set_canvas_context("plan")


def _build_note(win):
    """The Build tab's Note button, found by its place on the page."""
    from tests.test_block_editor_ribbon_tab import _buttons, _group, _page
    buttons = _buttons(_group(_page(win, "Build"), "2D Geometry"))
    assert list(buttons).index("Note") == list(buttons).index("Text") + 1     # beside Text
    return buttons["Note"]


def test_build_note_is_live_on_a_schematic_tab_and_off_on_a_block_tab(main_window, qapp):
    win = main_window
    btn = _build_note(win)
    win._set_canvas_context("plan")
    assert not btn.isEnabled()
    block = win.block_editor_manager.open_new()
    qapp.processEvents()
    try:
        assert not btn.isEnabled()
        assert btn.toolTip() == win._BE_NOTE_BLOCK_TIP
    finally:
        win.block_editor_manager.close(block)
        qapp.processEvents()
    sch = win.block_editor_manager.open_new(kind="schematic")
    qapp.processEvents()
    try:
        assert btn.isEnabled() and "arrow tip" in btn.toolTip()
        assert not win._mode_buttons["note"].isEnabled()    # Architecture stays plan and detail
    finally:
        win.block_editor_manager.close(sch)
        qapp.processEvents()


def test_the_build_button_runs_a_note_on_the_real_schematic_tab(
        main_window, qapp, real_system_library):
    """Ribbon button -> mode -> press handler -> editor, in the real window."""
    from PyQt6.QtCore import Qt

    from firepro3d.text_item import editing_text_item
    from tests._note_helpers import click
    win = main_window
    sch = win.block_editor_manager.open_new(kind="schematic")
    qapp.processEvents()
    scene = sch.editor_scene
    try:
        hints = []
        scene.instructionChanged.connect(hints.append)
        btn = _build_note(win)
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert scene.mode == "note" and btn.isChecked()
        assert hints[-1] == "Pick arrow tip"
        assert win.prop_manager._targets == [scene._note_ctl.template]
        assert "Leader End" in win.prop_manager._prop_widgets
        vr = sch.view.viewport().rect()
        pts = [sch.view.mapToScene(int(vr.width() * x), int(vr.height() * y))
               for x, y in ((.2, .2), (.4, .4), (.6, .45))]
        for p in pts:
            click(sch.view, p)
        item = scene._texts[-1]
        assert editing_text_item(scene) is item and item.data.leader["edge"] == "L"
        assert scene.mode != "note" and not btn.isChecked()
        item.setPlainText("Hold")
        scene._text_edit_ctl.commit()
    finally:
        win.block_editor_manager.close(sch)
        qapp.processEvents()


def test_activating_the_note_block_on_a_schematic_tab_arms_the_tool(
        main_window, qapp, real_system_library):
    from firepro3d.system_blocks import NOTE_BLOCK_ID
    win = main_window
    sch = win.block_editor_manager.open_new(kind="schematic")
    qapp.processEvents()
    try:
        win._on_block_activated(NOTE_BLOCK_ID)
        assert sch.editor_scene.mode == "note"
        sch.editor_scene.set_mode(None)
    finally:
        win.block_editor_manager.close(sch)
        qapp.processEvents()


def test_note_button_arms_the_note_tool_on_the_plan_scene(main_window):
    main_window._set_canvas_context("plan")
    main_window.scene.active_view_key = "plan:Plan: Level 1"
    main_window._mode_buttons["note"].click()
    try:
        assert main_window.scene.mode == "note"
    finally:
        main_window.scene.set_mode("select")


def test_note_mode_has_a_footer_label_and_instruction(main_window):
    assert main_window._MODE_LABELS["note"] == "Note"
    assert "elbow" in main_window._MODE_INSTRUCTIONS["note"]


@pytest.mark.parametrize("name", ["note_icon.svg", "keyed_note_icon.svg"])
def test_new_icons_are_two_token_and_render_in_both_themes(qapp, caplog, name):
    import re
    raw = open(asset_path("Ribbon", name), encoding="utf-8").read()
    assert 'viewBox="0 0 48 48"' in raw
    for h in re.findall(r"#[0-9a-fA-F]{6,8}\b", raw):
        assert h.upper() in ("#1A1A1A", "#004CFF"), f"{name}: {h}"
    icons._cache.clear()
    for theme in (icons.LIGHT, icons.DARK):
        with caplog.at_level("WARNING", logger="firepro3d.icons"):
            caplog.clear()
            ic = icons.themed_icon(name, theme)
        assert isinstance(ic, QIcon) and not ic.isNull()
        assert "not found" not in caplog.text
