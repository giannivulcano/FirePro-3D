"""Tests for Task D6: MainWindow._build_preferences_dialog / _open_preferences.

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


def test_open_preferences_has_six_tabs(main_window):
    """_build_preferences_dialog() returns a dialog with exactly 6 tabs.

    The sixth tab is the UI pane (System/Light/Dark theme selector) added on
    the design-token branch.
    """
    dlg = main_window._build_preferences_dialog()
    assert dlg._tabs.count() == 6
    titles = [dlg._tabs.tabText(i) for i in range(dlg._tabs.count())]
    assert "UI" in titles
    dlg.deleteLater()


EXPECTED_TABS = ["Manage", "Create", "Architecture",
                 "Sprinkler Systems", "Analyze", "Draft"]


def test_base_tabs_roster_and_order(main_window):
    tb = main_window.ribbon._tab_bar
    titles = [tb.tabText(i) for i in range(tb.count())]
    assert titles == EXPECTED_TABS


def test_no_modify_base_tab(main_window):
    tb = main_window.ribbon._tab_bar
    assert "Modify" not in [tb.tabText(i) for i in range(tb.count())]


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
_SURVIVING_MODES = [
    "draw_line", "draw_rectangle", "draw_circle", "polyline", "draw_arc",
    "draw_gridline", "dimension", "text",
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
