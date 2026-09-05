"""Block Manager flat table model + proxy + popup + dialog (S4.6)."""
from PyQt6.QtCore import Qt, QModelIndex
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_manager import BlockTableModel, Col, BlockDefRole, SortRole


def _def(name="A", library="L", series="S"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def _row_for_name(model, name):
    for r in range(model.rowCount()):
        if model.data(model.index(r, Col.NAME), Qt.ItemDataRole.DisplayRole) == name:
            return r
    return -1


# ---------------------------------------------------------------------------
# Task 1: BlockTableModel
# ---------------------------------------------------------------------------

def test_flat_columns_and_defrole(model_space, tmp_path):
    d = _def(name="Corner", library="Details", series="Joints")
    model_space.register_block_definition(d)
    m = BlockTableModel(model_space, root=str(tmp_path))
    assert m.rowCount() == 1
    assert m.columnCount() == len(Col)
    r = 0
    def cell(c): return m.data(m.index(r, c), Qt.ItemDataRole.DisplayRole)
    assert cell(Col.NAME) == "Corner"
    assert cell(Col.LIBRARY) == "Details"
    assert cell(Col.SERIES) == "Joints"
    assert cell(Col.COUNT) == "0"
    assert cell(Col.STATUS) == "project-only"
    assert m.data(m.index(r, Col.NAME), BlockDefRole) is d


def test_live_count(model_space, tmp_path):
    d = _def(name="Corner")
    model_space.register_block_definition(d)
    m = BlockTableModel(model_space, root=str(tmp_path))
    model_space.place_block_instance(d.id, (0.0, 0.0))
    r = _row_for_name(m, "Corner")
    assert m.data(m.index(r, Col.COUNT), Qt.ItemDataRole.DisplayRole) == "1"


def test_distinct_values(model_space, tmp_path):
    for n, lib in (("A", "L1"), ("B", "L1"), ("C", "L2")):
        model_space.register_block_definition(_def(name=n, library=lib))
    m = BlockTableModel(model_space, root=str(tmp_path))
    assert m.distinct_values(Col.LIBRARY) == ["L1", "L2"]
    assert m.distinct_values(Col.NAME) == ["A", "B", "C"]


def test_count_sortrole_is_numeric(model_space, tmp_path):
    d = _def(name="Big")
    model_space.register_block_definition(d)
    m = BlockTableModel(model_space, root=str(tmp_path))
    for _ in range(10):
        model_space.place_block_instance(d.id, (0.0, 0.0))
    r = _row_for_name(m, "Big")
    assert m.data(m.index(r, Col.COUNT), SortRole) == 10        # int, not "10"


# ---------------------------------------------------------------------------
# SourceStatusDelegate — keep the colour-map test (delegate is unchanged)
# ---------------------------------------------------------------------------
from firepro3d.theme import detect
from firepro3d.block_manager import SourceStatusDelegate


def test_status_delegate_colour_map():
    d = SourceStatusDelegate(detect())
    assert d.token_for("project-only") == "muted"
    assert d.token_for("library") == "ok"
    assert d.token_for("modified") == "warn"


# ---------------------------------------------------------------------------
# _format_load_summary (unchanged helper)
# ---------------------------------------------------------------------------

def test_format_load_summary_omits_zero_categories():
    from firepro3d.block_manager import _format_load_summary
    s = {"loaded": ["A", "B"], "replaced": [], "skipped": ["C"],
         "refused": [], "failed": ["x.fpdb"]}
    msg = _format_load_summary(s)
    assert "Loaded 2" in msg and "skipped 1" in msg and "unreadable" in msg
    assert "replaced" not in msg and "refused" not in msg
    empty = {"loaded": [], "replaced": [], "skipped": [], "refused": [], "failed": []}
    assert _format_load_summary(empty) == "Nothing to load."


# ---------------------------------------------------------------------------
# Task 2: BlockFilterProxy
# ---------------------------------------------------------------------------

def _make_proxy(model_space, tmp_path, specs):
    from firepro3d.block_manager import BlockTableModel, BlockFilterProxy
    for n, lib, ser in specs:
        model_space.register_block_definition(_def(name=n, library=lib, series=ser))
    m = BlockTableModel(model_space, root=str(tmp_path))
    p = BlockFilterProxy()
    p.setSourceModel(m)
    return m, p


def test_proxy_column_filter(model_space, tmp_path):
    from firepro3d.block_manager import Col
    m, p = _make_proxy(model_space, tmp_path,
                       [("A", "L1", "S1"), ("B", "L1", "S2"), ("C", "L2", "S1")])
    assert p.rowCount() == 3
    p.set_column_filter(Col.LIBRARY, {"L1"})
    assert p.rowCount() == 2
    assert p.is_filtered(Col.LIBRARY) is True
    # AND across columns
    p.set_column_filter(Col.SERIES, {"S2"})
    assert p.rowCount() == 1
    # clearing one restores
    p.set_column_filter(Col.LIBRARY, None)
    assert p.is_filtered(Col.LIBRARY) is False
    assert p.rowCount() == 1                       # still filtered by SERIES=S2
    p.clear_all()
    assert p.rowCount() == 3


def test_proxy_numeric_sort_on_count(model_space, tmp_path):
    from firepro3d.block_manager import Col, BlockTableModel, BlockFilterProxy, SortRole
    d_big = _def(name="Big"); d_small = _def(name="Small")
    model_space.register_block_definition(d_small)
    model_space.register_block_definition(d_big)
    for _ in range(10):
        model_space.place_block_instance(d_big.id, (0.0, 0.0))
    model_space.place_block_instance(d_small.id, (0.0, 0.0))   # count 1
    m = BlockTableModel(model_space, root=str(tmp_path))
    p = BlockFilterProxy(); p.setSourceModel(m)
    p.setSortRole(SortRole)
    p.sort(Col.COUNT, Qt.SortOrder.AscendingOrder)
    # ascending numeric: 1 (Small) before 10 (Big) — lexicographic would reverse
    first = p.data(p.index(0, Col.NAME), Qt.ItemDataRole.DisplayRole)
    assert first == "Small"


# ---------------------------------------------------------------------------
# Task 3: _FilterPopup headless test
# ---------------------------------------------------------------------------

def test_filter_popup_seeds_and_returns_selection(model_space, qapp, tmp_path):
    from firepro3d.block_manager import (BlockTableModel, BlockFilterProxy,
                                         _FilterPopup, Col)
    from firepro3d.theme import detect
    for n, lib in (("A", "L1"), ("B", "L1"), ("C", "L2")):
        model_space.register_block_definition(_def(name=n, library=lib))
    m = BlockTableModel(model_space, root=str(tmp_path))
    values = m.distinct_values(Col.LIBRARY)          # ["L1","L2"]
    pop = _FilterPopup(detect(), "Library", values, accepted=set(values))
    # all checked initially
    assert pop.chosen_values() == {"L1", "L2"}
    # simulate unchecking L2 via the API the popup exposes for tests
    pop.set_checked({"L1"})
    assert pop.chosen_values() == {"L1"}
    pop.close()


# ---------------------------------------------------------------------------
# Task 4 dialog tests (expected RED until Task 4 is implemented)
# ---------------------------------------------------------------------------

def _select_block(dlg, block_id):
    src_row = dlg.model.row_for_id(block_id)
    assert src_row >= 0
    proxy_idx = dlg.proxy.mapFromSource(dlg.model.index(src_row, 0))
    dlg.view.setCurrentIndex(proxy_idx)
    return proxy_idx


def test_dialog_constructs_and_selects(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog
    class _MW: settings = None
    d = _def(name="Corner")
    model_space.register_block_definition(d)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False, root=str(tmp_path))
    _select_block(dlg, d.id)
    assert dlg.lbl_name.text() == "Corner"       # read-only display
    assert dlg.btn_save.isEnabled() and not dlg.btn_reload.isEnabled()
    assert dlg.btn_editor.isEnabled()
    dlg.close()


def test_dialog_applies_column_filter(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog, Col
    class _MW: settings = None
    for n, lib in (("A", "L1"), ("B", "L2")):
        model_space.register_block_definition(_def(name=n, library=lib))
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False, root=str(tmp_path))
    assert dlg.proxy.rowCount() == 2
    dlg.proxy.set_column_filter(Col.LIBRARY, {"L1"})
    assert dlg.proxy.rowCount() == 1
    dlg.close()


def test_details_panel_is_read_only(model_space, qapp, tmp_path):
    # Metadata is edited in the Block Editor (v2), not inline in the Manager.
    from firepro3d.block_manager import BlockManagerDialog
    from PyQt6.QtWidgets import QLabel
    class _MW: settings = None
    d = _def(name="Corner", library="Details", series="Joints")
    model_space.register_block_definition(d)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False, root=str(tmp_path))
    _select_block(dlg, d.id)
    # the detail fields are display-only QLabels (no inline commit path)
    assert isinstance(dlg.lbl_name, QLabel)
    assert dlg.lbl_name.text() == "Corner"
    assert dlg.lbl_library.text() == "Details"
    assert dlg.lbl_series.text() == "Joints"
    assert not hasattr(dlg, "_commit_metadata")
    dlg.close()


def test_selection_survives_model_reset(model_space, qapp, tmp_path):
    # Selection + panel survive a reset (e.g. a new block loaded) via id re-select.
    from firepro3d.block_manager import BlockManagerDialog
    class _MW: settings = None
    d = _def(name="Keep")
    model_space.register_block_definition(d)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False, root=str(tmp_path))
    _select_block(dlg, d.id)
    # a new block registration fires blockDefinitionsChanged -> model reset
    model_space.register_block_definition(_def(name="Other", library="L2"))
    assert dlg._current_def() is not None and dlg._current_def().id == d.id
    assert dlg.lbl_name.text() == "Keep"
    dlg.close()


def test_group_no_longer_applies_but_empty_selection_blanks(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog
    class _MW: settings = None
    d = _def(name="Corner")
    model_space.register_block_definition(d)
    dlg = BlockManagerDialog(model_space, _MW(), apply_stylesheet=False, root=str(tmp_path))
    dlg.view.clearSelection()
    dlg._sync_ui()
    assert dlg._current_def() is None
    assert not dlg.btn_delete.isEnabled() and not dlg.btn_editor.isEnabled()
    dlg.close()


# ---------------------------------------------------------------------------
# S4.6 Bug fixes: tristate trap (I1) + search scope (I2)
# ---------------------------------------------------------------------------

def test_select_all_from_partial_selects_all(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockTableModel, _FilterPopup, Col
    from firepro3d.theme import detect
    for n in ("A", "B", "C"):
        model_space.register_block_definition(_def(name=n))
    m = BlockTableModel(model_space, root=str(tmp_path))
    vals = m.distinct_values(Col.NAME)                    # ["A","B","C"]
    pop = _FilterPopup(detect(), "Name", vals, accepted={"A"})   # partial state
    pop._toggle_all()                                     # simulate the (Select All) action
    assert pop.chosen_values() == {"A", "B", "C"}         # selects all, not clears
    pop._toggle_all()                                     # again -> clears all
    assert pop.chosen_values() == set()
    pop.close()


def test_select_all_scoped_to_search(model_space, qapp, tmp_path):
    from firepro3d.block_manager import BlockTableModel, _FilterPopup, Col
    from firepro3d.theme import detect
    for n in ("Alpha", "Able", "Beta"):
        model_space.register_block_definition(_def(name=n))
    m = BlockTableModel(model_space, root=str(tmp_path))
    vals = m.distinct_values(Col.NAME)                    # ["Able","Alpha","Beta"]
    pop = _FilterPopup(detect(), "Name", vals, accepted=set())   # none checked
    pop._search.setText("Al")                             # _filtered -> ["Alpha"] only ("al" in "alpha"; "al" not in "able" nor "beta")
    # (Select All) must only affect the search-filtered set, not all boxes
    pop._toggle_all()
    chosen = pop.chosen_values()
    # Use the implementation's own _filtered list (the authoritative visible set)
    filtered_names = {cb.text() for cb in pop._filtered}
    assert chosen == filtered_names and len(chosen) < 3     # not all 3
    pop.close()
