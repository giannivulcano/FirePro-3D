"""SV1 Task 2/3 -- Schematic editor, Save Schematic dialog, capability lock,
listing filters (D-S4, D-S9, D-S14, D-S15)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import (BlockEditorManager, BlockSaveDialog,
                                    library_tree_for)
from firepro3d.capabilities import SCHEMATIC_CAP_REASON
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _line_item():
    return LineItem(QPointF(0, 0), QPointF(40, 0))


@pytest.fixture()
def env(qapp):
    ms = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, ms)
    yield ms, tabs, mgr
    for w in list(mgr.open_editors()):
        mgr.close(w)
    tabs.deleteLater()


def _fake_exec(name, series=None):
    def _exec(dlg):
        dlg.name_edit.setText(name)
        if series is not None:
            dlg.series_sel.set_items([series], current=series)
        dlg._on_save()
        return dlg.result()
    return _exec


def test_open_new_schematic_tab_title_and_kind(env):
    ms, tabs, mgr = env
    w = mgr.open_new(kind="schematic")
    assert w.kind == "schematic"
    assert tabs.tabText(tabs.indexOf(w)) == "Schematic: New"


def test_save_schematic_dialog_commits_project_only(env, monkeypatch):
    ms, tabs, mgr = env
    import firepro3d.block_library as bl
    writes = []
    monkeypatch.setattr(bl, "save_to_library",
                        lambda *a, **k: writes.append(a))
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser A"))
    w = mgr.open_new(kind="schematic")
    w._add_primitive(_line_item())
    defn = w.save()
    assert defn is not None and defn.kind == "schematic"
    assert (defn.name, defn.library, defn.series) == ("Riser A", "", "")
    assert ms.instance_count(defn.id) == 0
    assert tabs.tabText(tabs.indexOf(w)) == "Schematic: Riser A"
    w._add_primitive(_line_item())
    assert w.save() is defn            # silent re-save
    assert writes == []                # never the block library (D-S5)


def test_save_dialog_schematic_shape(qapp):
    dlg = BlockSaveDialog(None, kind="schematic", schematic_series=["Risers"],
                          initial=("R", "", "Risers"))
    assert dlg.windowTitle() == "Save Schematic"
    assert dlg.validation_error() is None
    v = dlg.values()
    assert (v["library"], v["series"], v["save_to_library"]) == ("", "Risers", False)
    # D-S14: no Library row and no "Also save to library" row in the form.
    assert dlg.library_sel.parent() is None
    assert dlg.save_to_library_cb.parent() is None
    dlg.name_edit.setText("")
    assert dlg.validation_error() is not None
    dlg.deleteLater()


def test_schematic_series_plus_adds_and_returns_it(qapp):
    dlg = BlockSaveDialog(None, kind="schematic", schematic_series=[],
                          initial=("R", "", ""))
    dlg._add_schematic_series("Risers")
    assert dlg.values()["series"] == "Risers"
    dlg.deleteLater()


def test_schematic_save_leaves_the_library_toggle_setting(qapp):
    from PyQt6.QtCore import QSettings
    from firepro3d.block_editor import _SAVE_TO_LIB_KEY
    s = QSettings("GV", "FirePro3D")
    s.setValue(_SAVE_TO_LIB_KEY, True)
    dlg = BlockSaveDialog(None, kind="schematic", schematic_series=[],
                          initial=("R", "", ""))
    dlg._on_save()
    assert QSettings("GV", "FirePro3D").value(_SAVE_TO_LIB_KEY) in (True, "true")
    dlg.deleteLater()


def test_save_dialog_series_none_means_blank(qapp):
    dlg = BlockSaveDialog(None, kind="schematic", schematic_series=[],
                          initial=("R", "", ""))
    assert dlg.values()["series"] == ""
    dlg.deleteLater()


def test_save_validator_refuses_duplicate_in_series(env, monkeypatch):
    ms, tabs, mgr = env
    other = BlockDefinition.new(name="Riser A", library="", series="",
                                primitives=[_line_item().to_dict()],
                                origin=(0.0, 0.0), kind="schematic")
    ms.register_block_definition(other)
    seen = {}

    def _exec(dlg):
        dlg.name_edit.setText("Riser A")
        seen["err"] = dlg.validation_error()
        return 0                        # rejected
    monkeypatch.setattr(BlockSaveDialog, "exec", _exec)
    w = mgr.open_new(kind="schematic")
    w._add_primitive(_line_item())
    assert w.save() is None
    assert "already exists" in seen["err"]


def test_save_as_keeps_schematic_kind(env, monkeypatch):
    ms, tabs, mgr = env
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser A"))
    w = mgr.open_new(kind="schematic")
    w._add_primitive(_line_item())
    first = w.save()
    monkeypatch.setattr(BlockSaveDialog, "exec", _fake_exec("Riser B"))
    second = w.save_as()
    assert second.id != first.id and second.kind == "schematic"


def test_edit_definition_opens_schematic_tab(env):
    ms, tabs, mgr = env
    d = BlockDefinition.new(name="Riser A", library="", series="",
                            primitives=[_line_item().to_dict()],
                            origin=(0.0, 0.0), kind="schematic")
    ms.register_block_definition(d)
    w = mgr.edit_definition(d.id)
    assert w.kind == "schematic"
    assert tabs.tabText(tabs.indexOf(w)) == "Schematic: Riser A"
    assert len(w.gather_primitives()) == 1
    assert mgr.editor_for(d.id) is w


def test_capability_toggle_refused_in_schematic(env):
    ms, tabs, mgr = env
    w = mgr.open_new(kind="schematic")
    shown = []
    w.editor_scene._show_status = lambda msg, timeout=5000: shown.append(msg)
    w._add_primitive(_line_item())
    for kind in ("tile", "repeat", "end"):
        assert w.toggle_capability(kind) is False
    assert w.editor_scene.block_capability is None
    assert shown == [SCHEMATIC_CAP_REASON] * 3


def test_panel_omits_capability_rows_for_schematic(env):
    from firepro3d.block_properties_info import BlockPropertiesInfo
    ms, tabs, mgr = env
    sw = mgr.open_new(kind="schematic")
    props = BlockPropertiesInfo(sw.editor_scene, "New", editor=sw).get_properties()
    assert "Pattern tile" not in props and "End type" not in props
    bw = mgr.open_new()
    props = BlockPropertiesInfo(bw.editor_scene, "New", editor=bw).get_properties()
    assert "Pattern tile" in props


def test_retitle_schematics_follows_registry_name(env):
    ms, tabs, mgr = env
    d = BlockDefinition.new(name="Riser A", library="", series="",
                            primitives=[_line_item().to_dict()],
                            origin=(0.0, 0.0), kind="schematic")
    ms.register_block_definition(d)
    w = mgr.edit_definition(d.id)
    d.name = "Riser Z"
    mgr.retitle_schematics()
    assert tabs.tabText(tabs.indexOf(w)) == "Schematic: Riser Z"


# -- Task 3: listing filters (D-S4) -------------------------------------------

def _two_defs(ms):
    s = BlockDefinition.new(name="Riser A", library="", series="",
                            primitives=[_line_item().to_dict()],
                            origin=(0.0, 0.0), kind="schematic")
    b = BlockDefinition.new(name="Sym", library="L", series="S",
                            primitives=[_line_item().to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(s)
    ms.register_block_definition(b)
    return s, b


def _tree_texts(tree):
    out = []

    def walk(it):
        out.append(it.text(0))
        for i in range(it.childCount()):
            walk(it.child(i))
    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i))
    return out


def test_library_tree_for_excludes_schematics(qapp):
    ms = Model_Space()
    _two_defs(ms)
    tree = library_tree_for(ms)
    assert "" not in tree and tree.get("L") == ["S"]


def test_blocks_browser_hides_schematics(qapp):
    from firepro3d.blocks_browser import BlocksBrowser
    ms = Model_Space()
    _two_defs(ms)
    bb = BlocksBrowser(ms)
    bb.refresh()
    texts = _tree_texts(bb._tree)
    assert "Sym" in texts and "Riser A" not in texts
    bb.deleteLater()


def test_block_open_dialog_hides_schematics(qapp):
    from firepro3d.block_open_dialog import BlockOpenDialog
    ms = Model_Space()
    _two_defs(ms)
    dlg = BlockOpenDialog(ms)
    texts = _tree_texts(dlg._tree)
    assert "Sym" in texts and "Riser A" not in texts
    dlg.deleteLater()


def test_block_manager_hides_schematics_until_sv4(qapp):
    from firepro3d.block_manager import BlockManagerDialog
    ms = Model_Space()
    s, b = _two_defs(ms)
    dlg = BlockManagerDialog(ms, None)
    ids = [d.id for d in dlg.model._defs]
    assert b.id in ids and s.id not in ids
    dlg.deleteLater()


def test_block_manager_count_ignores_hidden_schematics(qapp):
    from firepro3d.block_manager import BlockManagerDialog

    def _label(with_schematic):
        ms = Model_Space()
        if with_schematic:
            _two_defs(ms)                    # schematic + "Sym"
        else:
            _s, b = _two_defs(Model_Space())
            ms.register_block_definition(b)
        ms.register_block_definition(BlockDefinition.new(
            name="Other", library="L", series="S",
            primitives=[_line_item().to_dict()], origin=(0.0, 0.0)))
        dlg = BlockManagerDialog(ms, None)
        try:
            return dlg.count_label.text()
        finally:
            dlg.deleteLater()

    plain = _label(False)
    assert plain.startswith("2 of 2 blocks")
    assert _label(True) == plain
