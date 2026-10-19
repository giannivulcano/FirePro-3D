"""Tests for the geo2d contextual ribbon tab (redesign 2026-09-16).

Verifies:
  1. Selecting a RectangleItem shows the 'Modify | Rectangle' contextual tab
     with groups Edit + Graphic Override — and NO Placement/Fill/Constraints
     (Placement dropped as property-panel redundant; Fill folded into the
     condensed Graphic Override group; the legacy Constraints group retired
     with the prototype — parametric-constraint-system.md §2).
  2. Picking a pattern on the ribbon Fill Pattern swatch (UP1) writes the
     rect's pattern layer AND pushes exactly one undo step.
  3. The Fill / Fill Pattern swatches are DISABLED when a LineItem
     (non-fillable) is selected (the Graphic Override group stays enabled —
     stroke override applies).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from firepro3d.geometry_2d import RectangleItem, LineItem
from main import MainWindow
from tests._mainwindow_helpers import dispose_main_window


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
    dispose_main_window(win)
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
    """Return the group label texts (UPPERCASE) found on a RibbonPage.

    Group labels render UPPERCASE + vertical after the chrome revamp (Task 3);
    field labels like ``Fill:`` keep their case+colon, so the colon check below
    still distinguishes a 'Fill' group from a 'Fill:' field label.
    """
    from firepro3d.ribbon_bar import RibbonGroup
    from PyQt6.QtWidgets import QLabel
    titles = []
    for g in page.findChildren(RibbonGroup):
        for lbl in g.findChildren(QLabel):
            titles.append(lbl.text().upper())
    return titles


def test_geo2d_tab_has_edit_graphic_override(main_window, qapp, clean_scene):
    """Selecting a RectangleItem must show 'Modify | Rectangle' with Edit +
    Graphic Override groups, and NO Placement/Fill/Constraints groups."""
    rect = _make_rect(main_window.scene)
    rect.setSelected(True)
    qapp.processEvents()

    tabs = _titles(main_window)
    assert "Modify | Rectangle" in tabs, f"Expected 'Modify | Rectangle' contextual tab; got {tabs}"

    idx = tabs.index("Modify | Rectangle")
    page = main_window.ribbon._stack.widget(idx)
    group_titles = _group_titles(page)

    assert "EDIT" in group_titles, group_titles
    assert "GRAPHIC OVERRIDE" in group_titles, group_titles
    assert "CONSTRAINTS" not in group_titles, group_titles   # legacy group retired
    # Dropped / folded away:
    assert "PLACEMENT" not in group_titles, group_titles
    assert "FILL" not in group_titles, group_titles  # a 'Fill:' field label is fine (has colon)


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Fill Pattern swatch routes through undo path (one undo step pushed)
# ─────────────────────────────────────────────────────────────────────────────

def _ribbon_fill_swatches(main_window, tab_title):
    """FillSwatches on the named contextual tab page (the property panel also
    hosts FillSwatches, so select the ribbon's by page ancestry)."""
    from firepro3d.ui_kit import FillSwatch
    idx = _titles(main_window).index(tab_title)
    page = main_window.ribbon._stack.widget(idx)
    return page.findChildren(FillSwatch)


def test_fill_pattern_swatch_routes_through_one_undo_step(
        main_window, qapp, clean_scene, monkeypatch):
    """Picking a pattern on the ribbon Fill Pattern swatch writes the pattern
    layer of the selected rect and pushes exactly one undo step."""
    from PyQt6.QtCore import Qt
    from firepro3d import colour_picker
    from firepro3d.fill_layers import PatternLayer
    from firepro3d.hatch_patterns import DEFAULT_TILE_REF
    rect = _make_rect(main_window.scene)
    rect.setSelected(True)
    qapp.processEvents()

    sw = next(s for s in _ribbon_fill_swatches(main_window, "Modify | Rectangle")
              if s._context == "Fill Pattern")
    new = PatternLayer(DEFAULT_TILE_REF, "token:auto", 1.0, 1.0)
    monkeypatch.setattr(colour_picker, "pick_fill", lambda *a, **k: new)
    before_pos = main_window.scene._undo_pos
    QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert rect.fill_layers.pattern == new
    assert main_window.scene._undo_pos == before_pos + 1, (
        f"Expected exactly one undo step pushed; "
        f"before={before_pos}, after={main_window.scene._undo_pos}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: fill controls disabled for a non-fillable item (LineItem)
# ─────────────────────────────────────────────────────────────────────────────

def test_fill_controls_disabled_for_non_fillable(main_window, qapp, clean_scene):
    """A LineItem (non-fillable) disables the Fill / Fill Pattern swatches in the Graphic
    Override group (the group itself stays enabled — stroke override applies)."""
    ln = _make_line(main_window.scene)
    ln.setSelected(True)
    qapp.processEvents()

    tabs = _titles(main_window)
    assert "Modify | Line" in tabs, f"Expected 'Modify | Line' tab; got {tabs}"

    swatches = _ribbon_fill_swatches(main_window, "Modify | Line")
    assert {s._context for s in swatches} == {"Fill", "Fill Pattern"}, swatches
    for sw in swatches:
        assert not sw.isEnabled(), (
            "fill swatches must be disabled when a non-fillable line is selected"
        )
