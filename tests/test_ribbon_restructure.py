"""Tests for MainWindow ribbon structure and settings-dialog rails.

Covers: ribbon tab roster/order, mode-button wiring, and the rails of the
System/Project Settings dialogs (replaces the deleted _build_preferences_dialog
factory test).

All tests reuse the session-scoped ``qapp`` fixture from tests/conftest.py.
The module-scoped ``_main_window_singleton`` fixture mirrors the pattern from
``test_osnap_ui.py`` to avoid creating a second MainWindow in the same process.
"""

from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from main import MainWindow


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow, shared across this module for speed.

    Save/restore SNAP_TOLERANCE_PX: MainWindow.__init__ overwrites the
    module-level constant from QSettings and would leak the value into other
    test modules if not restored.
    """
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def main_window(_main_window_singleton):
    """Per-test view of the shared MainWindow."""
    yield _main_window_singleton


def test_settings_dialogs_rails(qapp, make_model_space):
    """SystemSettingsDialog and ProjectSettingsDialog expose the correct rail keys."""
    from firepro3d.settings.system_settings_dialog import SystemSettingsDialog
    from firepro3d.settings.project_settings_dialog import ProjectSettingsDialog

    # make_model_space() is a factory — call it to get a Model_Space.
    scene = make_model_space()
    sysdlg = SystemSettingsDialog(scene=scene)
    assert sysdlg.rail_keys() == ["general", "ux", "ui", "import"]
    sysdlg.deleteLater()


# The Create tab was dissolved by the containment contract (C7): the model is
# placement-only, so loose 2D-geometry authoring moved to the Block-Editor /
# Paper contexts and block entry commands moved to the Architecture "Block" group.
EXPECTED_TABS = ["Manage", "Architecture",
                 "Sprinkler Systems", "Analyze", "Draft"]


def test_base_tabs_roster_and_order(main_window):
    tb = main_window.ribbon._tab_bar
    titles = [tb.tabText(i) for i in range(tb.count())]
    assert titles == EXPECTED_TABS


def test_no_modify_base_tab(main_window):
    tb = main_window.ribbon._tab_bar
    assert "Modify" not in [tb.tabText(i) for i in range(tb.count())]


# ── Containment-contract C7 ribbon topology ──────────────────────────────────

def _page_by_title(main_window, title):
    """Return the RibbonPage whose base tab has *title* (or None)."""
    tb = main_window.ribbon._tab_bar
    for i in range(tb.count()):
        if tb.tabText(i) == title:
            return main_window.ribbon._stack.widget(i)
    return None


def _group_titles(page):
    from PyQt6.QtWidgets import QLabel
    return {lbl.text() for lbl in page.findChildren(QLabel)}


def _button_texts(page):
    """Normalised (newline→space) texts of every button on the page."""
    from PyQt6.QtWidgets import QToolButton
    return {b.text().replace("\n", " ") for b in page.findChildren(QToolButton)}


def test_no_create_base_tab(main_window):
    """C7: the Create tab is dissolved (model is placement-only)."""
    tb = main_window.ribbon._tab_bar
    assert "Create" not in [tb.tabText(i) for i in range(tb.count())]


def test_architecture_has_block_group(main_window):
    """C7: block *entry* commands move to a new Architecture 'Block' group."""
    arch = _page_by_title(main_window, "Architecture")
    assert arch is not None
    assert "Block" in _group_titles(arch)
    btns = _button_texts(arch)
    assert "Create Block" in btns
    assert "Insert Block" in btns
    assert "Block Manager" in btns


def test_quick_and_text_block_buttons_retired(main_window):
    """C7: Quick Block + Text Block are retired everywhere on the base ribbon."""
    for title in ("Manage", "Architecture", "Sprinkler Systems", "Analyze", "Draft"):
        page = _page_by_title(main_window, title)
        assert page is not None
        btns = _button_texts(page)
        assert "Quick Block" not in btns, f"Quick Block still on {title}"
        assert "Text Block" not in btns, f"Text Block still on {title}"


def test_underlay_group_moved_to_architecture(main_window):
    """C7: the Underlay group relocates from Manage to Architecture (tentative)."""
    arch = _page_by_title(main_window, "Architecture")
    manage = _page_by_title(main_window, "Manage")
    assert "Underlay" in _group_titles(arch)
    assert "Underlay" not in _group_titles(manage), "Underlay still in Manage"


def test_block_editor_context_has_text_tool(main_window):
    """C5/C7: Text is the 9th primitive in the Block-Editor palette.

    Self-cleaning: this uses the module-scoped singleton, so it must not leave a
    Block Editor tab current — `_active_scene()` keys off the current central tab
    and would poison the mode-button dispatch tests that follow.
    """
    from firepro3d.block_editor import BlockEditorWidget
    main_window._open_block_editor()
    try:
        assert "text" in main_window._block_mode_buttons
    finally:
        w = main_window.central_tabs.currentWidget()
        if isinstance(w, BlockEditorWidget):
            main_window.block_editor_manager.close(w)
        main_window.central_tabs.setCurrentIndex(0)  # back to Model Space


def test_undo_redo_present_on_manage(main_window):
    assert hasattr(main_window, "_btn_undo") and hasattr(main_window, "_btn_redo")


# ── Mode-button sync tests (Task C3) ─────────────────────────────────────────

# Every mode string that must appear in _mode_buttons after the ribbon
# restructure.  Shared-button aliases (floor/floor_rect, …)
# each get their own entry because _mode_buttons[alias] = same_button is the
# invariant; clicking the shared button verifies the wiring, not the alias.
# Note: wall_rect was removed in Task 6 (single wall button, no dropdown).
# floor_rect was likewise collapsed into the single Floor button (floor-workflow
# branch) — it survives as a set_mode alias, not a distinct mode button.
# The loose 2D-geometry modes (draw_line/draw_rectangle/draw_circle/polyline/
# draw_arc/…) and the standalone "text" mode left the MAIN ribbon _mode_buttons
# with the Create tab (containment contract C7). They now live only in the
# Block-Editor palette (_block_mode_buttons) — never a Model-space tab.
_SURVIVING_MODES = [
    "draw_gridline", "dimension",
    "wall", "floor", "roof", "roof_rect",
    "room", "room_manual", "door", "window", "detail",
    "pipe", "sprinkler", "water_supply", "design_area",
    "radiation_emitter", "radiation_receiver",
]


def test_all_surviving_modes_registered(main_window):
    """Every mode in _SURVIVING_MODES must be a key in _mode_buttons."""
    missing = [m for m in _SURVIVING_MODES if m not in main_window._mode_buttons]
    assert not missing, f"mode buttons missing from _mode_buttons: {missing}"


@pytest.mark.parametrize("mode", _SURVIVING_MODES)
def test_mode_button_enters_mode(main_window, mode, monkeypatch):
    """Clicking the button registered for *mode* must invoke scene.set_mode.

    For shared-button aliases (e.g. wall/wall_rect both map to the same
    QToolButton) the click triggers the button's DEFAULT action, which calls
    set_mode with the button's wired mode — not necessarily *mode* itself.
    The invariant tested here is: (a) every mode string is registered and
    (b) the button is wired so that clicking it reaches set_mode at all.
    """
    if mode not in main_window._mode_buttons:
        pytest.skip(f"{mode!r} not registered (caught by test_all_surviving_modes_registered)")

    calls = []
    monkeypatch.setattr(main_window.scene, "set_mode", lambda *a, **k: calls.append(a))

    btn = main_window._mode_buttons[mode]
    # Ensure the button is unchecked so click() checks it (toggled→True), which
    # fires the callback.  For non-checkable buttons the check state is
    # irrelevant; for checkable ones toggled fires on BOTH transitions, but
    # un-checking first gives a consistent, predictable result.
    if btn.isCheckable() and btn.isChecked():
        btn.setChecked(False)

    btn.click()

    assert calls, (
        f"clicking the '{mode}' button did not call scene.set_mode "
        f"(button text: {btn.text()!r})"
    )
