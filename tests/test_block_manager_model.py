"""BlockTreeModel — Library/Series/block tree over the project's block definitions (S4.5)."""
from PyQt6.QtCore import Qt, QModelIndex
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_manager import BlockTreeModel, Col, BlockDefRole


def _def(name="A", library="L", series="S"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def _leaf_index(model, lib_name, ser_name, block_name):
    """Return the QModelIndex of a block leaf by walking Library->Series->block."""
    root = QModelIndex()
    for i in range(model.rowCount(root)):
        lib = model.index(i, 0, root)
        if model.data(lib, Qt.ItemDataRole.DisplayRole) != lib_name:
            continue
        for j in range(model.rowCount(lib)):
            ser = model.index(j, 0, lib)
            if model.data(ser, Qt.ItemDataRole.DisplayRole) != ser_name:
                continue
            for k in range(model.rowCount(ser)):
                leaf = model.index(k, 0, ser)
                if model.data(leaf, Qt.ItemDataRole.DisplayRole) == block_name:
                    return leaf
    return QModelIndex()


def test_tree_groups_library_series_block(model_space, tmp_path):
    d = _def(name="Corner", library="Details", series="Joints")
    model_space.register_block_definition(d)
    model = BlockTreeModel(model_space, root=str(tmp_path))

    root = QModelIndex()
    assert model.rowCount(root) == 1                         # one Library
    lib = model.index(0, 0, root)
    assert model.data(lib, Qt.ItemDataRole.DisplayRole) == "Details"
    assert model.rowCount(lib) == 1                          # one Series
    ser = model.index(0, 0, lib)
    assert model.data(ser, Qt.ItemDataRole.DisplayRole) == "Joints"
    assert model.rowCount(ser) == 1                          # one block leaf
    leaf = model.index(0, 0, ser)
    assert model.data(leaf, Qt.ItemDataRole.DisplayRole) == "Corner"


def test_leaf_columns_and_defrole(model_space, tmp_path):
    d = _def(name="Corner", library="Details", series="Joints")
    model_space.register_block_definition(d)
    model = BlockTreeModel(model_space, root=str(tmp_path))
    leaf = _leaf_index(model, "Details", "Joints", "Corner")
    assert leaf.isValid()

    def cell(col):
        return model.data(model.index(leaf.row(), col, leaf.parent()),
                          Qt.ItemDataRole.DisplayRole)
    assert cell(Col.COUNT) == "0"
    assert cell(Col.STATUS) == "project-only"
    # BlockDefRole resolves the definition on a leaf, None on a group row
    assert model.data(leaf, BlockDefRole) is d
    lib = model.index(0, 0, QModelIndex())
    assert model.data(lib, BlockDefRole) is None


def test_live_count_updates_on_place(model_space, tmp_path):
    d = _def(name="Corner", library="Details", series="Joints")
    model_space.register_block_definition(d)
    model = BlockTreeModel(model_space, root=str(tmp_path))
    model_space.place_block_instance(d.id, (0.0, 0.0))
    leaf = _leaf_index(model, "Details", "Joints", "Corner")
    cnt = model.data(model.index(leaf.row(), Col.COUNT, leaf.parent()),
                     Qt.ItemDataRole.DisplayRole)
    assert cnt == "1"


# ---------------------------------------------------------------------------
# SourceStatusDelegate — keep the colour-map test (delegate is unchanged)
# ---------------------------------------------------------------------------
from firepro3d.theme import detect
from firepro3d.block_manager import SourceStatusDelegate


def test_status_delegate_colour_map():
    d = SourceStatusDelegate(detect())
    # observable ground truth: each status maps to a distinct theme token name
    assert d.token_for("project-only") == "muted"
    assert d.token_for("library") == "ok"
    assert d.token_for("modified") == "warn"


# ---------------------------------------------------------------------------
# BlockManagerDialog — tree-aware tests (Task 5)
# ---------------------------------------------------------------------------

def _select_block(dlg, block_id):
    idx = dlg.model.index_for_id(block_id)
    assert idx.isValid()
    dlg.view.setCurrentIndex(idx)
    return idx


def test_dialog_constructs_and_reflects_scene(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog
    class _MW: settings = None
    d = _def(name="Corner")
    model_space.register_block_definition(d)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False,
                             root=str(tmp_path))
    _select_block(dlg, d.id)
    assert dlg.ed_name.text() == "Corner"
    assert dlg.btn_save.isEnabled()          # project-only -> Save enabled
    assert not dlg.btn_reload.isEnabled()    # project-only -> Reload disabled
    assert dlg.btn_editor.isEnabled()        # leaf selected -> Open in Editor enabled
    dlg.close()


def test_group_row_selection_blanks_panel(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog
    from PyQt6.QtCore import QModelIndex
    class _MW: settings = None
    d = _def(name="Corner", library="Details", series="Joints")
    model_space.register_block_definition(d)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False,
                             root=str(tmp_path))
    lib_index = dlg.model.index(0, 0, QModelIndex())     # a Library group row
    dlg.view.setCurrentIndex(lib_index)
    assert dlg._current_def() is None
    assert not dlg.btn_delete.isEnabled()
    assert not dlg.btn_editor.isEnabled()
    dlg.close()


def test_selection_survives_metadata_edit_reset(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog
    class _MW: settings = None
    d = _def(name="Old")
    model_space.register_block_definition(d)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False,
                             root=str(tmp_path))
    _select_block(dlg, d.id)
    assert dlg.ed_name.text() == "Old"
    dlg.ed_name.setText("New")
    dlg._commit_metadata()
    assert dlg._current_def() is not None and dlg._current_def().id == d.id
    assert dlg.ed_name.text() == "New"
    dlg.close()


def test_save_to_library_updates_status_after_reset(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog, Col, BlockDefRole
    from PyQt6.QtCore import Qt
    class _MW: settings = None
    d = _def(name="Corner")
    model_space.register_block_definition(d)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False,
                             root=str(tmp_path))
    leaf = _select_block(dlg, d.id)
    def status():
        return dlg.model.data(dlg.model.index(leaf.row(), Col.STATUS, leaf.parent()),
                              Qt.ItemDataRole.DisplayRole)
    assert status() == "project-only"
    dlg._save_to_library()
    # after refresh() reset, re-fetch the leaf (indices are rebuilt)
    leaf2 = dlg.model.index_for_id(d.id)
    assert dlg.model.data(dlg.model.index(leaf2.row(), Col.STATUS, leaf2.parent()),
                          Qt.ItemDataRole.DisplayRole) == "library"
    dlg.close()


def test_format_load_summary_omits_zero_categories():
    from firepro3d.block_manager import _format_load_summary
    s = {"loaded": ["A", "B"], "replaced": [], "skipped": ["C"],
         "refused": [], "failed": ["x.fpdb"]}
    msg = _format_load_summary(s)
    assert "Loaded 2" in msg and "skipped 1" in msg and "unreadable" in msg
    assert "replaced" not in msg and "refused" not in msg
    empty = {"loaded": [], "replaced": [], "skipped": [], "refused": [], "failed": []}
    assert _format_load_summary(empty) == "Nothing to load."


def test_tree_stays_expanded_after_load_reset(model_space, qapp, tmp_path):
    """Tree must stay fully expanded after a model reset triggered by a new block
    in a brand-new library (never previously selected, so the re-select logic does
    not auto-expand it).  Regression for the S4.5 headline flow.
    """
    from firepro3d.block_manager import BlockManagerDialog
    from PyQt6.QtCore import QModelIndex

    class _MW:
        settings = None

    d1 = _def(name="First", library="LibA", series="Ser1")
    model_space.register_block_definition(d1)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False,
                             root=str(tmp_path))
    # Embed a NEW block in a NEW library — fires blockDefinitionsChanged → model reset
    d2 = _def(name="Second", library="LibB", series="Ser2")
    model_space.register_block_definition(d2)
    # After the reset BOTH library group rows must be expanded (leaves visible)
    root = QModelIndex()
    assert dlg.model.rowCount(root) == 2, "expected two library rows"
    for i in range(dlg.model.rowCount(root)):
        lib_idx = dlg.model.index(i, 0, root)
        assert dlg.view.isExpanded(lib_idx), (
            f"library row {i} collapsed after reset")
        ser_idx = dlg.model.index(0, 0, lib_idx)
        assert dlg.view.isExpanded(ser_idx), (
            f"series row under library {i} collapsed after reset")
    dlg.close()
