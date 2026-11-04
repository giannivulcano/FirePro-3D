"""Seam fix item 5: a plan rename retargets the sheet viewports bound to it (D9, D10)."""
import json
import os

import pytest
from PyQt6.QtCore import QRectF

from firepro3d.assets import system_blocks_path
from firepro3d.block_library import load_block_file
from firepro3d.level_widget import _COL_NAME
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import PaperScene, SheetViewData
from firepro3d.system_blocks import NOTE_BLOCK_ID
from tests.test_note_ribbon import main_window  # noqa: F401  (module MainWindow fixture)
from tests.test_note_view_scope import CROP, SCALE, _ink_in_box, _paint

L1, L2 = "plan:Plan: Level 1", "plan:Plan: Level 2"


@pytest.fixture
def win(main_window):
    scene, lm = main_window.scene, main_window.level_mgr
    scene.register_block_definition(load_block_file(
        os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
    if lm.get("Level 2") is None:
        lm.add_level("Level 2", elevation=3000.0)
    main_window.plan_view_mgr.create("Level 2", lm)       # returns the existing one
    main_window.level_widget.populate()
    sheet = main_window.sheet_mgr.sheets[0]
    saved_views = list(sheet.sheet_views)
    yield main_window
    sheet.sheet_views[:] = saved_views
    for inst in [i for i in scene._block_instances if i.note]:
        scene.remove_block_instance(inst)
    if lm.get("Mezz") is not None:                      # leave the shared window as found
        main_window.level_widget.table.item(_row(main_window.level_widget, "Mezz"),
                                            _COL_NAME).setText("Level 2")


def _row(widget, name):
    return next(r for r in range(widget.table.rowCount())
                if widget.table.item(r, _COL_NAME).text() == name)


def _note(scene, level, view, pos):
    inst = scene.place_block_instance(NOTE_BLOCK_ID, pos, level=level, note={
        "view": view, "wrap_width_mm": 40.0, "box_height_mm": 8.0})
    inst.set_attributes({"Text": "MMMM"})
    return inst


def _setup(win):
    scene = win.scene
    scene.active_view_key, scene.active_level = L1, "Level 1"      # on screen: Plan L1
    win.level_mgr.apply_to_scene(scene, "Level 1")
    mine = _note(scene, "Level 2", L2, (200.0, 200.0))
    other = _note(scene, "Level 1", L1, (200.0, 500.0))
    sheet = win.sheet_mgr.sheets[0]
    sv = SheetViewData("plan", "Plan: Level 2", "V", SCALE, 10, 10,
                       CROP.width() * SCALE, CROP.height() * SCALE)
    sv.crop_rect = QRectF(CROP)
    sheet.sheet_views.append(sv)
    return scene, sheet, sv, mine, other


def _check_viewport(win, sheet, sv, mine, other):
    paper = PaperScene(sheet, win._view_resolver)
    vp = paper.add_viewport(sv)
    img = _paint(vp)
    assert _ink_in_box(img, mine, vp) > 40              # this plan's note drew
    assert _ink_in_box(img, other, vp) == 0             # the on-screen plan's note did not


def test_a_plan_rename_retargets_the_viewport_and_it_still_shows_only_its_notes(win):
    scene, sheet, sv, mine, other = _setup(win)
    _check_viewport(win, sheet, sv, mine, other)        # before: the baseline paints right
    w = win.level_widget
    w.table.item(_row(w, "Level 2"), _COL_NAME).setText("Mezz")
    assert sv.source_view_name == "Plan: Mezz"
    assert mine.note["view"] == "plan:Plan: Mezz"
    _check_viewport(win, sheet, sv, mine, other)        # after the rename: still its notes only


def test_undoing_the_rename_retargets_the_viewport_back(win):
    scene, sheet, sv, mine, other = _setup(win)
    scene.push_undo_state()
    w = win.level_widget
    w.table.item(_row(w, "Level 2"), _COL_NAME).setText("Mezz")
    scene.undo()                                        # levels, plan views and note keys jump back
    assert win.plan_view_mgr.get("Plan: Level 2") is not None
    back = [i for i in scene._block_instances if i.note and i.level == "Level 2"][0]
    assert back.note["view"] == L2
    assert sv.source_view_name == "Plan: Level 2"       # sheets are outside the model undo: follow
    _check_viewport(win, sheet, sv, back,
                    next(i for i in scene._block_instances if i.note and i.level == "Level 1"))
    scene.redo()                                        # and forward again
    assert sv.source_view_name == "Plan: Mezz"


def test_the_retargeted_name_survives_save_and_reload(win, tmp_path):
    scene, sheet, sv, mine, other = _setup(win)
    w = win.level_widget
    w.table.item(_row(w, "Level 2"), _COL_NAME).setText("Mezz")
    path = str(tmp_path / "r.FPD")
    assert scene.save_to_file(path)
    with open(path, encoding="utf-8") as fh:
        saved = json.load(fh)
    names = [v["source_view_name"] for s in saved["sheets"] for v in s["sheet_views"]
             if v["source_view_type"] == "plan"]
    assert "Plan: Mezz" in names and "Plan: Level 2" not in names
    back = Model_Space()
    back.load_from_file(path)
    loaded = [v.source_view_name for s in back._sheets for v in s.sheet_views
              if v.source_view_type == "plan"]
    assert "Plan: Mezz" in loaded
    assert [i.note["view"] for i in back._block_instances if i.note
            and i.level == "Mezz"] == ["plan:Plan: Mezz"]


# -- the undo / redo direction is derived from the restore, not remembered ------------

def _vp(sheet, name):
    sv = SheetViewData("plan", name, "V", SCALE, 0, 0, 10, 10)
    sheet.sheet_views.append(sv)
    return sv


def _rename(win, old, new):
    w = win.level_widget
    w.table.item(_row(w, old), _COL_NAME).setText(new)


def test_a_rename_chain_follows_undo_and_redo(win):
    sheet = win.sheet_mgr.sheets[0]
    sv = _vp(sheet, "Plan: Level 2")
    _rename(win, "Level 2", "B")
    _rename(win, "B", "C")
    assert sv.source_view_name == "Plan: C"
    win.scene.undo()
    assert sv.source_view_name == "Plan: B"
    win.scene.undo()
    assert sv.source_view_name == "Plan: Level 2"
    win.scene.redo()
    assert sv.source_view_name == "Plan: B"
    win.scene.redo()
    assert sv.source_view_name == "Plan: C"
    _rename(win, "C", "Level 2")                        # leave the shared window as found


def test_a_name_swap_by_three_renames_follows_undo_and_redo(win):
    sheet = win.sheet_mgr.sheets[0]
    a, b = _vp(sheet, "Plan: Level 1"), _vp(sheet, "Plan: Level 2")
    _rename(win, "Level 2", "Tmp")
    _rename(win, "Level 1", "Level 2")
    _rename(win, "Tmp", "Level 1")
    assert (a.source_view_name, b.source_view_name) == ("Plan: Level 2", "Plan: Level 1")
    for _ in range(3):
        win.scene.undo()
    assert (a.source_view_name, b.source_view_name) == ("Plan: Level 1", "Plan: Level 2")
    for _ in range(3):
        win.scene.redo()
    assert (a.source_view_name, b.source_view_name) == ("Plan: Level 2", "Plan: Level 1")
    for _ in range(3):
        win.scene.undo()                                # leave the shared window as found


def test_a_viewport_bound_to_a_freed_name_is_not_moved_by_undoing_the_create(win):
    scene, lm = win.scene, win.level_mgr
    _rename(win, "Level 2", "B")
    lm.add_level("Level 2", elevation=9000.0)           # a NEW level takes the freed name
    win.plan_view_mgr.create("Level 2", lm)
    scene.push_undo_state()
    sv = _vp(win.sheet_mgr.sheets[0], "Plan: Level 2")
    scene.undo()                                        # undo the create: not a rename
    assert win.plan_view_mgr.get("Plan: Level 2") is None
    assert sv.source_view_name == "Plan: Level 2"       # stays, unresolved; NOT moved to B
    scene.undo()                                        # and the rename itself, to leave it clean


def test_a_level_delete_and_its_undo_leave_the_viewport_name_alone(win, monkeypatch):
    from firepro3d import level_widget as lw_mod
    monkeypatch.setattr(lw_mod, "themed_confirm", lambda *a, **k: True)
    sv = _vp(win.sheet_mgr.sheets[0], "Plan: Level 2")
    w = win.level_widget
    w.table.selectRow(_row(w, "Level 2"))
    w._delete_level()
    assert sv.source_view_name == "Plan: Level 2"       # as at base: unresolved while it is gone
    assert win.plan_view_mgr.get("Plan: Level 2") is None
    win.scene.undo()
    assert sv.source_view_name == "Plan: Level 2"
    assert win.plan_view_mgr.get("Plan: Level 2") is not None      # resolves again


def test_a_rename_in_one_project_does_not_touch_the_next_project(win):
    _rename(win, "Level 2", "Mezz")
    win._modified = False
    win.new_file()
    sheet = win.sheet_mgr.sheets[0]
    sv = _vp(sheet, "Plan: Level 2")                    # project 2: no such plan view yet
    assert win.plan_view_mgr.get("Plan: Level 2") is None
    lm = win.level_mgr
    lm.add_level("Probe", elevation=12000.0)
    win.scene.push_undo_state()
    win.scene.undo()                                    # an unrelated level undo
    assert sv.source_view_name == "Plan: Level 2"       # not re-pointed to Mezz
