"""Draft-tab ribbon: Add Text mode button, Font group context, Refresh/Fit."""
from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

from firepro3d.paper_space import PaperSpaceWidget, TextAnnotationData

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import, required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from main import MainWindow


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow, shared across this module for speed."""
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
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
    """Per-test view of the shared MainWindow with add-text mode reset to off."""
    win = _main_window_singleton
    # Ensure add-text mode is off and no selection before each test
    if win.paper_space_widget.view._add_text_mode:
        win.paper_space_widget.set_add_text_mode(False)
    win.paper_space_widget.paper_scene.clearSelection()
    yield win
    # Teardown: leave add-text mode off and clear selection
    if win.paper_space_widget.view._add_text_mode:
        win.paper_space_widget.set_add_text_mode(False)
    win.paper_space_widget.paper_scene.clearSelection()


def test_add_text_button_registered(main_window):
    win = main_window
    assert win._add_text_ribbon_btn is not None
    assert win._add_text_ribbon_btn.isCheckable()


def test_add_text_click_switches_to_paper_tab(main_window):
    win = main_window
    # Make sure we're NOT on the paper tab first
    win.central_tabs.setCurrentIndex(0)
    assert not isinstance(win.central_tabs.currentWidget(), PaperSpaceWidget)

    win._add_text_ribbon_btn.setChecked(True)   # toggled fires the handler
    assert isinstance(win.central_tabs.currentWidget(), PaperSpaceWidget)
    assert win.paper_space_widget.view._add_text_mode is True

    win._add_text_ribbon_btn.setChecked(False)
    assert win.paper_space_widget.view._add_text_mode is False


def test_mode_exit_unchecks_ribbon_button(main_window):
    win = main_window
    win._add_text_ribbon_btn.setChecked(True)
    assert win._add_text_ribbon_btn.isChecked() is True
    win.paper_space_widget.set_add_text_mode(False)
    assert win._add_text_ribbon_btn.isChecked() is False


def test_escape_cancels_add_text_mode(main_window):
    from PyQt6.QtCore import Qt, QEvent
    from PyQt6.QtGui import QKeyEvent
    win = main_window
    win._add_text_ribbon_btn.setChecked(True)
    assert win.paper_space_widget.view._add_text_mode is True

    view = win.paper_space_widget.view
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                   Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(ev)
    assert view._add_text_mode is False
    assert win._add_text_ribbon_btn.isChecked() is False


def test_leaving_paper_tab_cancels_add_text_and_disables_font_group(main_window):
    win = main_window
    # First enter add-text mode on the paper tab
    win._activate_paper_sheet("Layout 1")
    win._add_text_ribbon_btn.setChecked(True)
    assert win.paper_space_widget.view._add_text_mode is True

    # Switch to model space (index 0)
    win.central_tabs.setCurrentIndex(0)
    assert win.paper_space_widget.view._add_text_mode is False
    assert win.font_group.container.isEnabled() is False


def test_font_group_disabled_on_model_tab(main_window):
    win = main_window
    win.central_tabs.setCurrentIndex(0)
    win._update_font_group_context()
    assert win.font_group.container.isEnabled() is False


def test_font_group_enabled_with_text_selected(main_window):
    win = main_window
    win._activate_paper_sheet("Layout 1")
    scene = win.paper_space_widget.paper_scene
    d = TextAnnotationData(text="hello")
    item = scene.add_annotation(d)
    item.setSelected(True)
    # selectionChanged should have fired _update_font_group_context
    assert win.font_group.container.isEnabled() is True

    item.setSelected(False)
    assert win.font_group.container.isEnabled() is False

    # Cleanup
    scene.remove_annotation(item)


def test_font_group_targets_template_in_add_text_mode(main_window):
    win = main_window
    # Reset template bold to a known baseline
    win.current_text_template.data.bold = False

    win._add_text_ribbon_btn.setChecked(True)
    assert win.font_group.container.isEnabled() is True

    win.font_group._commit("Bold", True)
    assert win.current_text_template.data.bold is True

    win._add_text_ribbon_btn.setChecked(False)
    # Reset
    win.current_text_template.data.bold = False


def test_refresh_and_fit_public_api_no_crash(main_window):
    """Ribbon Refresh/Fit buttons are wired to these public methods; confirm they do not raise."""
    win = main_window
    win.paper_space_widget.refresh_viewport()   # must not raise
    win.paper_space_widget.fit_sheet()          # must not raise
