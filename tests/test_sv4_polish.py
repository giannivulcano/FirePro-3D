"""SV4 -- schematics polish (schematics.md D-S4 / D-S5 / D-S16 / D-S17; concept
SD11): Block Manager Kind column + per-row verb gating + Used-in, the
``available_views`` Schematics group, the browser Duplicate verb, and the two
SV3 seam minors (one template write per Save as Template; an emptied index is
removed).
"""
from __future__ import annotations

import json
import os

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt

from firepro3d import app_data, block_library as bl
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorManager, BlockSaveDialog
from firepro3d.block_manager import BlockManagerDialog, BlockTableModel, Col
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.schematic_new_dialog import NewSchematicDialog
from firepro3d.schematic_scene import SchematicSceneManager


def _line(length=30):
    return LineItem(QPointF(0, 0), QPointF(length, 0)).to_dict()


def _block(ms, name="Sym", library="L", series="S"):
    d = BlockDefinition.new(name=name, library=library, series=series,
                            primitives=[_line()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


def _schematic(ms, name="Riser", series="", primitives=None):
    d = BlockDefinition.new(name=name, library="", series=series,
                            primitives=primitives or [_line()], origin=(0.0, 0.0),
                            kind="schematic")
    ms.register_block_definition(d)
    return d


def _cell(model, row, col):
    return model.data(model.index(row, col), Qt.ItemDataRole.DisplayRole)


def _row(model, block_id):
    r = model.row_for_id(block_id)
    assert r >= 0
    return r


def _select(dlg, block_id):
    src_row = dlg.model.row_for_id(block_id)
    assert src_row >= 0
    dlg.view.setCurrentIndex(dlg.proxy.mapFromSource(dlg.model.index(src_row, 0)))


class _MW:
    settings = None

    def __init__(self):
        self.opened = []

        class _Mgr:
            def __init__(self, outer):
                self._outer = outer

            def open_new(self, kind="block"):
                self._outer.opened.append(kind)

                class _W:
                    def seed_from_definition(self, defn):
                        pass
                return _W()
        self.block_editor_manager = _Mgr(self)


# -- Block Manager: Kind column, filter, Source, verb gating, Used-in ---------

def test_kind_column_lists_schematics_and_filters(model_space, tmp_path):
    b = _block(model_space)
    s = _schematic(model_space)
    m = BlockTableModel(model_space, root=str(tmp_path / "lib"),
                        templates_root=str(tmp_path / "tpl"))
    assert m.columnCount() == len(Col) and Col.KIND == max(Col)   # appended last
    assert m.headerData(Col.KIND, Qt.Orientation.Horizontal) == "Kind"
    assert _cell(m, _row(m, b.id), Col.KIND) == "Block"
    assert _cell(m, _row(m, s.id), Col.KIND) == "Schematic"
    assert m.distinct_values(Col.KIND) == ["Block", "Schematic"]

    from firepro3d.block_manager import BlockFilterProxy
    p = BlockFilterProxy()
    p.setSourceModel(m)
    p.set_column_filter(Col.KIND, {"Schematic"})
    assert p.rowCount() == 1
    assert p.data(p.index(0, Col.NAME), Qt.ItemDataRole.DisplayRole) == "Riser"


def test_schematic_source_reads_the_templates_folder(model_space, tmp_path):
    lib, tpl = str(tmp_path / "lib"), str(tmp_path / "tpl")
    s = _schematic(model_space)
    m = BlockTableModel(model_space, root=lib, templates_root=tpl)
    assert _cell(m, _row(m, s.id), Col.STATUS) == "project-only"
    bl.save_to_library(s, root=tpl)
    m.refresh()
    assert _cell(m, _row(m, s.id), Col.STATUS) == "library"
    assert bl.list_library(lib) == []                      # block library untouched


def test_schematic_row_disables_the_library_verbs(model_space, qapp, tmp_path):
    b = _block(model_space)
    s = _schematic(model_space)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False,
                             root=str(tmp_path / "lib"),
                             templates_root=str(tmp_path / "tpl"))
    try:
        _select(dlg, b.id)
        assert dlg.btn_save.isEnabled() and dlg.lbl_kind.text() == "Block"
        _select(dlg, s.id)
        assert dlg.lbl_kind.text() == "Schematic"
        assert not dlg.btn_save.isEnabled() and not dlg.btn_reload.isEnabled()
        assert dlg.btn_save.toolTip() and dlg.btn_reload.toolTip()
        assert dlg.btn_delete.isEnabled() and dlg.btn_editor.isEnabled()
        assert dlg.count_label.text().startswith("2 of 2 definitions")
        # New From Selected on a schematic row opens a Schematic editor.
        dlg._create_new_from_selected()
        assert dlg.main_window.opened == ["schematic"]
    finally:
        dlg.close()


def test_used_in_counts_a_schematic_nesting_the_block(model_space, tmp_path):
    b = _block(model_space)
    nested = {"type": "block_instance", "block_id": b.id, "pos": [10.0, 0.0],
              "rotation": 0.0}
    s = _schematic(model_space, primitives=[_line(), nested])
    m = BlockTableModel(model_space, root=str(tmp_path / "lib"),
                        templates_root=str(tmp_path / "tpl"))
    assert _cell(m, _row(m, b.id), Col.USED_IN) == "1"
    assert s.id in model_space.block_registry.users_of(b.id)
    assert _cell(m, _row(m, s.id), Col.USED_IN) == "0"


# -- available_views ---------------------------------------------------------

def test_available_views_lists_schematics_by_name(qapp):
    from firepro3d.paper_space import ViewResolver

    class _PVM:
        _views = {"Plan: Level 1": object()}

    class _DM:
        detail_names = []

    class _EM:
        open_directions = []

    ms = Model_Space()
    mgr = SchematicSceneManager(ms)
    resolver = ViewResolver(ms, _PVM(), _DM(), _EM(), schematic_scenes=mgr)
    assert "Schematics" not in resolver.available_views()
    _schematic(ms, name="riser b")
    _schematic(ms, name="Hanger", series="Typicals")
    assert resolver.available_views()["Schematics"] == ["Hanger", "riser b"]
    bare = ViewResolver(ms, _PVM(), _DM(), _EM())
    assert "Schematics" not in bare.available_views()


# -- Duplicate ---------------------------------------------------------------

def test_duplicate_schematic_is_a_new_definition_with_a_unique_copy_name(model_space):
    s = _schematic(model_space, name="Riser", series="Typicals",
                   primitives=[_line(), _line(80)])
    model_space.push_undo_state()
    fired = []
    model_space.blockDefinitionsChanged.connect(lambda: fired.append(1))

    c1 = model_space.duplicate_block_definition(s.id)
    assert c1 is not None and c1.id != s.id and c1.kind == "schematic"
    assert (c1.name, c1.library, c1.series) == ("Riser copy", "", "Typicals")
    assert c1.primitives == s.primitives and c1.primitives is not s.primitives
    assert model_space.instance_count(c1.id) == 0
    assert fired == [1]

    c2 = model_space.duplicate_block_definition(s.id)
    assert c2.name == "Riser copy 2"
    c3 = model_space.duplicate_block_definition(c1.id)
    assert c3.name == "Riser copy copy"
    assert model_space.duplicate_block_definition("nope") is None

    # One project undo step each (D-S17): the latest copy goes first.
    model_space.undo()
    assert model_space.get_block_definition(c3.id) is None
    assert model_space.get_block_definition(c2.id) is not None
    model_space.undo()
    assert model_space.get_block_definition(c2.id) is None
    assert model_space.get_block_definition(c1.id) is not None
    model_space.undo()
    assert model_space.get_block_definition(c1.id) is None
    assert model_space.get_block_definition(s.id) is not None


def test_browser_duplicate_signal_and_menu(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMenu
    from firepro3d.project_browser import ProjectBrowser, _ROLE_NAME, _ROLE_TYPE
    pb = ProjectBrowser()
    pb.refresh_schematics([("id1", "Riser A", "")])
    got = []
    pb.duplicateSchematic.connect(lambda i: got.append(i))
    leaf = next(pb._schem_root.child(i) for i in range(pb._schem_root.childCount())
                if pb._schem_root.child(i).data(0, _ROLE_TYPE) == "schematic")
    assert leaf.data(0, _ROLE_NAME) == "id1"
    monkeypatch.setattr(pb._tree, "itemAt", lambda pos: leaf)
    monkeypatch.setattr(QMenu, "exec", lambda self, *a: next(
        x for x in self.actions() if x.text() == "Duplicate").trigger())
    pb._on_context_menu(QPoint(0, 0))
    assert got == ["id1"]


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow per test (mirrors tests/test_sv3_save_template.py)."""
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


def test_browser_duplicate_creates_a_copy_leaf_without_opening_an_editor(mw):
    from firepro3d.project_browser import _ROLE_NAME, _ROLE_TYPE
    s = _schematic(mw.scene, name="Riser", series="Typicals")
    mw.scene.push_undo_state()
    mw._refresh_schematic_browser()
    open_before = len(list(mw.block_editor_manager.open_editors()))

    mw.project_browser.duplicateSchematic.emit(s.id)

    def _leaves(root):
        stack, out = [root], []
        while stack:
            it = stack.pop()
            if it.data(0, _ROLE_TYPE) == "schematic":
                out.append((it.text(0), it.data(0, _ROLE_NAME)))
            stack.extend(it.child(i) for i in range(it.childCount()))
        return out
    leaves = _leaves(mw.project_browser._schem_root)
    names = {n for n, _ in leaves}
    assert names == {"Riser", "Riser copy"}
    copy_id = next(i for n, i in leaves if n == "Riser copy")
    copy = mw.scene.get_block_definition(copy_id)
    assert copy.kind == "schematic" and copy.series == "Typicals"
    assert len(list(mw.block_editor_manager.open_editors())) == open_before
    # A plain block id is ignored by the verb.
    b = _block(mw.scene)
    mw.project_browser.duplicateSchematic.emit(b.id)
    names_after = {d.name for d in mw.scene._block_definitions.values()}
    assert {"Riser", "Riser copy", "Sym"} <= names_after      # shipped blocks also live here
    assert "Sym copy" not in names_after
    mw.scene.undo()
    assert mw.scene.get_block_definition(copy_id) is None
    assert {n for n, _ in _leaves(mw.project_browser._schem_root)} == {"Riser"}


# -- Seam minor (a): one template write per Save as Template -----------------

@pytest.fixture()
def env(qapp):
    from PyQt6.QtWidgets import QTabWidget
    ms = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, ms)
    yield ms, tabs, mgr
    for w in list(mgr.open_editors()):
        mgr.close(w)
    tabs.deleteLater()


def test_first_save_as_template_with_the_toggle_writes_once(env, monkeypatch):
    ms, _tabs, mgr = env
    w = mgr.open_new(kind="schematic")
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(100, 0)))
    w.editor_scene.push_undo_state()

    def _exec(dlg):
        dlg.name_edit.setText("Riser W")
        dlg.save_template_cb.setChecked(True)
        dlg._on_save()
        return dlg.result()
    monkeypatch.setattr(BlockSaveDialog, "exec", _exec)
    writes = []
    real = bl.save_to_library

    def _counted(defn, root=None, **kw):
        writes.append(root)
        return real(defn, root=root, **kw)
    monkeypatch.setattr(bl, "save_to_library", _counted)

    path = w.save_as_template(None)
    expected = os.path.join(app_data.schematics_dir(), "Riser W.fpdb")
    assert path == expected and os.path.isfile(path)
    assert writes == [app_data.schematics_dir()]            # one write, not two
    assert not w.is_dirty()
    # A later ribbon Save as Template still writes (the project copy changed).
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(0, 70)))
    w.editor_scene.push_undo_state()
    assert w.save_as_template(None) == expected
    assert len(writes) == 2
    assert len(json.load(open(expected, encoding="utf-8"))["primitives"]) == 2


# -- Seam minor (b), superseded 2026-10-10: no index is ever written ---------

def test_deleting_the_last_ungrouped_template_leaves_no_index(tmp_path):
    root = str(tmp_path)
    d = BlockDefinition.new(name="Hanger", library="", series="",
                            primitives=[_line()], origin=(0.0, 0.0), kind="schematic")
    bl.save_to_library(d, root=root)
    assert not os.path.exists(os.path.join(root, "index.json"))
    assert NewSchematicDialog.has_templates(root)
    bl.delete_from_library("", "", "Hanger.fpdb", root)
    assert not os.path.exists(os.path.join(root, "index.json"))
    assert not os.path.exists(os.path.join(root, "Hanger.fpdb"))
    assert bl.list_library(root) == [] and not NewSchematicDialog.has_templates(root)
    # A two-tier Series folder behaves the same; a re-save is listed again.
    b = BlockDefinition.new(name="Sym", library="L", series="S",
                            primitives=[_line()], origin=(0.0, 0.0))
    bl.save_to_library(b, root=root)
    series_dir = os.path.join(root, "L", "S")
    bl.delete_from_library("L", "S", "Sym.fpdb", root)
    assert os.path.isdir(series_dir) and not os.path.exists(
        os.path.join(series_dir, "index.json"))
    assert bl.list_folders(root) == {"L": ["S"]}
    bl.save_to_library(b, root=root)
    assert bl._find_by_id(b.id, root)[:3] == ("L", "S", "Sym.fpdb")
