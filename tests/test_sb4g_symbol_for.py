"""SB4g T3 -- BlockDefinition.symbol_for (sparse .fpdb / .fpd key) and the Block
Editor "Symbol for" row (design D7 / R10 / AC4). Helpers copied from
tests/test_sb1c_editor.py (not imported)."""
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorManager
from firepro3d.block_properties_info import BlockPropertiesInfo
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space

ROW = "Symbol for"
_KEEP: list = []        # the manager + tab widget own the editor: keep them alive


def _editor(project=None):
    project = project or Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    _KEEP.append((tabs, mgr))
    return project, mgr.open_new()


def _line():
    return LineItem(QPointF(-3.0, 0.0), QPointF(3.0, 0.0)).to_dict()


def test_symbol_for_is_sparse_and_round_trips(qapp):
    d = BlockDefinition.new(name="H", library="L", series="S", primitives=[_line()],
                            origin=(0.0, 0.0))
    assert d.symbol_for == ""
    assert "symbol_for" not in d.to_dict()          # untouched blocks stay byte-identical
    d.symbol_for = "Sprinkler"
    rec = d.to_dict()
    assert rec["symbol_for"] == "Sprinkler"
    assert BlockDefinition.from_dict(rec).symbol_for == "Sprinkler"
    assert BlockDefinition.from_dict({"id": "x"}).symbol_for == ""      # absent key -> none


def test_symbol_for_row_real_size_only_commits_and_reseeds(qapp):
    project, w = _editor()
    w.seed_from_dicts([_line()])
    info = BlockPropertiesInfo(w.editor_scene, "B", editor=w)
    props = info.get_properties()
    keys = list(props)
    assert keys[keys.index("Scale mode") + 1] == ROW               # beside Scale mode
    assert props[ROW]["options"] == ["(none)", "Sprinkler", "Water Supply", "Riser"]
    assert props[ROW]["value"] == "(none)"
    info.set_property(ROW, "Water Supply")
    assert w.editor_scene.block_meta["symbol_for"] == "Water Supply"
    defn = w.commit_block("B", "L", "S")
    assert defn.symbol_for == "Water Supply"
    tabs2 = QTabWidget()
    mgr2 = BlockEditorManager(tabs2, project)
    _KEEP.append((tabs2, mgr2))
    w2 = mgr2.open_for_definition(defn.id)
    w2.seed_from_definition(defn)
    assert w2.editor_scene.block_meta["symbol_for"] == "Water Supply"
    info.set_property("Scale mode", "Annotative")
    assert ROW not in info.get_properties()                         # real size only
    defn = w.commit_block("B", "L", "S")
    assert defn.symbol_for == ""                                    # an annotative block is no symbol


def test_symbol_for_undoes(qapp):
    _project, w = _editor()
    w.seed_from_dicts([_line()])
    sc = w.editor_scene
    sc.set_block_meta({**sc.block_meta, "symbol_for": "Riser"})
    sc.undo()
    assert sc.block_meta["symbol_for"] == ""


def test_symbol_for_saved_in_fpdb(qapp):
    d = BlockDefinition.new(name="MyHead", library="Heads", series="Mine",
                            primitives=[_line()], origin=(0.0, 0.0))
    d.symbol_for = "Sprinkler"
    path = block_library.save_to_library(d)          # isolated per-test user root (conftest)
    assert block_library.load_block_file(path).symbol_for == "Sprinkler"
