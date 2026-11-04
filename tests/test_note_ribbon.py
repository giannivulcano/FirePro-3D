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
    assert "note" in main_window._MODE_INSTRUCTIONS


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
