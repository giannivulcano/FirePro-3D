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
    # 6 base tabs → contextual insert slot is 6 (derived from the live tab
    # count so it can't drift). Must equal the actual base-tab count.
    assert main_window._contextual_index == 6
    assert main_window._contextual_index == main_window.ribbon._tab_bar.count()


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
        "opening": main_window._build_opening_context,
        "floor": main_window._build_floor_context,
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
    """Selecting a WallSegment must insert a 'Modify | Wall' contextual tab and
    switch to it."""
    wall = _make_wall(main_window.scene)
    wall.setSelected(True)
    qapp.processEvents()
    tabs = _titles(main_window)
    assert "Modify | Wall" in tabs, f"Expected 'Modify | Wall' tab; got {tabs}"
    assert main_window.ribbon._tab_bar.currentIndex() == tabs.index("Modify | Wall")


def test_deselect_removes_contextual_and_restores(main_window, qapp, clean_scene):
    """Clearing the selection must remove the contextual tab and restore the
    previously active base tab."""
    mw = main_window
    mw.ribbon._tab_bar.setCurrentIndex(2)            # 'Create' base tab
    wall = _make_wall(mw.scene)
    wall.setSelected(True)
    qapp.processEvents()
    assert "Modify | Wall" in _titles(mw)            # contextual appeared

    mw.scene.clearSelection()
    qapp.processEvents()
    tabs = _titles(mw)
    assert "Modify | Wall" not in tabs, f"contextual tab should be gone; got {tabs}"
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
    assert "Modify | Wall" in _titles(mw)

    # Swap selection: deselect wall, select pipe
    w.setSelected(False)
    p = _make_pipe(mw.scene)
    p.setSelected(True)
    qapp.processEvents()
    tabs = _titles(mw)
    assert "Modify | Pipe" in tabs, f"Expected 'Modify | Pipe' tab; got {tabs}"
    assert "Modify | Wall" not in tabs, f"'Modify | Wall' tab should be gone; got {tabs}"

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


# ── RegularPolygonItem → "geo2d" contextual key ───────────────────────────────

def test_polygon_family_key_is_geo2d(main_window):
    """_family_key_for(RegularPolygonItem) must return 'geo2d'.

    RED-VERIFY: before adding RegularPolygonItem to the isinstance tuple in
    _family_key_for, this test would return None and the assert would fail.
    """
    from firepro3d.construction_geometry import RegularPolygonItem
    from PyQt6.QtCore import QPointF

    poly = RegularPolygonItem(center=QPointF(0, 0), sides=6, radius_mm=50.0)
    key = main_window._family_key_for(poly)
    assert key == "geo2d", (
        f"Expected 'geo2d' for RegularPolygonItem; got {key!r}"
    )


def test_selecting_polygon_shows_geo2d_tab(main_window, qapp, clean_scene):
    """Selecting a RegularPolygonItem must insert a 'Modify | Polygon' contextual tab."""
    from firepro3d.construction_geometry import RegularPolygonItem
    from PyQt6.QtCore import QPointF

    poly = RegularPolygonItem(center=QPointF(0, 0), sides=6, radius_mm=50.0)
    poly.setFlag(poly.GraphicsItemFlag.ItemIsSelectable, True)
    main_window.scene.addItem(poly)
    try:
        poly.setSelected(True)
        qapp.processEvents()
        tabs = _titles(main_window)
        assert "Modify | Polygon" in tabs, (
            f"Expected 'Modify | Polygon' contextual tab; got tabs: {tabs}"
        )
        assert main_window._active_contextual_key == "geo2d", (
            f"Expected _active_contextual_key='geo2d'; got {main_window._active_contextual_key!r}"
        )
    finally:
        main_window.scene.removeItem(poly)
        main_window.scene.clearSelection()
        qapp.processEvents()


def test_title_updates_on_element_switch_within_family(main_window, qapp, clean_scene):
    """Switching between two element types in the SAME family (Rectangle →
    Circle, both geo2d) must retitle the contextual tab, not silently leave the
    old element name — the guard tracks (key, title), not key alone."""
    from firepro3d.construction_geometry import RectangleItem, CircleItem
    mw = main_window
    rect = RectangleItem(QPointF(0, 0), QPointF(500, 300))
    circ = CircleItem(QPointF(0, 0), 100.0)
    for it in (rect, circ):
        it.setFlag(it.GraphicsItemFlag.ItemIsSelectable, True)
        mw.scene.addItem(it)
    try:
        rect.setSelected(True)
        qapp.processEvents()
        assert "Modify | Rectangle" in _titles(mw), _titles(mw)

        # Swap element WITHOUT an empty intermediate selection: add the circle
        # (→ same 'geo2d' family key, so a key-only guard would early-return and
        # leave the stale 'Rectangle' title), then drop the rectangle.
        circ.setSelected(True)
        qapp.processEvents()
        rect.setSelected(False)
        qapp.processEvents()
        tabs = _titles(mw)
        assert "Modify | Circle" in tabs, f"Expected retitle to Circle; got {tabs}"
        assert "Modify | Rectangle" not in tabs, f"Old title lingered; got {tabs}"
        # Still exactly one contextual tab (no accumulation).
        assert sum(t.startswith("Modify") for t in tabs) == 1, tabs
    finally:
        for it in (rect, circ):
            mw.scene.removeItem(it)
        mw.scene.clearSelection()
        qapp.processEvents()


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
        assert mw.ribbon._tab_bar.count() == 6, (
            f"Expected 6 tabs (no contextual inserted); got {mw.ribbon._tab_bar.count()}: {titles}"
        )
        assert mw.ribbon._tab_bar.currentIndex() == 2, (
            f"Expected active tab 2 (Create) to be unchanged; got {mw.ribbon._tab_bar.currentIndex()}"
        )
    finally:
        mw.scene.removeItem(r)
        mw.scene.clearSelection()
        qapp.processEvents()
