"""SB3 MainWindow guards (module `mw` from test_constraint_pick_ribbon; runs in its
OWN pytest process): AC5 the load notice reaches the status bar through the real
window; AC9 Annotation / Marks pane OK marks the project modified, no undo step."""
import shutil

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d.assets import system_blocks_path
from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.room import Room
from firepro3d.settings.project_settings_dialog import ProjectSettingsDialog
from firepro3d.system_blocks import SYSTEM_DEFAULTS
from tests.test_constraint_pick_ribbon import mw  # noqa: F401


def _room(scene, name):
    r = Room(boundary=[QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000), QPointF(0, 2000)])
    r.name = name
    r.level = scene.active_level
    r._scale_manager_ref = scene.scale_manager
    scene.addItem(r)
    scene._rooms.append(r)
    r._update_label()
    return r


def _tag_def(ms, name):
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": "@[Name]", "x": 0.0,
                                         "y": 0.0, "height_mm": 3.0}])
    d.scale_mode = "annotative"
    d.host_category = "Room"
    d.attributes = [normalise_attr({"key": "Name", "source": "host", "host_key": "Name"})]
    ms.register_block_definition(d)
    return d


def _undo_state(ms):
    return (len(ms._undo_stack), ms._undo_pos)


def test_ac5_load_notice_reaches_the_status_bar(mw, qapp, tmp_path):
    """The Q6 notice reaches the MainWindow status bar through the real scene
    (``Model_Space._show_status`` must skip the hidden startup ``Model_View``,
    whose ``window()`` is itself: SB3 G4 fix, 2026-10-28)."""
    folder = tmp_path / "sys" / "Tags"
    folder.mkdir(parents=True)
    shutil.copy(system_blocks_path("Tags", "RoomTag.fpdb"), folder / "RoomTag.fpdb")
    block_library.set_system_root(str(tmp_path / "sys"))
    ms = mw.scene
    _room(ms, "Office")
    ms.annotation_defaults["Room"] = "missing-block-id"
    f = tmp_path / "n.fpd"
    assert ms.save_to_file(str(f))
    ms.load_from_file(str(f))
    qapp.processEvents()
    msg = mw.statusBar().currentMessage()
    assert "missing-block-id" in msg and "RoomTag" in msg                    # the last message, not "Loaded from"
    assert ms.annotation_block("Room").id == SYSTEM_DEFAULTS["Room"]
    assert ms.annotation_defaults["Room"] == "missing-block-id"
    assert ms._rooms[0]._tag.paints()


def test_ac9_pane_ok_marks_the_project_modified_without_an_undo_step(mw, qapp):
    ms = mw.scene
    d = _tag_def(ms, "A")
    d2 = _tag_def(ms, "B")
    ms.annotation_defaults["Room"] = d.id
    mw._modified = False
    before = _undo_state(ms)
    dlg = ProjectSettingsDialog(scene=ms, get_info=mw._get_project_info, set_info=mw._set_project_info,
                                on_changed=mw._on_project_settings_changed, parent=mw)
    combo = dlg._panes["annotation"]._combos["Room"]
    combo.setCurrentIndex(combo.findData(d2.id))
    dlg._on_ok()
    assert mw._modified is True and ms.annotation_defaults["Room"] == d2.id
    assert _undo_state(ms) == before
    mw._modified = False
    dlg2 = ProjectSettingsDialog(scene=ms, get_info=mw._get_project_info, set_info=mw._set_project_info,
                                 on_changed=mw._on_project_settings_changed, parent=mw)
    t = dlg2._panes["marks"]._table
    r = next(r for r in range(t.rowCount()) if t.item(r, 0).text() == "Door")
    t.item(r, 1).setText("DR-{n:02}")
    dlg2._on_ok()
    assert mw._modified is True and ms.mark_patterns["Door"] == "DR-{n:02}"
    assert _undo_state(ms) == before


def test_ac9_each_pane_apply_alone_marks_the_project_modified(mw, qapp):
    """The dialog-level OK also runs the Units pane, whose apply always calls
    on_changed -- so the OK test above cannot tell whether the Annotation / Marks
    panes are wired. Applying each pane alone can (RED proof: on_changed=None)."""
    ms = mw.scene
    d = _tag_def(ms, "C")
    d2 = _tag_def(ms, "D")
    ms.annotation_defaults["Room"] = d.id
    dlg = ProjectSettingsDialog(scene=ms, get_info=mw._get_project_info, set_info=mw._set_project_info,
                                on_changed=mw._on_project_settings_changed, parent=mw)
    mw._modified = False
    pane = dlg._panes["annotation"]
    pane._combos["Room"].setCurrentIndex(pane._combos["Room"].findData(d2.id))
    pane.apply()
    assert mw._modified is True and ms.annotation_defaults["Room"] == d2.id
    mw._modified = False
    marks = dlg._panes["marks"]
    t = marks._table
    r = next(r for r in range(t.rowCount()) if t.item(r, 0).text() == "Pipe")
    t.item(r, 1).setText("PP-{n:02}")
    marks.apply()
    assert mw._modified is True and ms.mark_patterns["Pipe"] == "PP-{n:02}"
