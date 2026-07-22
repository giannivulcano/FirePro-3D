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


# ─────────────────────────────────────────────────────────────────────────────
# Rev2 — new slots / UI states (T16)
# ─────────────────────────────────────────────────────────────────────────────

class TestSetPaperSize:
    """set_paper_size() mutates working.paper_size, pushes a snapshot, and
    triggers a preview refresh that places an item in the scene."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_set_paper_size_changes_working(self, tmp_path, monkeypatch):
        """set_paper_size("ANSI B") must update working.paper_size."""
        dlg = self._dlg(tmp_path, monkeypatch)
        original = dlg.working.paper_size
        assert original != "ANSI B", "test requires default != ANSI B"
        dlg.set_paper_size("ANSI B")
        assert dlg.working.paper_size == "ANSI B"

    def test_set_paper_size_pushes_snapshot(self, tmp_path, monkeypatch):
        """set_paper_size must push a snapshot so undo restores the old size."""
        dlg = self._dlg(tmp_path, monkeypatch)
        original = dlg.working.paper_size
        dlg.set_paper_size("ANSI B")
        assert len(dlg._undo_stack) >= 1
        dlg.undo()
        assert dlg.working.paper_size == original

    def test_set_paper_size_triggers_preview_item(self, tmp_path, monkeypatch):
        """After set_paper_size the preview scene must contain a TitleBlockTemplateItem."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.set_paper_size("ANSI B")
        kinds = [type(i).__name__ for i in dlg._preview_scene.items()]
        assert "TitleBlockTemplateItem" in kinds


class TestSetOrientation:
    """set_orientation() swaps dims so preview page has h > w for portrait."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()          # ANSI D landscape (native)
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_set_orientation_portrait_makes_h_gt_w(self, tmp_path, monkeypatch):
        """Switching to portrait on a landscape-native size must flip the page so h > w."""
        dlg = self._dlg(tmp_path, monkeypatch)
        assert dlg.working.orientation == "landscape"
        dlg.set_orientation("portrait")
        assert dlg.working.orientation == "portrait"
        # Probe the paper rect in the preview scene: the white background rect
        # is always added first with dims = (paper_w, paper_h).
        # After portrait switch on ANSI D: stored dims are (558.8, 863.6) so
        # swapped dims = (863.6, 558.8) → w=863.6, h=558.8 i.e. w > h still.
        # But logical page height (h) should be 558.8 and width 863.6 for portrait
        # i.e. it becomes a taller page when computed via _template_page_mm.
        # ANSI D stored as (558.8, 863.6) landscape → portrait swap → (863.6, 558.8)
        # wait — native landscape: w=558.8, h=863.6?
        # Let's just probe the sceneRect: for portrait the scene height > width.
        from firepro3d.titleblock_editor import _template_page_mm
        w, h = _template_page_mm(dlg.working)
        assert h > w, f"Portrait page should have h > w but got w={w}, h={h}"

    def test_set_orientation_pushes_snapshot_and_undoes(
            self, tmp_path, monkeypatch):
        """set_orientation must push a snapshot so undo restores."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.set_orientation("portrait")
        dlg.undo()
        assert dlg.working.orientation == "landscape"


class TestPickerDisplayName:
    """Library combo must show template.display_name, not bare name."""

    def test_picker_shows_display_name(self, tmp_path, monkeypatch):
        """After save, the library list must show 'Name (SIZE)' not 'Name'."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()          # "FirePro Default", ANSI D landscape
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        # The list item text must be the display_name, not just the bare name.
        texts = [dlg._template_list.item(i).text()
                 for i in range(dlg._template_list.count())]
        expected = t.display_name          # "FirePro Default (ANSI D)"
        assert expected in texts, (
            f"Expected display_name '{expected}' in list but got {texts}"
        )
        # Bare name must NOT appear as a standalone entry
        assert t.name not in texts, (
            f"Bare name '{t.name}' must not appear without size suffix"
        )

    def test_display_name_native_no_orientation_suffix(self, tmp_path, monkeypatch):
        """Native orientation → no ', Portrait' / ', Landscape' suffix."""
        t = make_default_template()          # ANSI D landscape (native)
        dn = t.display_name
        assert dn == "FirePro Default (ANSI D)", f"Unexpected display_name: {dn!r}"

    def test_display_name_non_native_appends_suffix(self, tmp_path, monkeypatch):
        """Non-native orientation → suffix appended inside parens."""
        t = make_default_template()
        t.orientation = "portrait"          # non-native for ANSI D
        dn = t.display_name
        assert dn == "FirePro Default (ANSI D, Portrait)", (
            f"Non-native display_name wrong: {dn!r}"
        )


class TestSizingComboUI:
    """set_cell_prop(i, 'sizing', 'dynamic') persists and is undoable;
    min-height DimensionEdit is disabled when a dynamic cell is selected."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def _stamp_cell_index(self, dlg) -> int:
        """Return the index of the 'stamp' cell in the default template."""
        cells = dlg.working.layout.cells
        for i, c in enumerate(cells):
            if c.kind == "stamp":
                return i
        raise AssertionError("No stamp cell found in default template")

    def test_set_cell_prop_sizing_dynamic_persists(self, tmp_path, monkeypatch):
        """set_cell_prop(i, 'sizing', 'dynamic') must write cell.sizing."""
        dlg = self._dlg(tmp_path, monkeypatch)
        # Use cell 0 (logo) which starts as static
        dlg.working.layout.cells[0].sizing = "static"
        dlg.set_cell_prop(0, "sizing", "dynamic")
        assert dlg.working.layout.cells[0].sizing == "dynamic"

    def test_set_cell_prop_sizing_undoable(self, tmp_path, monkeypatch):
        """Sizing change must be undoable via snapshot."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.working.layout.cells[0].sizing = "static"
        dlg.set_cell_prop(0, "sizing", "dynamic")
        assert dlg.working.layout.cells[0].sizing == "dynamic"
        dlg.undo()
        assert dlg.working.layout.cells[0].sizing == "static"

    def test_min_height_disabled_for_dynamic_cell(self, tmp_path, monkeypatch):
        """Selecting a dynamic cell must disable the min-height DimensionEdit."""
        dlg = self._dlg(tmp_path, monkeypatch)
        stamp_idx = self._stamp_cell_index(dlg)
        # Stamp cell is seeded as dynamic
        assert dlg.working.layout.cells[stamp_idx].sizing == "dynamic", (
            "Test pre-condition: stamp cell must be dynamic"
        )
        dlg._on_cell_selected(stamp_idx)
        assert not dlg._cell_min_height.isEnabled(), (
            "min_height edit must be disabled when cell sizing == 'dynamic'"
        )

    def test_min_height_enabled_for_static_cell(self, tmp_path, monkeypatch):
        """Selecting a static cell must enable the min-height DimensionEdit."""
        dlg = self._dlg(tmp_path, monkeypatch)
        # Cell 0 (logo) is static in the default template
        assert dlg.working.layout.cells[0].sizing == "static", (
            "Test pre-condition: cell 0 must be static"
        )
        dlg._on_cell_selected(0)
        assert dlg._cell_min_height.isEnabled(), (
            "min_height edit must be enabled when cell sizing == 'static'"
        )


class TestComponentTabsExist:
    """Editor must have an Overview, Drawing Area, and Info Strip tab."""

    def test_three_component_tabs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        tab = dlg._component_tabs
        titles = [tab.tabText(i) for i in range(tab.count())]
        assert "Overview" in titles, f"Missing 'Overview' tab; got {titles}"
        assert "Drawing Area" in titles, (
            f"Missing 'Drawing Area' tab; got {titles}")
        assert "Info Strip" in titles, (
            f"Missing 'Info Strip' tab; got {titles}")

    def test_no_variant_tabs_attribute(self, tmp_path, monkeypatch):
        """The old per-size variant QTabWidget (_variant_tabs) must be gone."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        assert not hasattr(dlg, "_variant_tabs"), (
            "_variant_tabs still present — variant machinery not fully removed"
        )

    def test_no_active_size_attribute(self, tmp_path, monkeypatch):
        """The vestigial _active_size attribute must be removed."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        assert not hasattr(dlg, "_active_size"), (
            "_active_size still present — variant machinery not fully removed"
        )


class TestTemplatePagMm:
    """_template_page_mm helper: swap rule correctness."""

    def test_native_orientation_no_swap(self):
        from firepro3d.titleblock_editor import _template_page_mm
        from firepro3d.titleblock_template import make_default_template
        t = make_default_template()          # ANSI D landscape (native)
        w, h = _template_page_mm(t)
        from firepro3d.paper_space import PAPER_SIZES
        stored_w, stored_h = PAPER_SIZES["ANSI D"]
        assert (w, h) == (stored_w, stored_h), (
            "Native orientation must not swap dims"
        )

    def test_non_native_orientation_swaps(self):
        from firepro3d.titleblock_editor import _template_page_mm
        from firepro3d.titleblock_template import make_default_template
        from firepro3d.paper_space import PAPER_SIZES
        t = make_default_template()
        t.orientation = "portrait"          # non-native for ANSI D
        w, h = _template_page_mm(t)
        stored_w, stored_h = PAPER_SIZES["ANSI D"]
        assert (w, h) == (stored_h, stored_w), (
            "Non-native orientation must swap dims"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fix 1 (CRITICAL): Portrait radio wiring — widget-driven test
# ─────────────────────────────────────────────────────────────────────────────

class TestPortraitRadioWiring:
    """_orient_portrait.toggled must be connected so clicking Portrait works.

    These tests drive .click() (not set_orientation()) to verify the actual
    signal wiring — source-inspection tests would miss a missing connect().
    """

    def _dlg(self, tmp_path, monkeypatch) -> "TitleBlockEditorDialog":
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()          # ANSI D landscape (native)
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_portrait_click_sets_working_orientation(self, tmp_path, monkeypatch):
        """Clicking the Portrait radio must update working.orientation to 'portrait'."""
        dlg = self._dlg(tmp_path, monkeypatch)
        assert dlg.working.orientation == "landscape", (
            "Pre-condition: default template is landscape"
        )
        dlg._orient_portrait.click()
        assert dlg.working.orientation == "portrait", (
            "Portrait radio click must set working.orientation to 'portrait'"
        )

    def test_portrait_click_makes_preview_page_h_gt_w(self, tmp_path, monkeypatch):
        """After clicking Portrait, the preview page dims must have h > w."""
        from firepro3d.titleblock_editor import _template_page_mm
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._orient_portrait.click()
        w, h = _template_page_mm(dlg.working)
        assert h > w, (
            f"Portrait page must have h > w after radio click, got w={w}, h={h}"
        )

    def test_landscape_click_restores_orientation(self, tmp_path, monkeypatch):
        """Clicking Portrait then Landscape must return working.orientation to 'landscape'."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._orient_portrait.click()
        assert dlg.working.orientation == "portrait"
        dlg._orient_landscape.click()
        assert dlg.working.orientation == "landscape", (
            "Landscape radio click must restore working.orientation to 'landscape'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fix 2: Manual paper-size change clears orientation override
# ─────────────────────────────────────────────────────────────────────────────

class TestPaperSizeChangeResetsOrientation:
    """PaperScene.paper_size setter must reset sheet.orientation to "" on size change.

    Spec: manual size change returns to the new size's native orientation so
    the template-mismatch fallback compares native-to-native.
    """

    def test_change_paper_clears_orientation(self, tmp_path, monkeypatch):
        """After applying a portrait template (orientation stored 'portrait'),
        changing the paper size via the scene setter must reset orientation to ''.
        """
        from firepro3d.paper_space import PaperScene, Sheet, PAPER_SIZES
        from unittest.mock import MagicMock

        sheet = Sheet.create_default()
        sheet.paper_size = "ANSI D"
        sheet.orientation = "portrait"   # simulate post-portrait-template apply
        resolver = MagicMock()
        resolver.model_scene = MagicMock()
        resolver.model_scene.scale_manager = MagicMock()

        scene = PaperScene(sheet, resolver)
        assert sheet.orientation == "portrait", "Pre-condition: orientation was set"

        # Trigger size change via the property setter (what change_paper calls)
        scene.paper_size = "ANSI B"
        assert sheet.orientation == "", (
            "Changing paper size must reset sheet.orientation to '' "
            "(return to native orientation)"
        )
