"""Editor behavior: working copy, save/cancel, snapshot undo, library actions."""
from unittest.mock import patch, MagicMock

from PyQt6.QtWidgets import QApplication, QMessageBox

import firepro3d.titleblock_template as tbt
from firepro3d.titleblock_template import make_default_template
from firepro3d.titleblock_editor import TitleBlockEditorDialog

_app = QApplication.instance() or QApplication([])


class TestEditorSession:
    def _dlg(self, tmp_path, monkeypatch, template=None):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        if template:
            tbt.save_to_library(template)
        return TitleBlockEditorDialog(project_template=None)

    def test_cancel_discards(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.variants["ANSI D"].strip_width_mm = 123.0
        dlg.reject()
        assert tbt.load_library()[0].variants["ANSI D"].strip_width_mm != 123.0

    def test_save_commits_and_stamps_modified(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.variants["ANSI D"].strip_width_mm = 95.0
        dlg.save()
        lib = tbt.load_library()[0]
        assert lib.variants["ANSI D"].strip_width_mm == 95.0

    def test_snapshot_undo_redo(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        before = dlg.working.variants["ANSI D"].strip_width_mm
        dlg.push_snapshot()
        dlg.working.variants["ANSI D"].strip_width_mm = 99.0
        dlg.undo()
        assert dlg.working.variants["ANSI D"].strip_width_mm == before
        dlg.redo()
        assert dlg.working.variants["ANSI D"].strip_width_mm == 99.0

    def test_save_blocked_on_validation_failure(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.variants["ANSI D"].strip_width_mm = 5.0   # under floor
        dlg.refresh_preview()
        assert not dlg.save_button.isEnabled()

    def test_new_duplicate_save(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.new_template()
        assert len(tbt.load_library()) == 0        # library untouched until save
        dlg.save()
        assert len(tbt.load_library()) == 1
        dlg.duplicate_template()
        dlg.save()
        assert len(tbt.load_library()) == 2
        uuids = {t.uuid for t in tbt.load_library()}
        assert len(uuids) == 2

    def test_delete_template(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.delete_template()
        assert tbt.load_library() == []

    def test_use_for_project(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.use_for_project()
        assert dlg.project_template_result is not None
        assert dlg.project_template_result.uuid == t.uuid

    def test_save_stamps_modified_today(self, tmp_path, monkeypatch):
        import datetime
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.variants["ANSI D"].strip_width_mm = 95.0
        dlg.save()
        assert tbt.load_library()[0].modified == datetime.date.today().isoformat()


class TestEditorForm:
    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_margin_slot_snapshots_and_undo(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.set_margin_edge(15.0)
        assert dlg.working.variants[dlg._active_size].margin_edge_mm == 15.0
        dlg.undo()
        assert dlg.working.variants[dlg._active_size].margin_edge_mm == 10.0

    def test_cell_reorder(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        first = dlg.working.variants[dlg._active_size].cells[0].kind
        dlg.move_cell(0, 1)
        assert dlg.working.variants[dlg._active_size].cells[1].kind == first

    def test_add_remove_cell(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        n = len(dlg.working.variants[dlg._active_size].cells)
        dlg.add_cell("static_text")
        assert len(dlg.working.variants[dlg._active_size].cells) == n + 1
        dlg.remove_cell(n)
        assert len(dlg.working.variants[dlg._active_size].cells) == n

    def test_add_variant_copies_cells_independently(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.set_active_size("ANSI D")
        dlg.add_variant("A3")
        assert "A3" in dlg.working.variants
        a3 = dlg.working.variants["A3"]
        d = dlg.working.variants["ANSI D"]
        assert len(a3.cells) == len(d.cells)
        a3.cells[0].label = "changed"
        assert d.cells[0].label != "changed"

    def test_set_cell_prop_and_border(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.set_cell_prop(1, "fill_color", "#ff0000")
        assert dlg.working.variants[dlg._active_size].cells[1].fill_color == "#ff0000"
        dlg.set_cell_border_prop(1, "width_mm", 0.7)
        assert dlg.working.variants[dlg._active_size].cells[1].border.width_mm == 0.7

    def test_preview_uses_renderer_item(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.refresh_preview()
        kinds = [type(i).__name__ for i in dlg._preview_scene.items()]
        assert "TitleBlockTemplateItem" in kinds


# ─────────────────────────────────────────────────────────────────────────────
# Finding 1: modified-stamp preserved on failed save
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveFailedStampPreserved:
    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_failed_save_restores_old_modified_and_shows_warning(
            self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        old_modified = dlg.working.modified

        warnings_shown = []

        import firepro3d.titleblock_editor as te
        with patch.object(te, "save_to_library", side_effect=OSError("disk full")):
            with patch.object(QMessageBox, "warning",
                              side_effect=lambda *a, **kw: warnings_shown.append(a)):
                result = dlg.save()

        assert result is False
        assert dlg.working.modified == old_modified
        assert len(warnings_shown) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Finding 2: save_button initial state
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveButtonInitialState:
    def test_save_button_disabled_when_no_template_selected(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        # Empty library, no project template
        dlg = TitleBlockEditorDialog(project_template=None)
        assert not dlg.save_button.isEnabled()


# ─────────────────────────────────────────────────────────────────────────────
# Finding 3: cell-border wiring
# ─────────────────────────────────────────────────────────────────────────────

class TestCellBorderWiring:
    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_cell_border_visible_toggle_applies_and_snapshots(
            self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        # Select first cell
        dlg._cell_list.setCurrentRow(0)
        variant = dlg.working.variants[dlg._active_size]
        # Ensure initial visible=True (the default)
        variant.cells[0].border.visible = True
        dlg._on_cell_selected(0)   # repopulate cell form

        snap_count_before = len(dlg._undo_stack)

        # Toggle visible off via the widget signal path
        dlg._cell_border_group._visible.setChecked(False)
        # _on_cell_border_changed fires via toggled signal

        assert variant.cells[0].border.visible is False
        assert len(dlg._undo_stack) == snap_count_before + 1

        # Undo should restore visible=True
        dlg.undo()
        assert dlg.working.variants[dlg._active_size].cells[0].border.visible is True


# ─────────────────────────────────────────────────────────────────────────────
# Finding 4: set_name snapshots
# ─────────────────────────────────────────────────────────────────────────────

class TestSetNameUndoable:
    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_set_name_pushes_snapshot_and_undo_restores(
            self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        old_name = dlg.working.name
        dlg.set_name("X")
        assert dlg.working.name == "X"
        dlg.undo()
        assert dlg.working.name == old_name


# ─────────────────────────────────────────────────────────────────────────────
# Finding 5: Ctrl+Shift+Z redo
# ─────────────────────────────────────────────────────────────────────────────

class TestCtrlShiftZRedo:
    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_ctrl_shift_z_triggers_redo(self, tmp_path, monkeypatch):
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent, Qt

        dlg = self._dlg(tmp_path, monkeypatch)
        before = dlg.working.variants[dlg._active_size].strip_width_mm
        dlg.set_margin_edge(55.0)
        dlg.undo()
        assert dlg.working.variants[dlg._active_size].margin_edge_mm != 55.0

        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z,
                       Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.ShiftModifier)
        dlg.keyPressEvent(ev)
        assert ev.isAccepted()
        assert dlg.working.variants[dlg._active_size].margin_edge_mm == 55.0


# ─────────────────────────────────────────────────────────────────────────────
# Finding 6: parse_dimension (imperial input in margin DimensionEdit widget)
# ─────────────────────────────────────────────────────────────────────────────

class TestDimensionParserImperial:
    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_inch_input_in_margin_widget_parses_to_254mm(
            self, tmp_path, monkeypatch):
        import pytest
        dlg = self._dlg(tmp_path, monkeypatch)
        # Drive the margin DimensionEdit widget directly (same pattern as
        # test_grid_dialog_dimension_input.py: setText + editingFinished.emit)
        dlg._edge_edit.setText('1"')
        dlg._edge_edit.editingFinished.emit()
        assert dlg._edge_edit.value_mm() == pytest.approx(25.4)
        # The slot must have applied it to the working variant
        assert (dlg.working.variants[dlg._active_size].margin_edge_mm
                == pytest.approx(25.4))
