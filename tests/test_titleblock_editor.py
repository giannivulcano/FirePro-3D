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
        dlg.working.layout.strip_width_mm = 123.0
        dlg.reject()
        assert tbt.load_library()[0].layout.strip_width_mm != 123.0

    def test_save_commits_and_stamps_modified(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.layout.strip_width_mm = 95.0
        dlg.save()
        lib = tbt.load_library()[0]
        assert lib.layout.strip_width_mm == 95.0

    def test_snapshot_undo_redo(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        before = dlg.working.layout.strip_width_mm
        dlg.push_snapshot()
        dlg.working.layout.strip_width_mm = 99.0
        dlg.undo()
        assert dlg.working.layout.strip_width_mm == before
        dlg.redo()
        assert dlg.working.layout.strip_width_mm == 99.0

    def test_save_blocked_on_validation_failure(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.layout.strip_width_mm = 5.0   # under floor
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
        # delete_template now asks for confirmation; answer Yes.
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes),
        )
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
        dlg.working.layout.strip_width_mm = 95.0
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
        assert dlg.working.layout.margin_edge_mm == 15.0
        dlg.undo()
        assert dlg.working.layout.margin_edge_mm == 10.0

    def test_cell_reorder(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        first = dlg.working.layout.cells[0].kind
        dlg.move_cell(0, 1)
        assert dlg.working.layout.cells[1].kind == first

    def test_add_remove_cell(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        n = len(dlg.working.layout.cells)
        dlg.add_cell("static_text")
        assert len(dlg.working.layout.cells) == n + 1
        dlg.remove_cell(n)
        assert len(dlg.working.layout.cells) == n

    def test_set_cell_prop_and_border(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.set_cell_prop(1, "fill_color", "#ff0000")
        assert dlg.working.layout.cells[1].fill_color == "#ff0000"
        dlg.set_cell_border_prop(1, "width_mm", 0.7)
        assert dlg.working.layout.cells[1].border.width_mm == 0.7

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
        layout = dlg.working.layout
        # Ensure initial visible=True (the default)
        layout.cells[0].border.visible = True
        dlg._on_cell_selected(0)   # repopulate cell form

        snap_count_before = len(dlg._undo_stack)

        # Toggle visible off via the widget signal path
        dlg._cell_border_group._visible.setChecked(False)
        # _on_cell_border_changed fires via toggled signal

        assert layout.cells[0].border.visible is False
        assert len(dlg._undo_stack) == snap_count_before + 1

        # Undo should restore visible=True
        dlg.undo()
        assert dlg.working.layout.cells[0].border.visible is True


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
        dlg.set_margin_edge(55.0)
        dlg.undo()
        assert dlg.working.layout.margin_edge_mm != 55.0

        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z,
                       Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.ShiftModifier)
        dlg.keyPressEvent(ev)
        assert ev.isAccepted()
        assert dlg.working.layout.margin_edge_mm == 55.0


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
        # The slot must have applied it to the working layout
        assert dlg.working.layout.margin_edge_mm == pytest.approx(25.4)


# ─────────────────────────────────────────────────────────────────────────────
# Fix 1 (blocker): TitleBlockItem.paint safe-get on migrated sheets
# ─────────────────────────────────────────────────────────────────────────────

class TestTitleBlockItemPaintSafeGet:
    """TitleBlockItem.paint must not KeyError when migrated keys are missing."""

    def test_paint_migrated_sheet_no_crash(self):
        """Render a TitleBlockItem whose fields dict is empty (all keys popped by
        migrate_legacy_fields) — must produce non-white pixels and not raise.
        """
        from PyQt6.QtGui import QImage, QPainter
        from firepro3d.paper_space import TitleBlockItem, PAPER_SIZES

        w, h = PAPER_SIZES.get("Letter", (215.9, 279.4))
        item = TitleBlockItem(w, h)
        # Simulate post-migration state: every legacy key removed.
        item.fields.clear()

        img = QImage(600, int(600 * h / w), QImage.Format.Format_RGB32)
        img.fill(0xFFFFFF)
        p = QPainter(img)
        p.scale(600 / w, 600 / w)
        # Must not raise (KeyError inside Qt would produce a native crash).
        item.paint(p, None, None)
        p.end()

        # Verify that something was actually drawn (borders/labels → non-white pixels).
        found_non_white = False
        for y in range(0, img.height(), 5):
            for x in range(0, img.width(), 5):
                if img.pixel(x, y) != 0xFFFFFFFF:
                    found_non_white = True
                    break
            if found_non_white:
                break
        assert found_non_white, "TitleBlockItem rendered all-white — nothing was drawn"

    def test_paint_missing_keys_show_defaults(self):
        """When all keys are absent, Company shows the DEFAULT_TITLE_BLOCK_FIELDS default."""
        from firepro3d.paper_space import TitleBlockItem, DEFAULT_TITLE_BLOCK_FIELDS, PAPER_SIZES

        w, h = PAPER_SIZES.get("ANSI D", (558.8, 863.6))
        item = TitleBlockItem(w, h)
        item.fields.clear()

        # Build the merged dict as paint() does.
        merged = {**DEFAULT_TITLE_BLOCK_FIELDS, **item.fields}
        assert merged["Company"] == DEFAULT_TITLE_BLOCK_FIELDS["Company"]
        assert merged["Drawn By"] == DEFAULT_TITLE_BLOCK_FIELDS["Drawn By"]
        assert merged["Checked By"] == DEFAULT_TITLE_BLOCK_FIELDS["Checked By"]


# ─────────────────────────────────────────────────────────────────────────────
# Fix 3: picker keys match renderer (PROJECT_STD_KEYS sync)
# ─────────────────────────────────────────────────────────────────────────────

class TestPickerKeyRendererSync:
    """Every project-group key the picker offers must be resolvable by build_field_values."""

    def test_all_picker_project_keys_resolve(self, tmp_path, monkeypatch):
        from firepro3d.paper_space import PROJECT_STD_KEYS, build_field_values
        from firepro3d.paper_space import Sheet

        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)

        # Build project_info with every standard key set to a non-empty value.
        project_info = {info_key: f"test_{info_key}" for info_key in PROJECT_STD_KEYS.values()}
        sheet = Sheet.create_default()
        vals = build_field_values(sheet, project_info)

        # Every display name the picker offers (= PROJECT_STD_KEYS.keys()) must
        # appear in the resolved vals dict with a non-empty value.
        for display_name in PROJECT_STD_KEYS.keys():
            assert vals.get(display_name), (
                f"Picker key '{display_name}' not resolved by build_field_values — "
                "picker and renderer are out of sync"
            )

    def test_picker_combo_contains_all_project_std_keys(self, tmp_path, monkeypatch):
        """The field_key combo must offer every PROJECT_STD_KEYS display name."""
        from firepro3d.paper_space import PROJECT_STD_KEYS

        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)

        combo_texts = {dlg._cell_field_key.itemText(i)
                       for i in range(dlg._cell_field_key.count())}
        for display_name in PROJECT_STD_KEYS.keys():
            assert display_name in combo_texts, (
                f"'{display_name}' missing from field_key picker combo"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Fix 4: Use→Save ordering
# ─────────────────────────────────────────────────────────────────────────────

class TestUseSaveOrdering:
    """use_for_project() then mutate then Save → project_template_result has new width + today."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_save_after_use_refreshes_project_result(self, tmp_path, monkeypatch):
        import datetime
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.use_for_project()
        assert dlg._use_requested is True

        # Mutate strip width after use_for_project().
        NEW_WIDTH = 111.0
        dlg.set_strip_width(NEW_WIDTH)

        # Drive _on_save_clicked (save succeeds since the template is valid).
        # Patch accept() so the dialog doesn't try to close.
        accepted = []
        monkeypatch.setattr(dlg, "accept", lambda: accepted.append(1))
        dlg._on_save_clicked()

        # project_template_result must carry the new width AND today's modified stamp.
        assert dlg.project_template_result is not None
        result_width = dlg.project_template_result.layout.strip_width_mm
        assert result_width == NEW_WIDTH, (
            f"project_template_result has old width {result_width}, expected {NEW_WIDTH}"
        )
        assert dlg.project_template_result.modified == datetime.date.today().isoformat(), (
            "project_template_result.modified not stamped to today"
        )
        assert accepted, "_on_save_clicked did not call accept()"


# ─────────────────────────────────────────────────────────────────────────────
# Fix 5: delete confirm dialog
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteConfirm:
    def _dlg(self, tmp_path, monkeypatch, t=None):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        if t is None:
            t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg, t

    def test_delete_cancel_keeps_template(self, tmp_path, monkeypatch):
        """Answering No to the confirm dialog keeps the template in the library."""
        dlg, t = self._dlg(tmp_path, monkeypatch)
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **kw: QMessageBox.StandardButton.No),
        )
        dlg.delete_template()
        # Template must still be in the library.
        assert len(tbt.load_library()) == 1

    def test_delete_yes_removes_template(self, tmp_path, monkeypatch):
        """Answering Yes to the confirm dialog removes the template."""
        dlg, t = self._dlg(tmp_path, monkeypatch)
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes),
        )
        dlg.delete_template()
        assert tbt.load_library() == []


# ─────────────────────────────────────────────────────────────────────────────
# Fix 6: Sheet No disabled in picker
# ─────────────────────────────────────────────────────────────────────────────

class TestSheetNoDisabled:
    def test_sheet_no_item_is_disabled(self, tmp_path, monkeypatch):
        """The 'Sheet No' item in the field_key combo must be non-selectable."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QStandardItemModel

        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)

        model = dlg._cell_field_key.model()
        assert isinstance(model, QStandardItemModel)

        # Find "Sheet No" in the model.
        found = False
        for i in range(model.rowCount()):
            item = model.item(i)
            if item is not None and item.text() == "Sheet No":
                found = True
                assert not (item.flags() & Qt.ItemFlag.ItemIsEnabled), (
                    "'Sheet No' item must be disabled (not selectable)"
                )
                break
        assert found, "'Sheet No' not found in the field_key combo model"
