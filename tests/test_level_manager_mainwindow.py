"""Level Manager through the REAL MainWindow (view-relationships section 12.4): project
open / new refresh every levelsChanged consumer (repro 2026-10-30: the Project Browser
Plans list kept Level 1/2/3 after opening a Ground/Roof file); a rename retitles the open
plan tab in place and keeps its PlanView; a delete closes the tab, drops the PlanView,
re-points floor refs and is one undo step; the dialog chains into the hidden hub (D4)."""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from firepro3d import level_widget as lw_mod
from firepro3d.floor_slab import FloorSlab
from firepro3d.level_widget import _COL_NAME
from firepro3d.wall import WallSegment
from tests._mainwindow_helpers import dispose_main_window


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh, SHOWN MainWindow per test (test_sb2b_level_undo idiom) with the post-open
    template-push offer stubbed (a possible modal — test_lt1_open_order idiom)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d.view_3d import View3D
    from firepro3d import snap_engine
    main_mod.View3D = View3D
    monkeypatch.setattr(main_mod.MainWindow, "_maybe_offer_template_push", lambda self: None)
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    w.resize(1200, 800)
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(300)
    yield w
    dispose_main_window(w)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _plans(win):
    root = win.project_browser._plans_root
    return [root.child(i).text(0) for i in range(root.childCount())]


def _tabs(win):
    return [win.central_tabs.tabText(i) for i in range(win.central_tabs.count())]


def _names(win):
    return [l.name for l in win.level_mgr.levels]


def _set_levels(win, *rows):
    win.level_mgr.from_list([{"name": n, "elevation_mm": e, "number": k} for n, e, k in rows])
    win.level_widget.populate()


def _row(widget, name):
    return next(r for r in range(widget.table.rowCount())
                if widget.table.item(r, _COL_NAME).data(Qt.ItemDataRole.UserRole) == name)


def _hub_rows(win):
    t = win.level_widget.table
    return [t.item(r, _COL_NAME).text() for r in range(t.rowCount())]


def test_project_open_refreshes_the_project_browser_plans(mw, tmp_path):
    win = mw
    _set_levels(win, ("Ground", 0.0, 1), ("Roof", 3048.0, 2))
    path = str(tmp_path / "levels.fpd")
    assert win.scene.save_to_file(path)
    win._modified = False
    win.new_file()
    assert _plans(win) == ["Level 1", "Level 2", "Level 3"]
    win._load_project(path)                                  # the real open path
    assert _names(win) == ["Ground", "Roof"]
    assert _plans(win) == ["Ground", "Roof"]                 # was Level 1/2/3 before the fix


def test_new_file_refreshes_the_project_browser_plans(mw):
    win = mw
    _set_levels(win, ("Ground", 0.0, 1), ("Roof", 3048.0, 2))
    win.level_widget.levelsChanged.emit()
    assert _plans(win) == ["Ground", "Roof"]
    win._modified = False
    win.new_file()
    assert _plans(win) == ["Level 1", "Level 2", "Level 3"]


def test_open_resorts_an_out_of_order_file_everywhere(mw, tmp_path):
    win = mw
    _set_levels(win, ("Ground", 0.0, 1), ("Mid", 4000.0, 2), ("Roof", 9000.0, 3))
    path = tmp_path / "shuffled.fpd"
    assert win.scene.save_to_file(str(path))
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["levels"].reverse()                                  # a file saved out of order
    path.write_text(json.dumps(doc), encoding="utf-8")
    win._modified = False
    win._load_project(str(path))
    assert _names(win) == ["Ground", "Mid", "Roof"]
    assert [l.number for l in win.level_mgr.levels] == [1, 2, 3]       # names / Numbers / elevations kept
    assert _plans(win) == ["Ground", "Mid", "Roof"]
    assert _hub_rows(win) == ["Ground", "Mid", "Roof"]


def test_rename_in_the_dialog_retitles_the_open_plan_tab_and_keeps_its_plan_view(mw):
    win = mw
    win._activate_plan_view("Level 2")
    pv = win.plan_view_mgr.get("Plan: Level 2")
    pv.view_depth = -123.0
    n_tabs = win.central_tabs.count()
    dlg = win._build_level_dialog()
    dlg.show(); QTest.qWaitForWindowExposed(dlg)
    try:
        dlg.widget.table.item(_row(dlg.widget, "Level 2"), _COL_NAME).setText("Mezz")
    finally:
        dlg.close()
    tabs = _tabs(win)
    assert "Plan: Mezz" in tabs and "Plan: Level 2" not in tabs
    assert win.central_tabs.count() == n_tabs                 # retitled in place, not re-opened
    i = tabs.index("Plan: Mezz")
    assert win.central_tabs.widget(i).plan_view_name == "Plan: Mezz"       # the view's own labels follow (M-9)
    assert win.central_tabs.widget(i).objectName() == "plan_view_Mezz"
    assert win.plan_view_mgr.get("Plan: Mezz") is pv and pv.view_depth == -123.0
    assert win.plan_view_mgr.get("Plan: Level 2") is None
    assert win.scene.active_level == "Mezz"
    assert win.central_tabs.tabText(win.central_tabs.currentIndex()) == "Plan: Mezz"
    assert _plans(win) == ["Level 1", "Mezz", "Level 3"]
    assert _hub_rows(win) == ["Level 1", "Mezz", "Level 3"]   # D4: the hidden hub repopulated


def test_delete_in_the_dialog_closes_tabs_drops_plan_views_repoints_refs_in_one_step(mw, monkeypatch):
    win = mw
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: True)
    scene = win.scene
    win._activate_plan_view("Level 2")
    win._activate_plan_view("Level 3")                        # active = Level 3
    wall = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    wall.level = "Level 3"
    scene.addItem(wall); scene._walls.append(wall)
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)])
    slab._top_level = "Level 3"; slab._bottom_level = "Level 2"
    scene.addItem(slab); scene._floor_slabs.append(slab)
    scene.push_undo_state()
    depth = len(scene._undo_stack)
    dlg = win._build_level_dialog()
    dlg.show(); QTest.qWaitForWindowExposed(dlg)
    try:
        table = dlg.widget.table
        sm = table.selectionModel()
        for name in ("Level 2", "Level 3"):
            sm.select(table.model().index(_row(dlg.widget, name), 0),
                      sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
        dlg.widget._delete_level()
    finally:
        dlg.close()
    assert _names(win) == ["Level 1"]
    assert not any(t in ("Plan: Level 2", "Plan: Level 3") for t in _tabs(win))
    assert win.plan_view_mgr.get("Plan: Level 2") is None and win.plan_view_mgr.get("Plan: Level 3") is None
    assert wall.level == "Level 1"
    assert (slab._top_level, slab._bottom_level) == ("Level 1", "Level 1")
    assert scene.active_level == "Level 1"                    # P7: the deleted active level's target
    assert win.central_tabs.tabText(win.central_tabs.currentIndex()) == "Plan: Level 1"
    assert _plans(win) == ["Level 1"]
    assert len(scene._undo_stack) == depth + 1                # the whole selection = one step
    scene.undo()
    assert _names(win) == ["Level 1", "Level 2", "Level 3"]
    assert _plans(win) == ["Level 1", "Level 2", "Level 3"]


def test_undo_of_a_rename_leaves_a_single_plan_tab(mw):
    win = mw
    win._activate_plan_view("Level 2")
    win.scene.push_undo_state()
    lw = win.level_widget
    lw.table.item(_row(lw, "Level 2"), _COL_NAME).setText("Mezz")
    assert "Plan: Mezz" in _tabs(win) and "Plan: Level 2" not in _tabs(win)
    win.scene.undo()
    tabs = _tabs(win)
    assert "Plan: Level 2" in tabs and "Plan: Mezz" not in tabs       # P8 reconcile
    assert win.central_tabs.tabText(win.central_tabs.currentIndex()) == "Plan: Level 2"
