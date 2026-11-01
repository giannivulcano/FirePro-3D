"""Block Editor Attributes editor: one Precision column (number decimals /
host-text display override) + the Unit override column (text-sizing-wrap
design D8, rule B-2'; AC5, AC6)."""
from firepro3d.block_attributes import normalise_attr
from firepro3d.block_attributes_editor import COLUMNS, PER_PROJECT, AttributesEditorDialog
from tests.test_sb2a_pickers import _editor


def _attrs():
    return [normalise_attr({"key": "L", "source": "host", "host_key": "Length"}),
            normalise_attr({"key": "Q", "source": "host", "host_key": "Flow"}),
            normalise_attr({"key": "M", "default": "A1"}),
            normalise_attr({"key": "N", "type": "number", "precision": 1, "source": "host",
                            "host_key": "Length"}),
            normalise_attr({"key": "C", "type": "number", "precision": 2})]


def _cell(dlg, row, col):
    return dlg.table.cellWidget(row, COLUMNS.index(col))


def _items(box):
    return [box.itemText(i) for i in range(box.count())]


def test_one_precision_column_and_a_unit_column(qapp):
    w = _editor("Pipe", _attrs())
    dlg = AttributesEditorDialog(w)
    head = [dlg.table.horizontalHeaderItem(c).text() for c in range(dlg.table.columnCount())]
    assert head.count("Precision") == 1 and "Decimals" not in head
    assert head[COLUMNS.index("precision")] == "Precision"
    assert head[COLUMNS.index("unit")] == "Unit"
    assert "display_precision" not in COLUMNS
    assert PER_PROJECT == "Per project settings"
    # AC6: the project's unit list (scale_manager.DISPLAY_UNIT_OPTIONS)
    assert _items(_cell(dlg, 0, "unit")) == [PER_PROJECT, "Imperial (ft-in)",
                                             "Metric (m)", "Metric (mm)"]
    assert _items(_cell(dlg, 0, "precision")) == [PER_PROJECT, "0", "1", "2", "3", "4", "5"]
    # text rows show the override (absent = Per project settings); number rows their decimals
    shown = [_cell(dlg, r, "precision").currentText() for r in range(5)]
    assert shown == [PER_PROJECT, PER_PROJECT, PER_PROJECT, "1", "2"]
    assert all(_cell(dlg, r, "unit").currentText() == PER_PROJECT for r in range(5))


def test_legacy_text_precision_is_never_read_as_an_override(qapp):
    """Nothing moves: a text record's stored precision (0 on the shipped tags,
    or any value) shows Per project settings and is written back unchanged."""
    attrs = _attrs()
    attrs[0] = normalise_attr({**attrs[0], "precision": 3})
    w = _editor("Pipe", attrs)
    dlg = AttributesEditorDialog(w)
    assert _cell(dlg, 0, "precision").currentText() == PER_PROJECT
    assert dlg.try_accept() is True
    assert w.editor_scene.block_meta["attributes"] == attrs


def test_columns_gate_by_type_and_host_kind(qapp):
    w = _editor("Pipe", _attrs())
    dlg = AttributesEditorDialog(w)

    def on(r):
        return (_cell(dlg, r, "unit").isEnabled(), _cell(dlg, r, "precision").isEnabled())

    assert on(0) == (True, True)       # host length text: unit + display precision
    assert on(1) == (False, True)      # host flow (hydraulic): precision only (G7)
    assert on(2) == (False, False)     # instance text: nothing to format
    assert on(3) == (True, True)       # host length number: unit + decimals
    assert on(4) == (False, True)      # instance number: decimals (as today)
    dlg.set_cell(1, "host_key", "Length")          # re-gates live
    assert on(1) == (True, True)
    dlg.set_cell(0, "source", "instance")
    assert on(0) == (False, False)
    dlg.set_cell(2, "type", "number")
    assert on(2) == (False, True)


def test_precision_column_writes_the_key_its_row_type_owns(qapp):
    w = _editor("Pipe", _attrs())
    dlg = AttributesEditorDialog(w)
    dlg.set_cell(0, "unit", "m")
    dlg.set_cell(0, "precision", "2")              # host text -> display override
    dlg.set_cell(1, "precision", "1")
    dlg.set_cell(3, "precision", "3")              # number -> decimals
    dlg.set_cell(4, "precision", "0")
    assert dlg.try_accept() is True
    recs = w.editor_scene.block_meta["attributes"]
    assert (recs[0]["unit"], recs[0]["display_precision"], recs[0]["precision"]) == ("m", 2, 0)
    assert recs[1]["display_precision"] == 1 and "unit" not in recs[1]
    assert recs[3]["precision"] == 3 and "display_precision" not in recs[3]
    assert recs[4]["precision"] == 0 and "display_precision" not in recs[4]
    dlg2 = AttributesEditorDialog(w)
    assert _cell(dlg2, 0, "unit").currentText() == "Metric (m)"
    assert _cell(dlg2, 0, "precision").currentText() == "2"
    assert _cell(dlg2, 3, "precision").currentText() == "3"
    dlg2.set_cell(0, "unit", "")                   # back to Per project settings
    dlg2.set_cell(0, "precision", "")
    assert dlg2.try_accept() is True
    rec = w.editor_scene.block_meta["attributes"][0]
    assert "unit" not in rec and "display_precision" not in rec and rec["precision"] == 0
