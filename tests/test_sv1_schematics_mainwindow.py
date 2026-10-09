"""SV1 Task 5 -- G1 (project half), G6 (SV1 half), capability lock on the
ribbon, real MainWindow (schematics.md D-S4/D-S9/D-S14/D-S16/D-S17)."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget, BlockSaveDialog
from firepro3d.capabilities import SCHEMATIC_CAP_REASON
from firepro3d.geometry_2d import LineItem
from firepro3d.project_browser import _ROLE_NAME, _ROLE_TYPE


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow per test (mirrors tests/test_stale_view_tabs.py)."""
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


def _leaves(win):
    out, stack = [], [win.project_browser._schem_root]
    while stack:
        it = stack.pop()
        if it.data(0, _ROLE_TYPE) == "schematic":
            out.append((it.data(0, _ROLE_NAME), it.text(0)))
        stack.extend(it.child(i) for i in range(it.childCount()))
    return out


def _fake_exec(name):
    def _exec(dlg):
        dlg.name_edit.setText(name)
        dlg._on_save()
        return dlg.result()
    return _exec


def _plain(win):
    d = BlockDefinition.new(
        name="Sym", library="L", series="S",
        primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()],
        origin=(0.0, 0.0))
    win.scene.register_block_definition(d)
    win.scene.push_undo_state()
    return d


def _new_saved_schematic(win, monkeypatch, name="Riser A"):
    plain = _plain(win)
    win.project_browser.createSchematic.emit()
    w = win.central_tabs.currentWidget()
    assert isinstance(w, BlockEditorWidget) and w.kind == "schematic"
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(100, 0)))
    w.editor_scene.place_block_instance(plain.id, (50.0, 20.0))
    w.editor_scene.push_undo_state()
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec(name))
    defn = w.save(win)
    assert defn is not None
    return w, defn, plain


def test_g1_new_save_lists_undo_and_round_trip(mw, monkeypatch, tmp_path):
    w, defn, plain = _new_saved_schematic(mw, monkeypatch)
    assert mw.central_tabs.tabText(mw.central_tabs.indexOf(w)) == "Schematic: Riser A"
    assert _leaves(mw) == [(defn.id, "Riser A")]
    assert mw.scene.get_block_definition(defn.id).kind == "schematic"
    assert mw.scene.instance_count(defn.id) == 0
    prims = list(defn.primitives)
    assert any(p.get("type") == "block_instance" and p.get("block_id") == plain.id
               for p in prims)
    mw.scene.undo()                                   # one project step
    assert mw.scene.get_block_definition(defn.id) is None
    assert _leaves(mw) == []
    mw.scene.redo()
    assert _leaves(mw) == [(defn.id, "Riser A")]
    path = tmp_path / "sv1.fpd"
    mw.scene.save_to_file(str(path))
    mw._apply_loaded_file(str(path))
    d2 = mw.scene.get_block_definition(defn.id)
    assert d2.kind == "schematic" and d2.primitives == prims
    assert _leaves(mw) == [(defn.id, "Riser A")]
    titles = [mw.central_tabs.tabText(i) for i in range(mw.central_tabs.count())]
    assert not any(t.startswith("Schematic: ") for t in titles)   # swept on load


def test_g6_leaf_double_click_opens_seeded_tab(mw, monkeypatch):
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    mw.block_editor_manager.close(w)
    leaf = next(it for it in [mw.project_browser._schem_root.child(i)
                              for i in range(mw.project_browser._schem_root.childCount())]
                if it.data(0, _ROLE_NAME) == defn.id)
    mw.project_browser._tree.itemDoubleClicked.emit(leaf, 0)
    ed = mw.central_tabs.currentWidget()
    assert isinstance(ed, BlockEditorWidget) and ed.kind == "schematic"
    assert mw.central_tabs.tabText(mw.central_tabs.currentIndex()) == "Schematic: Riser A"
    assert len(ed.gather_primitives()) == 2


def test_g6_hidden_from_block_pickers(mw, monkeypatch):
    from firepro3d.block_editor import library_tree_for
    from firepro3d.block_open_dialog import BlockOpenDialog
    _w, defn, plain = _new_saved_schematic(mw, monkeypatch)
    mw.blocks_browser.refresh()
    bb = []
    stack = [mw.blocks_browser._tree.topLevelItem(i)
             for i in range(mw.blocks_browser._tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        bb.append(it.text(0))
        stack.extend(it.child(i) for i in range(it.childCount()))
    assert "Sym" in bb and "Riser A" not in bb
    assert "" not in library_tree_for(mw.scene)
    dlg = BlockOpenDialog(mw.scene)
    try:
        names = []
        stack = [dlg._tree.topLevelItem(i) for i in range(dlg._tree.topLevelItemCount())]
        while stack:
            it = stack.pop()
            names.append(it.text(0))
            stack.extend(it.child(i) for i in range(it.childCount()))
        assert "Riser A" not in names
    finally:
        dlg.deleteLater()


def test_g6_rename_retitles_tab_and_is_one_undo(mw, monkeypatch):
    import firepro3d.themed_message as tm
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    monkeypatch.setattr(tm, "themed_input_text",
                        lambda *a, **k: ("Riser B", True))
    mw.project_browser.renameSchematic.emit(defn.id)
    assert defn.name == "Riser B"
    assert _leaves(mw) == [(defn.id, "Riser B")]
    assert mw.central_tabs.tabText(mw.central_tabs.indexOf(w)) == "Schematic: Riser B"
    mw.scene.undo()
    restored = mw.scene.get_block_definition(defn.id)
    assert restored.name == "Riser A"
    assert mw.central_tabs.tabText(mw.central_tabs.indexOf(w)) == "Schematic: Riser A"


def test_g6_rename_collision_is_refused(mw, monkeypatch):
    import firepro3d.themed_message as tm
    _w, a, _ = _new_saved_schematic(mw, monkeypatch, "Riser A")
    mw.project_browser.createSchematic.emit()
    w2 = mw.central_tabs.currentWidget()
    w2._add_primitive(LineItem(QPointF(0, 0), QPointF(5, 0)))
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser B"))
    b = w2.save(mw)
    infos = []
    monkeypatch.setattr(tm, "themed_input_text", lambda *a, **k: ("Riser A", True))
    monkeypatch.setattr(tm, "themed_info", lambda *a, **k: infos.append(a))
    mw.project_browser.renameSchematic.emit(b.id)
    assert b.name == "Riser B" and len(infos) == 1


def test_g6_delete_removes_leaf_and_closes_tab(mw, monkeypatch):
    import firepro3d.themed_message as tm
    from PyQt6 import sip
    w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    monkeypatch.setattr(tm, "themed_confirm", lambda *a, **k: True)
    mw.project_browser.deleteSchematic.emit(defn.id)
    assert mw.scene.get_block_definition(defn.id) is None
    assert _leaves(mw) == []
    assert mw.block_editor_manager.editor_for(defn.id) is None
    assert sip.isdeleted(w) or mw.central_tabs.indexOf(w) == -1
    mw.scene.undo()                                   # one project step
    assert mw.scene.get_block_definition(defn.id) is not None


def test_cap_lock_ribbon_disabled_in_schematic_tab_only(mw, monkeypatch):
    mw.project_browser.createSchematic.emit()
    for attr in ("_be_tile_btn", "_be_linetype_btn", "_be_end_btn"):
        btn = getattr(mw, attr)
        assert not btn.isEnabled()
        assert btn.toolTip() == SCHEMATIC_CAP_REASON
    info = mw._get_active_view_info()
    assert "Pattern tile" not in info.get_properties()
    mw.block_editor_manager.open_new()                # a plain block tab
    for attr in ("_be_tile_btn", "_be_linetype_btn", "_be_end_btn"):
        assert getattr(mw, attr).isEnabled()


def test_new_file_sweeps_schematic_tabs_and_clears_tree(mw, monkeypatch):
    _w, defn, _ = _new_saved_schematic(mw, monkeypatch)
    for ed in mw.block_editor_manager.open_editors():
        ed._mark_clean()
    mw.scene._modified = False
    mw._modified = False
    monkeypatch.setattr(mw, "_ask_save_changes", lambda *a, **k: True)
    mw.new_file()
    titles = [mw.central_tabs.tabText(i) for i in range(mw.central_tabs.count())]
    assert not any(t.startswith("Schematic: ") for t in titles)
    assert _leaves(mw) == []
