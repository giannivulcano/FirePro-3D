"""Task 8: notes follow their view through rename and delete (D10)."""
import os

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import level_widget as lw_mod
from firepro3d import note_controller as nc
from firepro3d.level_widget import _COL_NAME
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import Sheet, SheetViewData
from firepro3d.system_blocks import NOTE_BLOCK_ID
from main import MainWindow
from tests._mainwindow_helpers import dispose_main_window
from tests.test_note_view_scope import PLAN, place_note, view_fixture


# -- helpers ------------------------------------------------------------------

def test_rekey_moves_only_matching_notes(qapp):
    fx = view_fixture()
    ms = fx["ms"]
    a, b = place_note(ms, "plan:Plan: A"), place_note(ms, "plan:Plan: B")
    plain = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0))
    nc.rekey_notes(ms, "plan:Plan: A", "plan:Plan: C")
    assert (a.note["view"], b.note["view"]) == ("plan:Plan: C", "plan:Plan: B")
    assert plain.note is None


# -- detail rename ------------------------------------------------------------

def test_rename_detail_rekeys_marker_note_tab_and_viewport(qapp):
    fx = view_fixture()
    ms, det, tabs = fx["ms"], fx["det"], fx["tabs"]
    ms._sheets = [Sheet.create_default()]
    sv = SheetViewData("detail", "D1", "V", 0.1, 0, 0, 10, 10)
    other = SheetViewData("section", "D1", "V", 0.1, 0, 0, 10, 10)   # same name, other kind
    ms._sheets[0].sheet_views = [sv, other]
    det.open_detail("D1")
    ms.active_view_key = "detail:D1"
    note = place_note(ms, "detail:D1")
    assert det.rename_detail("D1", "D9") is True
    assert det.get_marker("D9").name == "D9" and det.get_marker("D1") is None
    assert note.note["view"] == "detail:D9"
    assert det._open_views["D9"]._detail_name == "D9" and "D1" not in det._open_views
    assert tabs.tabText(tabs.count() - 1) == "Detail: D9"
    assert ms.active_view_key == "detail:D9"
    assert sv.source_view_name == "D9" and other.source_view_name == "D1"


def test_rename_detail_refuses_a_taken_or_empty_name(qapp):
    fx = view_fixture()
    det = fx["det"]
    det.create_detail("D2", QRectF(0, 0, 100, 100), "Level 1")
    assert det.rename_detail("D1", "D2") is False
    assert det.rename_detail("D1", "  ") is False
    assert det.rename_detail("Nope", "D7") is False
    assert det.get_marker("D1") is not None


def test_the_name_row_renames_through_the_manager(qapp):
    fx = view_fixture()
    ms, det = fx["ms"], fx["det"]
    note = place_note(ms, "detail:D1")
    det.get_marker("D1").set_property("Name", "Roof")
    assert det.get_marker("Roof") is not None and det.get_marker("D1") is None
    assert note.note["view"] == "detail:Roof"


def test_a_detail_rename_survives_save_and_reload(qapp, tmp_path):
    fx = view_fixture()
    ms, det = fx["ms"], fx["det"]
    ms._detail_manager = det
    place_note(ms, "detail:D1")
    det.get_marker("D1").set_property("Name", "Roof")
    path = str(tmp_path / "n.FPD")
    assert ms.save_to_file(path)
    back = Model_Space()
    from firepro3d.detail_view import DetailViewManager
    from PyQt6.QtWidgets import QTabWidget
    tabs = QTabWidget()
    det2 = DetailViewManager(back, fx["lm"], back.scale_manager, tabs)
    back._detail_manager = det2
    back._level_manager = fx["lm"]
    back.load_from_file(path)
    notes = [i for i in back._block_instances if i.note]
    assert [n.note["view"] for n in notes] == ["detail:Roof"]
    assert det2.get_marker("Roof") is not None          # the view the note names exists


# -- detail delete ------------------------------------------------------------

def test_delete_detail_removes_its_notes_and_only_its_notes(qapp):
    fx = view_fixture()
    ms, det = fx["ms"], fx["det"]
    mine, keep = place_note(ms, "detail:D1"), place_note(ms, PLAN)
    det.delete_detail("D1")
    assert mine not in ms._block_instances and mine.scene() is None
    assert keep in ms._block_instances and keep.scene() is ms


def test_clear_leaves_notes_to_scene_clear(qapp):
    fx = view_fixture()
    ms, det = fx["ms"], fx["det"]
    note = place_note(ms, "detail:D1")
    det.clear()
    assert note in ms._block_instances


# -- level rename and delete through the real MainWindow ----------------------

@pytest.fixture(scope="module")
def _win(qapp):
    from firepro3d import snap_engine
    saved = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    dispose_main_window(win)
    snap_engine.SNAP_TOLERANCE_PX = saved


@pytest.fixture
def mw(_win):
    scene, lm = _win.scene, _win.level_mgr
    from firepro3d.block_library import load_block_file
    from firepro3d.assets import system_blocks_path
    scene.register_block_definition(load_block_file(
        os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
    if lm.get("Level 2") is None:
        lm.add_level("Level 2", elevation=3000.0)
        _win.plan_view_mgr.create("Level 2", lm)
    _win.level_widget.populate()
    scene.push_undo_state()
    yield _win
    for inst in [i for i in scene._block_instances if i.note]:
        scene.remove_block_instance(inst)


def _row(widget, name):
    return next(r for r in range(widget.table.rowCount())
                if widget.table.item(r, _COL_NAME).text() == name)


def _note_on_level(scene, name):
    inst = scene.place_block_instance(
        NOTE_BLOCK_ID, (0.0, 0.0), level=name,
        note={"view": f"plan:Plan: {name}", "wrap_width_mm": 40.0, "box_height_mm": 8.0})
    inst.set_attributes({"Text": "x"})
    scene.push_undo_state()
    return inst


def test_level_rename_rekeys_its_notes_and_undo_restores(mw):
    scene, w = mw.scene, mw.level_widget
    n2 = _note_on_level(scene, "Level 2")
    n1 = _note_on_level(scene, "Level 1")
    w.table.item(_row(w, "Level 2"), _COL_NAME).setText("Mezz")
    assert n2.note["view"] == "plan:Plan: Mezz" and n1.note["view"] == "plan:Plan: Level 1"
    scene.undo()                                           # the rename step restores the old key
    back = {i.level: i.note["view"] for i in scene._block_instances if i.note}
    assert back["Level 2"] == "plan:Plan: Level 2"
    w.table.item(_row(w, "Level 2"), _COL_NAME).setText("Level 2")    # leave the shared window as found
    scene.undo()


def test_level_delete_removes_its_notes_in_the_one_step_and_undo_restores(mw, monkeypatch):
    scene, w = mw.scene, mw.level_widget
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: True)
    _note_on_level(scene, "Level 2")
    keep = _note_on_level(scene, "Level 1")
    depth = len(scene._undo_stack)
    w.table.selectRow(_row(w, "Level 2"))
    w._delete_level()
    views = [i.note["view"] for i in scene._block_instances if i.note]
    assert views == ["plan:Plan: Level 1"] and keep in scene._block_instances
    assert len(scene._undo_stack) == depth + 1             # one step, notes included
    scene.undo()
    views = sorted(i.note["view"] for i in scene._block_instances if i.note)
    assert views == ["plan:Plan: Level 1", "plan:Plan: Level 2"]


# -- detail rename / delete versus the undo history (no undo step of their own) --

def _live_notes(ms):
    return [i for i in ms._block_instances if i.note]


def test_undo_past_a_detail_rename_keeps_the_note_visible_in_the_renamed_detail(qapp):
    fx = view_fixture()
    ms, det, lm = fx["ms"], fx["det"], fx["lm"]
    place_note(ms, "detail:D1")
    ms.push_undo_state()                      # state A: note under D1
    det.rename_detail("D1", "D9")
    ms.push_undo_state()                      # state B: note under D9
    place_note(ms, "detail:D9", pos=(900.0, 900.0))
    ms.push_undo_state()                      # state C
    ms.undo()                                 # back to B
    ms.undo()                                 # past the rename, to A
    ms.active_view_key, ms.active_level = "detail:D9", "Level 1"
    lm.apply_to_scene(ms, "Level 1")
    (n,) = _live_notes(ms)
    assert n.note["view"] == "detail:D9" and n.isVisible()
    ms.redo()
    ms.redo()
    lm.apply_to_scene(ms, "Level 1")
    assert [i.note["view"] for i in _live_notes(ms)] == ["detail:D9"] * 2
    assert all(i.isVisible() for i in _live_notes(ms))


def test_undo_past_a_detail_delete_brings_back_no_note_with_the_dead_key(qapp):
    fx = view_fixture()
    ms, det = fx["ms"], fx["det"]
    place_note(ms, "detail:D1")
    keep = place_note(ms, PLAN, pos=(900.0, 900.0))
    ms.push_undo_state()
    det.delete_detail("D1")
    ms.push_undo_state()
    ms.undo()
    assert [i.note["view"] for i in _live_notes(ms)] == [PLAN]
