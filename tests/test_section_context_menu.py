"""Elevation parity D6 / AC8: the section right-click menu is the plan's."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from tests._hosted_blocks_helpers import defn, gridline
from tests._mainwindow_helpers import dispose_main_window
from tests._section_window_helpers import (action, aim, open_section_window,
                                           right_click, settle, texts)
from tests.test_section_hide import _line_of
from tests.test_section_pipe_symbols import _pipe


def test_pipe_menu_has_every_plan_entry_and_hide_all_is_global(qapp, monkeypatch):
    """AC8 / R10: right-click a pipe in a section -> every entry plan's menu
    offers for that pipe, plus Fit All; Hide All (Pipe) hides every model pipe;
    Properties shows the model pipe."""
    win, _m, views = open_section_window(1)
    ms = win.scene
    try:
        pipe = _pipe(ms, (2000.0, -1000.0, 2400.0), (6000.0, -1000.0, 2400.0))
        other = _pipe(ms, (2000.0, -1000.0, 1200.0), (6000.0, -1000.0, 1200.0))
        sec = views[0].scene()
        settle(sec)
        plan_texts = texts(ms._build_entity_context_menu(pipe))      # plan's own builder
        line = _line_of(sec, pipe)
        pt = line.mapToScene(line.line().pointAt(0.25))
        aim(views[0], pt)
        menu = right_click(views[0], pt, monkeypatch)
        got = texts(menu)
        assert set(plan_texts) <= set(got), (plan_texts, got)
        assert "Hide All (Pipe)" in got and "Fit All" in got
        win.prop_manager.show_properties(None)      # the right-click selection already fed it
        action(menu, "Properties").trigger()
        assert win.prop_manager._targets == [pipe]
        menu = right_click(views[0], pt, monkeypatch)
        action(menu, "Hide All (Pipe)").trigger()
        assert pipe._display_overrides.get("visible") is False
        assert other._display_overrides.get("visible") is False
        assert not _line_of(sec, other).isVisible()
    finally:
        dispose_main_window(win)


def test_edit_block_on_a_hosted_copy_opens_its_definition(qapp, monkeypatch):
    """D6: Edit Block on a gridline-hosted copy opens the block's editor tab."""
    win, _m, views = open_section_window(1)
    ms = win.scene
    try:
        sec = views[0].scene()
        gridline(ms, (0, -3000), (6000, -3000), "Q")
        settle(sec)
        d = defn(ms, "EditMe")
        inst = sec.place_hosted_block(d.id, QPointF(2500.0, -1200.0))
        settle(sec)
        cp = sec._hosted_copies[id(inst)]
        pt = QPointF(*cp.block_pos())
        aim(views[0], pt)
        action(right_click(views[0], pt, monkeypatch), "Edit Block").trigger()
        QApplication.processEvents()
        assert any(getattr(w, "_edit_block_id", None) == d.id
                   for w in win.block_editor_manager.open_editors())
    finally:
        dispose_main_window(win)


def test_copy_starts_the_sections_own_base_pick(qapp, monkeypatch):
    """D6: Copy / Cut drive the section's modify controller (area C), never plan's."""
    win, _m, views = open_section_window(1)
    ms = win.scene
    try:
        sec = views[0].scene()
        gridline(ms, (0, -3000), (6000, -3000), "Q")
        settle(sec)
        inst = sec.place_hosted_block(defn(ms, "CopyMe").id, QPointF(2500.0, -1200.0))
        settle(sec)
        pt = QPointF(*sec._hosted_copies[id(inst)].block_pos())
        aim(views[0], pt)
        action(right_click(views[0], pt, monkeypatch), "Copy").trigger()
        assert sec.mode == "copy_base"
        assert ms.mode in (None, "select")
    finally:
        dispose_main_window(win)


def test_empty_canvas_menu_builds_without_a_target(qapp, monkeypatch):
    """AC8: right-click on empty canvas, nothing selected -> a menu, no crash;
    target-only entries absent."""
    win, _m, views = open_section_window(1)
    try:
        sec = views[0].scene()
        settle(sec)
        empty = QPointF(3000.0, -20000.0)
        aim(views[0], empty)
        got = texts(right_click(views[0], empty, monkeypatch))
        assert "Show All Hidden" in got and "Fit All" in got
        assert not any(t.startswith("Hide All") for t in got)
        assert "Properties" not in got and "Edit Block" not in got
    finally:
        dispose_main_window(win)
