"""Tests for the geo2d contextual ribbon tab — Placement + Fill groups.

Verifies:
  1. Selecting a RectangleItem shows the '2D Geometry' contextual tab containing
     groups named 'Placement' and 'Fill'.
  2. Driving the Fill-type control to 'solid' routes through the undo path:
     rect.fill_type == 'solid' AND exactly one undo step was pushed.
  3. Driving the Level Offset control commits the parsed mm to
     rect._level_offset_mm.
  4. Fill group is DISABLED when a LineItem (non-fillable) is selected.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from firepro3d.construction_geometry import RectangleItem, LineItem
from main import MainWindow


# ─────────────────────────────────────────────────────────────────────────────
# Module-scoped MainWindow singleton
# ─────────────────────────────────────────────────────────────────────────────

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
    """Per-test view of the shared MainWindow."""
    yield _main_window_singleton


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _titles(mw):
    """Return current ribbon tab titles."""
    tb = mw.ribbon._tab_bar
    return [tb.tabText(i) for i in range(tb.count())]


def _make_rect(scene):
    """Add a RectangleItem (fillable) to *scene* and return it."""
    r = RectangleItem(QPointF(0, 0), QPointF(500, 300))
    scene.addItem(r)
    return r


def _make_line(scene):
    """Add a LineItem (non-fillable) to *scene* and return it."""
    ln = LineItem(QPointF(0, 0), QPointF(1000, 0))
    scene.addItem(ln)
    return ln


@pytest.fixture(autouse=False)
def clean_scene(main_window, qapp):
    """Clear scene selection and geo2d items after each test."""
    yield
    main_window.scene.clearSelection()
    qapp.processEvents()
    for item in list(main_window.scene.items()):
        if isinstance(item, (RectangleItem, LineItem)):
            main_window.scene.removeItem(item)
    qapp.processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: groups named 'Placement' and 'Fill' appear on the geo2d tab
# ─────────────────────────────────────────────────────────────────────────────

def _group_titles(page):
    """Return the group label texts found on a RibbonPage."""
    from firepro3d.ribbon_bar import RibbonGroup
    from PyQt6.QtWidgets import QLabel
    titles = []
    for g in page.findChildren(RibbonGroup):
        for lbl in g.findChildren(QLabel):
            titles.append(lbl.text())
    return titles


def test_geo2d_tab_has_placement_and_fill_groups(main_window, qapp, clean_scene):
    """Selecting a RectangleItem must show '2D Geometry' tab with 'Placement'
    and 'Fill' groups."""
    rect = _make_rect(main_window.scene)
    rect.setSelected(True)
    qapp.processEvents()

    tabs = _titles(main_window)
    assert "2D Geometry" in tabs, f"Expected '2D Geometry' contextual tab; got {tabs}"

    # Find the contextual page
    idx = tabs.index("2D Geometry")
    page = main_window.ribbon._stack.widget(idx)
    group_titles = _group_titles(page)

    assert "Placement" in group_titles, (
        f"Expected 'Placement' group; found groups: {group_titles}"
    )
    assert "Fill" in group_titles, (
        f"Expected 'Fill' group; found groups: {group_titles}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Fill-type control routes through undo path (one undo step pushed)
# ─────────────────────────────────────────────────────────────────────────────

def test_fill_type_control_routes_through_undo(main_window, qapp, clean_scene):
    """Driving the Fill-type combo to 'solid' must set rect.fill_type and push
    exactly one snapshot onto the model undo stack."""
    rect = _make_rect(main_window.scene)
    rect.setSelected(True)
    qapp.processEvents()

    # Capture undo stack depth before change
    before_pos = main_window.scene._undo_pos

    # Find the fill-type combo (QComboBox with "none"/"solid"/"hatch" options)
    from PyQt6.QtWidgets import QComboBox
    tabs = _titles(main_window)
    idx = tabs.index("2D Geometry")
    page = main_window.ribbon._stack.widget(idx)
    combos = page.findChildren(QComboBox)

    fill_combo = None
    for c in combos:
        items = [c.itemText(i) for i in range(c.count())]
        if "none" in items and "solid" in items and "hatch" in items:
            fill_combo = c
            break
    assert fill_combo is not None, "Could not find Fill-type combo on geo2d page"

    # Drive the combo to "solid"
    fill_combo.setCurrentText("solid")
    fill_combo.activated.emit(fill_combo.currentIndex())
    qapp.processEvents()

    assert rect.fill_type == "solid", (
        f"Expected fill_type 'solid'; got {rect.fill_type!r}"
    )
    assert main_window.scene._undo_pos == before_pos + 1, (
        f"Expected exactly one undo step pushed; "
        f"before={before_pos}, after={main_window.scene._undo_pos}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Level Offset control commits parsed mm to rect._level_offset_mm
# ─────────────────────────────────────────────────────────────────────────────

def test_level_offset_control_commits_mm(main_window, qapp, clean_scene):
    """Entering a value into the Level Offset field must commit the parsed mm
    value to rect._level_offset_mm."""
    rect = _make_rect(main_window.scene)
    rect.setSelected(True)
    qapp.processEvents()

    from firepro3d.dimension_edit import DimensionEdit
    tabs = _titles(main_window)
    idx = tabs.index("2D Geometry")
    page = main_window.ribbon._stack.widget(idx)

    dim_edits = page.findChildren(DimensionEdit)
    assert dim_edits, "Expected at least one DimensionEdit (Level Offset) on geo2d page"

    # Use the first DimensionEdit (Level Offset)
    offset_edit = dim_edits[0]

    # Simulate the user typing "100 mm" — setText changes the display text
    # so it no longer matches _seed_text, and _on_editing_finished will parse it.
    offset_edit.setText("100 mm")
    offset_edit._on_editing_finished()
    qapp.processEvents()

    assert rect._level_offset_mm == pytest.approx(100.0, abs=0.1), (
        f"Expected _level_offset_mm ≈ 100.0; got {rect._level_offset_mm}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Fill group is disabled when a non-fillable item (LineItem) is selected
# ─────────────────────────────────────────────────────────────────────────────

def test_fill_group_disabled_for_non_fillable(main_window, qapp, clean_scene):
    """When only a LineItem (non-fillable) is selected, the Fill group must be
    disabled (all its controls inert)."""
    ln = _make_line(main_window.scene)
    ln.setSelected(True)
    qapp.processEvents()

    tabs = _titles(main_window)
    assert "2D Geometry" in tabs, f"Expected '2D Geometry' tab; got {tabs}"

    idx = tabs.index("2D Geometry")
    page = main_window.ribbon._stack.widget(idx)

    from firepro3d.ribbon_bar import RibbonGroup
    from PyQt6.QtWidgets import QLabel

    def _find_group_by_title(pg, title):
        for g in pg.findChildren(RibbonGroup):
            for lbl in g.findChildren(QLabel):
                if lbl.text() == title:
                    return g
        return None

    fill_group = _find_group_by_title(page, "Fill")
    assert fill_group is not None, "Fill group not found on page"

    assert not fill_group.isEnabled(), (
        "Fill group should be disabled when a non-fillable item is selected"
    )
