"""Tests for Task C1: contextual-tab registry + shared Edit group builder.

Reuses the module-scoped ``_main_window_singleton`` pattern from
``test_ribbon_restructure.py`` so the expensive MainWindow construction
happens once per test-module run.
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


def test_registry_has_expected_keys(main_window):
    keys = set(main_window._contextual_registry.keys())
    assert {"geo2d", "wall", "pipe", "sprinkler", "annotation",
            "gridline", "mixed"} <= keys


def test_contextual_index_after_base_tabs(main_window):
    # 7 base tabs → contextual insert slot is 7
    assert main_window._contextual_index == 7


def test_edit_group_builder_adds_group(main_window, qapp):
    from firepro3d.ribbon_bar import RibbonPage
    page = RibbonPage()
    main_window._build_contextual_edit_group(page)
    assert page._layout.count() >= 2  # at least one group + the trailing stretch


def test_registry_has_all_18_keys(main_window):
    """Registry must contain every entry in _CONTEXTUAL_TABS."""
    expected = set(MainWindow._CONTEXTUAL_TABS.keys())
    assert set(main_window._contextual_registry.keys()) == expected


def test_registry_titles_match(main_window):
    """Each registry value's tab title must match the _CONTEXTUAL_TABS map."""
    for key, (title, _builder) in main_window._contextual_registry.items():
        assert title == MainWindow._CONTEXTUAL_TABS[key], (
            f"Title mismatch for key {key!r}: got {title!r}, "
            f"expected {MainWindow._CONTEXTUAL_TABS[key]!r}"
        )


def test_registry_builder_is_shared_edit_group(main_window):
    """Every registry entry's builder must be _build_contextual_edit_group."""
    for key, (_title, builder) in main_window._contextual_registry.items():
        assert builder == main_window._build_contextual_edit_group, (
            f"Builder for key {key!r} is not _build_contextual_edit_group"
        )


def test_active_contextual_key_initially_none(main_window):
    """_active_contextual_key must start as None (no contextual tab shown)."""
    assert main_window._active_contextual_key is None


def test_pre_contextual_tab_initially_zero(main_window):
    """_pre_contextual_tab must start as 0."""
    assert main_window._pre_contextual_tab == 0


def test_edit_group_has_five_buttons(main_window, qapp):
    """The Edit group built by _build_contextual_edit_group must have 5 buttons."""
    from firepro3d.ribbon_bar import RibbonPage, RibbonButton, RibbonSmallButton
    from PyQt6.QtWidgets import QToolButton
    page = RibbonPage()
    main_window._build_contextual_edit_group(page)
    # Count all QToolButton descendants (RibbonButton and RibbonSmallButton both inherit)
    buttons = page.findChildren(QToolButton)
    assert len(buttons) == 5, f"Expected 5 buttons, got {len(buttons)}"
