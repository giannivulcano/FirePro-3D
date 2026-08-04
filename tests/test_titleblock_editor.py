"""Editor behavior: working copy, save/cancel, snapshot undo, library actions.

Rev-3 update: Info Strip tab removed; Fields tab added (DD-18). Tests for
cell-list, cell-form, and sizing-combo widgets removed accordingly. TestFieldsTab
covers the new Fields tab behavior.
"""
from unittest.mock import patch, MagicMock

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

import firepro3d.titleblock_template as tbt
from firepro3d.titleblock_template import make_default_template, place_field
from firepro3d.titleblock_editor import TitleBlockEditorDialog
from tests.test_titleblock_arrange import _drag_on_canvas, _mouse

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


class TestComponentTabsExist:
    """Editor must have Overview, Drawing Area, and Fields tabs (rev 3)."""

    def test_three_component_tabs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        tab = dlg._component_tabs
        titles = [tab.tabText(i) for i in range(tab.count())]
        assert "Overview" in titles, f"Missing 'Overview' tab; got {titles}"
        assert "Drawing Area" in titles, (
            f"Missing 'Drawing Area' tab; got {titles}")
        assert "Fields" in titles, (
            f"Missing 'Fields' tab; got {titles}")

    def test_no_info_strip_tab(self, tmp_path, monkeypatch):
        """The old Info Strip tab must be gone (replaced by Fields)."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        titles = [dlg._component_tabs.tabText(i)
                  for i in range(dlg._component_tabs.count())]
        assert "Info Strip" not in titles, (
            f"Info Strip tab must be removed in rev 3; got {titles}")

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


# ─────────────────────────────────────────────────────────────────────────────
# Smoke round-2 UI fixes
# ─────────────────────────────────────────────────────────────────────────────

class TestPreviewInOverviewTab:
    """Fix 2: _preview_view must be a descendant of the Overview tab page."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        return TitleBlockEditorDialog(project_template=None)

    def test_preview_view_inside_overview_tab(self, tmp_path, monkeypatch):
        """_preview_view must live inside the Overview tab widget."""
        from PyQt6.QtWidgets import QGraphicsView

        dlg = self._dlg(tmp_path, monkeypatch)
        overview_page = dlg._component_tabs.widget(0)
        assert overview_page is not None, "Overview tab (index 0) must exist"

        # Walk parent chain of _preview_view up to overview_page.
        widget = dlg._preview_view
        found = False
        while widget is not None:
            if widget is overview_page:
                found = True
                break
            widget = widget.parent()
        assert found, (
            "_preview_view is not a descendant of the Overview tab page — "
            "it must be placed inside the Overview tab (below Paper Setup)"
        )

    def test_overview_tab_is_index_0(self, tmp_path, monkeypatch):
        """Overview tab must be the first tab (index 0)."""
        dlg = self._dlg(tmp_path, monkeypatch)
        assert dlg._component_tabs.tabText(0) == "Overview", (
            "First component tab must be 'Overview'"
        )

    def test_no_standalone_preview_column(self, tmp_path, monkeypatch):
        """The dialog root layout must NOT have a standalone right-panel preview
        (i.e., _preview_view's top-level ancestor should be the Overview page,
        not the dialog itself)."""
        dlg = self._dlg(tmp_path, monkeypatch)
        # _preview_view.parent() must not be the dialog itself.
        assert dlg._preview_view.parent() is not dlg, (
            "_preview_view must not be a direct child of the dialog — "
            "it should be inside the Overview tab group box"
        )


class TestNameEditInPaperSetup:
    """Fix 3: _name_edit must be a descendant of the Paper Setup group box
    inside the Overview tab."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        return TitleBlockEditorDialog(project_template=None)

    def test_name_edit_inside_overview_tab(self, tmp_path, monkeypatch):
        """_name_edit must be a descendant of the Overview tab page."""
        dlg = self._dlg(tmp_path, monkeypatch)
        overview_page = dlg._component_tabs.widget(0)
        assert overview_page is not None

        widget = dlg._name_edit
        found = False
        while widget is not None:
            if widget is overview_page:
                found = True
                break
            widget = widget.parent()
        assert found, (
            "_name_edit is not inside the Overview tab — "
            "it must be the first row in the Paper Setup group box"
        )

    def test_name_edit_inside_paper_setup_group(self, tmp_path, monkeypatch):
        """_name_edit must be a descendant of a QGroupBox named 'Paper Setup'."""
        from PyQt6.QtWidgets import QGroupBox

        dlg = self._dlg(tmp_path, monkeypatch)
        overview_page = dlg._component_tabs.widget(0)
        assert overview_page is not None

        paper_setup_groups = [
            w for w in overview_page.findChildren(QGroupBox)
            if w.title() == "Paper Setup"
        ]
        assert paper_setup_groups, (
            "No QGroupBox titled 'Paper Setup' found in Overview tab"
        )
        paper_setup = paper_setup_groups[0]

        # _name_edit must be a descendant of paper_setup
        from PyQt6.QtWidgets import QLineEdit
        name_edits = paper_setup.findChildren(QLineEdit)
        assert dlg._name_edit in name_edits, (
            "_name_edit is not inside the 'Paper Setup' group box"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Rev 3: Fields tab (DD-18)
# ─────────────────────────────────────────────────────────────────────────────

class TestFieldsTab:
    """Fields tab: roster + intrinsics form + single-field preview (DD-18)."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    def test_roster_lists_all_with_placed_indicator(self, tmp_path, monkeypatch):
        """All fields should appear in the roster; seeded default has all placed (●)."""
        dlg = self._dlg(tmp_path, monkeypatch)
        lay = dlg.working.layout
        assert dlg._field_list.count() == len(lay.fields)
        assert all("●" in dlg._field_list.item(i).text()
                   for i in range(dlg._field_list.count()))

    def test_new_field_starts_unplaced(self, tmp_path, monkeypatch):
        """New fields start unplaced (○ indicator, id not in placed_ids)."""
        dlg = self._dlg(tmp_path, monkeypatch)
        n = len(dlg.working.layout.fields)
        dlg._new_field_btn.click()
        lay = dlg.working.layout
        assert len(lay.fields) == n + 1
        assert lay.fields[-1].id not in lay.placed_ids()
        assert "○" in dlg._field_list.item(n).text()

    def test_form_edit_writes_working_and_snapshots(self, tmp_path, monkeypatch):
        """Editing the name field writes working and pushes a snapshot."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(1)
        depth = len(dlg._undo_stack)
        dlg._fname_edit.setText("Renamed")
        dlg._fname_edit.editingFinished.emit()
        assert dlg.working.layout.fields[1].name == "Renamed"
        assert len(dlg._undo_stack) == depth + 1
        dlg.undo()
        assert dlg.working.layout.fields[1].name != "Renamed"

    def test_text_edit_multiline_commit(self, tmp_path, monkeypatch):
        """QPlainTextEdit text commits as multi-line text to the field."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(1)
        dlg._ftext_edit.setPlainText("Line1\nLine2")
        dlg._commit_field_text()
        assert dlg.working.layout.fields[1].text == "Line1\nLine2"

    def test_insert_token_at_cursor(self, tmp_path, monkeypatch):
        """_insert_token appends @[Key] at cursor and commits the text."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(1)
        dlg._ftext_edit.setPlainText("By ")
        cur = dlg._ftext_edit.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        dlg._ftext_edit.setTextCursor(cur)
        dlg._insert_token("Drawn By")
        assert dlg._ftext_edit.toPlainText() == "By @[Drawn By]"
        assert dlg.working.layout.fields[1].text == "By @[Drawn By]"

    def test_delete_placed_field_warns_and_removes(self, tmp_path, monkeypatch):
        """Deleting a placed field shows a warning, then removes it and unplaces it."""
        dlg = self._dlg(tmp_path, monkeypatch)
        monkeypatch.setattr(QMessageBox, "question", staticmethod(
            lambda *a, **kw: QMessageBox.StandardButton.Yes))
        dlg._field_list.setCurrentRow(1)
        fid = dlg.working.layout.fields[1].id
        dlg._delete_field_btn.click()
        lay = dlg.working.layout
        assert fid not in {f.id for f in lay.fields}
        assert fid not in lay.placed_ids()

    def test_single_field_preview_populates(self, tmp_path, monkeypatch):
        """Selecting a field populates the single-field preview scene."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(1)
        assert len(dlg._field_preview_scene.items()) > 0

    def test_kind_combo_swaps_inputs(self, tmp_path, monkeypatch):
        """Switching to 'revision_table' enables revision_rows and disables text/image."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(1)
        dlg._fkind_combo.setCurrentText("revision_table")
        assert dlg._frev_rows.isEnabled()
        assert not dlg._ftext_edit.isEnabled()
        assert dlg.working.layout.fields[1].kind == "revision_table"

    # (test_tabs_are_overview_drawingarea_fields removed — duplicate of
    #  TestArrangementsTab.test_tab_order.)

    def test_dup_field_gets_fresh_id_and_copy_suffix(self, tmp_path, monkeypatch):
        """Duplicate creates a new unplaced field with a fresh id and ' (copy)' suffix."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)
        orig_id = dlg.working.layout.fields[0].id
        orig_name = dlg.working.layout.fields[0].name
        n = len(dlg.working.layout.fields)
        dlg._dup_field_btn.click()
        lay = dlg.working.layout
        assert len(lay.fields) == n + 1
        new_f = lay.fields[-1]
        assert new_f.id != orig_id
        assert new_f.name == orig_name + " (copy)"
        assert new_f.id not in lay.placed_ids()

    def test_delete_unplaced_field_no_warning(self, tmp_path, monkeypatch):
        """Deleting an unplaced field does NOT show a warning dialog."""
        dlg = self._dlg(tmp_path, monkeypatch)
        # Add a new unplaced field
        dlg._new_field_btn.click()
        n_fields = len(dlg.working.layout.fields)
        new_row = n_fields - 1
        fid = dlg.working.layout.fields[new_row].id
        assert fid not in dlg.working.layout.placed_ids()

        question_called = []
        monkeypatch.setattr(QMessageBox, "question", staticmethod(
            lambda *a, **kw: question_called.append(1) or QMessageBox.StandardButton.Yes))

        dlg._field_list.setCurrentRow(new_row)
        dlg._delete_field_btn.click()
        assert not question_called, "No warning dialog for unplaced field"
        assert fid not in {f.id for f in dlg.working.layout.fields}

    def test_field_prop_no_snapshot_when_unchanged(self, tmp_path, monkeypatch):
        """_field_prop must NOT push a snapshot when the value is unchanged."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)
        f = dlg.working.layout.fields[0]
        current_name = f.name
        depth_before = len(dlg._undo_stack)
        dlg._field_prop("name", current_name)  # same value
        assert len(dlg._undo_stack) == depth_before, (
            "_field_prop must not snapshot when value is unchanged"
        )

    def test_field_preview_has_white_background(self, tmp_path, monkeypatch):
        """Single-field preview scene must contain a white rect behind the item."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(1)
        from PyQt6.QtWidgets import QGraphicsRectItem
        rects = [it for it in dlg._field_preview_scene.items()
                 if isinstance(it, QGraphicsRectItem)]
        assert any(r.brush().color().name() == "#ffffff" for r in rects)

    def test_fields_form_grouped_into_containers(self, tmp_path, monkeypatch):
        """The Fields intrinsics form is organised into four titled group boxes
        (grill 2026-08-04 item 5), and each widget lives in its expected group."""
        from PyQt6.QtWidgets import QGroupBox

        dlg = self._dlg(tmp_path, monkeypatch)
        groups = {g.title(): g for g in
                  dlg._field_form_widget.findChildren(QGroupBox)}
        assert {"Identity", "Content", "Text Style",
                "Fill & Border", "Cell Border"} <= set(groups)

        def owner(widget):
            p = widget.parent()
            while p is not None and not isinstance(p, QGroupBox):
                p = p.parent()
            return p.title() if p is not None else None

        assert owner(dlg._fname_edit) == "Identity"
        assert owner(dlg._fkind_combo) == "Identity"
        assert owner(dlg._ftext_edit) == "Content"
        assert owner(dlg._fimg_btn) == "Content"
        assert owner(dlg._frev_rows) == "Content"
        assert owner(dlg._ffont_combo) == "Text Style"
        assert owner(dlg._fbold) == "Text Style"
        assert owner(dlg._fitalic) == "Text Style"
        assert owner(dlg._ffield_fill_swatch) == "Fill & Border"
        assert owner(dlg._field_border_group._visible) == "Cell Border"

    def test_text_color_swatch_commits(self, tmp_path, monkeypatch):
        """Clicking the text-colour swatch commits text_color via one snapshot
        (grill 2026-08-04 item 6)."""
        from PyQt6.QtGui import QColor
        import firepro3d.titleblock_editor as tbe

        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)
        depth = len(dlg._undo_stack)
        monkeypatch.setattr(
            tbe.QColorDialog, "getColor",
            staticmethod(lambda *a, **kw: QColor("#0055ff")))
        dlg._ftext_color_swatch.click()
        assert dlg.working.layout.fields[0].text_color == "#0055ff"
        assert len(dlg._undo_stack) == depth + 1


# ─────────────────────────────────────────────────────────────────────────────
# Spec-review fixes (DD-13, border no-op, dup-name dedup)
# ─────────────────────────────────────────────────────────────────────────────

class TestSampleValuesKeysetMatchesBuildFieldValues:
    """DD-13: _SAMPLE_VALUES key set must cover build_field_values keys (minus __revisions__)."""

    def test_sample_values_keyset_matches_build_field_values(self):
        from firepro3d.paper_space import build_field_values, Sheet
        from firepro3d.titleblock_editor import _SAMPLE_VALUES

        vals = build_field_values(Sheet.create_default(), {})
        # Every key produced by build_field_values (except __revisions__) must
        # be present in _SAMPLE_VALUES so token-known/unknown behaves identically
        # in editor previews and on sheets.
        missing = set(vals) - {"__revisions__"} - set(_SAMPLE_VALUES)
        assert not missing, (
            f"Keys in build_field_values but absent from _SAMPLE_VALUES: {missing}"
        )
        # "Sheet No" must NOT be seeded (Insert-menu action is disabled; hand-typed
        # @[Sheet No] must render literally + warn in both preview and on sheets).
        assert "Sheet No" not in _SAMPLE_VALUES, (
            "'Sheet No' must not be in _SAMPLE_VALUES (not seeded by build_field_values)"
        )


class TestDuplicateNamesDeduped:
    """Duplicating the same field twice must produce 'X (copy)' then 'X (copy) 2'."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    def test_duplicate_names_deduped(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)
        orig_name = dlg.working.layout.fields[0].name

        # First duplicate → "X (copy)"
        dlg._dup_field_btn.click()
        names = [f.name for f in dlg.working.layout.fields]
        assert orig_name + " (copy)" in names, (
            f"First duplicate should be '{orig_name} (copy)'; got {names}"
        )

        # Select the copy just created (last item) and duplicate it
        dlg._field_list.setCurrentRow(len(dlg.working.layout.fields) - 1)
        dlg._dup_field_btn.click()
        names2 = [f.name for f in dlg.working.layout.fields]
        assert orig_name + " (copy) 2" in names2, (
            f"Second duplicate should be '{orig_name} (copy) 2'; got {names2}"
        )


class TestBorderGroupReemitNoSnapshot:
    """_on_field_border_changed with unchanged state must not push a snapshot."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    def test_border_group_reemit_no_snapshot(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        # Select first field (it will have a default border)
        dlg._field_list.setCurrentRow(0)
        f = dlg.working.layout.fields[0]
        # Load the group with the field's current border (matches current state)
        dlg._field_border_group.load(f.border)
        depth = len(dlg._undo_stack)
        # Call the handler — group state matches field border → must NOT snapshot
        dlg._on_field_border_changed()
        assert len(dlg._undo_stack) == depth, (
            "_on_field_border_changed must not push a snapshot when border is unchanged"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Quality-review fixes (QR-01..QR-04)
# ─────────────────────────────────────────────────────────────────────────────

class TestFontComboCommitSemantics:
    """QR-01: font combo must not snapshot per-keystroke; commits only on
    activated (dropdown pick) or editingFinished (typed entry)."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    def test_mid_type_no_snapshot(self, tmp_path, monkeypatch):
        """setText mid-typing must NOT push additional snapshots."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)
        depth_before = len(dlg._undo_stack)
        # Simulate partial typing — "Tim" then "Times New Roman"
        dlg._ffont_combo.lineEdit().setText("Tim")
        dlg._ffont_combo.lineEdit().setText("Times New Roman")
        assert len(dlg._undo_stack) == depth_before, (
            "Per-keystroke setText must not push snapshots; "
            f"depth went from {depth_before} to {len(dlg._undo_stack)}"
        )

    def test_editing_finished_commits_and_snapshots(self, tmp_path, monkeypatch):
        """editingFinished must commit the typed font family and push exactly one snapshot."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)
        depth_before = len(dlg._undo_stack)
        dlg._ffont_combo.lineEdit().setText("Times New Roman")
        dlg._ffont_combo.lineEdit().editingFinished.emit()
        f = dlg.working.layout.fields[0]
        assert f.font_family == "Times New Roman", (
            f"Expected font_family='Times New Roman', got {f.font_family!r}"
        )
        assert len(dlg._undo_stack) == depth_before + 1, (
            "editingFinished must push exactly one snapshot"
        )


class TestImageGroupUI:
    """Image controls (grill 2026-08-04 item 4): height input + larger thumb."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    def test_image_height_input_commits_and_snapshots_once(
            self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)
        depth = len(dlg._undo_stack)
        # Widget-driven edit (setText + editingFinished, like other dim tests)
        dlg._fimg_height.setText("12")
        dlg._fimg_height.editingFinished.emit()
        assert dlg.working.layout.fields[0].image_height_mm == 12.0
        assert len(dlg._undo_stack) == depth + 1

    def test_image_thumbnail_is_larger(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        assert dlg._fimg_thumb.width() >= 96
        assert dlg._fimg_thumb.height() >= 64


class TestInPlaceRosterUpdate:
    """QR-02: _field_prop must update roster in-place (no full rebuild),
    so _refresh_field_preview fires exactly once and image clear is reflected."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    def test_single_preview_refresh_per_field_prop(self, tmp_path, monkeypatch):
        """_field_prop for bold toggle must call _refresh_field_preview exactly once."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)

        call_count = [0]
        original = dlg._refresh_field_preview

        def counting_refresh():
            call_count[0] += 1
            original()

        monkeypatch.setattr(dlg, "_refresh_field_preview", counting_refresh)

        # Toggle bold (ensure it actually changes)
        f = dlg.working.layout.fields[0]
        dlg._fbold.setChecked(not f.bold)   # drives _field_prop("bold", ...)

        assert call_count[0] == 1, (
            f"_refresh_field_preview must be called exactly once per _field_prop, "
            f"got {call_count[0]}"
        )

    def test_clear_image_removes_thumbnail(self, tmp_path, monkeypatch):
        """Clicking the Clear image button must clear the thumb pixmap immediately."""
        import base64
        from PyQt6.QtGui import QImage, QPixmap
        from PyQt6.QtCore import QBuffer, QIODevice

        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)

        # Inject a 1×1 white pixel PNG as image_data
        img = QImage(1, 1, QImage.Format.Format_RGB32)
        img.fill(0xFFFFFF)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        data = base64.b64encode(bytes(buf.data())).decode("ascii")
        dlg._field_prop("image_data", data)
        # Confirm thumb is set
        assert dlg._fimg_thumb.pixmap() is not None and not dlg._fimg_thumb.pixmap().isNull(), (
            "Pre-condition: thumb should be set after image_data assigned"
        )

        # Now clear
        dlg._fimg_clear.click()

        pm = dlg._fimg_thumb.pixmap()
        assert pm is None or pm.isNull(), (
            "After clearing image, thumb must be null/empty"
        )


class TestFocusOutCommit:
    """QR-03a: FocusOut on _ftext_edit must commit the text to the field."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    def test_focus_out_commits_text(self, tmp_path, monkeypatch):
        """FocusOut event on _ftext_edit must call _commit_field_text."""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QFocusEvent

        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)
        dlg._ftext_edit.setPlainText("Via focus")

        from PyQt6.QtWidgets import QApplication
        QApplication.sendEvent(
            dlg._ftext_edit,
            QFocusEvent(QEvent.Type.FocusOut)
        )
        assert dlg.working.layout.fields[0].text == "Via focus", (
            "FocusOut must commit text to field; "
            f"got {dlg.working.layout.fields[0].text!r}"
        )


class TestBorderGroupWiring:
    """QR-03b: _field_border_group visible toggle must update field.border.visible
    and push exactly one snapshot."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    def test_border_visible_toggle_wired(self, tmp_path, monkeypatch):
        """Toggling the border visible checkbox must flip field.border.visible
        and push exactly one snapshot."""
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._field_list.setCurrentRow(0)
        f = dlg.working.layout.fields[0]
        orig_visible = f.border.visible
        depth_before = len(dlg._undo_stack)

        # Toggle the _visible checkbox in the border group
        dlg._field_border_group._visible.toggle()

        f_after = dlg.working.layout.fields[0]
        assert f_after.border.visible == (not orig_visible), (
            f"border.visible must flip from {orig_visible} to {not orig_visible}, "
            f"got {f_after.border.visible}"
        )
        assert len(dlg._undo_stack) == depth_before + 1, (
            f"Expected depth {depth_before + 1}, got {len(dlg._undo_stack)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Task 10: Arrangements tab assembly + dialog integration (DD-17)
# ─────────────────────────────────────────────────────────────────────────────

class TestArrangementsTab:
    """Arrangements tab: 3-column assembly + snapshot-per-gesture wiring."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    def _shown(self, tmp_path, monkeypatch):
        """Dialog shown with the Arrangements tab current + canvas fitted.

        mapFromScene needs a realized viewport for drag helpers to hit the
        intended cells, so show + resize + fit before synthesizing mouse
        events.
        """
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.resize(1100, 800)
        dlg.show()
        dlg._component_tabs.setCurrentWidget(dlg._arrange_tab)
        dlg._arrange_tab.canvas.fit_strip()
        return dlg

    @staticmethod
    def _rows(dlg):
        return [[s.field_id for s in r] for r in dlg.working.layout.rows]

    @staticmethod
    def _slot_of(dlg, fid):
        return next(s for row in dlg.working.layout.rows
                    for s in row if s.field_id == fid)

    def test_tab_order(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        tabs = [dlg._component_tabs.tabText(i)
                for i in range(dlg._component_tabs.count())]
        assert tabs == ["Overview", "Drawing Area", "Fields", "Arrangements"]

    def test_pool_shows_only_unplaced(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        assert dlg._arrange_tab.pool.count() == 0      # default: all placed
        dlg._new_field_btn.click()                     # adds unplaced field
        assert dlg._arrange_tab.pool.count() == 1

    def test_gesture_pushes_exactly_one_snapshot(self, tmp_path, monkeypatch):
        dlg = self._shown(tmp_path, monkeypatch)
        canvas = dlg._arrange_tab.canvas
        depth = len(dlg._undo_stack)
        before = self._rows(dlg)
        src = canvas.solved.cell_rects[1].center()
        dst = QPointF(src.x(), canvas.solved.cell_rects[4].bottom())
        _drag_on_canvas(canvas, src, dst)
        assert self._rows(dlg) != before               # layout mutated
        assert len(dlg._undo_stack) == depth + 1       # exactly one snapshot
        dlg.undo()
        assert self._rows(dlg) == before               # restored

    def test_delete_key_unplaces_and_snapshots(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        canvas = dlg._arrange_tab.canvas
        canvas.select_at(canvas.solved.cell_rects[1].center())
        fid = canvas.selected_field_id
        depth = len(dlg._undo_stack)
        QApplication.sendEvent(canvas, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Delete,
            Qt.KeyboardModifier.NoModifier))
        assert fid not in dlg.working.layout.placed_ids()
        assert len(dlg._undo_stack) == depth + 1
        assert dlg._arrange_tab.pool.count() == 1      # back in the pool
        # Roster indicator flipped to unplaced (○) for that field
        roster = {dlg._field_list.item(i).data(Qt.ItemDataRole.UserRole):
                  dlg._field_list.item(i).text()
                  for i in range(dlg._field_list.count())}
        assert "○" in roster[fid]

    def test_delete_stale_selection_noop(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        canvas = dlg._arrange_tab.canvas
        canvas.select_at(canvas.solved.cell_rects[1].center())
        fid = canvas.selected_field_id
        depth = len(dlg._undo_stack)
        canvas.unplaceRequested.emit(fid)      # real unplace: one snapshot
        canvas.unplaceRequested.emit(fid)      # stale re-emit: must be no-op
        assert len(dlg._undo_stack) == depth + 1

    def test_placement_props_follow_selection(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        tab = dlg._arrange_tab
        canvas = tab.canvas
        assert not tab.props_group.isEnabled()         # nothing selected yet
        canvas.select_at(canvas.solved.cell_rects[1].center())
        fid = canvas.selected_field_id
        slot = self._slot_of(dlg, fid)
        assert tab.props_group.isEnabled()
        assert abs(tab.min_height.value_mm() - slot.min_height_mm) < 1e-9
        depth = len(dlg._undo_stack)
        # Widget-driven edit (setText + editingFinished, like other dim tests)
        tab.min_height.setText("30")
        tab.min_height.editingFinished.emit()
        assert abs(slot.min_height_mm - 30.0) < 1e-6
        assert len(dlg._undo_stack) == depth + 1

    def test_sizing_change_writes_slot(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        tab = dlg._arrange_tab
        canvas = tab.canvas
        canvas.select_at(canvas.solved.cell_rects[1].center())
        fid = canvas.selected_field_id
        slot = self._slot_of(dlg, fid)
        assert slot.sizing == "static"
        depth = len(dlg._undo_stack)
        tab.sizing.setCurrentText("Dynamic")
        assert slot.sizing == "dynamic"
        assert len(dlg._undo_stack) == depth + 1
        # Clear selection, re-select the same field → combo shows Dynamic
        far = QPointF(canvas.solved.strip_rect.left() - 100,
                      canvas.solved.strip_rect.top())
        canvas.select_at(far)
        idx = canvas.solved.cell_field_ids.index(fid)
        canvas.select_at(canvas.solved.cell_rects[idx].center())
        assert tab.sizing.currentText() == "Dynamic"

    def test_strip_border_lives_on_arrangements(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        assert dlg._strip_border.parent() is not None
        w = dlg._strip_border
        while w is not None and w is not dlg._arrange_tab:
            w = w.parentWidget()
        assert w is dlg._arrange_tab

    def test_banner_shows_solver_warnings(self, tmp_path, monkeypatch):
        dlg = self._shown(tmp_path, monkeypatch)
        lay = dlg.working.layout
        fid = lay.rows[0][0].field_id
        lay.field_map()[fid].text = "@[Nope]"          # unknown token → warn
        dlg._arrange_tab.refresh(lay)
        assert dlg._arrange_tab.banner.isVisible()
        assert "Nope" in dlg._arrange_tab.banner.text()

    def test_mid_drag_esc_does_not_close_dialog(self, tmp_path, monkeypatch):
        dlg = self._shown(tmp_path, monkeypatch)
        canvas = dlg._arrange_tab.canvas
        vp = canvas.viewport()
        src = QPointF(canvas.mapFromScene(canvas.solved.cell_rects[1].center()))
        _mouse(vp, QEvent.Type.MouseButtonPress, src)
        _mouse(vp, QEvent.Type.MouseMove, src + QPointF(0, 40))
        assert canvas._dragging                        # drag armed
        QApplication.sendEvent(canvas, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier))
        assert dlg.isVisible()                         # dialog NOT closed
        assert not canvas._dragging                    # drag cancelled
        _mouse(vp, QEvent.Type.MouseButtonRelease, src + QPointF(0, 40),
               buttons=Qt.MouseButton.NoButton)
        # Esc with no drag in flight → normal dialog reject
        QApplication.sendEvent(dlg, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier))
        assert not dlg.isVisible()

    def test_undo_after_gesture_resyncs_pool(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg._new_field_btn.click()                     # unplaced pool field
        fid = dlg.working.layout.fields[-1].id
        assert dlg._arrange_tab.pool.count() == 1
        # Simulate a completed place gesture: snapshot → op → completed hook
        dlg.push_snapshot()
        place_field(dlg.working.layout, fid, 0)
        dlg._after_arrange_gesture()
        assert dlg._arrange_tab.pool.count() == 0
        dlg.undo()
        assert dlg._arrange_tab.pool.count() == 1      # pool re-synced
        assert fid not in dlg.working.layout.placed_ids()


# ─────────────────────────────────────────────────────────────────────────────
# Rev-3 review carry-ins: non-gesture canvas sync + placement-prop staleness
# ─────────────────────────────────────────────────────────────────────────────

class TestNonGestureCanvasSync:
    """Overview strip-geometry / border edits and undo must keep the
    Arrangements canvas and placement props in sync."""

    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.new_template()
        return dlg

    @staticmethod
    def _slot(dlg, fid):
        return next(s for row in dlg.working.layout.rows
                    for s in row if s.field_id == fid)

    def test_overview_strip_width_updates_canvas(self, tmp_path, monkeypatch):
        """A strip-width edit on the Overview tab re-solves the canvas."""
        dlg = self._dlg(tmp_path, monkeypatch)
        canvas = dlg._arrange_tab.canvas
        assert abs(canvas.solved.strip_rect.width() - 90.0) < 1e-6
        dlg._strip_width_edit.setText("70")
        dlg._strip_width_edit.editingFinished.emit()
        assert abs(dlg.working.layout.strip_width_mm - 70.0) < 1e-6
        assert abs(canvas.solved.strip_rect.width() - 70.0) < 1e-6, (
            "Arrangements canvas not re-solved after Overview strip-width edit"
        )

    def test_strip_border_toggle_resolves_canvas(self, tmp_path, monkeypatch):
        """Toggling strip border visibility re-solves the canvas (identity probe)."""
        dlg = self._dlg(tmp_path, monkeypatch)
        canvas = dlg._arrange_tab.canvas
        solved_before = canvas.solved
        dlg._strip_border._visible.toggle()
        assert not dlg.working.layout.strip_border.visible
        assert canvas.solved is not solved_before, (
            "Arrangements canvas not re-solved after strip-border change"
        )

    def test_undo_restores_placement_props_display(self, tmp_path, monkeypatch):
        """After undoing a min-height edit the DimensionEdit shows the
        reverted value (pre-fix: widget kept displaying the undone value)."""
        dlg = self._dlg(tmp_path, monkeypatch)
        tab = dlg._arrange_tab
        canvas = tab.canvas
        canvas.select_at(canvas.solved.cell_rects[1].center())
        fid = canvas.selected_field_id
        orig = self._slot(dlg, fid).min_height_mm
        tab.min_height.setText("30")
        tab.min_height.editingFinished.emit()
        assert abs(self._slot(dlg, fid).min_height_mm - 30.0) < 1e-6
        dlg.undo()
        # Model reverted…
        assert abs(self._slot(dlg, fid).min_height_mm - orig) < 1e-6
        # …and the widget displays the reverted value.
        assert abs(tab.min_height.value_mm() - orig) < 1e-6, (
            "Placement min-height widget shows a stale value after undo"
        )
