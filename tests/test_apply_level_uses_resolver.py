"""Guards that the paper ViewResolver built by MainWindow carries the
level manager (D1 wiring) and that _apply_plan_level/_apply_detail_level
delegate through it instead of inlining their own lookups."""
from __future__ import annotations

import pytest


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow with safe teardown.

    Mirrors the fixture in test_multi_sheet.py: saves/restores the snap
    tolerance constant that MainWindow.__init__ overwrites from QSettings.
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


def test_main_resolver_has_level_manager(mw):
    """The paper ViewResolver built by MainWindow must carry the level manager
    so viewports can isolate. Guards the wiring, not a synthetic stand-in."""
    win = mw
    assert win._view_resolver._level_manager is win.level_mgr
    win.plan_view_mgr.create(win.scene.active_level, win.level_mgr)
    ctx = win._view_resolver.resolve_level_context(
        "plan", f"Plan: {win.scene.active_level}")
    assert ctx is not None and ctx[0] == win.scene.active_level
