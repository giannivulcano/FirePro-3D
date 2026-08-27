"""Regression: view tabs from a prior project must not persist on load/new.

Bug (user, 2026-08-27): opening a project left the previous project's view
tabs open — e.g. a 'Plan: Level 1' tab lingered after opening a project that
has no Level 1. _apply_loaded_file / new_file never removed the disposable
Plan/Elevation/Detail tabs before opening the new project's plan view.
"""
from __future__ import annotations

import pytest
from PyQt6 import sip


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow per test (mirrors test_detail_new_project_leak.py)."""
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


def _plan_tabs(win):
    return [win.central_tabs.tabText(i)
            for i in range(win.central_tabs.count())
            if win.central_tabs.tabText(i).startswith("Plan: ")]


def test_close_stale_view_tabs_removes_views_keeps_paper(mw):
    win = mw
    win._activate_plan_view("Level 1")
    win._activate_plan_view("Level 2")
    win._activate_paper_sheet()  # open the paper singleton tab
    win._close_stale_view_tabs()
    titles = [win.central_tabs.tabText(i)
              for i in range(win.central_tabs.count())]
    assert not any(t.startswith(("Plan: ", "Elevation: ", "Detail: "))
                   for t in titles), f"view tabs not cleared: {titles}"
    # The paper singleton must NOT be deleted (it is reused, not disposable).
    assert not sip.isdeleted(win.paper_space_widget)


def test_new_file_closes_stale_plan_tabs(mw):
    win = mw
    win._activate_plan_view("Level 2")
    assert "Plan: Level 2" in _plan_tabs(win), "precondition"
    win._modified = False
    win.new_file()
    plan = _plan_tabs(win)
    assert len(plan) == 1, f"new_file must leave exactly one plan tab, got {plan}"
    assert "Plan: Level 2" not in plan, "stale plan tab persisted through new_file"


def test_load_project_leaves_single_plan_tab(mw, tmp_path, monkeypatch):
    win = mw
    # Avoid the embedded-template divergence modal during headless load.
    monkeypatch.setattr(win, "_maybe_offer_template_push", lambda: None)
    proj = str(tmp_path / "proj.FPD")
    win.scene.save_to_file(proj)
    # Leftover tabs from a prior session.
    win._activate_plan_view("Level 1")
    win._activate_plan_view("Level 2")
    assert len(_plan_tabs(win)) >= 2, "precondition: multiple plan tabs"
    win._modified = False
    win._load_project(proj)
    plan = _plan_tabs(win)
    assert len(plan) == 1, (
        f"opening a project must drop prior view tabs and leave exactly one "
        f"plan tab (the loaded active level); got {plan}")
