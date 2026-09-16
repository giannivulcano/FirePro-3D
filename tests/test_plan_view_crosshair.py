"""tests/test_plan_view_crosshair.py — plan views get the accent crosshair.

Bug (user, 2026-09-16; backlog #64): the accent crosshair was applied once at
startup (_apply_crosshair) over the views that existed THEN — only the vestigial
startup view.  Every plan tab is created LATER by _activate_plan_view, so a fresh
plan view never got the crosshair.  _activate_plan_view now seeds it from the
live ui/crosshair preference.

MainWindow-based (mirrors tests/test_stale_view_tabs.py); these pop a window.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    w = main_mod.MainWindow()
    yield w
    w._modified = False
    w.close()


def _plan_view(win, level):
    name = f"Plan: {level}"
    for i in range(win.central_tabs.count()):
        if win.central_tabs.tabText(i) == name:
            return win.central_tabs.widget(i)
    return None


def test_newly_activated_plan_view_gets_crosshair(mw):
    mw._activate_plan_view("Level 2")
    pv = _plan_view(mw, "Level 2")
    assert pv is not None
    assert pv._crosshair_enabled is True


def test_plan_view_honours_crosshair_preference_off(mw):
    mw.settings.setValue("ui/crosshair", False)
    mw._activate_plan_view("Level 3")
    pv = _plan_view(mw, "Level 3")
    assert pv is not None
    assert pv._crosshair_enabled is False
