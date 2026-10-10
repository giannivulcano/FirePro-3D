"""SV3 Task 8 -- New Schematic dialog: Blank | From template (schematics.md
D-S9 / D-S11c / D-S11d; concept SD6, Option A ratified 2026-10-09; guard G4).
"""
from __future__ import annotations

import json
import os

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import app_data, block_library as bl
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.schematic_new_dialog import NewSchematicDialog


def _line():
    return LineItem(QPointF(0, 0), QPointF(100, 0))


def _template(name, series="", root=None, bundled=None):
    d = BlockDefinition.new(name=name, library="", series=series, origin=(0.0, 0.0),
                            primitives=[_line().to_dict()], kind="schematic")
    bl.save_to_library(d, root=root, bundled=bundled)
    return d


def _shape(item):
    return (item.text(0), [_shape(item.child(i)) for i in range(item.childCount())])


def _leaf_named(dlg, text):
    found = []

    def walk(it):
        if it.text(0) == text:
            found.append(it)
        for i in range(it.childCount()):
            walk(it.child(i))
    for i in range(dlg._tree.topLevelItemCount()):
        walk(dlg._tree.topLevelItem(i))
    return found[0]


# -- dialog ---------------------------------------------------------------------

def test_tree_blank_first_then_templates_ungrouped_then_series(qapp, tmp_path):
    root = str(tmp_path)
    _template("Hanger", root=root)
    _template("Wet Valve", "Valve Trim", root=root)
    _template("Riser", "Risers", root=root)
    bl.save_to_library(BlockDefinition.new(                      # a stray BLOCK file
        name="Stray", library="", series="Risers", origin=(0.0, 0.0),
        primitives=[_line().to_dict()]), root=root)
    dlg = NewSchematicDialog(None, root=root)
    tops = [dlg._tree.topLevelItem(i) for i in range(dlg._tree.topLevelItemCount())]
    assert [_shape(t) for t in tops] == [
        ("Blank schematic", []),
        ("Templates", [("Hanger", []),
                       ("Risers", [("Riser", [])]),
                       ("Valve Trim", [("Wet Valve", [])])])]
    assert dlg._tree.currentItem() is tops[0]
    assert dlg._create_btn.isEnabled() and dlg._create_btn.text() == "Create"
    assert tops[0].toolTip(0) and _leaf_named(dlg, "Riser").toolTip(0)


def test_no_templates_lists_blank_only(qapp, tmp_path):
    dlg = NewSchematicDialog(None, root=str(tmp_path / "none"))
    assert dlg._tree.topLevelItemCount() == 1
    assert dlg._tree.topLevelItem(0).text(0) == "Blank schematic"
    assert NewSchematicDialog.has_templates(str(tmp_path / "none")) is False


def test_search_filters_templates_but_keeps_blank(qapp, tmp_path):
    root = str(tmp_path)
    _template("Hanger", root=root)
    _template("Riser", "Risers", root=root)
    dlg = NewSchematicDialog(None, root=root)
    dlg._search.setText("ris")
    assert not _leaf_named(dlg, "Blank schematic").isHidden()
    assert _leaf_named(dlg, "Hanger").isHidden()
    assert not _leaf_named(dlg, "Riser").isHidden()
    dlg._search.setText("zzz")
    assert not _leaf_named(dlg, "Blank schematic").isHidden()
    assert _leaf_named(dlg, "Risers").isHidden()
    assert dlg._list_stack.currentWidget() is dlg._tree          # Blank still listed


def test_choice_blank_and_template(qapp, tmp_path):
    root = str(tmp_path)
    t = _template("Riser", "Risers", root=root)
    dlg = NewSchematicDialog(None, root=root)
    assert dlg.choice() is None
    dlg._accept_choice()
    assert dlg.choice() == ("blank", None, None, None)
    dlg = NewSchematicDialog(None, root=root)
    leaf = _leaf_named(dlg, "Riser")
    dlg._tree.setCurrentItem(leaf)
    dlg._on_item_activated(leaf)                               # double-click = Create
    assert dlg.choice() == ("template", os.path.join(root, "Risers", "Riser.fpdb"),
                            t.id, "Riser")
    assert dlg.result() == dlg.DialogCode.Accepted


def test_create_disabled_on_a_series_folder(qapp, tmp_path):
    root = str(tmp_path)
    _template("Riser", "Risers", root=root)
    dlg = NewSchematicDialog(None, root=root)
    dlg._tree.setCurrentItem(_leaf_named(dlg, "Risers"))
    assert not dlg._create_btn.isEnabled()
    dlg._accept_choice()
    assert dlg.choice() is None


# -- MainWindow (G4) -------------------------------------------------------------

@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow per test (mirrors tests/test_sv1_schematics_mainwindow.py)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d.view_3d import View3D
    from firepro3d import snap_engine
    main_mod.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    yield w
    for ed in list(w.block_editor_manager.open_editors()):
        ed._mark_clean()
    w._modified = False
    w.close()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _pick(name):
    """Fake ``NewSchematicDialog.exec``: choose the leaf *name* (or Blank)."""
    def _exec(dlg):
        dlg._tree.setCurrentItem(_leaf_named(dlg, name))
        dlg._accept_choice()
        return dlg.result()
    return _exec


def _never(dlg):
    raise AssertionError("dialog shown with no templates on disk")


def _seed_template(mw):
    """A template bundling one plain block, written through the real writer."""
    plain = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0.0, 0.0),
                                primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()])
    nested = {"type": "block_instance", "block_id": plain.id, "pos": [50.0, 20.0],
              "rotation": 0.0, "uid": "sv3-seed-nested"}   # BlockInstance.to_nested_dict keys
    tpl = BlockDefinition.new(name="Riser T", library="", series="Risers", origin=(0.0, 0.0),
                              primitives=[_line().to_dict(), nested], kind="schematic")
    path = bl.save_to_library(tpl, root=app_data.schematics_dir(),
                              bundled={plain.id: plain.to_dict()})
    return tpl, plain, path


def test_g4_new_blank_without_templates_skips_the_dialog(mw, monkeypatch):
    monkeypatch.setattr(NewSchematicDialog, "exec", _never)
    mw.project_browser.createSchematic.emit()
    w = mw.central_tabs.currentWidget()
    assert w.kind == "schematic" and w._edit_block_id is None


def test_g4_new_from_template_loads_project_copy_one_undo(mw, monkeypatch):
    tpl, plain, _path = _seed_template(mw)
    assert NewSchematicDialog.has_templates()
    monkeypatch.setattr(NewSchematicDialog, "exec", _pick("Riser T"))
    mw.project_browser.createSchematic.emit()
    d = mw.scene.get_block_definition(tpl.id)
    assert d is not None and d.kind == "schematic" and d.series == "Risers"
    assert mw.scene.get_block_definition(plain.id) is not None     # bundled block adopted
    w = mw.central_tabs.currentWidget()
    assert w.kind == "schematic" and w._edit_block_id == tpl.id
    assert mw.central_tabs.tabText(mw.central_tabs.indexOf(w)) == "Schematic: Riser T"
    mw.scene.undo()                                                 # ONE project step
    assert mw.scene.get_block_definition(tpl.id) is None
    assert mw.scene.get_block_definition(plain.id) is None
    mw.scene.redo()
    assert mw.scene.get_block_definition(tpl.id) is not None
    # Idempotent re-pick (same id, same version) = skip, still opens the tab.
    mw.project_browser.createSchematic.emit()
    assert mw.central_tabs.currentWidget()._edit_block_id == tpl.id
    assert sum(1 for x in mw.scene._block_definitions.values() if x.kind == "schematic") == 1


def test_g4_new_blank_with_templates_opens_empty_tab(mw, monkeypatch):
    _seed_template(mw)
    monkeypatch.setattr(NewSchematicDialog, "exec", _pick("Blank schematic"))
    mw.project_browser.createSchematic.emit()
    w = mw.central_tabs.currentWidget()
    assert w.kind == "schematic" and w._edit_block_id is None


def test_g4_name_clash_refused_with_schematic_wording(mw, monkeypatch):
    from firepro3d import themed_message
    tpl, _plain, _path = _seed_template(mw)
    clash = BlockDefinition.new(name="Riser T", library="", series="Risers", origin=(0.0, 0.0),
                                primitives=[_line().to_dict()], kind="schematic")
    mw.scene.register_block_definition(clash)                     # different id, same name
    shown = []
    monkeypatch.setattr(themed_message, "themed_info",
                        lambda parent, title, msg, icon=None: shown.append((title, msg)))
    monkeypatch.setattr(NewSchematicDialog, "exec", _pick("Riser T"))
    before = mw.central_tabs.count()
    mw.project_browser.createSchematic.emit()
    assert mw.scene.get_block_definition(tpl.id) is None
    assert mw.central_tabs.count() == before
    assert shown == [("New Schematic",
                      "Could not load “Riser T”: a different schematic already uses "
                      "this name in the project.")]


def test_g4_override_redirects_the_picker_and_the_writer(mw, monkeypatch, tmp_path):
    from PyQt6.QtCore import QSettings
    QSettings("GV", "FirePro3D").setValue(app_data.SCHEMATIC_DIR_KEY, str(tmp_path / "shared"))
    tpl, _plain, path = _seed_template(mw)
    assert path.startswith(str(tmp_path / "shared"))
    assert [e["id"] for e in bl.list_library(app_data.schematics_dir())] == [tpl.id]
    monkeypatch.setattr(NewSchematicDialog, "exec", _pick("Riser T"))
    mw.project_browser.createSchematic.emit()
    assert mw.scene.get_block_definition(tpl.id) is not None


def test_g4_a_copied_template_opens_as_its_own_schematic(mw, monkeypatch):
    """Disk scan (2026-10-10): a template copied in Explorer is listed under
    its file name and opens as a separate schematic; the original still
    opens as itself afterwards."""
    import shutil
    tpl, _plain, path = _seed_template(mw)
    shutil.copyfile(path, os.path.join(os.path.dirname(path), "Riser T v2.fpdb"))
    monkeypatch.setattr(NewSchematicDialog, "exec", _pick("Riser T v2"))
    mw.project_browser.createSchematic.emit()
    copy_id = mw.central_tabs.currentWidget()._edit_block_id
    copy = mw.scene.get_block_definition(copy_id)
    assert copy_id != tpl.id and copy.name == "Riser T v2"
    monkeypatch.setattr(NewSchematicDialog, "exec", _pick("Riser T"))
    mw.project_browser.createSchematic.emit()
    assert mw.central_tabs.currentWidget()._edit_block_id == tpl.id
    assert mw.scene.get_block_definition(tpl.id).name == "Riser T"
