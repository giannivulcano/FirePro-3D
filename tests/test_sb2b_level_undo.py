"""SB2b G-L1 -- every Level-manager edit is one undo step; undo restores levels, item levels,
underlay level lists, plan views and the active level."""
from PyQt6.QtCore import QPointF, Qt

from firepro3d import level_widget as lw_mod
from firepro3d.level_manager import PlanViewManager
from firepro3d.level_widget import LevelWidget, _COL_ELEV, _COL_NAME, _COL_NUM
from firepro3d.underlay import Underlay
from firepro3d.wall import WallSegment


def _setup(shown_model_view):
    view, scene = shown_model_view
    lm = scene._level_manager
    if lm.get("Level 2") is None:
        lm.add_level("Level 2", elevation=3000.0)
    lm.get("Level 2").elevation = 3000.0
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    w.level = "Level 2"
    scene.addItem(w); scene._walls.append(w)
    scene.push_undo_state()                       # seed: the state before the edit
    widget = LevelWidget(lm, scene)
    scene.levelsRestored.connect(widget.populate)            # main.py does this via _on_levels_restored
    widget.duplicateLevel.connect(scene.duplicate_level_entities)   # main.py wiring
    return view, scene, lm, widget


def _row(widget, name):
    return next(r for r in range(widget.table.rowCount())
                if widget.table.item(r, _COL_NAME).text() == name)


def _underlay(scene, levels):
    """A real DXF underlay record + batched group registered on *scene*."""
    rec = Underlay(type="dxf", path="x.dxf", levels=list(levels))
    geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "layer": "A-WALL"}]
    group, _ = scene._build_batched_underlay_group(geoms, rec)
    scene.underlays.append((rec, group))
    return rec


def test_rename_undo_redo(qapp, shown_model_view):
    view, scene, lm, widget = _setup(shown_model_view)
    depth = len(scene._undo_stack)
    widget.table.item(_row(widget, "Level 2"), _COL_NAME).setText("Mezz")
    assert len(scene._undo_stack) == depth + 1
    assert scene._walls[0].level == "Mezz"
    scene.undo()
    assert lm.get("Level 2") is not None and lm.get("Mezz") is None
    assert scene._walls[0].level == "Level 2"
    assert widget.table.item(_row(widget, "Level 2"), _COL_NAME) is not None   # widget refreshed
    scene.redo()
    assert lm.get("Mezz") is not None and scene._walls[0].level == "Mezz"


def test_elevation_and_number_each_one_step(qapp, shown_model_view):
    view, scene, lm, widget = _setup(shown_model_view)
    r = _row(widget, "Level 2")
    old_num = lm.get("Level 2").number
    widget.table.item(r, _COL_ELEV).setData(Qt.ItemDataRole.UserRole, 4000.0)   # one edit: the branch reads UserRole first
    widget.table.item(r, _COL_NUM).setText("8")
    assert lm.get("Level 2").elevation == 4000.0 and lm.get("Level 2").number == 8
    scene.undo()
    assert lm.get("Level 2").number == old_num and lm.get("Level 2").elevation == 4000.0
    scene.undo()
    assert lm.get("Level 2").elevation == 3000.0


def test_add_delete_duplicate_each_one_step(qapp, shown_model_view, monkeypatch):
    view, scene, lm, widget = _setup(shown_model_view)
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: True)
    n0 = len(lm.levels)
    widget._add_level()
    assert len(lm.levels) == n0 + 1
    scene.undo()
    assert len(lm.levels) == n0
    widget.table.selectRow(_row(widget, "Level 2"))
    widget._delete_level()
    assert lm.get("Level 2") is None and scene._walls[0].level != "Level 2"
    scene.undo()
    assert lm.get("Level 2") is not None and scene._walls[0].level == "Level 2"
    pos = scene._undo_pos                              # after an undo the stack tail is redo history
    n_levels, n_walls = len(lm.levels), len(scene._walls)
    widget._duplicate_level_from(lm.get("Level 2"))
    assert scene._undo_pos == pos + 1                   # copies + level = ONE step
    assert (len(lm.levels), len(scene._walls)) == (n_levels + 1, n_walls + 1)
    scene.undo()
    assert (len(lm.levels), len(scene._walls)) == (n_levels, n_walls)


def test_undo_restores_active_level_and_underlay_levels(qapp, shown_model_view):
    view, scene, lm, widget = _setup(shown_model_view)
    rec = _underlay(scene, ["Level 2"])
    scene.active_level = "Level 2"
    scene.push_undo_state()
    widget.table.item(_row(widget, "Level 2"), _COL_NAME).setText("Mezz")
    assert rec.levels == ["Mezz"]
    scene.undo()
    assert rec.levels == ["Level 2"] and scene.active_level == "Level 2"


def test_undo_restores_active_level_after_delete(qapp, shown_model_view, monkeypatch):
    view, scene, lm, widget = _setup(shown_model_view)
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: True)
    scene.active_level = "Level 2"
    scene.push_undo_state()
    widget.table.selectRow(_row(widget, "Level 2"))
    widget._delete_level()
    scene.active_level = "Level 1"                     # what main's activeLevelChanged handler does
    scene.undo()
    assert lm.get("Level 2") is not None and scene.active_level == "Level 2"


def test_undo_restores_plan_views(qapp, shown_model_view):
    view, scene, lm, widget = _setup(shown_model_view)
    pvm = PlanViewManager()
    scene._plan_view_manager = pvm
    pvm.create("Level 2", lm)
    scene.push_undo_state()
    pvm.rename_level("Level 2", "Mezz")                # a rename moves the plan view with it
    lm.rename_level("Level 2", "Mezz", [], scene=scene)
    scene.push_undo_state()
    assert pvm.get("Plan: Mezz") is not None
    scene.undo()
    assert pvm.get("Plan: Level 2") is not None and pvm.get("Plan: Mezz") is None
    assert lm.get("Level 2") is not None


def test_unrelated_undo_keeps_the_active_level(qapp, shown_model_view):
    view, scene, lm, widget = _setup(shown_model_view)
    scene.active_level = "Level 2"
    scene.push_undo_state()
    w2 = WallSegment(QPointF(0, 500), QPointF(1000, 500), thickness_mm=200.0)
    w2.level = "Level 2"
    scene.addItem(w2); scene._walls.append(w2)
    scene.push_undo_state()
    scene.active_level = "Level 1"                     # a view switch is not an undo step
    fired = []
    scene.levelsRestored.connect(lambda: fired.append(1))
    scene.undo()
    assert len(scene._walls) == 1
    assert scene.active_level == "Level 1" and fired == []


def test_restore_refresh_pushes_nothing_and_fires_no_edit(qapp, shown_model_view):
    """populate() is the restore's refresh: styling the active row is not an edit."""
    view, scene, lm, widget = _setup(shown_model_view)
    widget.table.item(_row(widget, "Level 2"), _COL_NAME).setText("Mezz")
    fired = []
    widget.levelsChanged.connect(lambda: fired.append(1))
    pos = scene._undo_pos
    scene.undo()                                   # levelsRestored -> widget.populate
    assert scene._undo_pos == pos - 1 and fired == []


# -- the real MainWindow wiring (main.py _on_levels_restored) -------------------

import pytest
from PyQt6.QtTest import QTest

from tests._mainwindow_helpers import dispose_main_window


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from firepro3d import snap_engine
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    import main as main_mod
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    w = main_mod.MainWindow()
    w.resize(1200, 800)
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(300)
    yield w
    dispose_main_window(w)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def test_main_window_undo_of_a_rename_refreshes_the_level_views(mw):
    win = mw
    scene, lw = win.scene, win.level_widget
    win._activate_plan_view("Level 2")
    assert scene.active_level == "Level 2"
    scene.push_undo_state()                              # the state before the edit
    lw.table.item(_row(lw, "Level 2"), _COL_NAME).setText("Mezz")
    assert scene.active_level == "Mezz"                  # main's handler followed the rename
    scene.undo()
    names = [lw.table.item(r, _COL_NAME).text() for r in range(lw.table.rowCount())]
    assert "Level 2" in names and "Mezz" not in names    # the dock widget was repopulated
    assert scene.active_level == "Level 2"
    assert win.central_tabs.tabText(win.central_tabs.currentIndex()) == "Plan: Level 2"
