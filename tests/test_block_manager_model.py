"""BlockTableModel — flat live view over the project's block definitions (S4)."""
from PyQt6.QtCore import Qt, QModelIndex
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_manager import BlockTableModel, Col


def _def(name="A", library="L", series="S"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def test_columns_and_live_count(model_space, tmp_path):
    d = _def(name="Corner", library="Details", series="Joints")
    model_space.register_block_definition(d)
    model = BlockTableModel(model_space, root=str(tmp_path))

    assert model.rowCount(QModelIndex()) == 1
    assert model.columnCount(QModelIndex()) == len(Col)

    def cell(row, col):
        return model.data(model.index(row, col), Qt.ItemDataRole.DisplayRole)

    assert cell(0, Col.NAME) == "Corner"
    assert cell(0, Col.LIBRARY) == "Details"
    assert cell(0, Col.SERIES) == "Joints"
    assert cell(0, Col.COUNT) == "0"
    # source-status text is exposed via DisplayRole on the STATUS column
    assert cell(0, Col.STATUS) == "project-only"

    # live: placing an instance updates the COUNT cell (model reset on signal)
    model_space.place_block_instance(d.id, (0.0, 0.0))
    assert cell(0, Col.COUNT) == "1"


def test_definition_for_row(model_space, tmp_path):
    d = _def()
    model_space.register_block_definition(d)
    model = BlockTableModel(model_space, root=str(tmp_path))
    assert model.definition_at(0) is d


from firepro3d.theme import detect
from firepro3d.block_manager import SourceStatusDelegate


def test_status_delegate_colour_map():
    d = SourceStatusDelegate(detect())
    # observable ground truth: each status maps to a distinct theme token name
    assert d.token_for("project-only") == "muted"
    assert d.token_for("library") == "ok"
    assert d.token_for("modified") == "warn"


def test_dialog_constructs_and_reflects_scene(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog

    class _MW:
        settings = None
    d = _def(name="Corner")
    model_space.register_block_definition(d)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False,
                             root=str(tmp_path))
    assert dlg.model.rowCount() == 1
    # select the row and confirm the details panel populates
    dlg.view.selectRow(0)
    assert dlg.ed_name.text() == "Corner"
    assert dlg.btn_save.isEnabled()       # project-only -> Save enabled
    assert not dlg.btn_reload.isEnabled() # project-only -> Reload disabled
    dlg.close()
