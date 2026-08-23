"""Tests for Task C1 + C2: contextual-tab registry / Edit-group builder (C1)
and selection-driven show/hide/restore handler (C2).

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
    """All registry entries use _build_contextual_edit_group unless they have
    a richer family-specific builder (e.g. 'geo2d' uses _build_geo2d_context).
    Every entry must have a callable builder."""
    # Keys with dedicated builders (not the shared edit-group fallback):
    _DEDICATED_BUILDERS = {
        "geo2d": main_window._build_geo2d_context,
    }
    for key, (_title, builder) in main_window._contextual_registry.items():
        if key in _DEDICATED_BUILDERS:
            assert builder == _DEDICATED_BUILDERS[key], (
                f"Builder for key {key!r} expected {_DEDICATED_BUILDERS[key].__name__!r}, "
                f"got {builder.__name__!r}"
            )
        else:
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


# ─────────────────────────────────────────────────────────────────────────────
# Task C2: selection-driven contextual tab show / hide / restore
# ─────────────────────────────────────────────────────────────────────────────

from PyQt6.QtCore import QPointF
from firepro3d.wall import WallSegment
from firepro3d.pipe import Pipe
from firepro3d.node import Node


def _titles(mw):
    """Return the list of tab titles currently shown in the ribbon."""
    tb = mw.ribbon._tab_bar
    return [tb.tabText(i) for i in range(tb.count())]


def _make_wall(scene):
    """Add a real WallSegment to *scene* and return it."""
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0))
    scene.addItem(w)
    return w


def _make_pipe(scene):
    """Add a real Pipe (with two Nodes) to *scene* and return the pipe."""
    n1 = Node(0, 0)
    n2 = Node(1000, 0)
    scene.addItem(n1)
    scene.addItem(n2)
    p = Pipe(n1, n2)
    scene.addItem(p)
    return p


@pytest.fixture(autouse=False)
def clean_scene(main_window, qapp):
    """Per-test fixture: clear scene selection and remove non-permanent items
    added during a test, then reset the contextual-tab state.

    ``autouse=False`` — only the C2 tests request this fixture explicitly.
    """
    yield
    # Clear selection first so the selectionChanged handler runs cleanly.
    main_window.scene.clearSelection()
    qapp.processEvents()
    # Remove items that were dynamically added (walls, pipes, nodes).
    from firepro3d.wall import WallSegment as _WS
    from firepro3d.pipe import Pipe as _P
    from firepro3d.node import Node as _N
    for item in list(main_window.scene.items()):
        if isinstance(item, (_WS, _P, _N)):
            main_window.scene.removeItem(item)
    qapp.processEvents()


def test_selecting_a_wall_shows_wall_tab(main_window, qapp, clean_scene):
    """Selecting a WallSegment must insert a 'Wall' contextual tab and
    switch to it."""
    wall = _make_wall(main_window.scene)
    wall.setSelected(True)
    qapp.processEvents()
    tabs = _titles(main_window)
    assert "Wall" in tabs, f"Expected 'Wall' tab; got {tabs}"
    assert main_window.ribbon._tab_bar.currentIndex() == tabs.index("Wall")


def test_deselect_removes_contextual_and_restores(main_window, qapp, clean_scene):
    """Clearing the selection must remove the contextual tab and restore the
    previously active base tab."""
    mw = main_window
    mw.ribbon._tab_bar.setCurrentIndex(2)            # 'Create' base tab
    wall = _make_wall(mw.scene)
    wall.setSelected(True)
    qapp.processEvents()
    assert "Wall" in _titles(mw)                     # contextual appeared

    mw.scene.clearSelection()
    qapp.processEvents()
    tabs = _titles(mw)
    assert "Wall" not in tabs, f"'Wall' tab should be gone; got {tabs}"
    assert mw.ribbon._tab_bar.currentIndex() == 2, (
        f"Expected restore to tab 2 (Create); got {mw.ribbon._tab_bar.currentIndex()}"
    )


def test_switch_wall_to_pipe_keeps_pre_tab(main_window, qapp, clean_scene):
    """Switching directly from a wall selection to a pipe selection must swap
    the contextual tab and, after final deselect, restore the original base tab
    (not the contextual index)."""
    mw = main_window
    mw.ribbon._tab_bar.setCurrentIndex(2)            # remember 'Create'

    w = _make_wall(mw.scene)
    w.setSelected(True)
    qapp.processEvents()
    assert "Wall" in _titles(mw)

    # Swap selection: deselect wall, select pipe
    w.setSelected(False)
    p = _make_pipe(mw.scene)
    p.setSelected(True)
    qapp.processEvents()
    tabs = _titles(mw)
    assert "Pipe" in tabs, f"Expected 'Pipe' tab; got {tabs}"
    assert "Wall" not in tabs, f"'Wall' tab should be gone; got {tabs}"

    # Deselect everything — pre-tab must still be 2 (Create), not the
    # contextual index that was active during the wall→pipe swap.
    mw.scene.clearSelection()
    qapp.processEvents()
    assert mw.ribbon._tab_bar.currentIndex() == 2, (
        f"Expected restore to tab 2 (Create); got {mw.ribbon._tab_bar.currentIndex()}"
    )


def test_mixed_selection_shows_modify(main_window, qapp, clean_scene):
    """Selecting items from two different families must show the 'Modify' tab."""
    mw = main_window
    w = _make_wall(mw.scene)
    p = _make_pipe(mw.scene)
    w.setSelected(True)
    p.setSelected(True)
    qapp.processEvents()
    tabs = _titles(mw)
    assert "Modify" in tabs, f"Expected 'Modify' (mixed) tab; got {tabs}"


def test_unmappable_selection_shows_no_contextual(main_window, qapp, clean_scene):
    """Selecting only items that _family_key_for maps to None must NOT insert
    any contextual tab — the tab count stays at 7 and the active tab is
    unchanged."""
    from PyQt6.QtWidgets import QGraphicsRectItem
    mw = main_window
    mw.ribbon._tab_bar.setCurrentIndex(2)
    r = QGraphicsRectItem(0, 0, 10, 10)
    r.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
    mw.scene.addItem(r)
    try:
        r.setSelected(True)
        qapp.processEvents()
        titles = _titles(mw)
        assert mw.ribbon._tab_bar.count() == 7, (
            f"Expected 7 tabs (no contextual inserted); got {mw.ribbon._tab_bar.count()}: {titles}"
        )
        assert mw.ribbon._tab_bar.currentIndex() == 2, (
            f"Expected active tab 2 (Create) to be unchanged; got {mw.ribbon._tab_bar.currentIndex()}"
        )
    finally:
        mw.scene.removeItem(r)
        mw.scene.clearSelection()
        qapp.processEvents()
