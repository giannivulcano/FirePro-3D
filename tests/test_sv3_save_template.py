"""SV3 Tasks 4-7 -- Save as Template: dialog toggle, editor verb, collision
loop, ribbon button, browser verb (schematics.md D-S6 / D-S11c / D-S11d /
D-S14 / D-S16; concept SD5; guard G4).
"""
from __future__ import annotations

import json
import os

import pytest
from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtWidgets import QTabWidget

from firepro3d import app_data, block_library as bl
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import (BlockEditorManager, BlockSaveDialog,
                                    schematic_series_for)
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _line():
    return LineItem(QPointF(0, 0), QPointF(100, 0))


@pytest.fixture()
def env(qapp):
    ms = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, ms)
    yield ms, tabs, mgr
    for w in list(mgr.open_editors()):
        mgr.close(w)
    tabs.deleteLater()


def _plain(ms, name="Sym"):
    d = BlockDefinition.new(
        name=name, library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()])
    ms.register_block_definition(d)
    ms.push_undo_state()
    return d


def _fake_exec(name, *, template=False, series=None):
    def _exec(dlg):
        dlg.name_edit.setText(name)
        if series is not None:
            dlg.series_sel.set_items([series], current=series)
        if template:
            dlg.save_template_cb.setChecked(True)
        dlg._on_save()
        return dlg.result()
    return _exec


def _open_schematic_with_nested(env):
    """A Schematic editor holding a line + one nested plain block."""
    ms, _tabs, mgr = env
    plain = _plain(ms)
    w = mgr.open_new(kind="schematic")
    w._add_primitive(_line())
    w.editor_scene.place_block_instance(plain.id, (50.0, 20.0))
    w.editor_scene.push_undo_state()
    return w, plain


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# -- Task 4: dialog toggle ----------------------------------------------------

def test_schematic_dialog_has_template_toggle_default_off(qapp):
    dlg = BlockSaveDialog(kind="schematic")
    assert dlg.save_template_cb.isChecked() is False
    assert dlg.save_template_cb.text() == "Also save as Template"
    assert dlg.save_template_cb.toolTip()
    assert dlg.values()["save_template"] is False
    blk = BlockSaveDialog(library_tree={"L": ["S"]})
    assert blk.save_template_cb is None
    assert blk.values()["save_template"] is False


def test_template_toggle_is_remembered(qapp):
    dlg = BlockSaveDialog(kind="schematic")
    dlg.name_edit.setText("Riser")
    dlg.save_template_cb.setChecked(True)
    dlg._on_save()
    assert QSettings("GV", "FirePro3D").value(
        "BlockEditor/save_schematic_template", False, type=bool) is True
    assert BlockSaveDialog(kind="schematic").save_template_cb.isChecked() is True
    # The block toggle's own memory is untouched by a schematic save.
    assert BlockSaveDialog(library_tree={"L": ["S"]}).save_to_library_cb.isChecked() is True


def test_dialog_template_collision_three_way(qapp, tmp_path, monkeypatch):
    root = str(tmp_path)
    other = BlockDefinition.new(name="Riser", library="", series="", origin=(0.0, 0.0),
                                primitives=[_line().to_dict()], kind="schematic")
    bl.save_to_library(other, root=root)
    from firepro3d import themed_message
    choices = []
    choices_iter = []

    def _choice(parent, title, message, buttons, kind=None):
        choices.append(message)
        return choices_iter.pop(0)

    monkeypatch.setattr(themed_message, "themed_choice", _choice)
    choices_iter[:] = ["cancel"]
    dlg = BlockSaveDialog(kind="schematic", root=root, collision_id="me")
    dlg.name_edit.setText("Riser")
    dlg.save_template_cb.setChecked(True)
    dlg._on_save()
    assert dlg.result() == dlg.DialogCode.Rejected
    assert dlg.error_label.isHidden()
    assert "already saved as Riser" in choices[-1]
    choices_iter[:] = ["rename"]
    dlg = BlockSaveDialog(kind="schematic", root=root, collision_id="me")
    dlg.name_edit.setText("Riser")
    dlg.save_template_cb.setChecked(True)
    dlg._on_save()
    assert dlg.result() != dlg.DialogCode.Accepted                 # still open
    assert dlg.name_edit.selectedText() == "Riser"
    assert dlg.error_label.isVisibleTo(dlg) and "Riser" in dlg.error_label.text()
    choices_iter[:] = ["overwrite"]
    dlg = BlockSaveDialog(kind="schematic", root=root, collision_id="me")
    dlg.name_edit.setText("Riser")
    dlg.save_template_cb.setChecked(True)
    dlg._on_save()
    assert dlg.result() == dlg.DialogCode.Accepted
    assert dlg.values()["overwrite"] is True
    # Untoggled (the tick above is remembered, so untick): no probe, no prompt.
    choices.clear()
    dlg = BlockSaveDialog(kind="schematic", root=root, collision_id="me")
    assert dlg.save_template_cb.isChecked() is True
    dlg.save_template_cb.setChecked(False)
    dlg.name_edit.setText("Riser")
    dlg._on_save()
    assert dlg.result() == dlg.DialogCode.Accepted and choices == []


def test_schematic_series_for_unions_project_and_disk(qapp, tmp_path):
    root = str(tmp_path)
    bl.create_folder("", "Trim", root=root)
    ms = Model_Space()
    d = BlockDefinition.new(name="R", library="", series="Risers", origin=(0.0, 0.0),
                            primitives=[_line().to_dict()], kind="schematic")
    ms.register_block_definition(d)
    assert schematic_series_for(ms, root=root) == ["Risers", "Trim"]


def test_first_save_with_toggle_writes_bundled_template(env, monkeypatch):
    ms, _tabs, _mgr = env
    w, plain = _open_schematic_with_nested(env)
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser A", template=True))
    defn = w.save(None)
    assert defn is not None and defn.kind == "schematic"
    path = os.path.join(app_data.schematics_dir(), "Riser A.fpdb")
    assert os.path.isfile(path)
    data = _read(path)
    assert data["kind"] == "schematic" and plain.id in data["bundled"]
    idx = _read(os.path.join(app_data.schematics_dir(), "index.json"))
    assert idx["Riser A.fpdb"]["id"] == defn.id and idx["Riser A.fpdb"]["kind"] == "schematic"
    assert bl.list_library() == []                              # block library untouched


def test_silent_resave_never_writes_the_template(env, monkeypatch):
    ms, _tabs, _mgr = env
    w, _plain = _open_schematic_with_nested(env)
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser B"))
    defn = w.save(None)
    assert defn is not None
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(0, 50)))
    w.editor_scene.push_undo_state()
    again = w.save(None)
    assert again is not None and again.id == defn.id
    assert not os.path.exists(os.path.join(app_data.schematics_dir(), "Riser B.fpdb"))


# -- Task 5: editor verb + collision loop --------------------------------------

def test_save_as_template_saves_project_then_writes(env, monkeypatch):
    ms, _tabs, _mgr = env
    w, plain = _open_schematic_with_nested(env)
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser C"))
    path = w.save_as_template(None)                 # never saved: Save dialog runs first
    assert path == os.path.join(app_data.schematics_dir(), "Riser C.fpdb")
    defn = ms.get_block_definition(w._edit_block_id)
    assert defn.kind == "schematic" and not w.is_dirty()
    assert plain.id in _read(path)["bundled"]
    # Dirty edits are saved to the project before the template is written.
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(0, 70)))
    w.editor_scene.push_undo_state()
    assert w.is_dirty()
    assert w.save_as_template(None) == path
    assert not w.is_dirty()
    assert len(_read(path)["primitives"]) == len(ms.get_block_definition(defn.id).primitives)


def test_save_as_template_cancelled_first_save_writes_nothing(env, monkeypatch):
    w, _plain = _open_schematic_with_nested(env)
    monkeypatch.setattr(BlockSaveDialog, "exec", lambda dlg: 0)
    assert w.save_as_template(None) is None
    assert not os.path.exists(os.path.join(app_data.schematics_dir(), "index.json"))


def test_save_schematic_template_collision_rename_retries(env, monkeypatch):
    from firepro3d import themed_message
    from firepro3d.block_editor import save_schematic_template
    ms, _tabs, _mgr = env
    other = BlockDefinition.new(name="Riser D", library="", series="", origin=(0.0, 0.0),
                                primitives=[_line().to_dict()], kind="schematic")
    bl.save_to_library(other, root=app_data.schematics_dir())   # a different template
    w, _plain = _open_schematic_with_nested(env)
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser D"))
    defn = w.save(None)
    monkeypatch.setattr(themed_message, "themed_choice", lambda *a, **k: "rename")
    monkeypatch.setattr(themed_message, "themed_input_text",
                        lambda *a, **k: ("Riser E", True))
    path = save_schematic_template(ms, defn, None)
    assert path == os.path.join(app_data.schematics_dir(), "Riser E.fpdb")
    assert ms.get_block_definition(defn.id).name == "Riser E"      # renamed in project
    assert _read(os.path.join(app_data.schematics_dir(), "Riser D.fpdb"))["id"] == other.id
    ms.undo()                                                       # rename = one project step
    assert ms.get_block_definition(defn.id).name == "Riser D"


def test_save_schematic_template_collision_cancel_and_overwrite(env, monkeypatch):
    from firepro3d import themed_message
    from firepro3d.block_editor import save_schematic_template
    ms, _tabs, _mgr = env
    other = BlockDefinition.new(name="Riser F", library="", series="", origin=(0.0, 0.0),
                                primitives=[_line().to_dict()], kind="schematic")
    bl.save_to_library(other, root=app_data.schematics_dir())
    w, _plain = _open_schematic_with_nested(env)
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser F"))
    defn = w.save(None)
    path = os.path.join(app_data.schematics_dir(), "Riser F.fpdb")
    monkeypatch.setattr(themed_message, "themed_choice", lambda *a, **k: "cancel")
    assert save_schematic_template(ms, defn, None) is None
    assert _read(path)["id"] == other.id                            # untouched
    monkeypatch.setattr(themed_message, "themed_choice", lambda *a, **k: "overwrite")
    assert save_schematic_template(ms, defn, None) == path
    assert _read(path)["id"] == defn.id
