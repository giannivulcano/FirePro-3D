"""Level Manager widget (view-relationships section 12.4): a sortable VIEW over a
lowest-first manager whose rows map to levels by name (not index); Add above the top;
multi-select Delete (button / Delete key / context menu) to the nearest level below in
one undo step; single-row Duplicate; no View Level combo / Levels label /
_assign_selection. Real Model_Space + LevelManager + WallSegment (shown_model_view)."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QComboBox, QLabel

from firepro3d import level_widget as lw_mod
from firepro3d.level_manager import PlanViewManager
from firepro3d.level_widget import (LevelWidget, _COL_ELEV, _COL_NAME, _COL_NUM,
                                    _TIP_DELETE, _TIP_DELETE_ALL)
from firepro3d.wall import WallSegment


def _widget(shown_model_view, *rows):
    """rows: (name, elevation_mm, number) in FILE order -> (scene, lm, shown widget)."""
    view, scene = shown_model_view
    lm = scene._level_manager
    lm.from_list([{"name": n, "elevation_mm": e, "number": k} for n, e, k in rows])
    scene._plan_view_manager = PlanViewManager()
    scene.push_undo_state()                                  # the state before any edit
    w = LevelWidget(lm, scene)
    w.duplicateLevel.connect(scene.duplicate_level_entities)   # main.py wiring
    scene.levelsRestored.connect(w.populate)                   # main.py _on_levels_restored
    w.show()
    QTest.qWaitForWindowExposed(w)
    return scene, lm, w


def _rows(w, col=_COL_NAME):
    return [w.table.item(r, col).text() for r in range(w.table.rowCount())]


def _row_of(w, name):
    return next(r for r in range(w.table.rowCount())
                if w.table.item(r, _COL_NAME).data(Qt.ItemDataRole.UserRole) == name)


def _select(w, *names):
    w.table.clearSelection()
    sm = w.table.selectionModel()
    for n in names:
        sm.select(w.table.model().index(_row_of(w, n), 0),
                  sm.SelectionFlag.Select | sm.SelectionFlag.Rows)


def _click_header(w, col):
    hdr = w.table.horizontalHeader()
    QTest.mouseClick(hdr.viewport(), Qt.MouseButton.LeftButton,
                     pos=QPoint(hdr.sectionViewportPosition(col) + 10, hdr.height() // 2))


def _wall(scene, level, y=0.0):
    wall = WallSegment(QPointF(0, y), QPointF(1000, y), thickness_mm=200.0)
    wall.level = level
    scene.addItem(wall); scene._walls.append(wall)
    return wall


def _names(lm):
    return [l.name for l in lm.levels]


def test_rows_follow_manager_order_and_a_header_click_sorts_the_view_only(shown_model_view):
    scene, lm, w = _widget(shown_model_view, ("Level 1", 0.0, 1), ("Level 2", 3048.0, 2), ("Mezz", 1524.0, 10))
    assert _names(lm) == ["Level 1", "Mezz", "Level 2"]              # stored lowest first
    assert _rows(w) == ["Level 1", "Mezz", "Level 2"]
    assert w.table.horizontalHeader().sortIndicatorSection() == _COL_ELEV   # a real sort is established at build (no stray column-0 caret)
    assert w.table.horizontalHeader().isSortIndicatorShown() is False   # populate never re-shows the native arrow (C-1)
    _click_header(w, _COL_NUM)                                        # Number asc: 1, 2, 10
    assert _rows(w) == ["Level 1", "Level 2", "Mezz"]
    _click_header(w, _COL_NUM)                                        # second click reverses
    assert _rows(w) == ["Mezz", "Level 2", "Level 1"]
    assert _names(lm) == ["Level 1", "Mezz", "Level 2"]              # the store did not move
    w.table.item(0, _COL_NAME).setText("Roof")                        # row 0 is Mezz while sorted desc
    assert lm.get("Roof") is not None and lm.get("Mezz") is None
    assert lm.get("Roof").elevation == 1524.0                         # the mapping survived the sort


def test_numeric_sort_for_number_and_elevation(shown_model_view):
    scene, lm, w = _widget(shown_model_view, ("A", 9000.0, 1), ("B", 10000.0, 10), ("C", 20000.0, 2))
    assert _rows(w) == ["A", "B", "C"]            # 9000 < 10000 (lexical text sort would put "10000.000 mm" first)
    _click_header(w, _COL_NUM)
    assert _rows(w) == ["A", "C", "B"]            # 1, 2, 10 (lexical: 1, 10, 2)
    _click_header(w, _COL_ELEV)
    assert _rows(w) == ["A", "B", "C"]


def test_add_goes_above_the_top_with_the_top_gap_and_the_next_number(shown_model_view):
    scene, lm, w = _widget(shown_model_view, ("Level 1", 0.0, 1), ("Level 2", 3048.0, 2), ("Level 3", 6096.0, 3))
    depth = len(scene._undo_stack)
    w._add_level()
    new = lm.levels[-1]
    assert (new.name, new.number, new.elevation) == ("Level 4", 4, 9144.0)       # 6096 + (6096 - 3048)
    assert _rows(w)[-1] == "Level 4" and _rows(w, _COL_ELEV)[-1] == "9144.000 mm"  # ScaleManager() default METRIC_MM
    assert [ix.row() for ix in w.table.selectionModel().selectedRows()] == [3]      # the new row is selected
    assert len(scene._undo_stack) == depth + 1


def test_add_with_a_single_level_uses_ten_feet(shown_model_view):
    scene, lm, w = _widget(shown_model_view, ("Ground", 0.0, 1))
    w._add_level()
    assert [(l.name, l.elevation) for l in lm.levels] == [("Ground", 0.0), ("Level 1", 3048.0)]


def test_elevation_edit_resorts_the_store_and_the_view(shown_model_view):
    scene, lm, w = _widget(shown_model_view, ("Level 1", 0.0, 1), ("Level 2", 3048.0, 2), ("Level 3", 6096.0, 3))
    w.table.item(_row_of(w, "Level 3"), _COL_ELEV).setData(Qt.ItemDataRole.UserRole, 100.0)
    assert _names(lm) == ["Level 1", "Level 3", "Level 2"]
    assert _rows(w) == ["Level 1", "Level 3", "Level 2"]
    assert _rows(w, _COL_ELEV) == ["0.000 mm", "100.000 mm", "3048.000 mm"]
    assert [l.number for l in lm.levels] == [1, 3, 2]                 # Numbers never auto-change


def test_rename_keeps_the_plan_view_and_emits_level_renamed(shown_model_view):
    scene, lm, w = _widget(shown_model_view, ("Ground", 0.0, 1), ("L2", 3048.0, 2))
    pv = scene._plan_view_manager.create("L2", lm)
    pv.view_depth = -123.0
    got = []
    w.levelRenamed.connect(lambda o, n: got.append((o, n)))
    w.table.item(_row_of(w, "L2"), _COL_NAME).setText("Mezz")
    assert got == [("L2", "Mezz")]
    assert scene._plan_view_manager.get("Plan: Mezz") is pv and pv.view_depth == -123.0
    assert scene._plan_view_manager.get("Plan: L2") is None


def test_multi_delete_moves_items_to_the_nearest_level_below_in_one_step(shown_model_view, monkeypatch):
    scene, lm, w = _widget(shown_model_view, ("Ground", 0.0, 1), ("Mezz", 1524.0, 2), ("L2", 3048.0, 3), ("Roof", 9144.0, 4))
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: True)
    a, b = _wall(scene, "Mezz"), _wall(scene, "Roof", y=500.0)
    pvm = scene._plan_view_manager
    pvm.create("Mezz", lm); pvm.create("Roof", lm)
    removed = []
    w.levelsRemoved.connect(lambda names: removed.append(list(names)))
    scene.push_undo_state()
    depth = len(scene._undo_stack)
    _select(w, "Mezz", "Roof")
    w._delete_level()
    assert _names(lm) == ["Ground", "L2"]
    assert (a.level, b.level) == ("Ground", "L2")                     # Mezz -> Ground, Roof -> L2
    assert pvm.get("Plan: Mezz") is None and pvm.get("Plan: Roof") is None
    assert removed == [["Mezz", "Roof"]]
    assert _rows(w) == ["Ground", "L2"]
    assert len(scene._undo_stack) == depth + 1                        # the whole selection = one step
    scene.undo()
    assert _names(lm) == ["Ground", "Mezz", "L2", "Roof"]
    assert (scene._walls[0].level, scene._walls[1].level) == ("Mezz", "Roof")
    assert pvm.get("Plan: Mezz") is not None


def test_delete_is_refused_when_the_selection_covers_every_level(shown_model_view, monkeypatch):
    scene, lm, w = _widget(shown_model_view, ("Ground", 0.0, 1), ("Roof", 3048.0, 2))
    asked = []
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: asked.append(1) or True)
    _select(w, "Ground")
    assert w.del_btn.isEnabled() and w.del_btn.toolTip() == _TIP_DELETE
    _select(w, "Ground", "Roof")
    assert not w.del_btn.isEnabled() and w.del_btn.toolTip() == _TIP_DELETE_ALL
    delete = next(a for a in w._build_context_menu().actions() if a.text() == "Delete Levels")
    assert not delete.isEnabled() and delete.toolTip() == _TIP_DELETE_ALL
    depth = len(scene._undo_stack)
    w._delete_level()
    QTest.keyClick(w.table, Qt.Key.Key_Delete)
    assert len(lm.levels) == 2 and asked == [] and len(scene._undo_stack) == depth


def test_delete_key_and_context_menu_drive_the_same_actions(shown_model_view, monkeypatch):
    scene, lm, w = _widget(shown_model_view, ("Ground", 0.0, 1), ("Mezz", 1524.0, 2), ("Roof", 3048.0, 3))
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: True)
    w.table.setFocus()
    _select(w, "Mezz")
    QTest.keyClick(w.table, Qt.Key.Key_Delete)
    assert _names(lm) == ["Ground", "Roof"]
    menu = w._build_context_menu()
    assert [a.text() for a in menu.actions()] == ["Add Level", "Delete Level", "Duplicate Level"]   # section 12.4 order
    next(a for a in menu.actions() if a.text() == "Add Level").trigger()
    assert _names(lm) == ["Ground", "Roof", "Level 1"]                # above Roof: 3048 + (3048 - 0)
    _select(w, "Roof")
    next(a for a in w._build_context_menu().actions() if a.text() == "Delete Level").trigger()
    assert _names(lm) == ["Ground", "Level 1"]


def test_duplicate_needs_a_single_row_and_keeps_the_source_elevation(shown_model_view):
    scene, lm, w = _widget(shown_model_view, ("Ground", 0.0, 1), ("L2", 3048.0, 2))
    _wall(scene, "L2")
    _select(w, "Ground", "L2")
    assert not w.dup_btn.isEnabled()
    n = len(lm.levels)
    w._duplicate_level()                                              # no-op with two rows selected
    assert len(lm.levels) == n and len(scene._walls) == 1
    _select(w, "L2")
    assert w.dup_btn.isEnabled()
    depth = len(scene._undo_stack)
    w._duplicate_level()
    new = lm.levels[-1]
    assert new.name == "Level 1" and new.elevation == 3048.0 and len(scene._walls) == 2
    assert [wl.level for wl in scene._walls] == ["L2", "Level 1"]
    assert len(scene._undo_stack) == depth + 1                        # level + copies = one step


def test_combo_label_and_assign_selection_are_gone_and_the_active_row_is_bold(shown_model_view):
    scene, lm, w = _widget(shown_model_view, ("Ground", 0.0, 1), ("Roof", 3048.0, 2))
    assert w.findChildren(QComboBox) == []
    assert w.findChildren(QLabel) == []
    assert not hasattr(w, "_assign_selection")
    scene.active_level = "Roof"
    w.populate()
    assert w.table.item(_row_of(w, "Roof"), _COL_NAME).font().bold()
    assert not w.table.item(_row_of(w, "Ground"), _COL_NAME).font().bold()


def test_name_header_sort_is_case_insensitive(shown_model_view):
    """P13: the Name view sort ignores case (mockup l.name.toLowerCase())."""
    scene, lm, w = _widget(shown_model_view, ("alpha", 0.0, 1), ("Beta", 3048.0, 2), ("gamma", 6096.0, 3))
    _click_header(w, _COL_NAME)
    assert _rows(w) == ["alpha", "Beta", "gamma"]          # a case-sensitive sort gives Beta, alpha, gamma
    _click_header(w, _COL_NAME)
    assert _rows(w) == ["gamma", "Beta", "alpha"]
    assert _names(lm) == ["alpha", "Beta", "gamma"]        # view only


def test_delete_strips_the_level_from_underlay_records(shown_model_view, monkeypatch):
    """P12: underlay records (not scene items) lose the deleted name (as-built section 12.2)."""
    from firepro3d.underlay import Underlay
    scene, lm, w = _widget(shown_model_view, ("Ground", 0.0, 1), ("Mezz", 1524.0, 2), ("Roof", 3048.0, 3))
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: True)
    rec = Underlay(type="dxf", path="x.dxf", levels=["Ground", "Mezz"])
    geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "layer": "A-WALL"}]
    group, _ = scene._build_batched_underlay_group(geoms, rec)
    scene.underlays.append((rec, group))
    _select(w, "Mezz")
    w._delete_level()
    assert rec.levels == ["Ground"]


def test_add_number_with_custom_numbers_follows_the_count_rule(shown_model_view):
    """P9 (as-proposed, pending ratification): Number = 1 + count of levels at or below
    (element-parameters M14), which the mockup's max+1 would make 10 here."""
    scene, lm, w = _widget(shown_model_view, ("A", 0.0, 7), ("B", 3000.0, 9))
    w._add_level()
    assert [(l.name, l.number, l.elevation) for l in lm.levels] == [("A", 7, 0.0), ("B", 9, 3000.0), ("Level 1", 3, 6000.0)]
