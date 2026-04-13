"""Tests for grid dialog identity tracking (Task 11)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from firepro3d.grid_lines_dialog import _DirectionTab, GridLinesDialog
from PyQt6.QtCore import Qt


class TestDirectionTabIdentity:
    """Verify hidden column 5 stores backing refs."""

    def test_table_has_6_columns(self, qapp):
        tab = _DirectionTab("V")
        assert tab._table.columnCount() == 6

    def test_column_5_hidden(self, qapp):
        tab = _DirectionTab("V")
        assert tab._table.isColumnHidden(5)

    def test_add_row_backing_none(self, qapp):
        tab = _DirectionTab("V")
        tab._add_row()
        bck = tab._table.item(0, 5)
        assert bck is not None
        assert bck.data(Qt.ItemDataRole.UserRole) is None

    def test_read_rows_returns_5_tuple(self, qapp):
        tab = _DirectionTab("V")
        tab._add_row()
        rows = tab.read_rows()
        assert len(rows) == 1
        assert len(rows[0]) == 5
        assert rows[0][4] is None

    def test_populate_with_backing(self, qapp):
        tab = _DirectionTab("V")
        sentinel = object()
        tab.populate([("A", 0.0, 100.0, 90.0, sentinel)])
        rows = tab.read_rows()
        assert rows[0][4] is sentinel

    def test_populate_without_backing_compat(self, qapp):
        tab = _DirectionTab("V")
        tab.populate([("B", 0.0, 100.0, 90.0)])
        rows = tab.read_rows()
        assert rows[0][4] is None

    def test_generate_clears_backing(self, qapp):
        tab = _DirectionTab("V")
        sentinel = object()
        tab.populate([("X", 0.0, 100.0, 90.0, sentinel)])
        tab._generate_array()
        for row in tab.read_rows():
            assert row[4] is None


class TestGetGridlinesIncludesBacking:
    """Verify GridLinesDialog.get_gridlines() includes _backing key."""

    def test_new_dialog_no_backing(self, qapp):
        dlg = GridLinesDialog()
        dlg._v_tab._add_row()
        specs = dlg.get_gridlines()
        assert len(specs) == 1
        assert "_backing" in specs[0]
        assert specs[0]["_backing"] is None

    def test_existing_gridlines_have_backing(self, qapp):
        from unittest.mock import MagicMock
        from PyQt6.QtCore import QLineF, QPointF
        gl = MagicMock()
        gl.grid_label = "1"
        gl.line.return_value = QLineF(QPointF(0, 0), QPointF(0, -1000))
        dlg = GridLinesDialog(existing_gridlines=[gl])
        specs = dlg.get_gridlines()
        assert len(specs) == 1
        assert specs[0]["_backing"] is gl
