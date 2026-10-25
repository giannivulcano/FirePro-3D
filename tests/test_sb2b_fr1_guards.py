"""SB2b FR1 -- fix-round guards: Gridline Renumber scope, level resolver, level-number load,
release-hold safety, letter labels, and the missing creation-site / panel / Renumber guards."""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import gridline as gl_mod
from firepro3d import marks
from firepro3d.gridline import GridlineItem
from firepro3d.level_manager import LevelManager
from firepro3d.property_manager import PropertyManager
from firepro3d.renumber_dialog import RenumberDialog
from firepro3d.room import Room
from firepro3d.sprinkler import Sprinkler
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening


# ------------------------------------------------------------------ helpers

def _plan(scene, cat, scope, level=None, restart=False, keep=False):
    return marks.renumber_plan(scene, cat, scope, level,
                               restart_per_level=restart, keep_order=keep)


def _gridlines(scene):
    out = {}
    for p1, p2, lab in ((QPointF(5000, 0), QPointF(5000, 9000), "X"),
                        (QPointF(0, 0), QPointF(0, 9000), "Y"),
                        (QPointF(-1000, 8000), QPointF(9000, 8000), "Q"),
                        (QPointF(-1000, 1000), QPointF(9000, 1000), "R")):
        g = GridlineItem(p1, p2, lab)
        scene._register_gridline(g)
        out[lab] = g
    return out


def _door_on(scene, wall, x, level=None):
    op = WallOpening(wall, feature_id="door_914", offset_along=x)
    op.level = level or wall.level
    wall.openings.append(op)
    scene.addItem(op)
    return op


def _wall(scene, y=0.0, level=None):
    w = WallSegment(QPointF(0, y), QPointF(9000, y), thickness_mm=200.0)
    w.level = level or scene.active_level
    scene.addItem(w)
    scene._walls.append(w)
    return w


# ------------------------------------------------------------------ A: Gridline Renumber is whole-project

def test_gridline_category_forces_whole_project_scope_in_the_dialog(qapp, shown_model_view):
    view, scene = shown_model_view
    g = _gridlines(scene)
    g["X"].setSelected(True)
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_scope("selected")
    assert dlg._scope()[0] == "selected"
    dlg.set_category("Gridline")
    assert not dlg._r_selected.isEnabled() and not dlg._r_level.isEnabled()
    assert dlg._r_project.isChecked() and dlg._scope() == ("project", None)
    assert len(dlg.current_mapping()) == 4           # every gridline, not just the selected one
    dlg.set_category("Door")
    assert dlg._r_selected.isEnabled() and dlg._r_level.isEnabled()


def test_gridline_plan_ignores_selected_scope(qapp, shown_model_view):
    view, scene = shown_model_view
    g = _gridlines(scene)
    g["X"].setSelected(True)
    mapping = _plan(scene, "Gridline", "selected")
    assert {lab: mapping[gl] for lab, gl in g.items()} == {"Y": "1", "X": "2", "Q": "A", "R": "B"}
    assert len(set(mapping.values())) == 4


# ------------------------------------------------------------------ B: unknown level gets its own order

def test_unknown_level_element_does_not_collide_with_lowest_level(qapp, shown_model_view):
    view, scene = shown_model_view
    w_low = _wall(scene, 0.0, "Level 1")
    w_ghost = _wall(scene, 2000.0, "Ghost Level")        # not in the LevelManager
    ops = [_door_on(scene, w_low, 1000), _door_on(scene, w_low, 5000),
           _door_on(scene, w_ghost, 1000), _door_on(scene, w_ghost, 5000)]
    for o in ops:
        marks.set_mark(o, "")
    mapping = _plan(scene, "Door", "project")
    assert sorted(mapping.values(), key=lambda m: int(m[1:])) == ["D1", "D2", "D3", "D4"]
    assert [mapping[o] for o in ops[:2]] == ["D1", "D2"]       # known levels first


# ------------------------------------------------------------------ C: blank gridline labels are not duplicates

def test_blank_gridline_labels_are_not_duplicates(qapp, shown_model_view):
    view, scene = shown_model_view
    a = GridlineItem(QPointF(0, 0), QPointF(0, 9000), "")
    b = GridlineItem(QPointF(1000, 0), QPointF(1000, 9000), "")
    assert gl_mod.check_duplicate_labels([a, b]) == set()
    gl_mod.apply_duplicate_warnings([a, b])
    assert a.bubble1.pen().color().name() != "#ff8800"            # no orange warning
    c = GridlineItem(QPointF(2000, 0), QPointF(2000, 9000), "1")
    d = GridlineItem(QPointF(3000, 0), QPointF(3000, 9000), "1")
    assert gl_mod.check_duplicate_labels([a, b, c, d]) == {c, d}
    gl_mod.apply_duplicate_warnings([a, b, c, d])
    assert c.bubble1.pen().color().name() == "#ff8800"
    assert a.bubble1.pen().color().name() != "#ff8800"


# ------------------------------------------------------------------ D: one level resolver

def test_pipe_level_number_and_level_token_agree(qapp, shown_model_view):
    from firepro3d.element_params import host_values
    view, scene = shown_model_view
    lm = scene._level_manager
    lm.add_level("Level 3", 6000.0).number = 3
    n1 = scene.add_node(0, 0)
    n2 = scene.add_node(2000, 0)
    n1.level = "Level 3"
    n2.level = "Level 3"
    pipe = scene.add_pipe(n1, n2)
    pipe.level = ""                                        # the pipe's own level is unset
    assert marks.item_level_name(pipe) == "Level 3"
    assert marks.level_number_of(scene, pipe) == 3
    assert host_values(pipe)["Level.Number"].raw == 3
    scene.mark_patterns["Pipe"] = "{level}P{n}"
    other = scene.add_pipe(n2, scene.add_node(4000, 0))
    other.level = ""
    marks.mint(scene, other)
    assert marks.get_mark(other) == "3P1"


# ------------------------------------------------------------------ E: Level.number survives load

def test_all_zero_numbers_survive_a_round_trip_and_old_payload_numbers_by_elevation():
    lm = LevelManager()
    for lvl in lm.levels:
        lvl.number = 0
    saved = lm.to_list()
    lm2 = LevelManager()
    lm2.from_list(saved)
    assert [l.number for l in lm2.levels] == [0, 0, 0]
    old = [{k: v for k, v in d.items() if k != "number"} for d in saved]
    lm3 = LevelManager()
    lm3.from_list(old)
    assert sorted((l.elevation, l.number) for l in lm3.levels) == [
        (0.0, 1), (3048.0, 2), (6096.0, 3)]


def test_all_zero_numbers_survive_undo(qapp, shown_model_view):
    view, scene = shown_model_view
    lm = scene._level_manager
    for lvl in lm.levels:
        lvl.number = 0
    scene.push_undo_state()
    scene.push_undo_state()
    scene.undo()
    assert [l.number for l in scene._level_manager.levels] == [0] * len(lm.levels)


# ------------------------------------------------------------------ F: no-op assign pushes nothing

def test_assign_selection_with_no_change_pushes_no_undo_step(qapp, shown_model_view):
    from firepro3d.level_widget import LevelWidget
    view, scene = shown_model_view
    w = _wall(scene, 0.0, "Level 1")
    scene.active_level = "Level 1"
    scene.push_undo_state()
    widget = LevelWidget(scene._level_manager, scene)
    w.setSelected(True)
    depth = len(scene._undo_stack)
    widget._assign_selection()
    assert len(scene._undo_stack) == depth


# ------------------------------------------------------------------ G: release does not mask the caller's exception

def test_release_in_finally_does_not_mask_the_original_exception(qapp, shown_model_view, monkeypatch):
    view, scene = shown_model_view

    def _boom(_scene):
        raise ValueError("refresh failed")
    monkeypatch.setattr(marks, "refresh_duplicates", _boom)
    with pytest.raises(KeyError):
        marks.hold_duplicate_refresh(scene)
        try:
            marks.request_duplicate_refresh(scene)
            raise KeyError("original")
        finally:
            marks.release_duplicate_refresh(scene)


# ------------------------------------------------------------------ H: dialog with no levels

def test_dialog_on_a_scene_without_levels_does_not_crash(qapp, shown_model_view):
    view, scene = shown_model_view
    _door_on(scene, _wall(scene), 1000)
    scene._level_manager._levels = []
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    assert dlg._level.count() == 0
    dlg.set_scope("level")
    dlg._on_level_picked(0)
    assert dlg._scope() == ("project", None)
    dlg.current_mapping()
    scene._level_manager = None
    dlg2 = RenumberDialog(scene, parent=None)
    dlg2.set_category("Door")
    dlg2.set_scope("level")
    assert dlg2.table_rows() is not None


def test_level_picked_refreshes_once(qapp, shown_model_view):
    view, scene = shown_model_view
    scene._level_manager.add_level("Level 2", 3000.0)
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    n = []
    orig = dlg._refresh
    dlg._refresh = lambda: (n.append(1), orig())[1]
    dlg._on_level_picked(1)
    assert len(n) == 1


# ------------------------------------------------------------------ I: _open_renumber refreshes the panel once

@pytest.fixture(scope="module")
def _window(qapp):
    import main as _main_module
    from firepro3d import snap_engine
    from firepro3d.view_3d import View3D
    from tests._mainwindow_helpers import dispose_main_window
    _main_module.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = _main_module.MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    dispose_main_window(win)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def test_open_renumber_rebuilds_the_panel_once_and_shows_new_marks(qapp, _window, monkeypatch):
    win = _window
    scene = win.scene
    w = _wall(scene)
    a, b = _door_on(scene, w, 1000), _door_on(scene, w, 5000)
    marks.set_mark(a, "D7")
    marks.set_mark(b, "D9")
    scene.clearSelection()
    b.setSelected(True)
    calls = []
    orig = win.prop_manager.show_properties
    monkeypatch.setattr(win.prop_manager, "show_properties",
                        lambda items, *a_, **k: (calls.append(1), orig(items, *a_, **k))[1])
    # requestPropertyUpdate was connected to the original bound method; reconnect to the spy
    scene.requestPropertyUpdate.disconnect(orig)
    scene.requestPropertyUpdate.connect(win.prop_manager.show_properties)

    def _exec_accept(self):
        self.accept()
        return 1
    monkeypatch.setattr(RenumberDialog, "exec", _exec_accept)
    try:
        win._open_renumber()
    finally:
        scene.requestPropertyUpdate.disconnect(win.prop_manager.show_properties)
        scene.requestPropertyUpdate.connect(orig)
    assert marks.get_mark(b) == "D2"
    assert len(calls) == 1
    assert win.prop_manager._prop_widgets["Mark"].text() == "D2"
    # Cancel leaves the panel as it was
    monkeypatch.setattr(RenumberDialog, "exec", lambda self: 0)
    win._open_renumber()
    assert win.prop_manager._prop_widgets["Mark"].text() == "D2"


# ------------------------------------------------------------------ J: letter labels

@pytest.mark.parametrize("idx,label", [(0, "A"), (25, "Z"), (26, "AA"), (51, "AZ"), (52, "BA"),
                                       (701, "ZZ"), (702, "AAA"), (703, "AAB")])
def test_letter_label_is_bijective_base_26(idx, label):
    assert marks.letter_label(idx) == label
    assert gl_mod._label_to_letter_idx(label) == idx


def test_gridline_auto_letters_use_the_same_sequence():
    gl_mod.reset_grid_counters()
    try:
        got = [gl_mod._next_v_label() for _ in range(704)]
    finally:
        gl_mod.reset_grid_counters()
    assert got == [marks.letter_label(i) for i in range(704)]
    assert got[-2:] == ["AAA", "AAB"]


# ------------------------------------------------------------------ K: creation-site guards

def _populate(scene):
    """A wall with a door, and a pipe whose one node carries a sprinkler."""
    w = _wall(scene, 0.0)
    marks.mint(scene, w)
    d = _door_on(scene, w, 1000)
    marks.mint(scene, d)
    n1 = scene.add_node(0, 3000)
    n2 = scene.add_node(2000, 3000)
    pipe = scene.add_pipe(n1, n2)
    spr = scene.add_sprinkler(n1, Sprinkler(None))
    return w, d, n1, n2, pipe, spr


def _all_marks(scene):
    return {c: sorted(marks.get_mark(i) for i in marks.items_of_category(scene, c))
            for c in ("Wall", "Door", "Pipe", "Sprinkler")}


def test_populate_baseline(qapp, shown_model_view):
    view, scene = shown_model_view
    _populate(scene)
    assert _all_marks(scene) == {"Wall": ["WL1"], "Door": ["D1"], "Pipe": ["P1"], "Sprinkler": ["S1"]}


def _assert_level_copy_marks(scene):
    """Wall + door copies mint the next Mark. Pipe / sprinkler copies are NOT created
    on a level copy (filed node-level bug: the pasted node keeps the source z and
    reuses the original), so only the no-collision invariant holds for them."""
    got = _all_marks(scene)
    assert got["Wall"] == ["WL1", "WL2"] and got["Door"] == ["D1", "D2"]
    assert got["Pipe"] == ["P1"] and got["Sprinkler"] == ["S1"]


def test_array_copies_mint_next_marks(qapp, shown_model_view):
    from tests._snap_polish_helpers import click, move
    view, scene = shown_model_view
    w, d, n1, n2, pipe, spr = _populate(scene)
    scene.clearSelection()
    for it in (w, n1, n2, pipe):
        it.setSelected(True)
    assert scene._modify_ctl.start("array")
    click(view, QPointF(0, 0))
    move(view, QPointF(200, 0))
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Spacing").setText("20000")
    scene.dynamic_input.editor("Count").setText("2")
    scene.dynamic_input._accept()
    assert _all_marks(scene) == {"Wall": ["WL1", "WL2"], "Door": ["D1", "D2"],
                                 "Pipe": ["P1", "P2"], "Sprinkler": ["S1", "S2"]}


def test_array_count_3_refreshes_the_panel_once(qapp, shown_model_view):
    from tests._snap_polish_helpers import click, move
    view, scene = shown_model_view
    w, d, n1, n2, pipe, spr = _populate(scene)
    scene.clearSelection()
    for it in (w, n1, n2, pipe):
        it.setSelected(True)
    seen = []
    scene.requestPropertyUpdate.connect(lambda sel: seen.append(sel))
    assert scene._modify_ctl.start("array")
    click(view, QPointF(0, 0))
    move(view, QPointF(200, 0))
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Spacing").setText("20000")
    scene.dynamic_input.editor("Count").setText("3")
    n_before = len(seen)
    scene.dynamic_input._accept()
    assert len(scene._walls) == 3
    assert len(seen) - n_before == 1


def test_copy_to_level_mints_next_marks(qapp, shown_model_view):
    view, scene = shown_model_view
    w, d, n1, n2, pipe, spr = _populate(scene)
    scene._level_manager.add_level("Level 2", 3000.0)
    scene.copy_items_to_level([w, n1, n2, pipe], "Level 2")
    _assert_level_copy_marks(scene)


def test_duplicate_level_mints_next_marks(qapp, shown_model_view):
    from firepro3d.level_widget import LevelWidget
    view, scene = shown_model_view
    _populate(scene)
    lm = scene._level_manager
    widget = LevelWidget(lm, scene)
    widget.duplicateLevel.connect(scene.duplicate_level_entities)      # main.py wiring
    widget._duplicate_level_from(lm.get("Level 1"))
    _assert_level_copy_marks(scene)


def test_paste_pipe_and_sprinkler_mints(qapp, shown_model_view):
    view, scene = shown_model_view
    w, d, n1, n2, pipe, spr = _populate(scene)
    scene.clearSelection()
    for it in (n1, n2, pipe):
        it.setSelected(True)
    scene.copy_selected_items()
    scene.paste_items(QPointF(0, 6000))
    got = _all_marks(scene)
    assert got["Pipe"] == ["P1", "P2"] and got["Sprinkler"] == ["S1", "S2"]


def test_auto_populate_gives_sequential_sprinkler_marks(qapp, shown_model_view):
    from firepro3d.sprinkler_db import SprinklerRecord
    view, scene = shown_model_view
    sq = [QPointF(0, 0), QPointF(6000, 0), QPointF(6000, 4000), QPointF(0, 4000)]
    room = Room(sq)
    room.level = scene.active_level
    room._scale_manager_ref = scene.scale_manager
    scene.addItem(room)
    scene._rooms.append(room)
    rec = SprinklerRecord("t", "Tyco", "TY315", "Pendent", 5.6, 7.0, 130, 155, '1/2"')
    positions = [QPointF(1500, 1000), QPointF(4500, 1000), QPointF(3000, 3000)]
    scene.auto_populate_room(room, positions, rec, "Level 1", "Level 1", -50.8)
    assert sorted(marks.get_mark(s) for s in marks.items_of_category(scene, "Sprinkler")) == \
        ["S1", "S2", "S3"]


# ------------------------------------------------------------------ K4: multi-target panel Mark edit

def test_multi_target_mark_edit_is_one_undo_step_over_a_subset(qapp, shown_model_view):
    view, scene = shown_model_view
    w = _wall(scene)
    ds = [_door_on(scene, w, 1000 + 2000 * i) for i in range(3)]
    for i, d in enumerate(ds):
        marks.set_mark(d, ("D1", "D2", "X")[i])
    scene.push_undo_state()
    pm = PropertyManager()
    pm.show_properties(ds)
    depth = len(scene._undo_stack)
    edit = pm._prop_widgets["Mark"]
    edit.setText("X")
    edit.setModified(True)
    edit.editingFinished.emit()
    assert len(scene._undo_stack) == depth + 1
    assert [marks.get_mark(d) for d in ds] == ["X", "X", "X"]
    scene.undo()
    assert [marks.get_mark(i) for i in marks.items_of_category(scene, "Door")] == ["D1", "D2", "X"]


# ------------------------------------------------------------------ K5: Renumber sort_point paths + Gridline undo

def test_renumber_pipe_sprinkler_room_reading_order(qapp, shown_model_view):
    view, scene = shown_model_view
    # Pipes: midpoints (1000, 0) and (1000, 5000) -> upper first
    pipes = {}
    for y in (5000, 0):
        a, b = scene.add_node(0, y), scene.add_node(2000, y)
        pipes[y] = scene.add_pipe(a, b)
        marks.set_mark(pipes[y], "P9")
    m = _plan(scene, "Pipe", "project")
    assert (m[pipes[0]], m[pipes[5000]]) == ("P1", "P2")
    # Sprinklers: node positions
    sprs = {}
    for x in (4000, 500):
        n = scene.add_node(x, 9000)
        sprs[x] = scene.add_sprinkler(n, Sprinkler(None))
        marks.set_mark(sprs[x], "S9")
    m = _plan(scene, "Sprinkler", "project")
    assert (m[sprs[500]], m[sprs[4000]]) == ("S1", "S2")
    # Rooms: centroids
    rooms = {}
    for x in (8000, 0):
        r = Room([QPointF(x, 0), QPointF(x + 3000, 0), QPointF(x + 3000, 2000), QPointF(x, 2000)])
        r.level = scene.active_level
        r._scale_manager_ref = scene.scale_manager
        scene.addItem(r)
        scene._rooms.append(r)
        rooms[x] = r
        marks.set_mark(r, "9")
    m = _plan(scene, "Room", "project")
    assert (m[rooms[0]], m[rooms[8000]]) == ("101", "102")


def test_gridline_renumber_apply_then_undo_restores_labels(qapp, shown_model_view):
    view, scene = shown_model_view
    g = _gridlines(scene)
    scene.push_undo_state()
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Gridline")
    dlg.accept()
    assert sorted(marks.get_mark(x) for x in g.values()) == ["1", "2", "A", "B"]
    scene.undo()
    assert sorted(x.grid_label for x in scene._gridlines) == ["Q", "R", "X", "Y"]
