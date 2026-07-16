"""Gridline dialog dimension-input normalization (user-reported 2026-07-14).

Typing a bare number in a table cell (or the Default Length / Quick Fill
Spacing fields) must commit through the canonical DimensionEdit path:
display re-formats to project units, the exact mm value lands in the
UserRole+1 slot, and invalid input reverts (property-panel.md §3.8,
units-and-formatting.md §3, grid-system.md §7.3).

Tests exercise the real delegate/editor commit path, not source inspection.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from PyQt6.QtCore import Qt

from firepro3d.grid_lines_dialog import _DirectionTab
from firepro3d.dimension_edit import DimensionEdit, DimensionDelegate
from firepro3d.scale_manager import ScaleManager, DisplayUnit

ROLE = Qt.ItemDataRole.UserRole + 1

COL_OFFSET = 1
COL_SPACING = 2
COL_LENGTH = 3
COL_ANGLE = 4


def _make_sm(unit: DisplayUnit) -> ScaleManager:
    sm = ScaleManager()
    sm.display_unit = unit
    return sm


def _commit_cell(tab: _DirectionTab, row: int, col: int, text: str,
                 *, via_enter: bool = False):
    """Drive the real delegate edit path: open editor, type, commit.

    Default simulates the **Tab** path: Qt calls setModelData *before*
    the editor's editingFinished signal fires (user-reported regression
    2026-07-16 — the typed value reverted on Tab). ``via_enter=True``
    simulates Return/focus-out, where editingFinished fires first.
    """
    table = tab._table
    index = table.model().index(row, col)
    delegate = table.itemDelegateForColumn(col)
    assert isinstance(delegate, DimensionDelegate), (
        f"column {col} must use the DimensionDelegate")
    editor = delegate.createEditor(table, None, index)
    delegate.setEditorData(editor, index)
    editor.setText(text)
    if via_enter:
        editor.editingFinished.emit()      # DimensionEdit parse/revert
    delegate.setModelData(editor, table.model(), index)
    editor.deleteLater()


@pytest.fixture
def imperial_tab(qapp):
    tab = _DirectionTab("V", scale_manager=_make_sm(DisplayUnit.IMPERIAL))
    tab._add_row()   # row 0 at offset 0
    tab._add_row()   # row 1
    tab._reset_history()   # setup rows are the undo baseline
    return tab


@pytest.fixture
def metric_tab(qapp):
    tab = _DirectionTab("V", scale_manager=_make_sm(DisplayUnit.METRIC_MM))
    tab._add_row()
    tab._add_row()
    tab._reset_history()   # setup rows are the undo baseline
    return tab


class TestTabCommit:
    """Tab-to-next-cell must confirm the typed value (regression 2026-07-16)."""

    def test_tab_commit_persists_typed_value(self, metric_tab):
        _commit_cell(metric_tab, 1, COL_OFFSET, "250")   # Tab path (no emit)
        item = metric_tab._table.item(1, COL_OFFSET)
        assert item.data(ROLE) == pytest.approx(250.0)
        assert item.text() == metric_tab._sm.format_length(250.0)

    def test_enter_commit_still_works(self, metric_tab):
        _commit_cell(metric_tab, 1, COL_OFFSET, "250", via_enter=True)
        item = metric_tab._table.item(1, COL_OFFSET)
        assert item.data(ROLE) == pytest.approx(250.0)

    def test_double_commit_does_not_drift(self, imperial_tab):
        # commit() runs on Tab AND editingFinished may fire later on
        # focus-out; the seed guard must keep the exact value.
        _commit_cell(imperial_tab, 1, COL_OFFSET, "100", via_enter=True)
        item = imperial_tab._table.item(1, COL_OFFSET)
        assert item.data(ROLE) == pytest.approx(30480.0)


class TestUndoRedo:
    """In-dialog Ctrl+Z/Y over table state (user-requested 2026-07-16)."""

    def test_undo_cell_edit_restores_value_and_text(self, metric_tab):
        before_text = metric_tab._table.item(1, COL_OFFSET).text()
        _commit_cell(metric_tab, 1, COL_OFFSET, "999")
        metric_tab.undo()
        item = metric_tab._table.item(1, COL_OFFSET)
        assert item.text() == before_text

    def test_undo_restores_synced_spacing_too(self, metric_tab):
        sp_before = metric_tab._table.item(1, COL_SPACING).text()
        _commit_cell(metric_tab, 1, COL_OFFSET, "999")
        assert metric_tab._table.item(1, COL_SPACING).text() != sp_before
        metric_tab.undo()
        assert metric_tab._table.item(1, COL_SPACING).text() == sp_before

    def test_redo_reapplies_edit(self, metric_tab):
        _commit_cell(metric_tab, 1, COL_OFFSET, "999")
        edited_text = metric_tab._table.item(1, COL_OFFSET).text()
        metric_tab.undo()
        metric_tab.redo()
        item = metric_tab._table.item(1, COL_OFFSET)
        assert item.text() == edited_text
        assert item.data(ROLE) == pytest.approx(999.0)

    def test_undo_add_row(self, metric_tab):
        assert metric_tab._table.rowCount() == 2
        metric_tab._add_row()
        metric_tab._flush_pending_record()
        assert metric_tab._table.rowCount() == 3
        metric_tab.undo()
        assert metric_tab._table.rowCount() == 2

    def test_undo_generate_array(self, metric_tab):
        metric_tab._qf_count.setValue(5)
        metric_tab._generate_array()
        metric_tab._flush_pending_record()
        assert metric_tab._table.rowCount() == 5
        metric_tab.undo()
        assert metric_tab._table.rowCount() == 2

    def test_two_edits_two_undo_steps(self, metric_tab):
        base = metric_tab._table.item(1, COL_OFFSET).text()
        _commit_cell(metric_tab, 1, COL_OFFSET, "500")
        metric_tab._flush_pending_record()
        _commit_cell(metric_tab, 1, COL_OFFSET, "900")
        metric_tab.undo()
        assert metric_tab._table.item(1, COL_OFFSET).data(ROLE) == pytest.approx(500.0)
        metric_tab.undo()
        assert metric_tab._table.item(1, COL_OFFSET).text() == base

    def test_undo_at_baseline_is_noop(self, metric_tab):
        rows = metric_tab._table.rowCount()
        metric_tab.undo()
        assert metric_tab._table.rowCount() == rows

    def test_populate_resets_history(self, qapp):
        tab = _DirectionTab("V", scale_manager=_make_sm(DisplayUnit.METRIC_MM))
        tab.populate([("A", 0.0, 1000.0, 90.0), ("B", 500.0, 1000.0, 90.0)])
        tab.undo()   # nothing to undo — populate is the baseline
        assert tab._table.rowCount() == 2

    def test_backing_refs_survive_undo(self, qapp):
        from unittest.mock import MagicMock
        sentinel = MagicMock()
        sentinel._locked = False
        tab = _DirectionTab("V", scale_manager=_make_sm(DisplayUnit.METRIC_MM))
        tab.populate([("A", 0.0, 1000.0, 90.0, sentinel)])
        _commit_cell(tab, 0, COL_OFFSET, "250")
        tab.undo()
        assert tab.read_rows()[0][4] is sentinel

    def test_dialog_ctrl_z_routes_to_active_tab(self, qapp):
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent
        from firepro3d.grid_lines_dialog import GridLinesDialog
        dlg = GridLinesDialog(scale_manager=_make_sm(DisplayUnit.METRIC_MM))
        tab = dlg._tabs.currentWidget()
        tab._add_row()
        tab._flush_pending_record()
        assert tab._table.rowCount() == 1
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z,
                       Qt.KeyboardModifier.ControlModifier)
        dlg.keyPressEvent(ev)
        assert tab._table.rowCount() == 0
        ev_y = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Y,
                         Qt.KeyboardModifier.ControlModifier)
        dlg.keyPressEvent(ev_y)
        assert tab._table.rowCount() == 1


class TestCellNormalization:
    """The reported bug: raw typed text must re-format to project units."""

    def test_offset_bare_number_formats_imperial(self, imperial_tab):
        sm = imperial_tab._sm
        _commit_cell(imperial_tab, 1, COL_OFFSET, "100")
        item = imperial_tab._table.item(1, COL_OFFSET)
        # bare number in imperial = feet → 30480 mm, displayed formatted
        assert item.data(ROLE) == pytest.approx(30480.0)
        assert item.text() == sm.format_length(30480.0)
        assert item.text() != "100"

    def test_offset_bare_number_formats_metric(self, metric_tab):
        sm = metric_tab._sm
        _commit_cell(metric_tab, 1, COL_OFFSET, "100")
        item = metric_tab._table.item(1, COL_OFFSET)
        assert item.data(ROLE) == pytest.approx(100.0)
        assert item.text() == sm.format_length(100.0)

    def test_length_cell_formats(self, imperial_tab):
        sm = imperial_tab._sm
        _commit_cell(imperial_tab, 0, COL_LENGTH, "72")
        item = imperial_tab._table.item(0, COL_LENGTH)
        assert item.data(ROLE) == pytest.approx(72 * 304.8)
        assert item.text() == sm.format_length(72 * 304.8)

    def test_explicit_unit_input_honoured(self, imperial_tab):
        # typing mm into an imperial project must still parse as mm
        _commit_cell(imperial_tab, 1, COL_OFFSET, "3048 mm")
        item = imperial_tab._table.item(1, COL_OFFSET)
        assert item.data(ROLE) == pytest.approx(3048.0)


class TestOffsetSpacingSync:
    def test_offset_edit_recalculates_spacing(self, metric_tab):
        _commit_cell(metric_tab, 1, COL_OFFSET, "250")
        sp = metric_tab._table.item(1, COL_SPACING)
        assert sp.data(ROLE) == pytest.approx(250.0)
        assert sp.text() == metric_tab._sm.format_length(250.0)

    def test_spacing_edit_recalculates_offset(self, metric_tab):
        _commit_cell(metric_tab, 1, COL_SPACING, "600")
        off = metric_tab._table.item(1, COL_OFFSET)
        assert off.data(ROLE) == pytest.approx(600.0)   # prev offset 0 + 600
        assert off.text() == metric_tab._sm.format_length(600.0)

    def test_read_rows_returns_exact_mm(self, metric_tab):
        _commit_cell(metric_tab, 1, COL_OFFSET, "1234.5")
        rows = metric_tab.read_rows()
        assert rows[1][1] == pytest.approx(1234.5)


class TestInvalidInputReverts:
    def test_garbage_offset_reverts(self, metric_tab):
        before_val = metric_tab._table.item(1, COL_OFFSET).data(ROLE)
        before_text = metric_tab._table.item(1, COL_OFFSET).text()
        _commit_cell(metric_tab, 1, COL_OFFSET, "abc")
        item = metric_tab._table.item(1, COL_OFFSET)
        assert item.data(ROLE) == pytest.approx(float(before_val))
        assert item.text() == before_text

    def test_garbage_angle_reverts_without_raising(self, metric_tab):
        item = metric_tab._table.item(0, COL_ANGLE)
        before = item.data(ROLE)
        item.setText("abc")   # fires cellChanged → col-4 handler
        assert item.text() == f"{float(before):.1f}"
        assert item.data(ROLE) == pytest.approx(float(before))

    def test_angle_valid_edit_normalizes(self, metric_tab):
        item = metric_tab._table.item(0, COL_ANGLE)
        item.setText("135")   # normalized to 45 (0–90 convention)
        assert item.text() == "45.0"
        assert item.data(ROLE) == pytest.approx(45.0)


class TestStandaloneFields:
    def test_fields_are_dimension_edits(self, imperial_tab):
        assert isinstance(imperial_tab._length_edit, DimensionEdit)
        assert isinstance(imperial_tab._qf_spacing_edit, DimensionEdit)

    def test_qf_spacing_normalizes_on_commit(self, imperial_tab):
        sm = imperial_tab._sm
        imperial_tab._qf_spacing_edit.setText("30")
        imperial_tab._qf_spacing_edit.editingFinished.emit()
        assert imperial_tab._qf_spacing_edit.value_mm() == pytest.approx(30 * 304.8)
        assert imperial_tab._qf_spacing_edit.text() == sm.format_length(30 * 304.8)

    def test_generate_array_uses_committed_spacing(self, qapp):
        tab = _DirectionTab("V", scale_manager=_make_sm(DisplayUnit.METRIC_MM))
        tab._qf_spacing_edit.setText("500")
        tab._qf_spacing_edit.editingFinished.emit()
        tab._qf_count.setValue(3)
        tab._generate_array()
        assert tab._table.rowCount() == 3
        assert tab._table.item(2, COL_OFFSET).data(ROLE) == pytest.approx(1000.0)


class TestSceneRoundTrip:
    """Length/offset must survive open → OK unchanged (user-reported
    2026-07-16: Length grew by the 6% bubble overshoot on every OK)."""

    @staticmethod
    def _scene_line(offset: float, length: float, angle: float):
        """Build a gridline QLineF exactly as apply_grid_dialog does."""
        import math as m
        from PyQt6.QtCore import QLineF, QPointF
        from firepro3d.constants import GRIDLINE_BUBBLE_OVERSHOOT_FRAC
        rad = m.radians(angle)
        dx, dy = m.cos(rad), -m.sin(rad)
        px, py = -dy, dx
        ox, oy = offset * px, -offset * py
        over = length * GRIDLINE_BUBBLE_OVERSHOOT_FRAC
        return QLineF(QPointF(ox - over * dx, oy - over * dy),
                      QPointF(ox + length * dx, oy + length * dy))

    def _round_trip(self, qapp, offset, length, angle):
        from unittest.mock import MagicMock
        from firepro3d.grid_lines_dialog import GridLinesDialog
        gl = MagicMock()
        gl.grid_label = "1"
        gl._locked = False
        gl.line.return_value = self._scene_line(offset, length, angle)
        dlg = GridLinesDialog(existing_gridlines=[gl])
        specs = [s for s in dlg.get_gridlines() if s["_backing"] is gl]
        assert len(specs) == 1
        return specs[0]

    def test_vertical_length_round_trips(self, qapp):
        spec = self._round_trip(qapp, offset=0.0, length=1000.0, angle=90.0)
        assert spec["length"] == pytest.approx(1000.0)
        assert spec["offset"] == pytest.approx(0.0, abs=1e-9)

    def test_horizontal_length_and_offset_round_trip(self, qapp):
        spec = self._round_trip(qapp, offset=2500.0, length=8000.0, angle=0.0)
        assert spec["length"] == pytest.approx(8000.0)
        assert spec["offset"] == pytest.approx(2500.0)

    def test_angled_gridline_round_trips(self, qapp):
        spec = self._round_trip(qapp, offset=1200.0, length=5000.0, angle=80.0)
        assert spec["length"] == pytest.approx(5000.0)
        assert spec["offset"] == pytest.approx(1200.0)
        assert spec["angle_deg"] == pytest.approx(80.0)

    def test_zero_length_line_does_not_crash(self, qapp):
        from unittest.mock import MagicMock
        from PyQt6.QtCore import QLineF, QPointF
        from firepro3d.grid_lines_dialog import GridLinesDialog
        gl = MagicMock()
        gl.grid_label = "1"
        gl._locked = False
        gl.line.return_value = QLineF(QPointF(5.0, 5.0), QPointF(5.0, 5.0))
        dlg = GridLinesDialog(existing_gridlines=[gl])
        assert dlg.get_gridlines()  # no ZeroDivisionError


class TestNoScaleManagerFallback:
    """_DirectionTab with no ScaleManager (existing test convention)."""

    def test_add_row_and_read_rows_still_work(self, qapp):
        tab = _DirectionTab("V")
        tab._add_row()
        rows = tab.read_rows()
        assert len(rows) == 1

    def test_cell_commit_falls_back_to_mm(self, qapp):
        tab = _DirectionTab("V")
        tab._add_row()
        tab._add_row()
        _commit_cell(tab, 1, COL_OFFSET, "100")
        item = tab._table.item(1, COL_OFFSET)
        assert item.data(ROLE) == pytest.approx(100.0)
        assert item.text() == "100.0 mm"
