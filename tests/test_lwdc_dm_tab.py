"""LW-DC-2 / LW-DC-3 / LW-DC-6 -- Display Manager Line Weights tab: DEFAULTS and
CUSTOM sections, locked Default names, accent + per-row reset (real widgets,
settings isolated by conftest)."""
import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractItemDelegate, QApplication, QLineEdit

from firepro3d import paper_display as pd
from firepro3d import theme as th
from firepro3d.display_manager import DisplayManager
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef

_LW_TAB = 2


def _row(d, name):
    return next(r for r, lw in d._lw_row_def.items() if lw.name == name)


@pytest.fixture
def dm(qapp):
    pd.set_project_line_weights([*pd.DEFAULT_LINE_WEIGHTS,
                                 LineWeightDef("Pen X", 0.40)])
    d = DisplayManager(Model_Space(), active_context="paper")
    d._tabs.setCurrentIndex(_LW_TAB)
    d.show()
    yield d
    d.reject()
    d.close()


def _edit_cell(d, row, col, text):
    """Real in-place edit: open the editor, type, commit with Enter."""
    tbl = d._lw_table
    tbl.setCurrentCell(row, col)
    tbl.editItem(tbl.item(row, col))
    editor = tbl.viewport().findChild(QLineEdit)
    assert editor is not None
    editor.selectAll()
    QTest.keyClicks(editor, text)
    # Enter's own work: the delegate writes the editor into the model
    # (QTest key events do not reach the editor's commit filter here).
    tbl.commitData(editor)
    tbl.closeEditor(editor, QAbstractItemDelegate.EndEditHint.NoHint)
    # flush the editor's deleteLater so a second edit finds a fresh editor
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_section_headers_present_and_inert(dm):
    tbl = dm._lw_table
    assert tbl.columnCount() == 4
    assert tbl.item(0, 0).text() == "DEFAULTS"
    assert tbl.item(8, 0).text() == "CUSTOM"
    assert tbl.rowCount() == 7 + 1 + 1 + 1
    for r in (0, 8):
        assert tbl.item(r, 0).flags() == Qt.ItemFlag.ItemIsEnabled
        assert tbl.columnSpan(r, 0) == 4
        assert tbl.item(r, 0).font().bold()
        assert r not in dm._lw_row_def
    assert [tbl.item(r, 0).text() for r in range(1, 8)] == [
        d.name for d in sorted(pd.DEFAULT_LINE_WEIGHTS,
                               key=lambda d: d.width_mm)]
    assert tbl.item(9, 0).text() == "Pen X"
    # a header row never maps to a weight, so a forced cell change is ignored
    before = [d.copy() for d in dm._lw_defs]
    dm._on_lw_cell_changed(0, 0)
    assert [(d.name, d.width_mm) for d in dm._lw_defs] == [
        (d.name, d.width_mm) for d in before]


def test_default_name_is_locked_custom_name_is_not(dm):
    tbl = dm._lw_table
    fine = tbl.item(_row(dm, "Fine"), 0)
    assert not fine.flags() & Qt.ItemFlag.ItemIsEditable
    assert tbl.item(_row(dm, "Fine"), 1).flags() & Qt.ItemFlag.ItemIsEditable
    assert tbl.item(_row(dm, "Fine"), 2).flags() & Qt.ItemFlag.ItemIsEditable
    assert tbl.item(_row(dm, "Pen X"), 0).flags() & Qt.ItemFlag.ItemIsEditable
    # forced change (a programmatic setText bypasses the flag) is refused
    fine.setText("Bold")
    assert "Fine" in pd.weight_names() and "Bold" not in pd.weight_names()
    assert tbl.item(_row(dm, "Fine"), 0).text() == "Fine"


def test_width_edit_shows_accent_and_reset_button(dm):
    tbl = dm._lw_table
    accent = th.detect().color("accent")
    row = _row(dm, "Fine")
    assert tbl.cellWidget(row, 3) is None
    assert tbl.item(row, 1).foreground().color() != accent
    _edit_cell(dm, row, 1, "0.30")
    row = _row(dm, "Fine")
    assert pd.resolve_line_weight_mm("Fine") == pytest.approx(0.30)
    assert tbl.item(row, 1).foreground().color() == accent
    assert tbl.item(row, 2).foreground().color() != accent    # px untouched
    assert tbl.cellWidget(row, 3) is not None
    assert tbl.cellWidget(row, 3).toolTip() == "Reset to default"
    # only the edited row carries a reset button
    assert sum(tbl.cellWidget(r, 3) is not None for r in dm._lw_row_def) == 1


def test_px_edit_shows_accent(dm):
    tbl = dm._lw_table
    row = _row(dm, "Wide")
    _edit_cell(dm, row, 2, "9")
    row = _row(dm, "Wide")
    assert tbl.item(row, 2).foreground().color() == th.detect().color("accent")
    assert tbl.cellWidget(row, 3) is not None


def test_reset_button_restores_factory_and_emits(dm):
    tbl = dm._lw_table
    _edit_cell(dm, _row(dm, "Fine"), 1, "0.30")
    _edit_cell(dm, _row(dm, "Fine"), 2, "9")
    fired = []
    dm.lineWeightsChanged.connect(lambda: fired.append(1))
    btn = tbl.cellWidget(_row(dm, "Fine"), 3)
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    fine = next(d for d in pd.project_line_weights() if d.name == "Fine")
    assert (fine.width_mm, fine.model_px) == (0.25, 3)
    assert fired
    row = _row(dm, "Fine")
    assert tbl.item(row, 1).text() == "0.25" and tbl.item(row, 2).text() == "3"
    assert tbl.cellWidget(row, 3) is None


def test_context_menu_reset(dm):
    row = _row(dm, "Medium")
    menu = dm._lw_row_menu(row)
    act = next(a for a in menu.actions() if a.text() == "Reset to default")
    assert not act.isEnabled()                     # already factory
    _edit_cell(dm, row, 1, "0.45")
    menu = dm._lw_row_menu(_row(dm, "Medium"))
    act = next(a for a in menu.actions() if a.text() == "Reset to default")
    assert act.isEnabled()
    act.trigger()
    assert pd.resolve_line_weight_mm("Medium") == pytest.approx(0.35)
    assert dm._lw_row_menu(0) is None                       # header row
    assert dm._lw_row_menu(_row(dm, "Pen X")) is None       # Custom row


def test_dialog_reset_restores_defaults_keeps_custom(dm):
    _edit_cell(dm, _row(dm, "Fine"), 1, "0.30")
    dm._reset_all()
    rows = {d.name: (d.width_mm, d.model_px) for d in pd.project_line_weights()}
    assert rows["Fine"] == (0.25, 3)
    assert rows["Pen X"] == (0.40, None)
    assert len(rows) == 8
    assert dm._lw_table.item(_row(dm, "Pen X"), 0).text() == "Pen X"


def test_remove_only_on_custom_rows(dm):
    tbl = dm._lw_table
    for r in (0, _row(dm, "Fine"), 8):
        tbl.setCurrentCell(r, 0)
        assert not dm._lw_remove_btn.isEnabled(), r
    tbl.setCurrentCell(_row(dm, "Pen X"), 0)
    assert dm._lw_remove_btn.isEnabled()
    # a forced remove on a Default row deletes nothing
    unused = next(d.name for d in pd.DEFAULT_LINE_WEIGHTS
                  if not dm._line_weight_in_use(d.name))   # in-use refusal != lock
    tbl.setCurrentCell(_row(dm, unused), 0)
    dm._on_lw_remove()
    assert unused in pd.weight_names()
    tbl.setCurrentCell(_row(dm, "Pen X"), 0)
    dm._on_lw_remove()
    assert "Pen X" not in pd.weight_names()


def test_add_appends_to_custom_section(dm):
    dm._on_lw_add()
    tbl = dm._lw_table
    names = [lw.name for _r, lw in sorted(dm._lw_row_def.items())]
    assert names[:7] == [d.name for d in sorted(pd.DEFAULT_LINE_WEIGHTS,
                                                key=lambda d: d.width_mm)]
    assert any(n.startswith("Custom ") for n in names[7:])
    assert tbl.item(8, 0).text() == "CUSTOM"


def test_custom_name_may_not_equal_a_default_name(dm):
    row = _row(dm, "Pen X")
    dm._lw_table.item(row, 0).setText("Medium")             # refused
    assert "Pen X" in pd.weight_names()
    assert sum(n == "Medium" for n in pd.weight_names()) == 1
    assert dm._lw_table.item(_row(dm, "Pen X"), 0).text() == "Pen X"


# -- T7 review minors ----------------------------------------------------------

def _current_def(d):
    return d._lw_row_def.get(d._lw_table.currentRow())


def test_current_row_survives_a_resorting_edit(dm):
    tbl = dm._lw_table
    tbl.setCurrentCell(_row(dm, "Pen X"), 0)
    pen = dm._lw_row_def[_row(dm, "Pen X")]
    _edit_cell(dm, _row(dm, "Pen X"), 1, "0.95")        # re-sorts below Thick
    assert _current_def(dm) is pen
    assert tbl.currentRow() == _row(dm, "Pen X")
    assert dm._lw_remove_btn.isEnabled()
    _edit_cell(dm, _row(dm, "Pen X"), 0, "Pen Y")       # rename keeps it too
    assert _current_def(dm) is pen and dm._lw_remove_btn.isEnabled()


def test_added_weight_becomes_current(dm):
    dm._on_lw_add()
    cur = _current_def(dm)
    assert cur is not None and cur.name.startswith("Custom ")
    assert dm._lw_table.currentRow() == _row(dm, cur.name)
    assert dm._lw_remove_btn.isEnabled()


def test_auto_model_px_default_shows_accent_and_reset_restores_int(dm):
    tbl = dm._lw_table
    _edit_cell(dm, _row(dm, "Wide"), 2, "auto")
    wide = next(d for d in pd.project_line_weights() if d.name == "Wide")
    assert wide.model_px is None
    row = _row(dm, "Wide")
    assert tbl.item(row, 2).foreground().color() == th.detect().color("accent")
    btn = tbl.cellWidget(row, 3)
    assert btn is not None
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    wide = next(d for d in pd.project_line_weights() if d.name == "Wide")
    assert wide.model_px == 5 and isinstance(wide.model_px, int)
    assert tbl.cellWidget(_row(dm, "Wide"), 3) is None


def test_accent_follows_the_displayed_width(dm):
    tbl = dm._lw_table
    accent = th.detect().color("accent")
    row = _row(dm, "Fine")
    _edit_cell(dm, row, 1, "0.254")                      # shows 0.25 == factory
    row = _row(dm, "Fine")
    assert tbl.item(row, 1).text() == "0.25"
    assert tbl.item(row, 1).foreground().color() != accent
    assert tbl.cellWidget(row, 3) is None
    _edit_cell(dm, row, 1, "0.26")                       # shows 0.26: differs
    row = _row(dm, "Fine")
    assert tbl.item(row, 1).foreground().color() == accent
    assert tbl.cellWidget(row, 3) is not None
