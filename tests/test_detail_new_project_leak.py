"""Regression tests: detail manager does not leak across new_file() or from_list().

Bug (root cause)
----------------
MainWindow.new_file() called scene._clear_scene() but never reset
detail_manager — its _markers dict kept old entries, so the Project Browser
showed stale detail items with no geometry after File → New.

Likewise DetailViewManager.from_list() appended without clearing first, so
loading project B after project A accumulated A's details.

Tests
-----
- test_new_file_clears_details          : functional MainWindow path
- test_from_list_does_not_accumulate    : unit test for from_list idempotency
- test_clear_removes_marker_from_scene  : unit test for clear() itself
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QRectF


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixture — mirrors test_apply_level_uses_resolver.py
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow per test with safe teardown.

    Pins APPDATA to a temp dir so MainWindow.__init__ never touches real user
    data. Saves/restores the snap tolerance constant that __init__ overwrites
    from QSettings.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d.view_3d import View3D
    from firepro3d import snap_engine
    main_mod.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    yield w
    w._modified = False
    w.close()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


# ─────────────────────────────────────────────────────────────────────────────
# Functional test: MainWindow.new_file() resets the detail manager
# ─────────────────────────────────────────────────────────────────────────────

def test_new_file_clears_details(mw):
    """File → New must leave detail_manager empty (no stale markers)."""
    win = mw

    # Create a detail via the real path so detail_names is non-empty
    win.detail_manager.create_detail(
        "Detail 1",
        QRectF(0, 0, 1000, 1000),
        "Level 1",
    )
    assert win.detail_manager.detail_names, "pre-condition: detail must exist before new_file()"

    # Suppress the "unsaved changes" dialog — _ask_save_changes returns True
    # immediately when _modified is False.
    win._modified = False
    win.new_file()

    assert win.detail_manager.detail_names == [], (
        "new_file() must clear the detail manager; got: "
        f"{win.detail_manager.detail_names}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Unit test: from_list() does not accumulate across two calls
# ─────────────────────────────────────────────────────────────────────────────

def test_from_list_does_not_accumulate(mw):
    """Loading a project twice must not double-up detail markers.

    Calls from_list() with a single entry, then with a DIFFERENT entry (as
    would happen when opening project B after project A). Without the fix,
    both sets accumulate; with the fix, only the second load's entries remain.
    """
    dm = mw.detail_manager

    payload_a = [
        {
            "name": "Detail 1",
            "level_name": "Level 1",
            "crop_rect": {"x": 0.0, "y": 0.0, "w": 1000.0, "h": 1000.0},
            "bubble_pos": {"x": 500.0, "y": 1250.0},
        }
    ]
    payload_b = [
        {
            "name": "Detail 2",
            "level_name": "Level 1",
            "crop_rect": {"x": 2000.0, "y": 0.0, "w": 500.0, "h": 500.0},
            "bubble_pos": {"x": 2250.0, "y": 750.0},
        }
    ]

    dm.from_list(payload_a)
    assert dm.detail_names == ["Detail 1"], "first load must create exactly one entry"

    dm.from_list(payload_b)
    assert dm.detail_names == ["Detail 2"], (
        "second from_list() must REPLACE prior details, not accumulate; "
        f"got {dm.detail_names}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Unit test: clear() removes marker from the scene
# ─────────────────────────────────────────────────────────────────────────────

def test_clear_removes_marker_from_scene(mw):
    """clear() must remove the QGraphicsItem from the scene."""
    from firepro3d.detail_view import DetailMarker

    win = mw
    dm = win.detail_manager
    scene = win.scene

    marker = dm.create_detail("Detail 1", QRectF(0, 0, 500, 500), "Level 1")
    # Verify the marker is in the scene before clear
    assert any(isinstance(it, DetailMarker) for it in scene.items()), (
        "marker must be in scene after create_detail"
    )

    dm.clear()

    assert dm.detail_names == [], "clear() must empty _markers"
    assert dm._counter == 0, "clear() must reset _counter to 0"
    assert not any(isinstance(it, DetailMarker) for it in scene.items()), (
        "clear() must remove the DetailMarker QGraphicsItem from the scene"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sibling leak: plan_view_mgr per-view cut-plane settings across new_file()
#
# Same bug class as the detail leak above — new_file() cleared the detail
# manager but not plan_view_mgr._views, so a stale "Plan: <old level>" cut-plane
# view survived into the fresh project (masked because create() reuses by name).
# ─────────────────────────────────────────────────────────────────────────────

def test_new_file_clears_plan_views(mw):
    """File → New must drop stale per-level PlanViews (only the fresh one left)."""
    win = mw

    # Create a PlanView for a level that the fresh project won't reactivate.
    win.plan_view_mgr.create("Old Level", win.level_mgr)
    assert win.plan_view_mgr.get("Plan: Old Level") is not None, (
        "pre-condition: stale plan view must exist before new_file()"
    )

    win._modified = False
    win.new_file()

    assert win.plan_view_mgr.get("Plan: Old Level") is None, (
        "new_file() must clear stale PlanViews; the old level's view leaked"
    )


def test_plan_view_clear_empties_views(mw):
    """PlanViewManager.clear() must empty _views."""
    pvm = mw.plan_view_mgr
    pvm.create("Level A", mw.level_mgr)
    pvm.create("Level B", mw.level_mgr)
    assert pvm._views, "pre-condition: views must exist before clear()"

    pvm.clear()

    assert pvm._views == {}, "clear() must empty _views"
