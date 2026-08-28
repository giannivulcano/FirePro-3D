"""Tests for the reusable 'Graphic Override' ribbon group + Floor contextual tab.

Verifies (Task 7 of the floor-workflow feature branch):
  1. The Stroke Colour override action writes ``_display_overrides["color"]`` on
     each selected FloorSlab, takes visual effect (``_display_color`` set), and
     pushes exactly one undo step (undo reverts to no-override).
  2. The Fill Colour override action writes ``_display_overrides["fill"]``.
  3. The Clear action wipes the per-instance overrides (reverting the item to
     its category defaults); undo restores them.
  4. With nothing selected, invoking an override action pushes NO undo step.

QColorDialog.getColor is patched throughout so no modal ever blocks the suite.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from firepro3d.floor_slab import FloorSlab
from main import MainWindow


# ─────────────────────────────────────────────────────────────────────────────
# Module-scoped MainWindow singleton (mirrors test_geo2d_contextual_tab.py)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
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
    yield _main_window_singleton


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _titles(mw):
    tb = mw.ribbon._tab_bar
    return [tb.tabText(i) for i in range(tb.count())]


def _make_slab(scene):
    """Add a FloorSlab (three-point closed boundary) to *scene* and register it
    in ``_floor_slabs`` so the Display-Manager apply path can find it.

    Pushes an undo checkpoint AFTER registration so the "slab exists, no
    override" state is a distinct undo position — otherwise an undo after the
    first override would step past the slab's creation and delete it.
    """
    slab = FloorSlab([QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000)])
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    scene.push_undo_state()
    return slab


def _floor_page(mw):
    """Return the RibbonPage for the Floor contextual tab (must be shown)."""
    tabs = _titles(mw)
    assert "Floor" in tabs, f"Expected 'Floor' contextual tab; got {tabs}"
    idx = tabs.index("Floor")
    return mw.ribbon._stack.widget(idx)


def _group_titles(page):
    from firepro3d.ribbon_bar import RibbonGroup
    from PyQt6.QtWidgets import QLabel
    titles = []
    for g in page.findChildren(RibbonGroup):
        for lbl in g.findChildren(QLabel):
            titles.append(lbl.text())
    return titles


def _find_button(page, text):
    """Find a ribbon button on *page* whose text matches *text*."""
    from PyQt6.QtWidgets import QToolButton, QAbstractButton
    for b in page.findChildren(QAbstractButton):
        if b.text() == text:
            return b
    return None


@pytest.fixture(autouse=True)
def clean_scene(main_window, qapp):
    yield
    main_window.scene.clearSelection()
    qapp.processEvents()
    for item in list(main_window.scene.items()):
        if isinstance(item, FloorSlab):
            main_window.scene.removeItem(item)
            if item in main_window.scene._floor_slabs:
                main_window.scene._floor_slabs.remove(item)
    qapp.processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# Test: Floor contextual tab carries Edit + Graphic Override groups
# ─────────────────────────────────────────────────────────────────────────────

def test_floor_tab_has_edit_and_graphic_override_groups(main_window, qapp):
    slab = _make_slab(main_window.scene)
    slab.setSelected(True)
    qapp.processEvents()

    page = _floor_page(main_window)
    titles = _group_titles(page)
    assert "Edit" in titles, f"Expected 'Edit' group; got {titles}"
    assert "Graphic Override" in titles, (
        f"Expected 'Graphic Override' group; got {titles}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Stroke override sets _display_overrides["color"] + one undo step
# ─────────────────────────────────────────────────────────────────────────────

def test_stroke_override_sets_display_override_and_undo(
        main_window, qapp, monkeypatch):
    slab = _make_slab(main_window.scene)
    slab.setSelected(True)
    qapp.processEvents()

    from PyQt6.QtWidgets import QColorDialog
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor("#ff0000")))

    before_pos = main_window.scene._undo_pos
    main_window._graphic_override_stroke()
    qapp.processEvents()

    assert slab._display_overrides.get("color") == "#ff0000", (
        f"Expected stroke override '#ff0000'; got {slab._display_overrides}"
    )
    # Visual take-effect: apply path pushed it onto _display_color.
    assert (slab._display_color or "").lower() == "#ff0000", (
        f"Expected _display_color '#ff0000'; got {slab._display_color!r}"
    )
    # Exactly one undo step.
    assert main_window.scene._undo_pos == before_pos + 1, (
        f"Expected one undo step; before={before_pos}, "
        f"after={main_window.scene._undo_pos}"
    )
    # Undo reverts to no-override. Undo rebuilds FloorSlab objects, so the
    # original `slab` reference is stale — re-fetch from the scene.
    main_window.scene.undo()
    qapp.processEvents()
    slab2 = main_window.scene._floor_slabs[0]
    assert "color" not in slab2._display_overrides, (
        f"Undo should clear the stroke override; got {slab2._display_overrides}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Fill override sets _display_overrides["fill"]
# ─────────────────────────────────────────────────────────────────────────────

def test_fill_override_sets_display_override(main_window, qapp, monkeypatch):
    slab = _make_slab(main_window.scene)
    slab.setSelected(True)
    qapp.processEvents()

    from PyQt6.QtWidgets import QColorDialog
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor("#00cc00")))

    before_pos = main_window.scene._undo_pos
    main_window._graphic_override_fill()
    qapp.processEvents()

    assert slab._display_overrides.get("fill") == "#00cc00", (
        f"Expected fill override '#00cc00'; got {slab._display_overrides}"
    )
    assert (slab._display_fill_color or "").lower() == "#00cc00", (
        f"Expected _display_fill_color '#00cc00'; got {slab._display_fill_color!r}"
    )
    assert main_window.scene._undo_pos == before_pos + 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Clear reverts to category (overrides emptied); undo restores them
# ─────────────────────────────────────────────────────────────────────────────

def test_clear_reverts_to_category(main_window, qapp):
    slab = _make_slab(main_window.scene)
    slab.setSelected(True)
    # Seed both overrides directly, then snapshot this state as the clean
    # "before Clear" baseline. (The app's undo pushes a pre-mutation snapshot,
    # so a single undo of the Clear action returns to exactly this checkpoint.)
    slab._display_overrides["color"] = "#123456"
    slab._display_overrides["fill"] = "#654321"
    main_window.scene.push_undo_state()
    qapp.processEvents()

    before_pos = main_window.scene._undo_pos
    main_window._graphic_override_clear()
    qapp.processEvents()

    assert "color" not in slab._display_overrides, (
        f"Clear should remove the stroke override; got {slab._display_overrides}"
    )
    assert "fill" not in slab._display_overrides, (
        f"Clear should remove the fill override; got {slab._display_overrides}"
    )
    assert main_window.scene._undo_pos == before_pos + 1

    # Undo the Clear. Undo rebuilds FloorSlab objects, so re-fetch from the scene.
    main_window.scene.undo()
    qapp.processEvents()
    slab2 = main_window.scene._floor_slabs[0]
    assert slab2._display_overrides.get("color") == "#123456"
    assert slab2._display_overrides.get("fill") == "#654321"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: No selection → no undo step pushed
# ─────────────────────────────────────────────────────────────────────────────

def test_no_selection_no_undo(main_window, qapp, monkeypatch):
    main_window.scene.clearSelection()
    qapp.processEvents()

    from PyQt6.QtWidgets import QColorDialog
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor("#abcdef")))

    before_pos = main_window.scene._undo_pos
    main_window._graphic_override_stroke()
    main_window._graphic_override_fill()
    main_window._graphic_override_clear()
    qapp.processEvents()

    assert main_window.scene._undo_pos == before_pos, (
        f"No selection must push no undo step; "
        f"before={before_pos}, after={main_window.scene._undo_pos}"
    )
